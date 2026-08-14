"""Is there signal at *round* granularity, where there is none per action?

129 closed the reward question: a single micro-action does not move final
placement (entry 91, max |t| = 1.82) and does not move the **next fight** either
(1072 deviations, t = 0.95). 129.3 located the cause in the action space rather
than the reward -- the clone's own alternatives are near-equivalent, so no
outcome variable can separate them.

129.4's one remaining lever is granularity: make each decision a whole round's
board rather than one of ~400 micro-actions. 129.5 asked for the cheapest
possible test of that -- **measure the signal before training anything.**

So this is 129's probe with the *decision* coarsened instead of the outcome.
The coarse policy available today is the scripted teacher wrapped in
`search_policy(mode="board")`, whose `best_board` commits to a whole board once
per planning phase. The counterfactual: suppress that one round's board decision
(falling back to the base policy's board, which is itself a legitimate policy
output -- not a random board, which would measure something else, the trap
entry 91 documents), then measure the HP lost in that round's fight.

Both branches replay from the same seed and differ only in one round's board.
Placement actions draw nothing from the match RNG, so the combat seed is
identical across branches and the comparison is exactly paired.

Named outcomes, before the run:

* **A -- granularity is the answer.** One round's board decision moves that
  round's fight measurably (|t| well past 2) where a micro-action does not.
  Then a coarse action space is worth building and RL has a concrete path.
* **B -- nothing here either.** Then it is not granularity, and the honest
  conclusion is that this domain's per-decision signal is unrecoverable at any
  granularity from self-play alone -- which would close the RL direction the way
  128 closed fidelity.
* **C -- signal, but only where the search fires.** `best_board` returns None
  unless it beats the baseline by `margin`, so it changes few rounds. A large
  effect on a small subset is still a usable signal, but it says the lever is
  *which rounds matter*, not granularity as such.

Anchor: entry 106 measured this search worth **0.527 placement** over a whole
game. If a single round's application is undetectable while the game-long effect
is 0.527, that itself locates how the value accumulates.

    .venv/bin/python scripts/round_decision_credit.py --episodes 300
"""

from __future__ import annotations

import argparse
import hashlib
import math
import multiprocessing as mp
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rl.timing import timed  # noqa: E402

_W: dict = {}


def source_fingerprint() -> str:
    digest = hashlib.sha256()
    for name in ("rl/evaluate.py", "rl/env.py", "rl/search.py"):
        digest.update(Path(name).read_bytes())
    return digest.hexdigest()[:12]


def _init() -> None:
    import logging

    from engine.loader import load_all

    logging.getLogger("engine.loader").setLevel(logging.ERROR)
    _W["data"] = load_all()


def _rollout(seed: int, suppress: int | None, stop_after: int | None):
    """Play the search teacher, optionally skipping one round's board decision.

    Returns `(hp_after, fired)`: HP once each round's combat resolved, and the
    set of rounds where `best_board` actually returned a change. The second is
    what makes outcome C readable -- the search declines most rounds.
    """
    import rl.search as search_mod
    from rl.env import TFTEnv
    from rl.evaluate import scripted_policy
    from rl.search import search_policy

    env = TFTEnv(data=_W["data"])
    obs, _info = env.reset(seed=seed)

    state = {"round": 0}
    fired: set[int] = set()
    real_best_board = _W["real_best_board"]

    def gated_best_board(*args, **kwargs):
        if suppress is not None and state["round"] == suppress:
            return None
        out = real_best_board(*args, **kwargs)
        if out:
            fired.add(state["round"])
        return out

    search_mod.best_board = gated_best_board
    try:
        policy = search_policy(
            env, rng_seed=seed, base=scripted_policy(
                env, sell_bench=True, buy_synergy=True,
                match_items=True, corner_carry=True),
            mode="board")
        hp_after: dict[int, int] = {}
        seen = (env.match.round_id.stage, env.match.round_id.round)
        for _ in range(10_000):
            action = int(policy(obs, env.action_masks()))
            obs, _r, term, trunc, _i = env.step(action)
            now = (env.match.round_id.stage, env.match.round_id.round)
            if now != seen:
                hp_after[state["round"]] = env.player.hp
                state["round"] += 1
                seen = now
                if stop_after is not None and state["round"] > stop_after:
                    break
            if term or trunc:
                hp_after.setdefault(state["round"], env.player.hp)
                break
        return hp_after, fired
    finally:
        search_mod.best_board = real_best_board


def _episode(seed: int):
    import rl.search as search_mod

    _W.setdefault("real_best_board", search_mod.best_board)
    base_hp, fired = _rollout(seed, None, None)
    rows = []
    # Only rounds where the search actually changed the board can carry a
    # deviation: suppressing a round it declined is a no-op by construction and
    # would dilute the mean with guaranteed zeros.
    for rnd in sorted(fired):
        if rnd not in base_hp:
            continue
        alt_hp, _ = _rollout(seed, rnd, rnd)
        if rnd not in alt_hp:
            continue
        # Positive = suppressing that round's board decision cost HP.
        rows.append((rnd, float(base_hp[rnd] - alt_hp[rnd])))
    return rows, len(base_hp), len(fired)


def stats(values: list[float]) -> tuple[int, float, float]:
    n = len(values)
    if n < 2:
        return n, (values[0] if values else 0.0), 0.0
    mean = statistics.mean(values)
    sd = statistics.stdev(values)
    return n, mean, (0.0 if sd == 0 else mean / (sd / math.sqrt(n)))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episodes", type=int, default=300)
    parser.add_argument("--workers", type=int, default=10)
    args = parser.parse_args()

    before = source_fingerprint()
    print(f"source fingerprint: {before}")

    context = mp.get_context("spawn")
    rows: list[tuple[int, float]] = []
    rounds_played = fired_total = 0
    with timed("round_decision_credit", episodes=args.episodes, arms=1,
               workers=args.workers):
        with context.Pool(processes=args.workers, initializer=_init) as pool:
            for batch, played, fired in pool.imap_unordered(
                    _episode, range(args.episodes)):
                rows.extend(batch)
                rounds_played += played
                fired_total += fired

    if source_fingerprint() != before:
        print("!! SOURCE CHANGED MID-RUN -- discard (doc 99 entry 68.4)")
    if not rows:
        raise SystemExit("no deviations sampled")

    n, mean, t = stats([d for _, d in rows])
    print(f"\n{n} round-level deviations across {args.episodes} episodes.")
    print(f"the search changed the board in {fired_total}/{rounds_played} "
          f"rounds ({fired_total / max(rounds_played, 1):.1%})\n")
    print(f"{'quantity':<34}{'n':>7}{'hp cost':>10}{'t':>8}")
    print(f"{'one round board decision':<34}{n:>7}{mean:>10.3f}{t:>8.2f}")

    early = [d for r, d in rows if r < 12]
    late = [d for r, d in rows if r >= 12]
    for label, group in (("  of those, rounds 0-11", early),
                         ("  of those, rounds 12+", late)):
        gn, gmean, gt = stats(group)
        print(f"{label:<34}{gn:>7}{gmean:>10.3f}{gt:>8.2f}")

    print("\nReference: entry 129, one micro-action against the next fight, "
          "t = 0.95 (n=1072).\nEntry 106: this search is worth 0.527 placement "
          "over a whole game.")


if __name__ == "__main__":
    main()
