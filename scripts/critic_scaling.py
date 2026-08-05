r"""Is the critic data-limited or observation-limited? (doc 99 entry 59)

Entry 58.2 measured the ceiling: the best explained variance *any* critic could
reach predicting final placement is ~0.5 mid-game. Ours reaches **0.228
held-out** against **0.965 in-sample**. That gap is memorisation, but 58.3 could
not say which of two things causes it:

* **data-limited** -- the value head has the capacity and the observation has
  the information; there simply are not enough independent targets.
* **observation-limited** -- the 418-float encoding cannot express what
  separates these states, and no amount of data will help.

They demand opposite responses, so this measures the discriminating curve:
held-out explained variance as a function of **episodes**, at fixed capacity.

**Why episodes and not transitions.** The obvious reading of "137k training
rows" is that data is abundant. It is not. The return is dominated by a single
terminal placement per game, and every row from one episode shares it, so the
effective number of independent targets is closer to the **episode count** than
the row count. 400 episodes is a small dataset wearing a large one's clothes.
That is the hypothesis this script is built to test, and it predicts a curve
still rising at 1200 episodes.

**Reading it:**

* still climbing at the largest size -> data-limited, and collecting more is
  the cheapest available win.
* flat past some size, and the capacity arms do not help -> observation-limited,
  which per this project's record means *missing comparisons*, not more floats.
* flat, but a bigger network helps -> capacity-limited, the least likely and the
  easiest to fix.

**The value network here is the real one.** `net_arch=dict(pi=[], vf=[256,256])`
with `MlpPolicy` gives a value branch of `obs -> 256 -> 256 -> 1` over a Flatten
extractor, so a standalone MLP of that shape is equivalent, not an analogy.

    .venv/bin/python scripts/critic_scaling.py --max-episodes 1200
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rl.timing import timed  # noqa: E402
from scripts.train_ppo import ENV_DEFAULTS, collect_expert_data  # noqa: E402

# The teacher the current clones learn from (entry 53 flipped these on).
EXPERT_KWARGS = {
    "sell_bench": True,
    "roll_at_level": 0,
    "buy_synergy": True,
    "match_items": True,
    "corner_carry": True,
}

# Disjoint from training seeds and from the 510_000 the warm start's own
# holdout uses, so no episode can appear in two roles.
HOLDOUT_SEED_OFFSET = 880_000


def explained_variance(pred: np.ndarray, target: np.ndarray) -> float:
    var = float(np.var(target))
    return 0.0 if var == 0 else float(1.0 - np.var(target - pred) / var)


def fit_value_head(
    train: tuple[np.ndarray, np.ndarray],
    holdout: tuple[np.ndarray, np.ndarray],
    hidden: tuple[int, ...],
    epochs: int,
    batch_size: int = 256,
    lr: float = 1e-3,
    seed: int = 0,
) -> dict:
    """Regress returns on observations; report the best held-out EV reached.

    **Best-over-epochs, not final.** The question is what this much data can
    support, and a final-epoch number would confound it with how far past the
    optimum the run happened to stop. The in-sample figure is reported from the
    same epoch so the pair stays comparable.
    """
    import torch

    torch.manual_seed(seed)
    torch.set_num_threads(2)
    train_x, train_y = train
    hold_x, hold_y = holdout

    layers: list = []
    width = train_x.shape[1]
    for size in hidden:
        layers += [torch.nn.Linear(width, size), torch.nn.Tanh()]
        width = size
    layers.append(torch.nn.Linear(width, 1))
    net = torch.nn.Sequential(*layers)

    optimiser = torch.optim.Adam(net.parameters(), lr=lr)
    xt = torch.as_tensor(train_x, dtype=torch.float32)
    yt = torch.as_tensor(train_y, dtype=torch.float32)
    xh = torch.as_tensor(hold_x, dtype=torch.float32)

    best = {"ev_holdout": -np.inf, "ev_train": 0.0, "epoch": 0}
    n = len(xt)
    for epoch in range(epochs):
        permutation = torch.randperm(n)
        for start in range(0, n, batch_size):
            batch = permutation[start : start + batch_size]
            loss = torch.nn.functional.mse_loss(net(xt[batch]).flatten(), yt[batch])
            optimiser.zero_grad()
            loss.backward()
            optimiser.step()
        with torch.no_grad():
            ev_h = explained_variance(net(xh).flatten().numpy(), hold_y)
            ev_t = explained_variance(net(xt).flatten().numpy(), train_y)
        if ev_h > best["ev_holdout"]:
            best = {"ev_holdout": ev_h, "ev_train": ev_t, "epoch": epoch + 1}
    return best


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-episodes", type=int, default=1200)
    parser.add_argument("--holdout-episodes", type=int, default=150)
    parser.add_argument("--epochs", type=int, default=25)
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--gamma", type=float, default=0.999)
    parser.add_argument("--cache", type=Path, default=Path("runs/critic_scaling_data.npz"))
    parser.add_argument("--json", type=Path, default=Path("runs/critic_scaling.json"))
    args = parser.parse_args()

    from engine.loader import load_all

    logging.getLogger("engine.loader").setLevel(logging.ERROR)
    data = load_all()

    # Chunk sizes double, so every cumulative prefix is a clean episode split
    # and no episode is ever re-collected.
    sizes: list[int] = []
    size = max(args.max_episodes // 16, 25)
    while size < args.max_episodes:
        sizes.append(size)
        size *= 2
    sizes.append(args.max_episodes)

    if args.cache.exists():
        print(f"loading cached collection from {args.cache}")
        blob = np.load(args.cache)
        obs, returns = blob["obs"], blob["returns"]
        bounds = list(blob["bounds"])
        hold_x, hold_y = blob["hold_x"], blob["hold_y"]
    else:
        chunks: list[tuple[np.ndarray, np.ndarray]] = []
        bounds = []
        collected = 0
        with timed("critic_scaling.collect", episodes=args.max_episodes):
            for target in sizes:
                want = target - collected
                chunk = collect_expert_data(
                    data, want, gamma=args.gamma,
                    seed_offset=20_000 + collected * 13,
                    expert_kwargs=EXPERT_KWARGS, workers=args.workers,
                    **ENV_DEFAULTS,
                )
                chunks.append((chunk[0], chunk[3]))
                collected = target
                bounds.append(sum(len(c[0]) for c in chunks))
                print(f"  {collected} episodes -> {bounds[-1]} rows", flush=True)
            hold = collect_expert_data(
                data, args.holdout_episodes, gamma=args.gamma,
                seed_offset=HOLDOUT_SEED_OFFSET,
                expert_kwargs=EXPERT_KWARGS, workers=args.workers,
                **ENV_DEFAULTS,
            )
        obs = np.concatenate([c[0] for c in chunks])
        returns = np.concatenate([c[1] for c in chunks])
        hold_x, hold_y = hold[0], hold[3]
        np.savez_compressed(
            args.cache, obs=obs, returns=returns,
            bounds=np.array(bounds), hold_x=hold_x, hold_y=hold_y,
        )
        print(f"cached collection to {args.cache}")

    print(f"holdout: {len(hold_x)} rows from {args.holdout_episodes} episodes")

    results = {"scaling": [], "capacity": []}
    print(f"\n{'episodes':>9}{'rows':>9}{'EV train':>10}{'EV holdout':>12}{'epoch':>7}")
    for episodes, end in zip(sizes, bounds, strict=True):
        started = time.perf_counter()
        best = fit_value_head(
            (obs[:end], returns[:end]), (hold_x, hold_y),
            hidden=(256, 256), epochs=args.epochs,
        )
        results["scaling"].append({"episodes": episodes, "rows": int(end), **best})
        print(
            f"{episodes:>9}{end:>9}{best['ev_train']:>10.3f}"
            f"{best['ev_holdout']:>12.3f}{best['epoch']:>7}"
            f"   ({time.perf_counter() - started:.0f}s)",
            flush=True,
        )

    # Capacity arms at full data: if the curve is flat because the network is
    # too small, a wider one moves it; if it is flat because the observation is
    # the constraint, neither does.
    print(f"\n{'capacity':>12}{'EV train':>10}{'EV holdout':>12}")
    for hidden in [(64, 64), (256, 256), (512, 512)]:
        best = fit_value_head(
            (obs, returns), (hold_x, hold_y), hidden=hidden, epochs=args.epochs
        )
        results["capacity"].append({"hidden": list(hidden), **best})
        print(f"{str(hidden):>12}{best['ev_train']:>10.3f}{best['ev_holdout']:>12.3f}")

    scale = results["scaling"]
    first, last = scale[0]["ev_holdout"], scale[-1]["ev_holdout"]
    prev = scale[-2]["ev_holdout"] if len(scale) > 1 else first
    print(
        f"\nheld-out EV {first:.3f} -> {last:.3f} over "
        f"{sizes[0]} -> {sizes[-1]} episodes; last doubling added {last - prev:+.3f}."
    )
    print("The warm start's own critic measures 0.228; entry 58.2's ceiling is ~0.5.")
    if last - prev > 0.02:
        print("  -> still climbing: DATA-limited. Collect more episodes.")
    else:
        widths = {tuple(c["hidden"]): c["ev_holdout"] for c in results["capacity"]}
        if widths.get((512, 512), 0) - widths.get((256, 256), 0) > 0.02:
            print("  -> flat in data, better with width: CAPACITY-limited.")
        else:
            print(
                "  -> flat in data and in capacity: OBSERVATION-limited. Per this "
                "project's record that means missing *comparisons*, not more floats."
            )

    args.json.write_text(json.dumps(results, indent=1))
    print(f"results: {args.json}")


if __name__ == "__main__":
    main()
