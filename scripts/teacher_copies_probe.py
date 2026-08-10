"""Where does the teacher's 3-star progress go? Doc 99 entry 102.

101 measured the *field* (`GreedyPolicy`): untargeted archetypes reach a 3-star
in 0.33% of games against a real 34.5%, peaking at 5.9-6.6 copy-equivalents
where a 3-star needs 9. The teacher is a different code path and was not
measured, and the teacher is what matters -- it is the imitation ceiling, and
lesson 16 says improving it is the only lever that has ever moved the clone.

The two sell rules disagree, which is entry 86's recurring defect:

* `GreedyPolicy._sell_surplus` protects reroll targets and nothing else.
* the teacher (`rl/evaluate.py`) additionally guards `_copies_owned < 2`, so it
  keeps two copies sitting at the same star level.

Neither protects the case that actually compounds: a **single 1-star of a
champion already held at 2-star**. That copy is the start of the second pair a
3-star needs, and it looks like the weakest unit on the bench, so it is exactly
what a "sell the weakest surplus" rule reaches for first.

Reported per episode:

* 3-stars reached, by cost
* peak copy-equivalents (a 2-star counts 4, a 3-star 9; the bar is 9)
* **progress-breaking sells**: selling a 1-star while holding a 2-star of the
  same champion, which is the mechanism above, counted directly rather than
  inferred from the ceiling.

    .venv/bin/python scripts/teacher_copies_probe.py --episodes 30
"""

from __future__ import annotations

import argparse
import statistics
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from engine.loader import load_all  # noqa: E402
from rl.env import TFTEnv  # noqa: E402
from rl.evaluate import scripted_policy  # noqa: E402
from rl.opponents import STRATEGIES  # noqa: E402

TEACHER = {
    "sell_bench": True,
    "buy_synergy": True,
    "match_items": True,
    "corner_carry": True,
}


def _unit_at_slot(env, player, slot: int):
    """The unit a SELL action targets, board hex or bench index."""
    space = env.action_space_helper
    bench_index = space.bench_index_for_slot(slot)
    if bench_index is not None:
        return player.bench[bench_index]
    hex_ = space.hex_for_slot(slot)
    return player.board.get(hex_) if hex_ is not None else None


def copy_equivalents(player) -> Counter:
    counts: Counter = Counter()
    for unit in player.all_units:
        counts[unit.champion.id] += 3 ** (unit.star_level - 1)
    return counts


def run(data, episodes: int, econ_name: str | None, keep_pairs: int = 0) -> dict:
    econ = STRATEGIES[econ_name] if econ_name else None
    env = TFTEnv(data=data)
    policy = scripted_policy(env, econ=econ, keep_pairs=keep_pairs, **TEACHER)

    peaks: list[int] = []
    three_stars: Counter = Counter()
    episodes_with_three = 0
    breaking_sells = 0
    total_sells = 0

    for episode in range(episodes):
        obs, _info = env.reset(seed=episode)
        peak = 0
        seen: set[int] = set()
        while True:
            mask = env.action_masks()
            action = int(policy(obs, mask))
            decoded = env.action_space_helper.decode(action)
            player = env.player

            if decoded.kind.name == "SELL":
                total_sells += 1
                # Read the unit actually being sold, not merely whether the
                # seat holds a matching pair somewhere: an earlier version
                # checked the latter and over-counted.
                sold = _unit_at_slot(env, player, decoded.a)
                if sold is not None and sold.star_level == 1 and any(
                    u.champion.id == sold.champion.id and u.star_level == 2
                    for u in player.all_units
                ):
                    breaking_sells += 1

            peak = max(peak, max(copy_equivalents(player).values(), default=0))
            for unit in player.all_units:
                if unit.star_level == 3:
                    seen.add(unit.champion.cost)

            obs, _r, term, trunc, _i = env.step(action)
            if term or trunc:
                break

        peaks.append(peak)
        if seen:
            episodes_with_three += 1
            for cost in seen:
                three_stars[cost] += 1

    return {
        "episodes": episodes,
        "peaks": peaks,
        "three_stars": three_stars,
        "episodes_with_three": episodes_with_three,
        "breaking_sells": breaking_sells,
        "total_sells": total_sells,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episodes", type=int, default=30)
    parser.add_argument("--econ", default="standard")
    parser.add_argument("--keep-pairs", type=int, default=0)
    args = parser.parse_args()

    result = run(load_all(), args.episodes, args.econ or None, args.keep_pairs)
    n = result["episodes"]
    peaks = result["peaks"]
    print(f"teacher, econ={args.econ}, keep_pairs={args.keep_pairs}, {n} episodes\n")
    print(f"  episodes reaching any 3-star : {result['episodes_with_three']}/{n} "
          f"= {result['episodes_with_three'] / n:.1%}")
    print(f"  by cost                      : {dict(sorted(result['three_stars'].items()))}")
    print(f"  peak copy-equivalents        : mean {statistics.mean(peaks):.2f}, "
          f"max {max(peaks)}  (a 3-star needs 9)")
    print(f"  distribution                 : {sorted(Counter(peaks).items())}")
    share = (result["breaking_sells"] / result["total_sells"]
             if result["total_sells"] else 0.0)
    print(f"  progress-breaking sells      : {result['breaking_sells']}"
          f"/{result['total_sells']} = {share:.1%}")
    print("\n  real challenger, any 3-star: 34.5% of seats (doc 99 entry 97.5)")


if __name__ == "__main__":
    main()
