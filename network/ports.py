"""Port & SSH Inspector (CleanBoost v2.4, A.9).

Read-only: lists every LISTEN port with the process holding it,
checks port 22 (SSH) separately, flags sensitive ports.
Never raises — returns (ok, message, data).
"""
import psutil

from safety import protected

_PORT_GUIDES = {
    21: ("FTP (21) — plain-text file transfer. If you do not run an FTP "
         "server, stop it: Services (services.msc) -> find the FTP service "
         "-> Stop, then set Startup type to Disabled."),
    23: ("Telnet (23) — unencrypted remote login, unsafe on any network. "
         "Turn it off: Windows Features -> uncheck 'Telnet Client/Server', "
         "or stop the Telnet service in services.msc."),
    445: ("SMB (445) — Windows file sharing. If you do not share files with "
          "other PCs, disable it: Windows Features -> uncheck "
          "'SMB 1.0/CIFS File Sharing Support', and turn off File Sharing "
          "in Network settings."),
    3306: ("MySQL (3306) — database port. If only local apps use it, bind "
           "MySQL to 127.0.0.1 in my.ini (bind-address=127.0.0.1) and "
           "restart the MySQL service."),
    3389: ("Remote Desktop (3389) — remote control of this PC. If you do "
           "not use it: Settings -> System -> Remote Desktop -> Off. "
           "If you need it, use a strong password + Network Level "
           "Authentication."),
    5432: ("PostgreSQL (5432) — database port. If only local apps use it, "
           "set listen_addresses='localhost' in postgresql.conf and "
           "restart the PostgreSQL service."),
    5900: ("VNC (5900) — remote screen sharing. If you do not use it, close "
           "the VNC server app (or set its service to Disabled in "
           "services.msc). If you need it, require a strong password."),
}


def _scope(bind_ip):
    if (bind_ip or "") in ("127.0.0.1", "::1"):
        return "Local only"
    return "LAN"


def _process_name(pid, cache):
    if pid is None:
        return "unknown"
    if pid in cache:
        return cache[pid]
    try:
        name = psutil.Process(pid).name() or "unknown"
    except Exception:
        name = "unknown"
    cache[pid] = name
    return name


def list_listening_ports():
    """All LISTEN ports, one row per (port, bind_ip, pid).

    Row: {port, bind_ip, scope, pid, process, level, service}.
    level: 'critical' | 'warning' | 'normal' (see protected.port_severity).
    """
    try:
        conns = psutil.net_connections(kind="inet")
    except Exception as e:  # noqa: BLE001
        return False, f"Could not list connections: {e}", []
    cache = {}
    seen = set()
    rows = []
    for c in conns:
        try:
            if getattr(c, "status", "") != "LISTEN":
                continue
            laddr = getattr(c, "laddr", None)
            if not laddr:
                continue
            port = laddr.port
            bind_ip = laddr.ip or ""
            pid = getattr(c, "pid", None)
            key = (port, bind_ip, pid)
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "port": port,
                "bind_ip": bind_ip,
                "scope": _scope(bind_ip),
                "pid": pid,
                "process": _process_name(pid, cache),
                "level": protected.port_severity(port, bind_ip),
                "service": protected.SENSITIVE_PORTS.get(port, ""),
            })
        except Exception:
            continue
    rows.sort(key=lambda r: (r["port"], r["bind_ip"]))
    return True, f"Found {len(rows)} listening port(s).", rows


def check_ssh():
    """SSH (port 22) status.

    Returns (ok, message, data) with data = {"open": bool, "rows": [...]}.
    """
    ok, msg, rows = list_listening_ports()
    if not ok:
        return ok, msg, {"open": False, "rows": []}
    ssh_rows = [r for r in rows if r["port"] == 22]
    if ssh_rows:
        procs = ", ".join(sorted({r["process"] for r in ssh_rows}))
        lan = any(r["scope"] == "LAN" for r in ssh_rows)
        detail = (f"Port 22: OPEN ({procs}) — "
                  + ("other PCs on the LAN can SSH into this PC."
                     if lan else "bound to localhost only."))
        return True, detail, {"open": True, "rows": ssh_rows}
    return True, "Port 22: closed — safe.", {"open": False, "rows": []}


def get_port_guide(port):
    """English 'How to close' text for one port."""
    try:
        p = int(port)
    except (TypeError, ValueError):
        return "Select a port to see how to close it."
    if p in _PORT_GUIDES:
        return _PORT_GUIDES[p]
    return (f"Port {p} is held by the process shown in the table. To close "
            f"it, stop or uninstall the app/service using it "
            f"(Task Manager -> Services, or services.msc), then refresh "
            "this list to confirm it is gone.")
