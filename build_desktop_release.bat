@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\pyinstaller.exe" (
  echo 未找到打包环境。请先完成部署。
  pause
  exit /b 1
)

rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul
.venv\Scripts\pyinstaller.exe --noconfirm --clean --windowed --onedir --name "抖音作品提取" --paths . --add-data "web;web" --collect-all webview --collect-all openpyxl --collect-all multipart desktop_app.py

if errorlevel 1 (
  echo 打包失败。
  pause
  exit /b 1
)

set "PW_SOURCE=%LOCALAPPDATA%\ms-playwright"
set "PW_TARGET=%CD%\dist\抖音作品提取\ms-playwright"
if exist "%PW_SOURCE%\chromium-1243" xcopy "%PW_SOURCE%\chromium-1243" "%PW_TARGET%\chromium-1243\" /E /I /Q /Y >nul
if exist "%PW_SOURCE%\chromium_headless_shell-1243" xcopy "%PW_SOURCE%\chromium_headless_shell-1243" "%PW_TARGET%\chromium_headless_shell-1243\" /E /I /Q /Y >nul
if exist "%PW_SOURCE%\ffmpeg-1011" xcopy "%PW_SOURCE%\ffmpeg-1011" "%PW_TARGET%\ffmpeg-1011\" /E /I /Q /Y >nul

echo.
echo 已生成：%CD%\dist\抖音作品提取\抖音作品提取.exe
pause
