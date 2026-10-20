@echo off
REM ============================================================
REM git_push.bat - Commit + push thay doi len GitHub (branch main), repo PRIVATE.
REM Repo thuoc GitHub account: %REPO_ACCOUNT% (dat o duoi)
REM Account mac dinh cua may: %DEFAULT_ACCOUNT%
REM
REM QUAN TRONG: user.name/user.email chi doi danh tinh nguoi commit,
REM KHONG doi account dang nhap GitHub. Muon doi account dang nhap
REM qua HTTPS phai ghim credential.https://github.com.username.
REM Script switch ca 3 gia tri sang account cua repo truoc khi push,
REM xong (ke ca khi loi/huy) switch lai ve account mac dinh.
REM Cac lenh git config o day la muc LOCAL (chi trong repo nay).
REM Chi ap dung khi remote la HTTPS.
REM Luu y: file da co trong .gitignore (vi du .env*) se KHONG bi push.
REM ============================================================
cd /d "%~dp0"
title CleanBoost - Push source to GitHub
set EXITCODE=0
set REPO_ACCOUNT=manhdauvn09-manhds
set DEFAULT_ACCOUNT=manhdauvn09-manhds

where git >nul 2>nul
if errorlevel 1 (
  echo LOI: khong tim thay git trong PATH. Hay cai Git roi chay lai: https://git-scm.com/download/win
  pause
  exit /b 1
)

REM --- Switch sang account cua repo truoc khi push ---
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

echo Kiem tra thay doi local...
git status --short
REM status --porcelain bat ca file moi chua track (diff --quiet thi khong)
for /f %%I in ('git status --porcelain') do goto :has_changes
echo Khong co thay doi nao de commit. Khong lam gi ca.
goto :restore

:has_changes
set /p MSG=Nhap commit message (Enter = dung mac dinh "Update"):
if "%MSG%"=="" set MSG=Update

echo Dang add + commit...
git add -A
git commit -m "%MSG%"
if errorlevel 1 (
  echo LOI: commit that bai.
  set EXITCODE=1
  goto :restore
)

echo Dang push len origin main...
git push origin main
if errorlevel 1 (
  echo LOI: push that bai. Kiem tra mang, quyen truy cap repo private, hoac credential.
  echo Goi y: co the remote da co commit moi - chay git_pull.bat truoc roi chay lai file nay.
  echo Goi y: neu Git Credential Manager van hoi password, dung phuong an PAT o tren.
  set EXITCODE=1
  goto :restore
)

echo Push xong. Remote dang o:
git log --oneline -1

:restore
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
pause
exit /b %EXITCODE%
