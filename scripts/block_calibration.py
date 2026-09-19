"""Is the within-block SE honest across seed ranges? (doc 99 entry 160.158)

τ = 0.170 entered the gates as a between-block SD (lesson 29), estimated from
three swap blocks that replay-verification shows ran one teacher. Blocks of one
frozen teacher on fresh seeds are exchangeable by construction, so between-
block variance beyond the SE can only come from seed ranges carrying variance
the SE misses. This measures that directly on the stored records: split each
block into contiguous 100-seed sub-blocks and ask whether their means scatter
more than the block's own SD predicts.

Per block, Q = Σ (d_i − d̄)² / (s²/size) on the sub-block mean differences d_i,
with df = k − 1. Summed over blocks, Q ~ χ²(Σ df) under exchangeability.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import statistics
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SIZE = 100
TAU = 0.170

# The first primary contrast each block's own pre-registration named, as
# (run file stem, first arm, second arm, entry); the contrast is second − first.
CONTRASTS = (
    ("swap_composition_160_139", "base", "swap_first", "160.139"),
    ("swap_control_160_141", "base", "swap", "160.141"),
    ("swap_tiebreak_160_143", "base", "swap", "160.143"),
    ("macro_ceiling_160_145", "search:fast8", "search:standard", "160.145"),
    ("move_composition_160_147", "base", "move", "160.147"),
    ("move_replication_160_149", "base", "move", "160.149"),
    ("move_third_160_151", "base", "move", "160.151"),
    ("field_strength_160_153", "default/greedy", "default/full", "160.153"),
    ("tie_break_retention_160_156", "insertion", "hex", "160.156"),
)


def chi2_sf(x: float, df: int) -> float:
    """P(χ²(df) > x): the regularized upper incomplete gamma Q(df/2, x/2)."""
    a, z = df / 2.0, x / 2.0
    if z <= 0:
        return 1.0
    log_prefix = a * math.log(z) - z - math.lgamma(a)
    if z < a + 1:
        # Series for the lower tail P, which converges fast below the mode.
        term = total = 1.0 / a
        n = a
        for _ in range(10_000):
            n += 1
            term *= z / n
            total += term
            if abs(term) < abs(total) * 1e-15:
                break
        return 1.0 - total * math.exp(log_prefix)
    # Lentz's continued fraction for Q above the mode.
    tiny = 1e-300
    b = z + 1 - a
    c = 1 / tiny
    d = 1 / b
    h = d
    for i in range(1, 10_000):
        an = -i * (i - a)
        b += 2
        d = an * d + b
        d = tiny if abs(d) < tiny else d
        c = b + an / c
        c = tiny if abs(c) < tiny else c
        d = 1 / d
        delta = d * c
        h *= delta
        if abs(delta - 1) < 1e-15:
            break
    return math.exp(log_prefix) * h


def sub_block_q(differences: list[float], size: int = SIZE) -> tuple[float, int]:
    """Q and df for one block's paired differences, given in seed order."""
    if len(differences) % size or len(differences) < 2 * size:
        raise ValueError(
            f"{len(differences)} differences do not tile into >=2 sub-blocks of {size}"
        )
    s = statistics.stdev(differences)
    means = [
        statistics.fmean(differences[start:start + size])
        for start in range(0, len(differences), size)
    ]
    grand = statistics.fmean(means)
    q = sum((m - grand) ** 2 for m in means) * size / s**2
    return q, len(means) - 1


def _arm(record: dict) -> str:
    if "field" in record:
        return f"{record['field']}/{record['arm']}"
    return record["arm"]


def paired_differences(records: list[dict], first: str, second: str) -> list[float]:
    """second − first placement per seed, in seed order."""
    by_arm: dict[str, dict[int, float]] = {first: {}, second: {}}
    for record in records:
        arm = _arm(record)
        if arm in by_arm:
            by_arm[arm][record["seed"]] = record["placement"]
    if by_arm[first].keys() != by_arm[second].keys():
        raise ValueError(f"arms {first!r} and {second!r} were not played on the same seeds")
    return [by_arm[second][seed] - by_arm[first][seed] for seed in sorted(by_arm[first])]


def _critical(df: int, alpha: float) -> float:
    low, high = 0.0, df + 50.0 * math.sqrt(2 * df) + 50
    for _ in range(200):
        mid = (low + high) / 2
        low, high = (mid, high) if chi2_sf(mid, df) > alpha else (low, mid)
    return (low + high) / 2


def power(blocks: list[tuple[float, int]], tau: float, alpha: float = 0.05,
          size: int = SIZE, reps: int = 20_000, seed: int = 0) -> float:
    """Chance the pooled test rejects if seed ranges carry an SD of ``tau``.

    ``blocks`` is (s, sub-block count) per block. Only variances enter, so this
    can be computed before any sub-block mean is looked at.
    """
    rng = random.Random(seed)
    critical = _critical(sum(k - 1 for _s, k in blocks), alpha)
    rejections = 0
    for _ in range(reps):
        total = 0.0
        for s, k in blocks:
            spread = math.sqrt(s**2 / size + tau**2)
            means = [rng.gauss(0.0, spread) for _ in range(k)]
            grand = sum(means) / k
            total += sum((m - grand) ** 2 for m in means) * size / s**2
        rejections += total > critical
    return rejections / reps


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, default=REPO_ROOT / "runs")
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    blocks = []
    for stem, first, second, entry in CONTRASTS:
        records = json.loads((args.runs / f"{stem}.json").read_text())["records"]
        diffs = paired_differences(records, first, second)
        blocks.append({
            "block": stem, "entry": entry, "contrast": f"{second} − {first}",
            "n": len(diffs), "k": len(diffs) // SIZE,
            "s": statistics.stdev(diffs), "delta": statistics.fmean(diffs),
            "diffs": diffs,
        })

    # Power first: it reads only each block's s, never a sub-block mean.
    shape = [(b["s"], b["k"]) for b in blocks]
    pooled_df = sum(k - 1 for _s, k in shape)
    print(f"power at τ={TAU} (sub-block scale, α=0.05, df={pooled_df}): "
          f"{power(shape, TAU):.3f}")
    print(f"critical Q: {_critical(pooled_df, 0.05):.2f}\n")

    print(f"{'block':30s} {'contrast':34s} {'n':>4s} {'s':>6s} {'Δ':>7s} {'Q':>6s} {'df':>3s} {'p':>6s}")
    pooled_q = 0.0
    for b in blocks:
        q, df = sub_block_q(b.pop("diffs"))
        b.update(q=q, df=df, p=chi2_sf(q, df))
        pooled_q += q
        print(f"{b['block']:30s} {b['contrast']:34s} {b['n']:4d} {b['s']:6.3f} "
              f"{b['delta']:+7.3f} {q:6.2f} {df:3d} {b['p']:6.3f}")

    p = chi2_sf(pooled_q, pooled_df)
    ratio = pooled_q / pooled_df
    mean_var = statistics.fmean(b["s"] ** 2 for b in blocks)
    tau_sub = math.sqrt(max(0.0, ratio - 1) * mean_var / SIZE)
    print(f"\npooled Q = {pooled_q:.2f} on {pooled_df} df, p = {p:.3f}, "
          f"Q/df = {ratio:.3f}, implied sub-block τ = {tau_sub:.3f}")

    if args.json:
        args.json.write_text(json.dumps({
            "size": SIZE, "tau_tested": TAU, "blocks": blocks,
            "pooled_q": pooled_q, "pooled_df": pooled_df, "p": p,
            "q_over_df": ratio, "implied_tau": tau_sub,
        }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
