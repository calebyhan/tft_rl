"""How much of the observation can real data actually fill? (doc 04 milestone 2)

Entry 132: Riot's Live Client Data API does not expose TFT state, so any live
bridge needs a vision pipeline. Before commissioning one, measure what it would
have to extract -- per observation section, not in aggregate (lesson 27).

Method: take real seats from `data/reference/`, build an `ObservedState` from
the fields Riot's match payload actually carries, encode it, and compare each
index against the same seat encoded from a *fully observed* engine state. An
index that is always zero from real data is one real data cannot fill.

The engine arm is the control and it is the point: it says which indices are
fillable *at all*, so a section that is zero in both arms is reported as
structurally empty rather than as a coverage gap.

    .venv/bin/python scripts/bridge_coverage.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from bridge.adapter import to_player_state  # noqa: E402
from bridge.state import ObservedSeat, ObservedState, ObservedUnit  # noqa: E402
from engine.loader import load_all  # noqa: E402
from rl.env import TFTEnv  # noqa: E402
from scripts.reference_profile import champion_costs, unit_cost  # noqa: E402

REFERENCE = REPO_ROOT / "data" / "reference"


def real_states(path: Path, costs: dict[str, int], limit: int):
    """`ObservedState`s built from what Riot's match payload actually carries.

    Present: level, gold_left, units (champion + star). Absent: items, hex
    positions, bench, shop, xp, streak, augments. Absences are left empty
    rather than guessed -- guessing is what this script exists to measure.
    """
    payload = json.loads(path.read_text())
    out = []
    # Real Set 17 data contains **4-star units** -- 0.46% of challenger seats,
    # spread across many champions -- and `UnitInstance` caps at 3
    # (`STAR_LEVELS`). Clamping is the only option, but it is counted and
    # reported rather than silent, because a clamp that nobody sees is a
    # fidelity gap that becomes a fact. See doc 99 entry 132.
    clamped = [0]
    for match in payload["matches"]:
        seats = match["participants"]
        for seat in seats:
            board = [
                ObservedUnit(champion_id=u["character_id"],
                             star_level=min(u.get("tier", 1), 3))
                for u in seat.get("units", [])
                if unit_cost(u, costs) is not None
            ]
            if not board:
                continue
            others = [
                ObservedSeat(player_id=i + 1, level=o["level"],
                             hp=0, gold=o["gold_left"])
                for i, o in enumerate(s for s in seats if s is not seat)
            ]
            out.append(ObservedState(
                stage=5, round=1,
                hero=ObservedSeat(
                    player_id=0, level=seat["level"], gold=seat["gold_left"],
                    hp=0, board=board, bench=[], bench_slots=9),
                opponents=others,
            ))
            clamped[0] += sum(1 for u in seat.get("units", [])
                              if u.get("tier", 1) > 3)
            if len(out) >= limit:
                return out, clamped[0]
    return out, clamped[0]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seats", type=int, default=400)
    parser.add_argument("--control-games", type=int, default=25,
                        help="engine games forming the coverage denominator")
    args = parser.parse_args()

    data = load_all()
    env = TFTEnv(data=data)
    spec = env.encoder.spec
    registry = None

    # --- engine control: fully observed states ---------------------------
    # Across many games, not one. The control defines the denominator -- an
    # index it never touches is scored as unfillable -- so an undersampled
    # control inflates every coverage figure. The first version used 15 states
    # from a single game and reported traits at **250%**, which is impossible
    # and was the tell: 15 states touch 14 of 35 traits, 300 real seats touch
    # all of them.
    from rl.evaluate import scripted_policy
    engine_vecs = []
    for seed in range(args.control_games):
        obs, _info = env.reset(seed=seed)
        policy = scripted_policy(env, sell_bench=True, buy_synergy=True,
                                 match_items=True, corner_carry=True)
        for step in range(4000):
            if step % 29 == 0 and env.player.board:
                registry = env.player.registry
                engine_vecs.append(env.encoder.encode(
                    env.player, env.match.round_id,
                    [p for p in env.match.players
                     if p.player_id != env.player.player_id],
                    env._board_hexes))
            action = int(policy(obs, env.action_masks()))
            obs, _r, term, trunc, _i = env.step(action)
            if term or trunc:
                break
    assert engine_vecs, "no engine control states captured"

    # --- real arm ---------------------------------------------------------
    costs = champion_costs()
    sample = sorted(REFERENCE.glob("matches_challenger_*.json"))[-1]
    states, clamped = real_states(sample, costs, args.seats)
    real_vecs = []
    for state in states:
        hero, rid, opps = to_player_state(state, data, registry)
        real_vecs.append(env.encoder.encode(hero, rid, opps, env._board_hexes))

    engine = np.array(engine_vecs)
    real = np.array(real_vecs)
    e_live = (engine != 0).any(axis=0)
    r_live = (real != 0).any(axis=0)

    print(f"{len(real)} real seats from {sample.name}, "
          f"{len(engine)} engine control states")
    print(f"{clamped} unit(s) clamped from 4-star to 3-star "
          f"(the engine cannot represent them)\n")
    print(f"{'section':<12}{'width':>7}{'engine fills':>14}{'real fills':>12}"
          f"{'coverage':>11}")
    cursor = 0
    for name, width in spec.describe():
        if width == 0:
            continue
        sl = slice(cursor, cursor + width)
        e = int(e_live[sl].sum())
        r = int(r_live[sl].sum())
        # r > e means the control never touched an index real data fills, so
        # the denominator is not saturated and the ratio is not a coverage
        # figure at all. Flag it rather than print a number above 100%.
        cov = "n/a" if not e else ("control!" if r > e else f"{r / e:.0%}")
        print(f"{name:<12}{width:>7}{e:>14}{r:>12}{cov:>11}")
        cursor += width
    print(f"{'TOTAL':<12}{spec.size:>7}{int(e_live.sum()):>14}"
          f"{int(r_live.sum()):>12}"
          f"{int(r_live.sum()) / max(int(e_live.sum()), 1):>10.0%}")
    print("\n'engine fills' = indices ever non-zero with full observation; "
          "'real fills' = same\nfrom Riot's match payload. A section at 0% is "
          "one a vision pipeline must supply.\n'control!' = the engine sample "
          "never filled an index real data does, so the\ndenominator is "
          "undersaturated -- raise --control-games, do not read the ratio.")


if __name__ == "__main__":
    main()
