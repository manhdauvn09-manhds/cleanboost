@echo off
rem CleanBoost launcher with Admin rights (standard Windows UAC prompt).
rem Self-healing: installs new libraries automatically after git pull.
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

powershell -NoProfile -Command "Start-Process '%~dp0.venv\Scripts\pythonw.exe' -ArgumentList '\"%~dp0gui.py\"' -Verb RunAs"
