"""Learn to predict a fight instead of simulating it (doc 99 entry 145).

The problem the log keeps hitting is that **policy** learning has no signal:
91's 1,098 counterfactuals found no single action moves placement (max |t| =
1.82), so PPO's per-action advantage is ~46x below its own noise (130), and
three shaping modes collapsed without a BC anchor (93). Rewards were not
missing; the per-action signal is not there to be found.

A **value** problem has none of that. "Given these two boards, who wins?" has a
label on every fight, thousands per game, immediate, with no credit assignment
at all. It is supervised learning, not RL. 105.5 scoped it as step 2 of a
gated programme and 106 refused the gate; that refusal predates 108.2's 0.243
for search, so the premise has moved.

**Why it compounds:** measured here at 27 fights/sec single-core, a fight costs
37ms, which is why one board-search call costs ~2s. A surrogate answering in
microseconds makes search ~1000x cheaper, and deeper search is a better
teacher -- which 75 says a clone follows at 89%.

Features are **relational by construction**. The single most productive finding
in this project is that describing entities fails and comparing them works: an
~1800-float champion encoding was rejected three times, while twelve floats
across four comparisons closed a 1.266 placement gap. So the model never sees
"board A is these units"; it sees aggregate differentials between the two
boards. A descriptive per-unit encoding is the thing not to build here.

    .venv/bin/python scripts/combat_surrogate.py --states 40 --epochs 40
"""

from __future__ import annotations

import argparse
import random
import statistics
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import numpy as np  # noqa: E402

from engine.loader import load_all  # noqa: E402
from engine.match import Match  # noqa: E402
from engine.traits import active_traits  # noqa: E402
from rl.opponents import DEFAULT_FIELD, GreedyPolicy  # noqa: E402
from rl.search import clone_board, fight_value  # noqa: E402

# Named so the learned weights can be read, which is the point of keeping the
# feature set small enough to inspect.
TEAM_FEATURES = [
    "units", "stars", "cost", "health", "armor", "magic_resist",
    "attack_damage", "ability_power", "attack_speed", "dps", "effective_hp",
    "ranged", "items", "traits", "trait_tiers",
]


def team_vector(units, data) -> np.ndarray:
    """Aggregate one board. Never returned alone -- only as a difference."""
    if not units:
        return np.zeros(len(TEAM_FEATURES))
    stats = [u.derived_stats() for u in units]
    active = active_traits(units, data)
    dps = sum(s.attack_damage * s.attack_speed for s in stats)
    # Armor and MR are diminishing, so raw sums mislead; effective HP is the
    # quantity combat actually spends.
    ehp = sum(s.max_health * (1 + s.armor / 100) for s in stats)
    return np.array([
        len(units),
        sum(u.star_level for u in units),
        sum(u.champion.cost for u in units),
        sum(s.max_health for s in stats),
        sum(s.armor for s in stats),
        sum(s.magic_resist for s in stats),
        sum(s.attack_damage for s in stats),
        sum(s.ability_power for s in stats),
        sum(s.attack_speed for s in stats),
        dps,
        ehp,
        sum(1 for s in stats if s.attack_range > 1),
        sum(len(u.items) for u in units),
        len(active),
        sum(b.count for b in active.values()),
    ], dtype=float)


def features(team0, team1, data) -> np.ndarray:
    """Relational: differences and ratios, never the boards themselves."""
    a, b = team_vector(team0, data), team_vector(team1, data)
    diff = a - b
    # Ratios carry scale-free advantage; a 1000-HP lead means something
    # different at stage 2 and stage 6.
    total = np.where((a + b) == 0, 1.0, a + b)
    ratio = (a - b) / total
    return np.concatenate([diff, ratio])


