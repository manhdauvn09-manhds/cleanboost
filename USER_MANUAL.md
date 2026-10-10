# CleanBoost PRO — User Manual

Version 2.3 PRO — English edition.

---

## 1. What is CleanBoost?

CleanBoost is a Windows/Linux utility that:

- **Frees RAM** — see which apps eat your RAM, close them safely, or flush the RAM cache without closing anything.
- **Cleans junk files** — temp files, caches, Windows Update leftovers, Windows.old, leftover data of uninstalled apps, and more.
- **Quarantines** — removed files go to quarantine for 14 days first, so you can restore them with one click.
- **Automates** — schedule automatic cleanups and get alerts when RAM or disk runs low.

**Target OS:** Windows 10/11 first, Linux also supported.

---

## 2. Installation (Windows)

1. Install **Python 3.11+** from https://www.python.org/downloads/
   (tick **"Add python.exe to PATH"** during install).
2. Install **Git for Windows** from https://git-scm.com/download/win
   (needed for one-click updates).
3. **First time only:** double-click `setup_windows.bat` — it creates the
   virtual environment and installs libraries.
4. Launch the app: double-click `run_cleanboost.bat`.
   For full cleaning power, right-click `run_cleanboost_admin.bat`
   → **Run as administrator** (shows the standard Windows UAC prompt —
   CleanBoost never bypasses UAC).

**Updates:** after the first setup you never need `setup_windows.bat`
again. Just double-click `git_pull.bat` to pull the latest source, then
launch `run_cleanboost.bat` — new libraries install themselves
automatically (see `check_env.py`).

**Command line:** `run_cli.bat <command>` (e.g. `run_cli.bat status`).

---

## 3. Overview tab

- Three ring gauges show **RAM**, **CPU** and **Disk** usage in realtime.
- A red **WARNING** banner appears when RAM ≥ 90% or free disk ≤ 10%.

**Quick actions:**

| Button | What it does |
|---|---|
| **Free RAM now** | Finds your heaviest RAM-hungry apps, lets you tick the ones to close, then flushes the RAM cache. System processes are never touched. |
| **Light clean** | Flushes the RAM standby cache **without closing any app**. Completely safe. |

---

## 4. Processes tab

- Lists your processes sorted by RAM or CPU (click the column headers to sort).
- **Search** box filters by name in realtime.
- **End selected** — asks first for sensitive processes (marked `(!)`).
  Protected system processes (System, csrss.exe, lsass.exe, …) are hidden
  and can never be killed — killing them would crash Windows.
- **Force kill** — terminates immediately (use when an app is frozen).

---

## 5. Disk Cleaner tab

Three levels, each deeper than the last:

| Level | Name | Content | Needs Admin |
|---|---|---|---|
| 1 | **Standard** | Temp files, Recycle Bin, browser/app caches | No |
| 2 | **Advanced** | Windows Update, WinSxS, Windows.old, leftover app data | Recommended |
| 3 | **Deep** | Whole-drive junk patterns, risky items (each needs its own confirmation) | Yes + confirmation |

**Workflow:**

1. Pick a level → press **Scan**.
2. Results show as cards: group name, reclaimable size, and an **impact**
   note explaining what deleting does. Risky groups are tagged
   `[HIGH RISK]` / `[caution]`.
3. Tick the groups you want. Press **Details** to preview the actual files
   (largest 300 shown) before deleting.
4. Choose how to clean:
   - **Delete to free space** (recommended) — permanently deletes and shows
     the **real** freed disk space, measured directly from the drive.
   - **Quarantine (safe)** — moves files to quarantine (restorable for
     14 days). **Note:** quarantined files still occupy disk space until
     you delete them permanently from the Quarantine tab.
5. A confirmation dialog lists every group with its impact and red warnings
   for high-risk items. For levels 2/3 on Windows, a **System Restore
   Point** is created first.

**Honesty about freed space:** after cleaning, the result dialog shows
`REAL disk space freed` — measured from the drive before/after, not an
estimate. This is the number you will see in Explorer.

---

## 6. Quarantine tab

- Everything cleaned via *Quarantine* stays here for **14 days**.
- **Restore selected** — puts files back exactly where they were
  (renames if a new file appeared there).
- **Delete permanently** — this is what **really frees disk space**.
- **Clean items over 14 days** — permanently deletes expired items.
- Tip: `Ctrl+A` selects all rows; hold `Ctrl`/`Shift` for multiple rows.
  The **Select all** button does the same.

**Important:** quarantine lives on the same drive, so moving files there
does NOT free space. Only *Delete permanently* frees space.

---

## 7. Automation & CLI

**Scheduled cleanup** (every Sunday 03:00, Windows Task Scheduler / cron):

```
run_cli.bat schedule install
run_cli.bat schedule status
run_cli.bat schedule remove
```

**Monitor** — popup alerts when RAM ≥ 90% or disk free ≤ 10%:

```
run_cli.bat monitor
```

**Full CLI reference:**

```
status                    Show realtime RAM / CPU / disk
top -n 15                 List the hungriest processes
kill <pid> [--force]      Kill / force kill by PID
freeram [--mode light|standard]   Free RAM
scan --level 1|2|3        Dry-run junk scan (deletes nothing)
clean --level N [--all] [--permanent | --quarantine] [--yes]
quarantine list|restore|delete|purge
schedule install|status|remove
monitor [--interval 60]
```

Every kill/clean/restore action is written to an **audit log**
(`action_log.txt` in the app data folder).

---

## 8. Safety

- **Never bypasses UAC** — uses the standard Windows admin prompt.
- **Protected processes** can never be killed (System, csrss.exe,
  lsass.exe, …).
- **Protected paths** can never be cleaned (System32, WinSxS, Program
  Files, your Documents/Desktop/Downloads, …), even if a rule matches them.
- **High-risk rules** are off by default and need a separate confirmation.
- Symlink tricks cannot escape the protected-path check.
- Quarantine restore is guarded against path-traversal attacks.
- Only one CleanBoost GUI can run at a time (verified by process start
  time, immune to PID reuse).

---

## 9. FAQ

**I cleaned several GB but Explorer shows no free space.**
You probably used *Quarantine* — files are still on disk. Go to the
Quarantine tab → select → **Delete permanently**. Or clean with
*Delete to free space* from the start.

**The app says "Access denied".**
Run as administrator (`run_cleanboost_admin.bat` → Run as administrator).

**Two CleanBoost windows opened.**
The app detects the old instance and asks whether to close it.
If the old one runs as Admin and the new one as User, close it manually
or re-run the new one as Admin.

**After `git pull`, do I need to run setup again?**
No. Just launch `run_cleanboost.bat` — missing libraries install
automatically.

**Can I undo a cleanup?**
If you used *Quarantine*: yes, within 14 days (Restore selected).
If you used *Delete permanently*: no. For levels 2/3, a System Restore
Point is created first as a safety net.

---

## 10. Uninstall

1. Remove the scheduled task: `run_cli.bat schedule remove`.
2. Delete the CleanBoost folder.
3. (Optional) delete app data:
   - Windows: `%LOCALAPPDATA%\CleanBoost`, `%PROGRAMDATA%\CleanBoost`
   - Linux: `~/.config/cleanboost`, `~/.local/share/cleanboost`

---

*© copy by Dau Sy Manh — CleanBoost v2.3 PRO*
