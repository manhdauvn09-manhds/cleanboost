@echo off
chcp 65001 >nul
title CleanBoost - Cai dat tren Windows
echo ============================================
echo  CleanBoost - Cai dat tren Windows
echo ============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo [LOI] Chua cai Python!
  echo Tai Python 3.11+ tai: https://www.python.org/downloads/
  echo LUU Y: khi cai nho tick "Add python.exe to PATH".
  pause
  exit /b 1
)

echo [1/3] Tao moi truong ao .venv ...
python -m venv .venv
if errorlevel 1 (
  echo [LOI] Khong tao duoc .venv
  pause
  exit /b 1
)

echo [2/3] Cai thu vien (psutil, pyyaml, customtkinter) ...
call .venv\Scripts\pip install -r requirements.txt
if errorlevel 1 (
  echo [LOI] Cai thu vien that bai. Kiem tra mang roi chay lai.
  pause
  exit /b 1
)

echo [3/3] Kiem tra ...
call .venv\Scripts\python -c "import psutil, yaml, customtkinter; print('OK - thu vien day du')"

echo.
echo ============================================
echo  XONG!
echo  - Mo app: nhan doi run_cleanboost.bat
echo  - Muon full quyen (khuyen nghi): chuot phai
echo    run_cleanboost_admin.bat -^> Run as administrator
echo  - Dang ky don tu dong: .venv\Scripts\python main.py schedule install
echo ============================================
pause
