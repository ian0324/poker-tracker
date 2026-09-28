"""
NL5 Rush & Cash 剝削型翻前範圍。
- OPEN：各位置首入加注範圍（前面全棄）。
- VS3B：開池後被 3-bet 的決策（4bet / call / fold），依「我的位置 × 3-bet 者位置」對應到一組決策表。

範圍字串語法（逗號分隔）：
  對子     22+  /  66-99
  同花     A2s+ / K9s+ / T9s-54s（同花連牌區間）/ 97s+（同花隔一張，至 AK 邊界）
  不同花   ATo+ / KQo / T9o-87o
"""

RANKS = "AKQJT98765432"
R = {r: i for i, r in enumerate(RANKS)}  # A=0 ... 2=12


def all169():
    out = []
    for i in range(13):
        for j in range(13):
            if i == j:
                out.append(RANKS[i] * 2)
            elif i < j:
                out.append(RANKS[i] + RANKS[j] + "s")
            else:
                out.append(RANKS[j] + RANKS[i] + "o")
    return out


def combos(h):
    if len(h) == 2:
        return 6
    return 4 if h[2] == "s" else 12


def _expand_token(tok):
    tok = tok.strip()
    if not tok:
        return []
    plus = tok.endswith("+")
    if plus:
        tok = tok[:-1]
    if "-" in tok:
        a, b = tok.split("-")
        return _expand_span(a.strip(), b.strip())
    # pair
    if len(tok) == 2 and tok[0] == tok[1]:
        if plus:
            return [RANKS[i] * 2 for i in range(0, R[tok[0]] + 1)]
        return [tok]
    hi, lo, suf = tok[0], tok[1], tok[2]
    if not plus:
        return [tok]
    # "A2s+" -> A2s..AKs ; "T9s+" -> T9s,JTs,QJs,KQs? No: for connectors "+" means kicker up to hi-1.
    # Convention: X?s+ raises the LOW card up to (hi-1): A5s+ = A5s A6s ... AKs ; K9s+ = K9s KTs KJs KQs.
    out = []
    for k in range(R[lo], R[hi], -1):
        out.append(hi + RANKS[k] + suf)
    return out


def _expand_span(a, b):
    """66-99 / T9s-54s / ATs-AJs / T9o-87o"""
    if len(a) == 2 and a[0] == a[1]:
        i1, i2 = R[a[0]], R[b[0]]
        lo, hi = min(i1, i2), max(i1, i2)
        return [RANKS[i] * 2 for i in range(lo, hi + 1)]
    suf = a[2]
    gap_a = R[a[1]] - R[a[0]]
    gap_b = R[b[1]] - R[b[0]]
    out = []
    if gap_a == gap_b and a[0] != b[0]:
        # same-gap span, e.g. T9s-54s
        i1, i2 = R[a[0]], R[b[0]]
        for i in range(min(i1, i2), max(i1, i2) + 1):
            j = i + gap_a
            if j < 13:
                out.append(RANKS[i] + RANKS[j] + suf)
    else:
        # same high card, low card span: ATs-AJs
        hi = a[0]
        j1, j2 = R[a[1]], R[b[1]]
        for j in range(min(j1, j2), max(j1, j2) + 1):
            out.append(hi + RANKS[j] + suf)
    return out


def parse_range(s):
    out = set()
    for tok in s.split(","):
        for h in _expand_token(tok):
            out.add(h)
    return out


def range_pct(hands):
    return round(100.0 * sum(combos(h) for h in hands) / 1326, 1)


# ---------------------------------------------------------------------------
# 首入開池範圍（剝削型）
#   依據：池子 BB 面對開池棄牌 67%、SB/BB 3-bet 少且多為價值 → 後位可以開很寬；
#   早位保持偏緊，因為多人底池、抽水高、後面 4 個人。
# ---------------------------------------------------------------------------
OPEN = {
    "UTG": "44+, A9s+, A5s-A4s, KTs+, QTs+, JTs, T9s, 98s, AJo+, KQo",
    "MP":  "22+, A7s+, A5s-A2s, K9s+, Q9s+, J9s+, T9s, 98s, 87s, ATo+, KJo+, QJo",
    "CO":  "22+, A2s+, K7s+, Q8s+, J8s+, T8s+, 97s+, 86s+, 75s+, 65s, 54s, A9o+, KTo+, QTo+, JTo",
    "BTN": "22+, A2s+, K2s+, Q2s+, J4s+, T6s+, 96s+, 85s+, 74s+, 64s+, 53s+, 43s, A2o+, K7o+, Q8o+, J8o+, T8o+, 98o",
    "SB":  "22+, A2s+, K2s+, Q2s+, J4s+, T6s+, 96s+, 85s+, 75s+, 64s+, 54s, A2o+, K5o+, Q8o+, J8o+, T8o+, 98o",
}

