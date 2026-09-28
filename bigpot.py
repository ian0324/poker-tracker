# -*- coding: utf-8 -*-
"""
大底池決策訓練：從自己的手牌裡抽出「面對大注／加注的決策點」，附上規則建議。
決策點類型：
  pre5b   翻前 4-bet 後面對再加注（5-bet）全下
  raised  3BP/4BP 翻後被加注（含全下）
  river   河牌面對 ≥ 70% 底池的下注或全下
  turn2   轉牌面對大注（≥ 70% 底池）且對手前一街已經下注／加注過
  passive 河牌面對「前面都過牌、河牌才下注一次」（反例：一對可以跟）
"""
RANK_ORDER = "23456789TJQKA"
STREETS = ["preflop", "flop", "turn", "river"]


def hand_cat(cards, board):
    """hero 兩張 + 目前牌面 → 牌力分類。"""
    hs = cards.split()
    if len(hs) != 2 or len(board) < 3:
        return "air"
    hr = [RANK_ORDER.index(c[0]) for c in hs]
    br = [RANK_ORDER.index(c[0]) for c in board]
    allc = hs + list(board)
    ranks = [RANK_ORDER.index(c[0]) for c in allc]
    suits = [c[1] for c in allc]
    cnt = {}
    for r in ranks:
        cnt[r] = cnt.get(r, 0) + 1
    bcnt = {}
    for r in br:
        bcnt[r] = bcnt.get(r, 0) + 1
    # flush: 5 of a suit using at least one hole card
    for s in set(suits):
        if suits.count(s) >= 5 and s in [c[1] for c in hs]:
            return "flush"
    rs = set(ranks) | ({-1} if 12 in ranks else set())
    for st in range(8, -2, -1):
        if all(x in rs for x in range(st, st + 5)):
            # straight must use a hole card
            if any(x in hr for x in range(st, st + 5)):
                return "straight"
    quads = [r for r, c in cnt.items() if c == 4]
    trips = [r for r, c in cnt.items() if c == 3]
    pairs = [r for r, c in cnt.items() if c == 2]
    pocket = hr[0] == hr[1]
    if quads and (quads[0] in hr):
        return "quads"
    if trips and pairs and (trips[0] in hr or any(p in hr for p in pairs)):
        return "fullhouse"
    if trips:
        if pocket and hr[0] in trips:
            return "set"
        if trips[0] in hr:
            return "trips"
    top = max(br)
    my_pairs = [r for r in pairs if r in hr]
    if not pocket and len(my_pairs) >= 2:
        top2 = sorted(set(br))[-2:]
        return "top_two" if sorted(my_pairs)[-2:] == top2 else "two_pair"
    if pocket and hr[0] not in pairs and not any(hr[0] == t for t in trips):
        pass
    if pocket:
        if hr[0] > top:
            return "overpair"
        return "underpair"
    if my_pairs:
        r = my_pairs[0]
        if r == top:
            return "top_pair"
        if r > min(br):
            return "mid_pair"
        return "weak_pair"
    # draws (flop/turn only)
    if len(board) < 5:
        hsu = [c[1] for c in hs]
        fd = hsu[0] == hsu[1] and suits.count(hsu[0]) == 4
        outs = 0
        for st in range(-1, 9):
            need = [v for v in range(st, st + 5) if v not in rs]
            if len(need) == 1:
                outs += 1
        if fd or outs >= 2:
            return "draw"
    if min(hr) > top:
        return "overcards"
    return "air"


PAIR_CATS = {"overpair", "top_pair", "mid_pair", "weak_pair", "underpair"}
STRONG_CATS = {"quads", "fullhouse", "flush", "straight", "set", "trips", "top_two"}


