"""CleanBoost PRO — GUI (CustomTkinter).

Layout: sidebar điều hướng + topbar + 4 trang + status bar.
Trang Dọn rác: xem chi tiết file trước khi xóa, confirm có liệt kê ảnh hưởng,
nút Xóa giải phóng dung lượng THẬT (đo trực tiếp từ ổ đĩa).
Nút "?" góc phải mở sách hướng dẫn sử dụng.
"""
import os
import sys
import threading
import tkinter as tk
from tkinter import ttk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import customtkinter as ctk  # noqa: E402

from core import privilege, system_info, process_manager, memory_cleaner  # noqa: E402
from cleaner import engine, scanner, quarantine as Q  # noqa: E402
from cleaner.clean import clean_rules, fmt_summary  # noqa: E402
from cleaner import action_log  # noqa: E402
from safety import protected  # noqa: E402

GB = 1024 ** 3
FONT = "Segoe UI"
MONO = "Consolas"
ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "assets")
LOGO_PATH = os.path.join(ASSETS_DIR, "logo.png")

# ------------------------- theme -------------------------
THEMES = {
    "dark": dict(BG="#0e1117", SIDEBAR="#141926", CARD="#1a2030",
                 CARD2="#232c42", LINE="#2a3348", TXT="#e8edf7",
                 MUT="#9aa7c2"),
    "light": dict(BG="#edf0f5", SIDEBAR="#ffffff", CARD="#ffffff",
                  CARD2="#dfe5ef", LINE="#c3ccdd", TXT="#17202f",
                  MUT="#5d6c88"),
}
C_ACC = "#4f8cff"
C_GRN = "#1a9e6b"
C_YLW = "#b8860b"
C_RED = "#e05252"

C_BG = C_SIDEBAR = C_CARD = C_CARD2 = C_LINE = C_TXT = C_MUT = ""


def _theme_cfg_path():
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        d = os.path.join(base, "CleanBoost")
    else:
        d = os.path.join(os.path.expanduser("~"), ".config", "cleanboost")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "theme.txt")


def _load_theme():
    try:
        with open(_theme_cfg_path(), encoding="utf-8") as f:
            m = f.read().strip()
            return m if m in THEMES else "dark"
    except OSError:
        return "dark"


def set_theme(mode):
    """Đổi theme và lưu lại. Các hằng C_* được gán lại."""
    global C_BG, C_SIDEBAR, C_CARD, C_CARD2, C_LINE, C_TXT, C_MUT
    t = THEMES[mode]
    C_BG, C_SIDEBAR, C_CARD = t["BG"], t["SIDEBAR"], t["CARD"]
    C_CARD2, C_LINE, C_TXT, C_MUT = t["CARD2"], t["LINE"], t["TXT"], t["MUT"]
    ctk.set_appearance_mode(mode)
    try:
        with open(_theme_cfg_path(), "w", encoding="utf-8") as f:
            f.write(mode)
    except OSError:
        pass


set_theme(_load_theme())
ctk.set_default_color_theme("blue")


def _pick_font(candidates):
    """Chọn font đầu tiên có trên máy (đảm bảo hiển thị tiếng Việt)."""
    try:
        import tkinter.font as tkfont
        avail = set(tkfont.families())
    except Exception:  # noqa: BLE001
        avail = set()
    for c in candidates:
        if c in avail:
            return c
    return candidates[0]


def _init_fonts():
    global FONT, MONO
    FONT = _pick_font(["Segoe UI", "Arial", "Tahoma", "Verdana", "DejaVu Sans"])
    MONO = _pick_font(["Consolas", "Courier New", "DejaVu Sans Mono"])


def _bg(fn):
    threading.Thread(target=fn, daemon=True).start()


def _fmt_gb(n):
    return f"{n / GB:.2f} GB"


# ------------------------- widgets -------------------------

class RingGauge(tk.Canvas):
    """Đồng hồ tròn hiển thị %."""

    def __init__(self, parent, title, size=168):
        super().__init__(parent, width=size, height=size, bg=C_CARD,
                         highlightthickness=0)
        self._s = size
        self._title = title
        self.set(0, "")

    def set(self, pct, subtitle=""):
        self.delete("all")
        s, cx, cy, r = self._s, self._s / 2, self._s / 2, self._s / 2 - 20
        pct = max(0, min(100, pct))
        self.create_arc(cx - r, cy - r, cx + r, cy + r, start=90, extent=359.9,
                        style="arc", outline=C_LINE, width=13)
        color = C_ACC if pct < 70 else (C_YLW if pct < 90 else C_RED)
        if pct > 0:
            self.create_arc(cx - r, cy - r, cx + r, cy + r, start=90,
                            extent=-359.9 * pct / 100, style="arc",
                            outline=color, width=13)
        self.create_text(cx, cy - 10, text=f"{pct:.0f}%",
                         fill=C_TXT, font=(FONT, 24, "bold"))
        self.create_text(cx, cy + 18, text=self._title,
                         fill=C_MUT, font=(FONT, 12))
        if subtitle:
            self.create_text(cx, cy + 38, text=subtitle,
                             fill=C_MUT, font=(FONT, 10))


