"""抖音单作品采集：逐条打开用户提供的公开作品链接并拦截作品详情数据。"""
import asyncio
import logging
import re
from datetime import datetime

from playwright.async_api import async_playwright, Page

from config_manager import load_config
from spider import SESSION_DIR, DouyinSpider
from topic_spider import DouyinTopicSpider

logger = logging.getLogger(__name__)


class DouyinSingleVideoSpider:
    """复用本程序已登录的可见浏览器，只接收当前链接对应的作品详情。"""

    _VIDEO_ID_RE = re.compile(r"/(?:video|note)/(\d+)")

    def __init__(self, on_video=None, on_progress=None):
        self.on_video = on_video
        self.on_progress = on_progress
        self.results: list[dict] = []
        self.failed: list[dict] = []

    @classmethod
    def _video_id_from_url(cls, url: str) -> str:
        match = cls._VIDEO_ID_RE.search(url or "")
        return match.group(1) if match else ""

    @staticmethod
    def _to_video(aweme: dict) -> dict:
        stats = aweme.get("statistics", {}) or {}
        author = aweme.get("author", {}) or {}
        return {
            "video_id": str(aweme.get("aweme_id", "") or ""),
            "title": str(aweme.get("desc", "") or ""),
            "video_url": DouyinSpider._best_video_url(aweme),
            "create_time": int(aweme.get("create_time", 0) or 0),
            "view_count": int(stats.get("play_count", 0) or 0),
            "like_count": int(stats.get("digg_count", 0) or 0),
            "share_count": int(stats.get("share_count", 0) or 0),
            "author_name": str(author.get("nickname", "") or ""),
            "fetched_at": datetime.now().isoformat(),
        }

    @staticmethod
    def _is_aweme_response(url: str) -> bool:
        return "/aweme/" in (url or "").lower()

    async def _fetch_one(self, page: Page, raw_url: str) -> tuple[dict | None, str | None]:
        """打开一个作品页，等待当前作品详情响应；不采纳页面旁路的推荐作品。"""
        captured: dict[str, dict] = {}
        detail_ids: set[str] = set()
        response_tasks: set[asyncio.Task] = set()
        captured_event = asyncio.Event()
        expected_id = self._video_id_from_url(raw_url)

        async def _consume(response):
            if not self._is_aweme_response(response.url):
                return
            try:
                payload = await response.json()
            except Exception:
                return
            is_detail = "detail" in response.url.lower()
            for aweme in DouyinTopicSpider._find_awemes(payload):
                video = self._to_video(aweme)
                video_id = video["video_id"]
                if not video_id:
                    continue
                captured[video_id] = video
                if is_detail:
                    detail_ids.add(video_id)
                if expected_id and video_id == expected_id:
                    captured_event.set()
                elif is_detail and not expected_id:
                    captured_event.set()

        def _on_response(response):
            task = asyncio.create_task(_consume(response))
            response_tasks.add(task)
            task.add_done_callback(response_tasks.discard)

        page.on("response", _on_response)
        try:
            await page.goto(raw_url, wait_until="domcontentloaded", timeout=30_000)
            expected_id = expected_id or self._video_id_from_url(page.url)
            # 正常详情接口一返回立刻继续；7 秒只是登录、验证或慢网络的上限。
            try:
                await asyncio.wait_for(captured_event.wait(), timeout=7)
            except asyncio.TimeoutError:
                pass
            if response_tasks:
                await asyncio.wait(response_tasks, timeout=1)
            if expected_id and expected_id in captured:
                return captured[expected_id], None
            if not expected_id and len(detail_ids) == 1:
                video_id = next(iter(detail_ids))
                return captured[video_id], None
            if expected_id:
                return None, "未收到此链接对应的作品详情（请在弹出浏览器完成登录或验证后重试）"
            return None, "无法识别作品链接，请粘贴抖音作品分享链接或 https://www.douyin.com/video/... 链接"
        except Exception as exc:
            return None, f"打开作品链接失败: {exc}"
        finally:
            page.remove_listener("response", _on_response)
            if response_tasks:
                await asyncio.wait(response_tasks, timeout=1)

    async def fetch(self, urls: list[str]) -> list[dict]:
        cfg = load_config()["spider"]
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=str(SESSION_DIR), headless=False,
                viewport={"width": cfg["viewport_width"], "height": cfg["viewport_height"]},
                user_agent=cfg["user_agent"], locale=cfg["locale"],
            )
            page = context.pages[0] if context.pages else await context.new_page()
            try:
                for raw_url in urls:
                    video, error = await self._fetch_one(page, raw_url)
                    if video:
                        self.results.append(video)
                        if self.on_video:
                            self.on_video(raw_url, video)
                        logger.info("[单作品] 已读取 %s", video["video_id"])
                    else:
                        self.failed.append({"input": raw_url, "error": error or "读取失败"})
                    if self.on_progress:
                        self.on_progress(len(self.results) + len(self.failed), raw_url, error)
            finally:
                await context.close()
        return self.results