def rule(spot):
    """回傳 (建議動作 call/fold, 規則說明)。"""
    k = spot["kind"]
    cat = spot["cat"]
    eff = spot["eff_bb"]
    if k == "pre5b":
        if spot["hand169"] == "AA":
            return "call", "規則 2：面對 5-bet 全下只有 AA/KK 跟。"
        if spot["hand169"] == "KK":
            if eff > 150:
                return "fold", "規則 3：有效籌碼 >150bb、對手 5-bet/6-bet 全下，KK 也放（對手範圍幾乎只有 AA）。"
            return "call", "規則 2：面對 5-bet 全下只有 AA/KK 跟。"
        return "fold", "規則 2：面對 5-bet 全下只有 AA/KK 跟；QQ/AK 與 4-bet 詐唬牌一律棄（除非對手是 VPIP 40%+ 的魚）。"
    if cat in STRONG_CATS and k != "value":
        return "call", "兩對以上（頂兩對／set／順／花）面對加注可以繼續，通常直接全下。"
    if k == "raised":
        if cat == "overpair" and spot["hand169"] in ("AA", "KK") and eff <= 120 and spot["street"] == "flop":
            return "call", "規則 1 例外：AA/KK 超對在 3BP/4BP 翻牌、有效籌碼 ≤120bb，面對加注就全下——這是標準 stack off，對手範圍裡的 QQ/JJ/TT 會付錢。深籌碼（>150bb）才需要煞車。"
        if cat == "overpair" and spot["hand169"] == "QQ" and spot["pot_type"] == "3BP" and eff <= 100 and spot["street"] == "flop" and spot["board"] and max(RANK_ORDER.index(c[0]) for c in spot["board"]) <= RANK_ORDER.index("9"):
            return "call", "規則 1 例外：QQ 在 3BP、翻牌全是 9 以下、≤100bb，面對加注可以繼續（對手 JJ/TT/99 會全下）。牌面有 T 以上或 4BP 就放。"
        if cat in PAIR_CATS:
            if cat in ("overpair", "top_pair") and spot.get("villain_checked_prev") and spot["street"] != "flop" and spot.get("n_players", 2) == 2 and not spot.get("already_called"):
                return "call", "規則 1 例外：對手前一街有機會下注卻過牌（示弱），這一街你下注他才加注／全下——範圍偏兩極（慢打或詐唬），HU 頂對頂踢腳／超對可以跟。"
            if eff <= 60:
                return "call", "規則 1 例外：對手有效籌碼 ≤ 60bb，SPR 太低，一對牌可以跟。"
            if spot.get("already_called"):
                return "fold", "規則 1：3BP/4BP 一對牌被加注只跟一街；這是第二次被攻擊，棄。"
            if spot["street"] == "flop" and cat == "overpair" and spot.get("villain_flat_4bet") is False and spot["pot_type"] == "3BP":
                return "call", "規則 1：3BP 翻牌第一次被加注，超對可以跟一街看轉牌；轉牌再被下注就放。"
            return "fold", "規則 1：3BP/4BP 一對牌（含超對）面對加注就放。這個池子加注 75% 是兩對以上。"
        if cat == "two_pair":
            return "fold", "非頂兩對面對加注在 3BP/4BP 也放；對手範圍是 set／更大兩對。"
        return "fold", "沒有成牌（聽牌／空氣）面對加注一律棄，不追。"
    if k == "raised_srp":
        if cat in ("overpair", "top_pair"):
            if spot.get("already_called"):
                return "fold", "SRP 一對牌只跟一次加注；第二次被攻擊就放。"
            if spot["street"] == "river":
                return "fold", "河牌被加注：一對牌一律棄，這個池子河牌加注 75% 以上是價值。"
            return "call", "SRP 翻牌／轉牌第一次被加注：頂對／超對可以跟一街（對手加注裡有聽牌），下一街再被下注就放。"
        if cat == "two_pair":
            return "call", "兩對面對 SRP 加注可以跟；被再加注或河牌大注再評估。"
        return "fold", "中對以下／沒成牌面對加注：棄。"
    if k == "value":
        if spot["pot_type"] == "4BP+" and cat in ("top_two", "two_pair") and spot["street"] == "river":
            return "check", "4BP 平跟 4-bet 的範圍幾乎全是口袋對＋AK/AQ：你的兩對只贏 AQ/KQ，輸給所有 set。河牌被過牌讓到你，過牌攤牌或下 30–40% 小注，不要全下。"
        if cat in STRONG_CATS or cat == "top_two":
            return "bet", "強牌（頂兩對以上）在大底池被過牌讓到你：下注 60–75% 底池或全下拿價值，池子會用一對付錢。"
        if spot["pot_type"] in ("3BP", "4BP+"):
            return "check", "規則 1 的進攻版：3BP/4BP 一對牌（含 AK 頂對、超對）在大底池不要自己把籌碼推進去；過牌控池，被下注再依規則決定。"
        if cat in ("overpair", "top_pair") and spot["street"] == "turn":
            return "bet", "SRP 頂對／超對在轉牌可以再下一槍價值（50–60% 底池），河牌看對手反應。"
        return "check", "SRP 大底池一對牌在河牌：過牌攤牌，不要用大注／全下打薄價值（對手跟的多半比你大）。"
    if k == "bet3bp":
        if cat in PAIR_CATS or cat in ("air", "overcards", "draw", "two_pair"):
            if spot["street"] == "turn" and not spot.get("already_called"):
                return "fold", "規則 1：3BP/4BP 對手翻牌下注、轉牌再下注，一對牌只跟一街——翻牌已經跟過，轉牌放。"
            return "fold", "規則 1／4：3BP/4BP 連續兩街以上被下注，一對牌一律放。"
        return "call", "頂兩對以上面對連續下注可以繼續（考慮加注）。"
    if k == "river":
        if cat in PAIR_CATS or cat == "two_pair" or cat in ("air", "overcards", "draw"):
            return "fold", "規則 4：河牌面對 ≥70% 底池的下注／全下，一對或非頂兩對一律棄。對手連續攻擊＝有牌。"
        return "call", "頂兩對以上可以跟河牌大注。"
    if k == "turn2":
        if cat in PAIR_CATS or cat in ("air", "overcards", "two_pair"):
            return "fold", "規則 4：對手翻牌下注／加注後轉牌又下大注，一對放掉；不要跟到河牌再棄。"
        if cat == "draw":
            return "fold", "聽牌面對轉牌大注：賠率不夠，棄（除非對手很淺）。"
        return "call", "頂兩對以上繼續。"
    if k == "passive":
        if cat in ("top_pair", "overpair", "top_two", "two_pair") or cat in STRONG_CATS:
            return "call", "反例：對手前面都過牌、河牌才下注一次——這是池子最常詐唬的地方，頂對以上要跟。"
        return "fold", "反例情境但你只有中對以下／沒牌，還是棄。"
    return "fold", ""


