"""Network package (CleanBoost v2.4) — everything network-related.

All public functions follow the CleanBoost safety rules:
- system actions return (ok, message) and never raise;
- data functions return (ok, message, data) and never raise;
- read-only functions need no admin; anything needing admin reports it.
"""
from network import info, ports, speed, refresh

__all__ = ["info", "ports", "speed", "refresh"]