def _center_on(win, parent):
    """Căn Toplevel vào giữa cửa sổ cha."""
    try:
        parent.update_idletasks()
        win.update_idletasks()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        px, py = parent.winfo_x(), parent.winfo_y()
        ww, hh = win.winfo_width(), win.winfo_height()
        if ww < 50:
            ww = 600
        if hh < 50:
            hh = 400
        x = px + max(0, (pw - ww) // 2)
        y = py + max(0, (ph - hh) // 2)
        win.geometry(f"+{x}+{y}")
    except Exception:  # noqa: BLE001
        pass


def _make_modal(win, parent):
    """Biến Toplevel thành popup modal căn giữa màn hình chính.

    Phải đóng popup mới thao tác được màn hình chính.
    """
    try:
        win.transient(parent)
    except Exception:  # noqa: BLE001
        pass
    _center_on(win, parent)
    try:
        win.grab_set()
    except Exception:  # noqa: BLE001
        pass


def _dark_tree(parent):
    style = ttk.Style(parent)
    try:
        style.theme_use("clam")
    except Exception:  # noqa: BLE001
        pass
    style.configure("Treeview", background=C_CARD, foreground=C_TXT,
                    fieldbackground=C_CARD, rowheight=28, borderwidth=0,
                    font=(FONT, 11))
    style.configure("Treeview.Heading", background=C_CARD2,
                    foreground=C_TXT, relief="flat", font=(FONT, 11, "bold"))
    style.map("Treeview", background=[("selected", C_ACC)],
              foreground=[("selected", "#ffffff")])
    return ttk.Treeview(parent)


# ------------------------- dialogs -------------------------

class DetailDialog(ctk.CTkToplevel):
    """Xem chi tiết file sẽ bị xóa của 1 nhóm (trước khi xóa)."""

    def __init__(self, master, res):
        super().__init__(master)
        rule = res["rule"]
        self.title(f"Chi tiết — {rule['name']}")
        self.geometry("760x520")
        _make_modal(self, master)
        self.res = res

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=16, pady=(14, 6))
        ctk.CTkLabel(head, text=rule["name"], font=(FONT, 16, "bold"),
                     wraplength=700, justify="left").pack(anchor="w")
        info = rule.get("impact", "")
        if rule.get("warning"):
            info = f"⚠️ {rule['warning']}\n{info}"
        if rule.get("note"):
            info += f"\nℹ️ {rule['note']}"
        ctk.CTkLabel(head, text=info.strip(), text_color=C_MUT,
                     font=(FONT, 12), wraplength=700,
                     justify="left").pack(anchor="w", pady=(4, 0))

        self.status = ctk.CTkLabel(self, text="Đang tính dung lượng từng file...",
                                   text_color=C_MUT)
        self.status.pack(padx=16, pady=4, anchor="w")

        self.tree = _dark_tree(self)
        self.tree["columns"] = ("size",)
        self.tree.heading("#0", text="File / thư mục")
        self.tree.heading("size", text="Dung lượng")
        self.tree.column("#0", width=560)
        self.tree.column("size", width=120)
        self.tree.pack(fill="both", expand=True, padx=16, pady=6)

        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.pack(fill="x", padx=16, pady=(0, 14))
        self.foot_lbl = ctk.CTkLabel(foot, text="", text_color=C_MUT)
        self.foot_lbl.pack(side="left")
        ctk.CTkButton(foot, text="Đóng", width=100,
                      command=self.destroy).pack(side="right")
        _bg(self._load)

    def _load(self):
        res, rule = self.res, self.res["rule"]
        rows = []
        if res.get("orphans"):
            for o in res["orphans"]:
                rows.append((f"[{o['confidence']}] {o['path']}", o["size"]))
        else:
            paths = res.get("paths") or []
            # tính size cho tối đa 5000 file đầu để dialog không treo
            for fp in paths[:5000]:
                try:
                    rows.append((fp, os.path.getsize(fp)))
                except OSError:
                    continue
        rows.sort(key=lambda x: x[1], reverse=True)
        total_n = len(res.get("orphans") or res.get("paths") or [])
        self.after(0, lambda: self._fill(rows, total_n))

    def _fill(self, rows, total_n):
        show = rows[:300]
        for p, s in show:
            tag = "big" if s > 100 * 1024 * 1024 else ""
            self.tree.insert("", "end", text=p,
                             values=(_fmt_gb(s),), tags=(tag,))
        self.tree.tag_configure("big", foreground=C_YLW)
        self.status.pack_forget()
        extra = f" (trong {min(total_n, 5000)} mục đã duyệt)" if total_n > len(show) else ""
        self.foot_lbl.configure(
            text=f"Hiển thị {len(show)}/{total_n} mục lớn nhất{extra} • "
                 f"Tổng nhóm: {_fmt_gb(self.res['size'])}")


class ConfirmCleanDialog(ctk.CTkToplevel):
    """Hộp xác nhận xóa: liệt kê nhóm + ảnh hưởng + cảnh báo đỏ."""

    def __init__(self, master, items, permanent):
        """items: list of (rule, size). permanent True = xóa hẳn."""
        super().__init__(master)
        self.result = False
        total = sum(s for _, s in items)
        self.title("Xác nhận dọn dẹp")
        self.geometry("620x480")
        _make_modal(self, master)

        ctk.CTkLabel(self,
                     text="🗑 Xóa vĩnh viễn" if permanent else "📦 Chuyển vào khu cách ly",
                     font=(FONT, 17, "bold"),
                     text_color=C_RED if permanent else C_YLW).pack(pady=(16, 4))
        ctk.CTkLabel(self, text=f"Tổng: {_fmt_gb(total)} — {len(items)} nhóm",
                     font=(FONT, 13, "bold"), text_color=C_ACC).pack()

        box = ctk.CTkScrollableFrame(self, label_text="Các nhóm sẽ dọn")
        box.pack(fill="both", expand=True, padx=16, pady=10)
        for rule, size in items:
            f = ctk.CTkFrame(box, fg_color=C_CARD2)
            f.pack(fill="x", padx=6, pady=4)
            top = ctk.CTkFrame(f, fg_color="transparent")
            top.pack(fill="x", padx=10, pady=(8, 0))
            ctk.CTkLabel(top, text=rule["name"], font=(FONT, 12, "bold"),
                         wraplength=380, justify="left").pack(side="left")
            ctk.CTkLabel(top, text=_fmt_gb(size), text_color=C_ACC,
                         font=(FONT, 12, "bold")).pack(side="right")
            ctk.CTkLabel(f, text=rule.get("impact", ""), text_color=C_MUT,
                         font=(FONT, 11), wraplength=540,
                         justify="left").pack(anchor="w", padx=10, pady=(2, 2))
            if rule.get("warning"):
                ctk.CTkLabel(f, text=f"⚠️ {rule['warning']}",
                             text_color=C_RED, font=(FONT, 11, "bold"),
                             wraplength=540, justify="left").pack(anchor="w", padx=10, pady=(0, 8))

        note = ("File bị xóa KHÔNG khôi phục được." if permanent
                else "File được chuyển vào khu cách ly (giữ 14 ngày, khôi phục "
                     "được) — LƯU Ý: vẫn chiếm dung lượng ổ đĩa cho đến khi "
                     "bạn xóa vĩnh viễn trong tab Khu cách ly.")
        ctk.CTkLabel(self, text=note, text_color=C_MUT, font=(FONT, 11),
                     wraplength=560, justify="left").pack(padx=16, pady=4)

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(4, 16))
        ctk.CTkButton(row, text="Hủy", fg_color=C_CARD2,
                      command=self._no).pack(side="right", padx=6)
        ctk.CTkButton(row, text="🗑 Xóa vĩnh viễn" if permanent else "📦 Cách ly",
                      fg_color="#b91c1c" if permanent else "#b45309",
                      hover_color="#991b1b" if permanent else "#92400e",
                      command=self._yes).pack(side="right", padx=6)

    def _yes(self):
        self.result = True
        self.destroy()

    def _no(self):
        self.destroy()


