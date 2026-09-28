"""
GGPoker (Rush & Cash / cash game) hand history parser.

Produces one dict per hand:
{
  hand_id, table, game, sb, bb, played_at (ISO), button_seat, max_players,
  board (list), total_pot, rake, jackpot, run_times,
  hero_seat, hero_cards, hero_net,
  players: {name: {seat, stack, position, cards, net, invested, collected,
                    cashout_risk, ...street flags...}},
  actions: [(street, order, player, action, amount, total, all_in)]
}
"""
import re
from datetime import datetime

try:
    from equity import equity as calc_equity
except Exception:  # pragma: no cover
    calc_equity = None

STREETS = ("preflop", "flop", "turn", "river")

RE_HEADER = re.compile(
    r"^Poker Hand #(?P<id>[A-Z0-9]+): (?P<game>.+?) \(\$(?P<sb>[\d.]+)/\$(?P<bb>[\d.]+)\) - (?P<dt>\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})"
)
RE_TABLE = re.compile(r"^Table '(?P<table>[^']+)' (?P<max>\d+)-max Seat #(?P<btn>\d+) is the button")
RE_SEAT = re.compile(r"^Seat (?P<seat>\d+): (?P<name>\S+) \(\$(?P<stack>[\d.]+) in chips\)")
RE_POST = re.compile(r"^(?P<name>\S+): posts (?P<kind>small blind|big blind|straddle|ante|missed blind|the ante)\s*\$(?P<amt>[\d.]+)")
RE_DEALT = re.compile(r"^Dealt to (?P<name>\S+)\s*(?:\[(?P<cards>[^\]]+)\])?")
RE_ACTION = re.compile(
    r"^(?P<name>\S+): (?P<act>folds|checks|calls|bets|raises)"
    r"(?: \$(?P<a1>[\d.]+))?(?: to \$(?P<a2>[\d.]+))?(?P<allin> and is all-in)?"
)
RE_UNCALLED = re.compile(r"^Uncalled bet \(\$(?P<amt>[\d.]+)\) returned to (?P<name>\S+)")
RE_COLLECT = re.compile(r"^(?P<name>\S+) collected \$(?P<amt>[\d.]+) from pot")
RE_SHOWS = re.compile(r"^(?P<name>\S+): shows \[(?P<cards>[^\]]+)\]")
RE_STREET = re.compile(r"^\*\*\* (?P<name>[A-Z ]+?) \*\*\*(?: \[(?P<b1>[^\]]+)\])?(?: \[(?P<b2>[^\]]+)\])?")
RE_SUMMARY_POT = re.compile(r"^Total pot \$(?P<pot>[\d.]+)(?: \| Rake \$(?P<rake>[\d.]+))?(?: \| Jackpot \$(?P<jp>[\d.]+))?")
RE_CASHOUT_RISK = re.compile(r"^(?P<name>\S+): Pays Cashout Risk \(\$(?P<amt>[\d.]+)\)")
RE_RUN_TIMES = re.compile(r"^Hand was run (?P<n>\w+) times")
RE_CASH_DROP = re.compile(r"^Cash Drop to Pot ?: total \$(?P<amt>[\d.]+)")
RE_SUMMARY_SEAT = re.compile(r"^Seat (?P<seat>\d+): (?P<name>\S+)(?: \((?P<pos>button|small blind|big blind)\))? (?P<rest>.*)")
RE_SUMMARY_CARDS = re.compile(r"(?:showed|mucked) \[(?P<cards>[^\]]+)\]")

WORD_NUM = {"two": 2, "three": 3, "four": 4}


def _f(x):
    return float(x) if x else 0.0


def _r(x):
    return round(x + 1e-9, 2)


