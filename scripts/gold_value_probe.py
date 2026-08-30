"""What is a gold worth in combat margin? (doc 99 entry 160.71).

A dose-response calibration, not a learner. At a legality-uniform sampled
planning state the agent seat is granted ``+G`` gold, the frozen greedy policy
plays a fixed number of resolved rounds, and the terminal board is scored by
exact simulation against the then-visible opponent panel.

The grant is an intervention no policy observes and no label contains. It is
the only way to obtain a dose-response curve, because a real player cannot be
handed gold on request.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from engine.loader import load_all  # noqa: E402
from rl.search import clone_board, fight_value, opponent_panel  # noqa: E402
from scripts.reroll_target_calibration import _walk  # noqa: E402


def terminal_margin(env, seeds: list[list[int]], panel_size: int) -> float | None:
    """Exact margin of the current board against the visible panel."""
    player, match = env.player, env.match
    if match is None or not player.board:
        return None
    panel = opponent_panel(match, player, panel_size)
    if not panel:
        return None
    total = 0.0
    for other, trial_seeds in zip(panel, seeds[: len(panel)], strict=False):
        for seed in trial_seeds:
            total += fight_value(
                player.data, player.hex_board,
                clone_board(match, player, 0),
                clone_board(match, other, 1), seed)
    return total / max(len(seeds[0]) if seeds else 1, 1)


def run_arm(data, episode_seed: int, chosen: int, grant: int, args) -> dict | None:
    """Replay to the sampled state, grant ``+G`` gold, play ``R`` rounds."""
    env, policy, _count = _walk(data, episode_seed, args.panel_size, chosen)
    if env is None or env.match is None:
        return None

    before = {
        "gold": env.player.gold,
        "level": env.player.level,
        "hp": env.player.hp,
        "board_units": len(env.player.board),
        "rounds_played": env.match.rounds_played,
    }
    env.player.gold += grant

    seed_rng = random.Random(args.combat_seed + episode_seed)
    seeds = [
        [seed_rng.randrange(2**31) for _ in range(args.trials)]
        for _ in range(args.panel_size)
    ]

    def measure() -> dict:
        return {
            "rounds": env.match.rounds_played - before["rounds_played"],
            "margin": terminal_margin(env, seeds, args.panel_size),
            "gold": env.player.gold,
            "level": env.player.level,
            "hp": env.player.hp,
            "board_units": len(env.player.board),
        }

    # The trajectory is recorded at every round boundary rather than only at
    # the end (doc 99 entry 160.73): one replay then answers every horizon, and
    # the banked-gold diagnostic can be read as a curve instead of a point.
    target = before["rounds_played"] + args.rounds
    observation = env._observe()
    terminated = truncated = False
    trajectory = []
    resolved = env.match.rounds_played
    for _ in range(20000):
        if env.match.rounds_played >= target:
            break
        mask = env.action_masks()
        action = int(policy(observation, mask))
        observation, _reward, terminated, truncated, _info = env.step(action)
        if env.match.rounds_played > resolved:
            resolved = env.match.rounds_played
            trajectory.append(measure())
        if terminated or truncated:
            break

    final = measure()
    return {
        "grant": grant,
        "before": before,
        "rounds_resolved": final["rounds"],
        "episode_ended": bool(terminated or truncated),
        "trajectory": trajectory,
        "margin": final["margin"],
        "gold": final["gold"],
        "level": final["level"],
        "hp": final["hp"],
        "board_units": final["board_units"],
    }


def slope(doses: list[int], values: list[float]) -> float:
    """Least-squares margin-per-gold across the dose axis."""
    mean_dose = statistics.fmean(doses)
    mean_value = statistics.fmean(values)
    denominator = sum((dose - mean_dose) ** 2 for dose in doses)
    if not denominator:
        return 0.0
    return sum(
        (dose - mean_dose) * (value - mean_value)
        for dose, value in zip(doses, values, strict=True)
    ) / denominator


def summarise_dose(records: list[dict], dose: int, control: dict) -> dict:
    """Paired margin/HP/gold deltas of one dose against its own-seed control."""
    paired = [
        record["margin"] - control[record["episode_seed"]]["margin"]
        for record in records
        if record["margin"] is not None
        and control[record["episode_seed"]]["margin"] is not None
    ]
    hp = [
        record["hp"] - control[record["episode_seed"]]["hp"] for record in records
    ]
    kept = [
        record["gold"] - control[record["episode_seed"]]["gold"] for record in records
    ]
    sd = statistics.pstdev(paired) if len(paired) > 1 else 0.0
    se = sd / (len(paired) ** 0.5) if paired else 0.0
    return {
        "grant": dose,
        "n": len(paired),
        "mean_margin_delta": statistics.fmean(paired) if paired else None,
        "se": se,
        "t": (statistics.fmean(paired) / se) if paired and se else None,
        "mean_hp_delta": statistics.fmean(hp) if hp else None,
        # If this tracks the grant, the policy banked it rather than spending it.
        "mean_gold_delta": statistics.fmean(kept) if kept else None,
        "margin_per_gold": (statistics.fmean(paired) / dose) if paired and dose else None,
    }


def _at(record: dict, horizon: int) -> dict | None:
    for point in record.get("trajectory", ()):
        if point["rounds"] == horizon:
            return point
    return None


def horizon_view(by_dose: dict[int, list[dict]], doses: list[int], horizon: int) -> dict:
    """Paired dose effects at one horizon, plus the banked-gold diagnostic.

    Banked fraction is a marginal diagnostic over *all* arms. It is never used
    to filter the estimate: spending is downstream of the grant, so selecting on
    it would condition on a post-treatment variable (doc 99 entries 160.72,
    160.73).
    """
    control = {}
    for record in by_dose[doses[0]]:
        point = _at(record, horizon)
        if point is not None and point["margin"] is not None:
            control[record["episode_seed"]] = point

    rows = []
    for dose in doses:
        pairs = []
        banked = []
        for record in by_dose[dose]:
            point = _at(record, horizon)
            base = control.get(record["episode_seed"])
            if point is None or base is None or point["margin"] is None:
                continue
            pairs.append(point["margin"] - base["margin"])
            if dose:
                banked.append((point["gold"] - base["gold"]) / dose)
        sd = statistics.pstdev(pairs) if len(pairs) > 1 else 0.0
        se = sd / (len(pairs) ** 0.5) if pairs else 0.0
        rows.append({
            "grant": dose,
            "n": len(pairs),
            "mean_margin_delta": statistics.fmean(pairs) if pairs else None,
            "se": se,
            "t": (statistics.fmean(pairs) / se) if pairs and se else None,
            "unchanged": sum(1 for value in pairs if value == 0),
            "banked_fraction": statistics.fmean(banked) if banked else None,
        })
    usable = [row for row in rows if row["mean_margin_delta"] is not None]
    return {
        "horizon": horizon,
        "doses": rows,
        "fitted_lambda": slope(
            [row["grant"] for row in usable],
            [row["mean_margin_delta"] for row in usable],
        ) if len(usable) > 1 else None,
        "monotone": all(
            a["mean_margin_delta"] <= b["mean_margin_delta"]
            for a, b in zip(usable, usable[1:], strict=False)
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episode-seeds", type=int, default=40)
    parser.add_argument("--doses", type=int, nargs="+", default=[0, 2, 5, 10])
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--panel-size", type=int, default=2)
    parser.add_argument("--selection-seed", type=int, default=3)
    parser.add_argument("--combat-seed", type=int, default=7)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    data = load_all()
    by_dose: dict[int, list[dict]] = {dose: [] for dose in args.doses}
    skipped = 0
    for episode_seed in range(args.episode_seeds):
        _env, _policy, qualifying = _walk(data, episode_seed, args.panel_size, None)
        if not qualifying:
            skipped += 1
            continue
        chosen = random.Random(args.selection_seed + episode_seed).randrange(qualifying)
        for dose in args.doses:
            record = run_arm(data, episode_seed, chosen, dose, args)
            if record is None:
                continue
            record["episode_seed"] = episode_seed
            by_dose[dose].append(record)
        print(
            f"seed {episode_seed}: "
            + " ".join(
                f"G{dose}="
                f"{by_dose[dose][-1]['margin'] if by_dose[dose] and by_dose[dose][-1]['margin'] is not None else float('nan'):+.2f}"
                for dose in args.doses
            ),
            flush=True,
        )

    control = {
        record["episode_seed"]: record
        for record in by_dose[args.doses[0]]
        if record["margin"] is not None
    }
    doses = [
        summarise_dose(
            [r for r in by_dose[dose] if r["episode_seed"] in control], dose, control
        )
        for dose in args.doses
    ]
    usable = [d for d in doses if d["mean_margin_delta"] is not None]
    fitted = slope(
        [d["grant"] for d in usable], [d["mean_margin_delta"] for d in usable]
    ) if len(usable) > 1 else None
    monotone = all(
        a["mean_margin_delta"] <= b["mean_margin_delta"]
        for a, b in zip(usable, usable[1:], strict=False)
    )
    payload = {
        "config": vars(args) | {"json": str(args.json) if args.json else None},
        "episodes_skipped": skipped,
        "doses": doses,
        "fitted_lambda_margin_per_gold": fitted,
        "monotone_in_dose": monotone,
        # Primary endpoint is the last horizon; the rest is trajectory, not a
        # set of candidate endpoints (doc 99 entry 160.73).
        "horizons": [
            horizon_view(by_dose, args.doses, horizon)
            for horizon in range(1, args.rounds + 1)
        ],
        "records": by_dose,
    }
    print(json.dumps({k: v for k, v in payload.items() if k != "records"}, indent=2))
    if args.json:
        args.json.write_text(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
