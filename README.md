# CleanBoost — Phase 4 (tự động hóa)

App quản lý RAM/CPU + dọn file rác, chạy trên Windows 10/11 và Linux.

## Chạy nhanh trên Windows (không cần build exe)

1. Cài Python 3.11+ tại https://www.python.org/downloads/ (nhớ tick **Add python.exe to PATH**).
2. Giải nén gói này, nhấn đúp **`setup_windows.bat`** — chờ chạy xong.
3. Nhấn đúp **`run_cleanboost.bat`** để mở app.
   Muốn full quyền (khuyến nghị): chuột phải `run_cleanboost_admin.bat` → **Run as administrator** (hiện UAC chuẩn).
4. Muốn 1 file `.exe` duy nhất: chạy `build\build_windows.ps1` trên máy Windows
   (file exe sẽ nằm ở `dist\CleanBoost.exe`, đã nhúng manifest admin).

## Tự động hóa (Phase 4)

```bash
# Dọn tự động headless (mức 1, chỉ rule low-risk, vào khu cách ly)
.venv/bin/python auto_clean.py --dry-run

# Đăng ký dọn tự động mỗi Chủ nhật 03:00 (Task Scheduler / cron)
.venv/bin/python main.py schedule install
.venv/bin/python main.py schedule status
.venv/bin/python main.py schedule remove

# Theo dõi RAM/ổ đĩa, popup cảnh báo khi RAM>90% hoặc ổ trống<10%
.venv/bin/python main.py monitor --interval 60 --ram 90 --disk-free 10
```

GUI cũng tự hiện banner đỏ ở tab Tổng quan khi RAM > 90% hoặc ổ đĩa còn trống < 10%.

## Mức dọn rác

- **Mức 1 — Tiêu chuẩn:** temp user, thùng rác, cache trình duyệt/Zalo/Discord,
  thumbnail, journal. An toàn tuyệt đối.
- **Mức 2 — Nâng cao** (khuyến nghị admin): Windows Temp, Windows Update cache
  (+ DISM StartComponentCleanup dọn WinSxS), Windows.old, log CBS, dump crash,
  font/icon cache, **dữ liệu mồ côi của app đã gỡ** (mặc định không tick),
  patch cache, Delivery Optimization. Linux: apt clean, snap cũ, /var/log,
  kernel cũ (giữ bản đang chạy + 2 bản mới), orphan.
- **Mức 3 — Chuyên sâu** (admin + xác nhận từng nhóm): quét pattern toàn ổ C,
  cache dev (npm/pip/cargo... — OPT-IN, mặc định tắt), docker prune,
  🔴 tắt Hibernate, 🔴 xóa restore point cũ (giữ mới nhất),
  🔴 DISM ResetBase (không undo được). Các mục 🔴 luôn tắt mặc định và có
  cảnh báo riêng trước khi dọn.

## Orphan detector

So sánh thư mục trong `%AppData%`/`%LocalAppData%`/`%ProgramData%`
(với registry Uninstall trên Windows; với .desktop trên Linux): thư mục nào
không khớp app đang cài + không dùng > 90 ngày + không có process đang chạy
trỏ tới → gắn cờ `high`/`medium`. Kết quả chỉ là gợi ý, luôn qua khu cách ly.

## Chạy giao diện (GUI)

```bash
.venv/bin/python gui.py
```

4 tab: **Tổng quan** (gauge RAM/CPU/ổ đĩa, nút giải phóng RAM khẩn cấp,
dọn RAM nhẹ) · **Tiến trình** (bảng process, tìm kiếm, sắp xếp, kill/force kill)
· **Dọn rác** (chọn mức 1/2/3 → quét thử → tick nhóm → dọn vào khu cách ly
hoặc xóa vĩnh viễn) · **Khu cách ly** (khôi phục 1-click, xóa vĩnh viễn,
dọn mục quá 14 ngày).

## Cài đặt

```bash
cd cleanboost
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Trên Windows: mở PowerShell, `cd` vào thư mục, dùng `.venv\Scripts\python.exe`
thay cho `.venv/bin/python`. Muốn dùng full tính năng (xả Standby List,
quét chỗ cần quyền hệ thống) thì **Run as Administrator**.

## Đóng gói 1 file .exe (chạy trên Windows)

```powershell
powershell -ExecutionPolicy Bypass -File build\build_windows.ps1
```

File `dist\CleanBoost.exe` có nhúng manifest `requireAdministrator` → mở lên
hiện UAC prompt chuẩn của Windows (không bypass).

## Cách dùng

```bash
# Xem RAM / CPU / ổ đĩa realtime
.venv/bin/python main.py status

# Top 15 process ngốn RAM nhất (ẩn process hệ thống nguy hiểm)
.venv/bin/python main.py top -n 15
.venv/bin/python main.py top --sort cpu

# Kill / force kill theo PID (process hệ thống bị chặn cứng)
.venv/bin/python main.py kill 1234
.venv/bin/python main.py kill 1234 5678 --force

# Giải phóng RAM
.venv/bin/python main.py freeram --mode light      # chỉ xả cache RAM, không kill gì
.venv/bin/python main.py freeram --mode standard   # + gợi ý kill app ngốn RAM (có hỏi trước)

# Quét thử file rác mức 1 (KHÔNG xóa gì cả — chỉ tính dung lượng)
.venv/bin/python main.py scan --level 1

# Dọn thật: mặc định chuyển vào khu cách ly (khôi phục được)
.venv/bin/python main.py clean --level 1 --all        # dọn hết, không hỏi chọn
.venv/bin/python main.py clean --level 1              # hỏi chọn từng nhóm
.venv/bin/python main.py clean --level 1 --all --permanent --yes   # xóa hẳn, không hỏi

# Quản lý khu cách ly
.venv/bin/python main.py quarantine list
.venv/bin/python main.py quarantine restore <id>
.venv/bin/python main.py quarantine purge --days 14
```

## An toàn (áp dụng cho mọi lệnh)

- **Không bao giờ kill**: `System`, `csrss.exe`, `wininit.exe`, `services.exe`,
  `lsass.exe`, `winlogon.exe`... (Windows) / PID 0,1,2 và kernel thread (Linux).
- **Hỏi lại trước khi kill**: `explorer.exe`, `dwm.exe`... (kill gây nháy màn hình).
- **Không bao giờ quét/xóa**: `C:\Windows\System32`, `WinSxS`,
  `C:\Windows\Installer`, `Program Files`, thư mục `Documents/Desktop/Downloads`.
- `scan` là dry-run thuần túy: chỉ đọc và tính toán.

## Thêm rule dọn rác mới

Sửa file `cleaner/rules.yaml` — thêm 1 rule là xong, không cần sửa code.
Phase 1 chỉ có rule mức 1 (tiêu chuẩn). Mức 2/3, orphan detector, DISM:
Phase 3 theo plan.

## Ghi chú Phase 1

- Telegram/Zalo: rule hiện tại chỉ xóa file `*.tmp`/`*.temp` để an toàn tuyệt
  đối; cache sâu hơn sẽ nghiên cứu kỹ cấu trúc thư mục ở Phase 3.
- `freeram --mode standard` trên Linux muốn `drop_caches` thì chạy bằng `sudo`.
