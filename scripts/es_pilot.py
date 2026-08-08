"""Is there a fitness signal for population search to climb? (doc 99 entry 94)

Entry 93 closed the last of the per-action fixes: label noise (79), distribution
shift (81), observation width (83) and shaping (93) all improve the *per-action*
learning signal, and none moved placement. 91 explains why -- at this policy no
single action measurably changes the outcome, so there is nothing there to
sharpen.

91.4's surviving direction is methods that need no per-action credit at all.
Population/evolutionary search is the cheapest of them: perturb the policy
*parameters*, play whole episodes, keep what places better. It never asks which
action was responsible.

But it has its own precondition, and this measures it before a search is spent.
ES climbs a ranking of perturbations by episode-level fitness. That ranking is
only followable if it is **reproducible** -- if a perturbation that looks good
on one set of games still looks good on a different set. Placement has a
standard deviation of ~2.3, so a 40-game fitness estimate carries ~0.36 of
noise; if the true spread between perturbations is smaller than that, the
ranking is noise and ES would fit it exactly as PPO fit noise in 91.

**The measurement.** For each sigma, draw M perturbations and evaluate every one
on two *disjoint* seed blocks. Then correlate fitness on block A against fitness
on block B across the M perturbations. That correlation is the reliability of
the ranking, and it is the number that decides whether the direction is viable:

* **r near 1** -- the ranking is real and ES has a gradient to follow.
* **r near 0** -- the ranking is noise. ES is dead on arrival at this sigma, and
  more episodes per member (not more members) is the only fix.

Sigma is *relative*: each tensor is perturbed by `sigma * tensor.std()`, so one
sigma means the same thing to a layer with std 0.05 and one with std 0.46.
Only `action_net` is perturbed -- the critic cannot change behaviour, and
perturbing it would add cost and no signal.

The sigma grid is not guessed. Measured on 600 fixed states drawn from base
rollouts (fixed states, because once one action differs the trajectory diverges
and any later comparison is between two different games):

| sigma | 0.002 | 0.01 | 0.02 | 0.05 | 0.1 | 0.2 | 0.4 |
|---|---|---|---|---|---|---|---|
| decisions changed | 0.5% | 0.8% | 1.3% | 2.9% | 4.8% | 11.2% | 28.2% |

The clone's logits are ~28, so anything below ~0.02 leaves the argmax intact
almost everywhere and cannot produce a fitness difference to rank. Defaults
span the range where behaviour actually moves.

Noise is regenerated from an integer seed inside each worker rather than
pickled, which is the standard ES bandwidth trick and also keeps a perturbation
byte-identical across the two blocks.

    .venv/bin/python scripts/es_pilot.py runs/bc-econ-s0 --members 12 --block 40
"""

from __future__ import annotations

import argparse
import hashlib
import json
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
    for name in ("rl/evaluate.py", "rl/env.py", "rl/action.py"):
        digest.update(Path(name).read_bytes())
    return digest.hexdigest()[:12]


def _init(run_dir: str, env_kwargs: dict) -> None:
    import logging

    import torch
    from sb3_contrib import MaskablePPO

    from engine.loader import load_all
    from rl.env import TFTEnv

    logging.getLogger("engine.loader").setLevel(logging.ERROR)
    torch.set_num_threads(1)
    data = load_all()
    _W["env"] = TFTEnv(data=data, **env_kwargs)
    model = MaskablePPO.load(run_dir, device="cpu")
    _W["model"] = model
    # Only the actor: the critic is not consulted at inference, so perturbing
    # it would cost time and produce no behavioural difference at all.
    params = [(n, p) for n, p in model.policy.named_parameters()
              if n.startswith("action_net")]
    _W["params"] = params
    _W["base"] = [p.data.clone() for _n, p in params]
    # A one-element bias has no defined std (torch returns nan for unbiased
    # variance of n=1). Those tensors are left unperturbed rather than given a
    # made-up scale -- there are three of them and they are single scalars.
    scales = []
    for _n, p in params:
        s = p.data.std().item() if p.numel() > 1 else float("nan")
        scales.append(s if math.isfinite(s) and s > 0 else 0.0)
    _W["scales"] = scales


def _apply(member: int, sigma: float) -> None:
    """Set actor weights to base + sigma * scale * N(0,1), seeded by `member`.

    `member < 0` restores the unperturbed policy.
    """
    import torch

    for (_n, p), base in zip(_W["params"], _W["base"], strict=True):
        p.data.copy_(base)
    if member < 0:
        return
    gen = torch.Generator()
    gen.manual_seed(member)
    for (_n, p), base, scale in zip(_W["params"], _W["base"], _W["scales"],
                                    strict=True):
        if scale <= 0:
            continue
        noise = torch.randn(p.shape, generator=gen, dtype=p.dtype)
        p.data.copy_(base + sigma * scale * noise)


def _task(job):
    """One (perturbation, seed block) cell -> its placements."""
    from rl.evaluate import evaluate, sb3_policy

    member, sigma, block, seeds = job
    _apply(member, sigma)
    policy = sb3_policy(_W["model"])
    result = evaluate(_W["env"], policy, seeds=list(seeds))
    return member, sigma, block, result.placements


