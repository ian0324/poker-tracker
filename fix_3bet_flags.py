"""
一次性修補：舊版 parser 在玩家自己 3-bet / 4-bet 時漏算「3-bet 機會」與「面對 3-bet」旗標。
用法：python fix_3bet_flags.py [tracker.db 路徑]   （不給路徑就用 paths.DB_PATH）
會修改 hand_players.three_bet_opp / faced_three_bet（所有玩家），其他欄位不動。
"""
import sqlite3
import sys


def fix(db_path, uri=False):
    con = sqlite3.connect(db_path, uri=uri)
    con.row_factory = sqlite3.Row
    rows = con.execute("SELECT hand_id, ord, name, action FROM actions WHERE street='preflop' ORDER BY hand_id, ord").fetchall()
    upd_opp, upd_f3 = [], []
    cur_hand, n_raises, first_raiser = None, 0, None
    for r in rows:
        if r["hand_id"] != cur_hand:
            cur_hand, n_raises, first_raiser = r["hand_id"], 0, None
        name, act = r["name"], r["action"]
        if n_raises == 1 and name != first_raiser:
            upd_opp.append((cur_hand, name))
        if n_raises == 2 and name == first_raiser:
            upd_f3.append((cur_hand, name))
        if act == "raises":
            n_raises += 1
            if first_raiser is None:
                first_raiser = name
    before = dict(con.execute("SELECT SUM(three_bet_opp) o, SUM(faced_three_bet) f FROM hand_players").fetchone())
    con.executemany("UPDATE hand_players SET three_bet_opp=1 WHERE hand_id=? AND name=?", upd_opp)
    con.executemany("UPDATE hand_players SET faced_three_bet=1 WHERE hand_id=? AND name=?", upd_f3)
    con.commit()
    after = dict(con.execute("SELECT SUM(three_bet_opp) o, SUM(faced_three_bet) f FROM hand_players").fetchone())
    hero = dict(con.execute("SELECT SUM(three_bet) tb, SUM(three_bet_opp) opp, SUM(faced_three_bet) f3, SUM(fold_to_three_bet) ff FROM hand_players WHERE name='Hero'").fetchone())
    print("three_bet_opp:", before["o"], "->", after["o"], "| faced_three_bet:", before["f"], "->", after["f"])
    print("Hero 3-bet %.1f%% (%d/%d)  Fold to 3-bet %.1f%% (%d/%d)" % (
        100.0 * hero["tb"] / hero["opp"], hero["tb"], hero["opp"], 100.0 * hero["ff"] / hero["f3"], hero["ff"], hero["f3"]))
    con.close()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        fix(sys.argv[1], uri=sys.argv[1].startswith("file:"))
    else:
        import paths
        fix(paths.DB_PATH)
