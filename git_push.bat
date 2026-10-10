@echo off
chcp 65001 >nul
title CleanBoost - Push source to GitHub
cd /d "%~dp0"
where git >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Git not found! Download it from: https://git-scm.com/download/win
  pause
  exit /b 1
)
echo ============================================
echo  CleanBoost - Push source to GitHub
echo ============================================
git add -A
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value 2^>nul') do set dt=%%I
if defined dt (
  git commit -m "Update %dt:~0,4%-%dt:~4,2%-%dt:~6,2% %dt:~8,2%:%dt:~10,2%" 2>nul
) else (
  git commit -m "Update source" 2>nul
)
git push
if errorlevel 1 (
  echo.
  echo [ERROR] Push failed. Check your connection or GitHub login.
) else (
  echo.
  echo DONE! Source pushed to GitHub.
)
pause
