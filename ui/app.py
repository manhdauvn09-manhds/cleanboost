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
_LEVEL_NAMES = {1: "Standard", 2: "Advanced", 3: "Deep"}
ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "assets")
LOGO_PATH = os.path.join(ASSETS_DIR, "logo.png")

# ------------------------- theme -------------------------
# Semantic palette. Every button uses an explicit (bg, text, hover)
# triple from here — never CTk's default text color on a custom bg.
# That default is white, which is invisible on the light theme's pale
# secondary buttons (the "button only appears on hover" bug).
THEMES = {
    "dark": dict(BG="#0b1220", SIDEBAR="#0e1626", CARD="#111b2e",
                 CARD2="#1a2740", LINE="#24344f", TXT="#e8eef9",
                 MUT="#8ea2c4",
                 BTN2="#1c2942", BTN2_TXT="#dde6f5", BTN2_HOV="#2b3c5e"),
    "light": dict(BG="#f2f5fa", SIDEBAR="#ffffff", CARD="#ffffff",
                  CARD2="#e7edf6", LINE="#d3dceb", TXT="#182234",
                  MUT="#5a6b87",
                  BTN2="#e3eaf5", BTN2_TXT="#182234", BTN2_HOV="#ccd8ea"),
}
C_ACC = "#3d7eff"          # accent for graphics / text highlights
C_ACC_HOV = "#2f6ae8"       # hover color for accent buttons
C_ACC_BTN = "#2b63e8"      # primary button bg (white text)
C_ACC_BTN_HOV = "#1f4fc4"  # primary button hover
C_ONCOLOR = "#ffffff"      # text on any colored button
C_GRN = "#16a37a"
C_YLW = "#d98a1f"
C_RED = "#e5484d"

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

# v2.10.0: CustomTkinter only recolors widgets whose colors came from
# theme-color NAMES — widgets built with literal C_* hex values keep the
# old palette after set_theme(), so the theme toggle used to change the
# globals but left every existing widget painted in the old colors. This
# bidirectional map translates any known palette value (old + new, dark +
# light) to its counterpart in the OTHER theme so _repaint_theme() can
# walk the widget tree and actually flip the colors.
_THEME_ROLES = {
    "bg":        (("#0e1117", "#0b1220"), ("#edf0f5", "#f2f5fa")),
    "sidebar":   (("#141926", "#0e1626"), ("#ffffff", "#ffffff")),
    "card":      (("#1a2030", "#111b2e"), ("#ffffff", "#ffffff")),
    "card2":     (("#232c42", "#1a2740"), ("#dfe5ef", "#e7edf6")),
    "line":      (("#2a3348", "#24344f"), ("#c3ccdd", "#d3dceb")),
    "txt":       (("#e8edf7", "#e8eef9"), ("#17202f", "#182234")),
    "mut":       (("#9aa7c2", "#8ea2c4"), ("#4b5b76", "#5a6b87")),
    "btn2":      (("#232c42", "#1c2942"), ("#dbe3f0", "#e3eaf5")),
    "btn2_txt":  (("#e8edf7", "#dde6f5"), ("#17202f", "#182234")),
    "btn2_hov":  (("#33405f", "#2b3c5e"), ("#c2cfe4", "#ccd8ea")),
    "acc":       (("#4f8cff", "#3d7eff"), ("#4f8cff", "#3d7eff")),
    "acc_hov":   (("#3b78f0", "#2f6ae8"), ("#3b78f0", "#2f6ae8")),
    "acc_btn":   (("#2563eb", "#2b63e8"), ("#2563eb", "#2b63e8")),
    "acc_btn_hov": (("#1d4ed8", "#1f4fc4"), ("#1d4ed8", "#1f4fc4")),
    "grn":       (("#1a9e6b", "#16a37a"), ("#1a9e6b", "#16a37a")),
    "ylw":       (("#b8860b", "#d98a1f"), ("#b8860b", "#d98a1f")),
    "red":       (("#e05252", "#e5484d"), ("#e05252", "#e5484d")),
    "danger":    (("#b91c1c", "#c53030"), ("#b91c1c", "#c53030")),
    "danger_hov": (("#991b1b", "#a52626"), ("#991b1b", "#a52626")),
    "ok":        (("#047857", "#0e9f6e"), ("#047857", "#0e9f6e")),
    "ok_hov":    (("#065f46", "#0b7f57"), ("#065f46", "#0b7f57")),
}


def _build_theme_remap():
    remap = {}
    for _role, (darks, lights) in _THEME_ROLES.items():
        for c in darks:
            remap[c] = lights[1]
        for c in lights:
            remap[c] = darks[1]
    return remap


_THEME_REMAP = _build_theme_remap()


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
    if _attempt == 0:
        try:
            win.after_idle(lambda: _style_window_controls(win))
        except Exception:  # noqa: BLE001
            pass


def _dark_tree(parent):
    style = ttk.Style(parent)
    try:
        style.theme_use("clam")
    except Exception:  # noqa: BLE001
        pass
    style.configure("Treeview", background=C_CARD, foreground=C_TXT,
                    fieldbackground=C_CARD, rowheight=32, borderwidth=0,
                    font=(FONT, 10))
    style.configure("Treeview.Heading", background=C_CARD2,
                    foreground=C_MUT, relief="flat", font=(FONT, 9, "bold"),
                    padding=(10, 9))
    style.map("Treeview", background=[("selected", C_ACC_BTN)],
              foreground=[("selected", "#ffffff")])
    style.configure("Treeview", rowheight=32)
    style.configure("TCombobox", fieldbackground=C_CARD, background=C_CARD2,
                    foreground=C_TXT, arrowcolor=C_MUT, bordercolor=C_LINE,
                    lightcolor=C_LINE, darkcolor=C_LINE, padding=7)
    style.map("TCombobox", fieldbackground=[("readonly", C_CARD)],
              foreground=[("readonly", C_TXT)])
    return ttk.Treeview(parent)


def _style_window_controls(root):
    """Apply CleanBoost's control language to one window and its children."""
    danger_words = ("delete", "destroy all", "force kill", "end selected",
                    "review apps", "reset now", "high-risk",
                    "clean items over")
    safe_words = ("quarantine", "light clean", "clean memory", "restore")
    primary_words = ("optimize", "scan", "run ", "flush network",
                     "find bandwidth", "measure fastest", "adapter reset")

    def walk(widget):
        if isinstance(widget, ctk.CTkButton):
            try:
                if getattr(widget, "_cb_nav_button", False):
                    widget.configure(corner_radius=8)
                    for child in widget.winfo_children():
                        walk(child)
                    return
                text = str(widget.cget("text") or "").strip().lower()
                if any(word in text for word in danger_words):
                    fg, hover = "#c53030", "#a52626"
                    text_color = C_ONCOLOR
                elif text.startswith("quarantine"):
                    fg, hover = "#0e9f6e", "#0b7f57"
                    text_color = C_ONCOLOR
                elif any(word in text for word in safe_words):
                    fg, hover = "#0e9f6e", "#0b7f57"
                    text_color = C_ONCOLOR
                elif any(word in text for word in primary_words):
                    fg, hover = C_ACC_BTN, C_ACC_BTN_HOV
                    text_color = C_ONCOLOR
                else:
                    fg, hover = C_BTN2, C_BTN2_HOV
                    text_color = C_BTN2_TXT
                widget.configure(fg_color=fg, hover_color=hover,
                                 text_color=text_color, corner_radius=8,
                                 border_width=0)
                if int(widget.cget("height")) < 32:
                    widget.configure(height=32)
            except Exception:  # noqa: BLE001 - platform-specific CTk controls
                pass
        elif isinstance(widget, ctk.CTkEntry):
            try:
                widget.configure(fg_color=C_BG, text_color=C_TXT,
                                 placeholder_text_color=C_MUT,
                                 border_color=C_LINE, border_width=1,
                                 corner_radius=8)
            except Exception:  # noqa: BLE001
                pass
        elif isinstance(widget, ctk.CTkTextbox):
            try:
                widget.configure(fg_color=C_CARD, text_color=C_TXT,
                                 border_color=C_LINE, border_width=1,
                                 corner_radius=9,
                                 scrollbar_button_color=C_CARD2,
                                 scrollbar_button_hover_color=C_BTN2_HOV)
            except Exception:  # noqa: BLE001
                pass
        elif isinstance(widget, ctk.CTkCheckBox):
            try:
                widget.configure(text_color=C_TXT, fg_color=C_ACC_BTN,
                                 hover_color=C_ACC_BTN_HOV,
                                 border_color=C_LINE,
                                 checkmark_color=C_ONCOLOR,
                                 corner_radius=5, border_width=2)
            except Exception:  # noqa: BLE001
                pass
        elif isinstance(widget, ctk.CTkProgressBar):
            try:
                widget.configure(fg_color=C_CARD2, progress_color=C_ACC,
                                 border_color=C_LINE, corner_radius=5)
            except Exception:  # noqa: BLE001
                pass
        elif isinstance(widget, ctk.CTkTabview):
            try:
                widget.configure(fg_color=C_BG, segmented_button_fg_color=C_CARD,
                                 segmented_button_selected_color=C_ACC_BTN,
                                 segmented_button_selected_hover_color=C_ACC_BTN_HOV,
                                 segmented_button_unselected_color=C_CARD,
                                 segmented_button_unselected_hover_color=C_BTN2_HOV,
                                 text_color=C_TXT, corner_radius=10)
            except Exception:  # noqa: BLE001
                pass
        for child in widget.winfo_children():
            walk(child)

    try:
        walk(root)
    except Exception:  # noqa: BLE001 - window may already be closing
        pass


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
        compact = self._s < 120
        cx, cy = self._s / 2, self._s / 2
        r = self._s / 2 - (12 if compact else 20)
        width = 8 if compact else 13
        pct = max(0, min(100, pct))
        self.create_arc(cx - r, cy - r, cx + r, cy + r, start=90, extent=359.9,
                        style="arc", outline=C_LINE, width=width)
        color = C_ACC if pct < 70 else (C_YLW if pct < 90 else C_RED)
        if pct > 0:
            self.create_arc(cx - r, cy - r, cx + r, cy + r, start=90,
                            extent=-359.9 * pct / 100, style="arc",
                            outline=color, width=width)
        self.create_text(cx, cy - (6 if compact else 10), text=f"{pct:.0f}%",
                         fill=C_TXT, font=(FONT, 17 if compact else 24, "bold"))
        self.create_text(cx, cy + (13 if compact else 18), text=self._title,
                         fill=C_MUT, font=(FONT, 9 if compact else 12))
        if subtitle and not compact:
            self.create_text(cx, cy + 38, text=subtitle,
                             fill=C_MUT, font=(FONT, 10))


