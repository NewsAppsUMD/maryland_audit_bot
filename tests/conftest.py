"""Test configuration: make repo root and prototype/ importable.

prototype/ is not a package, so we add both the repo root (for scraper.py
and pdf_parser.py) and prototype/ (for utils.py) to sys.path.
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

for path in (str(REPO_ROOT), str(REPO_ROOT / "prototype")):
    if path not in sys.path:
        sys.path.insert(0, path)
