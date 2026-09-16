@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Update-App.ps1" -Root "%~dp0"
exit /b %ERRORLEVEL%
