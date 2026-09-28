"""
Hold'em hand evaluator + all-in equity calculator (pure Python, no deps).

evaluate7(cards) -> comparable tuple (higher is better)
equity(hands, board, samples=None) -> list of equities (fractions summing to 1)
  hands: list of 2-card lists e.g. [['Ah','Kd'], ['Qs','Qc']]
  board: 0-5 known board cards
  Exact enumeration when remaining cards <= 2 (flop / turn all-in),
  Monte Carlo otherwise (preflop).
"""
import itertools
import random

RANKS = "23456789TJQKA"
RV = {r: i + 2 for i, r in enumerate(RANKS)}
FULL_DECK = [r + s for r in RANKS for s in "shdc"]


def evaluate7(cards):
    """Return a tuple ranking for the best 5-card hand among 5-7 cards."""
    ranks = sorted((RV[c[0]] for c in cards), reverse=True)
    suits = {}
    for c in cards:
        suits.setdefault(c[1], []).append(RV[c[0]])
    # flush?
    flush_ranks = None
    for s, rs in suits.items():
        if len(rs) >= 5:
            flush_ranks = sorted(rs, reverse=True)
            break

    def straight_high(rs):
        u = sorted(set(rs), reverse=True)
        if 14 in u:
            u.append(1)
        run = 1
        for i in range(1, len(u)):
            if u[i] == u[i - 1] - 1:
                run += 1
                if run >= 5:
                    return u[i] + 4
            else:
                run = 1
        return 0

    if flush_ranks:
        sh = straight_high(flush_ranks)
        if sh:
            return (8, sh)
    counts = {}
    for r in ranks:
        counts[r] = counts.get(r, 0) + 1
    groups = sorted(counts.items(), key=lambda x: (x[1], x[0]), reverse=True)
    if groups[0][1] == 4:
        kick = max(r for r in ranks if r != groups[0][0])
        return (7, groups[0][0], kick)
    if groups[0][1] == 3 and len(groups) > 1 and groups[1][1] >= 2:
        return (6, groups[0][0], groups[1][0])
    if flush_ranks:
        return (5,) + tuple(flush_ranks[:5])
    sh = straight_high(ranks)
    if sh:
        return (4, sh)
    if groups[0][1] == 3:
        kick = [r for r in ranks if r != groups[0][0]][:2]
        return (3, groups[0][0]) + tuple(kick)
    if groups[0][1] == 2 and len(groups) > 1 and groups[1][1] == 2:
        kick = max(r for r in ranks if r != groups[0][0] and r != groups[1][0])
        return (2, groups[0][0], groups[1][0], kick)
    if groups[0][1] == 2:
        kick = [r for r in ranks if r != groups[0][0]][:3]
        return (1, groups[0][0]) + tuple(kick)
    return (0,) + tuple(ranks[:5])


def equity(hands, board, samples=None, seed=1):
    n = len(hands)
    used = set(board)
    for h in hands:
        used.update(h)
    deck = [c for c in FULL_DECK if c not in used]
    need = 5 - len(board)
    wins = [0.0] * n
    total = 0

    def score(full_board):
        vals = [evaluate7(h + full_board) for h in hands]
        best = max(vals)
        winners = [i for i, v in enumerate(vals) if v == best]
        share = 1.0 / len(winners)
        for i in winners:
            wins[i] += share

    if need <= 0:
        score(list(board))
        total = 1
    elif need <= 2 and samples is None:
        for combo in itertools.combinations(deck, need):
            score(list(board) + list(combo))
            total += 1
    else:
        rng = random.Random(seed)
        k = samples or 6000
        for _ in range(k):
            combo = rng.sample(deck, need)
            score(list(board) + combo)
        total = k
    return [w / total for w in wins]


if __name__ == "__main__":
    print(equity([["Ah", "Kd"], ["Qs", "Qc"]], []))
    print(equity([["Ah", "Kd"], ["Qs", "Qc"]], ["Ac", "7d", "2s"]))
    print(equity([["Ah", "Kd"], ["Qs", "Qc"], ["9h", "8h"]], ["Th", "7h", "2s", "3c"]))
