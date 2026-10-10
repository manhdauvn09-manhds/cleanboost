@echo off
rem CleanBoost CLI - self-healing launcher.
rem Usage: run_cli.bat status  |  run_cli.bat top  |  ...
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo No virtual environment found - running first-time setup...
  call setup_windows.bat
  if errorlevel 1 exit /b 1
)

".venv\Scripts\python.exe" check_env.py
if errorlevel 1 (
  echo [ERROR] Environment check failed. Try running setup_windows.bat.
  pause
  exit /b 1
)

"%~dp0.venv\Scripts\python.exe" "%~dp0main.py" %*
pause
