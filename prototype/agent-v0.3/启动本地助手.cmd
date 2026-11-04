@echo off
setlocal
chcp 65001 >nul
set "PYTHONDONTWRITEBYTECODE=1"
set "PYTHONIOENCODING=utf-8"
set "fde_task_python=F:\ChatGPT\work\runtimes\fde-data-simulation\.venv\Scripts\python.exe"
if not exist "%fde_task_python%" set "fde_task_python=python"
"%fde_task_python%" "%~dp0server.py" --open-browser
if errorlevel 1 pause
endlocal
