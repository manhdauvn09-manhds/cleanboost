@echo off
rem CleanBoost - DEBUG launcher: shows the error message in the console
rem instead of hiding it (the normal launcher uses pythonw.exe, which
rem shows nothing when the app crashes at startup).
rem If the app does not start, double-click THIS file and send a
rem screenshot of the error to get help.
chcp 65001 >nul
title CleanBoost - Debug launch
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] No virtual environment found - run setup_windows.bat first.
  pause
  exit /b 1
)
echo Starting CleanBoost with visible console...
echo If the app crashes, the error below tells you why.
echo.
".venv\Scripts\python.exe" gui.py
echo.
echo [EXIT] The app closed with code %errorlevel%.
echo If you saw an error above, send a screenshot of it.
pause