def position_names(n_players, button_seat, seats_in_order):
    """
    seats_in_order: list of seat numbers of players dealt in, in table order.
    Returns {seat: position} using standard 6-max naming.
    Order after button: SB, BB, UTG, MP(HJ), CO ... , BTN.
    """
    if not seats_in_order:
        return {}
    idx = seats_in_order.index(button_seat) if button_seat in seats_in_order else 0
    order = seats_in_order[idx + 1:] + seats_in_order[:idx + 1]  # SB first ... BTN last
    n = len(order)
    if n == 2:
        names = ["SB", "BB"]  # heads-up: button posts SB
        # in HU, button is SB; order[0] is the non-button
        return {order[0]: "BB", order[1]: "SB"}
    tail = {6: ["UTG", "MP", "CO", "BTN"], 5: ["UTG", "CO", "BTN"], 4: ["UTG", "BTN"], 3: ["BTN"]}
    if n > 6:
        mids = ["UTG", "UTG+1", "MP", "MP+1", "HJ", "CO"][: n - 3] + ["BTN"]
        names = ["SB", "BB"] + mids
    else:
        names = ["SB", "BB"] + tail.get(n, ["BTN"])
    return {s: names[i] for i, s in enumerate(order)}


def parse_hand(text):
    lines = [l.rstrip("\r") for l in text.strip().split("\n")]
    if not lines:
        return None
    m = RE_HEADER.match(lines[0])
    if not m:
        return None
    hand = {
        "hand_id": m.group("id"),
        "game": m.group("game"),
        "sb": _f(m.group("sb")),
        "bb": _f(m.group("bb")),
        "played_at": datetime.strptime(m.group("dt"), "%Y/%m/%d %H:%M:%S").strftime("%Y-%m-%d %H:%M:%S"),
        "table": "",
        "max_players": 6,
        "button_seat": 0,
        "board": [],
        "total_pot": 0.0,
        "rake": 0.0,
        "jackpot": 0.0,
        "run_times": 1,
        "cash_drop": 0.0,
        "hero_seat": None,
        "hero_cards": None,
        "hero_net": 0.0,
        "hero_ev_net": 0.0,
        "hero_equity": None,
        "allin_street": "",
        "players": {},
        "actions": [],
    }
    players = hand["players"]
    actions = hand["actions"]
    street = "preflop"
    order = 0
    # per-street betting state
    street_bet = {}  # name -> amount committed this street
    aggressor = {"preflop": None, "flop": None, "turn": None, "river": None}
    pf_raises = 0
    pf_raiser_seq = []  # sequence of raisers preflop
    seats_dealt = []

    def P(name):
        if name not in players:
            players[name] = {
                "seat": 0, "stack": 0.0, "position": "", "cards": None,
                "invested": 0.0, "collected": 0.0, "cashout_risk": 0.0, "net": 0.0,
                "vpip": 0, "pfr": 0, "saw_flop": 0, "saw_showdown": 0, "won_showdown": 0,
                "won_hand": 0, "won_sd_money": 0,
                "three_bet_opp": 0, "three_bet": 0, "faced_three_bet": 0, "fold_to_three_bet": 0,
                "cbet_opp": 0, "cbet": 0, "faced_cbet": 0, "fold_to_cbet": 0,
                "pf_calls": 0, "pf_raises": 0,
                "agg_bets": 0, "agg_raises": 0, "agg_calls": 0,
                "walk": 0, "steal_opp": 0, "steal": 0,
                "fold_street": "",
                "pot_type": "", "pf_role": "", "pf_first": "", "pf_faced": -1, "ip": -1, "flop_players": 0,
                "flop_strength": "", "flop_line": "", "turn_line": "", "river_line": "", "ev_net": 0.0,
            }
        return players[name]

    for line in lines[1:]:
        if not line.strip():
            continue
        mt = RE_TABLE.match(line)
        if mt:
            hand["table"] = mt.group("table")
            hand["max_players"] = int(mt.group("max"))
            hand["button_seat"] = int(mt.group("btn"))
            continue
        ms = RE_STREET.match(line)
        if ms:
            name = ms.group("name")
            b1, b2 = ms.group("b1"), ms.group("b2")
            if name in ("FLOP", "FIRST FLOP"):
                street = "flop"
                hand["board"] = b1.split()
            elif name in ("TURN", "FIRST TURN"):
                street = "turn"
                hand["board"] = b1.split() + b2.split()
            elif name in ("RIVER", "FIRST RIVER"):
                street = "river"
                hand["board"] = b1.split() + b2.split()
            elif name.startswith("SECOND") or name.startswith("THIRD"):
                # extra run-outs: no betting, ignore board
                street = "runout"
            elif name in ("SHOWDOWN", "FIRST SHOWDOWN", "SECOND SHOWDOWN", "THIRD SHOWDOWN"):
                street = "showdown"
            elif name == "SUMMARY":
                street = "summary"
            elif name == "HOLE CARDS":
                street = "preflop"
            if street in ("flop", "turn", "river"):
                street_bet = {}
            continue

        if street == "summary":
            mp = RE_SUMMARY_POT.match(line)
            if mp:
                hand["total_pot"] = _f(mp.group("pot"))
                hand["rake"] = _f(mp.group("rake"))
                hand["jackpot"] = _f(mp.group("jp"))
                continue
            mr = RE_RUN_TIMES.match(line)
            if mr:
                hand["run_times"] = WORD_NUM.get(mr.group("n"), 1)
                continue
            mss = RE_SUMMARY_SEAT.match(line)
            if mss:
                name = mss.group("name")
                if name in players:
                    mc = RE_SUMMARY_CARDS.search(mss.group("rest"))
                    if mc and not players[name]["cards"]:
                        players[name]["cards"] = mc.group("cards")
            continue

        mcd = RE_CASH_DROP.match(line)
        if mcd:
            hand["cash_drop"] = _f(mcd.group("amt"))
            continue
        mseat = RE_SEAT.match(line)
        if mseat:
            p = P(mseat.group("name"))
            p["seat"] = int(mseat.group("seat"))
            p["stack"] = _f(mseat.group("stack"))
            seats_dealt.append(p["seat"])
            continue
        mpost = RE_POST.match(line)
        if mpost:
            p = P(mpost.group("name"))
            amt = _f(mpost.group("amt"))
            p["invested"] += amt
            street_bet[mpost.group("name")] = street_bet.get(mpost.group("name"), 0) + amt
            continue
        md = RE_DEALT.match(line)
        if md:
            name = md.group("name")
            if md.group("cards"):
                p = P(name)
                p["cards"] = md.group("cards")
                if name == "Hero":
                    hand["hero_cards"] = md.group("cards")
            continue
        ma = RE_ACTION.match(line)
        if ma and street in ("preflop", "flop", "turn", "river"):
            name, act = ma.group("name"), ma.group("act")
            a1, a2 = _f(ma.group("a1")), _f(ma.group("a2"))
            allin = 1 if ma.group("allin") else 0
            p = P(name)
            amount = 0.0
            total = 0.0
            if act == "calls":
                amount = a1
                street_bet[name] = street_bet.get(name, 0) + a1
                total = street_bet[name]
            elif act == "bets":
                amount = a1
                street_bet[name] = street_bet.get(name, 0) + a1
                total = street_bet[name]
            elif act == "raises":
                # "raises $X to $Y": Y is the total this street
                total = a2
                amount = a2 - street_bet.get(name, 0)
                street_bet[name] = a2
            if amount:
                p["invested"] += amount
            order += 1
            actions.append((street, order, name, act, _r(amount), _r(total), allin))

            # ---- stat flags ----
            if street == "preflop":
                # 機會旗標要用「行動前」的加注次數判斷（否則自己 3-bet / 4-bet 時會漏算機會）
                # 3-bet opportunity: facing exactly one raise, not the raiser
                if pf_raises == 1 and name != pf_raiser_seq[0]:
                    p["three_bet_opp"] = 1
                # facing a 3-bet: you were the first raiser and now 2 raises exist and it's your turn
                if pf_raises == 2 and pf_raiser_seq and name == pf_raiser_seq[0]:
                    p["faced_three_bet"] = 1
                    if act == "folds":
                        p["fold_to_three_bet"] = 1
                if act in ("calls", "raises"):
                    p["vpip"] = 1
                if act == "calls":
                    p["pf_calls"] += 1
                if act == "raises":
                    p["pfr"] = 1
                    p["pf_raises"] += 1
                    pf_raises += 1
                    pf_raiser_seq.append(name)
                    aggressor["preflop"] = name
                    if pf_raises == 2:
                        p["three_bet"] = 1
            else:
                if act == "bets":
                    aggressor[street] = name
                    p["agg_bets"] += 1
                elif act == "raises":
                    aggressor[street] = name
                    p["agg_raises"] += 1
                elif act == "calls":
                    p["agg_calls"] += 1
                if street == "flop":
                    pfa = aggressor["preflop"]
                    flop_bets_so_far = [a for a in actions if a[0] == "flop" and a[3] in ("bets", "raises")]
                    if name == pfa and pfa and not [a for a in flop_bets_so_far if a[2] != name]:
                        # PFR acting on flop with no bet before them
                        if len(flop_bets_so_far) == 0 or (len(flop_bets_so_far) == 1 and flop_bets_so_far[0][2] == name and act == "bets"):
                            if p["cbet_opp"] == 0:
                                p["cbet_opp"] = 1
                                if act == "bets":
                                    p["cbet"] = 1
                    elif pfa and pfa != name and players.get(pfa, {}).get("cbet") and p["faced_cbet"] == 0:
                        # first response to the c-bet
                        if len([a for a in flop_bets_so_far]) == 1:
                            p["faced_cbet"] = 1
                            if act == "folds":
                                p["fold_to_cbet"] = 1
            if act == "folds":
                p["fold_street"] = street
            continue
        mu = RE_UNCALLED.match(line)
        if mu:
            p = P(mu.group("name"))
            p["invested"] -= _f(mu.group("amt"))
            continue
        mc = RE_COLLECT.match(line)
        if mc:
            p = P(mc.group("name"))
            p["collected"] += _f(mc.group("amt"))
            p["won_hand"] = 1
            continue
        msh = RE_SHOWS.match(line)
        if msh:
            p = P(msh.group("name"))
            p["cards"] = msh.group("cards")
            p["saw_showdown"] = 1
            continue
        mcr = RE_CASHOUT_RISK.match(line)
        if mcr:
            p = P(mcr.group("name"))
            p["cashout_risk"] += _f(mcr.group("amt"))
            continue
        # ignore everything else (Chooses to EV Cashout, mucks, etc.)

    # ---- post-processing ----
    pos = position_names(len(seats_dealt), hand["button_seat"], sorted(seats_dealt))
    folded_pre = {n for n, p in players.items() if p["fold_street"] == "preflop"}
    reached_sd = {n for n, p in players.items() if p["saw_showdown"]}
    # players who didn't fold and hand went to showdown are also at showdown (mucked)
    went_to_showdown = any(p["saw_showdown"] for p in players.values())
    for name, p in players.items():
        p["position"] = pos.get(p["seat"], "")
        p["net"] = _r(p["collected"] - p["invested"] - p["cashout_risk"])
        p["invested"] = _r(p["invested"])
        p["collected"] = _r(p["collected"])
        if p["fold_street"] not in ("preflop",) and hand["board"]:
            # saw flop if they didn't fold preflop and a flop was dealt
            p["saw_flop"] = 1
        if went_to_showdown and p["fold_street"] == "" and p["saw_flop"]:
            p["saw_showdown"] = 1
        if p["saw_showdown"] and p["collected"] > 0:
            p["won_showdown"] = 1
        if p["saw_flop"] and p["collected"] > 0:
            p["won_sd_money"] = 1  # WWSF numerator
        if name == "Hero":
            hand["hero_seat"] = p["seat"]
            hand["hero_net"] = p["net"]
    # steal: first-in raise from CO/BTN/SB with everyone before folded
    first_action = None
    for a in actions:
        if a[0] != "preflop":
            break
        if a[3] in ("calls", "raises", "bets"):
            first_action = a
            break
    if first_action:
        n = first_action[2]
        if players[n]["position"] in ("CO", "BTN", "SB"):
            players[n]["steal_opp"] = 1
            if first_action[3] == "raises":
                players[n]["steal"] = 1
    else:
        # everyone folded to BB: walk
        for n, p in players.items():
            if p["position"] == "BB":
                p["walk"] = 1
    # Also mark steal opportunity for CO/BTN/SB who folded first-in
    for a in actions:
        if a[0] != "preflop":
            break
        n = a[2]
        if a[3] == "folds" and players[n]["position"] in ("CO", "BTN", "SB") and first_action is not None and a[1] < first_action[1]:
            players[n]["steal_opp"] = 1
        elif a[3] == "folds" and players[n]["position"] in ("CO", "BTN", "SB") and first_action is None:
            players[n]["steal_opp"] = 1

    # ---- scenario classification (pot type / preflop role / first action / IP / flop players) ----
    pre = [a for a in actions if a[0] == "preflop"]
    n_raises = 0
    limpers = 0
    last_aggr = None
    for a in pre:
        name, act = a[2], a[3]
        p = players[name]
        if p["pf_first"] == "":
            p["pf_faced"] = n_raises
            if act == "raises":
                if n_raises == 0:
                    p["pf_first"] = "open" if limpers == 0 else "iso"
                elif n_raises == 1:
                    p["pf_first"] = "3bet"
                elif n_raises == 2:
                    p["pf_first"] = "4bet"
                else:
                    p["pf_first"] = "5bet+"
            elif act == "calls":
                if n_raises == 0:
                    p["pf_first"] = "limp"
                elif n_raises == 1:
                    p["pf_first"] = "call"
                elif n_raises == 2:
                    p["pf_first"] = "call3bet"
                else:
                    p["pf_first"] = "call4bet+"
            elif act == "folds":
                p["pf_first"] = "fold"
            elif act == "checks":
                p["pf_first"] = "check"
        if act == "raises":
            n_raises += 1
            last_aggr = name
        elif act == "calls" and n_raises == 0:
            limpers += 1
    hand["pf_raises"] = n_raises
    pot_type = {0: "LIMP", 1: "SRP", 2: "3BP"}.get(n_raises, "4BP+")
    hand["pot_type"] = pot_type
    flop_players = [n for n, p in players.items() if p["saw_flop"]]
    hand["flop_players"] = len(flop_players)
    # IP: among players who saw the flop, the one who acts last (closest to button going backwards)
    ip_name = None
    if flop_players:
        order = sorted(seats_dealt)
        bi = order.index(hand["button_seat"]) if hand["button_seat"] in order else 0
        ring = order[bi + 1:] + order[:bi + 1]  # SB ... BTN
        by_seat = {p["seat"]: n for n, p in players.items()}
        for s in reversed(ring):
            if by_seat.get(s) in flop_players:
                ip_name = by_seat[s]
                break
    for name, p in players.items():
        p["pot_type"] = pot_type
        if p["pf_first"] == "":
            p["pf_first"] = "walk" if p["walk"] else "none"
        if p["fold_street"] == "preflop":
            p["pf_role"] = "fold"
        elif name == last_aggr:
            p["pf_role"] = "raiser"
        elif p["vpip"]:
            p["pf_role"] = "caller"
        else:
            p["pf_role"] = "bb_check" if p["walk"] or n_raises == 0 else "none"
        if p["saw_flop"]:
            p["ip"] = 1 if name == ip_name else 0
        else:
            p["ip"] = -1
        p["flop_players"] = len(flop_players)
        if p["saw_flop"] and p["cards"] and len(hand["board"]) >= 3:
            p["flop_strength"] = flop_strength(p["cards"], hand["board"][:3])
            p["flop_line"] = flop_line([a for a in actions if a[0] == "flop" and a[2] == name])
            p["turn_line"] = flop_line([a for a in actions if a[0] == "turn" and a[2] == name])
            p["river_line"] = flop_line([a for a in actions if a[0] == "river" and a[2] == name])
        p["ev_net"] = p["net"]
    hand["hero_ev_net"] = hand["hero_net"]
    _allin_ev(hand)
    return hand


