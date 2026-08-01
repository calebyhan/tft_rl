"""PPO training loop (milestone 7, doc 03 sec 3.4).

Uses **MaskablePPO** from ``sb3-contrib`` rather than plain SB3 PPO: the action
space is large and mostly illegal at any given moment, and doc 03 sec 3.2's
design assumes masking. Masking turns "learn the rules of the interface" into a
non-problem so the agent only has to learn strategy.

Tracks win rate and average placement over training, per doc 03 sec 4.

    python scripts/train_ppo.py --timesteps 50000
    python scripts/train_ppo.py --timesteps 200000 --envs 8 --eval-episodes 30
    python scripts/train_ppo.py --baseline-only     # just measure the baselines

Checkpoints are written with a metadata sidecar recording the data version,
hyperparameters and metrics, so a saved model can always be traced back to the
Set/patch it was trained against (doc 02 sec 6).
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import sys
import time
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

from engine.loader import load_all  # noqa: E402
from rl.env import TFTEnv  # noqa: E402
from rl.evaluate import (  # noqa: E402
    end_planning_policy,
    evaluate,
    random_policy,
    sb3_policy,
    scripted_policy,
)

DEFAULT_RUN_DIR = Path("runs")


def build_env(data, seed: int | None = None, **kwargs) -> TFTEnv:
    return TFTEnv(data=data, seed=seed, **kwargs)


def make_vec_env(data, n_envs: int, seed: int, shaping: bool = False):
    from stable_baselines3.common.monitor import Monitor
    from stable_baselines3.common.vec_env import DummyVecEnv

    def factory(rank: int):
        def _init():
            env = build_env(data, seed=seed + rank, reward_shaping=shaping)
            return Monitor(env)

        return _init

    return DummyVecEnv([factory(i) for i in range(n_envs)])


class MetricsCallback:
    """Periodically evaluates the policy and records win rate / avg placement.

    Implemented against SB3's ``BaseCallback`` lazily so importing this module
    does not require torch when only the baselines are being measured.
    """

    def __new__(cls, *args, **kwargs):
        from stable_baselines3.common.callbacks import BaseCallback

        class _Callback(BaseCallback):
            def __init__(self, data, every: int, episodes: int, run_dir: Path, verbose=1):
                super().__init__(verbose)
                self.data = data
                self.every = every
                self.episodes = episodes
                self.run_dir = run_dir
                self.history: list[dict] = []
                self._eval_env = build_env(data)

            def _on_step(self) -> bool:
                if self.num_timesteps % self.every != 0:
                    return True
                self._record()
                return True

            def _record(self) -> None:
                result = evaluate(
                    self._eval_env,
                    sb3_policy(self.model),
                    seeds=range(self.episodes),
                )
                entry = {"timesteps": self.num_timesteps, **result.as_dict()}
                self.history.append(entry)
                self.logger.record("eval/avg_placement", result.avg_placement)
                self.logger.record("eval/win_rate", result.win_rate)
                self.logger.record("eval/top4_rate", result.top4_rate)
                if self.verbose:
                    print(
                        f"[{self.num_timesteps:>8} steps] "
                        f"avg_placement={result.avg_placement:.3f}  "
                        f"win_rate={result.win_rate:.1%}  top4={result.top4_rate:.1%}"
                    )
                (self.run_dir / "metrics.json").write_text(json.dumps(self.history, indent=2))

            def on_training_end(self) -> None:
                self._record()

        return _Callback(*args, **kwargs)


def collect_expert_data(data, episodes: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Record ``(observation, action_mask, action)`` from the scripted policy."""
    env = build_env(data)
    policy = scripted_policy(env)
    observations, masks, actions = [], [], []
    for seed in range(episodes):
        obs, _ = env.reset(seed=10_000 + seed)
        terminated = False
        while not terminated:
            mask = env.action_mask()
            action = policy(obs, mask)
            observations.append(obs.copy())
            masks.append(mask.copy())
            actions.append(action)
            obs, _, terminated, _, _ = env.step(action)
    return np.array(observations), np.array(masks), np.array(actions)


def behaviour_clone(model, data, episodes: int, epochs: int, batch_size: int = 256) -> None:
    """Warm-start the policy by imitating the scripted heuristic.

    With a terminal-only reward an untrained policy places 8th every game, so
    PPO starts with no gradient (see docs/99_judgement_calls.md 6c.2). Even with
    shaping, discovering the BUY -> SELECT -> PLACE chain by chance is slow.
    Behaviour cloning puts the policy in the neighbourhood of competent play
    first; PPO then improves from there rather than from nothing.
    """
    import torch

    obs, masks, actions = collect_expert_data(data, episodes)
    print(f"  collected {len(obs)} expert transitions from {episodes} episodes")

    device = model.device
    obs_t = torch.as_tensor(obs, dtype=torch.float32, device=device)
    mask_t = torch.as_tensor(masks, dtype=torch.bool, device=device)
    action_t = torch.as_tensor(actions, dtype=torch.long, device=device)

    optimiser = torch.optim.Adam(model.policy.parameters(), lr=1e-3)
    n = len(obs_t)
    for epoch in range(epochs):
        permutation = torch.randperm(n, device=device)
        total_loss = 0.0
        correct = 0
        for start in range(0, n, batch_size):
            batch = permutation[start : start + batch_size]
            distribution = model.policy.get_distribution(
                obs_t[batch], action_masks=mask_t[batch]
            )
            log_prob = distribution.log_prob(action_t[batch])
            loss = -log_prob.mean()
            optimiser.zero_grad()
            loss.backward()
            optimiser.step()
            total_loss += float(loss) * len(batch)
            with torch.no_grad():
                predicted = distribution.distribution.logits.argmax(dim=-1)
                correct += int((predicted == action_t[batch]).sum())
        print(
            f"  bc epoch {epoch + 1}/{epochs}: loss={total_loss / n:.4f} "
            f"action_match={correct / n:.1%}"
        )


