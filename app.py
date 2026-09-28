"""
Local web server for the poker tracker. Standard library only.
Run:  python app.py            (opens http://localhost:8000)
"""
import json
import os
import sys
import threading
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

import db
import stats

from paths import HANDS_DIR as DEFAULT_HANDS_DIR, INDEX_HTML, DB_PATH
PORT = int(os.environ.get("PORT", "8000"))

_lock = threading.Lock()


def filters_from(qs):
    f = {}
    for k in ("date_from", "date_to", "position", "hand169", "pot_type", "pf_role", "pf_first", "ip", "players", "saw_flop", "flop_strength", "flop_line", "turn_line", "river_line", "preset", "first_in", "vs3b_pos", "vs_open_pos", "vs4b_pos", "pf_resp", "opp_id", "opp_mode", "hid"):
        v = qs.get(k, [""])[0].strip()
        if v:
            f[k] = v
    return f


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # quieter console
        if "/api/" not in (args[0] if args else ""):
            return

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, name, ctype):
        path = INDEX_HTML if name == "index.html" else os.path.join(os.path.dirname(INDEX_HTML), name)
        with open(path, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        qs = parse_qs(u.query)
        path = u.path
        try:
            if path in ("/", "/index.html"):
                return self._file("index.html", "text/html; charset=utf-8")
            if not path.startswith("/api/"):
                return self._json({"error": "not found"}, 404)
            with _lock:
                con = db.connect()
                try:
                    return self._api(path, qs, con)
                finally:
                    con.close()
        except Exception as e:  # surface errors to the UI
            import traceback
            traceback.print_exc()
            return self._json({"error": str(e)}, 500)

    def _api(self, path, qs, con):
        player = qs.get("player", ["Hero"])[0]
        f = filters_from(qs)
        if path == "/api/meta":
            return self._json({**stats.meta(con), "hands_dir": DEFAULT_HANDS_DIR})
        if path == "/api/overall":
            return self._json(stats.overall(con, player, f))
        if path == "/api/positions":
            return self._json(stats.by_position(con, player, f))
        if path == "/api/hands169":
            return self._json(stats.by_hand169(con, player, f))
        if path == "/api/days":
            return self._json(stats.by_day(con, player, f))
        if path == "/api/graph":
            return self._json(stats.graph(con, player, f))
        if path == "/api/hands":
            sort = qs.get("sort", ["played_at"])[0]
            desc = qs.get("desc", ["1"])[0] == "1"
            limit = int(qs.get("limit", ["100"])[0])
            offset = int(qs.get("offset", ["0"])[0])
            return self._json(stats.hand_list(con, player, f, sort, desc, limit, offset))
        if path == "/api/hand":
            hid = qs.get("id", [""])[0]
            d = stats.hand_detail(con, hid)
            return self._json(d or {"error": "no such hand"}, 200 if d else 404)
        if path == "/api/sessions":
            return self._json(stats.sessions(con, player, f, int(qs.get("gap", ["30"])[0])))
        if path == "/api/strength":
            return self._json(stats.hand_strength_report(con, player, f))
        if path == "/api/marked":
            return self._json(stats.marked_hands(con, player))
        if path == "/api/presets":
            return self._json(stats.presets_summary(con, player, f))
        if path == "/api/position_graph":
            return self._json(stats.position_graph(con, player, f))
        if path == "/api/range":
            return self._json(stats.range_chart(con, player, f, qs.get("pos", [""])[0], qs.get("action", ["open"])[0]))
        if path == "/api/kv":
            return self._json({r["key"]: r["value"] for r in con.execute("SELECT key, value FROM kv")})
        if path == "/api/preflop":
            return self._json(stats.preflop_compare(con, player, f, qs.get("mode", ["open"])[0], qs.get("pos", ["BTN"])[0], qs.get("vpos", ["BB"])[0]))
        if path == "/api/preflop_charts":
            return self._json(stats.preflop_charts())
        if path == "/api/opponents":
            mh = int(qs.get("min_hands", ["30"])[0])
            return self._json(stats.opponents(con, mh, f, qs.get("q", [""])[0]))
        return self._json({"error": "unknown api"}, 404)

    def do_POST(self):
        u = urlparse(self.path)
        n = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            body = {}
        if u.path == "/api/kv":
            with _lock:
                con = db.connect()
                try:
                    con.execute("INSERT OR REPLACE INTO kv VALUES (?,?)", (str(body.get("key", "")), json.dumps(body.get("value"), ensure_ascii=False)))
                    con.commit()
                finally:
                    con.close()
            return self._json({"ok": True})
        if u.path == "/api/player":
            with _lock:
                con = db.connect()
                try:
                    return self._json(stats.set_player(con, body.get("name", ""), body.get("alias"), body.get("note")))
                finally:
                    con.close()
        if u.path == "/api/note":
            with _lock:
                con = db.connect()
                try:
                    return self._json(stats.set_note(con, body.get("hand_id", ""), body.get("star"), body.get("note")))
                finally:
                    con.close()
        if u.path == "/api/import":
            folder = (body.get("folder") or DEFAULT_HANDS_DIR).strip().strip('"')
            if not os.path.isdir(folder):
                return self._json({"error": f"資料夾不存在: {folder}"}, 400)
            with _lock:
                con = db.connect()
                try:
                    summary = db.import_folder(con, folder)
                    stats.refresh_bigpot(con)
                finally:
                    con.close()
            return self._json({"folder": folder, **summary})
        return self._json({"error": "unknown api"}, 404)


def auto_import(log=print):
    """Scan the hands folder at startup and import anything new."""
    if not os.path.isdir(DEFAULT_HANDS_DIR):
        log(f"hands folder not found: {DEFAULT_HANDS_DIR}")
        return None
    with _lock:
        con = db.connect()
        try:
            summary = db.import_folder(con, DEFAULT_HANDS_DIR)
            # 大底池決策點表：有新手牌或表是空的就重算
            if summary["new_hands"] or not con.execute("SELECT 1 FROM bigpot_spots LIMIT 1").fetchone():
                stats.refresh_bigpot(con)
        finally:
            con.close()
    log(f"auto-import: {summary['new_hands']} new hands from {summary['files']} files ({summary['skipped']} unchanged)")
    return summary


def make_server(port=None):
    """Create the HTTP server; port=None or 0 picks a free port. Returns (server, url)."""
    db.connect().close()  # ensure schema
    server = HTTPServer(("127.0.0.1", port or 0), Handler)
    url = f"http://127.0.0.1:{server.server_address[1]}"
    return server, url


def main():
    server, url = make_server(PORT)
    print(f"Poker tracker running at {url}   (Ctrl+C to stop)")
    print(f"Hands folder: {DEFAULT_HANDS_DIR}")
    print(f"Database:     {DB_PATH}")
    auto_import()
    if "--no-browser" not in sys.argv:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
