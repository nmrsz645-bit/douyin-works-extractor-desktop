"""抖音作品提取桌面版入口：本地服务运行在后台，界面由原生窗口承载。"""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
import urllib.request
import logging
from pathlib import Path


def _paths() -> tuple[Path, Path]:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS), Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent, Path(__file__).resolve().parent


RESOURCE_DIR, APP_DIR = _paths()


def _show_native_error(title: str, message: str) -> None:
    """在 WebView 尚未启动时给出可读的 Windows 原生提示。"""
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, message, title, 0x10)
    except Exception:
        # 无窗口/非 Windows 调试环境不应因为提示框再次失败。
        pass


def _configure_windows_desktop_runtime() -> None:
    """在创建窗口前验证 pythonnet 所需的 Windows .NET Framework。"""
    if not getattr(sys, "frozen", False):
        return
    try:
        import clr
        clr.AddReference("System.Windows.Forms")
        from Microsoft.Win32 import SystemEvents
        del SystemEvents
    except Exception as exc:
        raise RuntimeError(
            "此程序需要 Microsoft .NET Framework 4.8.1 或更高版本才能创建桌面窗口。\n\n"
            "请先安装或修复 .NET Framework，然后重新启动程序：\n"
            "https://dotnet.microsoft.com/download/dotnet-framework\n\n"
            f"检测详情：{type(exc).__name__}: {exc}"
        ) from exc


def _report_startup_error(exc: BaseException) -> None:
    logging.exception("桌面窗口启动失败", exc_info=exc)
    message = str(exc)
    if "Microsoft .NET Framework 4.8.1" in message:
        pass
    elif ".NET" in message or "Python.Runtime" in message or "coreclr" in message.lower():
        message = (
            "程序的 .NET Desktop 运行环境无法启动。\n\n"
            "请重新下载并完整解压最新版安装包后，再双击 Start-App.cmd。\n"
            "若仍失败，请将 desktop.log 发给软件提供方。"
        )
    else:
        message = (
            "程序启动失败。\n\n"
            f"原因：{message[:300]}\n\n"
            "请关闭程序后重试；仍失败时请将 desktop.log 发给软件提供方。"
        )
    _show_native_error("抖音作品提取启动失败", message)


# 发布目录会在重新打包时被替换；用户数据必须放到独立、持久的本机目录。
USER_DATA_DIR = Path(os.environ.get("LOCALAPPDATA", str(APP_DIR))) / "抖音作品提取"
USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
os.chdir(USER_DATA_DIR)
sys.path.insert(0, str(RESOURCE_DIR))

# 发布包自带浏览器内核时优先使用它，避免依赖电脑上已有的 Playwright 浏览器。
_bundled_browsers = APP_DIR / "ms-playwright"
if _bundled_browsers.is_dir():
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(_bundled_browsers)
os.environ["DOUYIN_SESSION_DIR"] = str(USER_DATA_DIR / "douyin_session")


def _free_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_server(url: str) -> bool:
    for _ in range(100):
        try:
            with urllib.request.urlopen(url, timeout=0.5) as response:
                if response.status == 200:
                    return True
        except OSError:
            time.sleep(0.1)
    return False


def main() -> None:
    # 必须在 import webview（间接 import clr）之前执行。
    _configure_windows_desktop_runtime()
    # 数据与登录会话永远写在 EXE 所在目录，而不是 PyInstaller 的临时目录。
    import db
    db.DB_PATH = USER_DATA_DIR / "data" / "douyin_monitor.db"
    import config_manager
    config_manager.CONFIG_PATH = USER_DATA_DIR / "config.yaml"
    config_manager.DEFAULTS["paths"] = {
        "data_dir": str(USER_DATA_DIR / "data"),
        "session_dir": str(USER_DATA_DIR / "douyin_session"),
        "db_path": str(db.DB_PATH),
    }

    logging.basicConfig(
        filename=str(USER_DATA_DIR / "desktop.log"),
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    import uvicorn
    import webview
    from web.app import app

    port = _free_local_port()
    url = f"http://127.0.0.1:{port}"
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()

    # 先显示明确的加载页；服务器可用后再导航，避免 WebView 启动竞争时留下白屏。
    loading_html = "<html><body style='font-family:Microsoft YaHei;text-align:center;padding-top:180px;color:#555'><h2>抖音作品提取正在加载…</h2><p>正在启动本地服务，请稍候。</p></body></html>"
    window = webview.create_window("抖音作品提取", html=loading_html, width=1280, height=820, min_size=(960, 640))

    def _load_main_page():
        if _wait_for_server(url):
            window.load_url(url)
        else:
            logging.error("本地服务启动超时: %s", url)
            window.load_html("<html><body style='font-family:Microsoft YaHei;text-align:center;padding-top:180px;color:#b42318'><h2>程序服务启动失败</h2><p>请关闭程序后重新打开；仍失败时请查看 desktop.log。</p></body></html>")
    try:
        webview.start(_load_main_page)
    finally:
        server.should_exit = True


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        _report_startup_error(exc)
        raise SystemExit(1)
