@echo off
rem Mo CleanBoost GUI (khong hien cua so console)
if not exist "%~dp0.venv\Scripts\pythonw.exe" (
  echo Chua cai dat! Chay setup_windows.bat truoc.
  pause
  exit /b 1
)
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0gui.py"