class HealthRing(tk.Canvas):
    """Phase 3 #health: a larger radial ring for the Health Score that
    turns GREEN / YELLOW / RED by zone and shows the score in big text.

    Reusable — same pattern as RingGauge but for bounded scores
    (0..100) instead of percentages, with a thicker ring and a softer
    green-by-default color (higher = better, unlike CPU% where higher is
    worse)."""

    def __init__(self, parent, size=140):
        super().__init__(parent, width=size, height=size, bg=C_CARD,
                         highlightthickness=0)
        self._s = size
        self.set(None, "Press Refresh")

    def set(self, score, subtitle=""):
        self.delete("all")
        cx, cy, r = self._s / 2, self._s / 2, self._s / 2 - 18
        # Background ring
        self.create_arc(cx - r, cy - r, cx + r, cy + r, start=90, extent=359.9,
                        style="arc", outline=C_LINE, width=16)
        if score is None:
            self.create_text(cx, cy - 6, text="--",
                             fill=C_TXT,
                             font=(FONT, 22 if self._s < 110 else 28, "bold"))
            self.create_text(cx, cy + 22, text="Health",
                             fill=C_MUT, font=(FONT, 9 if self._s < 110 else 11))
            if subtitle and self._s >= 120:
                self.create_text(cx, cy + 42, text=subtitle,
                                 fill=C_MUT, font=(FONT, 9))
            return
        score = max(0, min(100, score))
        # Color zones: green for >=80, yellow 50-79, red <50. Higher = better.
        if score >= 80:
            color = C_GRN
        elif score >= 50:
            color = C_YLW
        else:
            color = C_RED
        if score > 0:
            self.create_arc(cx - r, cy - r, cx + r, cy + r, start=90,
                            extent=-359.9 * score / 100, style="arc",
                            outline=color, width=16)
        self.create_text(cx, cy - 6, text=f"{score:.0f}",
                         fill=C_TXT,
                         font=(FONT, 22 if self._s < 110 else 28, "bold"))
        self.create_text(cx, cy + 22, text="/ 100",
                         fill=C_MUT, font=(FONT, 9 if self._s < 110 else 11))
        if subtitle and self._s >= 120:
            self.create_text(cx, cy + 42, text=subtitle,
                             fill=color, font=(FONT, 9, "bold"))



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
        ctk.CTkButton(foot, corner_radius=10, text="Close", width=100,
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
        ctk.CTkButton(row, corner_radius=10, text="Cancel", fg_color=C_BTN2,
                      text_color=C_BTN2_TXT, hover_color=C_BTN2_HOV,
                      command=self._no).pack(side="right", padx=6)
        ctk.CTkButton(row, corner_radius=10, text="Delete permanently" if permanent else "Quarantine",
                      fg_color="#c53030" if permanent else "#92400e",
                      text_color=C_ONCOLOR,
                      hover_color="#a52626" if permanent else "#78350f",
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
        run_btn = ctk.CTkButton(self, corner_radius=10, text="I understand — run high-risk actions",
                                fg_color="#c53030", text_color=C_ONCOLOR, hover_color="#a52626",
                                state="disabled",
                                command=self._yes)
        cb = ctk.CTkCheckBox(self, text="I understand the risks above.",
                             variable=var,
                             command=lambda: run_btn.configure(
                                 state="normal" if var.get() else "disabled"))
        cb.pack(padx=16, pady=8, anchor="w")
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(0, 16))
        ctk.CTkButton(row, corner_radius=10, text="Cancel", fg_color=C_BTN2, text_color=C_BTN2_TXT,
                      command=self._no).pack(side="right", padx=6)
        run_btn.pack(side="right", padx=6)

    def _yes(self):
        self.result = True
        self.destroy()

    def _no(self):
        self.destroy()


# Friendly app names for process exe names (v2.8.0). The old generic
# "Force kill the selected process(es)?" popup never said WHAT was
# about to die; the popup now shows these names big, with the exe
# name, PID and RAM underneath, so there is no ambiguity.
_FRIENDLY_APPS = {
    "onedrive.exe": "OneDrive",
    "chrome.exe": "Google Chrome",
    "msedge.exe": "Microsoft Edge",
    "firefox.exe": "Mozilla Firefox",
    "code.exe": "Visual Studio Code",
    "explorer.exe": "Windows Explorer",
    "notepad.exe": "Notepad",
    "spotify.exe": "Spotify",
    "teams.exe": "Microsoft Teams",
    "outlook.exe": "Microsoft Outlook",
    "winword.exe": "Microsoft Word",
    "excel.exe": "Microsoft Excel",
    "powerpnt.exe": "PowerPoint",
    "steam.exe": "Steam",
    "discord.exe": "Discord",
    "slack.exe": "Slack",
    "zoom.exe": "Zoom",
    "vlc.exe": "VLC media player",
    "photoshop.exe": "Adobe Photoshop",
    "cmd.exe": "Command Prompt",
    "powershell.exe": "PowerShell",
    "taskmgr.exe": "Task Manager",
}


def friendly_app_name(exe_name):
    """Human-readable app name for a process exe name."""
    n = (exe_name or "").strip()
    key = n.lower()
    if key in _FRIENDLY_APPS:
        return _FRIENDLY_APPS[key]
    base = n[:-4] if key.endswith(".exe") else n
    if not base:
        return n or "Unknown app"
    if "_" in base or "-" in base:
        return " ".join(w[:1].upper() + w[1:]
                        for w in base.replace("-", "_").split("_") if w)
    return base[:1].upper() + base[1:]


class ForceKillDialog(ctk.CTkToplevel):
    """Force-kill confirmation that NAMES its targets (v2.8.0).

    targets: list of dicts {pid, name, rss, warn}. Sensitive
    (warn) targets get an extra caution line. Modal via _make_modal.
    """

    def __init__(self, master, targets):
        super().__init__(master)
        self.title("Force kill")
        self.geometry("520x460")
        _make_modal(self, master)
        self.result = False
        ctk.CTkLabel(self, text="Force kill these apps?",
                     font=(FONT, 16, "bold")).pack(padx=16, pady=(16, 4))
        ctk.CTkLabel(
            self,
            text="Force kill closes apps immediately — unsaved work in "
                 "them will be LOST.",
            font=(FONT, 12), text_color=C_RED, wraplength=470,
            justify="left").pack(padx=16, pady=(0, 10))
        box = ctk.CTkScrollableFrame(self, label_text="Apps to force kill")
        box.pack(fill="both", expand=True, padx=16, pady=6)
        for t in targets:
            f = ctk.CTkFrame(box, fg_color=C_BTN2)
            f.pack(fill="x", padx=6, pady=4)
            ctk.CTkLabel(f, text=friendly_app_name(t["name"]),
                         font=(FONT, 13, "bold"), anchor="w",
                         wraplength=440, justify="left").pack(
                             anchor="w", padx=10, pady=(8, 0))
            detail = (f"{t['name']}  •  PID {t['pid']}  •  "
                      f"{t.get('rss', 0) / GB:.1f} GB")
            ctk.CTkLabel(f, text=detail, font=(FONT, 11),
                         text_color=C_MUT, anchor="w").pack(
                             anchor="w", padx=10, pady=(0, 2))
            if t.get("warn"):
                ctk.CTkLabel(
                    f, text="(!) Sensitive system process — closing it "
                            "may briefly hide the taskbar.",
                    font=(FONT, 11), text_color=C_YLW, anchor="w",
                    wraplength=440, justify="left").pack(
                        anchor="w", padx=10, pady=(0, 8))
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=14)
        ctk.CTkButton(row, corner_radius=10, text="Cancel", fg_color=C_BTN2,
                      text_color=C_BTN2_TXT,
                      command=self._no).pack(side="right", padx=6)
        ctk.CTkButton(row, corner_radius=10, text="Force kill", fg_color="#c53030",
                      text_color=C_ONCOLOR, hover_color="#a52626",
                      command=self._yes).pack(side="right", padx=6)

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
        ctk.CTkButton(self, corner_radius=10, text="Close", width=120,
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
        ctk.CTkButton(row, corner_radius=10, text="Close selected", fg_color="#c53030", text_color=C_ONCOLOR,
                      hover_color="#a52626", command=self._kill).pack(side="left", padx=4)
        ctk.CTkButton(row, corner_radius=10, text="Cancel", fg_color=C_BTN2, text_color=C_BTN2_TXT,
                      command=lambda: self._close(0)).pack(side="left", padx=4)

    def _kill(self):
        # Bug #4 fix: the old code ran process_manager.kill_process() per
        # ticked app ON THE UI THREAD — each kill calls p.terminate() then
        # p.wait(timeout=5), so with N ticked apps the whole window froze
        # up to N*5 s ("not responding"). Now the kills run in a worker
        # thread; we disable the buttons immediately for feedback and
        # call back into the UI thread when done.
        targets = [pid for pid, v in self._vars.items() if v.get()]
        if not targets:
            self._close(0)
            return
        # Disable the action buttons so the user gets immediate feedback
        # that the kills are in flight (the previous synchronous version
        # gave no feedback at all — the window simply froze).
        for w in self.winfo_children():
            try:
                if isinstance(w, ctk.CTkButton):
                    w.configure(state="disabled")
            except Exception:  # noqa: BLE001
                pass
        progress = ctk.CTkLabel(self, text="Closing apps...",
                                font=(FONT, 12), text_color=C_MUT)
        progress.pack(pady=(0, 6))

        def work():
            n = 0
            for pid in targets:
                try:
                    ok, _ = process_manager.kill_process(pid, force=False)
                    n += ok
                except Exception:  # noqa: BLE001
                    pass
            return n

        def done(n):
            # Don't touch a destroyed dialog's widgets.
            try:
                if not self.winfo_exists():
                    return
            except Exception:  # noqa: BLE001
                return
            if isinstance(n, Exception):
                progress.configure(text=f"Error: {n}")
            else:
                self._close(n)

        # Reuse the parent App's worker pool — do NOT spawn a raw thread
        # here, because the dialog might be destroyed while the kills
        # are still in flight and a raw thread would touch destroyed Tk
        # widgets. _run_bg posts results back via the safe UI queue.
        master_app = self._find_app()
        if master_app is not None:
            master_app._run_bg([], work, done=done,
                              status="Closing apps...", quiet=True)
        else:
            # Fallback (no App reachable): run in a daemon thread and
            # post back via the dialog's own after().
            import threading as _th

            def runner():
                try:
                    n = work()
                except Exception as e:  # noqa: BLE001
                    n = e
                try:
                    self.after(0, lambda: done(n))
                except Exception:  # noqa: BLE001
                    pass

            _th.Thread(target=runner, daemon=True).start()

    def _find_app(self):
        """Walk up the toplevel chain to the main App instance."""
        w = self
        while w is not None:
            if hasattr(w, "_run_bg") and hasattr(w, "_bg_queue"):
                return w
            try:
                w = w.master
            except Exception:  # noqa: BLE001
                return None
        return None

    def _close(self, n=0):
        self.destroy()
        self._on_done(n)


class HelpWindow(ctk.CTkToplevel):
    """User manual viewer (reads USER_MANUAL.md)."""

    def __init__(self, master):
        super().__init__(master)
        self.title("User Manual — CleanBoost")
        self.geometry("780x600")
        self.configure(fg_color=C_BG)
        _make_modal(self, master)
        header = ctk.CTkFrame(self, fg_color=C_CARD, corner_radius=10)
        header.pack(fill="x", padx=18, pady=(18, 8))
        ctk.CTkLabel(header, text="CLEANBOOST  /  USER GUIDE",
                     font=(FONT, 9, "bold"), text_color=C_ACC).pack(
                         anchor="w", padx=16, pady=(12, 2))
        ctk.CTkLabel(header, text="User Manual",
                     font=(FONT, 19, "bold")).pack(anchor="w", padx=16,
                                                    pady=(0, 12))
        self.box = ctk.CTkTextbox(self, wrap="word", font=(FONT, 12),
                                  fg_color=C_CARD, text_color=C_TXT,
                                  border_color=C_LINE, border_width=1,
                                  corner_radius=10, scrollbar_button_color=C_CARD2,
                                  scrollbar_button_hover_color=C_BTN2_HOV)
        self.box.pack(fill="both", expand=True, padx=18, pady=6)
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
        ctk.CTkButton(self, corner_radius=8, text="Close guide", width=120,
                      height=34, fg_color=C_BTN2, text_color=C_BTN2_TXT,
                      hover_color=C_BTN2_HOV,
                      command=self.destroy).pack(anchor="e", padx=18,
                                                 pady=(4, 16))

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

# Phase 3 (UI revamp): the sidebar is grouped into 3 sections by purpose
# instead of a flat list of 6 nav buttons. Each entry is (group, key).
# The labels ("MONITOR/CLEANUP/SYSTEM") render as section headers between
# the buttons.
PAGE_GROUPS = [
    ("MONITOR", [("dash", "Overview"), ("proc", "Processes"), ("net", "Network")]),
    ("CLEANUP", [("clean", "Disk Cleaner"), ("quar", "Quarantine")]),
    ("SYSTEM", [("startup", "Startup")]),
]

# v2.10.0: one-line descriptor under the page title in the top bar.
PAGE_SUBTITLES = {
    "dash": "Live health of your machine — RAM, CPU, disk and one-click actions",
    "proc": "Every running process — search, sort, end or force-kill",
    "clean": "Junk files by risk level — scan, review, clean to quarantine",
    "quar": "Everything CleanBoost quarantined — restore or delete for good",
    "net": "Diagnose and repair your network connection",
    "startup": "Apps that launch with Windows — disable or re-enable",
}


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
        self._proc_reselect = set()  # v2.8.0: rows to re-select after refresh
        self._net_loaded = False
        self._startup_loaded = False
        self._net_before = None
        self._net_after = None
        self._proc_sort = ("rss", True)
        self._nav_btns = {}
        self._pages = {}

        self._build_main()
        _style_window_controls(self)
        self._show_page("dash")

        self._tick_dashboard()
        self._refresh_proc()
        self._refresh_quarantine()
        self._refresh_sidebar_badges()  # Phase 3: populate sidebar badges

    # ------------------------- busy guard -------------------------
    def _run_bg(self, buttons, work, done=None, status: "str | None" = "Working...",
                timeout=None, quiet=False):
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

        v2.9.0 (Phase 2 #3): quiet=True skips the status bar update and
        the button-disable dance — for fire-and-forget background samplers
        like the dashboard tick that must not clobber the user-facing
        status line or block real button clicks.

        v2.9.0 regression fix: quiet samplers used to still take the
        busy lock and queue. The dashboard tick fires every 2s, so during
        a long task (scan, DISM) it piled up in the queue and delayed
        every real click behind it. Now quiet tasks run detached and
        post their result back through the UI queue — they never hold
        the lock, never queue, never block a button.
        """
        if quiet:
            def _quiet_runner():
                try:
                    res = work()
                except BaseException as e:  # noqa: BLE001
                    res = e
                cb = done
                if cb is not None:
                    _post_ui(self, lambda: cb(res))
            threading.Thread(target=_quiet_runner, daemon=True).start()
            return True
        if timeout is None:
            timeout = self._BG_DEFAULT_TIMEOUT
        task = (list(buttons), work, done, status, timeout, quiet)
        if not quiet:
            for b in buttons:
                try:
                    b.configure(state="disabled")
                except Exception:  # noqa: BLE001
                    pass
        if self._busy:
            self._bg_queue.append(task)
            if not quiet and status:
                # v2.8.0: a queued click used to show NOTHING — the button
                # just sat disabled, which users read as "the button died".
                # Name the queued task; the running task's tick (below)
                # also lists the queue from now on.
                self._set_status(
                    f"Queued: {status} — waiting for the current task")
            return True
        self._start_bg(*task)  # _start_bg takes all 6 (incl. quiet)
        return True

    # Default hard limit per background task (v2.7.0). Long jobs pass
    # their own bigger timeout to _run_bg.
    _BG_DEFAULT_TIMEOUT = 180
    # A task still running after this long is probably stuck (v2.6.1).
    _BG_WARN_SECONDS = 15 * 60

    def _start_bg(self, buttons, work, done, status, timeout, quiet=False):
        self._busy = True
        if not quiet:
            self._set_status(status)
        self._bg_task_id = getattr(self, "_bg_task_id", 0) + 1
        tid = self._bg_task_id
        self._bg_current = (tid, list(buttons))
        t0 = time.time()
        if not quiet:
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
                      warned=False, last_sec=-1, quiet=quiet)

    def _bg_poll(self, tid, t0, buttons, done, status, timeout, holder,
                 warned, last_sec, quiet=False):
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
        if sec != last_sec and not quiet:
            last_sec = sec
            mm, ss = sec // 60, sec % 60
            # v2.8.0: the tick also names queued work, so the status
            # bar always answers "what is running — and what is next".
            queued = ""
            if self._bg_queue:
                queued = (" | Queued: "
                          + "; ".join(t[3] for t in self._bg_queue
                                      if t[3]))
            self._set_status(f"{status} - {mm:02d}:{ss:02d}{queued}")
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
            last_sec, quiet=quiet))

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
        if self._bg_queue and not self._busy:
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
                self._set_status(f"Error: {e}", auto_clear=5000)
        # v2.9.0 regression fix: a task queued behind a normally-finished
        # one never ran — _finish_bg released the busy lock but forgot to
        # drain the queue (only _abandon_bg did). Clicking a button while
        # the startup loads left the task queued forever and its button
        # disabled — the exact "dead button" symptom v2.5.6+v2.7.0 fixed.
        # Drain only when done() did NOT already start a task: the kill
        # flow's done() refreshes the process list (starts a task) and
        # queues the badge refresh, and starting that queued task here
        # would bump _bg_task_id past the still-running refresh, whose
        # finish would then be discarded as "late" (no re-select).
        if self._bg_queue and not self._busy:
            self._start_bg(*self._bg_queue.pop(0))

    @staticmethod
    def _crash_log_path_local():
        """Compute the crash-log path WITHOUT importing gui (Bug UX #3).

        Mirrors gui._crash_log_path but lives here so a broken gui.py
        import cannot kill the safety net.
        """
        if sys.platform == "win32":
            base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
            d = os.path.join(base, "CleanBoost")
        else:
            d = os.path.join(os.path.expanduser("~"),
                             ".config", "cleanboost")
        try:
            os.makedirs(d, exist_ok=True)
        except OSError:
            pass
        return os.path.join(d, "crash.log")

    # ------------------------- shell -------------------------
    def _build_menu(self):
        """Keep the app chrome native-menu-free; navigation is themed below."""
        self._menubar = None

    def _about(self):
        from tkinter import messagebox
        try:
            messagebox.showinfo(
                "About CleanBoost",
                "CleanBoost PRO\n"
                "System care: RAM, CPU, disk, junk files, network.\n\n"
                "Version 2.9.0\n"
                "Built for Windows 10/11 and Linux.",
                parent=self)
        except Exception:  # noqa: BLE001
            pass

    def _set_theme_mode(self, mode):
        """Apply a specific theme (dark/light) and repaint surfaces."""
        if mode not in THEMES:
            return
        set_theme(mode)
        try:
            self.configure(fg_color=C_BG)
        except Exception:  # noqa: BLE001
            pass
        self._repaint_theme()
        _style_window_controls(self)
        self._next_theme = mode
        try:
            self.theme_btn.configure(
                text="☀️" if mode == "dark" else "🌙")
        except Exception:  # noqa: BLE001
            pass

    def _repaint_theme(self):
        """Recolor every existing widget for the newly-loaded theme.

        v2.10.0: the theme toggle used to only reassign the C_* globals —
        widgets built with literal hex colors kept the old palette, so the
        light theme never actually rendered. Walk the tree and remap every
        color-bearing property through _THEME_REMAP (old/new, dark/light).
        """
        def remap(color):
            if isinstance(color, str):
                key = color.lower()
                if key in _THEME_REMAP:
                    return _THEME_REMAP[key]
            return color

        def repaint(widget):
            props = {}
            for prop in ("fg_color", "text_color", "hover_color",
                         "border_color", "placeholder_text_color",
                         "label_text_color", "progress_color"):
                try:
                    val = widget.cget(prop)
                except Exception:  # noqa: BLE001 - prop not supported
                    continue
                nv = remap(val)
                if nv != val:
                    props[prop] = nv
            if props:
                try:
                    widget.configure(**props)
                except Exception:  # noqa: BLE001
                    pass
            if isinstance(widget, tk.Canvas):
                try:
                    widget.configure(bg=remap(widget.cget("bg")))
                except Exception:  # noqa: BLE001
                    pass
            for child in widget.winfo_children():
                repaint(child)

        try:
            repaint(self)
        except Exception:  # noqa: BLE001
            pass
        # Composite widgets (CTkScrollableFrame) hide their toplevel frame
        # inside an internal canvas, so winfo_children() never reaches
        # them — repaint every page frame explicitly.
        for _key, (f, _label) in getattr(self, "_pages", {}).items():
            try:
                repaint(f)
            except Exception:  # noqa: BLE001
                pass
        # ttk.Treeview colors come from a shared Style, not widget props.
        try:
            _dark_tree(self)
        except Exception:  # noqa: BLE001
            pass

    def _build_sidebar(self):
        # Phase 3 UI revamp: sidebar grouped into 3 sections (MONITOR /
        # CLEANUP / SYSTEM) instead of a flat 6-button column. Each
        # section uses a muted label header. Some buttons get a numeric
        # "badge" label (quarantine item count, process count) that is
        # refreshed lazily by _refresh_sidebar_badges().
        #
        # v2.10.0 restyle: tighter brand block, hairline dividers,
        # rounded nav pills and a quieter footer for a professional look.
        sb = ctk.CTkFrame(self, fg_color=C_SIDEBAR, corner_radius=0, width=224)
        sb.pack(side="left", fill="y")
        sb.pack_propagate(False)

        brand = ctk.CTkFrame(sb, fg_color="transparent")
        brand.pack(fill="x", padx=18, pady=(22, 12))
        try:
            from PIL import Image as PILImage
            _pil = PILImage.open(LOGO_PATH)
            self._logo_img = ctk.CTkImage(_pil, size=(46, 46))
            ctk.CTkLabel(brand, image=self._logo_img, text="").pack(
                side="left", padx=(0, 12))
        except Exception:  # noqa: BLE001
            pass
        bt = ctk.CTkFrame(brand, fg_color="transparent")
        bt.pack(side="left")
        ctk.CTkLabel(bt, text="CleanBoost", font=(FONT, 18, "bold"),
                     anchor="w").pack(anchor="w")
        ctk.CTkLabel(bt, text="PRO · system care", font=(FONT, 10),
                     text_color=C_MUT, anchor="w").pack(anchor="w")

        ctk.CTkFrame(sb, fg_color=C_LINE, height=1).pack(fill="x",
                                                         padx=16, pady=(0, 10))

        # Group container that we'll refresh badge labels inside.
        self._sidebar_container = ctk.CTkFrame(sb, fg_color="transparent")
        self._sidebar_container.pack(fill="x", padx=8, pady=(4, 0))
        self._sidebar_badges = {}   # key -> CTkLabel that holds the badge text
        for grp, entries in PAGE_GROUPS:
            hdr = ctk.CTkLabel(
                self._sidebar_container, text=grp,
                font=(FONT, 9, "bold"),
                text_color=C_MUT, anchor="w")
            hdr.pack(fill="x", padx=(14, 0), pady=(10, 3))
            for key, label in entries:
                icon = PAGE_ICONS[key]
                row = ctk.CTkFrame(self._sidebar_container,
                                   fg_color="transparent")
                row.pack(fill="x", pady=1)
                b = ctk.CTkButton(
                    row, text=f"  {icon}  {label}", anchor="w",
                    fg_color="transparent", text_color=C_TXT,
                    hover_color=C_BTN2_HOV, font=(FONT, 13),
                    height=36, corner_radius=8,
                    command=lambda k=key: self._show_page(k))
                b.pack(side="left", fill="x", expand=True)
                # The badge label sits to the right; its text is refreshed
                # lazily — only the quarantine badge starts non-empty.
                badge = ctk.CTkLabel(row, text="", font=(FONT, 9, "bold"),
                                     text_color=C_MUT, anchor="center",
                                     width=28)
                badge.pack(side="right", padx=(0, 8))
                self._nav_btns[key] = b
                self._sidebar_badges[key] = badge

        ctk.CTkLabel(sb, text="", fg_color="transparent").pack(fill="both", expand=True)
        ctk.CTkFrame(sb, fg_color=C_LINE, height=1).pack(fill="x", padx=16)
        ctk.CTkLabel(sb, text="© Dau Sy Manh", font=(FONT, 10),
                     text_color=C_MUT).pack(pady=(8, 2))
        ctk.CTkLabel(sb, text="CleanBoost v2.9.0", font=(FONT, 10),
                     text_color=C_MUT).pack(pady=(0, 14))

    def _build_main(self):
        self._nav_btns = {}
        self._sidebar_badges = {}
        main = ctk.CTkFrame(self, fg_color=C_BG, corner_radius=0)
        main.pack(fill="both", expand=True)

        # Product bar: identity left, global command/search and utility
        # actions right. Navigation is a separate, grouped horizontal menu.
        top = ctk.CTkFrame(main, fg_color=C_SIDEBAR, height=66,
                           corner_radius=0)
        top.pack(fill="x")
        top.pack_propagate(False)

        brand = ctk.CTkFrame(top, fg_color="transparent")
        brand.pack(side="left", padx=(22, 24))
        try:
            from PIL import Image as PILImage
            self._logo_img = ctk.CTkImage(PILImage.open(LOGO_PATH),
                                          size=(36, 36))
            ctk.CTkLabel(brand, image=self._logo_img, text="").pack(
                side="left", padx=(0, 10))
        except Exception:  # noqa: BLE001
            pass
        brand_text = ctk.CTkFrame(brand, fg_color="transparent")
        brand_text.pack(side="left")
        ctk.CTkLabel(brand_text, text="CLEANBOOST", font=(FONT, 14, "bold"),
                     anchor="w").pack(anchor="w")
        ctk.CTkLabel(brand_text, text="PC CARE CONSOLE", font=(FONT, 9),
                     text_color=C_MUT, anchor="w").pack(anchor="w")

        # Global search (Phase 3 #search): filter current data sets.
        srch = ctk.CTkFrame(top, fg_color=C_BG, corner_radius=9,
                            height=36, border_width=1, border_color=C_LINE)
        srch.pack(side="left", padx=(20, 0))
        srch.pack_propagate(False)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write",
                                  lambda *_: self._on_search_changed())
        search_entry = ctk.CTkEntry(
            srch, textvariable=self.search_var, width=210, height=34,
            border_width=0, fg_color="transparent",
            placeholder_text="Search this workspace",
            font=(FONT, 12), corner_radius=9)
        search_entry.pack(side="left", padx=10)
        ctk.CTkLabel(srch, text="⌕", font=(FONT, 20),
                     text_color=C_MUT).pack(side="left", padx=(4, 10))

        tools = ctk.CTkFrame(top, fg_color="transparent")
        tools.pack(side="right", padx=22)
        self.opt_btn = ctk.CTkButton(
            tools, text="Run optimization", width=160, height=36,
            font=(FONT, 12, "bold"), fg_color=C_ACC_BTN,
            text_color=C_ONCOLOR, hover_color=C_ACC_BTN_HOV,
            corner_radius=9,
            command=self._optimize_all)
        self.opt_btn.pack(side="right", padx=(10, 0))
        help_btn = ctk.CTkButton(tools, text="Help", width=54, height=36,
                                 font=(FONT, 11, "bold"), fg_color=C_BTN2,
                                 text_color=C_BTN2_TXT,
                                 hover_color=C_BTN2_HOV, corner_radius=9,
                                 command=lambda: HelpWindow(self))
        help_btn.pack(side="right", padx=(8, 0))
        self.theme_btn = ctk.CTkButton(
            tools, text="☀️" if C_BG == THEMES["dark"]["BG"] else "🌙",
            width=38, height=36, font=(FONT, 14), fg_color=C_BTN2,
            text_color=C_BTN2_TXT,
            hover_color=C_BTN2_HOV, corner_radius=9,
            command=self._toggle_theme)
        self.theme_btn.pack(side="right", padx=(8, 0))
        is_admin = privilege.is_admin()
        self.admin_badge = ctk.CTkLabel(
            tools, text="ADMIN" if is_admin else "STANDARD USER",
            font=(FONT, 9, "bold"), text_color=C_GRN if is_admin else C_MUT,
            fg_color=C_CARD, corner_radius=8)
        self.admin_badge.pack(side="right", padx=(0, 8), ipadx=8, ipady=5)

        # Category menu replaces the old permanent sidebar. Each group is
        # a compact horizontal menu with a clear, task-oriented category.
        nav_shell = ctk.CTkFrame(main, fg_color=C_CARD, corner_radius=0,
                                 height=58, border_width=0)
        nav_shell.pack(fill="x")
        nav_shell.pack_propagate(False)
        self._sidebar_container = ctk.CTkFrame(nav_shell,
                                               fg_color="transparent")
        self._sidebar_container.pack(side="left", padx=18, pady=7)
        self._sidebar_badges = {}
        for grp, entries in PAGE_GROUPS:
            group = ctk.CTkFrame(self._sidebar_container,
                                 fg_color="transparent")
            group.pack(side="left", padx=(0, 14))
            ctk.CTkLabel(group, text=grp.title(), font=(FONT, 8, "bold"),
                         text_color=C_MUT).pack(anchor="w", padx=(8, 0))
            buttons = ctk.CTkFrame(group, fg_color="transparent")
            buttons.pack(anchor="w")
            for key, label in entries:
                b = ctk.CTkButton(
                    buttons, text=f"{PAGE_ICONS[key]}  {label}",
                    height=30, width=max(112, len(label) * 9 + 68),
                    font=(FONT, 11, "bold"), anchor="center",
                    fg_color="transparent", text_color=C_MUT,
                    hover_color=C_BTN2_HOV, corner_radius=7,
                    command=lambda k=key: self._show_page(k))
                b.pack(side="left", padx=2)
                b._cb_nav_button = True
                self._nav_btns[key] = b
                badge = ctk.CTkLabel(b, text="", font=(FONT, 8, "bold"),
                                     text_color=C_MUT, width=0)
                badge.place_forget()
                self._sidebar_badges[key] = badge

        # Page title and helper copy sit below navigation, aligned with
        # the work surface rather than competing with global controls.
        heading = ctk.CTkFrame(main, fg_color="transparent", height=70)
        heading.pack(fill="x", padx=28, pady=(14, 0))
        heading.pack_propagate(False)
        self.page_title = ctk.CTkLabel(heading, text="",
                                       font=(FONT, 22, "bold"), anchor="w")
        self.page_title.pack(anchor="w")
        self.page_subtitle = ctk.CTkLabel(heading, text="", font=(FONT, 11),
                                          text_color=C_MUT, anchor="w")
        self.page_subtitle.pack(anchor="w", pady=(1, 0))

        # pages
        self.page_host = ctk.CTkFrame(main, fg_color=C_BG)
        self.page_host.pack(fill="both", expand=True, padx=28, pady=(4, 10))
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

        # Phase 3 #toast: a small overlay that surfaces action results
        # (kill done, clean done, ...) and auto-hides after 5s, instead
        # of permanent label text that is easy to mistake for stale info.
        self._toast_frame = ctk.CTkFrame(main, fg_color=C_CARD,
                                         corner_radius=12,
                                         border_width=1,
                                         border_color=C_LINE)
        self._toast_frame.place(relx=1.0, rely=1.0,
                                anchor="se", x=-20, y=-50, relwidth=0.32)
        self._toast_frame.place_forget()
        self._toast_label = ctk.CTkLabel(self._toast_frame, text="",
                                          font=(FONT, 12), anchor="w",
                                          justify="left", wraplength=380)
        self._toast_label.pack(anchor="w", padx=14, pady=10)
        self._toast_after_id = None

    def show_toast(self, message, ms=5000):
        """Phase 3 #toast: surface an action result as an auto-hiding
        hover overlay in the bottom-right corner."""
        try:
            self._toast_label.configure(text=message)
            self._toast_frame.place(relx=1.0, rely=1.0,
                                     anchor="se", x=-20, y=-50,
                                     relwidth=0.32)
        except Exception:  # noqa: BLE001
            return
        if self._toast_after_id is not None:
            try:
                self.after_cancel(self._toast_after_id)
            except Exception:  # noqa: BLE001
                pass
        self._toast_after_id = self.after(
            ms, lambda: self._hide_toast())

    def _hide_toast(self):
        try:
            self._toast_frame.place_forget()
        except Exception:  # noqa: BLE001
            pass
        self._toast_after_id = None

    def _refresh_sidebar_badges(self):
        """Refresh numeric badges on the categorized navigation controls.
        Runs in a worker because Q.list_items() etc. may touch disk."""
        def work():
            badges = {}
            try:
                badges["quar"] = len(Q.list_items())
            except Exception:  # noqa: BLE001
                badges["quar"] = 0
            try:
                badges["proc"] = len(process_manager.list_processes())
            except Exception:  # noqa: BLE001
                badges["proc"] = 0
            return badges

        def done(badges):
            if isinstance(badges, Exception):
                return
            for key, badge in self._sidebar_badges.items():
                n = badges.get(key, 0)
                txt = str(n) if n else ""
                try:
                    badge.configure(
                        text=txt,
                        text_color=C_RED if n and key == "quar" else C_MUT)
                    if txt:
                        badge.place(relx=1.0, rely=0.5, anchor="e",
                                    x=-9)
                    else:
                        badge.place_forget()
                except Exception:  # noqa: BLE001
                    pass

        self._run_bg([], work, done=done, status=None, quiet=True)

    def _on_search_changed(self):
        """Phase 3 #search: filter rows on the current page for terms
        typed into the global search bar. Currently drives the
        Processes and Quarantine tables; future tabs can subscribe."""
        q = self.search_var.get().strip().lower()
        # Apply to the visible page only.
        for key, (w, _label) in self._pages.items():
            if not w.winfo_ismapped():
                continue
            if key == "proc" and hasattr(self, "proc_tree"):
                tree = self.proc_tree
                for iid in tree.get_children():
                    name = (tree.item(iid, "text") or "").lower()
                    tags = " ".join(str(t) for t in
                                    (tree.item(iid, "values") or [])).lower()
                    # RG-1 fix: ttk.Treeview.reattach = move(item, parent,
                    # INDEX) — index is required (no default). "" → TypeError
                    # per keystroke, swallowed by Tk = silent search failure.
                    if q in name or q in tags:
                        tree.move(iid, "", "end")
                    else:
                        tree.detach(iid)
            elif key == "quar" and hasattr(self, "quar_tree"):
                tree = self.quar_tree
                for iid in tree.get_children():
                    name = (tree.item(iid, "text") or "").lower()
                    tags = " ".join(str(t) for t in
                                    (tree.item(iid, "values") or [])).lower()
                    if q in name or q in tags:
                        tree.move(iid, "", "end")
                    else:
                        tree.detach(iid)

    def _toggle_theme(self):
        # Bug #6 fix: do NOT destroy() the App — it drops all in-flight
        # state (scan results, quarantine selection, hogs table, speed
        # before/after). ctk.set_appearance_mode() (called inside
        # set_theme) already re-colors every CustomTkinter widget live,
        # so toggling without destroy keeps the user's state intact.
        new = "light" if C_BG == THEMES["dark"]["BG"] else "dark"
        self._set_theme_mode(new)

    def _show_page(self, key):
        for k, b in self._nav_btns.items():
            b.configure(fg_color=C_ACC_BTN if k == key else "transparent",
                        text_color=C_ONCOLOR if k == key else C_MUT)
        for k, (f, label) in self._pages.items():
            if k == key:
                f.pack(fill="both", expand=True)
                self.page_title.configure(text=label)
                try:
                    self.page_subtitle.configure(
                        text=PAGE_SUBTITLES.get(key, ""))
                except Exception:  # noqa: BLE001
                    pass
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
            # Bug #5 fix: load the current DNS on first Network-tab visit
            # too. The DNS Switcher used to read "Current DNS: -" until the
            # user changed DNS once, because _refresh_dns_current was only
            # ever called as the done-callback of a change.
            if hasattr(self, "dns_current_lbl"):
                self._refresh_dns_current()
        if key == "startup" and not getattr(self, "_startup_loaded", False):
            self._startup_loaded = True
            self._refresh_startup()

    def _set_status(self, text, auto_clear=None):
        """Update the bottom status bar.

        v2.9.0 regression fix: the busy guard (and _tick_status) called
        this helper but it was never defined, so every background task
        crashed at startup with AttributeError ('_tkinter.tkapp' object
        has no attribute '_set_status'). auto_clear (ms) clears the
        line again after a delay (used for transient error messages);
        a pending auto-clear is cancelled so a new message is never
        wiped by a stale timer.
        """
        try:
            self.status_lbl.configure(text=text)
        except Exception:  # noqa: BLE001 - window going away
            pass
        if auto_clear:
            pending = getattr(self, "_status_clear_after", None)
            if pending is not None:
                try:
                    self.after_cancel(pending)
                except Exception:  # noqa: BLE001
                    pass
            self._status_clear_after = self.after(
                auto_clear, lambda: self._set_status(""))

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
        page.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="dash")
        page.grid_columnconfigure(4, weight=2, uniform="dash")
        page.grid_rowconfigure(6, weight=1)

        self.d_banner = ctk.CTkLabel(page, text="", fg_color="#7f1d1d",
                                     corner_radius=8, text_color="#ffffff",
                                     font=(FONT, 12, "bold"))

        # Executive status panel: one visual anchor, one main action.
        hero = ctk.CTkFrame(page, fg_color=C_CARD, corner_radius=14,
                            border_width=1, border_color=C_LINE)
        hero.grid(row=1, column=0, columnspan=5, sticky="ew", pady=(0, 12))
        hero.grid_columnconfigure(0, weight=1)
        hero.grid_columnconfigure(1, weight=0)
        hero_left = ctk.CTkFrame(hero, fg_color="transparent")
        hero_left.grid(row=0, column=0, sticky="nsew", padx=(22, 12),
                       pady=9)
        ctk.CTkLabel(hero_left, text="SYSTEM OVERVIEW",
                     font=(FONT, 9, "bold"), text_color=C_ACC,
                     anchor="w").pack(anchor="w")
        ctk.CTkLabel(hero_left, text="Your PC, at a glance",
                     font=(FONT, 23, "bold"), anchor="w").pack(
                         anchor="w", pady=(5, 2))
        ctk.CTkLabel(hero_left,
                     text="Monitor resource use, review system health, and choose a safe next step.",
                     font=(FONT, 12), text_color=C_MUT, anchor="w",
                     wraplength=600, justify="left").pack(anchor="w")
        self.dash_msg = ctk.CTkLabel(hero_left, text="",
                                     text_color=C_MUT, font=(FONT, 11),
                                     anchor="w", wraplength=600,
                                     justify="left")
        self.dash_msg.pack(anchor="w", pady=(8, 0))

        hero_action = ctk.CTkFrame(hero, fg_color=C_CARD2, corner_radius=11)
        hero_action.grid(row=0, column=1, sticky="ns", padx=(8, 18),
                         pady=6)
        ctk.CTkLabel(hero_action, text="QUICK OPTIMIZATION",
                     font=(FONT, 9, "bold"), text_color=C_MUT).pack(
                         anchor="w", padx=13, pady=(5, 1))
        ctk.CTkLabel(hero_action,
                     text="Level 1 cleanup · quarantine only",
                     font=(FONT, 10), text_color=C_TXT,
                     justify="left").pack(anchor="w", padx=13, pady=(0, 5))
        self.optimize_btn = ctk.CTkButton(
            hero_action, text="Optimize this PC", height=28,
            fg_color=C_ACC_BTN, hover_color=C_ACC_BTN_HOV,
            text_color=C_ONCOLOR, font=(FONT, 11, "bold"),
            corner_radius=8, command=self._optimize)
        self.optimize_btn.pack(fill="x", padx=12, pady=(0, 8))
        self.opt_prog = ctk.CTkProgressBar(hero_action, height=4)
        self.opt_prog.pack(fill="x", padx=13, pady=(0, 2))
        self.opt_prog.set(0)
        self.opt_msg = ctk.CTkLabel(hero_action, text="Ready when you are",
                                    font=(FONT, 9), text_color=C_MUT,
                                    wraplength=240, justify="left")
        self.opt_msg.pack(anchor="w", padx=13, pady=(0, 4))

        # Resource telemetry strip. Rings are intentionally subordinate
        # to the hero and have equal widths for fast scanning.
        metric_specs = (("RAM", "g_ram"), ("CPU", "g_cpu"),
                        ("Disk", "g_disk"))
        for col, (label, attr) in enumerate(metric_specs):
            card = ctk.CTkFrame(page, fg_color=C_CARD, corner_radius=12,
                                border_width=1, border_color=C_LINE)
            card.grid(row=2, column=col, sticky="nsew", padx=(0, 8),
                      pady=(0, 12))
            ctk.CTkLabel(card, text=label.upper(), font=(FONT, 9, "bold"),
                         text_color=C_MUT).pack(anchor="w", padx=13,
                                                pady=(10, 0))
            gauge = RingGauge(card, label, size=94)
            gauge.pack(anchor="center", padx=4, pady=(0, 3))
            setattr(self, attr, gauge)

        # Health panel shares the strip, but gets extra width and emphasis.
        health = ctk.CTkFrame(page, fg_color=C_CARD, corner_radius=12,
                              border_width=1, border_color=C_LINE)
        health.grid(row=2, column=3, columnspan=2, sticky="nsew",
                    padx=(0, 0), pady=(0, 12))
        health.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(health, text="HEALTH SCORE", font=(FONT, 9, "bold"),
                     text_color=C_MUT).grid(row=0, column=0, columnspan=2,
                                            sticky="w", padx=16, pady=(11, 0))
        self.health_ring = HealthRing(health, size=82)
        self.health_ring.grid(row=1, column=0, rowspan=3, padx=(8, 2),
                              pady=(1, 5))
        self.health_score_lbl = ctk.CTkLabel(
            health, text="-- / 100", font=(FONT, 21, "bold"),
            text_color=C_ACC, anchor="w")
        self.health_score_lbl.grid(row=1, column=1, sticky="sw",
                                   padx=(2, 12), pady=(7, 0))
        self.health_break_lbl = ctk.CTkLabel(
            health, text="Refresh to check system health.", font=(FONT, 10),
            text_color=C_MUT, anchor="w", wraplength=280, justify="left")
        self.health_break_lbl.grid(row=2, column=1, sticky="nw",
                                   padx=(2, 12), pady=(2, 0))
        self.health_suggest_lbl = ctk.CTkLabel(
            health, text="", font=(FONT, 10), text_color=C_TXT,
            anchor="w", wraplength=280, justify="left")
        self.health_suggest_lbl.grid(row=3, column=1, sticky="nw",
                                     padx=(2, 12), pady=(1, 0))
        self.health_refresh_btn = ctk.CTkButton(
            health, text="Refresh score", height=28, width=118,
            fg_color=C_BTN2, text_color=C_BTN2_TXT,
            hover_color=C_BTN2_HOV, font=(FONT, 10, "bold"),
            corner_radius=7, command=self._refresh_health)
        self.health_refresh_btn.grid(row=4, column=1, sticky="w",
                                     padx=(2, 12), pady=(2, 9))

        # Action shelf: safe routine clean and explicit RAM recovery.
        ctk.CTkLabel(page, text="RECOMMENDED ACTIONS",
                     font=(FONT, 9, "bold"), text_color=C_MUT,
                     anchor="w").grid(row=3, column=0, columnspan=5,
                                      sticky="w", pady=(2, 6))
        action_shelf = ctk.CTkFrame(page, fg_color="transparent")
        action_shelf.grid(row=4, column=0, columnspan=5, sticky="ew",
                          pady=(0, 8))
        action_shelf.grid_columnconfigure((0, 1), weight=1, uniform="actions")
        c1 = ctk.CTkFrame(action_shelf, fg_color=C_CARD, corner_radius=12,
                          border_width=1, border_color=C_LINE)
        c1.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        ctk.CTkLabel(c1, text="Recover memory", font=(FONT, 13, "bold"),
                     anchor="w").pack(anchor="w", padx=16, pady=(13, 3))
        ctk.CTkLabel(c1, text="Review memory-heavy apps before closing any process.",
                     font=(FONT, 10), text_color=C_MUT, anchor="w",
                     wraplength=410, justify="left").pack(anchor="w", padx=16)
        self.emergency_btn = ctk.CTkButton(
            c1, text="Review apps", height=32, fg_color="#c53030",
            text_color=C_ONCOLOR, hover_color="#a52626",
            font=(FONT, 10, "bold"), corner_radius=7,
            command=self._emergency)
        self.emergency_btn.pack(anchor="w", padx=16, pady=(7, 9))

        c2 = ctk.CTkFrame(action_shelf, fg_color=C_CARD, corner_radius=12,
                          border_width=1, border_color=C_LINE)
        c2.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        ctk.CTkLabel(c2, text="Light memory cleanup", font=(FONT, 13, "bold"),
                     anchor="w").pack(anchor="w", padx=16, pady=(13, 3))
        ctk.CTkLabel(c2, text="Clear standby cache without closing your apps.",
                     font=(FONT, 10), text_color=C_MUT, anchor="w",
                     wraplength=410, justify="left").pack(anchor="w", padx=16)
        self.light_btn = ctk.CTkButton(
            c2, text="Clean memory", height=32, fg_color="#0e9f6e",
            text_color=C_ONCOLOR, hover_color="#0b7f57",
            font=(FONT, 10, "bold"), corner_radius=7, command=self._light)
        self.light_btn.pack(anchor="w", padx=16, pady=(7, 9))

        # Process snapshot is a single, legible work area rather than two
        # equal-height text boxes competing with the system summary.
        process_head = ctk.CTkFrame(page, fg_color="transparent")
        process_head.grid(row=5, column=0, columnspan=5, sticky="ew",
                          pady=(0, 5))
        ctk.CTkLabel(process_head, text="RESOURCE-HEAVY PROCESSES",
                     font=(FONT, 9, "bold"), text_color=C_MUT,
                     anchor="w").pack(side="left")
        ctk.CTkLabel(process_head, text="Sorted snapshots · RAM and CPU",
                     font=(FONT, 9), text_color=C_MUT,
                     anchor="w").pack(side="left", padx=(10, 0))
        self.top_refresh_btn = ctk.CTkButton(
            process_head, text="Refresh", width=78, height=27,
            fg_color=C_BTN2, text_color=C_BTN2_TXT,
            hover_color=C_BTN2_HOV, font=(FONT, 9, "bold"),
            corner_radius=7, command=self._refresh_top)
        self.top_refresh_btn.pack(side="right")

        tables = ctk.CTkFrame(page, fg_color="transparent")
        tables.grid(row=6, column=0, columnspan=5, sticky="nsew")
        tables.grid_columnconfigure((0, 1), weight=1, uniform="tables")
        t1 = ctk.CTkFrame(tables, fg_color=C_CARD, corner_radius=11,
                          border_width=1, border_color=C_LINE)
        t1.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        ctk.CTkLabel(t1, text="BY MEMORY", font=(FONT, 9, "bold"),
                     text_color=C_MUT, anchor="w").pack(
                         anchor="w", padx=12, pady=(9, 2))
        self.top_ram_box = ctk.CTkTextbox(t1, height=118, font=(MONO, 10),
                                          fg_color="transparent",
                                          border_width=0, corner_radius=0)
        self.top_ram_box.pack(fill="both", expand=True, padx=8, pady=(0, 7))
        self.top_ram_box.insert("1.0", "Loading...")
        self.top_ram_box.configure(state="disabled")
        t2 = ctk.CTkFrame(tables, fg_color=C_CARD, corner_radius=11,
                          border_width=1, border_color=C_LINE)
        t2.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        ctk.CTkLabel(t2, text="BY CPU", font=(FONT, 9, "bold"),
                     text_color=C_MUT, anchor="w").pack(
                         anchor="w", padx=12, pady=(9, 2))
        self.top_cpu_box = ctk.CTkTextbox(t2, height=118, font=(MONO, 10),
                                          fg_color="transparent",
                                          border_width=0, corner_radius=0)
        self.top_cpu_box.pack(fill="both", expand=True, padx=8, pady=(0, 7))
        self.top_cpu_box.insert("1.0", "Loading...")
        self.top_cpu_box.configure(state="disabled")

    def _tick_dashboard(self):
        # Bug #3 fix: the old code called system_info.cpu_percent() (which
        # does psutil.cpu_percent(interval=0.5) — a 0.5s BLOCKING call) on
        # the Tk UI thread, freezing the window ~0.5s every 2s. Now the
        # sampling runs in a background worker and the UI is updated via
        # _post_ui; the next tick is scheduled AFTER the result lands so
        # ticks never overlap.
        def work():
            mem = system_info.memory()
            cpu = system_info.cpu_percent()
            root = "C:\\" if sys.platform == "win32" else "/"
            disk = system_info.disk(root)
            return mem, cpu, disk

        def done(res):
            if getattr(self, "_closing", False):
                return
            if isinstance(res, Exception):
                # Don't kill the dashboard on a transient sample error —
                # just reschedule and try again next tick.
                self.after(2000, self._tick_dashboard)
                return
            mem, cpu, disk = res
            try:
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
                    self.d_banner.grid(row=0, column=0, columnspan=5,
                                       sticky="ew", pady=(0, 12))
                else:
                    self.d_banner.grid_forget()
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

        self._run_bg([], work, done=done, status=None, quiet=True)

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
            # Phase 3 #health: update the ring too.
            try:
                self.health_ring.set(data["score"], "")
            except Exception:  # noqa: BLE001
                pass
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
                self.show_toast(f"Optimize failed: {res}")
                return
            ok, msg, report = res
            self.opt_msg.configure(text=msg)
            if ok:
                ResultDialog(self, "Optimize finished",
                             optimizer.format_report(report))
                self.show_toast(f"Optimize finished — RAM freed {report.get('ram_freed_mb', 0):.0f} MB")
                self._refresh_quarantine()
                self._refresh_sidebar_badges()

        self._run_bg([self.optimize_btn], work, done=done,
                     status="Optimizing...", timeout=900)

    def _optimize_all(self):
        """Phase 3: global Optimize 1-Click button on the topbar. Calls
        the same _optimize pipeline that the dashboard button uses, so
        there's exactly one optimize code path."""
        self._optimize()

    # ------------------------- Processes page -------------------------
    def _build_processes(self, page):
        top = ctk.CTkFrame(page, fg_color="transparent")
        top.pack(fill="x", pady=(0, 8))
        self.p_search = ctk.CTkEntry(top, placeholder_text="Search processes...",
                                    width=300, height=36)
        self.p_search.pack(side="left", padx=(0, 8))
        self.p_search.bind("<KeyRelease>", lambda _e: self._fill_proc())
        self.p_refresh_btn = ctk.CTkButton(top, corner_radius=10, text="Refresh", width=110, height=36,
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
        self.p_kill_btn = ctk.CTkButton(row, corner_radius=10, text="End selected", height=36,
                                        command=lambda: self._kill_selected(False))
        self.p_kill_btn.pack(side="left", padx=(0, 8))
        self.p_fkill_btn = ctk.CTkButton(row, corner_radius=10, text="Force kill", height=36,
                                         fg_color="#c53030", text_color=C_ONCOLOR, hover_color="#a52626",
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
        # v2.8.0: re-select rows the kill flow asked to keep (respawned
        # / still-running targets, by PID) so retrying is one click.
        want = getattr(self, "_proc_reselect", set())
        if want:
            self._proc_reselect = set()
            for iid in self.p_tree.get_children():
                if iid in want:
                    self.p_tree.selection_add(iid)
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
            # v2.8.0: "No process selected." used to be a small grey
            # label only — easy to miss, so a second click looked like
            # a dead button. Say it in the status bar too.
            self.p_msg.configure(text="No process selected — click a row first.")
            self._set_status("No process selected — click a row first.")
            return
        targets = []
        for iid in sel:
            pid = int(iid)
            r = next((x for x in self._proc_rows if x["pid"] == pid), None)
            targets.append({
                "pid": pid,
                "name": r["name"] if r else f"PID {pid}",
                "rss": r["rss"] if r else 0,
                "warn": protected.check_process(
                    r["name"] if r else f"PID {pid}", pid) == "warn",
            })
        # v2.8.0: force kill now confirms with a dialog that NAMES
        # every target (friendly app name + exe + PID + RAM) instead
        # of the old generic "process(es)?" messagebox.
        if force:
            dlg = ForceKillDialog(self, targets)
            self.wait_window(dlg)
            if not dlg.result:
                return
        else:
            from tkinter import messagebox
            keep = []
            for t in targets:
                if t["warn"] and not messagebox.askyesno(
                        "Confirm",
                        f"{friendly_app_name(t['name'])} ({t['name']}) is "
                        "a sensitive system process.\nClose it anyway?",
                        parent=self):
                    continue
                keep.append(t)
            targets = keep
            if not targets:
                return

        def work():
            # v2.8.0: verify every kill instead of trusting it. An app
            # that restarts itself (OneDrive) used to be reported as
            # "Closed 1/1" while still sitting in the list — the user
            # reasonably concluded the button was broken.
            killed, respawned, alive, failed = [], [], [], []
            for t in targets:
                known = process_manager.snapshot_pids_by_name(t["name"])
                ok, msg = process_manager.kill_process(t["pid"], force=force)
                if not ok:
                    failed.append((t["name"], msg))
                    continue
                state, new_pid = process_manager.verify_process_gone(
                    t["pid"], t["name"], known_pids=known)
                if state == "gone":
                    killed.append(t["name"])
                elif state == "respawned":
                    respawned.append((t["name"], new_pid))
                else:
                    alive.append(t["name"])
            return {"killed": killed, "respawned": respawned,
                    "alive": alive, "failed": failed}

        def done(res):
            if isinstance(res, Exception):
                self.p_msg.configure(text=f"Error: {res}")
                return
            killed, respawned = res["killed"], res["respawned"]
            alive, failed = res["alive"], res["failed"]
            action_log.log("kill_gui", {"force": force,
                                        "killed": len(killed),
                                        "respawned": len(respawned),
                                        "failed": len(failed)})
            parts = [f"Closed {len(killed)}/{len(targets)} process(es)."]
            for nm, new_pid in respawned[:3]:
                if nm.lower() == "onedrive.exe":
                    tip = ("Disable it in the Startup tab or unlink it "
                           "in OneDrive Settings to stop it for good.")
                else:
                    tip = ("Disable it in the Startup tab to stop it "
                           "coming back.")
                parts.append(f"⚠ {friendly_app_name(nm)} restarted itself "
                             f"(new PID {new_pid}) — {tip}")
            if alive:
                parts.append("Still running: "
                             + ", ".join(friendly_app_name(x)
                                         for x in alive[:3])
                             + " — try again, or run as Administrator.")
            if failed:
                detail = "; ".join(
                    f"{friendly_app_name(nm)} ({nm}): {m}"
                    for nm, m in failed[:3])
                parts.append(f"Could not close — {detail}.")
                if any("access" in m.lower() or "denied" in m.lower()
                       for _nm, m in failed):
                    parts.append("Tip: apps running as Administrator cannot "
                                 "be closed by a normal session — relaunch "
                                 "CleanBoost via run_cleanboost_admin.bat.")
            # v2.5.2: a killed app with a startup entry comes back on
            # next boot — tell the user instead of letting it silently
            # "restart the old app".
            if sys.platform == "win32" and killed:
                try:
                    ok_s, _m, entries = startup_mod.list_startup()
                    if ok_s:
                        respawn = set()
                        for pname in killed:
                            for e in entries:
                                if e["enabled"] and pname.lower() in (e["value"] or "").lower():
                                    respawn.add(e["name"])
                        if respawn:
                            parts.append("Note: " + ", ".join(sorted(respawn))
                                         + " start(s) with Windows and will come back "
                                           "after restart — disable in the Startup tab.")
                except Exception:  # noqa: BLE001
                    pass
            # v2.8.0: re-select respawned / still-running rows BY PID
            # after the refresh, so retrying is one click, not a
            # re-hunt (and unrelated same-name rows are NOT selected).
            alive_pids = {t["pid"] for t in targets
                          if t["name"] in set(alive)}
            self._proc_reselect = ({str(new_pid)
                                    for _nm, new_pid in respawned}
                                   | {str(p) for p in alive_pids})
            # v2.7.0: refresh FIRST (it clears p_msg when it starts),
            # then set the result message so it actually stays visible.
            self._refresh_proc()
            self.p_msg.configure(text=" ".join(parts))
            self.show_toast(" ".join(parts), ms=4000)
            self._refresh_sidebar_badges()  # Phase 3: refresh proc count

        # v2.8.0: the status bar names WHAT is being closed, not just
        # "Closing processes...".
        names = ", ".join(friendly_app_name(t["name"])
                          for t in targets[:3])
        label = (f"Force killing {names}..."
                 if force else f"Closing {names}...")
        self._run_bg([self.p_kill_btn, self.p_fkill_btn], work, done=done,
                     status=label)

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
        self.c_scan_btn = ctk.CTkButton(row, corner_radius=10, text="Scan", width=150, height=38,
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
        self.c_del_btn = ctk.CTkButton(brow, corner_radius=10, text="Delete to free space",
                                       height=40, fg_color="#c53030", text_color=C_ONCOLOR,
                                       hover_color="#a52626", font=(FONT, 13, "bold"),
                                       command=lambda: self._do_clean(True))
        self.c_del_btn.pack(side="left", padx=(0, 8))
        self.c_q_btn = ctk.CTkButton(brow, corner_radius=10, text="Quarantine (safe)",
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
                     work, done=done,
                     status=f"Scanning ({_LEVEL_NAMES.get(level, level)})...",
                     timeout=900)

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
            # Bug #1 fix: do NOT skip action-specials (DISM / Docker prune /
            # Snap prune) — they return size 0 / count 0 by design (they run
            # a command instead of deleting measured files). Show them when
            # they are enabled for this OS so the user can tick & run them.
            is_special = bool(res.get("note")) and res["size"] == 0
            if res["size"] == 0 and res["count"] == 0 and not is_special:
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
            if is_special:
                name += "  [ACTION]"
            ctk.CTkLabel(top, text=name, font=(FONT, 12, "bold"),
                         wraplength=520, justify="left").pack(side="left")
            size_label = "— (action)" if is_special else _fmt_gb(res["size"])
            ctk.CTkLabel(top, text=size_label, font=(FONT, 13, "bold"),
                         text_color=C_ACC).pack(side="right", padx=(8, 0))
            ctk.CTkButton(top, corner_radius=10, text="Details", width=80, height=28,
                          fg_color=C_BTN2, text_color=C_BTN2_TXT, hover_color=C_BTN2_HOV,
                          command=lambda r=res: DetailDialog(self, r)).pack(side="right")

            impact_txt = rule.get("impact", "")
            if is_special and res.get("note"):
                # For action-specials, lead with the note (what command runs).
                impact_txt = (res["note"] + ("  " + impact_txt if impact_txt else ""))
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
                     work, done=done,
                     status=f"Cleaning {len(items)} group(s)...",
                     timeout=1900)

    def _after_clean(self, summary):
        if isinstance(summary, Exception):
            from tkinter import messagebox
            messagebox.showerror("Error", f"Cleanup failed: {summary}", parent=self)
            self.show_toast(f"Cleanup failed: {summary}", ms=6000)
            return
        ResultDialog(self, "Cleanup finished", fmt_summary(summary))
        self._refresh_quarantine()
        self._refresh_sidebar_badges()
        # Phase 3: toast the freed-space result instead of leaving the
        # status bar to be silently overwritten by the next tick.
        try:
            freed = summary.get("freed", 0) if isinstance(summary, dict) else 0
            self.show_toast(
                f"Cleanup finished — freed {_fmt_size(freed)}.",
                ms=5000)
        except Exception:  # noqa: BLE001
            pass
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
        self.q_refresh_btn = ctk.CTkButton(row, corner_radius=10, text="Refresh", height=36, fg_color=C_BTN2, text_color=C_BTN2_TXT,
                                           hover_color=C_BTN2_HOV,
                                           command=self._refresh_quarantine)
        self.q_refresh_btn.pack(side="left", padx=(0, 8))
        self.q_restore_btn = ctk.CTkButton(row, corner_radius=10, text="Restore selected", height=36,
                                           fg_color="#0e9f6e", text_color=C_ONCOLOR, hover_color="#0b7f57",
                                           command=self._q_restore)
        self.q_restore_btn.pack(side="left", padx=(0, 8))
        self.q_delete_btn = ctk.CTkButton(row, corner_radius=10, text="Delete permanently", height=36,
                                          fg_color="#c53030", text_color=C_ONCOLOR, hover_color="#a52626",
                                          command=self._q_delete)
        self.q_delete_btn.pack(side="left", padx=(0, 8))
        self.q_purge_btn = ctk.CTkButton(row, corner_radius=10, text="Clean items over 14 days", height=36,
                                         fg_color=C_BTN2, text_color=C_BTN2_TXT, hover_color=C_BTN2_HOV,
                                         command=self._q_purge)
        self.q_purge_btn.pack(side="left", padx=(0, 8))
        self.q_all_btn = ctk.CTkButton(row, corner_radius=10, text="Select all", height=36, fg_color=C_BTN2, text_color=C_BTN2_TXT,
                                       hover_color=C_BTN2_HOV,
                                       command=lambda: self._q_select_all(None))
        self.q_all_btn.pack(side="left", padx=(0, 8))
        self.q_destroy_btn = ctk.CTkButton(row, corner_radius=10, text="Destroy All", height=36,
                                            fg_color="#7f1d1d", text_color=C_ONCOLOR, hover_color="#a52626",
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
        self._run_bg(self._q_buttons, work, done=done,
                     status=f"Restoring {len(sel)} item(s)...", timeout=900)

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
                     status=f"Deleting {len(sel)} item(s) permanently...",
                     timeout=900)

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
        run_btn = ctk.CTkButton(dlg, corner_radius=10, text="Destroy All", fg_color="#7f1d1d", text_color=C_ONCOLOR,
                                hover_color="#a52626", state="disabled",
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
        ctk.CTkButton(row, corner_radius=10, text="Cancel", fg_color=C_BTN2, text_color=C_BTN2_TXT,
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
            self.show_toast(
                f"Destroy All — freed {_fmt_size(summary.get('freed', 0))}.",
                ms=5000)
            self._refresh_quarantine()
            self._refresh_sidebar_badges()

        self._q_prog_set(0)
        self._run_bg(self._q_buttons, work, done=done,
                     status="Destroying all quarantined items...", timeout=900)


    # ------------------------- Network page (v2.4) -------------------------
    def _build_network(self, page):
        # Phase 3 (#net accordion): collapse the 4 hard tabs into a labeled
        # accordion-style section header so the user always sees what each
        # group does at once. We keep the CTkTabview (it handles focus and
        # keyboard nav well) but add a clearer tab caption above it with
        # ICON + purpose, replacing the old one-line hint.
        header = ctk.CTkFrame(page, fg_color="transparent")
        header.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(
            header,
            text=(
                "📊 Overview = see info/ports   •  ⚡ Test = speed + diagnostics + hogs   "
                "•  🔄 DNS & Refresh = change DNS / flush caches   "
                "•  🛠 Repair = adapter / deep reset (Windows only)"
            ),
            text_color=C_MUT, font=(FONT, 12), anchor="w",
            wraplength=900, justify="left"
        ).pack(side="left", fill="x")
        ctk.CTkButton(header, corner_radius=10, text="Guide", width=90,
                      fg_color=C_BTN2, text_color=C_BTN2_TXT, hover_color=C_BTN2_HOV,
                      command=self._open_network_guide).pack(side="right")
        tabs = ctk.CTkTabview(page)
        tabs.pack(fill="both", expand=True)
        # Phase 3: rename tabs to clearer purpose-first labels.
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
        self.net_info_btn = ctk.CTkButton(row, corner_radius=10, text="Refresh Info", width=130,
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
        self.net_ports_btn = ctk.CTkButton(prow, corner_radius=10, text="Refresh Ports", width=130,
                                           fg_color=C_BTN2, text_color=C_BTN2_TXT, hover_color=C_BTN2_HOV,
                                           command=self._refresh_ports)
        self.net_ports_btn.pack(side="left", padx=(0, 8))
        self.net_guide_btn = ctk.CTkButton(prow, corner_radius=10, text="How to close", width=130,
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
        self.net_speed_btn = ctk.CTkButton(srow, corner_radius=10, text="Run Speed Test", width=150,
                                           fg_color=C_BTN2, text_color=C_BTN2_TXT, hover_color=C_BTN2_HOV,
                                           command=self._run_speed_test)
        self.net_speed_btn.pack(side="left", padx=(0, 8))
        self.net_speed_reset_btn = ctk.CTkButton(srow, corner_radius=10, text="Reset", width=90,
                                                 fg_color=C_BTN2, text_color=C_BTN2_TXT, hover_color=C_BTN2_HOV,
                                                 command=self._reset_speed)
        self.net_speed_reset_btn.pack(side="left")
        self.net_speed_msg = ctk.CTkLabel(srow, text="", text_color=C_MUT,
                                          font=(FONT, 11))
        self.net_speed_msg.pack(side="left", padx=10)
        # --- Network Diagnostics (v2.5) ---
        ctk.CTkLabel(scroll, text="Network Diagnostics", font=(FONT, 14, "bold"),
                     anchor="w").pack(anchor="w", pady=(0, 4))
        self.diag_btn = ctk.CTkButton(scroll, corner_radius=10, text="Run Diagnostics", width=160,
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
        self.hogs_btn = ctk.CTkButton(hrow, corner_radius=10, text="Find Bandwidth Hogs", width=170,
                                      fg_color=C_BTN2, text_color=C_BTN2_TXT, hover_color=C_BTN2_HOV,
                                      command=self._find_hogs)
        self.hogs_btn.pack(side="left", padx=(0, 8))
        self.hogs_kill_btn = ctk.CTkButton(hrow, corner_radius=10, text="End selected", width=130,
                                           fg_color="#c53030", text_color=C_ONCOLOR, hover_color="#a52626",
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
        self.net_refresh_btn = ctk.CTkButton(qrow, corner_radius=10, text="Quick Refresh", width=150,
                                             fg_color="#0e9f6e", text_color=C_ONCOLOR, hover_color="#0b7f57",
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
        self.flush_btn = ctk.CTkButton(frow, corner_radius=10, text="Flush Network", width=150,
                                       fg_color="#0e9f6e", text_color=C_ONCOLOR, hover_color="#0b7f57",
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
            b = ctk.CTkButton(drow, corner_radius=10, text=name, width=110,
                              fg_color=C_BTN2, text_color=C_BTN2_TXT, hover_color=C_BTN2_HOV,
                              command=lambda n=name: self._set_dns_preset(n))
            b.pack(side="left", padx=(0, 8))
            self.dns_preset_btns[name] = b
        self.dns_auto_btn = ctk.CTkButton(drow, corner_radius=10, text="Auto (ISP)", width=110,
                                          fg_color=C_BTN2, text_color=C_BTN2_TXT, hover_color=C_BTN2_HOV,
                                          command=self._set_dns_auto_ui)
        self.dns_auto_btn.pack(side="left", padx=(0, 8))
        self.dns_undo_btn = ctk.CTkButton(drow, corner_radius=10, text="Undo DNS change", width=140,
                                          fg_color="#92400e", text_color=C_ONCOLOR, hover_color="#78350f",
                                          command=self._undo_dns)
        self.dns_undo_btn.pack(side="left")
        drow2 = ctk.CTkFrame(scroll, fg_color="transparent")
        drow2.pack(fill="x", pady=(0, 4))
        self.dns_measure_btn = ctk.CTkButton(drow2, corner_radius=10, text="Measure fastest DNS",
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
        self.adapter_reset_btn = ctk.CTkButton(rrow, corner_radius=10, text="Adapter Reset...", width=150,
                                               fg_color="#92400e", text_color=C_ONCOLOR, hover_color="#78350f",
                                               command=self._adapter_reset_prompt)
        self.adapter_reset_btn.pack(side="left", padx=(0, 8))
        self.deep_reset_btn = ctk.CTkButton(rrow, corner_radius=10, text="Deep Reset...", width=150,
                                            fg_color="#c53030", text_color=C_ONCOLOR, hover_color="#a52626",
                                            command=self._deep_reset_prompt)
        self.deep_reset_btn.pack(side="left")
        self.reset_msg = ctk.CTkLabel(scroll, text="", text_color=C_MUT,
                                      font=(FONT, 11), wraplength=900,
                                      justify="left", anchor="w")
        self.reset_msg.pack(anchor="w", pady=(0, 8))

        # Phase 3 platform-gate: Adapter Reset / Deep Reset are Windows-only
        # (netsh winsock / ip reset). On other OSes the buttons used to be
        # clickable and then produced "requires Windows" — confusing.
        if sys.platform != "win32":
            for b in (self.adapter_reset_btn, self.deep_reset_btn):
                b.configure(state="disabled")
            ctk.CTkLabel(
                scroll,
                text=(
                    "Adapter / Deep Reset are Windows-only — they run "
                    "'netsh winsock reset' and similar. On Linux/macOS "
                    "use 'systemctl restart NetworkManager' or "
                    "'sudo ifconfig <iface> down && up'."
                ),
                text_color=C_YLW, font=(FONT, 11, "italic"),
                wraplength=900, justify="left", anchor="w"
            ).pack(anchor="w", pady=(4, 0))

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

        # _run_bg always returns True (queue-now); the dead "if not started"
        # branch (Phase 2 UX fix) could never fire and misled readers into
        # thinking there was a busy-fallback that did nothing.
        self._run_bg([self.net_info_btn, self.net_ports_btn],
                     work, done=done, status="Loading network...")
        return True

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

        # _run_bg always returns True (queue-now); dead branch removed.
        self._run_bg([self.net_info_btn], work, done=done,
                     status="Loading network info...")

    def _refresh_ports(self):
        self.net_ports_msg.configure(text="Loading...")

        def work():
            ok, msg, rows = net_ports.list_listening_ports()
            sok, smsg, ssh = net_ports.check_ssh()
            return ok, msg, rows, sok, smsg, ssh

        def done(res):
            self._net_ports_done(res)

        # _run_bg always returns True (queue-now); dead branch removed.
        self._run_bg([self.net_ports_btn], work, done=done,
                     status="Listing ports...")

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
                     status=f"Changing DNS to {name} ({primary})...")

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
                     status="Switching DNS to automatic (ISP)...")

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
                     status="Restoring saved DNS settings...")

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
            # v2.8.0: a pending kill result survives the refresh —
            # the old code overwrote "Closed 1/1" with the measurement
            # text the instant it arrived (same family as the v2.7.0
            # kill-message bug).
            pending = getattr(self, "_hog_result_msg", "")
            self._hog_result_msg = ""
            self.hogs_msg.configure(
                text=msg + (f" — {pending}" if pending else ""))

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
            # v2.8.0: do not set the message here — _find_hogs() below
            # overwrites it immediately. Park it for _find_hogs' done().
            self._hog_result_msg = f"Closed {n}/{len(targets)} app(s)."
            self._find_hogs()

        names = ", ".join(friendly_app_name(nm) for _pid, nm in targets[:3])
        self._run_bg([self.hogs_kill_btn], work, done=done,
                     status=f"Closing {names}...")

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
        ctk.CTkButton(row, corner_radius=10, text="Cancel", fg_color=C_BTN2, text_color=C_BTN2_TXT,
                      command=cancel).pack(side="left", padx=6)
        ctk.CTkButton(row, corner_radius=10, text="Reset Now", fg_color="#92400e", text_color=C_ONCOLOR,
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
        run_btn = ctk.CTkButton(dlg, corner_radius=10, text="Run Deep Reset", fg_color="#c53030", text_color=C_ONCOLOR,
                                hover_color="#a52626", state="disabled",
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
        ctk.CTkButton(row, corner_radius=10, text="Cancel", fg_color=C_BTN2, text_color=C_BTN2_TXT,
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
        self.s_refresh_btn = ctk.CTkButton(row, corner_radius=10, text="Refresh", height=36,
                                           fg_color=C_BTN2, text_color=C_BTN2_TXT, hover_color=C_BTN2_HOV,
                                           command=self._refresh_startup)
        self.s_refresh_btn.pack(side="left", padx=(0, 8))
        self.s_disable_btn = ctk.CTkButton(row, corner_radius=10, text="Disable selected", height=36,
                                           fg_color="#92400e", text_color=C_ONCOLOR, hover_color="#78350f",
                                           command=lambda: self._toggle_startup(False))
        self.s_disable_btn.pack(side="left", padx=(0, 8))
        self.s_enable_btn = ctk.CTkButton(row, corner_radius=10, text="Enable selected", height=36,
                                          fg_color="#0e9f6e", text_color=C_ONCOLOR, hover_color="#0b7f57",
                                          command=lambda: self._toggle_startup(True))
        self.s_enable_btn.pack(side="left")
        self.s_msg = ctk.CTkLabel(page, text="", text_color=C_MUT, font=(FONT, 12))
        self.s_msg.pack(anchor="w", pady=(8, 0))

        # Phase 3 platform-gate: the Startup tab is Windows-only — on
        # Linux/macOS the buttons used to be clickable and then returned
        # "requires Windows" after the click. Disable them up front with
        # an explanatory banner so the user isn't left guessing.
        if sys.platform != "win32":
            for b in (self.s_refresh_btn, self.s_disable_btn,
                      self.s_enable_btn):
                b.configure(state="disabled")
            ctk.CTkLabel(
                page,
                text=(
                    "Startup management is Windows-only — on this OS there is "
                    "nothing to list. (Linux/macOS apps manage their own "
                    "auto-start through systemd / launchd / XDG autostart.)"
                ),
                text_color=C_YLW, font=(FONT, 11, "italic"),
                wraplength=900, justify="left", anchor="w"
            ).pack(anchor="w", pady=(8, 0))

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
            # v2.8.0: a pending toggle result survives the refresh
            # (same message-clobber family as the hogs fix above).
            pending = getattr(self, "_startup_result_msg", "")
            self._startup_result_msg = ""
            self.s_msg.configure(
                text=msg + (f" | {pending}" if pending else ""))

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
            # v2.8.0: park the result for the refresh's done() instead
            # of setting it here — _refresh_startup() overwrites s_msg
            # with "Loading..." the moment it is called.
            self._startup_result_msg = text
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
