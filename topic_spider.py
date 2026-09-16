"""抖音话题视频采集：打开话题页，拦截搜索/话题列表接口并实时返回结果。"""
import asyncio
import logging
import random
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from playwright.async_api import async_playwright, Page

from spider import SESSION_DIR, DouyinSpider

logger = logging.getLogger(__name__)


def normalise_topic_input(raw: str) -> tuple[str, str]:
    """返回页面显示的话题名和实际要打开的抖音 URL。"""
    value = (raw or "").strip()
    if not value:
        raise ValueError("请输入话题名或话题链接")
    if value.startswith(("https://", "http://")):
        # 链接原样打开，适配抖音复制出的 challenge / hashtag / search 链接。
        return value, value
    topic = value.lstrip("#＃").strip()
    if not topic:
        raise ValueError("话题名不能为空")
    return f"#{topic}", f"https://www.douyin.com/search/{quote(topic)}?type=video"


class DouyinTopicSpider:
    """仅接收搜索/话题列表接口，避免把推荐流混入话题结果。"""

    def __init__(self, topic_input: str, *, start_ts: int | None = None,
                 end_ts: int | None = None, max_videos: int | None = None,
                 on_videos=None, headless: bool = False):
        from config_manager import load_config
        cfg = load_config()["spider"]
        self.topic, self.url = normalise_topic_input(topic_input)
        self.start_ts = start_ts
        self.end_ts = end_ts
        self.max_videos = max_videos
        self.on_videos = on_videos
        self.headless = headless
        self.max_scrolls = 80
        # 话题搜索在前几次滚动便应返回列表；避免接口未识别时长时间空滑。
        self.idle_limit = 10
        self.viewport = {"width": cfg["viewport_width"], "height": cfg["viewport_height"]}
        self.user_agent = cfg["user_agent"]
        self.locale = cfg["locale"]
        self.videos: list[dict] = []
        self._seen_ids: set[str] = set()
        self._stopped = False
        self._scroll_count = 0
        self._last_hit_scroll = 0
        self._error: str | None = None

    @staticmethod
    def _is_topic_response(url: str) -> bool:
        lower = url.lower()
        # 新版页面会从 /search 跳到 /jingxuan/search；实际 JSON 接口也可能
        # 使用 general/search，而不再是旧的 challenge/aweme 地址。
        return any(token in lower for token in ("/search", "/challenge/", "/hashtag/", "/jingxuan/"))

    @staticmethod
    def _find_awemes(payload: object) -> list[dict]:
        """兼容 aweme_list、data_list、aweme_info 等新版嵌套返回结构。"""
        found: list[dict] = []
        stack = [payload]
        visited: set[int] = set()
        while stack and len(visited) < 10000:
            value = stack.pop()
            if not isinstance(value, (dict, list)):
                continue
            identity = id(value)
            if identity in visited:
                continue
            visited.add(identity)
            if isinstance(value, dict):
                if value.get("aweme_id") and isinstance(value.get("video"), dict):
                    found.append(value)
                    continue
                stack.extend(value.values())
            else:
                stack.extend(value)
        return found

    @staticmethod
    def _to_video(aweme: dict) -> dict:
        stats = aweme.get("statistics", {})
        author = aweme.get("author", {})
        return {
            "video_id": str(aweme.get("aweme_id", "")),
            "title": aweme.get("desc", ""),
            "video_url": DouyinSpider._best_video_url(aweme),
            "create_time": int(aweme.get("create_time", 0) or 0),
            "view_count": int(stats.get("play_count", 0) or 0),
            "like_count": int(stats.get("digg_count", 0) or 0),
            "comment_count": int(stats.get("comment_count", 0) or 0),
            "author_name": author.get("nickname", ""),
            "author_sec_uid": str(author.get("sec_uid", "")),
            "fetched_at": datetime.now().isoformat(),
        }

    async def _on_response(self, response):
        if not self._is_topic_response(response.url):
            return
        try:
            data = await response.json()
        except Exception:
            return
        aweme_list = self._find_awemes(data)
        if not aweme_list:
            return
        new_videos = []
        for aweme in aweme_list:
            if self.max_videos is not None and len(self.videos) >= self.max_videos:
                self._stopped = True
                break
            video = self._to_video(aweme)
            if not video["video_id"] or video["video_id"] in self._seen_ids:
                continue
            publish_time = video["create_time"]
            if self.start_ts is not None and publish_time < self.start_ts:
                continue
            if self.end_ts is not None and publish_time > self.end_ts:
                continue
            self._seen_ids.add(video["video_id"])
            self.videos.append(video)
            new_videos.append(video)
            if self.max_videos is not None and len(self.videos) >= self.max_videos:
                self._stopped = True
                break
        if new_videos and self.on_videos:
            self.on_videos(new_videos)
        logger.info("[话题API] 候选 %d 条，新增 %d 条，累计 %d 条：%s",
                    len(aweme_list), len(new_videos), len(self.videos), response.url[:180])
        self._last_hit_scroll = self._scroll_count
        # 话题搜索结果按相关度排序，不可因某一条时间较早就提前停止。
        if not data.get("has_more", True) and new_videos:
            self._stopped = True

    async def _scroll_naturally(self, page: Page):
        await page.mouse.move(self.viewport["width"] // 2, self.viewport["height"] - 200)
        for _ in range(random.randint(2, 4)):
            await page.mouse.wheel(0, random.randint(450, 900))
            await page.wait_for_timeout(random.randint(180, 450))
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(random.randint(500, 1000))

    async def _has_service_exception(self, page: Page) -> bool:
        """识别抖音页面的服务异常页，避免继续无效滚动并加重风控。"""
        try:
            text = await page.locator("body").inner_text(timeout=1500)
        except Exception:
            return False
        return "服务异常" in text and ("重新刷新" in text or "加载数据" in text)

    async def _cool_down_if_needed(self, page: Page) -> bool:
        if await self._has_service_exception(page):
            self._error = (
                f"抖音页面提示服务异常，已安全停止；本次已保留 {len(self.videos)} 条结果。"
                "请等待 5 分钟后再重新提取，期间不要反复刷新页面。"
            )
            return True
        # 连续快速滑动容易触发服务异常。每 12 次滚动主动停顿一次，
        # 保持单浏览器、低频率的正常浏览节奏。
        if self._scroll_count and self._scroll_count % 12 == 0:
            pause_ms = random.randint(7000, 12000)
            logger.info("[话题限速] 已滚动 %d 次，暂停 %.1f 秒", self._scroll_count, pause_ms / 1000)
            await page.wait_for_timeout(pause_ms)
        return False

    async def fetch(self) -> list[dict]:
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=str(SESSION_DIR), headless=self.headless,
                viewport=self.viewport, user_agent=self.user_agent, locale=self.locale,
            )
            page = await context.new_page()
            page.on("response", lambda response: asyncio.create_task(self._on_response(response)))
            logger.info("[话题加载] %s", self.url)
            try:
                await page.goto(self.url, wait_until="domcontentloaded")
                for _ in range(self.max_scrolls):
                    if self._stopped:
                        break
                    if await self._cool_down_if_needed(page):
                        break
                    self._scroll_count += 1
                    await self._scroll_naturally(page)
                    if await self._cool_down_if_needed(page):
                        break
                    if self._scroll_count - self._last_hit_scroll >= self.idle_limit:
                        break
            except Exception as exc:
                self._error = f"话题页面打开失败: {exc}"
            finally:
                await context.close()
        if not self.videos and not self._error:
            self._error = "未收到话题作品列表（请在弹出浏览器完成登录或验证后重试）"
        return self.videos
