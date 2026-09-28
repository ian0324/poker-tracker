"""Statistics queries (PT4-style) over the SQLite DB."""
import sqlite3

STAT_SQL = """
SELECT
  COUNT(*)                                   AS hands,
  ROUND(SUM(hp.net), 2)                      AS net,
  ROUND(SUM(hp.ev_net), 2)                   AS ev_net,
  ROUND(SUM(hp.net / h.bb) / COUNT(*) * 100, 2) AS bb100,
  ROUND(SUM(hp.net / h.bb), 1)               AS bb_won,
  SUM(hp.vpip)                               AS vpip_n,
  SUM(hp.pfr)                                AS pfr_n,
  SUM(hp.three_bet)                          AS threebet_n,
  SUM(hp.three_bet_opp)                      AS threebet_opp,
  SUM(hp.fold_to_three_bet)                  AS f3b_n,
  SUM(hp.faced_three_bet)                    AS f3b_opp,
  SUM(hp.cbet)                               AS cbet_n,
  SUM(hp.cbet_opp)                           AS cbet_opp,
  SUM(hp.fold_to_cbet)                       AS fcb_n,
  SUM(hp.faced_cbet)                         AS fcb_opp,
  SUM(hp.saw_flop)                           AS saw_flop,
  SUM(hp.saw_showdown)                       AS wtsd_n,
  SUM(hp.won_showdown)                       AS wsd_n,
  SUM(hp.won_sd_money)                       AS wwsf_n,
  SUM(hp.agg_bets + hp.agg_raises)           AS agg_n,
  SUM(hp.agg_calls)                          AS call_n,
  SUM(hp.steal)                              AS steal_n,
  SUM(hp.steal_opp)                          AS steal_opp,
  SUM(hp.walk)                               AS walks,
  SUM(CASE WHEN hp.net > 0 THEN 1 ELSE 0 END) AS won_hands,
  ROUND(SUM(CASE WHEN hp.net > 0 THEN hp.net ELSE 0 END), 2) AS gross_won,
  ROUND(SUM(CASE WHEN hp.net < 0 THEN hp.net ELSE 0 END), 2) AS gross_lost,
  ROUND(MAX(hp.net), 2)                      AS biggest_win,
  ROUND(MIN(hp.net), 2)                      AS biggest_loss,
  SUM(CASE WHEN hp.saw_showdown=1 THEN hp.net ELSE 0 END) AS sd_net,
  SUM(CASE WHEN hp.saw_showdown=0 THEN hp.net ELSE 0 END) AS nsd_net
FROM hand_players hp JOIN hands h ON h.hand_id = hp.hand_id
WHERE hp.name = ? {where}
"""


def pct(n, d):
    return round(100.0 * n / d, 1) if d else None


def finish(row):
    if not row or not row["hands"]:
        return {"hands": 0}
    r = dict(row)
    r["vpip"] = pct(r["vpip_n"], r["hands"])
    r["pfr"] = pct(r["pfr_n"], r["hands"])
    r["threebet"] = pct(r["threebet_n"], r["threebet_opp"])
    r["fold_to_3bet"] = pct(r["f3b_n"], r["f3b_opp"])
    r["cbet"] = pct(r["cbet_n"], r["cbet_opp"])
    r["fold_to_cbet"] = pct(r["fcb_n"], r["fcb_opp"])
    r["wtsd"] = pct(r["wtsd_n"], r["saw_flop"])
    r["wsd"] = pct(r["wsd_n"], r["wtsd_n"])
    r["wwsf"] = pct(r["wwsf_n"], r["saw_flop"])
    r["af"] = round(r["agg_n"] / r["call_n"], 2) if r["call_n"] else None
    r["steal"] = pct(r["steal_n"], r["steal_opp"])
    r["win_rate_hands"] = pct(r["won_hands"], r["hands"])
    r["sd_net"] = round(r["sd_net"] or 0, 2)
    r["nsd_net"] = round(r["nsd_net"] or 0, 2)
    return r


def build_where(f):
    """f: dict with optional date_from, date_to, position, hand169, pot_type, pf_role, pf_first, ip, players, saw_flop."""
    clauses, params = [], []
    if f.get("date_from"):
        clauses.append("AND h.played_at >= ?")
        params.append(f["date_from"] + " 00:00:00")
    if f.get("date_to"):
        clauses.append("AND h.played_at <= ?")
        params.append(f["date_to"] + " 23:59:59")
    if f.get("position"):
        clauses.append("AND hp.position = ?")
        params.append(f["position"])
    if f.get("hand169"):
        vals = [v.strip() for v in f["hand169"].split(",") if v.strip()]
        if len(vals) == 1:
            clauses.append("AND hp.hand169 = ?")
            params.append(vals[0])
        elif vals:
            clauses.append("AND hp.hand169 IN (" + ",".join("?" * len(vals)) + ")")
            params += vals
    if f.get("pot_type"):
        clauses.append("AND hp.pot_type = ?")
        params.append(f["pot_type"])
    if f.get("pf_role"):
        clauses.append("AND hp.pf_role = ?")
        params.append(f["pf_role"])
    if f.get("pf_first"):
        clauses.append("AND hp.pf_first = ?")
        params.append(f["pf_first"])
    if f.get("ip") in ("0", "1", 0, 1):
        clauses.append("AND hp.ip = ?")
        params.append(int(f["ip"]))
    if f.get("players") == "hu":
        clauses.append("AND hp.flop_players = 2")
    elif f.get("players") == "multi":
        clauses.append("AND hp.flop_players >= 3")
    if f.get("saw_flop") == "1":
        clauses.append("AND hp.saw_flop = 1")
    if f.get("flop_strength"):
        vals = f["flop_strength"].split(",")
        clauses.append("AND hp.flop_strength IN (" + ",".join("?" * len(vals)) + ")")
        params += vals
    if f.get("flop_line"):
        vals = f["flop_line"].split(",")
        clauses.append("AND hp.flop_line IN (" + ",".join("?" * len(vals)) + ")")
        params += vals
    for col in ("turn_line", "river_line"):
        if f.get(col):
            vals = f[col].split(",")
            clauses.append(f"AND hp.{col} IN (" + ",".join("?" * len(vals)) + ")")
            params += vals
    if f.get("preset") in PRESETS:
        clauses.append("AND " + PRESETS[f["preset"]]["sql"])
    # ---- 翻前策略分頁用的隱藏篩選 ----
    if f.get("first_in") == "1":
        clauses.append("AND hp.pf_faced = 0 AND " + FIRST_IN_SQL)
    if f.get("vs3b_pos"):
        clauses.append("AND hp.faced_three_bet = 1 AND " + VILLAIN3B_POS_SQL + " = ?")
        params.append(f["vs3b_pos"])
    if f.get("vs_open_pos"):
        clauses.append("AND hp.pf_faced = 1 AND hp.pf_first IN ('3bet','call','fold') AND " + OPENER_POS_SQL + " = ? AND " + NO_CALLER_BETWEEN_SQL)
        params.append(f["vs_open_pos"])
    if f.get("vs4b_pos"):
        clauses.append("AND hp.pf_first = '3bet' AND " + OPENER_POS_SQL + " = ? AND " + FOURBET_BY_OPENER_SQL + " AND " + HERO_RESP4_SQL + " IS NOT NULL")
        params.append(f["vs4b_pos"])
    if f.get("opp_id"):
        mode = f.get("opp_mode", "table")
        extra = " AND v.vpip = 1" if mode == "vpip" else " AND v.cards IS NOT NULL" if mode == "shown" else ""
        clauses.append("AND EXISTS (SELECT 1 FROM hand_players v WHERE v.hand_id = hp.hand_id AND v.name = ?" + extra + ")")
        params.append(f["opp_id"].strip())
    if f.get("hid"):
        # 牌局編號搜尋：可只打後幾碼，大小寫不分
        q = f["hid"].strip().upper().replace("#", "")
        clauses.append("AND UPPER(hp.hand_id) LIKE ?")
        params.append("%" + q + "%")
    if f.get("pf_resp") in ("fold", "call", "4bet"):
        act = {"fold": "folds", "call": "calls", "4bet": "raises"}[f["pf_resp"]]
        clauses.append("AND " + HERO_RESP_SQL + " = ?")
        params.append(act)
    return " ".join(clauses), params


