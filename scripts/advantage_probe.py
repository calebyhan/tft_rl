r"""What do PPO's advantages actually reward? (doc 99 entry 61)

Entry 60 established *what* PPO does -- it converges onto REROLL, an almost
always-legal action with no immediate consequence, and reaches 8.000, the
`do_nothing` baseline exactly. Four mechanisms have been proposed for *why* and
all four were refuted: critic quality (60.1), the entropy bonus (60.1), reward
sparsity (60.4) and a transient 10k improvement that was noise (60.4).

Each of those was a *hypothesis about* the advantages. This measures them.

PPO moves probability mass toward actions with positive advantage. If REROLL
carries systematically positive advantage from the warm start, the drift needs
no further explanation -- the optimiser is doing exactly what it is supposed to
do, and the defect is in the signal rather than the algorithm. If REROLL's
advantage is neutral or negative, then PPO is moving toward it *despite* the
signal, which is a different and much stranger problem.

**The advantages come from PPO's own machinery**, not a reimplementation.
`collect_rollouts` fills the model's real `RolloutBuffer` and calls
`compute_returns_and_advantage` on it, so what is read here is what the
optimiser consumed. Re-deriving GAE would risk measuring a subtly different
quantity and concluding something confident about it -- which is the failure
mode this project has hit repeatedly (45.2, and the 381-vs-418 env rebuild
during entry 60's own investigation).

    .venv/bin/python scripts/advantage_probe.py runs/ws1200 --rollouts 8
"""

from __future__ import annotations

import argparse
import collections
import json
import logging
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def env_kwargs_from(run_dir: Path) -> dict:
    """Read the layout off the checkpoint's sidecar, never module defaults.

    Rebuilding an env from defaults is how three scripts here measured the
    wrong thing (45.2), and it raised a 381-vs-418 shape error during entry
    60's investigation.
    """
    saved = json.loads((run_dir / "metadata.json").read_text())["hyperparameters"]
    return {
        "copy_counts": saved["copy_counts"],
        "champion_encoding": saved["champion_encoding"],
        "scouting": saved["scouting"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--rollouts", type=int, default=8,
                        help="how many n_steps buffers to collect")
    parser.add_argument("--reward-shaping", action="store_true")
    parser.add_argument("--envs", type=int, default=4)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args()

    import torch
    from sb3_contrib import MaskablePPO
    from stable_baselines3.common.callbacks import BaseCallback

    from engine.loader import load_all
    from scripts.train_ppo import ENV_DEFAULTS, make_vec_env

    logging.getLogger("engine.loader").setLevel(logging.ERROR)
    torch.set_num_threads(2)
    data = load_all()

    saved = json.loads((args.run / "metadata.json").read_text())["hyperparameters"]
    # `make_vec_env` builds through `ENV_DEFAULTS`, which training populates
    # from its args and which is empty in any other process. Setting it from
    # the sidecar is the whole point of `env_kwargs_from` -- writing that
    # helper and then not calling it produced a 381-vs-418 shape error here.
    ENV_DEFAULTS.update(env_kwargs_from(args.run))
    ENV_DEFAULTS["shaping_mode"] = saved.get("shaping_mode", "potential")
    ENV_DEFAULTS["shaping_gamma"] = saved.get("gamma", 0.999)
    vec_env = make_vec_env(
        data, args.envs, args.seed, shaping=args.reward_shaping
    )
    model = MaskablePPO.load(args.run / "model", env=vec_env, device="cpu")
    print(f"loaded {args.run.name}: n_steps={model.n_steps} envs={args.envs} "
          f"shaping={args.reward_shaping} (trained with "
          f"shaping={saved.get('reward_shaping')})")

    from rl.action import ActionSpace
    space = ActionSpace(data.config)
    space.bind_board(sorted(vec_env.get_attr("_board_hexes")[0]))

    class _Silent(BaseCallback):
        def _on_step(self) -> bool:
            return True

    callback = _Silent()
    total = model.n_steps * args.envs * args.rollouts
    model._setup_learn(total_timesteps=total, callback=callback)
    callback.init_callback(model)

    by_kind: dict[str, list[float]] = collections.defaultdict(list)
    for i in range(args.rollouts):
        model.collect_rollouts(
            model.env, callback, model.rollout_buffer,
            n_rollout_steps=model.n_steps,
        )
        actions = model.rollout_buffer.actions.reshape(-1).astype(int)
        advantages = model.rollout_buffer.advantages.reshape(-1)
        for action, advantage in zip(actions, advantages, strict=True):
            by_kind[space.decode(int(action)).kind.name].append(float(advantage))
        print(f"  rollout {i + 1}/{args.rollouts}: {len(actions)} transitions",
              flush=True)

    every = [a for v in by_kind.values() for a in v]
    overall = statistics.mean(every)
    print(f"\n{len(every)} transitions; mean advantage {overall:+.4f} "
          f"(PPO normalises per batch, so the sign per *kind* is what matters)")
    print(f"\n{'action kind':<16}{'n':>8}{'share':>8}{'mean adv':>11}"
          f"{'median':>10}{'% positive':>12}")
    rows = sorted(by_kind.items(), key=lambda kv: -statistics.mean(kv[1]))
    summary = {}
    for kind, values in rows:
        positive = sum(1 for v in values if v > 0) / len(values)
        summary[kind] = {
            "n": len(values),
            "mean": statistics.mean(values),
            "median": statistics.median(values),
            "positive_rate": positive,
        }
        print(f"{kind:<16}{len(values):>8}{len(values) / len(every):>8.1%}"
              f"{statistics.mean(values):>11.4f}"
              f"{statistics.median(values):>10.4f}{positive:>12.1%}")

    reroll = summary.get("REROLL")
    # A minimum before any verdict. The first run of this probe printed a
    # confident conclusion off **three** REROLL samples -- the warm start
    # almost never rerolls, which is exactly why the question is interesting
    # and exactly why a handful of draws cannot answer it.
    MIN_SAMPLES = 60
    if reroll is None:
        print("\nREROLL never sampled -- cannot say anything about it here.")
    elif reroll["n"] < MIN_SAMPLES:
        print(
            f"\nREROLL sampled only {reroll['n']} times (mean {reroll['mean']:+.4f}) "
            f"-- below the {MIN_SAMPLES} needed to say anything. Raise "
            "--rollouts, or probe a policy that actually rerolls."
        )
    elif reroll["mean"] > 0 and reroll["mean"] > overall:
        print(
            f"\nREROLL carries above-average advantage ({reroll['mean']:+.4f} vs "
            f"{overall:+.4f} overall). PPO moving toward it needs no further "
            "explanation: the signal says to. The defect is upstream of the "
            "optimiser."
        )
    else:
        print(
            f"\nREROLL's advantage is {reroll['mean']:+.4f} against {overall:+.4f} "
            "overall -- NOT preferentially rewarded. PPO drifts toward it despite "
            "the signal, which the advantages alone do not explain."
        )

    if args.json:
        args.json.write_text(json.dumps(summary, indent=1))
        print(f"per-kind results: {args.json}")


if __name__ == "__main__":
    main()
