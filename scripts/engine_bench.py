"""Throughput and a behavioural fingerprint for the engine (doc 99 entry 95).

Entry 94 closed the last cheap learning-signal direction. The reframe that
followed: **every RL run in this project has seen ~378 games of TFT**
(150k timesteps / 397 steps per episode, at 66 env steps/sec). PPO on a game
with this branching factor is normally given 1e7-1e8 steps. Entries 89-94
measured "no learning signal" at 1e-3 of the usual budget, which is a weaker
claim than it was read as.

So throughput is the binding constraint, and this is the instrument for
changing it. Two numbers, deliberately in one script so they cannot drift
apart:

* **steps/sec** -- the thing being optimised.
* **fingerprint** -- a hash over every combat outcome in the benchmark games.

The fingerprint is the safety rail. Combat is deterministic given a seed
(a standing engine invariant), so *any* optimisation that changes a single tick
changes this hash. Every number in doc 99 was measured against the current
behaviour; an "optimisation" that silently alters combat invalidates all of
them at once and would be nearly impossible to detect afterwards. Run this
before and after, and the hash must be identical.

The benchmark plays the **scripted teacher**, not a random policy. The first
version of this script used seeded-random-legal and placed 8th in all 8 games:
it died in the early stages and never simulated a late-game board. Combat cost
grows with board size and unit count, so that benchmark would have been tuned
against the cheapest rounds in the game. `--policy random` is kept for
comparison but is not the number to optimise against.

    .venv/bin/python scripts/engine_bench.py --games 8 --json runs/bench_before.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def run(games: int, max_steps: int = 5000, policy_name: str = "scripted") -> dict:
    import logging

    from engine.loader import load_all
    from rl.env import TFTEnv

    logging.getLogger("engine.loader").setLevel(logging.ERROR)
    data = load_all()
    env = TFTEnv(data=data, copy_counts=True)

    policy = None
    if policy_name == "scripted":
        from rl.evaluate import scripted_policy
        from rl.opponents import STANDARD

        policy = scripted_policy(
            env, econ=STANDARD, sell_bench=True, buy_synergy=True,
            match_items=True, corner_carry=True,
        )

    digest = hashlib.sha256()
    steps = 0
    placements = []
    per_game = []
    start = time.perf_counter()
    for seed in range(games):
        game_start = time.perf_counter()
        obs, _info = env.reset(seed=seed)
        # Seeded per game, so the action stream is a pure function of `seed`
        # and does not depend on how many games ran before it.
        rng = np.random.default_rng(seed)
        info: dict = {}
        for _ in range(max_steps):
            mask = env.action_mask()
            if policy is not None:
                action = int(policy(obs, mask))
            else:
                legal = np.flatnonzero(mask)
                if not len(legal):
                    break
                action = int(rng.choice(legal))
            obs, _r, terminated, truncated, info = env.step(action)
            steps += 1
            if terminated or truncated:
                break
        # Hash the *outcome* of every seat, not just the agent's: a change
        # inside combat that happens not to move the agent's placement still
        # shows up here.
        for player in env.match.players:
            digest.update(
                f"{seed}|{player.player_id}|{player.hp}|{player.level}|"
                f"{player.gold}|{player.placement}".encode()
            )
        placements.append(info.get("placement") or env.n_players)
        per_game.append(time.perf_counter() - game_start)
    elapsed = time.perf_counter() - start

    return {
        "games": games,
        "steps": steps,
        "seconds": elapsed,
        "steps_per_sec": steps / elapsed,
        "sec_per_game": statistics.mean(per_game),
        "avg_placement": statistics.mean(placements),
        "fingerprint": digest.hexdigest()[:16],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=8)
    parser.add_argument("--policy", choices=("scripted", "random"),
                        default="scripted")
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument("--compare", type=Path, default=None,
                        help="an earlier --json to check against")
    args = parser.parse_args()

    result = run(args.games, policy_name=args.policy)
    result["policy"] = args.policy
    print(f"policy         {args.policy}")
    print(f"games          {result['games']}")
    print(f"steps          {result['steps']}")
    print(f"seconds        {result['seconds']:.1f}")
    print(f"steps/sec      {result['steps_per_sec']:.1f}")
    print(f"sec/game       {result['sec_per_game']:.2f}")
    print(f"placement      {result['avg_placement']:.3f}")
    print(f"fingerprint    {result['fingerprint']}")

    if args.compare and args.compare.exists():
        old = json.loads(args.compare.read_text())
        speedup = result["steps_per_sec"] / old["steps_per_sec"]
        print(f"\nvs {args.compare.name}: {old['steps_per_sec']:.1f} -> "
              f"{result['steps_per_sec']:.1f} steps/sec  ({speedup:.2f}x)")
        if old["fingerprint"] != result["fingerprint"]:
            print(f"!! FINGERPRINT CHANGED  {old['fingerprint']} -> "
                  f"{result['fingerprint']}")
            print("Combat behaviour is not identical. This is not an "
                  "optimisation -- it is a\nbehaviour change, and every "
                  "measurement in doc 99 was taken against the old\nbehaviour. "
                  "Find the difference before trusting the speedup.")
            raise SystemExit(1)
        print("fingerprint identical -- behaviour preserved")

    if args.json:
        args.json.write_text(json.dumps(result, indent=1))
        print(f"\nwrote {args.json}")


if __name__ == "__main__":
    main()
