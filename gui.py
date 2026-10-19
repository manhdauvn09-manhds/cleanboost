"""Launch the CleanBoost GUI.

    .venv/bin/python gui.py
"""
import os
import sys
import traceback

from ui.app import main
from cleaner.single_instance import ensure_single_instance


def _crash_log_path():
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        d = os.path.join(base, "CleanBoost")
    else:
        d = os.path.join(os.path.expanduser("~"), ".config", "cleanboost")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "startup_error.log")


if __name__ == "__main__":
    if ensure_single_instance():
        try:
            main()
        except Exception:
            # v2.5.4: the normal launcher uses pythonw.exe (no console),
            # so a startup crash used to be invisible — the app just
            # never appeared. Now the traceback is saved AND shown.
            text = traceback.format_exc()
            try:
                with open(_crash_log_path(), "w", encoding="utf-8") as f:
                    f.write(text)
            except OSError:
                pass
            try:
                import tkinter as tk
                from tkinter import messagebox
                root = tk.Tk()
                root.withdraw()
                messagebox.showerror(
                    "CleanBoost failed to start",
                    "CleanBoost crashed during startup.\n\n"
                    f"Details saved to:\n{_crash_log_path()}\n\n"
                    f"{text[-800:]}",
                    parent=root)
                root.destroy()
            except Exception:  # noqa: BLE001
                pass
            raise
