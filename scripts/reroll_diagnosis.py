"""Why is slow-rolling unplayable here? (doc 99 entry 85)

Entry 84's econ table re-derived the archetypes against the fair field:

| econ | placement |
|---|---|
| standard | 4.213 |
| fast8 | 4.337 |
| hyperroll | 4.877 |
| **slowroll6** | **6.077** |

Slow-rolling at level 6 is a mainstream, entirely viable real-TFT line. Here it
places **1.863 worse than standard** (t=+14.89) and worse than having no
economy at all. That is a fidelity claim, not an agent one: an agent trained
here learns reroll lines are traps, which is false of the game being modelled.

Entry 76 looked at this and concluded combat prices stars correctly (76.1
verified the star-vs-slot exchange rate) and that the shortfall is a gold
budget. A 1.863 gap is large enough to want the mechanism rather than the
category, and three times this session an "engine is broken" conclusion turned
out to be a policy *definition* -- so the first thing to rule out is that
`SLOWROLL6` is simply a badly written plan.

Profiles both economies round by round in the agent seat against the same
field, on shared seeds. The discriminating questions:

* **does it get its 3-stars, and when?** 73 measured 100% of games reaching
  one; if they land at 4-5 the game is already decided.
* **does it survive to spend them?** Slow-rolling trades early HP for later
  board strength. Real TFT accepts that trade because the payoff arrives in
  time. If HP hits zero first, the plan is fine and the *timeline* is wrong.
* **is it gold-starved or unit-starved?** Rolling to a 50 floor from 3-2 either
  converts gold into units or it does not.

    .venv/bin/python scripts/reroll_diagnosis.py --episodes 120 --workers 10
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rl.timing import timed  # noqa: E402

_W: dict = {}

TEACHER = {
    "sell_bench": True,
    "buy_synergy": True,
    "match_items": True,
    "corner_carry": True,
}


def _init(econ_name: str) -> None:
    import logging

    from engine.loader import load_all
    from rl.env import TFTEnv
    from rl.evaluate import scripted_policy
    from rl.opponents import STRATEGIES

    logging.getLogger("engine.loader").setLevel(logging.ERROR)
    data = load_all()
    env = TFTEnv(data=data)
    _W["env"] = env
    _W["policy"] = scripted_policy(env, econ=STRATEGIES[econ_name], **TEACHER)


def _episode(seed: int):
    """One game, sampling the agent's state once per round while it is alive."""
    env, policy = _W["env"], _W["policy"]
    obs, _info = env.reset(seed=seed)
    rows = []
    seen = set()
    placement = None
    for _ in range(20_000):
        label = str(env.match.round_id)
        player = env.player
        # Sample once per round, and only while alive -- a dead seat holds no
        # units, and averaging those in reads as "reroll has no 3-stars" when
        # it means "reroll is dead" (the vacuous-zero trap of entry 73).
        if label not in seen and player.alive:
            seen.add(label)
            units = list(player.board.values())
            rows.append({
                "round": label,
                "hp": player.hp,
                "gold": player.gold,
                "level": player.level,
                "board": len(units),
                "three_star": sum(1 for u in units if u.star_level >= 3),
                "two_star": sum(1 for u in units if u.star_level == 2),
                "value": sum(u.champion.cost * u.star_level for u in units),
            })
        obs, _r, term, trunc, info = env.step(policy(obs, env.action_masks()))
        if term or trunc:
            placement = info.get("placement")
            break
    return placement, rows


def run(econ_name: str, seeds, workers):
    context = mp.get_context("spawn")
    with context.Pool(processes=workers, initializer=_init,
                      initargs=(econ_name,)) as pool:
        out = list(pool.imap_unordered(_episode, list(seeds)))
    placements = [p for p, _ in out if p is not None]
    by_round = defaultdict(list)
    for _p, rows in out:
        for row in rows:
            by_round[row["round"]].append(row)
    return placements, by_round


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episodes", type=int, default=120)
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--econs", nargs="+", default=["standard", "slowroll6"])
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args()

    seeds = list(range(args.episodes))
    results = {}
    with timed("reroll_diagnosis", episodes=args.episodes,
               arms=len(args.econs), workers=args.workers):
        for econ in args.econs:
            placements, by_round = run(econ, seeds, args.workers)
            results[econ] = (placements, by_round)
            print(f"  {econ:<12}{statistics.mean(placements):.3f}", flush=True)

    labels = sorted(
        {label for _p, by in results.values() for label in by},
        key=lambda s: tuple(int(x) for x in s.split("-")),
    )

    print(f"\n{'round':<8}", end="")
    for econ in args.econs:
        print(f"{econ[:9]:>42}", end="")
    print()
    print(f"{'':<8}", end="")
    for _ in args.econs:
        print(f"{'alive':>7}{'hp':>7}{'gold':>7}{'lvl':>6}{'brd':>6}{'3*':>9}", end="")
    print()

    for label in labels:
        print(f"{label:<8}", end="")
        for econ in args.econs:
            rows = results[econ][1].get(label, [])
            if not rows:
                print(f"{'-':>42}", end="")
                continue
            alive = len(rows) / args.episodes
            print(
                f"{alive:>7.0%}"
                f"{statistics.mean(r['hp'] for r in rows):>7.1f}"
                f"{statistics.mean(r['gold'] for r in rows):>7.1f}"
                f"{statistics.mean(r['level'] for r in rows):>6.1f}"
                f"{statistics.mean(r['board'] for r in rows):>6.1f}"
                f"{statistics.mean(r['three_star'] for r in rows):>9.2f}",
                end="",
            )
        print()

    print("\n`alive` is the share of games still running at that round, so a "
          "column that\nfalls away early is dying rather than teching up. `3*` "
          "is the mean count of\n3-star units *among surviving seats*, which is "
          "the number the reroll plan\nexists to produce.")

    if args.json:
        args.json.write_text(json.dumps(
            {econ: {"placements": p,
                    "by_round": {k: v for k, v in by.items()}}
             for econ, (p, by) in results.items()}, indent=1))
        print(f"\nper-round rows: {args.json}")


if __name__ == "__main__":
    main()