def _allin_ev(hand):
    """If the hand ended with an all-in before the river and all live hands are known,
    compute equity-adjusted net (All-in EV) for every live player."""
    if calc_equity is None or not hand["actions"]:
        return
    last_street = hand["actions"][-1][0]
    if last_street not in ("preflop", "flop", "turn"):
        return
    street_acts = [a for a in hand["actions"] if a[0] == last_street]
    if not any(a[6] for a in street_acts):
        return
    live = [(n, p) for n, p in hand["players"].items() if p["fold_street"] == "" and p["invested"] > 0]
    if len(live) < 2 or any(not p["cards"] for _, p in live):
        return
    if "Hero" not in [n for n, _ in live]:
        return
    known = {"preflop": 0, "flop": 3, "turn": 4}[last_street]
    board = hand["board"][:known]
    if len(hand["board"]) < 5:
        return  # hand not fully dealt (shouldn't happen)
    hands = [p["cards"].split() for _, p in live]
    try:
        eqs = calc_equity(hands, board)
    except Exception:
        return
    total_collected = sum(p["collected"] for p in hand["players"].values())
    for (n, p), eq in zip(live, eqs):
        p["ev_net"] = _r(eq * total_collected - p["invested"] - p["cashout_risk"])
        if n == "Hero":
            hand["hero_equity"] = round(eq, 4)
            hand["hero_ev_net"] = p["ev_net"]
    hand["allin_street"] = last_street


