"""抖音博主视频采集模块 - 滚动触发 + API 拦截 (可复用)"""
import logging
import asyncio
import random
import os
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright, Page

SESSION_DIR = Path(os.environ.get("DOUYIN_SESSION_DIR", str(Path(__file__).parent / "douyin_session")))

logger = logging.getLogger(__name__)


@dataclass
class Profile:
    nickname: str
    avatar_url: str
    follower_count: int
    following_count: int
    total_likes: int
    bio: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Video:
    video_id: str
    title: str
    cover_url: str
    video_url: str
    duration_ms: int
    create_time: int
    like_count: int
    comment_count: int
    share_count: int
    view_count: int
    hashtags: list[str]
    fetched_at: str

    @property
    def public_url(self) -> str:
        """抖音公开播放链接 https://www.douyin.com/video/{video_id}"""
        if self.video_id:
            return f"https://www.douyin.com/video/{self.video_id}"
        return ""

    def to_dict(self) -> dict:
        return asdict(self)


class DouyinSpider:
    API_PATTERN = "/aweme/"
    PROFILE_PATTERNS = [
        "/user/profile/other/",
        "/user/info/",
        "/aweme/v1/web/user/profile/",
        "/web/api/v2/user/info/",
        "/aweme/v1/web/im/user/info/",
    ]

    def __init__(self, headless: bool | None = None, max_scrolls: int | None = None,
                 page_load_wait: int | None = None, idle_limit: int | None = None,
                 start_ts: int | None = None, end_ts: int | None = None,
                 on_videos=None, max_videos: int | None = None):
        from config_manager import load_config
        cfg = load_config()
        s = cfg["spider"]
        self.headless = headless if headless is not None else s["headless"]
        self.max_scrolls = max_scrolls if max_scrolls is not None else s["max_scrolls"]
        self.page_load_wait = page_load_wait if page_load_wait is not None else s["page_load_wait"]
        self.idle_limit = idle_limit if idle_limit is not None else s["scroll_idle_limit"]
        self.start_ts = start_ts
        self.end_ts = end_ts
        self.max_videos = max_videos
        self.target_sec_uid = ""
        # 每收到一页符合条件的作品就通知调用方；桌面版借此即时入库、即时显示。
        self.on_videos = on_videos
        self.videos: list[Video] = []
        self.profile: Profile | None = None
        self._seen_ids: set[str] = set()
        self._scroll_count = 0
        self._last_hit_scroll = 0
        self._stopped = False
        self._error: str | None = None

    @staticmethod
    def _best_video_url(aweme: dict) -> str:
        """优先选择作品接口提供的最高码率播放地址，不绕过权限或 DRM。"""
        video = aweme.get("video", {})
        candidates = []
        for item in video.get("bit_rate", []) or []:
            urls = item.get("play_addr", {}).get("url_list", []) or []
            if urls:
                candidates.append((int(item.get("bit_rate", 0) or 0), urls[0]))
        if candidates:
            return max(candidates, key=lambda value: value[0])[1]
        urls = video.get("play_addr", {}).get("url_list", []) or []
        return urls[0] if urls else ""

    @staticmethod
    def _parse_aweme(aweme: dict) -> Video:
        stats = aweme.get("statistics", {})
        vi = aweme.get("video", {})
        cover_list = vi.get("cover", {}).get("url_list", [])
        hashtags = [e.get("hashtag_name", "") for e in aweme.get("text_extra", []) if e.get("hashtag_name")]
        return Video(
            video_id=str(aweme.get("aweme_id", "")),
            title=aweme.get("desc", ""),
            cover_url=cover_list[-1] if cover_list else "",
            video_url=DouyinSpider._best_video_url(aweme),
            duration_ms=vi.get("duration", 0),
            create_time=aweme.get("create_time", 0),
            like_count=stats.get("digg_count", 0),
            comment_count=stats.get("comment_count", 0),
            share_count=stats.get("share_count", 0),
            view_count=stats.get("play_count", 0),
            hashtags=hashtags,
            fetched_at=datetime.now().isoformat(),
        )

    async def _on_response(self, response):
        # 抖音不同页面/版本的作品列表地址会变化；只要属于 aweme 请求并返回 aweme_list 即可识别。
        if self.API_PATTERN not in response.url:
            return
        try:
            data = await response.json()
        except Exception:
            return

        aweme_list = data.get("aweme_list", [])
        new = 0
        new_videos: list[Video] = []
        hit_before_start = False
        for aweme in aweme_list:
            if self.max_videos is not None and len(self.videos) >= self.max_videos:
                self._stopped = True
                break
            # 同一页面也会请求推荐流、搜索流等 /aweme/ 接口。只允许作者 sec_uid
            # 与当前主页完全一致的作品入库，绝不把别人的作品归到当前作者。
            author = aweme.get("author", {})
            author_sec_uid = str(author.get("sec_uid", ""))
            if not self.target_sec_uid or author_sec_uid != self.target_sec_uid:
                continue
            # Profile fallback: extract from first video's author
            if self.profile is None:
                if author:
                    avatar_list = (
                        author.get("avatar_medium", {}).get("url_list")
                        or author.get("avatar_thumb", {}).get("url_list")
                        or []
                    )
                    self.profile = Profile(
                        nickname=author.get("nickname", ""),
                        avatar_url=avatar_list[0] if avatar_list else "",
                        follower_count=author.get("follower_count", 0),
                        following_count=author.get("following_count", 0),
                        total_likes=author.get("total_favorited", 0),
                        bio=author.get("signature", ""),
                    )
                    logger.info("  [主页(fallback)] %s  粉丝:%s",
                                self.profile.nickname,
                                f"{self.profile.follower_count:,}")

            publish_time = int(aweme.get("create_time", 0) or 0)
            if self.start_ts is not None and publish_time < self.start_ts:
                hit_before_start = True
                continue
            if self.end_ts is not None and publish_time > self.end_ts:
                continue
            vid = str(aweme.get("aweme_id", ""))
            if vid and vid not in self._seen_ids:
                self._seen_ids.add(vid)
                video = self._parse_aweme(aweme)
                self.videos.append(video)
                new_videos.append(video)
                new += 1
                if self.max_videos is not None and len(self.videos) >= self.max_videos:
                    self._stopped = True
                    break

        if new_videos and self.on_videos:
            try:
                self.on_videos([video.to_dict() for video in new_videos])
            except Exception:
                # 即时显示失败不能打断浏览器继续采集；最终流程仍会记录错误。
                logger.exception("作品即时入库失败")

        gap = self._scroll_count - self._last_hit_scroll
        self._last_hit_scroll = self._scroll_count
        has_more = bool(data.get("has_more", False))
        logger.info("  [API] +%d/%d 条, 累计 %d, gap=%d %s",
                    new, len(aweme_list), len(self.videos), gap,
                    "(last page)" if not has_more else "")
        if not has_more and len(aweme_list) > 0:
            self._stopped = True
        # 抖音作品列表从新到旧；已经到达开始时间之前，继续翻页只会更早。
        if hit_before_start:
            self._stopped = True

    async def _on_profile_response(self, response):
        if self.profile is not None:
            return  # already captured
        url = response.url
        if not any(p in url for p in self.PROFILE_PATTERNS):
            return
        try:
            data = await response.json()
        except Exception:
            return
        user = data.get("user", {})
        if not user:
            return
        # 防止其它用户资料接口覆盖当前主页的作者资料。
        profile_sec_uid = str(user.get("sec_uid", ""))
        if profile_sec_uid and self.target_sec_uid and profile_sec_uid != self.target_sec_uid:
            return
        avatar_list = user.get("avatar_medium", {}).get("url_list") or user.get("avatar_thumb", {}).get("url_list") or []
        self.profile = Profile(
            nickname=user.get("nickname", ""),
            avatar_url=avatar_list[0] if avatar_list else "",
            follower_count=user.get("follower_count", 0),
            following_count=user.get("following_count", 0),
            total_likes=user.get("total_favorited", 0),
            bio=user.get("signature", ""),
        )
        logger.info("  [主页] %s  粉丝:%s",
                    self.profile.nickname,
                    f"{self.profile.follower_count:,}")

    async def _scroll_naturally(self, page: Page):
        vp = page.viewport_size or {"width": 1920, "height": 1080}
        await page.mouse.move(vp["width"] // 2, vp["height"] - 200)
        for _ in range(random.randint(2, 4)):
            await page.mouse.wheel(0, random.randint(400, 900))
            await page.wait_for_timeout(random.randint(200, 500))
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(random.randint(600, 1200))

    async def _has_service_exception(self, page: Page) -> bool:
        """识别抖音页面服务异常，避免继续空滑或频繁刷新。"""
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
        # 每 12 次滚动主动暂停，降低长时间连续访问触发限制的概率。
        if self._scroll_count and self._scroll_count % 12 == 0:
            pause_ms = random.randint(7000, 12000)
            logger.info("[主页限速] 已滚动 %d 次，暂停 %.1f 秒", self._scroll_count, pause_ms / 1000)
            await page.wait_for_timeout(pause_ms)
        return False

    async def fetch(self, sec_uid: str, max_retries: int = 3) -> list[Video]:
        """获取博主视频列表，支持自动重试（指数退避 + 抖动）。"""
        import time as _time
        for attempt in range(max_retries):
            try:
                return await self._fetch_attempt(sec_uid)
            except Exception as e:
                delay = (2 ** attempt) + random.uniform(0.5, 2.0)
                logger.warning("fetch 第 %d/%d 次失败: %s, %.1fs 后重试",
                               attempt + 1, max_retries, e, delay)
                if attempt < max_retries - 1:
                    await asyncio.sleep(delay)
                else:
                    self._error = f"fetch 失败（已重试 {max_retries} 次）: {e}"
                    logger.error(self._error)
                    return []

    async def _fetch_attempt(self, sec_uid: str) -> list[Video]:
        self.videos = []
        self.profile = None
        self._seen_ids = set()
        self._scroll_count = 0
        self._last_hit_scroll = 0
        self._stopped = False
        self._error = None
        self.target_sec_uid = sec_uid

        async with async_playwright() as p:
            from config_manager import load_config
            cfg = load_config()
            s = cfg["spider"]
            SESSION_DIR.mkdir(parents=True, exist_ok=True)
            context = await p.chromium.launch_persistent_context(
                user_data_dir=str(SESSION_DIR),
                headless=self.headless,
                viewport={"width": s["viewport_width"], "height": s["viewport_height"]},
                user_agent=s["user_agent"],
                locale=s["locale"],
            )
            page = await context.new_page()
            # Playwright 事件回调不会可靠地等待协程；显式创建任务，确保响应 JSON 会被解析。
            page.on("response", lambda response: asyncio.create_task(self._on_response(response)))
            page.on("response", lambda response: asyncio.create_task(self._on_profile_response(response)))

            url = f"https://www.douyin.com/user/{sec_uid}"
            logger.info("  [加载] %s", url)
            await page.goto(url, wait_until="domcontentloaded")
            # 页面骨架一出现就开始滚动。过去这里固定等 8 秒，造成看似卡死。
            if self.page_load_wait > 0:
                await asyncio.sleep(self.page_load_wait)

            # 不以首屏接口命中作为前提：有些主页首屏是预渲染的，实际滚动后才发作品列表请求。
            for i in range(self.max_scrolls):
                if self._stopped:
                    break
                if await self._cool_down_if_needed(page):
                    break
                self._scroll_count += 1
                await self._scroll_naturally(page)
                if await self._cool_down_if_needed(page):
                    break
                idle = self._scroll_count - self._last_hit_scroll
                if idle >= self.idle_limit:
                    break

            if not self.videos:
                self._error = "未收到作品列表(请在弹出浏览器完成登录或验证后重试)"

            await context.close()

        return self.videos