def pearson(xs: list[float], ys: list[float]) -> float:
    mx, my = statistics.mean(xs), statistics.mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    den = math.sqrt(sum((x - mx) ** 2 for x in xs)
                    * sum((y - my) ** 2 for y in ys))
    return num / den if den else 0.0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--members", type=int, default=12,
                        help="perturbations drawn per sigma")
    parser.add_argument("--block", type=int, default=40,
                        help="episodes per seed block (two disjoint blocks)")
    parser.add_argument("--sigmas", type=float, nargs="+",
                        default=[0.05, 0.15, 0.4])
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args()

    from scripts.teacher_gap import teacher_config

    _expert, env_kwargs, _search = teacher_config(args.run)
    before = source_fingerprint()
    print(f"source fingerprint: {before}")
    print(f"env: {env_kwargs}")

    block_a = list(range(args.block))
    block_b = list(range(1000, 1000 + args.block))

    jobs = [(-1, 0.0, "A", block_a), (-1, 0.0, "B", block_b)]
    for si, sigma in enumerate(args.sigmas):
        for m in range(args.members):
            # Distinct member ids across sigmas so no two cells share noise.
            member = si * 1000 + m + 1
            jobs.append((member, sigma, "A", block_a))
            jobs.append((member, sigma, "B", block_b))

    context = mp.get_context("spawn")
    rows = []
    with timed("es_pilot", episodes=sum(len(j[3]) for j in jobs),
               arms=len(args.sigmas), workers=args.workers):
        with context.Pool(processes=args.workers, initializer=_init,
                          initargs=(str(args.run / "model"), env_kwargs)) as pool:
            for out in pool.imap_unordered(_task, jobs):
                rows.append(out)
                print(".", end="", flush=True)
    print()

    if source_fingerprint() != before:
        print("!! SOURCE CHANGED MID-RUN -- discard (doc 99 entry 68.4)")

    fitness: dict[tuple[int, str], float] = {}
    raw: dict[str, list[int]] = {}
    for member, _sigma, block, placements in rows:
        fitness[(member, block)] = statistics.mean(placements)
        # Kept per seed, not just averaged: every member shares the same seed
        # blocks, so a member-vs-base comparison is *paired* and the seed
        # effects cancel. Summarising to a mean first throws that away and
        # leaves only an unpaired test against a base that has its own noise
        # -- which is exactly the comparison 94.4 could not make.
        raw[f"{member}:{block}"] = list(placements)

    base_a, base_b = fitness[(-1, "A")], fitness[(-1, "B")]
    base_mean = (base_a + base_b) / 2
    print(f"\nunperturbed clone: block A {base_a:.3f}  block B {base_b:.3f}")
    print("Blocks are disjoint, so the gap between these two is the scale of "
          "pure\nevaluation noise at this block size -- any spread smaller than "
          "it is not real.\n")

    print(f"{'sigma':>8}{'members':>9}{'mean':>8}{'best':>8}{'sd(A)':>8}"
          f"{'noise':>8}{'r(A,B)':>9}{'verdict':>12}")
    summary = {}
    for sigma in args.sigmas:
        members = sorted({m for m, s, _b, _p in rows if s == sigma and m >= 0})
        fa = [fitness[(m, "A")] for m in members]
        fb = [fitness[(m, "B")] for m in members]
        both = [(a + b) / 2 for a, b in zip(fa, fb, strict=True)]
        r = pearson(fa, fb)
        sd = statistics.stdev(fa) if len(fa) > 1 else 0.0
        # Within-member disagreement across disjoint blocks is a direct
        # estimate of the noise on a single block's fitness.
        noise = statistics.stdev([a - b for a, b in zip(fa, fb, strict=True)])
        noise /= math.sqrt(2)
        # Direction matters as much as reliability. At sigma 0.4 the pilot
        # measured r=0.99 while every member was ~2.2 placement *worse* than
        # base: what is being reliably ranked there is how badly each
        # perturbation broke the policy. A ranking that is reproducible and
        # entirely downhill is not something to climb (entry 94.3).
        broken = statistics.mean(both) > base_mean + 0.5
        verdict = ("broken" if broken else
                   "followable" if r >= 0.5 else
                   "marginal" if r >= 0.25 else "noise")
        print(f"{sigma:>8.3f}{len(members):>9}{statistics.mean(both):>8.3f}"
              f"{min(both):>8.3f}{sd:>8.3f}{noise:>8.3f}{r:>9.2f}"
              f"{verdict:>12}")
        summary[str(sigma)] = {
            "mean": statistics.mean(both), "best": min(both),
            "sd_block_a": sd, "noise": noise, "r": r,
            "fitness_a": fa, "fitness_b": fb, "members": members,
        }

    print("\n`sd(A)` is the observed spread of member fitness on one block; "
          "`noise` is how\nmuch of that spread a disjoint re-evaluation says is "
          "measurement error. When\n`sd(A)` is not comfortably above `noise`, "
          "the members are not actually\ndifferent and `r` collapses -- ES "
          "would be ranking noise (91, 93).")
    print("A sigma whose `mean` is far worse than the unperturbed clone is "
          "past the edge\nof the basin: the perturbation is breaking the policy "
          "rather than exploring\naround it. Useful sigma has mean close to "
          "base and r high.")

    if args.json:
        args.json.write_text(json.dumps(
            {"base_a": base_a, "base_b": base_b, "sigmas": summary,
             "placements": raw, "block_a": block_a, "block_b": block_b},
            indent=1))
        print(f"\nper-sigma results: {args.json}")


if __name__ == "__main__":
    main()
