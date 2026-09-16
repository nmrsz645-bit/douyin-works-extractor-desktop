@echo off
setlocal EnableExtensions
set "ROOT=%~dp0"
set "UPDATE_LOG=%ROOT%Update-App.log"

rem Run the updater first.  It never launches the GUI itself: this launcher
rem always starts the packaged EXE afterwards, even when update checking fails.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%Update-App.ps1" -Root "%ROOT%" >>"%UPDATE_LOG%" 2>&1

for %%F in ("%ROOT%app\*.exe") do (
  start "" "%%~fF"
  exit /b 0
)

echo Program files are incomplete. Please download and extract the full package again.
echo See "%UPDATE_LOG%" for update-check details.
pause
exit /b 1