OPEN_NOTES = {
    "UTG": "後面還有 5 個人，池子早位 3-bet 幾乎純價值（QQ+/AK），所以只開能承受被 3-bet 的牌。A5s/A4s 是用來偶爾 4-bet 詐唬的。",
    "MP":  "加入所有對子與更多同花 Ax、同花連牌；不同花只留 ATo+、KJo+、QJo。",
    "CO":  "後面只剩 BTN 和盲注，BB 棄牌 67%，可以開 28% 左右。同花隔一張（97s、86s、75s）開得起，但翻牌沒中要放棄。",
    "BTN": "池子對 BTN 開池的 3-bet 率低、BB 棄 67%，開 49% 左右是有利可圖的。注意：K7o、Q8o、J8o 這種牌翻後只打一對＋放棄，不要 3 條街詐唬。",
    "SB":  "全棄到 SB 時對 BB 加注（不 limp）。BB 棄牌率高，開 50%。SB 開池被 BB 3-bet 時 OOP，小牌一律棄。",
}

# ---------------------------------------------------------------------------
# 面對 3-bet 決策表
#   池子特性：3-bet 範圍窄且線性（價值為主）、面對 4-bet 很少棄真正的價值牌、翻後不會用空氣加注。
#   → 4-bet 只用 QQ+/AK（AKo 被 5-bet 全下時視對手：對 VPIP<25 的 reg 棄，對魚跟）。
#   → 跟注要靠「有位置」與「能中大牌」：IP 才跟同花連牌與中對子；OOP 只跟 JJ/TT/AQs。
#   → 小對子 22–66 不管在哪裡一律棄（隱含賠率不夠，抽水高）。
# ---------------------------------------------------------------------------
VS3B_TIERS = {
    # 我在早位/中位開池，被後面的非盲注位置 3-bet（對手範圍最緊）
    "oop_tight": {
        "4bet": "QQ+, AKs, AKo",
        "call": "JJ, TT, AQs",
        "note": "對手在你後面 3-bet 而且不是盲注：這是池子最緊的 3-bet 範圍（多為 JJ+/AQs+）。99 以下、AJs、KQs 都棄；AQo 也棄。",
    },
    # 我在 MP/CO 開池，被 BTN 3-bet（BTN 3-bet 稍寬，但我還是 OOP）
    "oop_btn": {
        "4bet": "QQ+, AKs, AKo",
        "call": "JJ, TT, 99, AQs, AJs, KQs",
        "note": "BTN 的 3-bet 比早位寬一點，可以多跟 99、AJs、KQs，但你是 OOP，翻後沒中頂對以上就放棄，不要 check-call 兩條街。",
    },
    # 我在 UTG/MP 開池，被 SB/BB 3-bet（我 IP，但盲注對早位 3-bet 偏緊）
    "ip_blinds_early": {
        "4bet": "QQ+, AKs, AKo",
        "call": "JJ, TT, 99, 88, AQs, AJs, KQs, JTs, T9s, AQo",
        "note": "盲注對早位開池的 3-bet 也偏緊，但你有位置，可以跟中對子與同花大牌看翻牌。翻後對手 c-bet 過高但轉牌棄牌多，浮動一次是有利的。",
    },
    # 我在 CO/BTN 開池，被 SB/BB 3-bet（我 IP，盲注對後位 3-bet 最寬）
    "ip_blinds_late": {
        "4bet": "QQ+, AKs, AKo",
        "call": "JJ-66, AQs-ATs, KQs, KJs, QJs, JTs, T9s, 98s, A5s-A4s, AQo, KQo",
        "note": "盲注面對後位偷盲的 3-bet 最寬，你 IP 可以跟最多牌。66/77 靠中 set，A5s/A4s 靠位置與可玩性；55 以下與其他同花連牌還是棄（抽水高）。",
    },
    # 我在 SB 開池，被 BB 3-bet（OOP，但 BB 的 3-bet 範圍寬）
    "sb_vs_bb": {
        "4bet": "QQ+, AKs, AKo, AQs",
        "call": "JJ-77, AJs, ATs, KQs, KJs, AQo",
        "note": "BB 對 SB 開池的 3-bet 最寬，可以把 AQs 也拿來 4-bet 價值。跟注後你 OOP，只用頂對＋以上繼續；小同花連牌全部棄，因為翻後沒有位置很難實現權益。",
    },
}

