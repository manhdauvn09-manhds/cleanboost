"""Launch the CleanBoost GUI.

    .venv/bin/python gui.py
"""
from ui.app import main
from cleaner.single_instance import ensure_single_instance

if __name__ == "__main__":
    if ensure_single_instance():
        main()

