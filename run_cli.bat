@echo off
rem Chay CleanBoost CLI: run_cli.bat status  |  run_cli.bat top  |  ...
if not exist "%~dp0.venv\Scripts\python.exe" (
  echo Chua cai dat! Chay setup_windows.bat truoc.
  pause
  exit /b 1
)
"%~dp0.venv\Scripts\python.exe" "%~dp0main.py" %*
pause