POS_ORDER = ["UTG", "MP", "CO", "BTN", "SB", "BB"]


def vs3b_tier(hero_pos, villain_pos):
    """Return tier key for hero opening at hero_pos and being 3-bet by villain_pos."""
    if hero_pos == "SB":
        return "sb_vs_bb"
    if villain_pos in ("SB", "BB"):
        return "ip_blinds_early" if hero_pos in ("UTG", "MP") else "ip_blinds_late"
    if villain_pos == "BTN":
        return "oop_tight" if hero_pos == "UTG" else "oop_btn"
    return "oop_tight"


def vs3b_pairs():
    """All (hero_pos, villain_pos) combos where villain acts after hero."""
    out = []
    for i, hp in enumerate(POS_ORDER[:-1]):
        for vp in POS_ORDER[i + 1:]:
            out.append((hp, vp))
    return out


def open_chart(pos):
    hands = parse_range(OPEN[pos])
    return {"pos": pos, "range": sorted(hands, key=lambda h: (RANKS.index(h[0]), RANKS.index(h[1]))),
            "pct": range_pct(hands), "note": OPEN_NOTES[pos],
            "action": {h: ("open" if h in hands else "fold") for h in all169()}}


def vs3b_chart(hero_pos, villain_pos):
    tier = vs3b_tier(hero_pos, villain_pos)
    t = VS3B_TIERS[tier]
    four = parse_range(t["4bet"])
    call = parse_range(t["call"]) - four
    opn = parse_range(OPEN[hero_pos])
    act = {}
    for h in all169():
        if h not in opn:
            act[h] = "na"  # 不在開池範圍內，不會遇到這個情境
        elif h in four:
            act[h] = "4bet"
        elif h in call:
            act[h] = "call"
        else:
            act[h] = "fold"
    n_open = sum(combos(h) for h in opn)
    n_cont = sum(combos(h) for h in opn if h in four or h in call)
    return {"hero": hero_pos, "villain": villain_pos, "tier": tier, "note": t["note"],
            "four_pct": round(100.0 * sum(combos(h) for h in opn if h in four) / n_open, 1),
            "call_pct": round(100.0 * sum(combos(h) for h in opn if h in call) / n_open, 1),
            "fold_pct": round(100.0 * (n_open - n_cont) / n_open, 1),
            "action": act}


