@echo off
chcp 65001 >nul
title CleanBoost - Setup on Windows
echo ============================================
echo  CleanBoost - Setup on Windows
echo  (Only needed once. After that, just git pull and run.)
echo ============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python not found!
  echo Download Python 3.11+ from: https://www.python.org/downloads/
  echo IMPORTANT: tick "Add python.exe to PATH" during install.
  pause
  exit /b 1
)

echo [1/3] Creating virtual environment .venv ...
python -m venv .venv
if errorlevel 1 (
  echo [ERROR] Could not create .venv
  pause
  exit /b 1
)

echo [2/3] Installing libraries ...
call .venv\Scripts\pip install -r requirements.txt
if errorlevel 1 (
  echo [ERROR] Failed to install libraries. Check your connection and retry.
  pause
  exit /b 1
)

echo [3/3] Verifying ...
call .venv\Scripts\python check_env.py
call .venv\Scripts\python -c "import psutil, yaml, customtkinter; print('OK - all libraries present')"

echo.
echo ============================================
echo  DONE!
echo  - Open the app: double-click run_cleanboost.bat
echo  - Full rights (recommended): right-click
echo    run_cleanboost_admin.bat -^> Run as administrator
echo  - Schedule auto-clean: .venv\Scripts\python main.py schedule install
echo.
echo  Later updates: just run git_pull.bat, then double-click
echo  run_cleanboost.bat - new libraries install automatically.
echo ============================================
pause
