@echo off
rem Mo CleanBoost GUI voi quyen Admin (hien UAC prompt chuan cua Windows)
if not exist "%~dp0.venv\Scripts\pythonw.exe" (
  echo Chua cai dat! Chay setup_windows.bat truoc.
  pause
  exit /b 1
)
powershell -NoProfile -Command "Start-Process '%~dp0.venv\Scripts\pythonw.exe' -ArgumentList '\"%~dp0gui.py\"' -Verb RunAs"