# 翻前第二次加注（= 3-bet）的 ord
THREEBET_ORD_SQL = "(SELECT a2.ord FROM actions a2 WHERE a2.hand_id=hp.hand_id AND a2.street='preflop' AND a2.action='raises' ORDER BY a2.ord LIMIT 1 OFFSET 1)"
# 3-bet 者的位置
VILLAIN3B_POS_SQL = "(SELECT v.position FROM actions a JOIN hand_players v ON v.hand_id=a.hand_id AND v.name=a.name WHERE a.hand_id=hp.hand_id AND a.street='preflop' AND a.action='raises' ORDER BY a.ord LIMIT 1 OFFSET 1)"
# 被 3-bet 之後 hero 的第一個動作
HERO_RESP_SQL = f"(SELECT a.action FROM actions a WHERE a.hand_id=hp.hand_id AND a.street='preflop' AND a.name=hp.name AND a.ord > {THREEBET_ORD_SQL} ORDER BY a.ord LIMIT 1)"
# 翻前第一個加注者（開池者）的位置
OPENER_POS_SQL = "(SELECT v.position FROM actions a JOIN hand_players v ON v.hand_id=a.hand_id AND v.name=a.name WHERE a.hand_id=hp.hand_id AND a.street='preflop' AND a.action='raises' ORDER BY a.ord LIMIT 1)"
# 開池之後、hero 行動之前沒有人跟注（純粹面對一個開池）
NO_CALLER_BETWEEN_SQL = "NOT EXISTS (SELECT 1 FROM actions a WHERE a.hand_id=hp.hand_id AND a.street='preflop' AND a.action='calls' AND a.name != hp.name AND a.ord < (SELECT MIN(a3.ord) FROM actions a3 WHERE a3.hand_id=hp.hand_id AND a3.street='preflop' AND a3.name=hp.name))"
# 翻前第三次加注（= 4-bet）的 ord，且必須是開池者做的
FOURBET_ORD_SQL = "(SELECT a4.ord FROM actions a4 WHERE a4.hand_id=hp.hand_id AND a4.street='preflop' AND a4.action='raises' ORDER BY a4.ord LIMIT 1 OFFSET 2)"
FOURBET_BY_OPENER_SQL = "(SELECT a4.name FROM actions a4 WHERE a4.hand_id=hp.hand_id AND a4.street='preflop' AND a4.action='raises' ORDER BY a4.ord LIMIT 1 OFFSET 2) = (SELECT a1.name FROM actions a1 WHERE a1.hand_id=hp.hand_id AND a1.street='preflop' AND a1.action='raises' ORDER BY a1.ord LIMIT 1)"
# 被 4-bet 之後 hero 的第一個動作
HERO_RESP4_SQL = f"(SELECT a.action FROM actions a WHERE a.hand_id=hp.hand_id AND a.street='preflop' AND a.name=hp.name AND a.ord > {FOURBET_ORD_SQL} ORDER BY a.ord LIMIT 1)"
# hero 行動前沒有任何人投錢（真正的首入位）
FIRST_IN_SQL = "NOT EXISTS (SELECT 1 FROM actions a WHERE a.hand_id=hp.hand_id AND a.street='preflop' AND a.action IN ('calls','raises') AND a.ord < (SELECT MIN(a3.ord) FROM actions a3 WHERE a3.hand_id=hp.hand_id AND a3.street='preflop' AND a3.name=hp.name))"


STRONG = "('set','two_pair','trips','straight','flush','fullhouse+')"
PREMIUM_VS_3BET = "('AA','KK','QQ','JJ','TT','AKs','AKo','AQs','AJs','KQs')"

