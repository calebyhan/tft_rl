"""Print an annotated combat log for a scripted fight.

Milestone 3's verification tool: run a deterministic fight and read the log
against doc 01 sec 3 (movement, targeting, attack timers, mana, casts).

    python scripts/demo_combat.py [--seed N] [--scenario duel|skirmish]
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.combat import CombatSimulator, place_team  # noqa: E402
from engine.hexgrid import Board  # noqa: E402
from engine.items import ItemRegistry  # noqa: E402
from engine.loader import load_all  # noqa: E402
from engine.traits import TraitState  # noqa: E402
from engine.unit import UnitInstance  # noqa: E402

SCENARIOS = {
    # A ranged carry in the back line vs a melee tank that has to walk in.
    "duel": (
        [("TFT17_Kindred", 2, (), (3, 3))],
        [("TFT17_Poppy", 2, (), (3, 3))],
    ),
    # Two-a-side with items and an active trait on each board.
    "skirmish": (
        [
            ("TFT17_Jinx", 2, ("TFT_Item_InfinityEdge",), (3, 2)),
            ("TFT17_Kindred", 2, (), (3, 4)),
        ],
        [
            ("TFT17_Poppy", 2, ("TFT_Item_WarmogsArmor",), (0, 3)),
            ("TFT17_Blitzcrank", 2, (), (0, 4)),
        ],
    ),
}


def build(data, registry, board, spec, team):
    units, slots = [], []
    for champion_id, star, item_ids, slot in spec:
        units.append(
            UnitInstance(
                data.champions[champion_id],
                star,
                [data.items[i] for i in item_ids],
                registry=registry,
            )
        )
        slots.append(slot)
    return place_team(units, slots, team=team, board=board)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), default="duel")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

    data = load_all()
    registry = ItemRegistry(data.items, data.config.max_items_per_unit)
    board = Board()
    spec0, spec1 = SCENARIOS[args.scenario]
    team0 = build(data, registry, board, spec0, 0)
    team1 = build(data, registry, board, spec1, 1)

    sim = CombatSimulator(team0, team1, data, seed=args.seed, board=board)

    print(f"=== {args.scenario} (seed {args.seed}) ===\n")
    for team_index, team in enumerate((team0, team1)):
        print(f"Team {team_index}:")
        state = TraitState(team, data)
        for unit in team:
            s = unit.derived_stats()
            items = ", ".join(i.display_name for i in unit.items) or "no items"
            print(
                f"  {unit.name:<12} {unit.champion.role:<9} at {unit.position} "
                f"hp={s.max_health:.0f} ad={s.attack_damage:.0f} as={s.attack_speed:.2f} "
                f"range={s.attack_range} armor={s.armor:.0f} mr={s.magic_resist:.0f} "
                f"mana={s.starting_mana:.0f}/{s.max_mana:.0f} (+{s.mana_per_attack:.0f}/atk) "
                f"[{items}]"
            )
        if state.active:
            traits = ", ".join(
                f"{data.traits[t].display_name} {bp.count}" for t, bp in sorted(state.active.items())
            )
            print(f"  traits: {traits}")
        print()

    result = sim.run()
    print(sim.log.render())
    print()
    print(
        f"--> winner: team {result.winner}  duration: {result.duration:.2f}s  "
        f"ticks: {result.ticks}  timed_out: {result.timed_out}"
    )
    print(f"    survivors: {result.survivor_summary}")
    print(f"    log events: {len(result.log)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
