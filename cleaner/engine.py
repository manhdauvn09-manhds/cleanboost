"""Nạp rules.yaml & lọc theo mức độ / OS."""
import glob
import os
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
RULES_PATH = os.path.join(HERE, "rules.yaml")


def platform_name() -> str:
    return "windows" if sys.platform == "win32" else "linux"


def load_rules(path: str = RULES_PATH) -> list:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("rules", []) if data else []


def expand_path(raw: str) -> str:
    # Windows: %TEMP% ; Linux/macOS: ~ và $HOME
    return os.path.expandvars(os.path.expanduser(raw))


def rules_for(level: int, plat: str = None) -> list:
    """Các rule thuộc mức <= level và đúng OS hiện tại."""
    plat = plat or platform_name()
    return [r for r in load_rules()
            if r.get("level", 1) <= level and plat in r.get("os", [])]


def resolve_paths(rule: dict) -> list:
    """Giải nén paths của rule (hỗ trợ glob như Firefox Profiles/*/cache2)."""
    out = []
    for raw in rule.get("paths", []):
        for p in glob.glob(expand_path(raw)):
            if os.path.exists(p):
                out.append(p)
    return out
