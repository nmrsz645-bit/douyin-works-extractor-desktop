"""作品提取的暂停与继续，不依赖真实抖音页面。"""

import asyncio
import json
import sys
import threading
import types
from html.parser import HTMLParser

import pytest

from web import app as web_app
import single_video_spider
import spider as author_spider
import topic_spider


def request(method: str, path: str, payload: dict | None = None):
    """直接调用真实 ASGI 应用，避免另装测试客户端。"""
    body = json.dumps(payload or {}).encode()
    sent = []
    delivered = False

    async def receive():
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": method, "scheme": "http", "path": path,
        "raw_path": path.encode(), "query_string": b"", "root_path": "",
        "headers": [(b"content-type", b"application/json")],
        "client": ("test", 1), "server": ("test", 80),
    }
    asyncio.run(web_app.app(scope, receive, send))
    status = next(message["status"] for message in sent if message["type"] == "http.response.start")
    content = b"".join(message.get("body", b"") for message in sent if message["type"] == "http.response.body")
    return status, json.loads(content)


@pytest.mark.parametrize("source,state_name,status_path", [
    ("author", "_extract_state", "/api/extract-status"),
    ("topic", "_topic_state", "/api/topic-status"),
    ("single", "_single_state", "/api/single-status"),
])
def test_pause_and_resume_active_extraction(source, state_name, status_path):
    state = getattr(web_app, state_name)
    original = state.copy()
    try:
        state.update({"running": True, "paused": False})
        status, _ = request("POST", "/api/extraction/pause", {"source": source})
        assert status == 200
        assert request("GET", status_path)[1]["paused"] is True

        status, _ = request("POST", "/api/extraction/resume", {"source": source})
        assert status == 200
        assert request("GET", status_path)[1]["paused"] is False
    finally:
        state.clear()
        state.update(original)


def test_inactive_extraction_cannot_be_paused():
    status, _ = request("POST", "/api/extraction/pause", {"source": "author"})
    assert status == 409


class FakePage:
    def __init__(self):
        self.url = ""

    def on(self, *_):
        pass

    async def goto(self, url, **_):
        self.url = url


class FakeBrowserContext:
    def __init__(self):
        self.pages = [FakePage()]

    async def close(self):
        pass

    async def new_page(self):
        return self.pages[0]


class FakePlaywright:
    def __init__(self, context):
        self.chromium = self
        self.context = context

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    async def launch_persistent_context(self, **_):
        return self.context


def test_single_extraction_waits_between_links_when_paused(monkeypatch, tmp_path):
    """首条完成后暂停，不得在继续前打开下一条链接。"""
    context = FakeBrowserContext()
    monkeypatch.setattr(single_video_spider, "async_playwright", lambda: FakePlaywright(context))
    monkeypatch.setattr(single_video_spider, "SESSION_DIR", tmp_path / "session")
    gate = threading.Event()
    gate.set()
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    opened = []

    async def fetch_one(_page, url):
        opened.append(url)
        if len(opened) == 1:
            first_started.set()
            await release_first.wait()
        return {"video_id": url}, None

    async def scenario():
        spider = single_video_spider.DouyinSingleVideoSpider(pause_gate=gate)
        monkeypatch.setattr(spider, "_fetch_one", fetch_one)
        task = asyncio.create_task(spider.fetch(["first", "second"]))
        await asyncio.wait_for(first_started.wait(), 1)
        gate.clear()
        release_first.set()
        await asyncio.sleep(0.15)
        assert opened == ["first"]
        gate.set()
        await asyncio.wait_for(task, 1)
        assert opened == ["first", "second"]

    asyncio.run(scenario())


