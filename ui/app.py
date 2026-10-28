"""CleanBoost PRO — GUI (CustomTkinter).

Layout: left sidebar + topbar + 4 pages + status bar.
Every long task runs in a background thread with its buttons disabled
(no double-click hangs). All popups are modal and centered on the main
window. Light/dark theme with a toggle. UI language: English.
"""
import os
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import customtkinter as ctk  # noqa: E402

from core import privilege, system_info, process_manager, memory_cleaner  # noqa: E402
from core import health as health_mod, optimize as optimizer  # noqa: E402
from core import startup as startup_mod  # noqa: E402
from network import info as net_info, ports as net_ports  # noqa: E402
from network import speed as net_speed, refresh as net_refresh  # noqa: E402
from network import dns as net_dns, diag as net_diag, hogs as net_hogs  # noqa: E402
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
# Semantic palette. Every button uses an explicit (bg, text, hover)
# triple from here — never CTk's default text color on a custom bg.
# That default is white, which is invisible on the light theme's pale
# secondary buttons (the "button only appears on hover" bug).
THEMES = {
    "dark": dict(BG="#0e1117", SIDEBAR="#141926", CARD="#1a2030",
                 CARD2="#232c42", LINE="#2a3348", TXT="#e8edf7",
                 MUT="#9aa7c2",
                 BTN2="#232c42", BTN2_TXT="#e8edf7", BTN2_HOV="#33405f"),
    "light": dict(BG="#edf0f5", SIDEBAR="#ffffff", CARD="#ffffff",
                  CARD2="#dfe5ef", LINE="#c3ccdd", TXT="#17202f",
                  MUT="#4b5b76",
                  BTN2="#dbe3f0", BTN2_TXT="#17202f", BTN2_HOV="#c2cfe4"),
}
C_ACC = "#4f8cff"          # accent for graphics / text highlights
C_ACC_BTN = "#2563eb"      # primary button bg (white text: 5.2:1)
C_ACC_BTN_HOV = "#1d4ed8"  # primary button hover
C_ONCOLOR = "#ffffff"      # text on any colored button
C_GRN = "#1a9e6b"
C_YLW = "#b8860b"
C_RED = "#e05252"

C_BG = C_SIDEBAR = C_CARD = C_CARD2 = C_LINE = C_TXT = C_MUT = ""
C_BTN2 = C_BTN2_TXT = C_BTN2_HOV = ""


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
    """Switch theme and persist it. Reassigns the C_* globals."""
    global C_BG, C_SIDEBAR, C_CARD, C_CARD2, C_LINE, C_TXT, C_MUT
    global C_BTN2, C_BTN2_TXT, C_BTN2_HOV
    t = THEMES[mode]
    C_BG, C_SIDEBAR, C_CARD = t["BG"], t["SIDEBAR"], t["CARD"]
    C_CARD2, C_LINE, C_TXT, C_MUT = t["CARD2"], t["LINE"], t["TXT"], t["MUT"]
    C_BTN2, C_BTN2_TXT, C_BTN2_HOV = t["BTN2"], t["BTN2_TXT"], t["BTN2_HOV"]
    ctk.set_appearance_mode(mode)
    try:
        with open(_theme_cfg_path(), "w", encoding="utf-8") as f:
            f.write(mode)
    except OSError:
        pass


set_theme(_load_theme())
ctk.set_default_color_theme("blue")


def _pick_font(candidates):
    """Pick the first font available on this machine."""
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


def _post_ui(widget, fn):
    """Run fn() on the UI thread, from any thread (v2.7.0).

    Worker threads must NEVER call widget.after() themselves: when the
    main thread is not inside the main loop at that moment, Tk raises
    RuntimeError("main thread is not in main loop") IN THE WORKER,
    killing it silently (invisible under pythonw.exe) and leaving the
    UI's busy lock set forever. Instead, fn is put on the App's
    thread-safe queue and executed by the UI thread's drain loop.
    """
    w = widget
    while getattr(w, "master", None) is not None:
        w = w.master
    q = getattr(w, "_ui_queue", None)
    if q is not None:
        q.put(fn)
    else:  # no App (should not happen) - last-resort direct call
        widget.after(0, fn)


def _fmt_gb(n):
    return f"{n / GB:.2f} GB"


def _fmt_size(n):
    """Human size (v2.5.3): 850 B / 12.3 KB / 4.5 MB / 1.23 GB.

    The old _fmt_gb showed every file under ~5 MB as '0.00 GB', which
    made small quarantined files look like size 0.
    """
    n = float(n or 0)
    if n < 1024:
        return f"{n:.0f} B"
    if n < 1024 ** 2:
        return f"{n / 1024:.1f} KB"
    if n < 1024 ** 3:
        return f"{n / 1024 ** 2:.1f} MB"
    return f"{n / GB:.2f} GB"


# ------------------------- modal helpers -------------------------

def _center_on(win, parent):
    """Center a Toplevel on its parent window."""
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


def _make_modal(win, parent, _attempt=0):
    """Make a Toplevel a modal popup centered on the main window.

    The main window cannot be used until the popup is closed.
    v2.7.1: grab_set can fail silently when the window is not viewable
    yet (the old try/except swallowed it, leaving the main window
    clickable behind the popup). Verify the grab actually held and
    retry briefly if it did not.
    """
    if _attempt == 0:
        try:
            win.transient(parent)
        except Exception:  # noqa: BLE001
            pass
        _center_on(win, parent)
    try:
        win.grab_set()
    except Exception:  # noqa: BLE001
        pass
    try:
        grabbed = win.grab_status() is not None
    except Exception:  # noqa: BLE001
        grabbed = False
    if not grabbed and _attempt < 10:
        try:
            win.after(100, lambda: _make_modal(win, parent, _attempt + 1))
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
    style.map("Treeview", background=[("selected", C_ACC_BTN)],
              foreground=[("selected", "#ffffff")])
    return ttk.Treeview(parent)


# ------------------------- widgets -------------------------

class RingGauge(tk.Canvas):
    """Circular gauge showing a percentage."""

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


# ------------------------- dialogs -------------------------

class DetailDialog(ctk.CTkToplevel):
    """Show the actual files a group will delete (before deleting)."""

    def __init__(self, master, res):
        super().__init__(master)
        rule = res["rule"]
        self.title(f"Details — {rule['name']}")
        self.geometry("760x520")
        _make_modal(self, master)
        self.res = res

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=16, pady=(14, 6))
        ctk.CTkLabel(head, text=rule["name"], font=(FONT, 16, "bold"),
                     wraplength=700, justify="left").pack(anchor="w")
        info = rule.get("impact", "")
        if rule.get("warning"):
            info = f"WARNING: {rule['warning']}\n{info}"
        if rule.get("note"):
            info += f"\nNote: {rule['note']}"
        ctk.CTkLabel(head, text=info.strip(), text_color=C_MUT,
                     font=(FONT, 12), wraplength=700,
                     justify="left").pack(anchor="w", pady=(4, 0))

        self.status = ctk.CTkLabel(self, text="Calculating file sizes...",
                                   text_color=C_MUT)
        self.status.pack(padx=16, pady=4, anchor="w")

        self.tree = _dark_tree(self)
        self.tree["columns"] = ("size",)
        self.tree.heading("#0", text="File / folder")
        self.tree.heading("size", text="Size")
        self.tree.column("#0", width=560)
        self.tree.column("size", width=120)
        self.tree.pack(fill="both", expand=True, padx=16, pady=6)

        foot = ctk.CTkFrame(self, fg_color="transparent")
        foot.pack(fill="x", padx=16, pady=(0, 14))
        self.foot_lbl = ctk.CTkLabel(foot, text="", text_color=C_MUT)
        self.foot_lbl.pack(side="left")
        ctk.CTkButton(foot, text="Close", width=100,
                      command=self.destroy).pack(side="right")
        _bg(self._load)

    def _load(self):
        res = self.res
        rows = []
        if res.get("orphans"):
            for o in res["orphans"]:
                rows.append((f"[{o['confidence']}] {o['path']}", o["size"]))
        else:
            paths = res.get("paths") or []
            for fp in paths[:5000]:
                try:
                    rows.append((fp, os.path.getsize(fp)))
                except OSError:
                    continue
        rows.sort(key=lambda x: x[1], reverse=True)
        total_n = len(res.get("orphans") or res.get("paths") or [])
        _post_ui(self, lambda: self._fill(rows, total_n))

    def _fill(self, rows, total_n):
        show = rows[:300]
        for p, s in show:
            tag = "big" if s > 100 * 1024 * 1024 else ""
            self.tree.insert("", "end", text=p,
                             values=(_fmt_gb(s),), tags=(tag,))
        self.tree.tag_configure("big", foreground=C_YLW)
        self.status.pack_forget()
        extra = f" (of {min(total_n, 5000)} scanned)" if total_n > len(show) else ""
        self.foot_lbl.configure(
            text=f"Showing {len(show)}/{total_n} largest items{extra} — "
                 f"group total: {_fmt_gb(self.res['size'])}")


class ConfirmCleanDialog(ctk.CTkToplevel):
    """Confirm deletion: lists groups + impact + red warnings."""

    def __init__(self, master, items, permanent):
        """items: list of (rule, size). permanent True = delete forever."""
        super().__init__(master)
        self.result = False
        total = sum(s for _, s in items)
        self.title("Confirm cleanup")
        self.geometry("620x480")
        _make_modal(self, master)

        ctk.CTkLabel(self,
                     text="Delete permanently" if permanent else "Move to quarantine",
                     font=(FONT, 17, "bold"),
                     text_color=C_RED if permanent else C_YLW).pack(pady=(16, 4))
        ctk.CTkLabel(self, text=f"Total: {_fmt_gb(total)} — {len(items)} groups",
                     font=(FONT, 13, "bold"), text_color=C_ACC).pack()

        box = ctk.CTkScrollableFrame(self, label_text="Groups to clean")
        box.pack(fill="both", expand=True, padx=16, pady=10)
        for rule, size in items:
            # v2.7.1: CTkFrame has NO text_color argument — passing it
            # raised ValueError on the FIRST row, aborting the dialog
            # mid-build: header + empty box, no buttons, zombie window.
            f = ctk.CTkFrame(box, fg_color=C_BTN2)
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
                ctk.CTkLabel(f, text=f"WARNING: {rule['warning']}",
                             text_color=C_RED, font=(FONT, 11, "bold"),
                             wraplength=540, justify="left").pack(anchor="w", padx=10, pady=(0, 8))

        note = ("Deleted files CANNOT be recovered." if permanent
                else "Files move to quarantine (kept 14 days, restorable) — "
                     "NOTE: they still occupy disk space until you delete them "
                     "permanently from the Quarantine tab.")
        ctk.CTkLabel(self, text=note, text_color=C_MUT, font=(FONT, 11),
                     wraplength=560, justify="left").pack(padx=16, pady=4)

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(4, 16))
        ctk.CTkButton(row, text="Cancel", fg_color=C_BTN2,
                      text_color=C_BTN2_TXT, hover_color=C_BTN2_HOV,
                      command=self._no).pack(side="right", padx=6)
        ctk.CTkButton(row, text="Delete permanently" if permanent else "Quarantine",
                      fg_color="#b91c1c" if permanent else "#92400e",
                      text_color=C_ONCOLOR,
                      hover_color="#991b1b" if permanent else "#78350f",
                      command=self._yes).pack(side="right", padx=6)

    def _yes(self):
        self.result = True
        self.destroy()

    def _no(self):
        self.destroy()


class HighRiskConfirmDialog(ctk.CTkToplevel):
    """Second confirmation for HIGH-RISK rules (v2.5.2).

    Shown AFTER the normal ConfirmCleanDialog when any selected rule
    has risk == "high" (e.g. DISM ResetBase, old restore points,
    Disable Hibernate). Lists each high-risk rule with its full
    warning + impact, and requires the "I understand" checkbox
    before the Run button enables.
    """

    def __init__(self, master, high_rules):
        super().__init__(master)
        self.result = False
        self.title("HIGH-RISK — confirm again")
        self.geometry("640x520")
        _make_modal(self, master)

        ctk.CTkLabel(self, text="HIGH-RISK actions selected",
                     font=(FONT, 17, "bold"), text_color=C_RED).pack(pady=(16, 4))
        ctk.CTkLabel(self, text="These actions are IRREVERSIBLE or remove a safety net. "
                                "Read each one before proceeding.",
                     font=(FONT, 12), text_color=C_MUT, wraplength=580,
                     justify="left").pack(padx=16, pady=(0, 8))

        box = ctk.CTkScrollableFrame(self, label_text="High-risk groups")
        box.pack(fill="both", expand=True, padx=16, pady=6)
        for rule in high_rules:
            # v2.7.1: same CTkFrame text_color bug as ConfirmCleanDialog.
            f = ctk.CTkFrame(box, fg_color=C_BTN2)
            f.pack(fill="x", padx=6, pady=4)
            ctk.CTkLabel(f, text=rule["name"], font=(FONT, 13, "bold"),
                         wraplength=520, justify="left").pack(anchor="w", padx=10, pady=(8, 0))
            ctk.CTkLabel(f, text=rule.get("impact", ""), text_color=C_MUT,
                         font=(FONT, 11), wraplength=520,
                         justify="left").pack(anchor="w", padx=10, pady=(2, 2))
            if rule.get("warning"):
                ctk.CTkLabel(f, text=f"WARNING: {rule['warning']}",
                             text_color=C_RED, font=(FONT, 11, "bold"),
                             wraplength=520, justify="left").pack(anchor="w", padx=10, pady=(0, 8))
            if rule.get("note"):
                ctk.CTkLabel(f, text=f"Note: {rule['note']}",
                             text_color=C_MUT, font=(FONT, 11),
                             wraplength=520, justify="left").pack(anchor="w", padx=10, pady=(0, 8))

        var = tk.BooleanVar(value=False)
        run_btn = ctk.CTkButton(self, text="I understand — run high-risk actions",
                                fg_color="#b91c1c", text_color=C_ONCOLOR, hover_color="#991b1b",
                                state="disabled",
                                command=self._yes)
        cb = ctk.CTkCheckBox(self, text="I understand the risks above.",
                             variable=var,
                             command=lambda: run_btn.configure(
                                 state="normal" if var.get() else "disabled"))
        cb.pack(padx=16, pady=8, anchor="w")
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(0, 16))
        ctk.CTkButton(row, text="Cancel", fg_color=C_BTN2, text_color=C_BTN2_TXT,
                      command=self._no).pack(side="right", padx=6)
        run_btn.pack(side="right", padx=6)

    def _yes(self):
        self.result = True
        self.destroy()

    def _no(self):
        self.destroy()


