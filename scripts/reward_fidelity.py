"""Does the advantage signal track what actually changes placement? (entry 91)

Entry 90 measured PPO's own advantages at the `bc-econ-s0` clone and found the
drift: `END_PLANNING` is the most-rewarded common action (+4.6pp positive rate,
t~+3.4) and `BUY` -- a third of all transitions -- the least (-4.4pp, t~-8.0).
Moving mass from BUY to END_PLANNING fully accounts for the collapse to 8.000
(89.1).

90.2 left two readings that the advantages cannot separate:

* **buying is genuinely bad** at this policy, or
* **credit misassignment** -- advantage is `return - V(s)`, the critic's
  held-out EV is ~0.58, and BUY happens in systematically identifiable states
  (gold in hand, board not full), so a critic that misestimates those states
  hands every BUY in them the same bias.

They have opposite fixes, so this measures which. The ground truth is a
counterfactual, not a value estimate: deviate from the policy's chosen action
**once**, then let the policy play on, and see what happens to final placement.

PPO's advantage is `Q(s,a) - V(s)`, i.e. how much better `a` is than what the
policy would have done on average. The empirical analogue: take the policy's
own action, versus one *sampled from the policy itself*, and difference the
outcomes. Averaged per kind, a positive mean means deviating from that kind
hurts -- the action was carrying real value.

So the comparison is: **does the kind PPO rewards least (BUY) turn out to be
the kind whose loss costs most?** If so the signal is inverted, which is
misassignment measured rather than argued.

Replay-from-seed rather than `deepcopy` (the env holds a `mappingproxy`), and
the determinism of replay is verified in `disagreement_cost.py`. Both branches
share every RNG draw and differ only in the substituted action.

    .venv/bin/python scripts/reward_fidelity.py runs/bc-econ-s0 --episodes 300
"""

from __future__ import annotations

import argparse
import hashlib
import json
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


def _rollout(seed: int, override: tuple[int, int] | None):
    """Play under the clone, optionally forcing one action at one step."""
    from rl.env import TFTEnv

    env = TFTEnv(data=_W["data"], **_W["env_kwargs"])
    obs, _info = env.reset(seed=seed)
    space = env.action_space_helper
    trace = []
    placement = None
    for step in range(10_000):
        mask = env.action_masks()
        action = _act(obs, mask, deterministic=True)
        trace.append((step, action, space.decode(action).kind.name))
        if override is not None and override[0] == step:
            action = override[1]
        obs, _r, term, trunc, info = env.step(action)
        if term or trunc:
            placement = info.get("placement")
            break
    return placement, trace


def _episode(seed: int):
    import random

    base_placement, trace = _rollout(seed, None)
    if base_placement is None or not trace:
        return []
    rng = random.Random(seed)
    picks = rng.sample(trace, min(_W["per_episode"], len(trace)))

    env = _W["env"]
    rows = []
    for step, chosen, kind in picks:
        # Replay to `step` to recover the exact mask, then sample an
        # alternative from the policy's *own* distribution -- that is the
        # baseline PPO's advantage is measured against.
        obs, _info = env.reset(seed=seed)
        mask = env.action_masks()
        for _ in range(step):
            act = _act(obs, mask, deterministic=True)
            obs, _r, term, trunc, _i = env.step(act)
            if term or trunc:
                break
            mask = env.action_masks()
        # The clone is sharply peaked (training logits ~28), so a single
        # stochastic draw returns the argmax almost every time -- the first
        # version of this probe sampled 16 deviations and got zero. Draw until
        # a genuinely different action appears, which keeps the alternative
        # inside the policy's own support (the baseline PPO's advantage is
        # measured against) rather than falling back to a uniform random
        # action, which would measure something else entirely.
        alternative = chosen
        for _ in range(40):
            candidate = _act(obs, mask, deterministic=False)
            if candidate != chosen:
                alternative = candidate
                break
        if alternative == chosen:
            continue
        alt_placement, _ = _rollout(seed, (step, alternative))
        if alt_placement is None:
            continue
        # Positive = deviating from the chosen action made placement worse,
        # i.e. that action was carrying real value.
        rows.append((kind, alt_placement - base_placement))
    return rows


def stats(values: list[float]) -> tuple[int, float, float]:
    n = len(values)
    if n < 2:
        return n, (values[0] if values else 0.0), 0.0
    mean = statistics.mean(values)
    sd = statistics.stdev(values)
    return n, mean, (mean / (sd / math.sqrt(n)) if sd > 0 else 0.0)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--episodes", type=int, default=300)
    parser.add_argument("--per-episode", type=int, default=3)
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--advantages", type=Path, default=Path("runs/adv_clone.json"),
                        help="per-kind advantage summary from advantage_probe.py")
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args()

    from scripts.teacher_gap import teacher_config

    _expert, env_kwargs, _search = teacher_config(args.run)
    before = source_fingerprint()
    print(f"source fingerprint: {before}")

    context = mp.get_context("spawn")
    rows = []
    with timed("reward_fidelity", episodes=args.episodes, arms=1,
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

    adv = {}
    if args.advantages.exists():
        adv = json.loads(args.advantages.read_text())

    print(f"\n{len(rows)} deviations. Positive `cost` = losing that action hurt "
          "placement.\n")
    print(f"{'action kind':<16}{'n':>6}{'cost':>9}{'t':>7}{'PPO adv':>10}"
          f"{'adv rank':>10}{'cost rank':>11}")

    ranked_cost = sorted(by_kind, key=lambda k: -stats(by_kind[k])[1])
    ranked_adv = sorted(
        [k for k in by_kind if k in adv], key=lambda k: -adv[k]["mean"]
    )
    for kind in ranked_cost:
        n, mean, t = stats(by_kind[kind])
        a = adv.get(kind, {}).get("mean")
        a_rank = ranked_adv.index(kind) + 1 if kind in ranked_adv else 0
        c_rank = ranked_cost.index(kind) + 1
        print(f"{kind:<16}{n:>6}{mean:>9.3f}{t:>7.2f}"
              f"{(f'{a:+.4f}' if a is not None else '-'):>10}"
              f"{(a_rank or '-'):>10}{c_rank:>11}")

    common = [k for k in ranked_cost if k in adv and len(by_kind[k]) >= 30]
    if len(common) >= 3:
        xs = [adv[k]["mean"] for k in common]
        ys = [stats(by_kind[k])[1] for k in common]
        mx, my = statistics.mean(xs), statistics.mean(ys)
        num = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
        den = math.sqrt(sum((x - mx) ** 2 for x in xs)
                        * sum((y - my) ** 2 for y in ys))
        r = num / den if den else 0.0
        print(f"\ncorrelation between PPO advantage and true cost, "
              f"{len(common)} kinds: r = {r:+.2f}")
        print("A strongly *negative* r means the signal is inverted -- the "
              "actions PPO\npenalises are the ones whose loss costs most, which "
              "is credit misassignment\nmeasured rather than argued (90.2). "
              "Near zero means the signal is simply\nuninformative about which "
              "actions matter.")

    if args.json:
        args.json.write_text(json.dumps(
            {k: {"n": len(v), "mean": statistics.mean(v)} for k, v in by_kind.items()},
            indent=1))
        print(f"\nper-kind results: {args.json}")


if __name__ == "__main__":
    main()
