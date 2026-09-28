"""Resolve folders for both `python app.py` and the packaged PokerTracker.exe.

Layout expected:
  poker/
    PokerTracker.exe   (or tracker/app.py when running from source)
    hands/             hand history .txt files
    tracker/tracker.db database
"""
import os
import sys

if getattr(sys, "frozen", False):
    # PyInstaller one-file: the exe lives in poker/, bundled data in sys._MEIPASS
    BASE = os.path.dirname(os.path.abspath(sys.executable))
    RESOURCES = getattr(sys, "_MEIPASS", BASE)
else:
    RESOURCES = os.path.dirname(os.path.abspath(__file__))   # tracker/
    BASE = os.path.dirname(RESOURCES)                         # poker/

HANDS_DIR = os.environ.get("POKER_HANDS", os.path.join(BASE, "hands"))
DATA_DIR = os.path.join(BASE, "tracker")
if not os.path.isdir(DATA_DIR):
    DATA_DIR = BASE
DB_PATH = os.environ.get("POKER_DB", os.path.join(DATA_DIR, "tracker.db"))
# Prefer an index.html living next to the database (poker/tracker/index.html) so UI
# updates don't require rebuilding the exe; fall back to the bundled copy.
_external = os.path.join(DATA_DIR, "index.html")
INDEX_HTML = _external if os.path.isfile(_external) else os.path.join(RESOURCES, "index.html")
