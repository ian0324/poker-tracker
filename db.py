"""SQLite storage for parsed hands."""
import os
import sqlite3
import glob

import parser as hh

from paths import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS hands (
  hand_id TEXT PRIMARY KEY,
  table_name TEXT, game TEXT, sb REAL, bb REAL,
  played_at TEXT, button_seat INTEGER, max_players INTEGER, n_players INTEGER,
  board TEXT, total_pot REAL, rake REAL, jackpot REAL, run_times INTEGER, cash_drop REAL,
  pot_type TEXT, pf_raises INTEGER, flop_players INTEGER,
  hero_seat INTEGER, hero_cards TEXT, hero_hand TEXT, hero_pos TEXT, hero_net REAL, hero_ev_net REAL, hero_equity REAL, allin_street TEXT,
  raw TEXT, source_file TEXT
);
CREATE INDEX IF NOT EXISTS idx_hands_time ON hands(played_at);
CREATE TABLE IF NOT EXISTS hand_players (
  hand_id TEXT, name TEXT, seat INTEGER, stack REAL, position TEXT, cards TEXT, hand169 TEXT,
  invested REAL, collected REAL, cashout_risk REAL, net REAL,
  vpip INTEGER, pfr INTEGER, saw_flop INTEGER, saw_showdown INTEGER, won_showdown INTEGER,
  won_hand INTEGER, won_sd_money INTEGER,
  three_bet_opp INTEGER, three_bet INTEGER, faced_three_bet INTEGER, fold_to_three_bet INTEGER,
  cbet_opp INTEGER, cbet INTEGER, faced_cbet INTEGER, fold_to_cbet INTEGER,
  pf_calls INTEGER, pf_raises INTEGER, agg_bets INTEGER, agg_raises INTEGER, agg_calls INTEGER,
  walk INTEGER, steal_opp INTEGER, steal INTEGER, fold_street TEXT,
  pot_type TEXT, pf_role TEXT, pf_first TEXT, pf_faced INTEGER, ip INTEGER, flop_players INTEGER,
  flop_strength TEXT, flop_line TEXT, turn_line TEXT, river_line TEXT, ev_net REAL,
  PRIMARY KEY (hand_id, name)
);
CREATE INDEX IF NOT EXISTS idx_hp_name ON hand_players(name);
CREATE INDEX IF NOT EXISTS idx_hp_scen ON hand_players(name, pot_type, pf_role);
CREATE TABLE IF NOT EXISTS actions (
  hand_id TEXT, street TEXT, ord INTEGER, name TEXT, action TEXT, amount REAL, total REAL, all_in INTEGER
);
CREATE INDEX IF NOT EXISTS idx_actions_hand ON actions(hand_id);
CREATE TABLE IF NOT EXISTS notes (
  hand_id TEXT PRIMARY KEY, star INTEGER DEFAULT 0, note TEXT DEFAULT '', updated_at TEXT
);
CREATE TABLE IF NOT EXISTS player_notes (
  name TEXT PRIMARY KEY, alias TEXT DEFAULT '', note TEXT DEFAULT '', updated_at TEXT
);
CREATE TABLE IF NOT EXISTS bigpot_spots (
  hand_id TEXT, street TEXT, kind TEXT, rec TEXT, actual TEXT, net_bb REAL, ev_bb REAL, cat TEXT
);
CREATE INDEX IF NOT EXISTS idx_bp_hand ON bigpot_spots(hand_id);
CREATE TABLE IF NOT EXISTS kv (
  key TEXT PRIMARY KEY, value TEXT
);
CREATE TABLE IF NOT EXISTS imported_files (
  path TEXT PRIMARY KEY, mtime REAL, hands INTEGER
);
"""

RANKS = "23456789TJQKA"


def hand169(cards):
    """'Ah Kd' -> 'AKo', 'Ah Kh' -> 'AKs', 'Ah Ad' -> 'AA'."""
    if not cards:
        return None
    cs = cards.split()
    if len(cs) != 2:
        return None
    r1, s1 = cs[0][0], cs[0][1]
    r2, s2 = cs[1][0], cs[1][1]
    if RANKS.index(r1) < RANKS.index(r2):
        r1, r2 = r2, r1
    if r1 == r2:
        return r1 + r2
    return r1 + r2 + ("s" if s1 == s2 else "o")


def connect(path=DB_PATH):
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


PLAYER_COLS = [
    "seat", "stack", "position", "cards", "invested", "collected", "cashout_risk", "net",
    "vpip", "pfr", "saw_flop", "saw_showdown", "won_showdown", "won_hand", "won_sd_money",
    "three_bet_opp", "three_bet", "faced_three_bet", "fold_to_three_bet",
    "cbet_opp", "cbet", "faced_cbet", "fold_to_cbet",
    "pf_calls", "pf_raises", "agg_bets", "agg_raises", "agg_calls",
    "walk", "steal_opp", "steal", "fold_street",
    "pot_type", "pf_role", "pf_first", "pf_faced", "ip", "flop_players", "flop_strength", "flop_line", "turn_line", "river_line", "ev_net",
]


def insert_hand(con, h, raw, source_file):
    hero = h["players"].get("Hero", {})
    con.execute(
        "INSERT OR IGNORE INTO hands VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            h["hand_id"], h["table"], h["game"], h["sb"], h["bb"], h["played_at"],
            h["button_seat"], h["max_players"], len(h["players"]), " ".join(h["board"]),
            h["total_pot"], h["rake"], h["jackpot"], h["run_times"], h["cash_drop"],
            h["pot_type"], h["pf_raises"], h["flop_players"],
            h["hero_seat"], h["hero_cards"], hand169(h["hero_cards"]), hero.get("position"), h["hero_net"], h["hero_ev_net"], h["hero_equity"], h["allin_street"],
            raw, source_file,
        ),
    )
    if con.total_changes == 0:
        return False
    rows = []
    for name, p in h["players"].items():
        rows.append([h["hand_id"], name] + [p[c] for c in PLAYER_COLS[:4]] + [hand169(p["cards"])] + [p[c] for c in PLAYER_COLS[4:]])
    con.executemany(
        "INSERT OR IGNORE INTO hand_players VALUES (" + ",".join("?" * (len(PLAYER_COLS) + 3)) + ")", rows
    )
    con.executemany(
        "INSERT INTO actions VALUES (?,?,?,?,?,?,?,?)",
        [(h["hand_id"],) + a for a in h["actions"]],
    )
    return True


def import_file(con, path):
    """Returns (new_hands, total_hands, errors)."""
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        text = f.read()
    new, total, errors = 0, 0, 0
    for chunk in hh.split_hands(text):
        total += 1
        try:
            h = hh.parse_hand(chunk)
        except Exception:
            h = None
        if not h:
            errors += 1
            continue
        before = con.total_changes
        cur = con.execute("SELECT 1 FROM hands WHERE hand_id=?", (h["hand_id"],)).fetchone()
        if cur:
            continue
        insert_hand(con, h, chunk.strip(), os.path.basename(path))
        new += 1
    con.execute(
        "INSERT OR REPLACE INTO imported_files VALUES (?,?,?)",
        (os.path.abspath(path), os.path.getmtime(path), total),
    )
    con.commit()
    return new, total, errors


def import_folder(con, folder, progress=None):
    files = sorted(glob.glob(os.path.join(folder, "**", "*.txt"), recursive=True))
    summary = {"files": 0, "skipped": 0, "new_hands": 0, "total_hands": 0, "errors": 0}
    for i, fp in enumerate(files):
        row = con.execute("SELECT mtime FROM imported_files WHERE path=?", (os.path.abspath(fp),)).fetchone()
        if row and abs(row["mtime"] - os.path.getmtime(fp)) < 1:
            summary["skipped"] += 1
            continue
        new, total, err = import_file(con, fp)
        summary["files"] += 1
        summary["new_hands"] += new
        summary["total_hands"] += total
        summary["errors"] += err
        if progress:
            progress(i + 1, len(files), fp)
    return summary


if __name__ == "__main__":
    import sys
    con = connect()
    print(import_folder(con, sys.argv[1] if len(sys.argv) > 1 else "../hands"))
