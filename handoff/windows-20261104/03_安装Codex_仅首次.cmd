@echo off
setlocal
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\install_codex.ps1"
set "fde_exit=%errorlevel%"
if /I not "%FDE_HANDOFF_NO_PAUSE%"=="1" pause
exit /b %fde_exit%
