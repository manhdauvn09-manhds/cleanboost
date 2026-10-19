"""Startup Manager (CleanBoost v2.5, B.3).

Lists apps that start with Windows from:
- HKCU\\...\\Run and HKLM\\...\\Run (registry)
- the per-user and all-users Startup folders

Disabling NEVER deletes: a registry value is renamed with the
`CleanBoost_disabled_` prefix, a Startup-folder file is renamed the
same way — one click re-enables it. Protected entries (Windows
Security, audio/network drivers) cannot be disabled at all.

HKLM changes need Admin. Never raises — returns (ok, message[, data]).
"""
import os
import sys

from cleaner import action_log
from core import privilege

DISABLED_PREFIX = "CleanBoost_disabled_"

# Entries that must never be disabled: security + hardware drivers.
# Matched case-insensitively against name + value.
PROTECTED_STARTUP_SUBSTRINGS = (
    "securityhealth", "windows defender", "msmpeng",
    "realtek", "synaptics", "ctfmon", "igfx", "radeon",
    "wavessvc", "rthdcpl", "hd audio", "audio",
    "intel", "nvidia", "amd",
)

_RUN_SUBKEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _is_protected(name, value):
    hay = f"{name or ''} {value or ''}".lower()
    return any(s in hay for s in PROTECTED_STARTUP_SUBSTRINGS)


def _display_name(raw):
    if raw.startswith(DISABLED_PREFIX):
        return raw[len(DISABLED_PREFIX):]
    return raw


def _startup_folders():
    folders = []
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "")
        progdata = os.environ.get("PROGRAMDATA", "")
        if appdata:
            folders.append((os.path.join(
                appdata, r"Microsoft\Windows\Start Menu\Programs\Startup"),
                "Startup folder (user)"))
        if progdata:
            folders.append((os.path.join(
                progdata, r"Microsoft\Windows\Start Menu\Programs\StartUp"),
                "Startup folder (all users)"))
    return folders


def _read_registry_items():
    import winreg
    items = []
    for hive, hive_name, location in (
            (winreg.HKEY_CURRENT_USER, "HKCU", "HKCU Run"),
            (winreg.HKEY_LOCAL_MACHINE, "HKLM", "HKLM Run")):
        try:
            with winreg.OpenKey(hive, _RUN_SUBKEY) as key:
                _n_vals, n_values, _last = winreg.QueryInfoKey(key)
                for i in range(n_values):
                    try:
                        name, value, _typ = winreg.EnumValue(key, i)
                    except OSError:
                        continue
                    enabled = not name.startswith(DISABLED_PREFIX)
                    items.append({
                        "key": name,
                        "name": _display_name(name),
                        "location": location,
                        "value": value if isinstance(value, str) else str(value),
                        "enabled": enabled,
                        "protected": _is_protected(_display_name(name), value),
                    })
        except OSError:
            continue
    return items


def _read_folder_items():
    items = []
    for folder, location in _startup_folders():
        try:
            names = os.listdir(folder)
        except OSError:
            continue
        for fn in names:
            full = os.path.join(folder, fn)
            if not os.path.isfile(full):
                continue
            enabled = not fn.startswith(DISABLED_PREFIX)
            items.append({
                "key": fn,
                "name": _display_name(fn),
                "location": location,
                "value": full,
                "enabled": enabled,
                "protected": _is_protected(_display_name(fn), full),
            })
    return items


def list_startup():
    """All startup entries. Returns (ok, message, items)."""
    try:
        if sys.platform != "win32":
            return False, "Startup Manager is only supported on Windows.", []
        items = _read_registry_items() + _read_folder_items()
        items.sort(key=lambda i: (i["location"], i["name"].lower()))
        return True, f"Found {len(items)} startup entr(ies).", items
    except Exception as e:  # noqa: BLE001
        return False, f"Could not list startup apps: {e}", []