def measure_baselines(data, episodes: int) -> dict:
    """Doc 03 sec 4: know the floor before claiming the agent learned anything."""
    env = build_env(data)
    rng = random.Random(0)
    baselines = {
        "do_nothing": end_planning_policy(env),
        "random_legal": random_policy(rng),
        "scripted": scripted_policy(env),
    }
    out = {}
    for name, policy in baselines.items():
        result = evaluate(env, policy, seeds=range(episodes))
        out[name] = result.as_dict()
        print(f"{name:>14}: {result.summary()}")
    return out


def write_metadata(run_dir: Path, data, args, metrics: dict, elapsed: float) -> None:
    """CLAUDE.md: store checkpoints with the context needed to interpret them."""
    metadata = {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "elapsed_seconds": round(elapsed, 1),
        "data_version": asdict(data.version),
        "unverified_constants": list(data.config.unverified),
        "hyperparameters": vars(args),
        "metrics": metrics,
        "algorithm": "MaskablePPO (sb3-contrib)",
        "observation_size": build_env(data).observation_space.shape[0],
        "action_space_size": build_env(data).action_space.n,
    }
    (run_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, default=str))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timesteps", type=int, default=50_000)
    parser.add_argument("--envs", type=int, default=4)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--eval-episodes", type=int, default=20)
    parser.add_argument("--eval-every", type=int, default=10_000)
    parser.add_argument("--learning-rate", type=float, default=3e-4)
    parser.add_argument("--n-steps", type=int, default=512)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--gamma", type=float, default=0.999, help="long horizon: ~30 rounds")
    parser.add_argument("--ent-coef", type=float, default=0.01)
    parser.add_argument("--run-dir", type=Path, default=None)
    parser.add_argument("--baseline-only", action="store_true")
    parser.add_argument("--device", default="cpu", help="cpu is faster for small MLPs")
    parser.add_argument("--warm-start", type=int, default=0,
                        help="behaviour-clone from the scripted policy for N episodes first")
    parser.add_argument("--warm-start-epochs", type=int, default=10)
    parser.add_argument(
        "--reward-shaping",
        action="store_true",
        help=(
            "Enable dense survival shaping. Doc 03 sec 3.3 recommends starting "
            "without it, but with a terminal-only reward an untrained policy "
            "places 8th every game, so all returns are identical and PPO gets "
            "no gradient. Shaping is what bootstraps out of that."
        ),
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.ERROR, format="%(levelname)s %(name)s: %(message)s")
    data = load_all()

    print(f"data: set {data.version.set} patch {data.version.patch}")
    print(f"{len(data.champions)} champions, {len(data.traits)} traits, {len(data.items)} items\n")

    print("=== baselines ===")
    baselines = measure_baselines(data, args.eval_episodes)
    if args.baseline_only:
        return 0

    from sb3_contrib import MaskablePPO

    run_dir = args.run_dir or DEFAULT_RUN_DIR / time.strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n=== training -> {run_dir} ===")

    np.random.seed(args.seed)
    random.seed(args.seed)

    vec_env = make_vec_env(data, args.envs, args.seed, shaping=args.reward_shaping)
    model = MaskablePPO(
        "MlpPolicy",
        vec_env,
        learning_rate=args.learning_rate,
        n_steps=args.n_steps,
        batch_size=args.batch_size,
        gamma=args.gamma,
        ent_coef=args.ent_coef,
        seed=args.seed,
        device=args.device,
        verbose=0,
        tensorboard_log=str(run_dir / "tb"),
    )

    started = time.perf_counter()
    if args.warm_start:
        print("\n--- behaviour cloning from the scripted policy ---")
        behaviour_clone(model, data, args.warm_start, args.warm_start_epochs)
        warm = evaluate(build_env(data), sb3_policy(model), seeds=range(args.eval_episodes))
        print(f"  after cloning: {warm.summary()}")
        baselines["after_warm_start"] = warm.as_dict()

    callback = MetricsCallback(data, args.eval_every, args.eval_episodes, run_dir)
    model.learn(total_timesteps=args.timesteps, callback=callback, progress_bar=False)
    elapsed = time.perf_counter() - started

    model.save(run_dir / "model")

    print("\n=== final evaluation ===")
    env = build_env(data)
    final = evaluate(env, sb3_policy(model), seeds=range(args.eval_episodes))
    print(f"     trained: {final.summary()}")
    print(f"   vs random: avg_placement={baselines['random_legal']['avg_placement']:.3f}")
    print(f" vs scripted: avg_placement={baselines['scripted']['avg_placement']:.3f}")

    metrics = {
        "baselines": baselines,
        "final": final.as_dict(),
        "history": callback.history,
    }
    write_metadata(run_dir, data, args, metrics, elapsed)

    improvement = baselines["random_legal"]["avg_placement"] - final.avg_placement
    print(f"\nimprovement over random: {improvement:+.3f} placement")
    print(f"artifacts: {run_dir}/model.zip, metadata.json, metrics.json")
    print(f"trained {args.timesteps} steps in {elapsed:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