# ---------------------------------------------------------------------------
# 面對開池（前面剛好一次加注、中間沒人跟注）的決策表：3-bet / call / fold
#   池子特性：面對 3-bet 棄牌 63%，所以盲注位的詐唬 3-bet（A5s-A2s 這類）是有利的；
#   對手 c-bet 過高但轉牌棄牌多 → 有位置跟注（IP）比 OOP 跟注值錢很多；
#   SB 不要平跟（OOP + 後面還有 BB），3-bet 或棄；BB 面對後位開池要多守。
# ---------------------------------------------------------------------------
VSOPEN_TIERS = {
    "ip_vs_early": {  # 我在 MP/CO/BTN，面對 UTG/MP 開池
        "3bet": "QQ+, AKs, AKo, AQs",
        "call": "JJ-55, AJs, ATs, KQs, KJs, QJs, JTs, T9s, 98s, AQo",
        "note": "早位開池範圍緊（約 13–19%），3-bet 只用 QQ+/AK/AQs 打價值；有位置可以用中對子與同花大牌跟注看翻牌（對手 c-bet 多、轉牌棄得多，浮動一次有利）。AJo/KQo 直接棄。",
    },
    "ip_vs_late": {  # 我在 BTN 面對 CO 開池（或 CO 面對 MP 偷盲）
        "3bet": "TT+, AQs+, AJs, KQs, A5s-A4s, AQo+",
        "call": "99-22, ATs-A6s, KJs, KTs, QJs, QTs, JTs, T9s, 98s, 87s, 76s, AJo, KQo",
        "note": "後位開池範圍寬，3-bet 價值範圍放寬到 TT+/AJs+/AQo+，加 A5s/A4s 當詐唬（對手棄 3-bet 63%）。有位置可以跟很多牌，但翻後沒中就放棄。",
    },
    "sb_vs_early": {  # 我在 SB 面對 UTG/MP 開池
        "3bet": "TT+, AJs+, KQs, AQo+, A5s-A4s",
        "call": "",
        "note": "SB 面對早位開池：3-bet 或棄，不要平跟（OOP 而且後面還有 BB 可能 squeeze）。價值 TT+/AJs+/AQo+，A5s/A4s 少量詐唬。",
    },
    "sb_vs_late": {  # 我在 SB 面對 CO/BTN 開池
        "3bet": "77+, ATs+, KJs+, QJs, JTs, AJo+, KQo, A5s-A2s",
        "call": "",
        "note": "SB 對後位偷盲：3-bet 或棄。對手偷盲寬、棄 3-bet 高，所以 77+/ATs+/AJo+ 都能 3-bet 價值，A5s-A2s 當詐唬。被 4-bet 時除了 QQ+/AK 全棄。",
    },
    "bb_vs_early": {  # 我在 BB 面對 UTG/MP 開池
        "3bet": "QQ+, AKs, AKo",
        "call": "JJ-22, AQs-A2s, K9s+, Q9s+, J9s+, T8s+, 97s+, 86s+, 75s+, 65s, 54s, AQo, AJo, KQo",
        "note": "BB 已經投了 1bb，面對早位 2.5bb 開池只要再補 1.5bb 就能看翻牌，整體守約 19%（3-bet 2.6% + 跟注 16%）；但 3-bet 只用 QQ+/AK，因為早位開池不會棄什麼。",
    },
    "bb_vs_late": {  # 我在 BB 面對 CO/BTN 開池
        "3bet": "TT+, AQs+, AJs, KQs, AQo+, A5s-A2s",
        "call": "99-22, ATs-A6s, K2s+, Q6s+, J7s+, T7s+, 96s+, 85s+, 75s+, 64s+, 54s, ATo+, K9o+, Q9o+, J9o+, T9o",
        "note": "這是你之前守得太緊的位置。對後位偷盲要守約 33%（3-bet 6.5% + 跟注 26%）：TT+/AQ+ 3-bet 價值、A5s-A2s 詐唬 3-bet，其他同花牌與 ATo+/K9o+ 跟注。翻後沒中頂對或聽牌就 check-fold，不要跟 c-bet 太多。",
    },
    "bb_vs_sb": {  # 我在 BB 面對 SB 開池
        "3bet": "99+, ATs+, KJs+, QJs, AJo+, KQo, A5s-A2s",
        "call": "88-22, A9s-A6s, K2s+, Q5s+, J6s+, T6s+, 95s+, 85s+, 74s+, 64s+, 53s+, A5o+, K9o+, Q9o+, J9o+, T9o, 98o",
        "note": "SB 開池最寬而且你有位置（翻後 IP），整體守約 40%（3-bet 10% + 跟注 30%）：99+/ATs+/AJo+ 價值、A5s-A2s 詐唬；其他可玩的牌都跟注。",
    },
}


def vsopen_tier(hero_pos, villain_pos):
    """hero_pos 面對 villain_pos 的開池。villain 必須在 hero 前面行動。"""
    early = villain_pos in ("UTG", "MP")
    if hero_pos == "BB":
        if villain_pos == "SB":
            return "bb_vs_sb"
        return "bb_vs_early" if early else "bb_vs_late"
    if hero_pos == "SB":
        return "sb_vs_early" if early else "sb_vs_late"
    # hero in MP/CO/BTN, in position
    return "ip_vs_early" if early else "ip_vs_late"


def vsopen_pairs():
    out = []
    for i, hp in enumerate(POS_ORDER):
        for vp in POS_ORDER[:i]:
            out.append((hp, vp))
    return out


def vsopen_chart(hero_pos, villain_pos):
    tier = vsopen_tier(hero_pos, villain_pos)
    t = VSOPEN_TIERS[tier]
    three = parse_range(t["3bet"])
    call = parse_range(t["call"]) - three if t["call"] else set()
    act = {}
    for h in all169():
        act[h] = "3bet" if h in three else "call" if h in call else "fold"
    n3 = sum(combos(h) for h in three)
    nc = sum(combos(h) for h in call)
    return {"hero": hero_pos, "villain": villain_pos, "tier": tier, "note": t["note"],
            "three_pct": round(100.0 * n3 / 1326, 1), "call_pct": round(100.0 * nc / 1326, 1),
            "fold_pct": round(100.0 * (1326 - n3 - nc) / 1326, 1), "action": act}