class ResultDialog(ctk.CTkToplevel):
    """Show cleanup results in monospace text."""

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
        ctk.CTkButton(self, text="Close", width=120,
                      command=self.destroy).pack(pady=(0, 14))


class EmergencyDialog(ctk.CTkToplevel):
    """Pick apps to kill for emergency RAM release."""

    def __init__(self, master, cands, on_done):
        super().__init__(master)
        self.title("Emergency RAM release")
        self.geometry("540x460")
        _make_modal(self, master)
        self._on_done = on_done
        self._vars = {}
        ctk.CTkLabel(self, text="Select apps to close (system processes excluded):",
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
        ctk.CTkButton(row, text="Close selected", fg_color="#b91c1c", text_color=C_ONCOLOR,
                      hover_color="#991b1b", command=self._kill).pack(side="left", padx=4)
        ctk.CTkButton(row, text="Cancel", fg_color=C_BTN2, text_color=C_BTN2_TXT,
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
    """User manual viewer (reads USER_MANUAL.md)."""

    def __init__(self, master):
        super().__init__(master)
        self.title("User Manual — CleanBoost")
        self.geometry("780x600")
        _make_modal(self, master)
        ctk.CTkLabel(self, text="User Manual",
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
        ctk.CTkButton(self, text="Close", width=120,
                      command=self.destroy).pack(pady=(0, 14))

    def _render(self):
        import re
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for name in ("USER_MANUAL.md", "HuongDanSuDung.md"):
            p = os.path.join(root, name)
            if os.path.exists(p):
                break
        try:
            with open(p, encoding="utf-8") as f:
                lines = f.read().splitlines()
        except OSError:
            lines = ["User manual not found."]
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
    ("dash", "Overview"),
    ("proc", "Processes"),
    ("clean", "Disk Cleaner"),
    ("quar", "Quarantine"),
    ("net", "Network"),
    ("startup", "Startup"),
]
PAGE_ICONS = {"dash": "📊", "proc": "⚙️", "clean": "🧹", "quar": "📦",
              "net": "🌐", "startup": "🚀"}


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("CleanBoost PRO")
        self.geometry("1120x700")
        self.minsize(980, 600)
        self.configure(fg_color=C_BG)
        _init_fonts()
        self._next_theme = None
        self._busy = False  # True while a background task runs
        self._bg_queue = []  # v2.5.6: tasks waiting for the busy lock
        # v2.7.0: thread-safe hand-off to the UI thread (see _post_ui).
        self._ui_queue = queue.Queue()
        self.after(60, self._drain_ui_queue)
        try:
            self.iconphoto(True, tk.PhotoImage(file=LOGO_PATH))
        except Exception:  # noqa: BLE001
            pass

        self._level = tk.IntVar(value=1)
        self._last_scan = []
        self._scan_checks = {}
        self._proc_rows = []
        self._net_loaded = False
        self._startup_loaded = False
        self._net_before = None
        self._net_after = None
        self._proc_sort = ("rss", True)
        self._nav_btns = {}
        self._pages = {}

        self._build_sidebar()
        self._build_main()
        self._show_page("dash")

        self._tick_dashboard()
        self._refresh_proc()
        self._refresh_quarantine()

    # ------------------------- busy guard -------------------------
    def _run_bg(self, buttons, work, done=None, status="Working...",
                timeout=None):
        """Run work() in a background thread.

        Disables the given buttons while running so a button can never be
        clicked twice (prevents duplicate threads / hangs). Re-enables them
        when done.

        v2.5.6: tasks are QUEUED instead of dropped when one is already
        running. The old drop behavior silently lost work (e.g. opening
        the Network tab while the startup process-list load was still
        running dropped both Network tasks and left "Loading..." stuck
        forever). Buttons are disabled at queue time too, so a button
        group can have at most one queued task.

        v2.7.0: every task has a hard TIMEOUT (default 180s; long jobs
        pass a bigger one). A task that overruns is ABANDONED: the busy
        lock is released, its buttons come back, the queue moves on, and
        the timeout is logged with the task name. The stray thread is a
        daemon and its late result is ignored, so no single hang — in
        any feature, on any machine — can lock the UI forever again.
        Always returns True — the task will run (now or after the queue).
        """
        if timeout is None:
            timeout = self._BG_DEFAULT_TIMEOUT
        task = (list(buttons), work, done, status, timeout)
        for b in buttons:
            try:
                b.configure(state="disabled")
            except Exception:  # noqa: BLE001
                pass
        if self._busy:
            self._bg_queue.append(task)
            return True
        self._start_bg(*task)
        return True

    # Default hard limit per background task (v2.7.0). Long jobs pass
    # their own bigger timeout to _run_bg.
    _BG_DEFAULT_TIMEOUT = 180
    # A task still running after this long is probably stuck (v2.6.1).
    _BG_WARN_SECONDS = 15 * 60

    def _start_bg(self, buttons, work, done, status, timeout):
        self._busy = True
        self._set_status(status)
        self._bg_task_id = getattr(self, "_bg_task_id", 0) + 1
        tid = self._bg_task_id
        self._bg_current = (tid, list(buttons))
        t0 = time.time()
        action_log.log("bg_task_start", {"task": status, "id": tid})
        # v2.7.0: the worker thread NEVER touches Tk. It only stores
        # its result here and sets the event; the UI thread polls.
        holder = {"event": threading.Event(), "result": None}

        def runner():
            try:
                holder["result"] = work()
            except Exception as e:  # noqa: BLE001
                holder["result"] = e
            except BaseException as e:  # noqa: BLE001
                # SystemExit / KeyboardInterrupt in a worker thread must
                # never leave the UI locked forever (v2.6.1).
                holder["result"] = RuntimeError(
                    f"Task aborted ({type(e).__name__}): {e}")
            holder["event"].set()

        threading.Thread(target=runner, daemon=True).start()
        self._bg_poll(tid, t0, buttons, done, status, timeout, holder,
                      warned=False, last_sec=-1)

    def _bg_poll(self, tid, t0, buttons, done, status, timeout, holder,
                 warned, last_sec):
        """UI-thread poll for the running task (v2.7.0, replaces calling
        after() from the worker thread — see _post_ui): finish when the
        worker posts its result, abandon at the timeout, tick the
        elapsed clock every second."""
        if tid != getattr(self, "_bg_task_id", 0) \
                or not getattr(self, "_busy", False):
            return
        if holder["event"].is_set():
            self._finish_bg(tid, t0, buttons, holder["result"], done,
                            status)
            return
        elapsed = time.time() - t0
        if elapsed >= timeout:
            self._abandon_bg(tid, status, timeout)
            return
        sec = int(elapsed)
        if sec != last_sec:
            last_sec = sec
            mm, ss = sec // 60, sec % 60
            self._set_status(f"{status} - {mm:02d}:{ss:02d}")
            if elapsed >= self._BG_WARN_SECONDS and not warned:
                warned = True
                self._set_status(
                    f"Still running after 15 min: {status} Long jobs "
                    "(DISM, big scans) can take a while - the task will "
                    "be stopped automatically at its time limit.")
                action_log.log("bg_task_slow",
                               {"task": status, "id": tid,
                                "seconds": int(elapsed)})
        self.after(100, lambda: self._bg_poll(
            tid, t0, buttons, done, status, timeout, holder, warned,
            last_sec))

    def _drain_ui_queue(self):
        """Execute callbacks posted from worker threads (v2.7.0)."""
        try:
            while True:
                fn = self._ui_queue.get_nowait()
                try:
                    fn()
                except Exception:  # noqa: BLE001
                    pass
        except queue.Empty:
            pass
        try:
            self.after(60, self._drain_ui_queue)
        except Exception:  # noqa: BLE001 - window going away
            pass

    def _release_buttons(self, buttons):
        """Re-enable a finished/abandoned task's buttons — except the
        ones that belong to a task still waiting in the queue."""
        queued_buttons = set()
        for q in self._bg_queue:
            queued_buttons.update(id(b) for b in q[0])
        for b in buttons:
            if id(b) in queued_buttons:
                continue
            try:
                b.configure(state="normal")
            except Exception:  # noqa: BLE001
                pass

    def _abandon_bg(self, tid, status, timeout):
        """Give up on an overrunning task (v2.7.0): release the lock and
        its buttons, say what happened, keep the queue moving. The
        task's late _finish_bg is ignored via the task-id check."""
        cur = getattr(self, "_bg_current", (tid, []))
        buttons = cur[1] if cur[0] == tid else []
        self._bg_task_id = tid + 1  # invalidate the stray thread's finish
        self._busy = False
        self._release_buttons(buttons)
        action_log.log("bg_task_timeout",
                       {"task": status, "id": tid, "timeout": timeout})
        self._set_status(
            f"Stopped a stuck task after {timeout}s: {status} "
            "The app is usable again - please try once more. "
            "(Details are in the action log.)")
        if self._bg_queue:
            self._start_bg(*self._bg_queue.pop(0))

    def _finish_bg(self, tid, t0, buttons, result, done, status):
        if tid != getattr(self, "_bg_task_id", 0):
            # Late finish of an abandoned task: ignore it completely so
            # it cannot clobber the state of whatever runs now.
            action_log.log("bg_task_late_finish",
                           {"task": status, "id": tid})
            return
        self._busy = False
        # Do not re-enable buttons that belong to a queued task — they
        # stay disabled until that task runs and finishes.
        self._release_buttons(buttons)
        self._set_status("")
        action_log.log("bg_task_done",
                       {"task": status, "id": tid,
                        "seconds": round(time.time() - t0, 1),
                        "error": isinstance(result, Exception)})
        if done:
            try:
                done(result)
            except Exception as e:  # noqa: BLE001
                # A failing done() must not stall the queue or leave
                # the app silent — report it and keep going.
                self._set_status(f"Error: {e}")
        # A done() may itself have started a new task (nested _run_bg);
        # only drain the queue when nothing is running now.
        if self._bg_queue and not self._busy:
            self._start_bg(*self._bg_queue.pop(0))

    def _set_status(self, text):
        try:
            self.status_lbl.configure(text=text)
        except Exception:  # noqa: BLE001
            pass

    def report_callback_exception(self, exc, val, tb):
        """Tkinter calls this when a button/menu callback raises (v2.7.1).

        Default Tk behavior prints to stderr — invisible under
        pythonw.exe, which is how a broken button produced a zombie
        dialog with no error shown. Now: log it AND show it, so a
        failing feature can never die silently again.
        """
        try:
            import traceback
            text = "".join(traceback.format_exception(exc, val, tb))
            action_log.log("ui_callback_error",
                           {"exc": f"{exc.__name__}: {val}"})
            try:
                from gui import _crash_log_path
                with open(_crash_log_path(), "a", encoding="utf-8") as f:
                    f.write(text + "\n")
            except Exception:  # noqa: BLE001
                pass
            from tkinter import messagebox
            messagebox.showerror(
                "Unexpected error",
                f"{exc.__name__}: {val}\n\n"
                "The action did not complete. Details were written to "
                "the error log (see the status bar for its location).",
                parent=self)
        except Exception:  # noqa: BLE001
            pass

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
        ctk.CTkLabel(txt, text="PRO", font=(FONT, 11),
                     text_color=C_MUT, anchor="w").pack(anchor="w")

        for key, label in PAGES:
            icon = PAGE_ICONS[key]
            b = ctk.CTkButton(sb, text=f"  {icon}  {label}", anchor="w",
                              fg_color="transparent", text_color=C_TXT,
                              hover_color=C_BTN2_HOV, font=(FONT, 13),
                              height=42,
                              command=lambda k=key: self._show_page(k))
            b.pack(fill="x", padx=10, pady=3)
            self._nav_btns[key] = b

        ctk.CTkLabel(sb, text="", fg_color="transparent").pack(fill="both", expand=True)
        ctk.CTkLabel(sb, text="© copy by Dau Sy Manh", font=(FONT, 11),
                     text_color=C_MUT).pack(pady=(0, 4))
        ctk.CTkLabel(sb, text="CleanBoost v2.7.1", font=(FONT, 10),
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
        help_btn = ctk.CTkButton(top, text="?", width=34, height=34,
                                 font=(FONT, 15, "bold"), fg_color=C_BTN2,
                                 text_color=C_BTN2_TXT,
                                 hover_color=C_BTN2_HOV,
                                 command=lambda: HelpWindow(self))
        help_btn.pack(side="right", padx=(8, 0))
        self.theme_btn = ctk.CTkButton(
            top, text="☀️" if C_BG == THEMES["dark"]["BG"] else "🌙",
            width=34, height=34, font=(FONT, 14), fg_color=C_BTN2,
            text_color=C_BTN2_TXT,
            hover_color=C_BTN2_HOV, command=self._toggle_theme)
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
        for key, label in PAGES:
            if key == "dash":
                # v2.7.0: Overview scrolls — the Top-10 panel made it
                # taller than smaller windows.
                f = ctk.CTkScrollableFrame(self.page_host, fg_color=C_BG)
            else:
                f = ctk.CTkFrame(self.page_host, fg_color=C_BG)
            self._pages[key] = (f, label)
        self._build_dashboard(self._pages["dash"][0])
        self._build_processes(self._pages["proc"][0])
        self._build_cleaner(self._pages["clean"][0])
        self._build_quarantine(self._pages["quar"][0])
        self._build_network(self._pages["net"][0])
        self._build_startup(self._pages["startup"][0])

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
            b.configure(fg_color=C_ACC_BTN if k == key else "transparent",
                        text_color="#ffffff" if k == key else C_TXT)
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
        if key == "dash":
            self._refresh_top()
        if key == "net" and not getattr(self, "_net_loaded", False):
            if self._refresh_network_all():
                self._net_loaded = True
        if key == "startup" and not getattr(self, "_startup_loaded", False):
            self._startup_loaded = True
            self._refresh_startup()

    def _tick_status(self):
        def work():
            try:
                n = len(Q.list_items())
                s = Q.total_size()
                return f"Quarantine: {n} items ({s/GB:.2f} GB)   Log: {action_log.path()}"
            except Exception:  # noqa: BLE001
                return ""
        def done(text):
            if text:
                # don't override a task's own status message
                if not self._busy:
                    self._set_status(text)
            self.after(10000, self._tick_status)
        _bg(lambda: _post_ui(self, lambda: done(work())))

    # ------------------------- Overview page -------------------------
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
        self.g_disk = RingGauge(cards, "Disk")
        self.g_disk.pack(side="left", padx=10)

        ctk.CTkLabel(page, text="Quick actions", font=(FONT, 14, "bold"),
                     anchor="w").pack(anchor="w", pady=(10, 6))
        row = ctk.CTkFrame(page, fg_color="transparent")
        row.pack(fill="x")

        c1 = ctk.CTkFrame(row, fg_color=C_CARD, corner_radius=12)
        c1.pack(side="left", fill="both", expand=True, padx=(0, 8))
        ctk.CTkLabel(c1, text="Emergency RAM release",
                     font=(FONT, 14, "bold"), anchor="w").pack(anchor="w", padx=16, pady=(14, 2))
        ctk.CTkLabel(c1, text="Finds your heaviest RAM-hungry apps, lets you "
                              "tick the ones to close, then frees RAM.",
                     font=(FONT, 12), text_color=C_MUT, wraplength=380,
                     justify="left", anchor="w").pack(anchor="w", padx=16, pady=(0, 10))
        self.emergency_btn = ctk.CTkButton(c1, text="Free RAM now", fg_color="#b91c1c", text_color=C_ONCOLOR,
                                           hover_color="#991b1b",
                                           command=self._emergency)
        self.emergency_btn.pack(anchor="w", padx=16, pady=(0, 16))

        c2 = ctk.CTkFrame(row, fg_color=C_CARD, corner_radius=12)
        c2.pack(side="left", fill="both", expand=True, padx=(8, 0))
        ctk.CTkLabel(c2, text="Light RAM clean",
                     font=(FONT, 14, "bold"), anchor="w").pack(anchor="w", padx=16, pady=(14, 2))
        ctk.CTkLabel(c2, text="Flushes RAM standby cache without closing any "
                              "app. Completely safe.",
                     font=(FONT, 12), text_color=C_MUT, wraplength=380,
                     justify="left", anchor="w").pack(anchor="w", padx=16, pady=(0, 10))
        self.light_btn = ctk.CTkButton(c2, text="Light clean", fg_color="#047857", text_color=C_ONCOLOR,
                                       hover_color="#065f46",
                                       command=self._light)
        self.light_btn.pack(anchor="w", padx=16, pady=(0, 16))

        # Health Score + Optimize in 1 Click (v2.4)
        hrow = ctk.CTkFrame(page, fg_color="transparent")
        hrow.pack(fill="x", pady=(10, 0))

        h1 = ctk.CTkFrame(hrow, fg_color=C_CARD, corner_radius=12)
        h1.pack(side="left", fill="both", expand=True, padx=(0, 8))
        ctk.CTkLabel(h1, text="Health Score",
                     font=(FONT, 14, "bold"), anchor="w").pack(anchor="w", padx=16, pady=(14, 2))
        self.health_score_lbl = ctk.CTkLabel(h1, text="-- / 100",
                                             font=(FONT, 22, "bold"), text_color=C_ACC,
                                             anchor="w")
        self.health_score_lbl.pack(anchor="w", padx=16)
        self.health_break_lbl = ctk.CTkLabel(h1, text="Press Refresh to calculate.",
                                             font=(FONT, 11), text_color=C_MUT, wraplength=380,
                                             justify="left", anchor="w")
        self.health_break_lbl.pack(anchor="w", padx=16, pady=(0, 6))
        self.health_suggest_lbl = ctk.CTkLabel(h1, text="", font=(FONT, 11),
                                               text_color=C_TXT, wraplength=380,
                                               justify="left", anchor="w")
        self.health_suggest_lbl.pack(anchor="w", padx=16, pady=(0, 10))
        self.health_refresh_btn = ctk.CTkButton(h1, text="Refresh Health Score",
                                                fg_color=C_BTN2, text_color=C_BTN2_TXT, hover_color=C_BTN2_HOV,
                                                command=self._refresh_health)
        self.health_refresh_btn.pack(anchor="w", padx=16, pady=(0, 16))

        h2 = ctk.CTkFrame(hrow, fg_color=C_CARD, corner_radius=12)
        h2.pack(side="left", fill="both", expand=True, padx=(8, 0))
        ctk.CTkLabel(h2, text="Optimize in 1 Click",
                     font=(FONT, 14, "bold"), anchor="w").pack(anchor="w", padx=16, pady=(14, 2))
        ctk.CTkLabel(h2, text="Light RAM clean + level-1 junk to quarantine + "
                              "Quick Refresh. Kills nothing, deletes nothing "
                              "permanently.",
                     font=(FONT, 12), text_color=C_MUT, wraplength=380,
                     justify="left", anchor="w").pack(anchor="w", padx=16, pady=(0, 10))
        self.optimize_btn = ctk.CTkButton(h2, text="Optimize Now", fg_color="#047857", text_color=C_ONCOLOR,
                                          hover_color="#065f46",
                                          command=self._optimize)
        self.optimize_btn.pack(anchor="w", padx=16, pady=(0, 8))
        self.opt_prog = ctk.CTkProgressBar(h2, width=280, height=12)
        self.opt_prog.pack(anchor="w", padx=16, pady=(0, 6))
        self.opt_prog.set(0)
        self.opt_msg = ctk.CTkLabel(h2, text="", font=(FONT, 11),
                                    text_color=C_MUT, wraplength=380,
                                    justify="left", anchor="w")
        self.opt_msg.pack(anchor="w", padx=16, pady=(0, 16))

        # Top 10 processes by RAM / CPU (v2.7.0)
        trow = ctk.CTkFrame(page, fg_color="transparent")
        trow.pack(fill="x", pady=(14, 6))
        ctk.CTkLabel(trow, text="Top 10 processes", font=(FONT, 14, "bold"),
                     anchor="w").pack(side="left")
        self.top_refresh_btn = ctk.CTkButton(
            trow, text="Refresh", width=90, height=28,
            fg_color=C_BTN2, text_color=C_BTN2_TXT, hover_color=C_BTN2_HOV,
            command=self._refresh_top)
        self.top_refresh_btn.pack(side="left", padx=(10, 0))
        ctk.CTkLabel(trow, text="Auto-refreshes while you stay on this page. "
                                "To close an app: Processes tab -> select -> End task.",
                     font=(FONT, 11), text_color=C_MUT, anchor="w").pack(side="left", padx=(10, 0))

        tcols = ctk.CTkFrame(page, fg_color="transparent")
        tcols.pack(fill="x")
        t1 = ctk.CTkFrame(tcols, fg_color=C_CARD, corner_radius=12)
        t1.pack(side="left", fill="both", expand=True, padx=(0, 8))
        ctk.CTkLabel(t1, text="Top 10 by RAM", font=(FONT, 12, "bold"),
                     anchor="w").pack(anchor="w", padx=12, pady=(10, 4))
        self.top_ram_box = ctk.CTkTextbox(t1, height=168, font=(FONT, 11),
                                          fg_color="transparent")
        self.top_ram_box.pack(fill="both", expand=True, padx=8, pady=(0, 10))
        self.top_ram_box.insert("1.0", "Loading...")
        self.top_ram_box.configure(state="disabled")
        t2 = ctk.CTkFrame(tcols, fg_color=C_CARD, corner_radius=12)
        t2.pack(side="left", fill="both", expand=True, padx=(8, 0))
        ctk.CTkLabel(t2, text="Top 10 by CPU", font=(FONT, 12, "bold"),
                     anchor="w").pack(anchor="w", padx=12, pady=(10, 4))
        self.top_cpu_box = ctk.CTkTextbox(t2, height=168, font=(FONT, 11),
                                          fg_color="transparent")
        self.top_cpu_box.pack(fill="both", expand=True, padx=8, pady=(0, 10))
        self.top_cpu_box.insert("1.0", "Loading...")
        self.top_cpu_box.configure(state="disabled")

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
            self.g_disk.set(disk["percent"], f"{100-disk['percent']:.0f}% free")
            warns = []
            if mem["percent"] >= 90:
                warns.append(f"RAM is {mem['percent']:.0f}% full — free some RAM!")
            if 100 - disk["percent"] <= 10:
                warns.append(f"Disk only {100-disk['percent']:.0f}% free — clean junk files!")
            if warns:
                self.d_banner.configure(text="WARNING: " + "  |  ".join(warns))
                self.d_banner.pack(fill="x", pady=(0, 8), before=self.g_ram.master)
            else:
                self.d_banner.pack_forget()
        except Exception:  # noqa: BLE001
            pass
        # v2.7.0: refresh the Top-10 panel every ~20s while Overview is
        # on screen and nothing else is running.
        self._dash_ticks = getattr(self, "_dash_ticks", 0) + 1
        if self._dash_ticks % 10 == 0 and not self._busy:
            try:
                if self._pages["dash"][0].winfo_ismapped():
                    self._refresh_top()
            except Exception:  # noqa: BLE001
                pass
        self.after(2000, self._tick_dashboard)

    def _light(self):
        self.dash_msg.configure(text="")

        def done(msgs):
            # v2.7.0: this used to pass the text as a POSITIONAL arg to
            # configure() — CustomTkinter reads that as `require_redraw`
            # and silently sets nothing, so Light clean NEVER showed its
            # result and looked dead. Always use text=.
            if isinstance(msgs, Exception):
                self.dash_msg.configure(text=f"Error: {msgs}")
            else:
                self.dash_msg.configure(
                    text="Light clean done: " + " | ".join(msgs))

        self._run_bg([self.light_btn],
                     lambda: memory_cleaner.light_clean(),
                     done=done,
                     status="Cleaning RAM cache...")

    def _emergency(self):
        self.dash_msg.configure(text="")
        self._run_bg([self.emergency_btn],
                     lambda: process_manager.emergency_candidates(min_rss_mb=200),
                     done=self._open_emergency,
                     status="Finding RAM-hungry apps...")

    def _open_emergency(self, cands):
        if isinstance(cands, Exception):
            self.dash_msg.configure(text=f"Error: {cands}")
            return
        if not cands:
            self.dash_msg.configure(text="No app of yours is using over 200 MB.")
            return
        EmergencyDialog(self, cands, self._after_emergency)

    def _after_emergency(self, killed):
        if killed:
            self.dash_msg.configure(text=f"Closed {killed} app(s). Flushing RAM...")
            self._light()
            action_log.log("freeram_emergency", {"killed": killed})
        else:
            self.dash_msg.configure(text="Nothing was closed.")

    # ------------------------- Top 10 processes (v2.7.0) -------------------------
    def _refresh_top(self):
        """Fill the Overview Top-10 boxes (RAM + CPU) in one bg task."""
        def work():
            return process_manager.list_processes(sort_by="memory",
                                                  limit=150)

        def done(rows):
            if isinstance(rows, Exception):
                self._set_top_text(f"Error: {rows}", f"Error: {rows}")
                return
            by_ram = rows[:10]
            by_cpu = sorted(rows, key=lambda r: r["cpu"],
                            reverse=True)[:10]
            ram_txt = "\n".join(
                f"{i}. {r['name']} - {_fmt_size(r['rss'])} (PID {r['pid']})"
                for i, r in enumerate(by_ram, 1)) or "No processes."
            cpu_txt = "\n".join(
                f"{i}. {r['name']} - {r['cpu']:.1f}% (PID {r['pid']})"
                for i, r in enumerate(by_cpu, 1)) or "No processes."
            self._set_top_text(ram_txt, cpu_txt)

        self._run_bg([self.top_refresh_btn], work, done=done,
                     status="Loading top processes...")

    def _set_top_text(self, ram_txt, cpu_txt):
        for box, txt in ((self.top_ram_box, ram_txt),
                         (self.top_cpu_box, cpu_txt)):
            try:
                box.configure(state="normal")
                box.delete("1.0", "end")
                box.insert("1.0", txt)
                box.configure(state="disabled")
            except Exception:  # noqa: BLE001
                pass

    # ------------------------- Health Score + Optimize (v2.4) -------------------------
    def _refresh_health(self):
        self.health_break_lbl.configure(text="Calculating...")
        self.health_suggest_lbl.configure(text="")

        def work():
            # Junk size comes from a level-1 scan (no path list needed).
            junk = 0
            for res in [scanner.scan_rule(r) for r in engine.rules_for(1)]:
                if not res.get("error"):
                    junk += res.get("size", 0)
            return health_mod.compute_health(junk_bytes=junk)

        def done(res):
            if isinstance(res, Exception):
                self.health_break_lbl.configure(text=f"Error: {res}")
                return
            ok, _msg, data = res
            if not ok:
                self.health_break_lbl.configure(text=_msg)
                return
            self.health_score_lbl.configure(text=f"{data['score']} / 100")
            self.health_break_lbl.configure(text=health_mod.format_health(data))
            self.health_suggest_lbl.configure(
                text=" | ".join(data["suggestions"]))

        self._run_bg([self.health_refresh_btn], work, done=done,
                     status="Calculating Health Score...", timeout=600)

    def _optimize(self):
        self.opt_msg.configure(text="")
        self.opt_prog.set(0)

        def progress(done_n, total, label):
            try:
                _post_ui(self, lambda: self.opt_prog.set(
                    done_n / total if total else 0))
            except Exception:  # noqa: BLE001
                pass

        def work():
            return optimizer.run_optimize(progress_cb=progress)

        def done(res):
            self.opt_prog.set(0)
            if isinstance(res, Exception):
                self.opt_msg.configure(text=f"Error: {res}")
                return
            ok, msg, report = res
            self.opt_msg.configure(text=msg)
            if ok:
                ResultDialog(self, "Optimize finished",
                             optimizer.format_report(report))
                self._refresh_quarantine()

        self._run_bg([self.optimize_btn], work, done=done,
                     status="Optimizing...", timeout=900)

    # ------------------------- Processes page -------------------------
    def _build_processes(self, page):
        top = ctk.CTkFrame(page, fg_color="transparent")
        top.pack(fill="x", pady=(0, 8))
        self.p_search = ctk.CTkEntry(top, placeholder_text="Search processes...",
                                    width=300, height=36)
        self.p_search.pack(side="left", padx=(0, 8))
        self.p_search.bind("<KeyRelease>", lambda _e: self._fill_proc())
        self.p_refresh_btn = ctk.CTkButton(top, text="Refresh", width=110, height=36,
                                           fg_color=C_BTN2, text_color=C_BTN2_TXT, hover_color=C_BTN2_HOV,
                                           command=self._refresh_proc)
        self.p_refresh_btn.pack(side="left")
        self.p_count = ctk.CTkLabel(top, text="", text_color=C_MUT)
        self.p_count.pack(side="left", padx=12)

        self.p_tree = _dark_tree(page)
        self.p_tree["columns"] = ("ram", "cpu", "user", "name")
        self.p_tree.heading("#0", text="PID", command=lambda: self._sort_proc("pid"))
        self.p_tree.heading("ram", text="RAM", command=lambda: self._sort_proc("rss"))
        self.p_tree.heading("cpu", text="CPU %", command=lambda: self._sort_proc("cpu"))
        self.p_tree.heading("user", text="User")
        self.p_tree.heading("name", text="Process name")
        self.p_tree.column("#0", width=90)
        self.p_tree.column("ram", width=110)
        self.p_tree.column("cpu", width=90)
        self.p_tree.column("user", width=150)
        self.p_tree.pack(fill="both", expand=True, pady=(0, 8))

        row = ctk.CTkFrame(page, fg_color="transparent")
        row.pack(fill="x")
        self.p_kill_btn = ctk.CTkButton(row, text="End selected", height=36,
                                        command=lambda: self._kill_selected(False))
        self.p_kill_btn.pack(side="left", padx=(0, 8))
        self.p_fkill_btn = ctk.CTkButton(row, text="Force kill", height=36,
                                         fg_color="#b91c1c", text_color=C_ONCOLOR, hover_color="#991b1b",
                                         command=lambda: self._kill_selected(True))
        self.p_fkill_btn.pack(side="left")
        ctk.CTkLabel(row, text="(!) = sensitive, asks first. Dangerous system processes are hidden.",
                     text_color=C_MUT, font=(FONT, 11)).pack(side="left", padx=14)
        self.p_msg = ctk.CTkLabel(page, text="", text_color=C_MUT, font=(FONT, 12))
        self.p_msg.pack(anchor="w", pady=(6, 0))

    def _refresh_proc(self):
        self.p_msg.configure(text="")
        self._run_bg([self.p_refresh_btn],
                     lambda: process_manager.list_processes(sort_by="memory", limit=300),
                     done=self._set_proc_rows,
                     status="Loading processes...")

    def _set_proc_rows(self, rows):
        if isinstance(rows, Exception):
            self.p_msg.configure(text=f"Error: {rows}")
            return
        self._proc_rows = rows
        self._fill_proc()
        # v2.7.0: do NOT clear p_msg here — the kill flow sets its result
        # message right after refreshing, and clearing it here erased the
        # only feedback the user ever saw ("kill doesn't work").
        self.p_count.configure(text=f"{len(rows)} processes")

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
                                       r["user"], r["name"] + (" (!)" if tag else "")),
                               tags=(tag,))
        self.p_tree.tag_configure("warn", foreground=C_YLW)
        self.p_count.configure(text=f"{n} processes")

    def _kill_selected(self, force):
        sel = self.p_tree.selection()
        if not sel:
            self.p_msg.configure(text="No process selected.")
            return
        from tkinter import messagebox
        # v2.5.2: force kill can lose unsaved work — confirm first.
        if force and not messagebox.askyesno(
                "Force kill",
                "Force kill closes apps immediately — unsaved work in "
                "them will be LOST.\n\nForce kill the selected process(es)?",
                parent=self):
            return
        targets = []
        for iid in sel:
            pid = int(iid)
            r = next((x for x in self._proc_rows if x["pid"] == pid), None)
            name = r["name"] if r else f"PID {pid}"
            if protected.check_process(name, pid) == "warn":
                if not messagebox.askyesno("Confirm",
                        f"{name} is a sensitive system process.\nClose it anyway?",
                        parent=self):
                    continue
            targets.append((pid, name))

        def work():
            killed, failed = 0, []
            for pid, pname in targets:
                ok, msg = process_manager.kill_process(pid, force=force)
                if ok:
                    killed += 1
                else:
                    failed.append((pname, msg))
            return {"killed": killed, "failed": failed}

        def done(res):
            if isinstance(res, Exception):
                self.p_msg.configure(text=f"Error: {res}")
                return
            n = res["killed"]
            failed = res["failed"]
            action_log.log("kill_gui", {"force": force, "killed": n,
                                        "failed": len(failed)})
            msg = f"Closed {n}/{len(targets)} process(es)."
            if failed:
                # v2.7.0: say WHICH apps could not be closed and why —
                # "kill doesn't work" was undebuggable without this.
                detail = "; ".join(f"{nm}: {m}" for nm, m in failed[:3])
                msg += f" Could not close — {detail}."
                if any("access" in m.lower() or "denied" in m.lower()
                       for _nm, m in failed):
                    msg += (" Tip: apps running as Administrator cannot "
                            "be closed by a normal session — relaunch "
                            "CleanBoost via run_cleanboost_admin.bat.")
            # v2.5.2: a killed app with a startup entry comes back on
            # next boot — tell the user instead of letting it silently
            # "restart the old app".
            if sys.platform == "win32" and n:
                try:
                    ok_s, _m, entries = startup_mod.list_startup()
                    if ok_s:
                        respawn = set()
                        for _pid, pname in targets:
                            for e in entries:
                                if e["enabled"] and pname.lower() in (e["value"] or "").lower():
                                    respawn.add(e["name"])
                        if respawn:
                            msg += (" Note: " + ", ".join(sorted(respawn))
                                    + " start(s) with Windows and will come back "
                                      "after restart — disable in the Startup tab.")
                except Exception:  # noqa: BLE001
                    pass
            # v2.7.0: refresh FIRST (it clears p_msg when it starts),
            # then set the result message so it actually stays visible.
            self._refresh_proc()
            self.p_msg.configure(text=msg)

        self._run_bg([self.p_kill_btn, self.p_fkill_btn], work, done=done,
                     status="Closing processes...")

    # ------------------------- Disk Cleaner page -------------------------
    def _build_cleaner(self, page):
        lv = ctk.CTkFrame(page, fg_color="transparent")
        lv.pack(fill="x", pady=(0, 8))
        self._lv_cards = {}
        lv_data = [
            (1, "Standard", "Temp files, recycle bin, browser/app caches\nCompletely safe", C_GRN),
            (2, "Advanced", "Windows Update, WinSxS, Windows.old,\nleftover app data - needs Admin", C_YLW),
            (3, "Deep", "Whole-drive junk patterns, risky items\nAdmin + confirmation", C_RED),
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
        self.c_scan_btn = ctk.CTkButton(row, text="Scan", width=150, height=38,
                                        fg_color=C_ACC_BTN,
                                        hover_color=C_ACC_BTN_HOV,
                                        text_color=C_ONCOLOR,
                                        font=(FONT, 13, "bold"),
                                        command=self._scan)
        self.c_scan_btn.pack(side="left", padx=(0, 10))
        self.c_prog = ctk.CTkProgressBar(row, width=280, height=12)
        self.c_prog.pack(side="left", padx=6)
        self.c_prog.set(0)
        self.c_total = ctk.CTkLabel(row, text="Pick a level, then press Scan",
                                    font=(FONT, 13, "bold"), text_color=C_ACC)
        self.c_total.pack(side="left", padx=10)

        self.c_results = ctk.CTkScrollableFrame(
            page, label_text="Scan results — tick groups, press Details to preview files",
            label_font=(FONT, 12, "bold"))
        self.c_results.pack(fill="both", expand=True, pady=(0, 8))

        brow = ctk.CTkFrame(page, fg_color="transparent")
        brow.pack(fill="x")
        self.c_del_btn = ctk.CTkButton(brow, text="Delete to free space",
                                       height=40, fg_color="#b91c1c", text_color=C_ONCOLOR,
                                       hover_color="#991b1b", font=(FONT, 13, "bold"),
                                       command=lambda: self._do_clean(True))
        self.c_del_btn.pack(side="left", padx=(0, 8))
        self.c_q_btn = ctk.CTkButton(brow, text="Quarantine (safe)",
                                     height=40, fg_color="#92400e",
                                     hover_color="#78350f", text_color=C_ONCOLOR,
                                     font=(FONT, 13),
                                     command=lambda: self._do_clean(False))
        self.c_q_btn.pack(side="left")
        ctk.CTkLabel(brow, text="Delete frees real disk space (measured from the drive). Quarantine is safer but files stay on disk.",
                     text_color=C_MUT, font=(FONT, 11), wraplength=420,
                     justify="left").pack(side="left", padx=14)

    def _set_level(self, i):
        self._level.set(i)
        for k, (card, color) in self._lv_cards.items():
            card.configure(border_color=color if k == i else C_LINE)

    def _scan(self):
        for w in self.c_results.winfo_children():
            w.destroy()
        self._scan_checks = {}
        self.c_total.configure(text="Scanning...")
        self.c_prog.start()
        level = self._level.get()

        def work():
            return [scanner.scan_rule(r, collect_paths=True)
                    for r in engine.rules_for(level)]

        def done(results):
            self.c_prog.stop()
            self.c_prog.set(0)
            self._show_scan(results)

        self._run_bg([self.c_scan_btn, self.c_del_btn, self.c_q_btn],
                     work, done=done, status="Scanning...", timeout=900)

    def _show_scan(self, results):
        if isinstance(results, Exception):
            self.c_total.configure(text=f"Scan error: {results}")
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
                name += "  [HIGH RISK]"
            elif rule.get("risk") == "medium":
                name += "  [caution]"
            ctk.CTkLabel(top, text=name, font=(FONT, 12, "bold"),
                         wraplength=520, justify="left").pack(side="left")
            ctk.CTkLabel(top, text=_fmt_gb(res["size"]), font=(FONT, 13, "bold"),
                         text_color=C_ACC).pack(side="right", padx=(8, 0))
            ctk.CTkButton(top, text="Details", width=80, height=28,
                          fg_color=C_BTN2, text_color=C_BTN2_TXT, hover_color=C_BTN2_HOV,
                          command=lambda r=res: DetailDialog(self, r)).pack(side="right")

            impact_txt = rule.get("impact", "")
            if res.get("truncated"):
                impact_txt += " (File list capped at 200,000 for performance.)"
            ctk.CTkLabel(card, text=impact_txt, font=(FONT, 11),
                         text_color=C_MUT, wraplength=760,
                         justify="left", anchor="w").pack(anchor="w", padx=(48, 10), pady=(0, 8))
            self._scan_checks[rule["id"]] = (var, res)
        if not shown:
            ctk.CTkLabel(self.c_results, text="All clean! Nothing to remove at this level.",
                         font=(FONT, 13), text_color=C_GRN).pack(pady=20)
        self._update_total()

    def _update_total(self):
        total = sum(res["size"] for var, res in self._scan_checks.values() if var.get())
        n = sum(1 for var, _ in self._scan_checks.values() if var.get())
        self.c_total.configure(text=f"{n} groups selected — total {_fmt_gb(total)}")
        self.c_del_btn.configure(text=f"Delete {_fmt_gb(total)} to free space")

    def _checked(self):
        return [(res["rule"], res["size"])
                for _rid, (var, res) in self._scan_checks.items() if var.get()]

    def _do_clean(self, permanent):
        from tkinter import messagebox
        items = self._checked()
        if not items:
            messagebox.showwarning("Nothing selected",
                                   "Tick at least one group first.", parent=self)
            return
        dlg = None
        try:
            dlg = ConfirmCleanDialog(self, items, permanent)
        except Exception as e:  # noqa: BLE001
            # v2.7.1: a dialog that fails mid-build must never be left
            # on screen as a button-less zombie.
            messagebox.showerror("Dialog error",
                                 f"Could not open the confirmation dialog: {e}",
                                 parent=self)
            return
        self.wait_window(dlg)
        if not dlg.result:
            return
        # v2.5.2: HIGH-RISK rules need a SECOND confirmation with full
        # warnings + an "I understand" checkbox (CLI already requires
        # typing "yes" for high-risk rules).
        high = [rule for rule, _ in items if rule.get("risk") == "high"]
        if high:
            try:
                dlg2 = HighRiskConfirmDialog(self, high)
            except Exception as e:  # noqa: BLE001
                messagebox.showerror("Dialog error",
                                     f"Could not open the high-risk dialog: {e}",
                                     parent=self)
                return
            self.wait_window(dlg2)
            if not dlg2.result:
                return
        if self._level.get() >= 2 and sys.platform == "win32":
            messagebox.showinfo("Safety",
                                "A System Restore Point will be created before cleaning.",
                                parent=self)
        self.c_prog.start()
        level, results = self._level.get(), self._last_scan
        ids = {rule["id"] for rule, _ in items}

        def work():
            return clean_rules(results, ids, permanent=permanent, level=level)

        def done(summary):
            self.c_prog.stop()
            self.c_prog.set(0)
            self._after_clean(summary)

        self._run_bg([self.c_scan_btn, self.c_del_btn, self.c_q_btn],
                     work, done=done, status="Cleaning...", timeout=1900)

    def _after_clean(self, summary):
        if isinstance(summary, Exception):
            from tkinter import messagebox
            messagebox.showerror("Error", f"Cleanup failed: {summary}", parent=self)
            return
        ResultDialog(self, "Cleanup finished", fmt_summary(summary))
        self._refresh_quarantine()
        for w in self.c_results.winfo_children():
            w.destroy()
        self._scan_checks = {}
        self.c_total.configure(text="Done — press Scan to check again.")
        self.c_del_btn.configure(text="Delete to free space")

    # ------------------------- Quarantine page -------------------------
    def _build_quarantine(self, page):
        ctk.CTkLabel(page, text="Removed files stay here for 14 days. To REALLY free disk space, use Delete permanently.",
                     text_color=C_MUT, font=(FONT, 12), anchor="w",
                     wraplength=900, justify="left").pack(anchor="w", pady=(0, 8))
        self.q_tree = _dark_tree(page)
        self.q_tree.configure(selectmode="extended")
        self.q_tree.bind("<Control-a>", self._q_select_all)
        self.q_tree.bind("<Control-A>", self._q_select_all)
        self.q_tree["columns"] = ("orig", "size", "date", "rule")
        self.q_tree.heading("#0", text="ID")
        self.q_tree.heading("orig", text="Original file")
        self.q_tree.heading("size", text="Size")
        self.q_tree.heading("date", text="Quarantined at")
        self.q_tree.heading("rule", text="Rule")
        self.q_tree.column("#0", width=120)
        self.q_tree.column("orig", width=420)
        self.q_tree.column("size", width=110)
        self.q_tree.column("date", width=150)
        self.q_tree.column("rule", width=160)
        self.q_tree.pack(fill="both", expand=True, pady=(0, 8))

        row = ctk.CTkFrame(page, fg_color="transparent")
        row.pack(fill="x")
        self.q_refresh_btn = ctk.CTkButton(row, text="Refresh", height=36, fg_color=C_BTN2, text_color=C_BTN2_TXT,
                                           hover_color=C_BTN2_HOV,
                                           command=self._refresh_quarantine)
        self.q_refresh_btn.pack(side="left", padx=(0, 8))
        self.q_restore_btn = ctk.CTkButton(row, text="Restore selected", height=36,
                                           fg_color="#047857", text_color=C_ONCOLOR, hover_color="#065f46",
                                           command=self._q_restore)
        self.q_restore_btn.pack(side="left", padx=(0, 8))
        self.q_delete_btn = ctk.CTkButton(row, text="Delete permanently", height=36,
                                          fg_color="#b91c1c", text_color=C_ONCOLOR, hover_color="#991b1b",
                                          command=self._q_delete)
        self.q_delete_btn.pack(side="left", padx=(0, 8))
        self.q_purge_btn = ctk.CTkButton(row, text="Clean items over 14 days", height=36,
                                         fg_color=C_BTN2, text_color=C_BTN2_TXT, hover_color=C_BTN2_HOV,
                                         command=self._q_purge)
        self.q_purge_btn.pack(side="left", padx=(0, 8))
        self.q_all_btn = ctk.CTkButton(row, text="Select all", height=36, fg_color=C_BTN2, text_color=C_BTN2_TXT,
                                       hover_color=C_BTN2_HOV,
                                       command=lambda: self._q_select_all(None))
        self.q_all_btn.pack(side="left", padx=(0, 8))
        self.q_destroy_btn = ctk.CTkButton(row, text="Destroy All", height=36,
                                            fg_color="#7f1d1d", text_color=C_ONCOLOR, hover_color="#991b1b",
                                            command=self._q_destroy_prompt)
        self.q_destroy_btn.pack(side="left")
        # v2.5.3: progress bar — Destroy / Delete used to run with no
        # visible progress at all.
        self.q_prog = ctk.CTkProgressBar(page, width=320, height=12)
        self.q_prog.pack(anchor="w", pady=(8, 0))
        self.q_prog.set(0)
        self.q_msg = ctk.CTkLabel(page, text="", text_color=C_MUT, font=(FONT, 12))
        self.q_msg.pack(anchor="w", pady=(8, 0))
        ctk.CTkLabel(page, text="Tip: press Ctrl+A to select all, hold Ctrl/Shift for multiple rows.",
                     text_color=C_MUT, font=(FONT, 11)).pack(anchor="w")
        self._q_buttons = [self.q_refresh_btn, self.q_restore_btn,
                           self.q_delete_btn, self.q_purge_btn, self.q_all_btn,
                           self.q_destroy_btn]

    def _q_select_all(self, _event):
        self.q_tree.selection_set(self.q_tree.get_children())
        return "break"

    def _q_prog_set(self, frac):
        """Set the quarantine progress bar (0..1). Safe from any thread."""
        try:
            self.q_prog.configure(mode="determinate")
            self.q_prog.set(max(0.0, min(1.0, float(frac))))
        except Exception:  # noqa: BLE001
            pass

    def _q_prog_start_indeterminate(self):
        try:
            self.q_prog.configure(mode="indeterminate")
            self.q_prog.start()
        except Exception:  # noqa: BLE001
            pass

    def _q_prog_done(self):
        """Stop + reset the quarantine progress bar."""
        try:
            self.q_prog.stop()
            self.q_prog.configure(mode="determinate")
            self.q_prog.set(0)
        except Exception:  # noqa: BLE001
            pass

    def _refresh_quarantine(self):
        # v2.5.3: auto-remove stale entries (stored file no longer exists)
        # on every refresh, so the table never clogs with ghost rows.
        try:
            removed_stale = Q.prune_stale()
        except Exception:  # noqa: BLE001
            removed_stale = 0
        for i in self.q_tree.get_children():
            self.q_tree.delete(i)
        items = Q.list_items()
        for it in sorted(items, key=lambda x: x.get("quarantined_at", ""), reverse=True):
            self.q_tree.insert("", "end", iid=it["id"], text=it["id"],
                               values=(it["orig"], _fmt_size(it["size"]),
                                       it.get("quarantined_at", "")[:16].replace("T", " "),
                                       it.get("rule", "")))
        msg = (f"{len(items)} item(s) — {_fmt_size(Q.total_size())} "
               "in quarantine (not freed yet)")
        if removed_stale:
            msg += (f" — removed {removed_stale} stale entr"
                    + ("y" if removed_stale == 1 else "ies")
                    + " whose files no longer exist.")
        self.q_msg.configure(text=msg)

    def _q_restore(self):
        from tkinter import messagebox
        sel = self.q_tree.selection()
        if not sel:
            self.q_msg.configure(text="No item selected.")
            return

        def work():
            msgs = []
            for idx, iid in enumerate(sel):
                ok, msg = Q.restore(iid)
                msgs.append(("OK " if ok else "! ") + msg)
                action_log.log("quarantine_restore", {"id": iid, "ok": ok})
                _post_ui(self, lambda f=(idx + 1) / len(sel): self._q_prog_set(f))
            return msgs

        def done(msgs):
            self._q_prog_done()
            if isinstance(msgs, Exception):
                messagebox.showerror("Error", str(msgs), parent=self)
                return
            messagebox.showinfo("Restore", "\n".join(msgs[:10]), parent=self)
            self._refresh_quarantine()

        self._q_prog_set(0)
        self._run_bg(self._q_buttons, work, done=done, status="Restoring...", timeout=900)

    def _q_delete(self):
        from tkinter import messagebox
        sel = self.q_tree.selection()
        if not sel:
            self.q_msg.configure(text="No item selected.")
            return
        if not messagebox.askyesno("Confirm",
                f"PERMANENTLY delete {len(sel)} item(s)? This frees real disk space.",
                parent=self):
            return

        def work():
            deleted, failed = 0, []
            for idx, iid in enumerate(sel):
                ok, msg = Q.delete_permanent(iid)
                action_log.log("quarantine_delete", {"id": iid, "ok": ok})
                if ok:
                    deleted += 1
                else:
                    failed.append(f"{iid}: {msg}")
                _post_ui(self, lambda f=(idx + 1) / len(sel): self._q_prog_set(f))
            return deleted, failed

        def done(res):
            self._q_prog_done()
            if isinstance(res, Exception):
                messagebox.showerror("Error", str(res), parent=self)
                return
            deleted, failed = res
            if failed:
                messagebox.showwarning(
                    "Delete finished with failures",
                    f"Deleted {deleted}/{len(sel)} item(s).\n\n"
                    "Failed (these items are still in quarantine):\n"
                    + "\n".join(failed[:5])
                    + ("\n... (locked/in-use files cannot be deleted while "
                       "another app holds them — close the app and try again.)"
                       if len(failed) > 5 else
                       "\n(Locked/in-use files cannot be deleted while "
                       "another app holds them — close the app and try again.)"),
                    parent=self)
            self._refresh_quarantine()

        self._q_prog_set(0)
        self._run_bg(self._q_buttons, work, done=done,
                     status="Deleting permanently...", timeout=900)

    def _q_purge(self):
        from tkinter import messagebox

        def work():
            n, freed = Q.purge_expired()
            action_log.log("quarantine_purge", {"removed": n, "freed": freed})
            return n, freed

        def done(res):
            self._q_prog_done()
            if isinstance(res, Exception):
                messagebox.showerror("Error", str(res), parent=self)
                return
            n, freed = res
            messagebox.showinfo("Clean expired",
                                f"Permanently deleted {n} item(s) older than 14 days ({_fmt_size(freed)}).\n\n"
                                "Items newer than 14 days are NOT removed by this button — "
                                "use Destroy All to remove everything.",
                                parent=self)
            self._refresh_quarantine()

        self._q_prog_start_indeterminate()
        self._run_bg(self._q_buttons, work, done=done,
                     status="Cleaning expired items...", timeout=900)

    def _q_destroy_prompt(self):
        items = Q.list_items()
        if not items:
            self.q_msg.configure(text="Quarantine is already empty.")
            return
        total = Q.total_size()
        dlg = ctk.CTkToplevel(self)
        dlg.title("Destroy All — DANGER")
        dlg.geometry("560x340")
        _make_modal(dlg, self)
        ctk.CTkLabel(dlg, text="DESTROY ALL quarantined items?",
                     font=(FONT, 16, "bold"), text_color=C_RED,
                     wraplength=500, justify="left").pack(padx=16, pady=(16, 6))
        ctk.CTkLabel(dlg, text=f"This PERMANENTLY deletes ALL {len(items)} item(s) "
                              f"({_fmt_size(total)}) in quarantine.\n\n"
                              "NOTHING can be restored afterwards. Use this when "
                              "you are sure you no longer need any of it.",
                     font=(FONT, 12), text_color=C_MUT, wraplength=500,
                     justify="left").pack(padx=16, pady=(0, 10))
        var = tk.BooleanVar(value=False)
        run_btn = ctk.CTkButton(dlg, text="Destroy All", fg_color="#7f1d1d", text_color=C_ONCOLOR,
                                hover_color="#991b1b", state="disabled",
                                command=lambda: (dlg.destroy(),
                                                 self._run_destroy_all()))
        cb = ctk.CTkCheckBox(dlg, text="I understand — destroy everything in "
                                       "quarantine, no restore possible.",
                             variable=var,
                             command=lambda: run_btn.configure(
                                 state="normal" if var.get() else "disabled"))
        cb.pack(padx=16, pady=6, anchor="w")
        row = ctk.CTkFrame(dlg, fg_color="transparent")
        row.pack(pady=12)
        ctk.CTkButton(row, text="Cancel", fg_color=C_BTN2, text_color=C_BTN2_TXT,
                      command=dlg.destroy).pack(side="left", padx=6)
        run_btn.pack(side="left", padx=6)

    def _run_destroy_all(self):
        def work():
            def progress(done_n, total):
                _post_ui(self, lambda: self._q_prog_set(
                    done_n / total if total else 1))
            ok, msg, summary = Q.delete_all(progress_cb=progress)
            action_log.log("quarantine_destroy_all",
                           {"ok": ok, "deleted": summary.get("deleted", 0),
                            "failed": len(summary.get("failed", [])),
                            "freed": summary.get("freed", 0)})
            return ok, msg, summary

        def done(res):
            from tkinter import messagebox
            self._q_prog_done()
            if isinstance(res, Exception):
                messagebox.showerror("Error", str(res), parent=self)
                return
            ok, msg, summary = res
            failed = summary.get("failed", [])
            if failed:
                messagebox.showwarning(
                    "Destroy All finished with failures",
                    f"{msg}\nFreed: {_fmt_size(summary.get('freed', 0))}.\n\n"
                    "Still in quarantine (close the app holding them and retry):\n"
                    + "\n".join(f"{name}: {reason}" for _i, name, reason in failed[:5]),
                    parent=self)
            else:
                messagebox.showinfo("Destroy All",
                                    f"{msg}\nFreed: {_fmt_size(summary.get('freed', 0))}.",
                                    parent=self)
            self._refresh_quarantine()

        self._q_prog_set(0)
        self._run_bg(self._q_buttons, work, done=done,
                     status="Destroying all quarantined items...", timeout=900)


    # ------------------------- Network page (v2.4) -------------------------
    def _build_network(self, page):
        # v2.6.0: 4 subtabs instead of one long scroll - every job has
        # its own place, so you never hunt through the whole tab.
        header = ctk.CTkFrame(page, fg_color="transparent")
        header.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(header, text="Overview = see  \u2022  Test = measure  \u2022  Fix = DNS & Refresh  \u2022  Repair = broken connection",
                     text_color=C_MUT, font=(FONT, 12), anchor="w").pack(side="left")
        ctk.CTkButton(header, text="Guide", width=90,
                      fg_color=C_BTN2, text_color=C_BTN2_TXT, hover_color=C_BTN2_HOV,
                      command=self._open_network_guide).pack(side="right")
        tabs = ctk.CTkTabview(page)
        tabs.pack(fill="both", expand=True)
        tabs.add("Overview")
        tabs.add("Test & Diagnose")
        tabs.add("DNS & Refresh")
        tabs.add("Repair")
        self._build_net_overview(tabs.tab("Overview"))
        self._build_net_test(tabs.tab("Test & Diagnose"))
        self._build_net_dns(tabs.tab("DNS & Refresh"))
        self._build_net_repair(tabs.tab("Repair"))

    def _net_tab_scroll(self, parent):
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True)
        return scroll

    def _open_network_guide(self):
        """Open the Network tab guideline (huong-dan-tab-network.html)."""
        import webbrowser
        from pathlib import Path
        from tkinter import messagebox
        guide = Path(__file__).resolve().parent.parent / "huong-dan-tab-network.html"
        if guide.exists():
            try:
                webbrowser.open(guide.as_uri())
                return
            except Exception:  # noqa: BLE001
                pass
        messagebox.showinfo("Network Guide",
                            f"Guide file not found:\n{guide}",
                            parent=self)

    def _build_net_overview(self, parent):
        scroll = self._net_tab_scroll(parent)

        # --- Network Info ---
        ctk.CTkLabel(scroll, text="Network Info", font=(FONT, 14, "bold"),
                     anchor="w").pack(anchor="w", pady=(0, 4))
        row = ctk.CTkFrame(scroll, fg_color="transparent")
        row.pack(fill="x", pady=(0, 4))
        self.net_info_btn = ctk.CTkButton(row, text="Refresh Info", width=130,
                                          fg_color=C_BTN2, text_color=C_BTN2_TXT, hover_color=C_BTN2_HOV,
                                          command=self._refresh_net_info)
        self.net_info_btn.pack(side="left")
        self.net_info_msg = ctk.CTkLabel(row, text="", text_color=C_MUT,
                                         font=(FONT, 11))
        self.net_info_msg.pack(side="left", padx=10)
        self.net_info_box = ctk.CTkTextbox(scroll, font=(MONO, 12), height=190)
        self.net_info_box.pack(fill="x", pady=(0, 4))
        self.net_info_box.insert("1.0", "Press Refresh Info to load.")
        self.net_info_box.configure(state="disabled")
        ctk.CTkLabel(scroll, text="Compare with: ipconfig /all in Command Prompt.",
                     text_color=C_MUT, font=(FONT, 11), anchor="w"
                     ).pack(anchor="w", pady=(0, 12))
        # --- Port & SSH Inspector ---
        ctk.CTkLabel(scroll, text="Port & SSH Inspector", font=(FONT, 14, "bold"),
                     anchor="w").pack(anchor="w", pady=(0, 4))
        self.net_ssh_lbl = ctk.CTkLabel(scroll, text="Port 22: unknown",
                                        font=(FONT, 12, "bold"), anchor="w")
        self.net_ssh_lbl.pack(anchor="w", pady=(0, 4))
        self.net_port_tree = _dark_tree(scroll)
        self.net_port_tree["columns"] = ("process", "scope", "level")
        self.net_port_tree.heading("#0", text="Port / Bind IP")
        self.net_port_tree.heading("process", text="Process")
        self.net_port_tree.heading("scope", text="Scope")
        self.net_port_tree.heading("level", text="Level")
        self.net_port_tree.column("#0", width=220)
        self.net_port_tree.column("process", width=220)
        self.net_port_tree.column("scope", width=130)
        self.net_port_tree.column("level", width=110)
        self.net_port_tree.pack(fill="x", pady=(0, 4))
        self.net_port_tree.tag_configure("critical", foreground=C_RED)
        self.net_port_tree.tag_configure("warning", foreground=C_YLW)
        prow = ctk.CTkFrame(scroll, fg_color="transparent")
        prow.pack(fill="x", pady=(0, 4))
        self.net_ports_btn = ctk.CTkButton(prow, text="Refresh Ports", width=130,
                                           fg_color=C_BTN2, text_color=C_BTN2_TXT, hover_color=C_BTN2_HOV,
                                           command=self._refresh_ports)
        self.net_ports_btn.pack(side="left", padx=(0, 8))
        self.net_guide_btn = ctk.CTkButton(prow, text="How to close", width=130,
                                           fg_color=C_BTN2, text_color=C_BTN2_TXT, hover_color=C_BTN2_HOV,
                                           command=self._port_guide)
        self.net_guide_btn.pack(side="left")
        self.net_ports_msg = ctk.CTkLabel(prow, text="", text_color=C_MUT,
                                          font=(FONT, 11))
        self.net_ports_msg.pack(side="left", padx=10)
        ctk.CTkLabel(scroll, text="Red = sensitive port open to the whole LAN. "
                                  "Select a row, then press How to close.",
                     text_color=C_MUT, font=(FONT, 11), anchor="w"
                     ).pack(anchor="w", pady=(0, 12))

    def _build_net_test(self, parent):
        scroll = self._net_tab_scroll(parent)

        # --- Speed Test ---
        ctk.CTkLabel(scroll, text="Speed Test (before / after)", font=(FONT, 14, "bold"),
                     anchor="w").pack(anchor="w", pady=(0, 4))
        self.net_before_lbl = ctk.CTkLabel(scroll, text="Before: -",
                                           font=(FONT, 12), anchor="w")
        self.net_before_lbl.pack(anchor="w")
        self.net_after_lbl = ctk.CTkLabel(scroll, text="After: -",
                                          font=(FONT, 12), anchor="w")
        self.net_after_lbl.pack(anchor="w", pady=(0, 4))
        srow = ctk.CTkFrame(scroll, fg_color="transparent")
        srow.pack(fill="x", pady=(0, 4))
        self.net_speed_btn = ctk.CTkButton(srow, text="Run Speed Test", width=150,
                                           fg_color=C_BTN2, text_color=C_BTN2_TXT, hover_color=C_BTN2_HOV,
                                           command=self._run_speed_test)
        self.net_speed_btn.pack(side="left", padx=(0, 8))
        self.net_speed_reset_btn = ctk.CTkButton(srow, text="Reset", width=90,
                                                 fg_color=C_BTN2, text_color=C_BTN2_TXT, hover_color=C_BTN2_HOV,
                                                 command=self._reset_speed)
        self.net_speed_reset_btn.pack(side="left")
        self.net_speed_msg = ctk.CTkLabel(srow, text="", text_color=C_MUT,
                                          font=(FONT, 11))
        self.net_speed_msg.pack(side="left", padx=10)
        # --- Network Diagnostics (v2.5) ---
        ctk.CTkLabel(scroll, text="Network Diagnostics", font=(FONT, 14, "bold"),
                     anchor="w").pack(anchor="w", pady=(0, 4))
        self.diag_btn = ctk.CTkButton(scroll, text="Run Diagnostics", width=160,
                                      fg_color=C_BTN2, text_color=C_BTN2_TXT, hover_color=C_BTN2_HOV,
                                      command=self._run_diagnostics)
        self.diag_btn.pack(anchor="w", pady=(0, 4))
        self.diag_box = ctk.CTkTextbox(scroll, font=(MONO, 12), height=170)
        self.diag_box.pack(fill="x", pady=(0, 4))
        self.diag_box.insert("1.0", "Press Run Diagnostics.")
        self.diag_box.configure(state="disabled")
        # --- Bandwidth Hog Finder (v2.5) ---
        ctk.CTkLabel(scroll, text="Bandwidth Hog Finder", font=(FONT, 14, "bold"),
                     anchor="w").pack(anchor="w", pady=(12, 4))
        ctk.CTkLabel(scroll, text="Ranked by active connections (per-app byte counts "
                                  "are not available).",
                     text_color=C_MUT, font=(FONT, 11), anchor="w").pack(anchor="w")
        self.hogs_total_lbl = ctk.CTkLabel(scroll, text="Total: -",
                                           font=(FONT, 12), anchor="w")
        self.hogs_total_lbl.pack(anchor="w", pady=(0, 4))
        self.hogs_tree = _dark_tree(scroll)
        self.hogs_tree["columns"] = ("conn", "remote")
        self.hogs_tree.heading("#0", text="Process (PID)")
        self.hogs_tree.heading("conn", text="Connections")
        self.hogs_tree.heading("remote", text="Remote IPs")
        self.hogs_tree.column("#0", width=300)
        self.hogs_tree.column("conn", width=120)
        self.hogs_tree.column("remote", width=380)
        self.hogs_tree.pack(fill="x", pady=(0, 4))
        hrow = ctk.CTkFrame(scroll, fg_color="transparent")
        hrow.pack(fill="x", pady=(0, 4))
        self.hogs_btn = ctk.CTkButton(hrow, text="Find Bandwidth Hogs", width=170,
                                      fg_color=C_BTN2, text_color=C_BTN2_TXT, hover_color=C_BTN2_HOV,
                                      command=self._find_hogs)
        self.hogs_btn.pack(side="left", padx=(0, 8))
        self.hogs_kill_btn = ctk.CTkButton(hrow, text="End selected", width=130,
                                           fg_color="#b91c1c", text_color=C_ONCOLOR, hover_color="#991b1b",
                                           command=self._end_hog)
        self.hogs_kill_btn.pack(side="left")
        self.hogs_msg = ctk.CTkLabel(hrow, text="", text_color=C_MUT, font=(FONT, 11))
        self.hogs_msg.pack(side="left", padx=10)

    def _build_net_dns(self, parent):
        scroll = self._net_tab_scroll(parent)

        # --- Quick Refresh ---
        ctk.CTkLabel(scroll, text="Quick Refresh", font=(FONT, 14, "bold"),
                     anchor="w").pack(anchor="w", pady=(12, 4))
        ctk.CTkLabel(scroll, text="Flush DNS + release + renew IP. Your connection "
                                  "drops briefly while renewing.",
                     text_color=C_MUT, font=(FONT, 11), anchor="w",
                     wraplength=900, justify="left").pack(anchor="w", pady=(0, 4))
        qrow = ctk.CTkFrame(scroll, fg_color="transparent")
        qrow.pack(fill="x", pady=(0, 4))
        self.net_refresh_btn = ctk.CTkButton(qrow, text="Quick Refresh", width=150,
                                             fg_color="#047857", text_color=C_ONCOLOR, hover_color="#065f46",
                                             command=self._quick_refresh_net)
        self.net_refresh_btn.pack(side="left", padx=(0, 8))
        self.net_refresh_prog = ctk.CTkProgressBar(qrow, width=280, height=12)
        self.net_refresh_prog.pack(side="left", padx=6)
        self.net_refresh_prog.set(0)
        self.net_refresh_msg = ctk.CTkLabel(scroll, text="", text_color=C_MUT,
                                            font=(FONT, 11), wraplength=900,
                                            justify="left", anchor="w")
        self.net_refresh_msg.pack(anchor="w", pady=(0, 8))
        # --- Flush Network (v2.6.0) ---
        ctk.CTkLabel(scroll, text="Flush Network", font=(FONT, 14, "bold"),
                     anchor="w").pack(anchor="w", pady=(12, 4))
        ctk.CTkLabel(scroll, text="Clears stale DNS, ARP and NetBIOS caches that make websites "
                                  "fail to load or load slowly. Does NOT disconnect you - "
                                  "your IP stays the same. Steps that need Admin are skipped "
                                  "with a note unless you run as Administrator.",
                     text_color=C_MUT, font=(FONT, 11), anchor="w",
                     wraplength=900, justify="left").pack(anchor="w", pady=(0, 4))
        frow = ctk.CTkFrame(scroll, fg_color="transparent")
        frow.pack(fill="x", pady=(0, 4))
        self.flush_btn = ctk.CTkButton(frow, text="Flush Network", width=150,
                                       fg_color="#047857", text_color=C_ONCOLOR, hover_color="#065f46",
                                       command=self._flush_network)
        self.flush_btn.pack(side="left", padx=(0, 8))
        self.flush_prog = ctk.CTkProgressBar(frow, width=280, height=12)
        self.flush_prog.pack(side="left", padx=6)
        self.flush_prog.set(0)
        self.flush_msg = ctk.CTkLabel(scroll, text="", text_color=C_MUT,
                                      font=(FONT, 11), wraplength=900,
                                      justify="left", anchor="w")
        self.flush_msg.pack(anchor="w", pady=(0, 8))

        # --- DNS Switcher (v2.5) ---
        ctk.CTkLabel(scroll, text="DNS Switcher", font=(FONT, 14, "bold"),
                     anchor="w").pack(anchor="w", pady=(12, 4))
        ctk.CTkLabel(scroll, text="Switching DNS needs Admin. Your current DNS is "
                                  "saved before every change — Undo restores it exactly.",
                     text_color=C_MUT, font=(FONT, 11), anchor="w",
                     wraplength=900, justify="left").pack(anchor="w", pady=(0, 4))
        self.dns_current_lbl = ctk.CTkLabel(scroll, text="Current DNS: -",
                                            font=(FONT, 12), anchor="w")
        self.dns_current_lbl.pack(anchor="w", pady=(0, 4))
        drow = ctk.CTkFrame(scroll, fg_color="transparent")
        drow.pack(fill="x", pady=(0, 4))
        self.dns_preset_btns = {}
        for name in ("Cloudflare", "Google", "Quad9"):
            b = ctk.CTkButton(drow, text=name, width=110,
                              fg_color=C_BTN2, text_color=C_BTN2_TXT, hover_color=C_BTN2_HOV,
                              command=lambda n=name: self._set_dns_preset(n))
            b.pack(side="left", padx=(0, 8))
            self.dns_preset_btns[name] = b
        self.dns_auto_btn = ctk.CTkButton(drow, text="Auto (ISP)", width=110,
                                          fg_color=C_BTN2, text_color=C_BTN2_TXT, hover_color=C_BTN2_HOV,
                                          command=self._set_dns_auto_ui)
        self.dns_auto_btn.pack(side="left", padx=(0, 8))
        self.dns_undo_btn = ctk.CTkButton(drow, text="Undo DNS change", width=140,
                                          fg_color="#92400e", text_color=C_ONCOLOR, hover_color="#78350f",
                                          command=self._undo_dns)
        self.dns_undo_btn.pack(side="left")
        drow2 = ctk.CTkFrame(scroll, fg_color="transparent")
        drow2.pack(fill="x", pady=(0, 4))
        self.dns_measure_btn = ctk.CTkButton(drow2, text="Measure fastest DNS",
                                             width=170, fg_color=C_BTN2, text_color=C_BTN2_TXT,
                                             hover_color=C_BTN2_HOV,
                                             command=self._measure_dns)
        self.dns_measure_btn.pack(side="left", padx=(0, 8))
        self.dns_suggest_lbl = ctk.CTkLabel(drow2, text="", text_color=C_MUT,
                                            font=(FONT, 11))
        self.dns_suggest_lbl.pack(side="left")
        self.dns_msg = ctk.CTkLabel(scroll, text="", text_color=C_MUT,
                                    font=(FONT, 11), wraplength=900,
                                    justify="left", anchor="w")
        self.dns_msg.pack(anchor="w", pady=(0, 12))

    def _build_net_repair(self, parent):
        scroll = self._net_tab_scroll(parent)

        # --- Adapter Reset & Deep Reset (v2.5) ---
        ctk.CTkLabel(scroll, text="Adapter Reset & Deep Reset", font=(FONT, 14, "bold"),
                     anchor="w").pack(anchor="w", pady=(12, 4))
        ctk.CTkLabel(scroll, text="Adapter Reset turns your network off for ~5-10 seconds. "
                                  "Deep Reset resets Winsock & TCP/IP — a PC restart is required afterwards.",
                     text_color=C_RED, font=(FONT, 11, "bold"), anchor="w",
                     wraplength=900, justify="left").pack(anchor="w", pady=(0, 4))
        rrow = ctk.CTkFrame(scroll, fg_color="transparent")
        rrow.pack(fill="x", pady=(0, 4))
        self.adapter_reset_btn = ctk.CTkButton(rrow, text="Adapter Reset...", width=150,
                                               fg_color="#92400e", text_color=C_ONCOLOR, hover_color="#78350f",
                                               command=self._adapter_reset_prompt)
        self.adapter_reset_btn.pack(side="left", padx=(0, 8))
        self.deep_reset_btn = ctk.CTkButton(rrow, text="Deep Reset...", width=150,
                                            fg_color="#b91c1c", text_color=C_ONCOLOR, hover_color="#991b1b",
                                            command=self._deep_reset_prompt)
        self.deep_reset_btn.pack(side="left")
        self.reset_msg = ctk.CTkLabel(scroll, text="", text_color=C_MUT,
                                      font=(FONT, 11), wraplength=900,
                                      justify="left", anchor="w")
        self.reset_msg.pack(anchor="w", pady=(0, 8))

    def _refresh_network_all(self):
        """First-visit Network load: info + ports in ONE task (v2.5.5).

        v2.5.6: tasks queue instead of being dropped, so this always
        returns True (runs now or right after the current task).
        The old drop behavior lost the Port load when the startup
        process-list task was still running.
        """
        self.net_info_msg.configure(text="Loading...")
        self.net_ports_msg.configure(text="Loading...")

        def work():
            info = net_info.get_network_info()
            ok, msg, rows = net_ports.list_listening_ports()
            sok, smsg, ssh = net_ports.check_ssh()
            return info, (ok, msg, rows, sok, smsg, ssh)

        def done(res):
            if isinstance(res, Exception):
                self.net_info_msg.configure(text=f"Error: {res}")
                self.net_ports_msg.configure(text=f"Error: {res}")
                return
            info, ports = res
            self._net_info_done(info)
            self._net_ports_done(ports)

        started = self._run_bg([self.net_info_btn, self.net_ports_btn],
                               work, done=done, status="Loading network...")
        if not started:
            self.net_info_msg.configure(text="Busy — please try again.")
            self.net_ports_msg.configure(text="Busy — please try again.")
        return bool(started)

    def _net_info_done(self, res):
        if isinstance(res, Exception):
            self.net_info_msg.configure(text=f"Error: {res}")
            return
        ok, msg, data = res
        self.net_info_box.configure(state="normal")
        self.net_info_box.delete("1.0", "end")
        self.net_info_box.insert("1.0", net_info.format_info(data))
        self.net_info_box.configure(state="disabled")
        self.net_info_msg.configure(text=msg)

    def _net_ports_done(self, res):
        if isinstance(res, Exception):
            self.net_ports_msg.configure(text=f"Error: {res}")
            return
        ok, msg, rows, _sok, smsg, ssh = res
        for i in self.net_port_tree.get_children():
            self.net_port_tree.delete(i)
        for r in rows:
            self.net_port_tree.insert(
                "", "end", text=f"{r['port']}  ({r['bind_ip'] or '-'})",
                values=(r["process"], r["scope"], r["level"]),
                tags=(r["level"],))
        is_open = ssh.get("open", False)
        self.net_ssh_lbl.configure(
            text=smsg, text_color=C_RED if is_open else C_GRN)
        self.net_ports_msg.configure(text=msg if ok else msg)

    def _refresh_net_info(self):
        self.net_info_msg.configure(text="Loading...")

        def work():
            return net_info.get_network_info()

        def done(res):
            self._net_info_done(res)

        if not self._run_bg([self.net_info_btn], work, done=done,
                            status="Loading network info..."):
            # Busy-guard dropped the task — never leave "Loading..."
            # stuck on screen (v2.5.5).
            self.net_info_msg.configure(text="Busy — please try again.")

    def _refresh_ports(self):
        self.net_ports_msg.configure(text="Loading...")

        def work():
            ok, msg, rows = net_ports.list_listening_ports()
            sok, smsg, ssh = net_ports.check_ssh()
            return ok, msg, rows, sok, smsg, ssh

        def done(res):
            self._net_ports_done(res)

        if not self._run_bg([self.net_ports_btn], work, done=done,
                            status="Listing ports..."):
            self.net_ports_msg.configure(text="Busy — please try again.")

    def _port_guide(self):
        sel = self.net_port_tree.selection()
        if not sel:
            ResultDialog(self, "How to close a port",
                         net_ports.get_port_guide(None))
            return
        txt = self.net_port_tree.item(sel[0], "text") or ""
        try:
            port = int(txt.split()[0])
        except (ValueError, IndexError):
            port = None
        ResultDialog(self, "How to close", net_ports.get_port_guide(port))

    def _run_speed_test(self):
        self.net_speed_msg.configure(text="Testing...")

        def work():
            return net_speed.run_speed_test()

        def done(res):
            if isinstance(res, Exception):
                self.net_speed_msg.configure(text=f"Error: {res}")
                return
            ok, msg, results = res
            summary = net_speed.format_speed(results)
            if self._net_before is None:
                self._net_before = results
                self.net_before_lbl.configure(text="Before: " + summary)
                self.net_speed_msg.configure(text="Saved as Before. Run again after "
                                                  "Quick Refresh to compare.")
            else:
                self._net_after = results
                self.net_after_lbl.configure(text="After: " + summary)
                pb = (self._net_before or {}).get("ping_1_1_1_1_ms")
                pa = results.get("ping_1_1_1_1_ms")
                if pb is not None and pa is not None:
                    delta = pa - pb
                    self.net_speed_msg.configure(
                        text=f"Ping change: {delta:+.0f} ms (negative = better).")
                else:
                    self.net_speed_msg.configure(text=msg)
            if not ok:
                self.net_speed_msg.configure(text=msg)

        self._run_bg([self.net_speed_btn], work, done=done,
                     status="Running speed test...", timeout=300)

    def _reset_speed(self):
        self._net_before = None
        self._net_after = None
        self.net_before_lbl.configure(text="Before: -")
        self.net_after_lbl.configure(text="After: -")
        self.net_speed_msg.configure(text="Cleared.")

    def _quick_refresh_net(self):
        self.net_refresh_msg.configure(text="")
        self.net_refresh_prog.set(0)

        def progress(i, total, label):
            try:
                _post_ui(self, lambda: self.net_refresh_prog.set(
                    i / total if total else 0))
                _post_ui(self, lambda: self.net_refresh_msg.configure(
                    text=f"Step: {label}..."))
            except Exception:  # noqa: BLE001
                pass

        def work():
            return net_refresh.quick_refresh(progress_cb=progress)

        def done(res):
            self.net_refresh_prog.set(0)
            if isinstance(res, Exception):
                self.net_refresh_msg.configure(text=f"Error: {res}")
                return
            ok, msg, steps = res
            lines = [msg]
            for s in steps:
                lines.append(f"- {s['step']}: "
                             + ("OK" if s["ok"] else f"FAILED — {s['message']}"))
            self.net_refresh_msg.configure(
                text="\n".join(lines),
                text_color=C_GRN if ok else C_RED)

        self._run_bg([self.net_refresh_btn], work, done=done,
                     status="Refreshing network...", timeout=300)

    def _flush_network(self):
        """Flush Network button: clear stale caches, keep the IP."""
        self.flush_msg.configure(text="")
        self.flush_prog.set(0)

        def progress(i, total, label):
            try:
                _post_ui(self, lambda: self.flush_prog.set(
                    i / total if total else 0))
                _post_ui(self, lambda: self.flush_msg.configure(
                    text=f"Step: {label}..."))
            except Exception:  # noqa: BLE001
                pass

        def work():
            return net_refresh.flush_network(progress_cb=progress)

        def done(res):
            self.flush_prog.set(0)
            if isinstance(res, Exception):
                self.flush_msg.configure(text=f"Error: {res}")
                return
            ok, msg, steps = res
            lines = [msg]
            for s in steps:
                if s.get("skipped"):
                    lines.append(f"- {s['step']}: SKIPPED — {s['message']}")
                else:
                    lines.append(f"- {s['step']}: "
                                 + ("OK" if s["ok"] else f"FAILED — {s['message']}"))
            self.flush_msg.configure(
                text="\n".join(lines),
                text_color=C_GRN if ok else C_RED)

        self._run_bg([self.flush_btn], work, done=done,
                     status="Flushing network caches...", timeout=300)

    # ------------------------- Network v2.5 handlers -------------------------
    def _dns_buttons(self):
        return (list(self.dns_preset_btns.values())
                + [self.dns_auto_btn, self.dns_undo_btn, self.dns_measure_btn])

    def _refresh_dns_current(self):
        def work():
            return net_dns.get_current_dns()

        def done(res):
            if isinstance(res, Exception):
                self.dns_current_lbl.configure(text=f"Current DNS: error ({res})")
                return
            _ok, _msg, data = res
            dns = data.get("dns") or []
            self.dns_current_lbl.configure(
                text=f"Current DNS ({data.get('adapter', '')}): "
                     + (", ".join(dns) if dns else "automatic / unknown"))

        self._run_bg([self.dns_measure_btn], work, done=done,
                     status="Reading DNS...")

    def _set_dns_preset(self, name):
        from tkinter import messagebox
        primary, secondary = net_dns.PRESETS[name]
        if not messagebox.askyesno(
                "Change DNS",
                f"Switch DNS to {name} ({primary} / {secondary})?\n\n"
                "Your current DNS will be saved first — Undo restores it.",
                parent=self):
            return
        self.dns_msg.configure(text="")

        def work():
            return net_dns.set_dns(primary, secondary)

        def done(res):
            if isinstance(res, Exception):
                self.dns_msg.configure(text=f"Error: {res}")
                return
            ok, msg = res
            self.dns_msg.configure(text=msg, text_color=C_GRN if ok else C_RED)
            self._refresh_dns_current()

        self._run_bg(self._dns_buttons(), work, done=done,
                     status="Changing DNS...")

    def _set_dns_auto_ui(self):
        from tkinter import messagebox
        if not messagebox.askyesno(
                "Change DNS",
                "Switch DNS back to automatic (ISP / DHCP)?\n\n"
                "Your current DNS will be saved first — Undo restores it.",
                parent=self):
            return
        self.dns_msg.configure(text="")

        def work():
            return net_dns.set_dns_auto()

        def done(res):
            if isinstance(res, Exception):
                self.dns_msg.configure(text=f"Error: {res}")
                return
            ok, msg = res
            self.dns_msg.configure(text=msg, text_color=C_GRN if ok else C_RED)
            self._refresh_dns_current()

        self._run_bg(self._dns_buttons(), work, done=done,
                     status="Changing DNS...")

    def _undo_dns(self):
        self.dns_msg.configure(text="")

        def work():
            return net_dns.restore_dns()

        def done(res):
            if isinstance(res, Exception):
                self.dns_msg.configure(text=f"Error: {res}")
                return
            ok, msg = res
            self.dns_msg.configure(text=msg, text_color=C_GRN if ok else C_RED)
            self._refresh_dns_current()

        self._run_bg(self._dns_buttons(), work, done=done,
                     status="Restoring DNS...")

    def _measure_dns(self):
        self.dns_suggest_lbl.configure(text="Measuring...")

        def work():
            return net_dns.measure_dns()

        def done(res):
            if isinstance(res, Exception):
                self.dns_suggest_lbl.configure(text=f"Error: {res}")
                return
            ok, msg, results = res
            parts = []
            for r in results:
                parts.append(f"{r['name']}: "
                             + (f"{r['avg_ms']:.0f} ms" if r["ok"] else "failed"))
            self.dns_suggest_lbl.configure(text=msg + "  (" + "; ".join(parts) + ")")

        self._run_bg([self.dns_measure_btn], work, done=done,
                     status="Measuring DNS speed...")

    def _run_diagnostics(self):
        self.diag_box.configure(state="normal")
        self.diag_box.delete("1.0", "end")
        self.diag_box.insert("1.0", "Running diagnostics...")
        self.diag_box.configure(state="disabled")

        def work():
            return net_diag.run_diagnostics()

        def done(res):
            if isinstance(res, Exception):
                text = f"Diagnostics error: {res}"
            else:
                _ok, _msg, data = res
                text = net_diag.format_diagnostics(data)
            self.diag_box.configure(state="normal")
            self.diag_box.delete("1.0", "end")
            self.diag_box.insert("1.0", text)
            self.diag_box.configure(state="disabled")

        self._run_bg([self.diag_btn], work, done=done,
                     status="Running diagnostics...")

    def _find_hogs(self):
        self.hogs_msg.configure(text="Measuring (3s)...")

        def work():
            return net_hogs.get_bandwidth_hogs()

        def done(res):
            if isinstance(res, Exception):
                self.hogs_msg.configure(text=f"Error: {res}")
                return
            ok, msg, data = res
            for i in self.hogs_tree.get_children():
                self.hogs_tree.delete(i)
            self._hog_rows = data.get("rows", [])
            for idx, r in enumerate(self._hog_rows):
                self.hogs_tree.insert(
                    "", "end", iid=str(idx),
                    text=f"{r['process']} (PID {r['pid']})",
                    values=(r["connections"],
                            ", ".join(r["remote_ips"][:3])))
            self.hogs_total_lbl.configure(
                text=f"Total: {data['recv_per_sec'] / 1024:.0f} KB/s down, "
                     f"{data['sent_per_sec'] / 1024:.0f} KB/s up")
            self.hogs_msg.configure(text=msg)

        self._run_bg([self.hogs_btn], work, done=done,
                     status="Measuring bandwidth...")

    def _end_hog(self):
        from tkinter import messagebox
        sel = self.hogs_tree.selection()
        if not sel:
            self.hogs_msg.configure(text="No app selected.")
            return
        targets = []
        for iid in sel:
            r = self._hog_rows[int(iid)]
            if protected.check_process(r["process"], r["pid"]) == "warn":
                if not messagebox.askyesno(
                        "Confirm",
                        f"{r['process']} is a sensitive system process.\n"
                        "Close it anyway?", parent=self):
                    continue
            targets.append((r["pid"], r["process"]))

        def work():
            n = 0
            for pid, _name in targets:
                ok, _ = process_manager.kill_process(pid, force=False)
                n += ok
            return n

        def done(n):
            if isinstance(n, Exception):
                self.hogs_msg.configure(text=f"Error: {n}")
                return
            action_log.log("kill_hogs", {"killed": n})
            self.hogs_msg.configure(text=f"Closed {n}/{len(targets)} app(s).")
            self._find_hogs()

        self._run_bg([self.hogs_kill_btn], work, done=done,
                     status="Closing apps...")

    def _adapter_reset_prompt(self):
        dlg = ctk.CTkToplevel(self)
        dlg.title("Adapter Reset")
        dlg.geometry("500x260")
        _make_modal(dlg, self)
        ctk.CTkLabel(dlg, text="Adapter Reset will turn your network OFF "
                              "for ~5-10 seconds.",
                     font=(FONT, 13, "bold"), text_color=C_RED,
                     wraplength=440, justify="left").pack(padx=16, pady=(16, 6))
        ctk.CTkLabel(dlg, text="Use it when WiFi is stuck or the adapter "
                              "behaves strangely. Your connection should come "
                              "back automatically.",
                     font=(FONT, 12), text_color=C_MUT, wraplength=440,
                     justify="left").pack(padx=16, pady=(0, 10))
        count_lbl = ctk.CTkLabel(dlg, text="Resetting in 3...",
                                 font=(FONT, 14, "bold"))
        count_lbl.pack(pady=6)
        state = {"cancelled": False, "n": 3}

        def cancel():
            state["cancelled"] = True
            dlg.destroy()

        def reset_now():
            state["cancelled"] = True
            dlg.destroy()
            self._run_adapter_reset()

        row = ctk.CTkFrame(dlg, fg_color="transparent")
        row.pack(pady=12)
        ctk.CTkButton(row, text="Cancel", fg_color=C_BTN2, text_color=C_BTN2_TXT,
                      command=cancel).pack(side="left", padx=6)
        ctk.CTkButton(row, text="Reset Now", fg_color="#92400e", text_color=C_ONCOLOR,
                      hover_color="#78350f", command=reset_now).pack(side="left", padx=6)

        def tick():
            if state["cancelled"]:
                return
            try:
                if not dlg.winfo_exists():
                    return
            except Exception:  # noqa: BLE001
                return
            if state["n"] <= 0:
                state["cancelled"] = True
                try:
                    dlg.destroy()
                except Exception:  # noqa: BLE001
                    pass
                self._run_adapter_reset()
                return
            count_lbl.configure(text=f"Resetting in {state['n']}... "
                                     "(press Cancel to stop)")
            state["n"] -= 1
            dlg.after(1000, tick)

        tick()

    def _run_adapter_reset(self):
        self.reset_msg.configure(text="Resetting adapter...")

        def progress(i, total, label):
            try:
                _post_ui(self, lambda: self.reset_msg.configure(
                    text=f"Adapter Reset: {label}..."))
            except Exception:  # noqa: BLE001
                pass

        def work():
            return net_refresh.adapter_reset(progress_cb=progress)

        def done(res):
            if isinstance(res, Exception):
                self.reset_msg.configure(text=f"Error: {res}")
                return
            ok, msg, steps = res
            lines = [msg]
            for s in steps:
                lines.append(f"- {s['step']}: "
                             + ("OK" if s["ok"] else f"FAILED — {s['message']}"))
            self.reset_msg.configure(text="\n".join(lines),
                                     text_color=C_GRN if ok else C_RED)
            self._refresh_net_info()

        self._run_bg([self.adapter_reset_btn], work, done=done,
                     status="Resetting adapter...", timeout=300)

    def _deep_reset_prompt(self):
        dlg = ctk.CTkToplevel(self)
        dlg.title("Deep Reset — DANGER")
        dlg.geometry("520x320")
        _make_modal(dlg, self)
        ctk.CTkLabel(dlg, text="Deep Reset resets Winsock & TCP/IP to defaults.",
                     font=(FONT, 14, "bold"), text_color=C_RED,
                     wraplength=460, justify="left").pack(padx=16, pady=(16, 6))
        ctk.CTkLabel(dlg, text="Only use this when Quick Refresh and Adapter Reset "
                              "did NOT fix the connection.\n\n"
                              "You MUST restart your PC afterwards for it to take effect.",
                     font=(FONT, 12), text_color=C_MUT, wraplength=460,
                     justify="left").pack(padx=16, pady=(0, 10))
        var = tk.BooleanVar(value=False)
        run_btn = ctk.CTkButton(dlg, text="Run Deep Reset", fg_color="#b91c1c", text_color=C_ONCOLOR,
                                hover_color="#991b1b", state="disabled",
                                command=lambda: (dlg.destroy(),
                                                 self._run_deep_reset()))
        cb = ctk.CTkCheckBox(dlg, text="I understand — reset Winsock & TCP/IP "
                                       "and I will restart my PC.",
                             variable=var,
                             command=lambda: run_btn.configure(
                                 state="normal" if var.get() else "disabled"))
        cb.pack(padx=16, pady=6, anchor="w")
        row = ctk.CTkFrame(dlg, fg_color="transparent")
        row.pack(pady=12)
        ctk.CTkButton(row, text="Cancel", fg_color=C_BTN2, text_color=C_BTN2_TXT,
                      command=dlg.destroy).pack(side="left", padx=6)
        run_btn.pack(side="left", padx=6)

    def _run_deep_reset(self):
        self.reset_msg.configure(text="Running Deep Reset...")

        def work():
            return net_refresh.deep_reset()

        def done(res):
            if isinstance(res, Exception):
                self.reset_msg.configure(text=f"Error: {res}")
                return
            ok, msg, steps = res
            lines = [msg]
            for s in steps:
                lines.append(f"- {s['step']}: "
                             + ("OK" if s["ok"] else f"FAILED — {s['message']}"))
            self.reset_msg.configure(text="\n".join(lines),
                                     text_color=C_GRN if ok else C_RED)

        self._run_bg([self.deep_reset_btn], work, done=done,
                     status="Running Deep Reset...")

    # ------------------------- Startup page (v2.5) -------------------------
    def _build_startup(self, page):
        ctk.CTkLabel(page, text="Apps that start with Windows. Disabling renames the "
                                "entry (restorable) — nothing is deleted. Protected "
                                "entries (security / drivers) cannot be disabled.",
                     text_color=C_MUT, font=(FONT, 12), anchor="w",
                     wraplength=900, justify="left").pack(anchor="w", pady=(0, 8))
        self.s_tree = _dark_tree(page)
        self.s_tree["columns"] = ("location", "status", "protected")
        self.s_tree.heading("#0", text="App")
        self.s_tree.heading("location", text="Location")
        self.s_tree.heading("status", text="Status")
        self.s_tree.heading("protected", text="Protected")
        self.s_tree.column("#0", width=320)
        self.s_tree.column("location", width=220)
        self.s_tree.column("status", width=110)
        self.s_tree.column("protected", width=110)
        self.s_tree.pack(fill="both", expand=True, pady=(0, 8))
        self.s_tree.tag_configure("disabled", foreground=C_MUT)
        self.s_tree.tag_configure("prot", foreground=C_YLW)

        row = ctk.CTkFrame(page, fg_color="transparent")
        row.pack(fill="x")
        self.s_refresh_btn = ctk.CTkButton(row, text="Refresh", height=36,
                                           fg_color=C_BTN2, text_color=C_BTN2_TXT, hover_color=C_BTN2_HOV,
                                           command=self._refresh_startup)
        self.s_refresh_btn.pack(side="left", padx=(0, 8))
        self.s_disable_btn = ctk.CTkButton(row, text="Disable selected", height=36,
                                           fg_color="#92400e", text_color=C_ONCOLOR, hover_color="#78350f",
                                           command=lambda: self._toggle_startup(False))
        self.s_disable_btn.pack(side="left", padx=(0, 8))
        self.s_enable_btn = ctk.CTkButton(row, text="Enable selected", height=36,
                                          fg_color="#047857", text_color=C_ONCOLOR, hover_color="#065f46",
                                          command=lambda: self._toggle_startup(True))
        self.s_enable_btn.pack(side="left")
        self.s_msg = ctk.CTkLabel(page, text="", text_color=C_MUT, font=(FONT, 12))
        self.s_msg.pack(anchor="w", pady=(8, 0))

    def _refresh_startup(self):
        self.s_msg.configure(text="Loading...")

        def work():
            return startup_mod.list_startup()

        def done(res):
            if isinstance(res, Exception):
                self.s_msg.configure(text=f"Error: {res}")
                return
            ok, msg, items = res
            for i in self.s_tree.get_children():
                self.s_tree.delete(i)
            self._startup_rows = items
            for idx, it in enumerate(items):
                tags = []
                if it["protected"]:
                    tags.append("prot")
                if not it["enabled"]:
                    tags.append("disabled")
                self.s_tree.insert("", "end", iid=str(idx), text=it["name"],
                                   values=(it["location"],
                                           "Enabled" if it["enabled"] else "Disabled",
                                           "Yes" if it["protected"] else "No"),
                                   tags=tuple(tags))
            self.s_msg.configure(text=msg if ok else msg)

        self._run_bg([self.s_refresh_btn], work, done=done,
                     status="Loading startup apps...")

    def _toggle_startup(self, enable):
        sel = self.s_tree.selection()
        if not sel:
            self.s_msg.configure(text="No startup entry selected.")
            return
        targets = []
        skipped_protected = []
        for iid in sel:
            it = self._startup_rows[int(iid)]
            if it["protected"] and not enable:
                # v2.5.6: skip protected entries, do NOT abort the whole
                # batch when other selected entries are fine.
                skipped_protected.append(it["name"])
                continue
            if it["enabled"] == enable:
                continue
            targets.append(it)
        if not targets:
            if skipped_protected:
                self.s_msg.configure(
                    text="Selected entr(ies) are protected and cannot be "
                         "disabled: " + ", ".join(skipped_protected))
            else:
                self.s_msg.configure(text="Selected entries are already in that state.")
            return

        def work():
            msgs = []
            for it in targets:
                ok, msg = startup_mod.set_enabled(it["key"], it["location"], enable)
                msgs.append(("OK " if ok else "! ") + msg)
            return msgs

        def done(msgs):
            if isinstance(msgs, Exception):
                self.s_msg.configure(text=f"Error: {msgs}")
                return
            text = " | ".join(msgs[:3])
            if skipped_protected:
                text += (" | Skipped (protected): "
                         + ", ".join(skipped_protected))
            self.s_msg.configure(text=text)
            self._refresh_startup()

        self._run_bg([self.s_disable_btn, self.s_enable_btn], work, done=done,
                     status="Changing startup entries...")


def main():
    while True:
        app = App()
        app.mainloop()
        if not app._next_theme:
            break


if __name__ == "__main__":
    main()
