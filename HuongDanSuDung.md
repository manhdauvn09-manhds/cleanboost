# SÁCH HƯỚNG DẪN SỬ DỤNG CLEANBOOST

**Phiên bản:** 2.1 PRO (giao diện mới) — Ngày 10/10/2026
**Hỗ trợ:** Windows 10 / 11 (64-bit) và Linux (Ubuntu, Fedora...)

---

## 1. CleanBoost là gì?

CleanBoost là app giúp máy tính chạy nhẹ và gọn hơn, gồm 2 chức năng chính:

1. **Quản lý RAM/CPU:** xem app nào đang "ăn" RAM/CPU nhiều nhất, tắt (kill)
   an toàn các app không cần thiết, giải phóng RAM khẩn cấp khi máy chậm.
2. **Dọn file rác ổ C:** quét và dọn file tạm, cache, log, bộ cài cũ, dữ liệu
   thừa của app đã gỡ... theo 3 mức độ từ an toàn đến chuyên sâu.

**Nguyên tắc của app:** không bao giờ làm lỗi hệ điều hành. Mọi thao tác nguy
hiểm đều có xem trước, hỏi xác nhận, và file bị dọn được đưa vào **khu cách ly**
(khôi phục được trong 14 ngày) thay vì xóa ngay.

---

## 2. Cài đặt và khởi động (Windows)

### Bước 1 — Cài Python (chỉ làm 1 lần)

1. Tải Python 3.11 trở lên tại https://www.python.org/downloads/
2. Khi cài đặt, **nhớ tick chọn "Add python.exe to PATH"** rồi mới bấm Install.

### Bước 2 — Cài CleanBoost

1. Giải nén gói `cleanboost-windows.zip` ra một thư mục (ví dụ `D:\CleanBoost`).
2. Nhấn đúp file **`setup_windows.bat`**, chờ chạy xong (nó tự tạo môi trường
   và cài thư viện, mất khoảng 1–3 phút tùy mạng).

### Bước 3 — Mở app

- **Mở thường:** nhấn đúp **`run_cleanboost.bat`**
- **Mở với quyền Admin (khuyến nghị):** chuột phải vào
  **`run_cleanboost_admin.bat`** → **Run as administrator** → bấm **Yes** ở
  bảng UAC hiện ra.

> **Vì sao nên chạy bản Admin?** Nhiều chỗ dọn (Windows.old, WinSxS, Software
> Distribution...) cần quyền hệ thống. Chạy bản thường thì các mục đó sẽ hiện
> chữ "cần admin" và bị bỏ qua. App **không** tự bypass quyền — bảng UAC là của
> Windows hiện ra minh bạch, bạn luôn biết khi nào app chạy quyền cao.

### Trên Linux

```bash
cd cleanboost
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python gui.py            # mở giao diện
sudo .venv/bin/python gui.py       # bản root (đầy đủ tính năng)
```

---

## 3. Tổng quan giao diện

App có thanh điều hướng bên trái với 4 trang:

| Trang | Chức năng |
|-------|-----------|
| 📊 **Tổng quan** | Đồng hồ RAM/CPU/ổ đĩa, giải phóng RAM |
| ⚙️ **Tiến trình** | Xem và tắt các app đang chạy |
| 🧹 **Dọn rác** | Quét và dọn file rác theo 3 mức |
| 📦 **Khu cách ly** | Xem/khôi phục/xóa vĩnh viễn file đã dọn |

Góc trên bên phải có nút **"?"** — bấm vào để mở chính sách hướng dẫn này ngay
trong app. Thanh trạng thái dưới cùng hiện dung lượng khu cách ly và đường dẫn
file nhật ký.

---

## 4. Tab 📊 Tổng quan

### 4.1. Đồng hồ trạng thái

Ba đồng hồ tròn hiển thị theo thời gian thực (cập nhật mỗi 2 giây):

- **RAM** — % đã dùng và số GB cụ thể (ví dụ: 62% — 9.9/16 GB)
- **CPU** — % tải tổng
- **Ổ đĩa** — % đã dùng của ổ C (Windows) hoặc ổ `/` (Linux)

Đồng hồ chuyển vàng khi trên 70%, đỏ khi trên 90%.

Khi RAM ≥ 90% hoặc ổ đĩa còn trống ≤ 10%, một **banner đỏ** sẽ hiện ngay trên
cùng để cảnh báo bạn.

### 4.2. Nút "🧊 Dọn RAM nhẹ (không kill)"