# ---------------------------------------------------------------------------
# 我 3-bet 之後被 4-bet：5-bet 全下 / 跟注 / 棄牌
#   池子的 4-bet 幾乎純價值（QQ+/AK），所以 5-bet 全下只用 AA/KK；
#   QQ/AK 用跟的（IP 可以多跟 JJ/AQs 看翻牌），3-bet 詐唬牌（A5s-A2s 等）一律棄。
#   對 VPIP 40%+ 的魚可以把 QQ/AK 也拿來 5-bet 全下。
# ---------------------------------------------------------------------------
VS4B_TIERS = {
    "ip_vs4b": {
        "5bet": "KK+",
        "call": "QQ, JJ, AKs, AKo, AQs",
        "note": "你有位置。對手 4-bet 幾乎是 QQ+/AK：AA/KK 直接 5-bet 全下；QQ/JJ/AK/AQs 跟注看翻牌（沒中超對或頂對就放）；A5s-A2s、TT 以下、KQs 這些 3-bet 牌全部棄。對魚（VPIP 40%+）QQ/AK 也可以全下。",
    },
    "oop_vs4b": {
        "5bet": "KK+",
        "call": "QQ, AKs, AKo",
        "note": "你沒有位置，能跟 4-bet 的更少：AA/KK 5-bet 全下，QQ/AK 跟注，其他全棄（JJ、AQs 在 OOP 跟 4-bet 是虧的）。對魚 QQ/AK 也可以全下。",
    },
}


def vs4b_tier(hero_pos, villain_pos):
    """hero 在 hero_pos 3-bet villain_pos 的開池後被 4-bet；IP＝hero 在 villain 之後行動且不是盲注對後位。"""
    hi, vi = POS_ORDER.index(hero_pos), POS_ORDER.index(villain_pos)
    # 翻後順序：SB、BB 最先，UTG…BTN 依序；BB vs SB 是 hero IP
    if hero_pos in ("SB", "BB"):
        return "ip_vs4b" if (hero_pos == "BB" and villain_pos == "SB") else "oop_vs4b"
    return "ip_vs4b" if hi > vi else "oop_vs4b"


def vs4b_chart(hero_pos, villain_pos):
    tier = vs4b_tier(hero_pos, villain_pos)
    t = VS4B_TIERS[tier]
    three = parse_range(VSOPEN_TIERS[vsopen_tier(hero_pos, villain_pos)]["3bet"])
    five = parse_range(t["5bet"])
    call = parse_range(t["call"]) - five
    act = {}
    for h in all169():
        if h not in three:
            act[h] = "na"
        elif h in five:
            act[h] = "5bet"
        elif h in call:
            act[h] = "call"
        else:
            act[h] = "fold"
    n3 = sum(combos(h) for h in three) or 1
    n5 = sum(combos(h) for h in three if h in five)
    nc = sum(combos(h) for h in three if h in call)
    return {"hero": hero_pos, "villain": villain_pos, "tier": tier, "note": t["note"],
            "five_pct": round(100.0 * n5 / n3, 1), "call_pct": round(100.0 * nc / n3, 1),
            "fold_pct": round(100.0 * (n3 - n5 - nc) / n3, 1), "action": act}


def all_charts():
    return {
        "open": {p: open_chart(p) for p in OPEN},
        "vs3b": {f"{h}-{v}": vs3b_chart(h, v) for h, v in vs3b_pairs()},
        "vsopen": {f"{h}-{v}": vsopen_chart(h, v) for h, v in vsopen_pairs()},
        "vs4b": {f"{h}-{v}": vs4b_chart(h, v) for h, v in vsopen_pairs()},
    }


if __name__ == "__main__":
    for p in OPEN:
        print(p, range_pct(parse_range(OPEN[p])), "%")
    for h, v in vs3b_pairs():
        c = vs3b_chart(h, v)
        print(h, "vs", v, c["tier"], "4bet", c["four_pct"], "call", c["call_pct"], "fold", c["fold_pct"])