def spots(con, player="Hero", since=None, limit=2000):
    q = """SELECT h.hand_id, h.played_at, h.board, h.bb, h.pot_type, hp.cards, hp.hand169, hp.position, hp.net, hp.ev_net, hp.pf_first
           FROM hand_players hp JOIN hands h ON h.hand_id=hp.hand_id
           WHERE hp.name=? AND hp.cards IS NOT NULL AND hp.vpip=1 AND (hp.saw_flop=1 OR hp.pf_raises>=2)"""
    args = [player]
    if since:
        q += " AND h.played_at >= ?"
        args.append(since)
    q += " ORDER BY h.played_at DESC LIMIT ?"
    args.append(limit)
    hands = con.execute(q, args).fetchall()
    out = []
    hud_cache = {}

    def hud(name):
        if name not in hud_cache:
            r = con.execute("SELECT COUNT(*) n, SUM(vpip) v, SUM(pfr) p, SUM(three_bet) tb, SUM(three_bet_opp) tbo FROM hand_players WHERE name=?", (name,)).fetchone()
            al = con.execute("SELECT alias, note FROM player_notes WHERE name=?", (name,)).fetchone()
            hud_cache[name] = {"hands": r["n"], "vpip": round(100.0 * (r["v"] or 0) / r["n"]) if r["n"] else None,
                               "pfr": round(100.0 * (r["p"] or 0) / r["n"]) if r["n"] else None,
                               "threebet": round(100.0 * (r["tb"] or 0) / r["tbo"]) if r["tbo"] else None,
                               "alias": al["alias"] if al else "", "note": al["note"] if al else ""}
        return hud_cache[name]
    for h in hands:
        acts = con.execute("SELECT street, ord, name, action, amount, total, all_in FROM actions WHERE hand_id=? ORDER BY ord", (h["hand_id"],)).fetchall()
        players = {r["name"]: dict(r) for r in con.execute("SELECT name, position, cards, stack, net FROM hand_players WHERE hand_id=?", (h["hand_id"],))}
        bb = h["bb"] or 0.05
        board = (h["board"] or "").split()
        sp = _scan(h, acts, players, bb, board, player)
        for x in sp:
            x["villain_hud"] = hud(x["villain"])
            x["seats"] = [{"name": n, "pos": p["position"], "stack_bb": round((p["stack"] or 0) / bb), "hero": n == player} for n, p in players.items()]
        out.extend(sp)
    return out


