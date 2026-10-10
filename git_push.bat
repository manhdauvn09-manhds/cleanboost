@echo off
chcp 65001 >nul
title CleanBoost - Push source len GitHub
cd /d "%~dp0"
where git >nul 2>nul
if errorlevel 1 (
  echo [LOI] Chua cai Git! Tai Git tai: https://git-scm.com/download/win
  pause
  exit /b 1
)
echo ============================================
echo  CleanBoost - Day source len GitHub
echo ============================================
git add -A
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value 2^>nul') do set dt=%%I
if defined dt (
  git commit -m "Cap nhat %dt:~0,4%-%dt:~4,2%-%dt:~6,2% %dt:~8,2%:%dt:~10,2%" 2>nul
) else (
  git commit -m "Cap nhat source" 2>nul
)
git push
if errorlevel 1 (
  echo.
  echo [LOI] Push that bai. Kiem tra mang hoac dang nhap lai GitHub.
) else (
  echo.
  echo XONG! Da push source len GitHub.
)
pause
