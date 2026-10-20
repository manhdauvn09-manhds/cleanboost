@echo off
REM ============================================================
REM git_pull.bat - Pull code moi nhat (branch main) cho repo PRIVATE.
REM Repo thuoc GitHub account: %REPO_ACCOUNT% (dat o duoi)
REM Account mac dinh cua may: %DEFAULT_ACCOUNT%
REM
REM QUAN TRONG: user.name/user.email chi doi danh tinh nguoi commit,
REM KHONG doi account dang nhap GitHub. Muon doi account dang nhap
REM qua HTTPS phai ghim credential.https://github.com.username.
REM Script switch ca 3 gia tri sang account cua repo truoc khi pull,
REM xong (ke ca khi loi) switch lai ve account mac dinh.
REM Cac lenh git config o day la muc LOCAL (chi trong repo nay).
REM Chi ap dung khi remote la HTTPS.
REM ============================================================
cd /d "%~dp0"
title CleanBoost - Pull latest source from GitHub
set EXITCODE=0
set REPO_ACCOUNT=manhdauvn09-manhds
set DEFAULT_ACCOUNT=manhdauvn09-manhds

where git >nul 2>nul
if errorlevel 1 (
  echo LOI: khong tim thay git trong PATH. Hay cai Git roi chay lai: https://git-scm.com/download/win
  pause
  exit /b 1
)

REM --- Switch sang account cua repo truoc khi pull ---
git config user.name %REPO_ACCOUNT%
git config user.email %REPO_ACCOUNT%@users.noreply.github.com
git config credential.https://github.com.username %REPO_ACCOUNT%
ver >nul
echo Da switch GitHub account sang: %REPO_ACCOUNT%

REM --- Phuong an du phong bang PAT (chi khi GCM khong nha credential) ---
REM Dat bien moi truong CB_GIT_TOKEN=<PAT classic, scope repo>
REM cua %REPO_ACCOUNT% tren MAY LOCAL roi chay lai file nay.
REM Token chi nam trong bien moi truong cua may, TUYET DOI khong ghi vao repo.
if defined CB_GIT_TOKEN (
  git remote set-url origin https://%REPO_ACCOUNT%:%CB_GIT_TOKEN%@github.com/%REPO_ACCOUNT%/cleanboost.git
  echo Da dung PAT tu bien moi truong CB_GIT_TOKEN cho remote.
)

echo Dang pull origin main...
git pull origin main
if errorlevel 1 (
  echo LOI: pull that bai. Kiem tra mang, quyen truy cap repo private, hoac credential.
  echo Goi y: neu Git Credential Manager van hoi password, dung phuong an PAT o tren.
  set EXITCODE=1
)

REM --- Tra remote ve URL sach (khong chua token) neu da dung PAT ---
if defined CB_GIT_TOKEN (
  git remote set-url origin https://github.com/%REPO_ACCOUNT%/cleanboost.git
)

REM --- Switch lai ve account mac dinh sau khi xong ---
git config user.name %DEFAULT_ACCOUNT%
git config user.email %DEFAULT_ACCOUNT%@users.noreply.github.com
git config credential.https://github.com.username %DEFAULT_ACCOUNT%
ver >nul
echo Da switch GitHub account ve mac dinh: %DEFAULT_ACCOUNT%

if "%EXITCODE%"=="0" (
  echo Pull xong. Ban dang o:
  git log --oneline -1
  if exist ".venv\Scripts\python.exe" (
    echo Dang dong bo thu vien neu can...
    ".venv\Scripts\python.exe" check_env.py
  )
  echo.
  echo DONE! Double-click run_cleanboost.bat de mo app.
)
pause
exit /b %EXITCODE%
