"""Price the budget: can a seat afford to level *and* hit? (doc 99 entry 120)

Entry 119.4 found that across six `commit_level` / `pivot_at` variants, 1-cost
3-stars and end level trade off monotonically -- the engine can hit or it can
level, never both -- while real seats do both: 0.271 three-stars at level 8.26,
placing 4.43.

That is a statement about a *budget*, and a budget is arithmetic, not
simulation. This script totals what a seat earns against what levelling and
rolling cost, using only the constants in `data/config.json`. If the two do not
reconcile, one of those constants is wrong, and the residual says which.

Every constant involved is `community_documented` rather than Riot-published
(see the provenance block in `data/config.json`), so an error here is entirely
possible and has never been checked.

    .venv/bin/python scripts/economy_budget.py
    .venv/bin/python scripts/economy_budget.py --measure --games 60

`--measure` adds the engine's *observed* per-seat gold ledger, which tests the
arithmetic itself: if the analytic income ceiling and the engine disagree, the
model below is wrong and nothing downstream of it means anything.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.loader import load_all  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Reference targets from the real-match sample (doc 99 entries 111, 119).
REAL_END_LEVEL = 8.26
REAL_C1_THREE_STARS = 0.271
REAL_PLACEMENT = 4.43


def rounds_up_to(cfg: dict, stage: int, rnd: int) -> list[tuple[int, int]]:
    """Every round played from 1-1 through (stage, rnd) inclusive."""
    rs = cfg["round_structure"]
    out: list[tuple[int, int]] = []
    for s in range(1, stage + 1):
        last = rs["rounds_per_stage"] if s > 1 else rs["stage_one_rounds"]
        for r in range(1, last + 1):
            if s == stage and r > rnd:
                break
            out.append((s, r))
    return out


def base_income(cfg: dict, stage: int, rnd: int) -> int:
    """The ramp overrides the flat base for the rounds it names."""
    ramp = cfg["income_ramp"]
    key = f"{stage}-{rnd}"
    if key in ramp:
        return int(ramp[key])
    # The ramp's last entry is the point the flat rate takes over; anything
    # earlier than the first entry has not been named, which only happens if
    # the table is edited, so fall through to the base either way.
    return int(cfg["base_income"])


@dataclass
class Income:
    base: int
    interest: int
    streak: int
    wins: int

    @property
    def total(self) -> int:
        return self.base + self.interest + self.streak + self.wins


def income_over(cfg: dict, played: list[tuple[int, int]], *,
                max_interest: bool, streaking: bool, winning: bool) -> Income:
    """Total gold earned across `played`.

    `max_interest` is the ceiling assumption and is *not* free: holding 50 gold
    for interest is exactly the gold a reroll seat is trying to spend. Reported
    separately so the conflict stays visible.
    """
    cap = int(cfg["interest_cap"])
    best_streak = max(bonus for _, bonus in cfg["streak_bonus"])
    base = sum(base_income(cfg, s, r) for s, r in played)
    n = len(played)
    return Income(
        base=base,
        interest=cap * n if max_interest else 0,
        streak=best_streak * n if streaking else 0,
        wins=int(cfg["pvp_win_gold"]) * n if winning else 0,
    )


def xp_cost_to_level(cfg: dict, level: int, played: int) -> tuple[int, int]:
    """(gold spent buying XP, XP still missing) to reach `level`.

    Passive XP accrues every round played; the rest is bought at
    `xp_purchase_gold` per `xp_purchase_amount`.
    """
    table = cfg["xp_to_next_level"]
    needed = sum(int(table[str(lv)]) for lv in range(1, level))
    passive = int(cfg["passive_xp_per_round"]) * played
    short = max(0, needed - passive)
    per_gold = int(cfg["xp_purchase_amount"]) / int(cfg["xp_purchase_gold"])
    return round(short / per_gold), short


def copies_per_roll(cfg: dict, level: int, cost: int, champs_at_cost: int,
                    *, contested: float = 0.0) -> float:
    """Expected copies of one *named* champion per reroll.

    `contested` is the fraction of *that champion's* copies already held by
    other seats, the rest of the pool being fresh. Uniform depletion across
    every champion is deliberately not modelled: it cancels out of the share
    exactly, so it cannot change this number and pretending otherwise would
    make the parameter read as a correction it is not.
    """
    odds = cfg["shop_odds"][str(level)][cost - 1]
    pool = int(cfg["pool_sizes"][str(cost)])
    mine = pool * (1.0 - contested)
    share = mine / (mine + pool * (champs_at_cost - 1))
    return int(cfg["shop_slots"]) * odds * share


def gold_for_three_star(cfg: dict, level: int, cost: int, champs_at_cost: int,
                        *, contested: float = 0.0) -> tuple[float, float]:
    """(gold, rolls) to assemble 9 copies of one named champion from zero."""
    per_roll = copies_per_roll(cfg, level, cost, champs_at_cost,
                               contested=contested)
    rolls = 9 / per_roll
    return rolls * int(cfg["reroll_cost"]) + 9 * cost, rolls


def report(cfg: dict, counts: dict[int, int], *, stage: int, rnd: int,
           level: int) -> None:
    played = rounds_up_to(cfg, stage, rnd)
    n = len(played)
    print(f"\n=== budget through {stage}-{rnd} ({n} rounds), target level "
          f"{level} ===")

    floor = income_over(cfg, played, max_interest=False, streaking=False,
                        winning=False)
    ceil = income_over(cfg, played, max_interest=True, streaking=True,
                       winning=True)
    print(f"  income floor (base only)          {floor.total:6d}g")
    print(f"  income ceiling (max int+streak+win){ceil.total:6d}g"
          f"   [base {ceil.base}, interest {ceil.interest}, "
          f"streak {ceil.streak}, wins {ceil.wins}]")

    xp_gold, short = xp_cost_to_level(cfg, level, n)
    print(f"  XP to level {level}: {short} xp short of passive "
          f"-> {xp_gold}g")

    for cost, label in ((1, "1-cost"), (3, "3-cost")):
        # Roll at the level a reroll seat actually sits at for that cost.
        roll_level = 5 if cost == 1 else 7
        gold, rolls = gold_for_three_star(cfg, roll_level, cost, counts[cost])
        print(f"  one {label} 3-star at level {roll_level}: "
              f"{rolls:5.1f} rolls, {gold:6.0f}g")

    gold, _ = gold_for_three_star(cfg, 5, 1, counts[1])
    need = xp_gold + gold
    print(f"  --> level {level} AND one 1-cost 3-star: {need:.0f}g needed")
    for name, inc in (("floor", floor), ("ceiling", ceil)):
        slack = inc.total - need
        verdict = "fits" if slack >= 0 else "SHORT"
        print(f"      vs income {name:7s} {inc.total:5d}g: "
              f"{slack:+6.0f}g  {verdict}")


_STANDARD_CURVE = {"2-5": 5, "3-2": 6, "4-1": 7, "4-5": 8, "5-5": 9}


def curve_target(now: tuple[int, int]) -> int:
    """The STANDARD level curve, as a plain function of the round."""
    best = 4
    for key, level in _STANDARD_CURVE.items():
        s, r = (int(x) for x in key.split("-"))
        if (s, r) <= now:
            best = max(best, level)
    return best


def ledger(cfg: dict, counts: dict[int, int], *, rolldown: tuple[int, int],
           through: tuple[int, int], bank: int = 50,
           streaking: bool = False, winning: bool = True) -> dict:
    """Round-by-round gold for a seat that banks, then rolls down.

    This is the whole point of the exercise. The endpoint totals above compare
    a seat's income against a *sum* of costs, which lets it spend the same gold
    twice: interest is only earned on gold that has not been rolled. Walking
    the rounds prices the schedule instead, so banking and rolling compete for
    the same coin the way they actually do.

    Before `rolldown` the seat buys XP toward the STANDARD curve but never
    breaks `bank`; from `rolldown` on it stops levelling and rolls to zero.
    """
    cap = int(cfg["interest_cap"])
    per_gold = int(cfg["xp_purchase_amount"]) / int(cfg["xp_purchase_gold"])
    xp_table = cfg["xp_to_next_level"]
    streak = max(b for _, b in cfg["streak_bonus"]) if streaking else 0
    win = int(cfg["pvp_win_gold"]) if winning else 0

    gold, xp, level, rolls, copies = 0, 0, 1, 0, 0.0
    # P(9 copies) is not `copies / 9`. Nine copies of *one named* champion are
    # needed, so the right statistic is a tail probability, and at these counts
    # the two differ by an order of magnitude: 4.87 expected copies reads as
    # 0.54 three-stars linearly and ~0.03 as a tail. Each shop slot is an
    # independent trial at p ~ 0.01, varying only with level, so the copy count
    # is Poisson-binomial and Poisson(total expected copies) approximates it
    # closely enough for an order-of-magnitude budget question.
    for now in rounds_up_to(cfg, *through):
        # The free shop every round is copies the seat sees without paying.
        copies += copies_per_roll(cfg, level, 1, counts[1])
        gold += base_income(cfg, *now) + min(gold // 10, cap) + streak + win
        xp += int(cfg["passive_xp_per_round"])
        while level < int(cfg["max_level"]) and xp >= int(xp_table[str(level)]):
            xp -= int(xp_table[str(level)])
            level += 1

        if now < rolldown:
            want = curve_target(now)
            while level < want and gold - int(cfg["xp_purchase_gold"]) >= bank:
                gold -= int(cfg["xp_purchase_gold"])
                xp += int(per_gold * int(cfg["xp_purchase_gold"]))
                while (level < int(cfg["max_level"])
                       and xp >= int(xp_table[str(level)])):
                    xp -= int(xp_table[str(level)])
                    level += 1
        else:
            while gold >= int(cfg["reroll_cost"]):
                gold -= int(cfg["reroll_cost"])
                rolls += 1
                copies += copies_per_roll(cfg, level, 1, counts[1])

    return {"level": level, "rolls": rolls, "copies": copies,
            "three_stars": poisson_tail(copies, 9), "gold_left": gold}


def poisson_tail(mean: float, at_least: int) -> float:
    """P(X >= at_least) for X ~ Poisson(mean)."""
    term = math.exp(-mean)
    below = term
    for k in range(1, at_least):
        term *= mean / k
        below += term
    return max(0.0, 1.0 - below)


def frontier(cfg: dict, counts: dict[int, int]) -> None:
    """Sweep the roll-down round: does the *arithmetic* reach the real corner?

    Entry 119.4 found the engine cannot hit and level at once. If this table
    shows the same wall, the constants forbid it and the engine's policy is
    exonerated; if the table clears the corner the engine cannot, the shortfall
    is policy, not economy.
    """
    print("\n=== arithmetic frontier: bank to X, then roll down (through 5-7)"
          " ===")
    print(f"{'rolldown':>9} {'end lvl':>8} {'rolls':>6} {'c1 copies':>10} "
          f"{'P(3-star)':>11}")
    schedule = [(2, 1), (3, 1), (3, 5), (4, 1), (4, 3), (4, 5), (5, 1),
                (5, 5), (9, 9)]
    for rd in schedule:
        row = ledger(cfg, counts, rolldown=rd, through=(5, 7))
        label = "never" if rd == (9, 9) else f"{rd[0]}-{rd[1]}"
        print(f"{label:>9} {row['level']:8d} {row['rolls']:6d} "
              f"{row['copies']:10.2f} {row['three_stars']:11.3f}")
    print(f"{'real':>9} {REAL_END_LEVEL:8.2f} {'--':>6} {'--':>10} "
          f"{REAL_C1_THREE_STARS:11.3f}")


def measure(games: int, seed: int) -> None:
    """The engine's observed ledger, as a check on the arithmetic above.

    Reports gold *earned* and rerolls *taken* per seat. The arithmetic is only
    worth reading if the engine's income matches it; and the reroll count is
    the quantity the frontier above claims is affordable, so the two tables
    answer the same question from opposite ends.
    """
    from engine import player as player_mod
    from rl.action import ActionKind
    from rl.env import TFTEnv
    from rl.evaluate import scripted_policy
    from rl.opponents import HYPERROLL, STANDARD

    # Instrument the grant itself rather than watching `player.gold`. A naive
    # inflow counter credits unit sales, carousel gold and augment payouts too,
    # and reads 558g against an analytic ceiling of 434 -- an apparent economy
    # bug that is entirely the measurement. `award_income` is also the only
    # hook that can tell the agent's seat from the seven opponents', which all
    # earn through the same call.
    tally: dict[str, int] = {}
    watched: list[object] = []
    real_award = player_mod.PlayerState.award_income

    def counting_award(self, *a, **kw):
        got = real_award(self, *a, **kw)
        if watched and self is watched[0]:
            for part in ("base", "interest", "streak", "win_bonus"):
                tally[part] = tally.get(part, 0) + getattr(got, part)
        return got

    player_mod.PlayerState.award_income = counting_award

    # The other half of the ledger. Income alone cannot distinguish a seat that
    # *cannot* afford to roll from one that spends the same gold on XP and
    # units, and those two diagnoses point at opposite fixes.
    real_xp = player_mod.PlayerState.buy_xp

    def counting_xp(self, *a, **kw):
        if watched and self is watched[0]:
            tally["-xp"] = tally.get("-xp", 0) - self.config.xp_purchase_gold
        return real_xp(self, *a, **kw)

    player_mod.PlayerState.buy_xp = counting_xp

    cfg = json.loads((DATA_DIR / "config.json").read_text())
    data = load_all(DATA_DIR)
    for econ in (STANDARD, HYPERROLL):
        tally.clear()
        levels: list[int] = []
        rerolls: list[int] = []
        rounds: list[int] = []
        unspent: list[int] = []
        for g in range(games):
            env = TFTEnv(data=data)
            policy = scripted_policy(env, econ=econ, sell_bench=True,
                                     buy_synergy=True, match_items=True,
                                     corner_carry=True)
            obs, _info = env.reset(seed=seed + g)
            watched[:] = [env.player]   # the match, and so the seat, exists
                                        # only after reset
            rolled = 0
            for _ in range(20000):
                index = int(policy(obs, env.action_masks()))
                if env.action_space_helper.decode(index).kind is ActionKind.REROLL:
                    rolled += 1
                obs, _r, term, trunc, _i = env.step(index)
                if term or trunc:
                    break
            levels.append(env.player.level)
            rerolls.append(rolled)
            unspent.append(env.player.gold)
            rid = env.match.round_id
            rounds.append(len(rounds_up_to(cfg, rid.stage, rid.round)))
        income = {k: v for k, v in tally.items() if not k.startswith("-")}
        total = sum(income.values()) / games
        roll_gold = statistics.mean(rerolls) * int(cfg["reroll_cost"])
        xp_gold = -tally.get("-xp", 0) / games
        left = statistics.mean(unspent)
        print(f"\n=== engine, {games} games, {econ.name} seat ===")
        print(f"  income per game       {total:7.1f}   "
              + ", ".join(f"{k} {v / games:.1f}"
                          for k, v in sorted(income.items())))
        print(f"  spent on rerolls      {roll_gold:7.1f}  "
              f"({statistics.mean(rerolls):.1f} rolls)")
        print(f"  spent on XP           {xp_gold:7.1f}")
        print(f"  unspent at death      {left:7.1f}")
        print(f"  residual (units, net of sales) "
              f"{total - roll_gold - xp_gold - left:7.1f}")
        print(f"  rounds survived       {statistics.mean(rounds):7.1f}")
        print(f"  end level             {statistics.mean(levels):7.2f}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--measure", action="store_true",
                    help="also run the engine and report its observed ledger")
    ap.add_argument("--games", type=int, default=40)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    cfg = json.loads((DATA_DIR / "config.json").read_text())
    data = load_all(DATA_DIR)
    counts: dict[int, int] = {}
    for champ in data.champions.values():
        counts[champ.cost] = counts.get(champ.cost, 0) + 1

    print(f"reference (real matches): level {REAL_END_LEVEL}, "
          f"{REAL_C1_THREE_STARS} 1-cost 3-stars/seat, "
          f"placement {REAL_PLACEMENT}")
    print(f"champions per cost: {dict(sorted(counts.items()))}")

    # A seat placing 4.43 dies mid-stage-5; 5-1 and 5-7 bracket it.
    for stage, rnd, level in ((4, 7, 8), (5, 1, 8), (5, 7, 8), (6, 1, 9)):
        report(cfg, counts, stage=stage, rnd=rnd, level=level)

    frontier(cfg, counts)

    if args.measure:
        measure(args.games, args.seed)


if __name__ == "__main__":
    main()