PRESETS = {
    "caller_oop_high_draw": {
        "title": "1. SRP 跟注者 OOP，翻牌只有高牌或聽牌",
        "desc": "翻前跟注後 OOP 沒中牌，check-call 或 check-fold 都在漏血；要嘛翻前棄，要嘛翻牌 check-raise 拿棄牌率。",
        "sql": "hp.pot_type = 'SRP' AND hp.pf_role = 'caller' AND hp.ip = 0 AND hp.flop_strength IN ('overcards','flush_draw','oesd','gutshot')",
    },
    "call_turn_fold_river": {
        "title": "2. 轉牌跟注後河牌棄牌",
        "desc": "跟了轉牌卻在河牌放棄，是最貴的線路：要嘛轉牌就棄，要嘛河牌跟到底。",
        "sql": "EXISTS (SELECT 1 FROM actions a WHERE a.hand_id = hp.hand_id AND a.name = hp.name AND a.street = 'turn' AND a.action = 'calls') AND hp.fold_street = 'river'",
    },
    "flop_checkraise": {
        "title": "3. 翻牌 check-raise",
        "desc": "實際只虧 $15 但 EV 虧 $25——你 check-raise 之後常是落後方全下，靠運氣補回來。檢查是用什麼牌 check-raise、被 3-bet 後怎麼處理。",
        "sql": "hp.flop_line = 'check-raise'",
    },
    "bb_call_weak_suited": {
        "title": "4. BB 用 Kxs／Qxs／同花隔張跟注開池",
        "desc": "這些牌 OOP 跟注後翻後太難打；改成 3-bet 或棄牌，跟注留給同花連牌與 Axs。",
        "sql": "hp.position = 'BB' AND hp.pf_first = 'call' AND (hp.hand169 LIKE 'K_s' OR hp.hand169 LIKE 'Q_s' OR hp.hand169 IN ('97s','86s','75s','64s','53s','T8s','J9s'))",
    },
    "cbet_called_turn_giveup": {
        "title": "5. 翻牌 C-bet 被跟，轉牌 check 後棄牌",
        "desc": "對手翻牌跟注範圍很寬、轉牌面對第二槍棄 50%；你 check 等於把底池送回去。",
        "sql": "hp.cbet = 1 AND EXISTS (SELECT 1 FROM actions a WHERE a.hand_id = hp.hand_id AND a.name = hp.name AND a.street = 'turn' AND a.action = 'checks') AND hp.fold_street IN ('turn','river')",
    },
    "call_3bet_out_of_range": {
        "title": "6. 面對 3-bet 用 TT／AQ 以下的牌跟注",
        "desc": "池子的 3-bet 範圍是線性的 QQ+/AK；AJs、KQs、中小對子跟注 3-bet 全部虧損。",
        "sql": "hp.faced_three_bet = 1 AND hp.fold_to_three_bet = 0 AND hp.hand169 NOT IN ('AA','KK','QQ','JJ','TT','AKs','AKo','AQs')",
    },
    "call_flop_raise": {
        "title": "7. 翻牌被加注後跟注",
        "desc": "這個池子翻牌加注幾乎不詐唬（攤牌贏 75%）。實際虧 $31、EV 虧 $20，怎麼算都是虧。",
        "sql": "EXISTS (SELECT 1 FROM actions a WHERE a.hand_id = hp.hand_id AND a.name = hp.name AND a.street = 'flop' AND a.action = 'calls' AND EXISTS (SELECT 1 FROM actions b WHERE b.hand_id = a.hand_id AND b.street = 'flop' AND b.action = 'raises' AND b.name != hp.name AND b.ord < a.ord))",
    },
    "turn_allin": {
        "title": "8. 轉牌全下",
        "desc": "轉牌把錢全放進去時平均是落後方（EV −$17）。多半是頂對／超對對上兩對以上，轉牌被加注要更常放手。",
        "sql": "h.allin_street = 'turn'",
    },
    "call_flop_fold_turn": {
        "title": "9. 翻牌跟注後轉牌棄牌",
        "desc": "翻牌浮起來（float）但轉牌就放棄；翻牌跟注前先想好轉牌計畫。",
        "sql": "EXISTS (SELECT 1 FROM actions a WHERE a.hand_id = hp.hand_id AND a.name = hp.name AND a.street = 'flop' AND a.action = 'calls') AND hp.fold_street = 'turn'",
    },
    "bb_call_checkfold": {
        "title": "10. BB 跟注開池後翻牌 check-fold",
        "desc": "防守了大盲卻在翻牌面對 C-bet 全棄。對手 C-bet 62%，這裡要多 check-raise 或用聽牌 check-call。",
        "sql": "hp.position = 'BB' AND hp.pf_first = 'call' AND hp.flop_line = 'check-fold'",
    },
    "btn_suited_junk_bluff": {
        "title": "11. BTN 用同花小連牌／隔張開池，翻後沒中還下注詐唬",
        "desc": "這些牌在 BTN 靠偷盲賺；翻牌被跟後沒中（空氣／高牌／卡順／中弱對）就該 check 放棄，不要當詐唬主力。",
        "sql": "hp.position = 'BTN' AND hp.pf_first IN ('open','iso') AND hp.pot_type = 'SRP' AND hp.saw_flop = 1 AND hp.hand169 LIKE '__s' AND substr(hp.hand169,1,1) NOT IN ('A','K') AND hp.flop_strength IN ('air','overcards','gutshot','weak_pair','mid_pair') AND (hp.flop_line LIKE 'bet%' OR hp.turn_line LIKE 'bet%' OR hp.river_line LIKE 'bet%')",
    },
    "bp_raised": {
        "title": "13. 大底池：3BP/4BP 一對牌被加注卻繼續",
        "desc": "規則 1。3-bet/4-bet 底池拿一對（含超對／AK 頂對）面對加注，建議棄卻跟或再加注的手。",
        "sql": "EXISTS (SELECT 1 FROM bigpot_spots b WHERE b.hand_id=hp.hand_id AND b.kind='raised' AND b.rec='fold' AND b.actual!='fold')",
    },
    "bp_bet3bp": {
        "title": "14. 大底池：3BP/4BP 連續兩街被下注沒放",
        "desc": "規則 1。對手翻牌下注、轉牌／河牌再下注，你拿一對還跟。",
        "sql": "EXISTS (SELECT 1 FROM bigpot_spots b WHERE b.hand_id=hp.hand_id AND b.kind='bet3bp' AND b.rec='fold' AND b.actual!='fold')",
    },
    "bp_pre5b": {
        "title": "15. 大底池：面對 5-bet 全下用 QQ/AK 跟",
        "desc": "規則 2／3。只有 AA/KK 跟（>150bb 連 KK 都放）。",
        "sql": "EXISTS (SELECT 1 FROM bigpot_spots b WHERE b.hand_id=hp.hand_id AND b.kind='pre5b' AND b.rec='fold' AND b.actual!='fold')",
    },
    "bp_river": {
        "title": "16. 大底池：河牌大注用一對／弱兩對跟",
        "desc": "規則 4。對手連續攻擊到河牌下 ≥60% 底池或全下，你用一對或非頂兩對跟。",
        "sql": "EXISTS (SELECT 1 FROM bigpot_spots b WHERE b.hand_id=hp.hand_id AND b.kind IN ('river','turn2') AND b.rec='fold' AND b.actual!='fold')",
    },
    "bp_value": {
        "title": "17. 大底池：一對牌自己下大注／全下",
        "desc": "規則 1 的進攻版。3BP/4BP 或 ≥40bb 底池被過牌讓到你，你拿一對下 ≥60% 底池或全下。",
        "sql": "EXISTS (SELECT 1 FROM bigpot_spots b WHERE b.hand_id=hp.hand_id AND b.kind='value' AND b.rec='check' AND b.actual='bet')",
    },
    "bp_srp": {
        "title": "18. SRP 被加注第二次還跟",
        "desc": "SRP 一對牌只跟一次加注；河牌被加注一律棄。",
        "sql": "EXISTS (SELECT 1 FROM bigpot_spots b WHERE b.hand_id=hp.hand_id AND b.kind='raised_srp' AND b.rec='fold' AND b.actual!='fold')",
    },
    "bp_passive": {
        "title": "19. 反例：河牌單一下注該跟卻棄",
        "desc": "對手前面都過牌、河牌才下一次注，你拿頂對以上棄掉——這是池子最常詐唬的地方。",
        "sql": "EXISTS (SELECT 1 FROM bigpot_spots b WHERE b.hand_id=hp.hand_id AND b.kind='passive' AND b.rec='call' AND b.actual='fold')",
    },
    "toppair_big_loss": {
        "title": "20. 頂對輸 ≥40bb",
        "desc": "翻牌頂對最後輸掉 40bb 以上的手：頂對小底池是賺的，全部虧損來自這些。",
        "sql": "hp.flop_strength='top_pair' AND hp.net/h.bb <= -40",
    },
    "air_second_barrel": {
        "title": "12. 空氣 C-bet 被跟注後，轉牌再下第二槍",
        "desc": "第一槍對手棄 43% 是賺的；被跟之後的第二槍對手只棄 50% 而且範圍已經變強。空氣被跟就 check。",
        "sql": "hp.cbet = 1 AND hp.flop_strength IN ('air','overcards','gutshot') AND hp.turn_line LIKE 'bet%' AND EXISTS (SELECT 1 FROM actions a WHERE a.hand_id = hp.hand_id AND a.street = 'flop' AND a.name != hp.name AND a.action = 'calls')",
    },
}


