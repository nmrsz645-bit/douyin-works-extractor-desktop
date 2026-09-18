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


def _configure_bundled_dotnet() -> None:
    """让 pythonnet 使用发布包附带的 .NET Desktop Runtime。

    pywebview 的 Windows Forms 后端由 pythonnet 驱动。若只依赖用户电脑的
    .NET 环境，部分机器会在 Python.Runtime.Loader.Initialize 阶段失败。
    发布版把 x64 Windows Desktop Runtime 放在 app/dotnet，下列环境变量必须
    在 import webview（也就是 import clr）之前设置。
    """
    dotnet_dir = APP_DIR / "dotnet"
    runtime_config = dotnet_dir / "pythonnet.runtimeconfig.json"
    required_paths = (
        runtime_config,
        dotnet_dir / "host" / "fxr",
        dotnet_dir / "shared" / "Microsoft.NETCore.App",
        dotnet_dir / "shared" / "Microsoft.WindowsDesktop.App",
    )

    def _present(path: Path) -> bool:
        return path.is_file() or (path.is_dir() and any(path.iterdir()))

    if all(_present(path) for path in required_paths):
        os.environ["DOTNET_ROOT"] = str(dotnet_dir)
        os.environ["DOTNET_ROOT_X64"] = str(dotnet_dir)
        os.environ["PYTHONNET_RUNTIME"] = "coreclr"
        os.environ["PYTHONNET_CORECLR_RUNTIME_CONFIG"] = str(runtime_config)
        return

    # 开发时仍可使用电脑已有的运行环境；只有发给用户的冻结版必须完整自带。
    if getattr(sys, "frozen", False):
        missing = "\n".join(f"• {path.relative_to(APP_DIR)}" for path in required_paths if not _present(path))
        raise RuntimeError(
            "程序自带的 .NET 运行环境不完整，无法启动。\n\n"
            "请删除当前程序文件夹后，重新下载并完整解压最新版安装包；"
            "不要只复制 app 文件夹内的部分文件。\n\n"
            f"缺少的文件或目录：\n{missing}"
        )


def _report_startup_error(exc: BaseException) -> None:
    logging.exception("桌面窗口启动失败", exc_info=exc)
    message = str(exc)
    if ".NET" in message or "Python.Runtime" in message or "coreclr" in message.lower():
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
    _configure_bundled_dotnet()
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