Chỉ xả bộ nhớ đệm của RAM (working set + Standby List trên Windows, page
cache trên Linux). **Không tắt bất kỳ app nào** — an toàn tuyệt đối, nhưng hiệu
quả vừa phải. Phù hợp khi bạn không muốn động vào app đang mở.

> Nói thẳng: Windows vốn đã tự quản lý RAM tốt. Cách giải phóng RAM **thật sự**
> hiệu quả là tắt các app nặng bạn không dùng nữa (xem mục 4.3 và tab Tiến
> trình). Nút "dọn nhẹ" hữu ích nhất khi bạn chuẩn bị mở game/app nặng.

### 4.3. Nút "⚡ Giải phóng RAM khẩn cấp"

1. App liệt kê các app **của chính bạn** đang ngốn trên 200 MB RAM (đã tự loại
   trừ process hệ thống).
2. Một hộp thoại hiện ra cho bạn **tick chọn** app muốn tắt (mặc định tick hết).
3. Bấm "Kill đã chọn" → app tắt chúng rồi xả lại RAM.

**An toàn:** app không bao giờ kill process hệ thống (như `csrss.exe`,
`lsass.exe`...). Khi kill, app cho chương trình cơ hội tự đóng gọn gàng trước,
chỉ force kill khi app bị lì.

---

## 5. Tab ⚙️ Tiến trình

Bảng liệt kê các app/process đang chạy, sắp xếp theo mức ngốn RAM (mặc định).

- **Ô tìm kiếm:** gõ tên để lọc (ví dụ: `chrome`).
- **Bấm vào tiêu đề cột** (PID / RAM / CPU%) để đổi cách sắp xếp.
- **Nút "↻ Làm mới"** để tải lại danh sách.
- **Chọn một hoặc nhiều dòng**, rồi bấm:
  - **Kill đã chọn:** đóng nhẹ nhàng (khuyên dùng trước).
  - **🔴 Force kill đã chọn:** kết thúc ngay lập tức, dùng khi app bị treo.

**Các ký hiệu cần biết:**

- Dòng có chữ **⚠️** (ví dụ `explorer.exe`, `dwm.exe`): process hệ thống nhạy
  cảm — kill được nhưng có thể gây nháy màn hình/mất taskbar vài giây, app sẽ
  **hỏi lại bạn** trước khi kill.
- Process hệ thống nguy hiểm (như `System`, `csrss.exe`, `wininit.exe`) đã bị
  **ẩn khỏi bảng** — app từ chối kill để tránh làm sập Windows.

> ⚠️ Lưu ý: kill app đang mở có thể làm mất dữ liệu chưa lưu (văn bản chưa save,
> game chưa save...). Hãy save việc đang làm trước khi kill.

---

## 6. Tab 🧹 Dọn rác

Đây là tab quan trọng nhất. Quy trình gồm 4 bước:

**Bước 1 — Chọn mức dọn** (3 nút trên cùng):

| Mức | Đối tượng | Cần gì |
|-----|-----------|--------|
| 🟢 **Tiêu chuẩn** | File tạm của user, thùng rác, cache trình duyệt (Chrome/Edge/Cốc Cốc/Firefox...), cache Zalo/Discord/Teams/Spotify, thumbnail, DirectX shader cache, báo cáo lỗi | Chạy được ngay, an toàn tuyệt đối |
| 🟡 **Nâng cao** | Thêm: Windows Temp, cache Windows Update, dọn WinSxS bằng DISM, Windows.old, log hệ thống phình to, file dump khi crash, font/icon cache, lịch sử quét Defender, bộ cài driver còn sót (NVIDIA/AMD/Intel), cache Office, file tạm Steam, **dữ liệu mồ côi của app đã gỡ**, backup iTunes (tắt mặc định) | Nên chạy bản Admin |
| 🔴 **Chuyên sâu** | Thêm: quét pattern rác toàn ổ C, cache của dân dev (npm/pip/docker... — **tắt mặc định**), dọn Docker, và 3 mục **🔴 nguy hiểm** (tắt mặc định): **tắt Hibernate** (xóa file `hiberfil.sys`), **xóa restore point cũ** (giữ mới nhất), **DISM ResetBase** | Admin + xác nhận từng mục |

Mỗi rule đều ghi rõ **"ảnh hưởng khi xóa"** (ví dụ: "Trình duyệt tải lại ảnh — lần mở đầu chậm hơn") để bạn quyết định có cơ sở.

