@echo off
chcp 65001 >nul
title CleanBoost - Pull latest source from GitHub
cd /d "%~dp0"
where git >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Git not found! Download it from: https://git-scm.com/download/win
  pause
  exit /b 1
)
echo ============================================
echo  CleanBoost - Pull latest source from GitHub
echo ============================================
git pull
if errorlevel 1 (
  echo.
  echo [ERROR] Pull failed. Check your connection or repo access.
  pause
  exit /b 1
)
echo.
echo Source is up to date.
if exist ".venv\Scripts\python.exe" (
  echo Syncing libraries if needed...
  ".venv\Scripts\python.exe" check_env.py
)
echo.
echo DONE! Double-click run_cleanboost.bat to launch the app.
pause