def presets_summary(con, player="Hero", filters=None):
    """Hands / net for each preset (ignores the 'preset' key in filters)."""
    base = {k: v for k, v in (filters or {}).items() if k != "preset"}
    out = []
    for key, meta in PRESETS.items():
        w, p = build_where({**base, "preset": key})
        row = con.execute(
            f"""SELECT COUNT(*) AS hands, ROUND(COALESCE(SUM(hp.net),0),2) AS net, ROUND(COALESCE(SUM(hp.ev_net),0),2) AS ev
                FROM hand_players hp JOIN hands h ON h.hand_id=hp.hand_id WHERE hp.name=? {w}""",
            [player] + p,
        ).fetchone()
        out.append({"key": key, "title": meta["title"], "desc": meta["desc"], "hands": row["hands"], "net": row["net"], "ev": row["ev"]})
    return out


def overall(con, player="Hero", filters=None):
    w, p = build_where(filters or {})
    row = con.execute(STAT_SQL.format(where=w), [player] + p).fetchone()
    return finish(row)


def by_position(con, player="Hero", filters=None):
    w, p = build_where(filters or {})
    out = []
    for pos in ("UTG", "MP", "CO", "BTN", "SB", "BB"):
        row = con.execute(STAT_SQL.format(where=w + " AND hp.position = ?"), [player] + p + [pos]).fetchone()
        r = finish(row)
        r["position"] = pos
        out.append(r)
    return out


def by_hand169(con, player="Hero", filters=None):
    w, p = build_where(filters or {})
    rows = con.execute(
        f"""SELECT hp.hand169 AS hand, COUNT(*) AS hands, ROUND(SUM(hp.net),2) AS net,
               ROUND(SUM(hp.net/h.bb)/COUNT(*)*100,1) AS bb100,
               SUM(hp.vpip) AS vpip_n, SUM(hp.pfr) AS pfr_n,
               SUM(hp.saw_showdown) AS wtsd_n, SUM(hp.won_showdown) AS wsd_n
            FROM hand_players hp JOIN hands h ON h.hand_id=hp.hand_id
            WHERE hp.name=? AND hp.hand169 IS NOT NULL {w}
            GROUP BY hp.hand169""",
        [player] + p,
    ).fetchall()
    out = {}
    for r in rows:
        d = dict(r)
        d["vpip"] = pct(d["vpip_n"], d["hands"])
        d["pfr"] = pct(d["pfr_n"], d["hands"])
        out[d["hand"]] = d
    return out


