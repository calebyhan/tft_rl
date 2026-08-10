"""Does one action move *that round's* fight, when it cannot move placement?

Entry 91 measured the counterfactual cost of a single action against **final
placement** and found nothing: 1098 deviations, largest |t| = 1.82, overall mean
-0.101 at t ~ -1.4. 91.3 concluded that per-action credit assignment from
terminal placement is unattainable here -- ~400 actions per episode, each with
no individually measurable effect, collectively spanning 7 placements -- and
that PPO's advantages are therefore fitting noise.

That is a statement about the **signal**, not about the actions. The causal
chain from one buy to a final placement runs through twenty more rounds of
compounding. The chain from that same buy to **the very next combat** is one
round long.

So this is entry 91's design with the outcome variable moved: deviate once, then
measure the HP the seat loses in the next fight rather than where it finishes.
The reward this would license -- per-round combat outcome -- has never been
tried here; `TFTEnv` rewards `(9 - placement) / 8` at game end, with optional
board/survival shaping that entries 92-93 showed concentrates credit on
`END_PLANNING` and does not stop the collapse.

Named outcomes, before the run:

* **A -- the signal is there.** Single actions measurably move the next fight
  (|t| well past 2). Then a dense per-round reward has real signal exactly where
  terminal placement has none, and "make RL work" has a concrete path.
* **B -- nothing here either.** Then 91.2's reading is the whole story: the
  per-action signal exists only against a *better* policy, not within one, and
  no amount of reward densification helps. The fix would have to be better
  alternatives (a stronger reference), not a denser signal.
* **C -- split by kind.** Board actions (BUY, SELECT, PLACE) move the fight and
  economy actions (BUY_XP, REROLL) do not, which is what the causal story
  predicts -- economy pays off rounds later. That would license a *mixed*
  objective rather than a uniform one, and says which kinds it can cover.

**C is the outcome the causal story predicts**, stated ahead so a result cannot
be fitted to it afterwards.

Replay-from-seed, exactly as entry 91 did; both branches share every RNG draw
and differ only in the substituted action.

    .venv/bin/python scripts/round_credit.py runs/bc-econ-s0 --episodes 200
"""

from __future__ import annotations

import argparse
import hashlib
import math
import multiprocessing as mp
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rl.timing import timed  # noqa: E402

_W: dict = {}


def source_fingerprint() -> str:
    digest = hashlib.sha256()
    for name in ("rl/evaluate.py", "rl/env.py", "rl/action.py"):
        digest.update(Path(name).read_bytes())
    return digest.hexdigest()[:12]


def _init(run_dir: str, env_kwargs: dict, per_episode: int) -> None:
    import logging

    import torch
    from sb3_contrib import MaskablePPO

    from engine.loader import load_all
    from rl.env import TFTEnv

    logging.getLogger("engine.loader").setLevel(logging.ERROR)
    torch.set_num_threads(1)
    _W["data"] = load_all()
    _W["env_kwargs"] = env_kwargs
    _W["env"] = TFTEnv(data=_W["data"], **env_kwargs)
    _W["model"] = MaskablePPO.load(run_dir, device="cpu")
    _W["per_episode"] = per_episode


def _act(obs, mask, deterministic: bool) -> int:
    action, _ = _W["model"].predict(
        obs, action_masks=mask, deterministic=deterministic
    )
    return int(action)


def _rollout(seed: int, override: tuple[int, int] | None, until_round: int | None):
    """Play under the clone, optionally forcing one action at one step.

    Returns `(trace, hp_after)`. `hp_after` maps a round index to the seat's HP
    once that round's combat has resolved, which is the quantity the deviation
    is credited against. Stops early once `until_round` has resolved, so the
    deviated branch costs one round rather than a whole game.
    """
    from rl.env import TFTEnv

    env = TFTEnv(data=_W["data"], **_W["env_kwargs"])
    obs, _info = env.reset(seed=seed)
    space = env.action_space_helper
    trace = []
    hp_after: dict[int, int] = {}
    rounds = 0
    seen = (env.match.round_id.stage, env.match.round_id.round)
    for step in range(10_000):
        mask = env.action_masks()
        action = _act(obs, mask, deterministic=True)
        trace.append((step, action, space.decode(action).kind.name, rounds))
        if override is not None and override[0] == step:
            action = override[1]
        obs, _r, term, trunc, _info = env.step(action)
        now = (env.match.round_id.stage, env.match.round_id.round)
        if now != seen:
            # The round the seat just played has resolved; its HP now reflects
            # that combat. Record against the index the actions carried.
            hp_after[rounds] = env.player.hp
            rounds += 1
            seen = now
            if until_round is not None and rounds > until_round:
                break
        if term or trunc:
            hp_after.setdefault(rounds, env.player.hp)
            break
    return trace, hp_after