def _toggle_registry(location, key, enable):
    import winreg
    hive = winreg.HKEY_CURRENT_USER if location == "HKCU Run" else winreg.HKEY_LOCAL_MACHINE
    if hive == winreg.HKEY_LOCAL_MACHINE and not privilege.is_admin():
        return False, ("Admin rights required to change machine-wide "
                       "startup entries. Run CleanBoost as Administrator.")
    new_key = key if enable else DISABLED_PREFIX + key
    if enable and key.startswith(DISABLED_PREFIX):
        new_key = key[len(DISABLED_PREFIX):]
    elif not enable and key.startswith(DISABLED_PREFIX):
        return False, "This entry is already disabled."
    elif enable and not key.startswith(DISABLED_PREFIX):
        return False, "This entry is already enabled."
    try:
        with winreg.OpenKey(hive, _RUN_SUBKEY, 0,
                            winreg.KEY_READ | winreg.KEY_SET_VALUE) as h:
            try:
                value, typ = winreg.QueryValueEx(h, key)
            except OSError:
                return False, "Startup entry not found (list may be stale)."
            try:
                winreg.QueryValueEx(h, new_key)
                return False, (f"An entry named '{new_key}' already exists.")
            except OSError:
                pass
            winreg.SetValueEx(h, new_key, 0, typ, value)
            try:
                winreg.DeleteValue(h, key)
            except OSError:
                # v2.5.6: rollback — without this, both the enabled AND
                # the disabled name exist and the entry shows up twice.
                try:
                    winreg.DeleteValue(h, new_key)
                except OSError:
                    pass
                return False, ("Could not rename startup entry "
                               "(old value could not be removed).")
    except OSError as e:
        return False, f"Could not change startup entry: {e}"
    return True, ("Startup entry enabled." if enable
                  else "Startup entry disabled (renamed, restorable).")


def _toggle_folder(location, key, enable):
    for folder, loc in _startup_folders():
        if loc != location:
            continue
        src = os.path.join(folder, key)
        if not os.path.isfile(src):
            return False, "Startup file not found (list may be stale)."
        if enable and key.startswith(DISABLED_PREFIX):
            dst_name = key[len(DISABLED_PREFIX):]
        elif not enable and not key.startswith(DISABLED_PREFIX):
            dst_name = DISABLED_PREFIX + key
        else:
            return False, ("This entry is already enabled."
                            if enable else "This entry is already disabled.")
        dst = os.path.join(folder, dst_name)
        if os.path.exists(dst):
            return False, f"A file named '{dst_name}' already exists."
        try:
            os.rename(src, dst)
        except OSError as e:
            return False, f"Could not rename startup file: {e}"
        return True, ("Startup entry enabled." if enable
                      else "Startup entry disabled (renamed, restorable).")
    return False, "Startup folder not found."


def set_enabled(key, location, enabled):
    """Enable/disable one entry (rename, never delete).

    Returns (ok, message). Protected entries are refused.
    """
    try:
        if sys.platform != "win32":
            return False, "Startup Manager is only supported on Windows."
        ok, _msg, items = list_startup()
        if ok:
            item = next((i for i in items
                         if i["key"] == key and i["location"] == location), None)
            # v2.5.6: protection only blocks DISABLING. A protected entry
            # that was disabled before the protection list existed must
            # still be re-enableable — the old code blocked both ways.
            if item and item["protected"] and not enabled:
                return False, (f"'{item['name']}' is protected (security / "
                               "driver) and cannot be disabled.")
        if location in ("HKCU Run", "HKLM Run"):
            ok, msg = _toggle_registry(location, key, enabled)
        elif location.startswith("Startup folder"):
            ok, msg = _toggle_folder(location, key, enabled)
        else:
            return False, f"Unknown startup location: {location}"
        action_log.log("startup_toggle",
                       {"key": key, "location": location,
                        "enabled": enabled, "ok": ok})
        return ok, msg
    except Exception as e:  # noqa: BLE001
        return False, f"Could not change startup entry: {e}"