@pytest.mark.parametrize("source", ["author", "topic"])
def test_scrolling_extraction_waits_between_scrolls_when_paused(source, monkeypatch, tmp_path):
    """一轮滚动完成后暂停，不得继续下一轮滚动。"""
    module = author_spider if source == "author" else topic_spider
    context = FakeBrowserContext()
    monkeypatch.setattr(module, "async_playwright", lambda: FakePlaywright(context))
    monkeypatch.setattr(module, "SESSION_DIR", tmp_path / "session")
    gate = threading.Event()
    gate.set()
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    scrolls = []

    async def scenario():
        if source == "author":
            crawler = author_spider.DouyinSpider(
                max_scrolls=2, idle_limit=20, page_load_wait=0, pause_gate=gate,
            )
        else:
            crawler = topic_spider.DouyinTopicSpider("测试话题", pause_gate=gate)
            crawler.max_scrolls = 2

        async def scroll(_page):
            scrolls.append(len(scrolls) + 1)
            if len(scrolls) == 1:
                first_started.set()
                await release_first.wait()

        async def no_cool_down(_page):
            return False

        monkeypatch.setattr(crawler, "_scroll_naturally", scroll)
        monkeypatch.setattr(crawler, "_cool_down_if_needed", no_cool_down)
        task = asyncio.create_task(
            crawler._fetch_attempt("test-sec-uid") if source == "author" else crawler.fetch()
        )
        await asyncio.wait_for(first_started.wait(), 1)
        gate.clear()
        release_first.set()
        await asyncio.sleep(0.15)
        assert scrolls == [1]
        gate.set()
        await asyncio.wait_for(task, 1)
        assert scrolls == [1, 2]

    asyncio.run(scenario())


def test_single_api_pause_stops_next_link_until_resume(monkeypatch, tmp_path):
    """页面操作控制实际接口任务，保留首条结果后再继续第二条。"""
    original = web_app._single_state.copy()
    context = FakeBrowserContext()
    monkeypatch.setattr(single_video_spider, "async_playwright", lambda: FakePlaywright(context))
    monkeypatch.setattr(single_video_spider, "SESSION_DIR", tmp_path / "session")
    monkeypatch.setattr(web_app, "clear_single_video_results", lambda: 0)
    saved = []
    monkeypatch.setattr(web_app, "upsert_single_video_result", lambda url, video, order: saved.append((url, order)))
    first_started = threading.Event()
    release_first = threading.Event()
    opened = []

    async def fetch_one(_self, _page, url):
        opened.append(url)
        if len(opened) == 1:
            first_started.set()
            await asyncio.to_thread(release_first.wait)
        return {"video_id": url.rsplit("/", 1)[-1]}, None

    monkeypatch.setattr(single_video_spider.DouyinSingleVideoSpider, "_fetch_one", fetch_one)

    async def scenario():
        task = asyncio.create_task(web_app.api_single_extract({
            "urls": "https://www.douyin.com/video/1\nhttps://www.douyin.com/video/2",
        }))
        try:
            assert await asyncio.to_thread(first_started.wait, 2)
            paused = await web_app.api_pause_extraction({"source": "single"})
            assert paused["paused"] is True
            release_first.set()
            await asyncio.sleep(0.15)
            assert opened == ["https://www.douyin.com/video/1"]
            assert saved == [("https://www.douyin.com/video/1", 1)]
        finally:
            release_first.set()
            await web_app.api_resume_extraction({"source": "single"})
            result = await asyncio.wait_for(task, 2)
            assert result["total"] == 2
            assert opened == ["https://www.douyin.com/video/1", "https://www.douyin.com/video/2"]

    try:
        asyncio.run(scenario())
    finally:
        web_app._single_state.clear()
        web_app._single_state.update(original)