def _episode(seed: int):
    import random

    trace, base_hp = _rollout(seed, None, None)
    if not trace:
        return []
    rng = random.Random(seed)
    # Only steps whose round actually resolved can be credited.
    usable = [row for row in trace if row[3] in base_hp]
    if not usable:
        return []
    picks = rng.sample(usable, min(_W["per_episode"], len(usable)))

    env = _W["env"]
    rows = []
    for step, chosen, kind, rnd in picks:
        obs, _info = env.reset(seed=seed)
        mask = env.action_masks()
        for _ in range(step):
            act = _act(obs, mask, deterministic=True)
            obs, _r, term, trunc, _i = env.step(act)
            if term or trunc:
                break
            mask = env.action_masks()
        # Same as entry 91: draw until a genuinely different action appears, so
        # the alternative stays inside the policy's own support. The clone is
        # sharply peaked, so a single stochastic draw returns the argmax.
        alternative = chosen
        for _ in range(40):
            candidate = _act(obs, mask, deterministic=False)
            if candidate != chosen:
                alternative = candidate
                break
        if alternative == chosen:
            continue
        _alt_trace, alt_hp = _rollout(seed, (step, alternative), rnd)
        if rnd not in alt_hp:
            continue
        # Positive = deviating cost HP in the very next fight, i.e. the chosen
        # action was carrying real value for that round.
        rows.append((kind, float(base_hp[rnd] - alt_hp[rnd])))
    return rows


def stats(values: list[float]) -> tuple[int, float, float]:
    n = len(values)
    if n < 2:
        return n, (values[0] if values else 0.0), 0.0
    mean = statistics.mean(values)
    sd = statistics.stdev(values)
    return n, mean, (0.0 if sd == 0 else mean / (sd / math.sqrt(n)))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--episodes", type=int, default=200)
    parser.add_argument("--per-episode", type=int, default=3)
    parser.add_argument("--workers", type=int, default=10)
    args = parser.parse_args()

    from scripts.teacher_gap import teacher_config

    _expert, env_kwargs, _search = teacher_config(args.run)
    before = source_fingerprint()
    print(f"source fingerprint: {before}")

    context = mp.get_context("spawn")
    rows = []
    with timed("round_credit", episodes=args.episodes, arms=1,
               workers=args.workers):
        with context.Pool(processes=args.workers, initializer=_init,
                          initargs=(str(args.run / "model"), env_kwargs,
                                    args.per_episode)) as pool:
            for batch in pool.imap_unordered(_episode, range(args.episodes)):
                rows.extend(batch)

    if source_fingerprint() != before:
        print("!! SOURCE CHANGED MID-RUN -- discard (doc 99 entry 68.4)")
    if not rows:
        raise SystemExit("no deviations sampled")

    by_kind: dict[str, list[float]] = defaultdict(list)
    for kind, delta in rows:
        by_kind[kind].append(delta)

    print(f"\n{len(rows)} deviations. Positive `hp cost` = losing that action "
          "cost HP in the *next fight*.\n")
    print(f"{'action kind':<16}{'n':>6}{'hp cost':>10}{'t':>8}")
    for kind in sorted(by_kind, key=lambda k: -stats(by_kind[k])[1]):
        n, mean, t = stats(by_kind[kind])
        print(f"{kind:<16}{n:>6}{mean:>10.3f}{t:>8.2f}")
    n, mean, t = stats([d for _, d in rows])
    print(f"{'ALL':<16}{n:>6}{mean:>10.3f}{t:>8.2f}")
    print("\nEntry 91 reference, same deviations against final placement: "
          "overall -0.101 at t ~ -1.4,\nlargest per-kind |t| = 1.82.")


if __name__ == "__main__":
    main()
