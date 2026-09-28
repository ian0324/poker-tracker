"""
Desktop entry point: starts the local server on a free port and shows the UI
in a native window (pywebview / Edge WebView2). Falls back to the default
browser if pywebview is not available.

When frozen (PokerTracker.exe), Python modules found in <exe dir>/tracker/
take precedence over the bundled copies, so updating the .py files there
only needs an app restart, not a rebuild.
"""
import os
import sys

if getattr(sys, "frozen", False):
    _ext = os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "tracker")
    if os.path.isfile(os.path.join(_ext, "app.py")):
        sys.path.insert(0, _ext)

import threading
import webbrowser

import app


def run():
    server, url = app.make_server(0)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        app.auto_import(log=lambda *_: None)
    except Exception:
        pass
    try:
        import webview  # pywebview
    except Exception:
        webbrowser.open(url)
        try:
            t.join()
        except KeyboardInterrupt:
            pass
        return
    webview.create_window("Poker Tracker", url, width=1500, height=950, min_size=(1100, 700))
    webview.start()
    server.shutdown()


if __name__ == "__main__":
    run()
