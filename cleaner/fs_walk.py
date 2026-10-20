"""Safe directory walking (v2.6.1).

Every os.walk in CleanBoost goes through safe_walk(): it never descends
into directory junctions / symlinks and it caps the depth below the base.

Why: on Windows, os.walk DOES descend into junctions (e.g.
``AppData\\Local\\Application Data`` -> ``AppData\\Local``) even with the
default followlinks=False, because a junction is not reported as a
symlink. A junction pointing at an ancestor re-walks the whole subtree
at every level until paths hit the Windows length limit - a scan of one
cache folder could re-walk the same tree a dozen times and run for hours
instead of seconds, leaving the UI locked with no feedback.
"""
import os
import sys

MAX_WALK_DEPTH = 60
_REPARSE_POINT = 0x400  # FILE_ATTRIBUTE_REPARSE_POINT (Windows)


def is_junction(path):
    """True for symlinked dirs and Windows junction/reparse dirs."""
    try:
        st = os.lstat(path)
    except OSError:
        return True  # cannot stat -> do not descend (safe default)
    if os.path.islink(path):
        return True
    if sys.platform == "win32":
        attrs = getattr(st, "st_file_attributes", 0)
        return bool(attrs & _REPARSE_POINT)
    return False


def prune_junction_dirs(root, dirs):
    """In-place: drop sub-directories that are junctions/symlinks."""
    dirs[:] = [d for d in dirs
               if not is_junction(os.path.join(root, d))]


def safe_walk(top, max_depth=MAX_WALK_DEPTH):
    """Like os.walk (topdown), but prunes junctions and caps depth."""
    top = os.fspath(top)
    base_depth = top.rstrip(os.sep).count(os.sep)
    for root, dirs, files in os.walk(top, onerror=lambda e: None):
        if root.count(os.sep) - base_depth >= max_depth:
            dirs[:] = []
        else:
            prune_junction_dirs(root, dirs)
        yield root, dirs, files
