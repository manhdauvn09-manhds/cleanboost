@echo off
rem CleanBoost launcher - self-healing: installs new libraries automatically
rem after git pull, so you never need to re-run setup_windows.bat.
cd /d "%~dp0"

if not exist ".venv\Scripts\pythonw.exe" (
  echo No virtual environment found - running first-time setup...
  call setup_windows.bat
  if errorlevel 1 exit /b 1
)

rem Sync libraries if requirements.txt changed (e.g. after git pull)
".venv\Scripts\python.exe" check_env.py
if errorlevel 1 (
  echo [ERROR] Environment check failed. Try running setup_windows.bat.
  pause
  exit /b 1
)

start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0gui.py"