class ResultDialog(ctk.CTkToplevel):
    """Hiện kết quả dọn (dùng font mono để dễ đọc)."""

    def __init__(self, master, title, text):
        super().__init__(master)
        self.title(title)
        self.geometry("560x380")
        _make_modal(self, master)
        ctk.CTkLabel(self, text=title, font=(FONT, 15, "bold")).pack(pady=(14, 6))
        box = ctk.CTkTextbox(self, font=(MONO, 12), wrap="word")
        box.pack(fill="both", expand=True, padx=16, pady=6)
        box.insert("1.0", text)
        box.configure(state="disabled")
        ctk.CTkButton(self, text="Đóng", width=120,
                      command=self.destroy).pack(pady=(0, 14))


class EmergencyDialog(ctk.CTkToplevel):
    """Chọn app để kill khẩn cấp."""

    def __init__(self, master, cands, on_done):
        super().__init__(master)
        self.title("Giải phóng RAM khẩn cấp")
        self.geometry("540x460")
        _make_modal(self, master)
        self._on_done = on_done
        self._vars = {}
        ctk.CTkLabel(self, text="Chọn app để tắt (đã loại trừ process hệ thống):",
                     font=(FONT, 13, "bold")).pack(padx=14, pady=(14, 6))
        frm = ctk.CTkScrollableFrame(self)
        frm.pack(fill="both", expand=True, padx=14, pady=6)
        for r in cands:
            var = tk.BooleanVar(value=True)
            ctk.CTkCheckBox(
                frm, text=f"{r['name']} — {r['rss']/GB:.1f} GB (PID {r['pid']})",
                variable=var).pack(anchor="w", padx=8, pady=3)
            self._vars[r["pid"]] = var
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=12)
        ctk.CTkButton(row, text="⚡ Tắt đã chọn", fg_color="#b91c1c",
                      hover_color="#991b1b", command=self._kill).pack(side="left", padx=4)
        ctk.CTkButton(row, text="Đóng", fg_color=C_CARD2,
                      command=lambda: self._close(0)).pack(side="left", padx=4)

    def _kill(self):
        n = 0
        for pid, var in self._vars.items():
            if var.get():
                ok, _ = process_manager.kill_process(pid, force=False)
                n += ok
        self._close(n)

    def _close(self, n=0):
        self.destroy()
        self._on_done(n)


class HelpWindow(ctk.CTkToplevel):
    """Cửa sổ hướng dẫn sử dụng (đọc HuongDanSuDung.md)."""

    def __init__(self, master):
        super().__init__(master)
        self.title("Hướng dẫn sử dụng — CleanBoost")
        self.geometry("780x600")
        _make_modal(self, master)
        ctk.CTkLabel(self, text="📖 Hướng dẫn sử dụng",
                     font=(FONT, 17, "bold")).pack(pady=(14, 6))
        self.box = ctk.CTkTextbox(self, wrap="word", font=(FONT, 13))
        self.box.pack(fill="both", expand=True, padx=16, pady=6)
        tb = self.box._textbox
        tb.tag_config("h1", font=(FONT, 19, "bold"), foreground=C_ACC,
                      spacing1=10, spacing3=6)
        tb.tag_config("h2", font=(FONT, 15, "bold"), foreground=C_TXT,
                      spacing1=8, spacing3=4)
        tb.tag_config("bold", font=(FONT, 13, "bold"))
        tb.tag_config("mono", font=(MONO, 12), foreground=C_ACC,
                      background=C_CARD2)
        tb.tag_config("mut", foreground=C_MUT)
        self._render()
        self.box.configure(state="disabled")
        ctk.CTkButton(self, text="Đóng", width=120,
                      command=self.destroy).pack(pady=(0, 14))

    def _render(self):
        import re
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        p = os.path.join(root, "HuongDanSuDung.md")
        try:
            with open(p, encoding="utf-8") as f:
                lines = f.read().splitlines()
        except OSError:
            lines = ["Không tìm thấy file HuongDanSuDung.md"]
        tb = self.box._textbox
        in_code = False
        for line in lines:
            s = line.rstrip()
            if s.strip().startswith("```"):
                in_code = not in_code
                continue
            if in_code or (s.startswith("|") and s.endswith("|")):
                tb.insert("end", s + "\n", "mono")
                continue
            if s.startswith("# "):
                tb.insert("end", s[2:] + "\n", "h1")
            elif s.startswith("## "):
                tb.insert("end", s[3:] + "\n", "h2")
            elif s.startswith("### "):
                tb.insert("end", s[4:] + "\n", "h2")
            elif s.strip() == "---":
                tb.insert("end", "─" * 60 + "\n", "mut")
            elif re.match(r"\s*(\d+\.|-|\*) ", s):
                self._rich(s.strip() + "\n", bullet=True)
            elif not s.strip():
                tb.insert("end", "\n")
            else:
                self._rich(s + "\n")

    def _rich(self, text, bullet=False):
        import re
        tb = self.box._textbox
        if bullet:
            tb.insert("end", "  • ")
            text = re.sub(r"^(\d+\.|-|\*)\s+", "", text)
        # **bold** và `code`
        parts = re.split(r"(\*\*.+?\*\*|`.+?`)", text)
        for pt in parts:
            if pt.startswith("**") and pt.endswith("**"):
                tb.insert("end", pt[2:-2], "bold")
            elif pt.startswith("`") and pt.endswith("`") and len(pt) > 2:
                tb.insert("end", pt[1:-1], "mono")
            elif pt:
                tb.insert("end", pt)

# =====================================================================
# App shell
# =====================================================================