RANK_ORDER = "23456789TJQKA"
ACT_SHORT = {"checks": "check", "calls": "call", "bets": "bet", "raises": "raise", "folds": "fold"}


def flop_line(acts):
    """Player's own flop actions -> 'check-call', 'check-raise', 'bet', 'call', 'raise', 'fold', ..."""
    if not acts:
        return ""
    names = [ACT_SHORT.get(a[3], a[3]) for a in acts]
    return "-".join(names[:2])


def flop_strength(cards, board):
    """Classify a 2-card hand on a 3-card flop. Returns one label."""
    hs = cards.split()
    if len(hs) != 2:
        return ""
    hr = [RANK_ORDER.index(c[0]) for c in hs]
    br = [RANK_ORDER.index(c[0]) for c in board]
    hsu = [c[1] for c in hs]
    bsu = [c[1] for c in board]
    allr = hr + br
    cnt = {}
    for r in allr:
        cnt[r] = cnt.get(r, 0) + 1
    bcnt = {}
    for r in br:
        bcnt[r] = bcnt.get(r, 0) + 1
    pocket = hr[0] == hr[1]
    top = max(br)
    # flush / straight
    flush = len(set(bsu)) == 1 and hsu[0] == hsu[1] == bsu[0]
    rs = set(allr) | ({-1} if 12 in allr else set())
    straight = any(all(x in rs for x in range(s, s + 5)) for s in range(-1, 9))
    quads = any(c == 4 for c in cnt.values())
    fh = any(c >= 3 for c in cnt.values()) and any(c == 2 for c in cnt.values())
    if quads or fh:
        return "fullhouse+"
    if flush:
        return "flush"
    if straight:
        return "straight"
    trips = [r for r, c in cnt.items() if c == 3]
    if trips:
        if pocket and hr[0] in trips:
            return "set"
        if bcnt.get(trips[0], 0) == 3:
            return "board_trips"
        return "trips"
    pair_ranks = [r for r, c in cnt.items() if c == 2 and (r in hr)]
    hole_pairs = [r for r in pair_ranks if not pocket or True]
    # draws
    fd = hsu[0] == hsu[1] and bsu.count(hsu[0]) == 2
    outs_sets = 0
    for x in range(-1, 9):
        need = [v for v in range(x, x + 5) if v not in rs]
        if len(need) == 1 and need[0] not in br and need[0] >= -1:
            outs_sets += 1
    oesd = outs_sets >= 2
    gut = outs_sets == 1
    if not pocket and len(pair_ranks) >= 2:
        return "two_pair"
    if pocket:
        if hr[0] > top:
            return "combo_draw" if fd else "overpair"
        # pocket below top card
        if fd or oesd:
            return "combo_draw"
        return "underpair"
    if pair_ranks:
        r = pair_ranks[0]
        kind = "top_pair" if r == top else ("mid_pair" if r > min(br) else "weak_pair")
        if fd or oesd:
            return "combo_draw"
        return kind
    if fd and (oesd or gut):
        return "combo_draw"
    if fd:
        return "flush_draw"
    if oesd:
        return "oesd"
    if gut:
        return "gutshot"
    if min(hr) > top:
        return "overcards"
    return "air"


def split_hands(text):
    text = text.replace("\r\n", "\n")
    chunks = re.split(r"\n(?=Poker Hand #)", text)
    return [c for c in chunks if c.strip().startswith("Poker Hand #")]


def parse_file(path):
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        text = f.read()
    hands = []
    errors = 0
    for chunk in split_hands(text):
        try:
            h = parse_hand(chunk)
            if h:
                hands.append(h)
            else:
                errors += 1
        except Exception:
            errors += 1
    return hands, errors


if __name__ == "__main__":
    import sys, json
    total, err = 0, 0
    net = 0.0
    for p in sys.argv[1:]:
        hs, e = parse_file(p)
        total += len(hs)
        err += e
        net += sum(h["hero_net"] for h in hs)
    print("hands", total, "errors", err, "hero_net", round(net, 2))
