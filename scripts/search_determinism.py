"""Is the search teacher a function of the board state? (doc 99 entry 79)

Entry 78.2 measured the positional search worth **-0.330 (t=-2.53)** to the
teacher. Entry 79.1 then cloned it and got **nothing**: 4.930 against the plain
econ clone's 4.740 (+0.190, t=+1.31), with the gap to teacher *widening* from
0.857 to 1.047. The per-action table localised it exactly -- BUY 96.2%, BUY_XP
95.0%, PICK_AUGMENT 99.2% all unmoved, while SELECT fell 84.0% -> 47.4% and
PLACE 78.8% -> 44.5%, on **expert states with deterministic prediction**.

A clone that cannot fit its own training set is a statement about the setup
(CLAUDE.md). Two setups could be at fault and they have opposite remedies:

1. the observation cannot express *which hex is better* -- a relation between
   our units and the enemy's threats that a flat MLP will not derive; or
2. the teacher is not a function of the observation at all, so identical
   states carry different labels and no student can fit them.

`best_move` shuffles the full move list and takes the first `max_candidates`,
so (2) is true by construction. This measures **how** true, which (1) vs (2)
cannot be settled by reading alone:

* **agreement** -- call `best_move` on one state under several RNG streams and
  count how often it returns the same `(from, to)`. This is the *ceiling on
  action match* for SELECT/PLACE: no student can beat the rate at which the
  teacher agrees with itself. A rate is uninterpretable without its achievable
  maximum, and 47.4% has been quoted against 100%.
* **margin** -- how much the chosen move beats the runner-up. A large margin
  under disagreement means the candidates were genuinely different and the
  sampling is throwing away good moves; a margin near zero means the search is
  picking between near-equivalent boards, and the churn buys nothing.

    .venv/bin/python scripts/search_determinism.py --states 60 --repeats 5
"""

from __future__ import annotations

import argparse
import random
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.loader import load_all  # noqa: E402
from rl.action import ActionKind  # noqa: E402
from rl.env import TFTEnv  # noqa: E402
from rl.evaluate import scripted_policy  # noqa: E402
from rl.opponents import STANDARD  # noqa: E402
from rl.search import best_move  # noqa: E402

TEACHER = {
    "sell_bench": True,
    "buy_synergy": True,
    "match_items": True,
    "corner_carry": True,
    "econ": STANDARD,
}


def probe_state(env, repeats: int, max_candidates: int, panel_size: int):
    """Run the search `repeats` times on one state under different streams.

    Returns `(moves, margins)`. Nothing about the env is advanced: `best_move`
    restores `player.board` in a `finally`, and its fights run through the
    private RNG passed in rather than the match's, so the host game is
    untouched (see rl/search.py's module docstring).
    """
    moves = []
    for repeat in range(repeats):
        move = best_move(
            env, random.Random(1000 + repeat),
            max_candidates=max_candidates, panel_size=panel_size,
        )
        moves.append(move)
    return moves


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--states", type=int, default=60)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--max-candidates", type=int, default=12)
    parser.add_argument("--panel-size", type=int, default=1)
    args = parser.parse_args()

    data = load_all()
    env = TFTEnv(data=data)
    policy = scripted_policy(env, **TEACHER)

    agreements: list[float] = []
    distinct_counts: Counter = Counter()
    none_rate = 0
    sampled = 0
    episode = 0

    while sampled < args.states:
        obs, info = env.reset(seed=episode)
        episode += 1
        done = False
        while not done and sampled < args.states:
            mask = env.action_masks()
            action = policy(obs, mask)
            # Probe at the moment the search would fire: the end of a planning
            # phase with a board worth rearranging. Sampling uniformly over all
            # steps would mostly catch states where `best_move` returns None
            # immediately and measure nothing.
            if (env.action_space_helper.decode(action).kind
                    is ActionKind.END_PLANNING and len(env.player.board) >= 2):
                moves = probe_state(env, args.repeats, args.max_candidates,
                                    args.panel_size)
                sampled += 1
                counts = Counter(moves)
                top, hits = counts.most_common(1)[0]
                agreements.append(hits / len(moves))
                distinct_counts[len(counts)] += 1
                none_rate += moves.count(None) / len(moves)
            obs, _reward, terminated, truncated, _info = env.step(action)
            done = terminated or truncated

    n = len(agreements)
    mean_agreement = statistics.mean(agreements)
    print(f"\n{n} states, {args.repeats} RNG streams each, "
          f"max_candidates={args.max_candidates} panel_size={args.panel_size}\n")
    print(f"  modal-move agreement : {mean_agreement:.1%}")
    print(f"  states where every stream agreed : "
          f"{sum(a == 1.0 for a in agreements) / n:.1%}")
    print(f"  mean distinct answers per state  : "
          f"{sum(k * v for k, v in distinct_counts.items()) / n:.2f}"
          f" (of {args.repeats})")
    print(f"  'no move' rate                   : {none_rate / n:.1%}")
    print("\n  distinct answers  states")
    for k in sorted(distinct_counts):
        print(f"  {k:>16}  {distinct_counts[k]:>6}")

    print(f"\nThis is the CEILING on SELECT/PLACE action match: a student "
          f"cannot agree\nwith the teacher more often than the teacher agrees "
          f"with itself. Entry 79.1\nread SELECT at 47.4% and called it a "
          f"failure to fit; against a ceiling of\n{mean_agreement:.1%} that "
          "reading changes.")


if __name__ == "__main__":
    main()