def by_day(con, player="Hero", filters=None):
    w, p = build_where(filters or {})
    rows = con.execute(
        f"""SELECT substr(h.played_at,1,10) AS day, COUNT(*) AS hands, ROUND(SUM(hp.net),2) AS net,
               ROUND(SUM(hp.net/h.bb)/COUNT(*)*100,1) AS bb100,
               SUM(hp.vpip) AS vpip_n, SUM(hp.pfr) AS pfr_n
            FROM hand_players hp JOIN hands h ON h.hand_id=hp.hand_id
            WHERE hp.name=? {w} GROUP BY day ORDER BY day""",
        [player] + p,
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["vpip"] = pct(d["vpip_n"], d["hands"])
        d["pfr"] = pct(d["pfr_n"], d["hands"])
        out.append(d)
    return out


def graph(con, player="Hero", filters=None):
    """Cumulative net / showdown / non-showdown, one point per hand."""
    w, p = build_where(filters or {})
    rows = con.execute(
        f"""SELECT h.played_at, hp.net, hp.saw_showdown, h.bb, h.hand_id, hp.ev_net
            FROM hand_players hp JOIN hands h ON h.hand_id=hp.hand_id
            WHERE hp.name=? {w} ORDER BY h.played_at, h.hand_id""",
        [player] + p,
    ).fetchall()
    net = sd = nsd = ev = 0.0
    pts = []
    ids = []
    for r in rows:
        net += r["net"]
        ev += r["ev_net"] if r["ev_net"] is not None else r["net"]
        if r["saw_showdown"]:
            sd += r["net"]
        else:
            nsd += r["net"]
        pts.append([round(net, 2), round(sd, 2), round(nsd, 2), round(ev, 2)])
        ids.append(r["hand_id"])
    # thin to <= 3000 points for the browser but keep ids aligned
    if len(pts) > 3000:
        step = len(pts) / 3000.0
        idx = [int(i * step) for i in range(3000)] + [len(pts) - 1]
        pts = [pts[i] for i in idx]
        ids = [ids[i] for i in idx]
    return {"points": pts, "ids": ids, "n": len(rows), "bb": rows[0]["bb"] if rows else 0.05}


def hand_list(con, player="Hero", filters=None, sort="played_at", desc=True, limit=200, offset=0):
    w, p = build_where(filters or {})
    sort_col = {"played_at": "h.played_at", "net": "hp.net", "pot": "h.total_pot", "ev": "(hp.ev_net - hp.net)"}.get(sort, "h.played_at")
    rows = con.execute(
        f"""SELECT h.hand_id, h.played_at, h.table_name, hp.position, hp.cards, hp.hand169,
               hp.net, h.total_pot, h.board, hp.saw_showdown, hp.fold_street, h.n_players,
               hp.vpip, hp.pfr, hp.pot_type, hp.pf_role, hp.ip, hp.flop_strength, hp.flop_line, hp.turn_line, hp.river_line, hp.ev_net, h.bb, h.allin_street,
               (SELECT group_concat(o.position || ':' || o.cards, ' | ') FROM hand_players o
                  WHERE o.hand_id = h.hand_id AND o.name != hp.name AND o.cards IS NOT NULL) AS opp_cards
            FROM hand_players hp JOIN hands h ON h.hand_id=hp.hand_id
            WHERE hp.name=? {w}
            ORDER BY {sort_col} {'DESC' if desc else 'ASC'} LIMIT ? OFFSET ?""",
        [player] + p + [limit, offset],
    ).fetchall()
    total = con.execute(
        f"SELECT COUNT(*) FROM hand_players hp JOIN hands h ON h.hand_id=hp.hand_id WHERE hp.name=? {w}",
        [player] + p,
    ).fetchone()[0]
    out = [dict(r) for r in rows]
    if out:
        ids = [r["hand_id"] for r in out]
        q = ",".join("?" * len(ids))
        acts = con.execute(f"SELECT hand_id, street, name, action, amount, total, all_in FROM actions WHERE hand_id IN ({q}) ORDER BY hand_id, ord", ids).fetchall()
        blinds = {r["hand_id"]: (r["sb"], r["bb"]) for r in con.execute(f"SELECT hand_id, sb, bb FROM hands WHERE hand_id IN ({q})", ids)}
        stars = {r["hand_id"]: (r["star"], r["note"]) for r in con.execute(f"SELECT hand_id, star, note FROM notes WHERE hand_id IN ({q})", ids)}
        by = {}
        for a in acts:
            by.setdefault(a["hand_id"], []).append(a)
        for r in out:
            bb = r.get("bb") or blinds.get(r["hand_id"], (0.02, 0.05))[1]
            sb = blinds.get(r["hand_id"], (0.02, 0.05))[0]
            pot = sb + bb
            line = {"preflop": [], "flop": [], "turn": [], "river": []}
            pots = {}
            cur = "preflop"
            for a in by.get(r["hand_id"], []):
                if a["street"] != cur:
                    pots[cur] = round(pot, 2)
                    cur = a["street"]
                pot += a["amount"] or 0
                if a["name"] == player:
                    code = {"folds": "F", "checks": "X", "calls": "C", "bets": "B", "raises": "R"}[a["action"]]
                    if a["action"] in ("bets", "raises"):
                        code += f"{(a['total'] or a['amount']) / bb:.0f}"
                    if a["all_in"]:
                        code += "!"
                    line[cur].append(code)
            pots[cur] = round(pot, 2)
            r["line"] = {k: " ".join(v) for k, v in line.items()}
            r["pots"] = pots
            r["star"], r["note"] = stars.get(r["hand_id"], (0, ""))
            r["ev_diff"] = round((r.get("ev_net") if r.get("ev_net") is not None else r["net"]) - r["net"], 2)
    return {"rows": out, "total": total}


def hand_detail(con, hand_id):
    h = con.execute("SELECT * FROM hands WHERE hand_id=?", (hand_id,)).fetchone()
    if not h:
        return None
    players = con.execute("SELECT * FROM hand_players WHERE hand_id=? ORDER BY seat", (hand_id,)).fetchall()
    acts = con.execute("SELECT * FROM actions WHERE hand_id=? ORDER BY ord", (hand_id,)).fetchall()
    note = con.execute("SELECT star, note FROM notes WHERE hand_id=?", (hand_id,)).fetchone()
    # opponent HUD stats over the whole database
    names = [p["name"] for p in players if p["name"] != "Hero"]
    hud = {}
    aliases = {}
    if names:
        q = ",".join("?" * len(names))
        for r in con.execute(f"SELECT name, alias, note FROM player_notes WHERE name IN ({q})", names):
            aliases[r["name"]] = {"alias": r["alias"], "note": r["note"]}
        for r in con.execute(
            f"""SELECT name, COUNT(*) AS hands, SUM(vpip) AS v, SUM(pfr) AS p, SUM(three_bet) AS tb, SUM(three_bet_opp) AS tbo,
                       SUM(fold_to_cbet) AS fc, SUM(faced_cbet) AS fco, SUM(cbet) AS cb, SUM(cbet_opp) AS cbo
                FROM hand_players WHERE name IN ({q}) GROUP BY name""", names):
            hud[r["name"]] = {"hands": r["hands"], "vpip": pct(r["v"], r["hands"]), "pfr": pct(r["p"], r["hands"]),
                              "threebet": pct(r["tb"], r["tbo"]), "fold_to_cbet": pct(r["fc"], r["fco"]), "cbet": pct(r["cb"], r["cbo"])}
    # session hands around this one (gap <= 30 min), for the sidebar
    from datetime import datetime, timedelta
    t0 = datetime.strptime(h["played_at"], "%Y-%m-%d %H:%M:%S")
    lo = (t0 - timedelta(hours=12)).strftime("%Y-%m-%d %H:%M:%S")
    hi = (t0 + timedelta(hours=12)).strftime("%Y-%m-%d %H:%M:%S")
    near = con.execute(
        """SELECT h.hand_id, h.played_at, h.hero_net, h.hero_cards, hp.saw_showdown FROM hands h
           LEFT JOIN hand_players hp ON hp.hand_id=h.hand_id AND hp.name='Hero'
           WHERE h.played_at BETWEEN ? AND ? ORDER BY h.played_at, h.hand_id""", (lo, hi)).fetchall()
    near = [dict(r) for r in near]
    idx = next((i for i, r in enumerate(near) if r["hand_id"] == hand_id), 0)
    gap = timedelta(minutes=30)
    a = idx
    while a > 0 and datetime.strptime(near[a]["played_at"], "%Y-%m-%d %H:%M:%S") - datetime.strptime(near[a - 1]["played_at"], "%Y-%m-%d %H:%M:%S") <= gap:
        a -= 1
    b = idx
    while b < len(near) - 1 and datetime.strptime(near[b + 1]["played_at"], "%Y-%m-%d %H:%M:%S") - datetime.strptime(near[b]["played_at"], "%Y-%m-%d %H:%M:%S") <= gap:
        b += 1
    session = near[a:b + 1]
    return {"hand": dict(h), "players": [dict(p) for p in players], "actions": [dict(a) for a in acts],
            "star": note["star"] if note else 0, "note": note["note"] if note else "", "hud": hud, "session": session, "aliases": aliases}


def set_player(con, name, alias=None, note=None):
    cur = con.execute("SELECT alias, note FROM player_notes WHERE name=?", (name,)).fetchone()
    a = cur["alias"] if cur else ""
    n = cur["note"] if cur else ""
    if alias is not None:
        a = alias.strip()
    if note is not None:
        n = note
    from datetime import datetime
    con.execute("INSERT OR REPLACE INTO player_notes VALUES (?,?,?,?)", (name, a, n, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    con.commit()
    return {"name": name, "alias": a, "note": n}


def set_note(con, hand_id, star=None, note=None):
    cur = con.execute("SELECT star, note FROM notes WHERE hand_id=?", (hand_id,)).fetchone()
    s = cur["star"] if cur else 0
    n = cur["note"] if cur else ""
    if star is not None:
        s = int(star)
    if note is not None:
        n = note
    from datetime import datetime
    con.execute("INSERT OR REPLACE INTO notes VALUES (?,?,?,?)", (hand_id, s, n, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    con.commit()
    return {"hand_id": hand_id, "star": s, "note": n}


def marked_hands(con, player="Hero"):
    rows = con.execute(
        """SELECT n.hand_id, n.star, n.note, n.updated_at, h.played_at, hp.position, hp.cards, h.board, hp.net, hp.pot_type, hp.pf_role, hp.ip
           FROM notes n JOIN hands h ON h.hand_id=n.hand_id LEFT JOIN hand_players hp ON hp.hand_id=n.hand_id AND hp.name=?
           WHERE n.star > 0 OR n.note != '' ORDER BY n.updated_at DESC""", (player,)).fetchall()
    return [dict(r) for r in rows]


def sessions(con, player="Hero", filters=None, gap_minutes=30):
    """Split hands into sessions by time gap."""
    from datetime import datetime, timedelta
    w, p = build_where(filters or {})
    rows = con.execute(
        f"""SELECT h.played_at, hp.net, hp.ev_net, hp.vpip, hp.pfr, h.bb FROM hand_players hp JOIN hands h ON h.hand_id=hp.hand_id
            WHERE hp.name=? {w} ORDER BY h.played_at""", [player] + p).fetchall()
    out = []
    cur = None
    gap = timedelta(minutes=gap_minutes)
    for r in rows:
        t = datetime.strptime(r["played_at"], "%Y-%m-%d %H:%M:%S")
        if cur is None or t - cur["_last"] > gap:
            if cur:
                out.append(cur)
            cur = {"start": r["played_at"], "end": r["played_at"], "hands": 0, "net": 0.0, "ev": 0.0, "vpip": 0, "pfr": 0, "bb": r["bb"], "_last": t, "_first": t}
        cur["_last"] = t
        cur["end"] = r["played_at"]
        cur["hands"] += 1
        cur["net"] += r["net"]
        cur["ev"] += r["ev_net"] if r["ev_net"] is not None else r["net"]
        cur["vpip"] += r["vpip"]
        cur["pfr"] += r["pfr"]
    if cur:
        out.append(cur)
    for s in out:
        mins = max(1, int((s["_last"] - s["_first"]).total_seconds() // 60) + 1)
        s["minutes"] = mins
        s["net"] = round(s["net"], 2)
        s["ev"] = round(s["ev"], 2)
        s["bb100"] = round(s["net"] / s["bb"] / s["hands"] * 100, 1)
        s["vpip"] = pct(s["vpip"], s["hands"])
        s["pfr"] = pct(s["pfr"], s["hands"])
        s["hands_per_hour"] = round(s["hands"] / mins * 60)
        del s["_last"], s["_first"]
    out.reverse()
    return out


STRENGTH_ORDER = ["fullhouse+", "flush", "straight", "set", "trips", "board_trips", "two_pair", "overpair", "top_pair", "combo_draw",
                  "flush_draw", "oesd", "mid_pair", "weak_pair", "underpair", "gutshot", "overcards", "air"]


def hand_strength_report(con, player="Hero", filters=None):
    w, p = build_where(filters or {})
    rows = con.execute(
        f"""SELECT hp.flop_strength AS s, hp.ip, COUNT(*) AS hands, ROUND(SUM(hp.net),2) AS net,
               ROUND(SUM(hp.net/h.bb)/COUNT(*)*100,1) AS bb100,
               SUM(hp.saw_showdown) AS wtsd_n, SUM(hp.won_showdown) AS wsd_n, SUM(hp.won_sd_money) AS wwsf_n,
               SUM(hp.flop_line LIKE 'bet%') AS bet_n, SUM(hp.flop_line='check-raise' OR hp.flop_line='raise') AS raise_n,
               SUM(hp.flop_line='check-call' OR hp.flop_line='call') AS call_n, SUM(hp.flop_line LIKE '%fold') AS fold_n
            FROM hand_players hp JOIN hands h ON h.hand_id=hp.hand_id
            WHERE hp.name=? AND hp.saw_flop=1 AND hp.flop_strength != '' {w}
            GROUP BY hp.flop_strength, hp.ip""", [player] + p).fetchall()
    by = {}
    for r in rows:
        d = by.setdefault(r["s"], {"strength": r["s"], "hands": 0, "net": 0.0, "bbsum": 0.0, "wtsd_n": 0, "wsd_n": 0, "wwsf_n": 0, "bet_n": 0, "raise_n": 0, "call_n": 0, "fold_n": 0, "ip": {}, })
        for k in ("hands", "wtsd_n", "wsd_n", "wwsf_n", "bet_n", "raise_n", "call_n", "fold_n"):
            d[k] += r[k]
        d["net"] += r["net"]
        d["ip"]["IP" if r["ip"] == 1 else "OOP"] = {"hands": r["hands"], "net": r["net"], "bb100": r["bb100"]}
    out = []
    for s in STRENGTH_ORDER:
        if s not in by:
            continue
        d = by[s]
        d["net"] = round(d["net"], 2)
        d["bb100"] = round(d["net"] / 0.05 / d["hands"] * 100, 1) if d["hands"] else None
        d["wtsd"] = pct(d["wtsd_n"], d["hands"])
        d["wsd"] = pct(d["wsd_n"], d["wtsd_n"])
        d["wwsf"] = pct(d["wwsf_n"], d["hands"])
        for k in ("bet", "raise", "call", "fold"):
            d[k] = pct(d[k + "_n"], d["hands"])
        del d["bbsum"]
        out.append(d)
    return out


def opponents(con, min_hands=30, filters=None, name_like=""):
    f = {k: v for k, v in (filters or {}).items() if k not in ("opp_id", "opp_mode")}
    w, p = build_where(f)
    nl = ""
    if name_like:
        nl = " AND hp.name LIKE ?"
        p = p + ["%" + name_like.strip() + "%"]
    rows = con.execute(
        f"""SELECT hp.name, COUNT(*) AS hands, ROUND(SUM(hp.net),2) AS net,
               ROUND(AVG(hp.stack / h.bb)) AS stack_bb,
               SUM(hp.vpip) AS vpip_n, SUM(hp.pfr) AS pfr_n,
               SUM(hp.three_bet) AS tb_n, SUM(hp.three_bet_opp) AS tb_opp,
               SUM(hp.fold_to_three_bet) AS f3b_n, SUM(hp.faced_three_bet) AS f3b_opp,
               SUM(hp.steal) AS st_n, SUM(hp.steal_opp) AS st_opp,
               SUM(CASE WHEN hp.position='BB' AND hp.pf_faced=1 AND hp.pf_first='fold' THEN 1 ELSE 0 END) AS bbf_n,
               SUM(CASE WHEN hp.position='BB' AND hp.pf_faced=1 THEN 1 ELSE 0 END) AS bbf_opp,
               SUM(hp.cbet) AS cb_n, SUM(hp.cbet_opp) AS cb_opp,
               SUM(hp.fold_to_cbet) AS fcb_n, SUM(hp.faced_cbet) AS fcb_opp,
               SUM(hp.saw_flop) AS sf, SUM(hp.saw_showdown) AS wtsd_n, SUM(hp.won_showdown) AS wsd_n,
               SUM(hp.agg_bets+hp.agg_raises) AS agg, SUM(hp.agg_calls) AS calls,
               SUM(CASE WHEN hp.cards IS NOT NULL THEN 1 ELSE 0 END) AS shown,
               MIN(h.played_at) AS first_seen, MAX(h.played_at) AS last_seen,
               (SELECT alias FROM player_notes pn WHERE pn.name=hp.name) AS alias,
               (SELECT note FROM player_notes pn WHERE pn.name=hp.name) AS pnote
            FROM hand_players hp JOIN hands h ON h.hand_id=hp.hand_id
            WHERE hp.name != 'Hero' {w} {nl}
            GROUP BY hp.name HAVING COUNT(*) >= ? ORDER BY hands DESC LIMIT 300""",
        p + [min_hands],
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["vpip"] = pct(d["vpip_n"], d["hands"])
        d["pfr"] = pct(d["pfr_n"], d["hands"])
        d["threebet"] = pct(d["tb_n"], d["tb_opp"])
        d["cbet"] = pct(d["cb_n"], d["cb_opp"])
        d["fold_to_3bet"] = pct(d["f3b_n"], d["f3b_opp"])
        d["steal"] = pct(d["st_n"], d["st_opp"])
        d["bb_fold"] = pct(d["bbf_n"], d["bbf_opp"])
        d["fold_to_cbet"] = pct(d["fcb_n"], d["fcb_opp"])
        d["wtsd"] = pct(d["wtsd_n"], d["sf"])
        d["wsd"] = pct(d["wsd_n"], d["wtsd_n"])
        d["af"] = round(d["agg"] / d["calls"], 2) if d["calls"] else None
        out.append(d)
    return out


def meta(con):
    r = con.execute("SELECT COUNT(*) AS n, MIN(played_at) AS a, MAX(played_at) AS b FROM hands").fetchone()
    return {"hands": r["n"], "first": r["a"], "last": r["b"]}


def position_graph(con, player="Hero", filters=None):
    """Cumulative net per position (6 series), sampled to <= 600 points each."""
    w, p = build_where(filters or {})
    rows = con.execute(
        f"""SELECT hp.position, hp.net FROM hand_players hp JOIN hands h ON h.hand_id=hp.hand_id
            WHERE hp.name=? {w} ORDER BY h.played_at, h.hand_id""",
        [player] + p,
    ).fetchall()
    series = {k: [] for k in ("UTG", "MP", "CO", "BTN", "SB", "BB")}
    cum = {k: 0.0 for k in series}
    for r in rows:
        pos = r["position"]
        if pos not in series:
            continue
        cum[pos] += r["net"]
        series[pos].append(round(cum[pos], 2))
    out = {}
    for k, v in series.items():
        if len(v) > 600:
            step = len(v) / 600.0
            v = [v[int(i * step)] for i in range(600)] + [v[-1]]
        out[k] = v
    return out


def range_chart(con, player="Hero", filters=None, position="", action="open"):
    """
    For each 169 hand: how often the player took `action` as first preflop action,
    among hands where that action was available.
    action: open | 3bet | call | fold_vs_open | limp
    Opportunity sets:
      open/limp : hands where player's pf_first in (open, fold, limp) i.e. first-in spot
                  (approximation: pf_first in open/limp/fold with no raise before) -> we use pf_first in ('open','limp','fold') AND player faced no raise
      3bet/call : hands where player's pf_first in ('3bet','call','fold') and there was exactly one raise before -> pf_first in those and pot had >=1 raise
    We approximate "faced a raise" by pf_first in ('3bet','call','fold_vs_raise').
    """
    f = {k: v for k, v in (filters or {}).items() if k in ("date_from", "date_to")}
    w, p = build_where(f)
    extra = ""
    if position:
        extra = " AND hp.position = ?"
        p = p + [position]
    rows = con.execute(
        f"""SELECT hp.hand169, hp.pf_first, hp.pf_faced, hp.position
            FROM hand_players hp JOIN hands h ON h.hand_id=hp.hand_id
            WHERE hp.name=? AND hp.hand169 IS NOT NULL {w} {extra}""",
        [player] + p,
    ).fetchall()
    opp, hit = {}, {}
    for r in rows:
        k = r["hand169"]
        pf = r["pf_first"]
        if action in ("open", "limp"):
            if r["pf_faced"] == 0 and pf in ("open", "iso", "limp", "fold"):
                opp[k] = opp.get(k, 0) + 1
                if (action == "open" and pf in ("open", "iso")) or (action == "limp" and pf == "limp"):
                    hit[k] = hit.get(k, 0) + 1
        else:  # facing a single raise
            if r["pf_faced"] == 1 and pf in ("3bet", "call", "fold"):
                opp[k] = opp.get(k, 0) + 1
                if (action == "3bet" and pf == "3bet") or (action == "call" and pf == "call") or (action == "fold_vs_open" and pf == "fold"):
                    hit[k] = hit.get(k, 0) + 1
    return {k: {"opp": opp[k], "n": hit.get(k, 0), "freq": round(100.0 * hit.get(k, 0) / opp[k], 1)} for k in opp}


def preflop_compare(con, player="Hero", filters=None, mode="open", pos="BTN", vpos="BB"):
    """
    翻前策略對照。
    mode=open : 該位置首入時，每個 169 手牌的實際開池次數 / 首入機會、開池手的淨利與 EV。
    mode=vs3b : 在 pos 開池被 vpos 3-bet 時，每個 169 手牌的實際 4bet/call/fold 次數與淨利、EV。
    """
    import ranges
    f = {k: v for k, v in (filters or {}).items() if k in ("date_from", "date_to")}
    w, p = build_where(f)
    out = {}
    if mode == "open":
        rows = con.execute(
            f"""SELECT hp.hand169, hp.pf_first, hp.net, hp.ev_net
                FROM hand_players hp JOIN hands h ON h.hand_id=hp.hand_id
                WHERE hp.name=? AND hp.position=? AND hp.hand169 IS NOT NULL
                  AND hp.pf_faced=0 AND {FIRST_IN_SQL} {w}""",
            [player, pos] + p).fetchall()
        for r in rows:
            k = r["hand169"]
            d = out.setdefault(k, {"opp": 0, "open": 0, "net": 0.0, "ev": 0.0})
            d["opp"] += 1
            if r["pf_first"] in ("open", "iso"):
                d["open"] += 1
                d["net"] += r["net"] or 0
                d["ev"] += (r["ev_net"] if r["ev_net"] is not None else r["net"]) or 0
        chart = ranges.open_chart(pos)
    elif mode == "vs3b":
        rows = con.execute(
            f"""SELECT hp.hand169, hp.net, hp.ev_net, {HERO_RESP_SQL} AS resp
                FROM hand_players hp JOIN hands h ON h.hand_id=hp.hand_id
                WHERE hp.name=? AND hp.position=? AND hp.hand169 IS NOT NULL
                  AND hp.pf_first IN ('open','iso') AND hp.faced_three_bet=1
                  AND {VILLAIN3B_POS_SQL} = ? {w}""",
            [player, pos, vpos] + p).fetchall()
        for r in rows:
            k = r["hand169"]
            d = out.setdefault(k, {"opp": 0, "fold": 0, "call": 0, "4bet": 0, "net": 0.0, "ev": 0.0})
            d["opp"] += 1
            a = {"folds": "fold", "calls": "call", "raises": "4bet"}.get(r["resp"])
            if a:
                d[a] += 1
            d["net"] += r["net"] or 0
            d["ev"] += (r["ev_net"] if r["ev_net"] is not None else r["net"]) or 0
        chart = ranges.vs3b_chart(pos, vpos)
    if mode == "vsopen":
        out = {}
        rows = con.execute(
            f"""SELECT hp.hand169, hp.pf_first, hp.net, hp.ev_net
                FROM hand_players hp JOIN hands h ON h.hand_id=hp.hand_id
                WHERE hp.name=? AND hp.position=? AND hp.hand169 IS NOT NULL
                  AND hp.pf_faced=1 AND hp.pf_first IN ('3bet','call','fold')
                  AND {OPENER_POS_SQL} = ? AND {NO_CALLER_BETWEEN_SQL} {w}""",
            [player, pos, vpos] + p).fetchall()
        for r in rows:
            k = r["hand169"]
            d = out.setdefault(k, {"opp": 0, "fold": 0, "call": 0, "3bet": 0, "net": 0.0, "ev": 0.0})
            d["opp"] += 1
            d[r["pf_first"]] += 1
            d["net"] += r["net"] or 0
            d["ev"] += (r["ev_net"] if r["ev_net"] is not None else r["net"]) or 0
        chart = ranges.vsopen_chart(pos, vpos)
    if mode == "vs4b":
        out = {}
        rows = con.execute(
            f"""SELECT hp.hand169, hp.net, hp.ev_net, {HERO_RESP4_SQL} AS resp
                FROM hand_players hp JOIN hands h ON h.hand_id=hp.hand_id
                WHERE hp.name=? AND hp.position=? AND hp.hand169 IS NOT NULL
                  AND hp.pf_first='3bet' AND {OPENER_POS_SQL} = ? AND {FOURBET_BY_OPENER_SQL} {w}""",
            [player, pos, vpos] + p).fetchall()
        for r in rows:
            if not r["resp"]:
                continue
            k = r["hand169"]
            d = out.setdefault(k, {"opp": 0, "fold": 0, "call": 0, "5bet": 0, "net": 0.0, "ev": 0.0})
            d["opp"] += 1
            d[{"folds": "fold", "calls": "call", "raises": "5bet"}.get(r["resp"], "fold")] += 1
            d["net"] += r["net"] or 0
            d["ev"] += (r["ev_net"] if r["ev_net"] is not None else r["net"]) or 0
        chart = ranges.vs4b_chart(pos, vpos)
    for d in out.values():
        d["net"] = round(d["net"], 2)
        d["ev"] = round(d["ev"], 2)
    return {"chart": chart, "actual": out}


def preflop_charts():
    import ranges
    return ranges.all_charts()


def refresh_bigpot(con, player="Hero"):
    """重算 bigpot_spots 表（匯入新手牌後呼叫）。"""
    import bigpot
    sp = bigpot.spots(con, player, limit=100000)
    con.execute("DELETE FROM bigpot_spots")
    con.executemany("INSERT INTO bigpot_spots VALUES (?,?,?,?,?,?,?,?)",
                    [(x["hand_id"], x["street"], x["kind"], x["rec"], x["actual"], x["net_bb"], x["ev_bb"], x["cat"]) for x in sp])
    con.commit()
    return len(sp)
