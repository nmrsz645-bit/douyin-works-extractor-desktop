@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo 未找到运行环境。请重新部署此工具。
  pause
  exit /b 1
)

start "抖音作品提取" /min cmd /c ".venv\Scripts\python.exe monitor.py web --port 8091"
timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:8091"