PAGES = [
    ("dash", "📊", "Tổng quan"),
    ("proc", "⚙️", "Tiến trình"),
    ("clean", "🧹", "Dọn rác"),
    ("quar", "📦", "Khu cách ly"),
]


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("CleanBoost PRO")
        self.geometry("1120x700")
        self.minsize(980, 600)
        self.configure(fg_color=C_BG)
        _init_fonts()
        self._next_theme = None
        try:
            self.iconphoto(True, tk.PhotoImage(file=LOGO_PATH))
        except Exception:  # noqa: BLE001
            pass

        self._level = tk.IntVar(value=1)
        self._last_scan = []
        self._scan_checks = {}
        self._proc_rows = []
        self._proc_sort = ("rss", True)
        self._nav_btns = {}
        self._pages = {}

        self._build_sidebar()
        self._build_main()
        self._show_page("dash")

        self._tick_dashboard()
        self._refresh_proc()
        self._refresh_quarantine()

    # ------------------------- shell -------------------------
    def _build_sidebar(self):
        sb = ctk.CTkFrame(self, fg_color=C_SIDEBAR, corner_radius=0, width=210)
        sb.pack(side="left", fill="y")
        sb.pack_propagate(False)

        logo = ctk.CTkFrame(sb, fg_color="transparent")
        logo.pack(fill="x", padx=16, pady=(20, 6))
        try:
            from PIL import Image as PILImage
            _pil = PILImage.open(LOGO_PATH)
            self._logo_img = ctk.CTkImage(_pil, size=(52, 52))
            ctk.CTkLabel(logo, image=self._logo_img, text="").pack(
                side="left", padx=(0, 10))
        except Exception:  # noqa: BLE001
            pass
        txt = ctk.CTkFrame(logo, fg_color="transparent")
        txt.pack(side="left")
        ctk.CTkLabel(txt, text="CleanBoost", font=(FONT, 19, "bold"),
                     anchor="w").pack(anchor="w")
        ctk.CTkLabel(txt, text="PRO • dọn RAM & rác", font=(FONT, 11),
                     text_color=C_MUT, anchor="w").pack(anchor="w")

        for key, icon, label in PAGES:
            b = ctk.CTkButton(sb, text=f"  {icon}  {label}", anchor="w",
                              fg_color="transparent", text_color=C_MUT,
                              hover_color=C_CARD2, font=(FONT, 13),
                              height=42,
                              command=lambda k=key: self._show_page(k))
            b.pack(fill="x", padx=10, pady=3)
            self._nav_btns[key] = b

        ctk.CTkLabel(sb, text="", fg_color="transparent").pack(fill="both", expand=True)
        ctk.CTkLabel(sb, text="© copy by Đậu Sỹ Mạnh", font=(FONT, 11),
                     text_color=C_MUT).pack(pady=(0, 4))
        ctk.CTkLabel(sb, text="CleanBoost v2.2 PRO", font=(FONT, 10),
                     text_color=C_MUT).pack(pady=(0, 16))

    def _build_main(self):
        main = ctk.CTkFrame(self, fg_color=C_BG, corner_radius=0)
        main.pack(side="left", fill="both", expand=True)

        # topbar
        top = ctk.CTkFrame(main, fg_color=C_BG, height=58)
        top.pack(fill="x", padx=20, pady=(14, 0))
        top.pack_propagate(False)
        self.page_title = ctk.CTkLabel(top, text="", font=(FONT, 19, "bold"))
        self.page_title.pack(side="left")
        # help "?" góc phải
        help_btn = ctk.CTkButton(top, text="?", width=34, height=34,
                                font=(FONT, 15, "bold"), fg_color=C_CARD2,
                                hover_color=C_ACC,
                                command=lambda: HelpWindow(self))
        help_btn.pack(side="right", padx=(8, 0))
        # nút đổi theme sáng/tối
        self.theme_btn = ctk.CTkButton(
            top, text="☀️" if C_BG == THEMES["dark"]["BG"] else "🌙",
            width=34, height=34, font=(FONT, 14), fg_color=C_CARD2,
            hover_color=C_ACC, command=self._toggle_theme)
        self.theme_btn.pack(side="right", padx=(8, 0))
        is_admin = privilege.is_admin()
        self.admin_badge = ctk.CTkLabel(
            top, text="● ADMIN" if is_admin else "● USER",
            font=(FONT, 11, "bold"),
            text_color=C_GRN if is_admin else C_MUT)
        self.admin_badge.pack(side="right")

        # pages
        self.page_host = ctk.CTkFrame(main, fg_color=C_BG)
        self.page_host.pack(fill="both", expand=True, padx=20, pady=10)
        for key, _icon, label in PAGES:
            f = ctk.CTkFrame(self.page_host, fg_color=C_BG)
            self._pages[key] = (f, label)
        self._build_dashboard(self._pages["dash"][0])
        self._build_processes(self._pages["proc"][0])
        self._build_cleaner(self._pages["clean"][0])
        self._build_quarantine(self._pages["quar"][0])

        # status bar
        sb = ctk.CTkFrame(main, fg_color=C_SIDEBAR, height=30, corner_radius=0)
        sb.pack(fill="x", side="bottom")
        sb.pack_propagate(False)
        self.status_lbl = ctk.CTkLabel(sb, text="", font=(FONT, 11),
                                       text_color=C_MUT)
        self.status_lbl.pack(side="left", padx=16)
        self._tick_status()

    def _toggle_theme(self):
        new = "light" if C_BG == THEMES["dark"]["BG"] else "dark"
        set_theme(new)
        self._next_theme = new
        self.destroy()

    def _show_page(self, key):
        for k, b in self._nav_btns.items():
            b.configure(fg_color=C_ACC if k == key else "transparent",
                        text_color="#ffffff" if k == key else C_MUT)
        for k, (f, label) in self._pages.items():
            if k == key:
                f.pack(fill="both", expand=True)
                self.page_title.configure(text=label)
            else:
                f.pack_forget()
        if key == "quar":
            self._refresh_quarantine()
        if key == "proc":
            self._refresh_proc()

    def _tick_status(self):
        try:
            qn, qs = len(Q.list_items()), Q.total_size()
            logp = action_log.path()
            self.status_lbl.configure(
                text=f"📦 Khu cách ly: {qn} mục ({qs/GB:.2f} GB)    "
                     f"📝 Nhật ký: {logp}")
        except Exception:  # noqa: BLE001
            pass
        self.after(10000, self._tick_status)

    # ------------------------- Trang Tổng quan -------------------------
    def _build_dashboard(self, page):
        self.d_banner = ctk.CTkLabel(page, text="", fg_color="#7f1d1d",
                                     corner_radius=10, text_color="#ffffff",
                                     font=(FONT, 13, "bold"))
        cards = ctk.CTkFrame(page, fg_color="transparent")
        cards.pack(fill="x", pady=(0, 6))
        self.g_ram = RingGauge(cards, "RAM")
        self.g_ram.pack(side="left", padx=10)
        self.g_cpu = RingGauge(cards, "CPU")
        self.g_cpu.pack(side="left", padx=10)
        self.g_disk = RingGauge(cards, "Ổ đĩa")
        self.g_disk.pack(side="left", padx=10)

        ctk.CTkLabel(page, text="Hành động nhanh", font=(FONT, 14, "bold"),
                     anchor="w").pack(anchor="w", pady=(10, 6))
        row = ctk.CTkFrame(page, fg_color="transparent")
        row.pack(fill="x")

        c1 = ctk.CTkFrame(row, fg_color=C_CARD, corner_radius=12)
        c1.pack(side="left", fill="both", expand=True, padx=(0, 8))
        ctk.CTkLabel(c1, text="⚡ Giải phóng RAM khẩn cấp",
                     font=(FONT, 14, "bold"), anchor="w").pack(anchor="w", padx=16, pady=(14, 2))
        ctk.CTkLabel(c1, text="Tự tìm app bạn đang không dùng mà ngốn RAM, "
                              "cho bạn tick chọn rồi tắt hàng loạt.",
                     font=(FONT, 12), text_color=C_MUT, wraplength=380,
                     justify="left", anchor="w").pack(anchor="w", padx=16, pady=(0, 10))
        ctk.CTkButton(c1, text="Giải phóng ngay", fg_color="#b91c1c",
                      hover_color="#991b1b",
                      command=self._emergency).pack(anchor="w", padx=16, pady=(0, 16))

        c2 = ctk.CTkFrame(row, fg_color=C_CARD, corner_radius=12)
        c2.pack(side="left", fill="both", expand=True, padx=(8, 0))
        ctk.CTkLabel(c2, text="🧊 Dọn RAM nhẹ",
                     font=(FONT, 14, "bold"), anchor="w").pack(anchor="w", padx=16, pady=(14, 2))
        ctk.CTkLabel(c2, text="Xả bộ nhớ đệm RAM (Standby List) — không tắt "
                              "bất kỳ app nào. An toàn tuyệt đối.",
                     font=(FONT, 12), text_color=C_MUT, wraplength=380,
                     justify="left", anchor="w").pack(anchor="w", padx=16, pady=(0, 10))
        ctk.CTkButton(c2, text="Dọn nhẹ", fg_color="#047857",
                      hover_color="#065f46",
                      command=self._light).pack(anchor="w", padx=16, pady=(0, 16))

        self.dash_msg = ctk.CTkLabel(page, text="", text_color=C_MUT,
                                     font=(FONT, 12), wraplength=900,
                                     justify="left", anchor="w")
        self.dash_msg.pack(anchor="w", pady=(10, 0))

    def _tick_dashboard(self):
        try:
            mem = system_info.memory()
            cpu = system_info.cpu_percent()
            root = "C:\\" if sys.platform == "win32" else "/"
            disk = system_info.disk(root)
            self.g_ram.set(mem["percent"], f"{mem['used']/GB:.1f}/{mem['total']/GB:.1f} GB")
            self.g_cpu.set(min(cpu, 100), "")
            self.g_disk.set(disk["percent"], f"còn trống {100-disk['percent']:.0f}%")
            warns = []
            if mem["percent"] >= 90:
                warns.append(f"RAM đã dùng {mem['percent']:.0f}% — hãy giải phóng!")
            if 100 - disk["percent"] <= 10:
                warns.append(f"ổ đĩa chỉ còn trống {100-disk['percent']:.0f}% — hãy dọn rác!")
            if warns:
                self.d_banner.configure(text="⚠️ " + "  |  ".join(warns))
                self.d_banner.pack(fill="x", pady=(0, 8), before=self.g_ram.master)
            else:
                self.d_banner.pack_forget()
        except Exception:  # noqa: BLE001
            pass
        self.after(2000, self._tick_dashboard)

    def _light(self):
        self.dash_msg.configure(text="Đang dọn...")
        def work():
            msgs = memory_cleaner.light_clean()
            self.after(0, lambda: self.dash_msg.configure(text="🧊 " + " | ".join(msgs)))
            action_log.log("freeram_light", {"messages": msgs})
        _bg(work)

    def _emergency(self):
        self.dash_msg.configure(text="Đang tìm app ngốn RAM...")
        def work():
            cands = process_manager.emergency_candidates(min_rss_mb=200)
            self.after(0, lambda: self._open_emergency(cands))
        _bg(work)

    def _open_emergency(self, cands):
        if not cands:
            self.dash_msg.configure(text="Không tìm thấy app nào của bạn ngốn trên 200 MB.")
            return
        EmergencyDialog(self, cands, self._after_emergency)

    def _after_emergency(self, killed):
        if killed:
            self.dash_msg.configure(text=f"⚡ Đã tắt {killed} app. Đang xả lại RAM...")
            self._light()
            action_log.log("freeram_emergency", {"killed": killed})
        else:
            self.dash_msg.configure(text="Không tắt gì cả.")

    # ------------------------- Trang Tiến trình -------------------------
    def _build_processes(self, page):
        top = ctk.CTkFrame(page, fg_color="transparent")
        top.pack(fill="x", pady=(0, 8))
        self.p_search = ctk.CTkEntry(top, placeholder_text="🔍 Tìm tiến trình...",
                                    width=300, height=36)
        self.p_search.pack(side="left", padx=(0, 8))
        self.p_search.bind("<KeyRelease>", lambda _e: self._fill_proc())
        ctk.CTkButton(top, text="↻ Làm mới", width=110, height=36,
                      fg_color=C_CARD2, hover_color=C_ACC,
                      command=self._refresh_proc).pack(side="left")
        self.p_count = ctk.CTkLabel(top, text="", text_color=C_MUT)
        self.p_count.pack(side="left", padx=12)

        self.p_tree = _dark_tree(page)
        self.p_tree["columns"] = ("ram", "cpu", "user", "name")
        self.p_tree.heading("#0", text="PID", command=lambda: self._sort_proc("pid"))
        self.p_tree.heading("ram", text="RAM", command=lambda: self._sort_proc("rss"))
        self.p_tree.heading("cpu", text="CPU %", command=lambda: self._sort_proc("cpu"))
        self.p_tree.heading("user", text="User")
        self.p_tree.heading("name", text="Tên tiến trình")
        self.p_tree.column("#0", width=90)
        self.p_tree.column("ram", width=110)
        self.p_tree.column("cpu", width=90)
        self.p_tree.column("user", width=150)
        self.p_tree.pack(fill="both", expand=True, pady=(0, 8))

        row = ctk.CTkFrame(page, fg_color="transparent")
        row.pack(fill="x")
        ctk.CTkButton(row, text="Tắt đã chọn", height=36,
                      command=lambda: self._kill_selected(False)).pack(side="left", padx=(0, 8))
        ctk.CTkButton(row, text="🔴 Force kill", height=36, fg_color="#b91c1c",
                      hover_color="#991b1b",
                      command=lambda: self._kill_selected(True)).pack(side="left")
        ctk.CTkLabel(row, text="⚠️ = nhạy cảm (hỏi lại trước khi tắt) • Process hệ thống nguy hiểm đã ẩn",
                     text_color=C_MUT, font=(FONT, 11)).pack(side="left", padx=14)
        self.p_msg = ctk.CTkLabel(page, text="", text_color=C_MUT, font=(FONT, 12))
        self.p_msg.pack(anchor="w", pady=(6, 0))

    def _refresh_proc(self):
        self.p_msg.configure(text="Đang tải...")
        def work():
            rows = process_manager.list_processes(sort_by="memory", limit=300)
            self.after(0, lambda: self._set_proc_rows(rows))
        _bg(work)

    def _set_proc_rows(self, rows):
        self._proc_rows = rows
        self._fill_proc()
        self.p_msg.configure(text="")
        self.p_count.configure(text=f"{len(rows)} tiến trình")

    def _sort_proc(self, key):
        rev = not (self._proc_sort[0] == key and self._proc_sort[1])
        self._proc_sort = (key, rev)
        self._proc_rows.sort(key=lambda r: r[key], reverse=rev)
        self._fill_proc()

    def _fill_proc(self):
        q = (self.p_search.get() or "").lower()
        for i in self.p_tree.get_children():
            self.p_tree.delete(i)
        n = 0
        for r in self._proc_rows:
            if q and q not in r["name"].lower():
                continue
            n += 1
            tag = "warn" if r["state"] == "warn" else ""
            self.p_tree.insert("", "end", iid=str(r["pid"]), text=str(r["pid"]),
                               values=(f"{r['rss']/GB:.1f} GB", f"{r['cpu']:.1f}",
                                       r["user"], r["name"] + (" ⚠️" if tag else "")),
                               tags=(tag,))
        self.p_tree.tag_configure("warn", foreground=C_YLW)
        self.p_count.configure(text=f"{n} tiến trình")

    def _kill_selected(self, force):
        sel = self.p_tree.selection()
        if not sel:
            self.p_msg.configure(text="Chưa chọn tiến trình nào.")
            return
        from tkinter import messagebox
        n = 0
        for iid in sel:
            pid = int(iid)
            r = next((x for x in self._proc_rows if x["pid"] == pid), None)
            name = r["name"] if r else f"PID {pid}"
            if protected.check_process(name, pid) == "warn":
                if not messagebox.askyesno("Xác nhận",
                        f"{name} là process hệ thống nhạy cảm.\nVẫn tắt?",
                        parent=self):
                    continue
            ok, _ = process_manager.kill_process(pid, force=force)
            n += ok
        action_log.log("kill_gui", {"force": force, "killed": n})
        self.p_msg.configure(text=f"Đã tắt {n}/{len(sel)} tiến trình.")
        self._refresh_proc()

    # ------------------------- Trang Dọn rác -------------------------
    def _build_cleaner(self, page):
        # mức dọn: 3 cards
        lv = ctk.CTkFrame(page, fg_color="transparent")
        lv.pack(fill="x", pady=(0, 8))
        self._lv_cards = {}
        lv_data = [
            (1, "🟢 Tiêu chuẩn", "Temp, thùng rác, cache\nAn toàn tuyệt đối", C_GRN),
            (2, "🟡 Nâng cao", "Update, WinSxS, Windows.old,\ndata app đã gỡ • cần Admin", C_YLW),
            (3, "🔴 Chuyên sâu", "Quét toàn ổ C, mục nguy hiểm\nAdmin + xác nhận", C_RED),
        ]
        for i, title, desc, color in lv_data:
            card = ctk.CTkFrame(lv, fg_color=C_CARD, corner_radius=12,
                                border_width=2, border_color=C_LINE)
            card.pack(side="left", fill="both", expand=True, padx=6)
            card.bind("<Button-1>", lambda _e, i=i: self._set_level(i))
            t = ctk.CTkLabel(card, text=title, font=(FONT, 13, "bold"), anchor="w")
            t.pack(anchor="w", padx=14, pady=(10, 0))
            t.bind("<Button-1>", lambda _e, i=i: self._set_level(i))
            d = ctk.CTkLabel(card, text=desc, font=(FONT, 11), text_color=C_MUT,
                             anchor="w", justify="left")
            d.pack(anchor="w", padx=14, pady=(2, 10))
            d.bind("<Button-1>", lambda _e, i=i: self._set_level(i))
            self._lv_cards[i] = (card, color)
        self._set_level(1)

        row = ctk.CTkFrame(page, fg_color="transparent")
        row.pack(fill="x", pady=(0, 6))
        self.c_scan_btn = ctk.CTkButton(row, text="🔍 Quét thử", width=150, height=38,
                                        fg_color=C_ACC, hover_color="#3b7ded",
                                        font=(FONT, 13, "bold"),
                                        command=self._scan)
        self.c_scan_btn.pack(side="left", padx=(0, 10))
        self.c_prog = ctk.CTkProgressBar(row, width=280, height=12)
        self.c_prog.pack(side="left", padx=6)
        self.c_prog.set(0)
        self.c_total = ctk.CTkLabel(row, text="Chọn mức rồi bấm Quét thử",
                                    font=(FONT, 13, "bold"), text_color=C_ACC)
        self.c_total.pack(side="left", padx=10)

        self.c_results = ctk.CTkScrollableFrame(
            page, label_text="Kết quả quét — tick chọn nhóm, bấm «Chi tiết» để xem file",
            label_font=(FONT, 12, "bold"))
        self.c_results.pack(fill="both", expand=True, pady=(0, 8))

        brow = ctk.CTkFrame(page, fg_color="transparent")
        brow.pack(fill="x")
        self.c_del_btn = ctk.CTkButton(brow, text="🗑 Xóa để giải phóng dung lượng",
                                       height=40, fg_color="#b91c1c",
                                       hover_color="#991b1b", font=(FONT, 13, "bold"),
                                       command=lambda: self._do_clean(True))
        self.c_del_btn.pack(side="left", padx=(0, 8))
        self.c_q_btn = ctk.CTkButton(brow, text="📦 Cách ly (an toàn)",
                                     height=40, fg_color="#b45309",
                                     hover_color="#92400e", font=(FONT, 13),
                                     command=lambda: self._do_clean(False))
        self.c_q_btn.pack(side="left")
        ctk.CTkLabel(brow, text="«Xóa» giải phóng GB thật (đo từ ổ đĩa). «Cách ly» an toàn hơn nhưng file vẫn nằm trên ổ đĩa.",
                     text_color=C_MUT, font=(FONT, 11), wraplength=420,
                     justify="left").pack(side="left", padx=14)

    def _set_level(self, i):
        self._level.set(i)
        for k, (card, color) in self._lv_cards.items():
            card.configure(border_color=color if k == i else C_LINE)

    def _scan(self):
        self.c_scan_btn.configure(state="disabled")
        self.c_prog.start()
        for w in self.c_results.winfo_children():
            w.destroy()
        self._scan_checks = {}
        self.c_total.configure(text="Đang quét...")
        level = self._level.get()

        def work():
            try:
                results = [scanner.scan_rule(r, collect_paths=True)
                           for r in engine.rules_for(level)]
            except Exception as e:  # noqa: BLE001
                results = e
            self.after(0, lambda: self._show_scan(results))
        _bg(work)

    def _show_scan(self, results):
        self.c_prog.stop()
        self.c_prog.set(0)
        self.c_scan_btn.configure(state="normal")
        if isinstance(results, Exception):
            self.c_total.configure(text=f"Lỗi quét: {results}")
            return
        self._last_scan = results
        shown = 0
        for res in results:
            rule = res["rule"]
            if res.get("error"):
                continue
            if res["size"] == 0 and res["count"] == 0:
                continue
            shown += 1
            var = tk.BooleanVar(value=bool(rule.get("default_on")))
            card = ctk.CTkFrame(self.c_results, fg_color=C_CARD, corner_radius=10)
            card.pack(fill="x", padx=6, pady=4)

            top = ctk.CTkFrame(card, fg_color="transparent")
            top.pack(fill="x", padx=10, pady=(8, 0))
            cb = ctk.CTkCheckBox(top, text="", variable=var, width=28,
                                 command=self._update_total)
            cb.pack(side="left")
            name = rule["name"]
            if rule.get("risk") == "high":
                name += "  🔴"
            elif rule.get("risk") == "medium":
                name += "  🟡"
            ctk.CTkLabel(top, text=name, font=(FONT, 12, "bold"),
                         wraplength=520, justify="left").pack(side="left")
            ctk.CTkLabel(top, text=_fmt_gb(res["size"]), font=(FONT, 13, "bold"),
                         text_color=C_ACC).pack(side="right", padx=(8, 0))
            ctk.CTkButton(top, text="Chi tiết", width=80, height=28,
                          fg_color=C_CARD2, hover_color=C_ACC,
                          command=lambda r=res: DetailDialog(self, r)).pack(side="right")

            ctk.CTkLabel(card, text=rule.get("impact", ""), font=(FONT, 11),
                         text_color=C_MUT, wraplength=760,
                         justify="left", anchor="w").pack(anchor="w", padx=(48, 10), pady=(0, 8))
            self._scan_checks[rule["id"]] = (var, res)
        if not shown:
            ctk.CTkLabel(self.c_results, text="Sạch! Không tìm thấy gì để dọn ở mức này. 🎉",
                         font=(FONT, 13), text_color=C_GRN).pack(pady=20)
        self._update_total()

    def _update_total(self):
        total = sum(res["size"] for var, res in self._scan_checks.values() if var.get())
        n = sum(1 for var, _ in self._scan_checks.values() if var.get())
        self.c_total.configure(text=f"Đã chọn {n} nhóm • Tổng {_fmt_gb(total)}")
        self.c_del_btn.configure(text=f"🗑 Xóa {_fmt_gb(total)} để giải phóng")

    def _checked(self):
        return [(rule, res["size"]) for rid, (var, res) in self._scan_checks.items()
                if var.get() for rule in [res["rule"]]]

    def _do_clean(self, permanent):
        from tkinter import messagebox
        items = self._checked()
        if not items:
            messagebox.showwarning("Chưa chọn", "Bạn chưa tick nhóm nào để dọn.", parent=self)
            return
        dlg = ConfirmCleanDialog(self, items, permanent)
        self.wait_window(dlg)
        if not dlg.result:
            return
        if self._level.get() >= 2 and sys.platform == "win32":
            messagebox.showinfo("An toàn", "App sẽ tự tạo System Restore Point trước khi dọn.", parent=self)
        self.c_del_btn.configure(state="disabled")
        self.c_q_btn.configure(state="disabled")
        self.c_prog.start()
        level, results = self._level.get(), self._last_scan
        ids = {rule["id"] for rule, _ in items}

        def work():
            try:
                summary = clean_rules(results, ids, permanent=permanent, level=level)
            except Exception as e:  # noqa: BLE001
                summary = e
            self.after(0, lambda: self._after_clean(summary))
        _bg(work)

    def _after_clean(self, summary):
        self.c_prog.stop()
        self.c_prog.set(0)
        self.c_del_btn.configure(state="normal")
        self.c_q_btn.configure(state="normal")
        if isinstance(summary, Exception):
            from tkinter import messagebox
            messagebox.showerror("Lỗi", f"Dọn thất bại: {summary}", parent=self)
            return
        ResultDialog(self, "Hoàn tất dọn dẹp", fmt_summary(summary))
        self._refresh_quarantine()
        self._tick_status()
        for w in self.c_results.winfo_children():
            w.destroy()
        self._scan_checks = {}
        self.c_total.configure(text="Đã dọn xong — bấm Quét thử để kiểm tra lại.")
        self.c_del_btn.configure(text="🗑 Xóa để giải phóng dung lượng")

    # ------------------------- Trang Khu cách ly -------------------------
    def _build_quarantine(self, page):
        ctk.CTkLabel(page, text="File đã dọn được giữ ở đây 14 ngày. Muốn giải phóng dung lượng THẬT, hãy «Xóa vĩnh viễn».",
                     text_color=C_MUT, font=(FONT, 12), anchor="w",
                     wraplength=900, justify="left").pack(anchor="w", pady=(0, 8))
        self.q_tree = _dark_tree(page)
        self.q_tree.configure(selectmode="extended")
        self.q_tree.bind("<Control-a>", self._q_select_all)
        self.q_tree.bind("<Control-A>", self._q_select_all)
        self.q_tree["columns"] = ("orig", "size", "date", "rule")
        self.q_tree.heading("#0", text="ID")
        self.q_tree.heading("orig", text="File gốc")
        self.q_tree.heading("size", text="Dung lượng")
        self.q_tree.heading("date", text="Ngày cách ly")
        self.q_tree.heading("rule", text="Rule")
        self.q_tree.column("#0", width=120)
        self.q_tree.column("orig", width=420)
        self.q_tree.column("size", width=110)
        self.q_tree.column("date", width=150)
        self.q_tree.column("rule", width=160)
        self.q_tree.pack(fill="both", expand=True, pady=(0, 8))

        row = ctk.CTkFrame(page, fg_color="transparent")
        row.pack(fill="x")
        ctk.CTkButton(row, text="↻ Làm mới", height=36, fg_color=C_CARD2,
                      hover_color=C_ACC,
                      command=self._refresh_quarantine).pack(side="left", padx=(0, 8))
        ctk.CTkButton(row, text="↩ Khôi phục đã chọn", height=36, fg_color="#047857",
                      hover_color="#065f46",
                      command=self._q_restore).pack(side="left", padx=(0, 8))
        ctk.CTkButton(row, text="🗑 Xóa vĩnh viễn đã chọn", height=36, fg_color="#b91c1c",
                      hover_color="#991b1b",
                      command=self._q_delete).pack(side="left", padx=(0, 8))
        ctk.CTkButton(row, text="🧹 Dọn mục quá 14 ngày", height=36, fg_color=C_CARD2,
                      hover_color=C_ACC,
                      command=self._q_purge).pack(side="left", padx=(0, 8))
        ctk.CTkButton(row, text="☑ Chọn tất cả", height=36, fg_color=C_CARD2,
                      hover_color=C_ACC,
                      command=lambda: self._q_select_all(None)).pack(side="left")
        self.q_msg = ctk.CTkLabel(page, text="", text_color=C_MUT, font=(FONT, 12))
        self.q_msg.pack(anchor="w", pady=(8, 0))
        ctk.CTkLabel(page, text="Mẹo: bấm Ctrl+A để chọn tất cả, giữ Ctrl/Shift để chọn nhiều dòng.",
                     text_color=C_MUT, font=(FONT, 11)).pack(anchor="w")

    def _refresh_quarantine(self):
        for i in self.q_tree.get_children():
            self.q_tree.delete(i)
        items = Q.list_items()
        for it in sorted(items, key=lambda x: x.get("quarantined_at", ""), reverse=True):
            self.q_tree.insert("", "end", iid=it["id"], text=it["id"],
                               values=(it["orig"], _fmt_gb(it["size"]),
                                       it.get("quarantined_at", "")[:16].replace("T", " "),
                                       it.get("rule", "")))
        self.q_msg.configure(text=f"{len(items)} mục — {Q.total_size()/GB:.2f} GB đang nằm trong khu cách ly (chưa giải phóng)")

    def _q_select_all(self, _event):
        self.q_tree.selection_set(self.q_tree.get_children())
        return "break"

    def _q_restore(self):
        from tkinter import messagebox
        sel = self.q_tree.selection()
        if not sel:
            return
        msgs = []
        for iid in sel:
            ok, msg = Q.restore(iid)
            msgs.append(("✅ " if ok else "⚠️ ") + msg)
            action_log.log("quarantine_restore", {"id": iid, "ok": ok})
        messagebox.showinfo("Khôi phục", "\n".join(msgs[:10]), parent=self)
        self._refresh_quarantine()
        self._tick_status()

    def _q_delete(self):
        from tkinter import messagebox
        sel = self.q_tree.selection()
        if not sel:
            return
        if not messagebox.askyesno("Xác nhận",
                f"Xóa VĨNH VIỄN {len(sel)} mục? Dung lượng sẽ được giải phóng thật.",
                parent=self):
            return
        for iid in sel:
            ok, _ = Q.delete_permanent(iid)
            action_log.log("quarantine_delete", {"id": iid, "ok": ok})
        self._refresh_quarantine()
        self._tick_status()

    def _q_purge(self):
        from tkinter import messagebox
        n, freed = Q.purge_expired()
        action_log.log("quarantine_purge", {"removed": n, "freed": freed})
        messagebox.showinfo("Dọn quá hạn",
                            f"Đã xóa vĩnh viễn {n} mục quá 14 ngày ({freed/GB:.2f} GB).",
                            parent=self)
        self._refresh_quarantine()
        self._tick_status()


def main():
    while True:
        app = App()
        app.mainloop()
        if not app._next_theme:
            break
        # theme đã được set_theme() trước khi destroy -> vòng lặp vẽ lại


if __name__ == "__main__":
    main()