def generate(data, states: int, seed: int, trials: int = 1):
    """Labelled fights from real mid-game boards, all seat pairs at each state.

    `trials > 1` averages several fights per matchup, which is how the test set
    is built: a single fight is a noisy draw from the matchup's true value, and
    scoring against noise understates any model. The train set stays at one
    fight per matchup -- more distinct matchups beats cleaner labels there.
    """
    rows, labels = [], []
    rng = random.Random(seed)
    game = 0
    while len(rows) < states * 40:
        policies = [GreedyPolicy(seed=s, econ=DEFAULT_FIELD[s % len(DEFAULT_FIELD)])
                    for s in range(8)]
        match = Match(data, policies, seed=seed * 1000 + game)
        game += 1
        rounds = 0
        while not match.finished and rounds < 22:
            match.play_round()
            rounds += 1
            live = [p for p in match.players if p.alive and p.board]
            if len(live) < 2:
                break
            for a in live:
                b = rng.choice([p for p in live if p is not a])
                t0 = clone_board(match, a, 0)
                t1 = clone_board(match, b, 1)
                rows.append(features(t0, t1, data))
                draws = [fight_value(
                    data, a.hex_board,
                    clone_board(match, a, 0), clone_board(match, b, 1),
                    rng.randrange(2**31)) for _ in range(trials)]
                labels.append(sum(draws) / len(draws))
        print(f"  game {game}: {len(rows)} labelled fights", flush=True)
    return np.array(rows), np.array(labels)


