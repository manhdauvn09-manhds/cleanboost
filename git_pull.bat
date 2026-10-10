@echo off
chcp 65001 >nul
title CleanBoost - Pull source tu GitHub
cd /d "%~dp0"
where git >nul 2>nul
if errorlevel 1 (
  echo [LOI] Chua cai Git! Tai Git tai: https://git-scm.com/download/win
  pause
  exit /b 1
)
echo ============================================
echo  CleanBoost - Lay source moi nhat tu GitHub
echo ============================================
git pull
if errorlevel 1 (
  echo.
  echo [LOI] Pull that bai. Kiem tra mang hoac quyen truy cap repo.
) else (
  echo.
  echo XONG! Source da duoc cap nhat ban moi nhat.
  echo Neu requirements.txt co thu vien moi, chay lai setup_windows.bat.
)
pause
