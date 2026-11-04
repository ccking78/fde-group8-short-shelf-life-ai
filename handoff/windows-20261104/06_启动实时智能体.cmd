@echo off
setlocal
chcp 65001 >nul
"%~dp0.runtime\python\python.exe" -X utf8 -B "%~dp0tools\handoff.py" start %*
set "fde_exit=%errorlevel%"
if not "%fde_exit%"=="0" echo Please read the message above and docs\03_troubleshooting.md.
if /I not "%FDE_HANDOFF_NO_PAUSE%"=="1" pause
exit /b %fde_exit%
