"""Đọc thông tin RAM / CPU / ổ đĩa realtime qua psutil."""
import psutil

GB = 1024 ** 3


def memory() -> dict:
    vm = psutil.virtual_memory()
    return {
        "total": vm.total,
        "available": vm.available,
        "used": vm.used,
        "percent": vm.percent,
    }


def cpu_percent() -> float:
    return psutil.cpu_percent(interval=0.5)


def cpu_count() -> int:
    return psutil.cpu_count(logical=True) or 1


def disk(path: str) -> dict:
    du = psutil.disk_usage(path)
    return {
        "total": du.total,
        "used": du.used,
        "free": du.free,
        "percent": du.percent,
    }


def fmt_gb(n: float) -> str:
    return f"{n / GB:.1f} GB"