def test_topic_api_pause_stops_next_scroll_until_resume(monkeypatch, tmp_path):
    original = web_app._topic_state.copy()
    context = FakeBrowserContext()
    monkeypatch.setattr(topic_spider, "async_playwright", lambda: FakePlaywright(context))
    monkeypatch.setattr(topic_spider, "SESSION_DIR", tmp_path / "session")
    monkeypatch.setattr(web_app, "clear_topic_results", lambda: 0)
    actual_constructor = web_app.DouyinTopicSpider

    def two_scrolls(*args, **kwargs):
        crawler = actual_constructor(*args, **kwargs)
        crawler.max_scrolls = 2
        return crawler

    monkeypatch.setattr(web_app, "DouyinTopicSpider", two_scrolls)
    first_started = threading.Event()
    release_first = threading.Event()
    scrolls = []

    async def scroll(_self, _page):
        scrolls.append(len(scrolls) + 1)
        if len(scrolls) == 1:
            first_started.set()
            await asyncio.to_thread(release_first.wait)

    async def no_cool_down(_self, _page):
        return False

    monkeypatch.setattr(topic_spider.DouyinTopicSpider, "_scroll_naturally", scroll)
    monkeypatch.setattr(topic_spider.DouyinTopicSpider, "_cool_down_if_needed", no_cool_down)

    async def scenario():
        task = asyncio.create_task(web_app.api_topic_extract({"topic": "测试话题", "top_count": 2}))
        try:
            assert await asyncio.to_thread(first_started.wait, 2)
            assert (await web_app.api_pause_extraction({"source": "topic"}))["paused"] is True
            release_first.set()
            await asyncio.sleep(0.15)
            assert scrolls == [1]
        finally:
            release_first.set()
            await web_app.api_resume_extraction({"source": "topic"})
            await asyncio.wait_for(task, 2)
            assert scrolls == [1, 2]

    try:
        asyncio.run(scenario())
    finally:
        web_app._topic_state.clear()
        web_app._topic_state.update(original)


def test_author_api_pause_stops_next_scroll_until_resume(monkeypatch, tmp_path):
    original = web_app._extract_state.copy()
    context = FakeBrowserContext()
    monkeypatch.setattr(author_spider, "async_playwright", lambda: FakePlaywright(context))
    monkeypatch.setattr(author_spider, "SESSION_DIR", tmp_path / "session")
    monkeypatch.setattr(web_app, "clear_extraction_results", lambda: 0)
    monkeypatch.setattr(web_app, "list_creators", lambda: [{
        "id": 1, "name": "测试作者", "sec_uid": "test-sec-uid", "enabled": 1,
    }])
    monkeypatch.setitem(sys.modules, "transcriber", types.SimpleNamespace(WHISPER_AVAILABLE=False))
    actual_constructor = web_app.DouyinSpider

    def two_scrolls(**kwargs):
        return actual_constructor(**{**kwargs, "max_scrolls": 2})

    monkeypatch.setattr(web_app, "DouyinSpider", two_scrolls)
    first_started = threading.Event()
    release_first = threading.Event()
    scrolls = []

    async def scroll(_self, _page):
        scrolls.append(len(scrolls) + 1)
        if len(scrolls) == 1:
            first_started.set()
            await asyncio.to_thread(release_first.wait)

    async def no_cool_down(_self, _page):
        return False

    monkeypatch.setattr(author_spider.DouyinSpider, "_scroll_naturally", scroll)
    monkeypatch.setattr(author_spider.DouyinSpider, "_cool_down_if_needed", no_cool_down)

    async def scenario():
        task = asyncio.create_task(web_app.api_run_fetch(
            creator_id=None, creator_ids=None, start_at="", end_at="", max_per_creator=2,
        ))
        try:
            assert await asyncio.to_thread(first_started.wait, 2)
            assert (await web_app.api_pause_extraction({"source": "author"}))["paused"] is True
            release_first.set()
            await asyncio.sleep(0.15)
            assert scrolls == [1]
        finally:
            release_first.set()
            await web_app.api_resume_extraction({"source": "author"})
            await asyncio.wait_for(task, 2)
            assert scrolls == [1, 2]

    try:
        asyncio.run(scenario())
    finally:
        web_app._extract_state.clear()
        web_app._extract_state.update(original)


@pytest.mark.parametrize("template", ["extract.html", "topic.html", "single.html"])
def test_each_extraction_page_exposes_pause_button(template):
    """三个提取页面都应提供用户可操作的暂停入口。"""
    class Buttons(HTMLParser):
        def __init__(self):
            super().__init__()
            self.controls = {}

        def handle_starttag(self, tag, attrs):
            if tag == "button":
                attributes = dict(attrs)
                self.controls[attributes.get("id")] = attributes

    parsed = Buttons()
    parsed.feed(web_app.render(template).body.decode("utf-8"))
    pause_button = parsed.controls.get("pause-extract")
    assert pause_button is not None
    assert pause_button.get("onclick") == "toggleExtractPause()"