def _scan(h, acts, players, bb, board, player):
    res = []
    pot_prev = 0.0  # pot from previous streets
    street = None
    committed = {n: (0.5 * bb if p.get("position") == "SB" else bb if p.get("position") == "BB" else 0.0) for n, p in players.items()}
    committed = {n: v for n, v in committed.items() if v}  # blinds (posts are not in the actions table)
    n_raises_pre = 0
    hero_raised_pre = 0
    villain_agg_prev = {}  # name -> did bet/raise on previous streets
    villain_agg_this = {}
    checks_only_before = {s: True for s in STREETS}  # nobody bet on this street before
    hero_called_raise_in_hand = False
    seq = []  # (street, name, action, total_bb)
    for a in acts:
        s = a["street"]
        if s not in STREETS:
            continue
        if s != street:
            if street is not None:
                pot_prev += sum(committed.values())
                committed = {}
            for n, v in villain_agg_this.items():
                villain_agg_prev[n] = villain_agg_prev.get(n, False) or v
            villain_agg_this = {}
            street = s
        name, act, total = a["name"], a["action"], a["total"] or 0.0
        pot_now = pot_prev + sum(committed.values())
        if name == player:
            facing = max(committed.values()) - committed.get(player, 0.0) if committed else 0.0
            if facing <= 0.001 and s in ("turn", "river") and act in ("bets", "checks") and pot_now / bb >= 40 and h["pot_type"] in ("3BP", "4BP+", "SRP"):
                nb = {"turn": 4, "river": 5}[s]
                cat = hand_cat(players[player]["cards"], board[:nb])
                bet_bb = round((total - committed.get(player, 0.0)) / bb, 1) if act == "bets" else 0
                big = act == "bets" and (bet_bb >= 0.6 * pot_now / bb or players[player]["stack"] - total <= 0.011)
                if (big or act == "checks") and (cat in PAIR_CATS or cat in STRONG_CATS or cat in ("two_pair", "top_two")):
                    others = [n for n in players if n != player and any(x["name"] == n and x["street"] == s and x["action"] == "checks" for x in acts if x["ord"] < a["ord"])]
                    vname = others[0] if others else None
                    v = players.get(vname, {}) if vname else {}
                    eff = min(players[player]["stack"], v.get("stack", 0)) / bb if v else 0
                    spot = {
                        "hand_id": h["hand_id"], "played_at": h["played_at"], "kind": "value", "street": s,
                        "pot_type": h["pot_type"], "position": h["position"], "cards": players[player]["cards"], "hand169": h["hand169"],
                        "board": board[:nb], "cat": cat, "pot_bb": round(pot_now / bb, 1), "facing_bb": 0, "eff_bb": round(eff),
                        "villain": vname or "", "villain_pos": v.get("position", ""), "villain_cards": v.get("cards"),
                        "villain_stack_bb": round(v.get("stack", 0) / bb), "villain_allin": False, "villain_total_bb": 0,
                        "already_called": hero_called_raise_in_hand,
                        "actual": "bet" if act == "bets" else "check", "actual_bet_bb": bet_bb,
                        "net_bb": round((players[player]["net"] or 0) / bb, 1),
                        "ev_bb": round(((h["ev_net"] if h["ev_net"] is not None else players[player]["net"]) or 0) / bb, 1),
                        "seq": [dict(street=x[0], name=x[1], pos=players.get(x[1], {}).get("position", ""), action=x[2], bb=x[3]) for x in seq],
                        "n_players": sum(1 for n in players if not any(x["name"] == n and x["action"] == "folds" and x["ord"] < a["ord"] for x in acts)),
                    }
                    spot["rec"], spot["rule"] = rule(spot)
                    res.append(spot)
            if facing > 0 and act in ("calls", "folds", "raises"):
                aggr = max(committed, key=committed.get)
                v = players.get(aggr, {})
                eff = min(players[player]["stack"], v.get("stack", 0)) / bb if v else 0
                kind = None
                if s == "preflop":
                    v_allin = v and (v.get("stack", 0) - committed.get(aggr, 0) <= 0.011)
                    if hero_raised_pre >= 2 and n_raises_pre >= 4 and v_allin:
                        kind = "pre5b"
                else:
                    nb = {"flop": 3, "turn": 4, "river": 5}[s]
                    cur_board = board[:nb]
                    cat = hand_cat(players[player]["cards"], cur_board)
                    villain_raised_now = any(x["name"] == aggr and x["action"] == "raises" and x["street"] == s and x["ord"] < a["ord"] for x in acts)
                    pot_before = max(pot_now - facing, 0.01)
                    frac = facing / pot_before
                    v_allin_now = v.get("stack", 0) - committed.get(aggr, 0) <= 0.011
                    if h["pot_type"] in ("3BP", "4BP+") and villain_raised_now and facing / bb >= 12:
                        kind = "raised"
                    elif h["pot_type"] in ("SRP", "LIMP") and villain_raised_now and facing / bb >= 12:
                        kind = "raised_srp"
                    elif h["pot_type"] in ("3BP", "4BP+") and s in ("turn", "river") and villain_agg_prev.get(aggr) and frac >= 0.4 and facing / bb >= 12:
                        kind = "bet3bp"
                    elif s == "river" and (frac >= 0.6 or v_allin_now) and facing / bb >= 8:
                        kind = "passive" if (not villain_agg_prev.get(aggr) and not villain_raised_now) else "river"
                    elif s == "turn" and (frac >= 0.6 or v_allin_now) and villain_agg_prev.get(aggr) and facing / bb >= 10:
                        kind = "turn2"
                if kind:
                    cat = hand_cat(players[player]["cards"], board[:{"preflop": 0, "flop": 3, "turn": 4, "river": 5}[s]]) if s != "preflop" else "preflop"
                    spot = {
                        "hand_id": h["hand_id"], "played_at": h["played_at"], "kind": kind, "street": s,
                        "pot_type": h["pot_type"], "position": h["position"], "cards": players[player]["cards"], "hand169": h["hand169"],
                        "board": board[:{"preflop": 0, "flop": 3, "turn": 4, "river": 5}[s]], "cat": cat,
                        "pot_bb": round(pot_now / bb, 1), "facing_bb": round(facing / bb, 1), "eff_bb": round(eff),
                        "villain_total_bb": round(committed.get(aggr, 0) / bb, 1),
                        "villain": aggr, "villain_pos": v.get("position", ""), "villain_cards": v.get("cards"),
                        "villain_stack_bb": round(v.get("stack", 0) / bb), "villain_allin": bool(any(x["name"] == aggr and x["all_in"] and x["street"] == s for x in acts)),
                        "already_called": hero_called_raise_in_hand,
                        "villain_checked_prev": any(x["name"] == aggr and x["action"] == "checks" and x["street"] in STREETS[1:STREETS.index(s)] for x in acts),
                        "actual": {"calls": "call", "folds": "fold", "raises": "raise"}[act],
                        "net_bb": round((players[player]["net"] or 0) / bb, 1),
                        "ev_bb": round(((h["ev_net"] if h["ev_net"] is not None else players[player]["net"]) or 0) / bb, 1),
                        "seq": [dict(street=x[0], name=x[1], pos=players.get(x[1], {}).get("position", ""), action=x[2], bb=x[3]) for x in seq],
                        "n_players": sum(1 for n in players if not any(x["name"] == n and x["action"] == "folds" and x["ord"] < a["ord"] for x in acts)),
                    }
                    spot["rec"], spot["rule"] = rule(spot)
                    res.append(spot)
                if act == "calls" and any(x["name"] == aggr and x["action"] == "raises" and x["street"] == s and s != "preflop" for x in acts):
                    hero_called_raise_in_hand = True
        # update state
        if act in ("bets", "raises"):
            committed[name] = total
            if name != player:
                villain_agg_this[name] = True
            if s == "preflop":
                n_raises_pre += 1
                if name == player:
                    hero_raised_pre += 1
        elif act == "calls":
            committed[name] = total if total else max(committed.values()) if committed else 0
        seq.append((s, name, act, round(total / bb, 1) if total else 0))
    return res