def measure_ceiling(data, samples: int, seed: int, trials: int) -> float:
    """How much of a fight's outcome is predictable at all.

    A single fight is one draw from a matchup's distribution. Variance splits
    into *between-matchup* (what any model could learn) and *within-matchup*
    (combat randomness, which nothing can). The best achievable R^2 against
    a `trials`-averaged label is between / (between + within/trials).

    Measured before the model is scored, because a rate without its achievable
    maximum is uninterpretable -- this project's most repeated lesson.
    """
    rng = random.Random(seed + 991)
    per_matchup = []
    game = 0
    while len(per_matchup) < samples:
        policies = [GreedyPolicy(seed=s, econ=DEFAULT_FIELD[s % len(DEFAULT_FIELD)])
                    for s in range(8)]
        match = Match(data, policies, seed=90_000 + seed * 100 + game)
        game += 1
        rounds = 0
        while not match.finished and rounds < 22 and len(per_matchup) < samples:
            match.play_round()
            rounds += 1
            live = [p for p in match.players if p.alive and p.board]
            if len(live) < 2:
                break
            a = rng.choice(live)
            b = rng.choice([p for p in live if p is not a])
            draws = [fight_value(
                data, a.hex_board,
                clone_board(match, a, 0), clone_board(match, b, 1),
                rng.randrange(2**31)) for _ in range(8)]
            per_matchup.append(draws)

    means = [sum(d) / len(d) for d in per_matchup]
    within = statistics.mean(statistics.variance(d) for d in per_matchup)
    between = statistics.variance(means) - within / 8
    between = max(between, 0.0)
    best = between / (between + within / trials) if between else 0.0
    print(f"\nceiling: {len(per_matchup)} matchups x 8 fights -- "
          f"between-matchup var {between:.2f}, within-matchup var "
          f"{within:.2f}")
    print(f"best achievable R^2 against a {trials}-fight label: {best:.2f}")
    return best


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--states", type=int, default=40)
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--test-trials", type=int, default=5,
                        help="fights averaged per test matchup; see `generate`")
    parser.add_argument("--ceiling-samples", type=int, default=60)
    parser.add_argument("--cache", type=Path, default=None,
                        help="npz to load the dataset from, or write it to")
    parser.add_argument("--patience", type=int, default=20)
    parser.add_argument("--save", type=Path, default=None,
                        help="write weights + feature normalisation for reuse")
    args = parser.parse_args()

    import torch

    data = load_all()
    if args.cache and args.cache.exists():
        blob = np.load(args.cache)
        X, y, Xte_raw, yte_raw = (blob["X"], blob["y"],
                                  blob["Xte"], blob["yte"])
        ceiling = float(blob["ceiling"])
        print(f"loaded {len(X)} train / {len(Xte_raw)} test from {args.cache}")
    else:
        ceiling = measure_ceiling(data, args.ceiling_samples, args.seed,
                                  args.test_trials)
        X, y = generate(data, args.states, args.seed)
        Xte_raw, yte_raw = generate(data, max(args.states // 4, 1),
                                    args.seed + 7777, trials=args.test_trials)
        if args.cache:
            np.savez(args.cache, X=X, y=y, Xte=Xte_raw, yte=yte_raw,
                     ceiling=ceiling)
            print(f"wrote dataset to {args.cache}")
    print(f"\n{len(X)} labelled fights, {X.shape[1]} relational features")
    print(f"label: mean {y.mean():+.2f}, sd {y.std():.2f}")

    X = np.concatenate([X, Xte_raw])
    y = np.concatenate([y, yte_raw])
    split = len(X) - len(Xte_raw)
    mu, sd = X[:split].mean(0), X[:split].std(0) + 1e-8
    Xtr = torch.tensor((X[:split] - mu) / sd, dtype=torch.float32)
    ytr = torch.tensor(y[:split], dtype=torch.float32).unsqueeze(1)
    Xte = torch.tensor((X[split:] - mu) / sd, dtype=torch.float32)
    yte = torch.tensor(y[split:], dtype=torch.float32).unsqueeze(1)

    # Baselines first: a rate is uninterpretable without its achievable
    # maximum, and a model that cannot beat "predict the mean" or "count the
    # units" is not worth the milliseconds it saves.
    var = float(((yte - ytr.mean()) ** 2).mean())
    units_only = X[split:, TEAM_FEATURES.index("units")]
    scale = float(np.polyfit(X[:split, TEAM_FEATURES.index("units")],
                             y[:split], 1)[0])
    offset = float(np.polyfit(X[:split, TEAM_FEATURES.index("units")],
                              y[:split], 1)[1])
    unit_mse = float(((y[split:] - (units_only * scale + offset)) ** 2).mean())

    # **Early stopping on a validation split carved from the training data.**
    # A first version trained a fixed 200 epochs and reported the last one; the
    # test loss bottomed at epoch 100 (5.988) and rose to 6.760 by 200, so the
    # reported number was an overfit model. Selecting the best *test* epoch
    # instead would leak the test set, which is the other way to get this wrong.
    cut = int(0.85 * len(Xtr))
    Xva, yva = Xtr[cut:], ytr[cut:]
    Xtr, ytr = Xtr[:cut], ytr[:cut]

    model = torch.nn.Sequential(
        torch.nn.Linear(Xtr.shape[1], 64), torch.nn.ReLU(),
        torch.nn.Linear(64, 64), torch.nn.ReLU(),
        torch.nn.Linear(64, 1))
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    best_val, best_state, stale, best_epoch = float("inf"), None, 0, 0
    for epoch in range(args.epochs):
        perm = torch.randperm(len(Xtr))
        for i in range(0, len(Xtr), 256):
            idx = perm[i:i + 256]
            opt.zero_grad()
            loss = torch.nn.functional.mse_loss(model(Xtr[idx]), ytr[idx])
            loss.backward()
            opt.step()
        with torch.no_grad():
            val = torch.nn.functional.mse_loss(model(Xva), yva).item()
        if val < best_val - 1e-4:
            best_val, best_epoch, stale = val, epoch + 1, 0
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
        else:
            stale += 1
            if stale >= args.patience:
                break
    if best_state is not None:
        model.load_state_dict(best_state)
    print(f"  early stop: best val mse {best_val:.3f} at epoch {best_epoch}",
          flush=True)

    with torch.no_grad():
        pred = model(Xte).squeeze(1).numpy()
    mse = float(((pred - y[split:]) ** 2).mean())
    sign = float(np.mean(np.sign(pred) == np.sign(y[split:])))

    print(f"\n{'predictor':>26}{'test mse':>11}{'R^2':>8}{'sign acc':>10}")
    print(f"{'predict the mean':>26}{var:>11.3f}{0.0:>8.2f}{'--':>10}")
    print(f"{'unit-count only (linear)':>26}{unit_mse:>11.3f}"
          f"{1 - unit_mse / var:>8.2f}{'--':>10}")
    mse_r2 = 1 - mse / var
    print(f"{'relational MLP':>26}{mse:>11.3f}{mse_r2:>8.2f}{sign:>10.1%}")
    if args.save:
        # Normalisation travels with the weights: a consumer that standardises
        # differently is running a different model.
        torch.save({"state": model.state_dict(), "mu": mu, "sd": sd,
                    "features": TEAM_FEATURES, "r2": mse_r2,
                    "sign_acc": sign, "ceiling": ceiling}, args.save)
        print(f"saved surrogate to {args.save}")

    share = f"{mse_r2 / ceiling:.0%}" if ceiling else "--"
    print(f"\nachievable R^2 {ceiling:.2f}; the MLP reaches {share} of it.")


if __name__ == "__main__":
    main()