**Bước 2 — Bấm "🔍 Quét thử".** App chỉ **tính toán**, chưa xóa gì cả. Kết quả
hiện từng nhóm kèm dung lượng (ví dụ: "Log CBS — 4.2 GB").

**Bước 3 — Tick chọn** các nhóm muốn dọn (mặc định app đã tick sẵn các nhóm an
toàn theo rule; các nhóm "mồ côi" và mục 🔴 luôn **tắt mặc định** — bạn phải tự
bật). Tổng dung lượng sẽ dọn hiện ở góc trên.

**Bước 3b — Xem chi tiết trước khi xóa (khuyên dùng).** Mỗi nhóm có nút
**"Chi tiết"** — bấm vào để xem danh sách file/thư mục sẽ bị xóa (xếp theo dung
lượng lớn nhất), kèm giải thích **ảnh hưởng khi xóa** và cảnh báo (nếu có).
Hãy xem kỹ nhóm "dữ liệu mồ côi" trước khi dọn.

**Bước 4 — Bấm dọn** (2 lựa chọn):

- **🗑 "Xóa để giải phóng dung lượng" (khuyên dùng):** một hộp xác nhận hiện ra
  liệt kê từng nhóm + ảnh hưởng + cảnh báo đỏ (nếu có). Bấm xác nhận → app xóa
  và báo **số GB giải phóng THỰC TẾ** (đo trực tiếp từ ổ đĩa, khớp với những gì
  bạn thấy trong Explorer).
- **📦 "Cách ly (an toàn)":** file được **chuyển** vào khu cách ly, giữ 14 ngày,
  khôi phục được bất cứ lúc nào (xem mục 7). **Lưu ý:** file cách ly vẫn nằm
  trên cùng ổ đĩa nên **chưa giải phóng dung lượng** — muốn giải phóng thật thì
  vào tab Khu cách ly → Xóa vĩnh viễn.

**Lưu ý quan trọng:**

- Với các mục **🔴 nguy hiểm** (risk: high), app hiện **cảnh báo riêng** liệt kê
  rủi ro (ví dụ: "DISM ResetBase — không undo được") và chỉ dọn khi bạn xác
  nhận đã hiểu.
- Trước khi dọn ở **mức 2/3 trên Windows**, app tự tạo **System Restore Point**
  để bạn có thể rollback hệ thống nếu có gì bất thường.
- Chi tiết từng rule dọn nằm trong file `cleaner/rules.yaml` — bạn (hoặc cộng
  đồng) có thể thêm rule mới mà không cần sửa code.

---

## 7. Tab 📦 Khu cách ly

Nơi chứa mọi file/thư mục đã dọn (mặc định giữ **14 ngày**).

| Cột | Ý nghĩa |
|-----|---------|
| ID | Mã của lần cách ly |
| File gốc | Vị trí ban đầu của file |
| Dung lượng | Dung lượng đã thu hồi |
| Ngày cách ly | Thời điểm dọn |
| Rule | Rule nào đã dọn nó |

Các nút chức năng:

- **↩ Khôi phục đã chọn:** đưa file về đúng chỗ cũ trong 1 click. (Nếu chỗ cũ
  đã có file mới, app sẽ đổi tên file khôi phục thành `...restored_<mã>` để
  không ghi đè.)
- **🗑 Xóa vĩnh viễn đã chọn:** xóa hẳn khỏi khu cách ly (có hỏi xác nhận).
- **🧹 Dọn mục quá 14 ngày:** xóa vĩnh viễn các mục đã hết hạn lưu.
- **↻ Làm mới:** tải lại danh sách.

Vị trí lưu trên máy bạn:

- Windows: `C:\ProgramData\CleanBoost\Quarantine`
- Linux: `~/.local/share/cleanboost/quarantine`

---

## 8. Dọn tự động và theo dõi

Không cần mở app bằng tay, bạn có thể dùng dòng lệnh (mở `run_cli.bat` trên
Windows rồi gõ lệnh):

### 8.1. Dọn tự động định kỳ

```text
main.py schedule install    → đăng ký dọn tự động mỗi Chủ nhật lúc 03:00
main.py schedule status     → xem đã đăng ký chưa
main.py schedule remove     → gỡ lịch
```

Mỗi lần chạy, app tự quét mức 1 và dọn các nhóm an toàn vào khu cách ly, ghi
nhật ký đầy đủ. Trên Windows lịch chạy qua Task Scheduler, trên Linux qua cron.

Muốn chạy dọn tự động ngay 1 lần để thử:

```text
main.py clean --level 1 --all       → dọn hết nhóm mức 1 (vào khu cách ly)
auto_clean.py --dry-run             → chỉ xem sẽ dọn gì, không dọn thật
```

### 8.2. Theo dõi và cảnh báo

```text
main.py monitor --interval 60 --ram 90 --disk-free 10
```

App chạy nền, kiểm tra mỗi 60 giây: nếu RAM ≥ 90% hoặc ổ trống ≤ 10% sẽ hiện
**popup cảnh báo** (mỗi loại cảnh báo tối đa 1 lần / 30 phút để không spam).
Bấm `Ctrl+C` để dừng.

---

## 9. Dùng bằng dòng lệnh (đầy đủ)

| Lệnh | Chức năng |
|------|-----------|
| `main.py status` | Xem RAM/CPU/ổ đĩa |
| `main.py top -n 15` | Top process ngốn RAM (thêm `--sort cpu` để xếp theo CPU) |
| `main.py kill 1234` | Kill process theo PID (`--force` để force kill, nhiều PID cách nhau bởi dấu cách) |
| `main.py freeram --mode light` | Dọn RAM nhẹ, không kill |
| `main.py freeram --mode standard` | Gợi ý kill app ngốn RAM (có hỏi trước, `--yes` để kill hết) |
| `main.py scan --level 1` | Quét thử mức 1/2/3 (không xóa gì) |
| `main.py clean --level 2` | Dọn thật: hỏi chọn nhóm rồi hỏi Xóa (giải phóng GB thật) hay Cách ly; `--permanent` để xóa hẳn không hỏi, `--quarantine` để chỉ cách ly, `--all` để dọn hết |
| `main.py quarantine list` | Liệt kê khu cách ly |
| `main.py quarantine restore <id>` | Khôi phục 1 mục |
| `main.py quarantine purge` | Xóa mục quá 14 ngày |

---

## 10. An toàn & quyền riêng tư

- **5 lớp bảo vệ:** (1) danh sách process/đường dẫn cấm kill/xóa cứng;
  (2) luôn quét thử + xem trước trước khi dọn; (3) khu cách ly 14 ngày;
  (4) tự tạo System Restore Point trước khi dọn mức 2/3; (5) nhật ký mọi thao
  tác.
- **Nhật ký audit** nằm tại `C:\ProgramData\CleanBoost\actions.jsonl`
  (Windows) hoặc `~/.local/share/cleanboost/actions.jsonl` (Linux) — bạn luôn
  biết app đã làm gì với máy mình.
- App **chỉ chạy trên máy bạn**, không gửi dữ liệu đi đâu.

---

## 11. Xử lý sự cố thường gặp

**Nhấn đúp file .bat mà app không mở?**
→ Bạn chưa chạy `setup_windows.bat`, hoặc máy chưa cài Python / chưa tick
"Add python.exe to PATH". Làm lại mục 2.

**Hiện chữ "cần admin" và bị bỏ qua nhiều mục?**
→ Đóng app, chuột phải `run_cleanboost_admin.bat` → Run as administrator.

**Phần mềm diệt virus cảnh báo?**
→ Một số antivirus nhạy cảm với app xin quyền admin hoặc file .bat. Đây là app
mã nguồn mở chạy trên máy bạn; bạn có thể mở code ra xem. Nếu bị chặn, thêm
thư mục CleanBoost vào danh sách loại trừ (exclusion) của antivirus.

**Quét mức 3 chạy rất lâu?**
→ Bình thường — app đang duyệt toàn bộ ổ C và bỏ qua các thư mục hệ thống.
Hãy để nó chạy hết, đừng tắt giữa chừng.

**Dọn xong mà RAM vẫn cao / ổ vẫn đầy?**
→ RAM cao sau khi dọn nhẹ là bình thường (Windows dùng RAM trống làm cache).
Ổ đầy: thử quét mức 2 hoặc 3 — các "đại gia" GB thường nằm ở Windows.old,
MEMORY.DMP, log CBS.

**Lỡ dọn nhầm file?**
→ Mở tab 📦 Khu cách ly → chọn file → "Khôi phục đã chọn" (trong 14 ngày).

**Muốn gỡ CleanBoost?**
→ Chạy `main.py schedule remove` để gỡ lịch tự động (nếu đã đăng ký), rồi xóa
thư mục CleanBoost. Muốn sạch hẳn thì xóa thêm `C:\ProgramData\CleanBoost`
(nơi chứa khu cách ly và nhật ký).

---

*Hết sách hướng dẫn. Chúc bạn dọn máy vui vẻ! 🧹*
