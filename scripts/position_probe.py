"""Does positioning change anything in this engine? (doc 99 entry 47)

Before searching over *where* to place units, or fixing the positional
targeting gap §36 has carried open, establish that position affects outcomes at
all. Searching a dimension the simulator does not express would find nothing,
and no amount of budget would fix that.

The measurement: hold both boards fixed, re-fight them under many random
arrangements of one side, and look at the spread in outcome. The comparison
that makes the spread interpretable is the **same arrangement re-fought under
different combat seeds** -- that is the engine's own noise. Positioning only
matters if rearranging moves the result by more than reseeding does.

    .venv/bin/python scripts/position_probe.py --boards 12 --layouts 12
"""

from __future__ import annotations

import argparse
import random
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.loader import load_all  # noqa: E402
from rl.action import ActionKind  # noqa: E402
from rl.env import TFTEnv  # noqa: E402
from rl.evaluate import scripted_policy  # noqa: E402
from rl.search import clone_board, fight_value, opponent_panel  # noqa: E402
from rl.timing import timed  # noqa: E402

FLAGS = dict(sell_bench=True, buy_synergy=True, match_items=True, corner_carry=True)


def rearranged(player, rng: random.Random) -> dict:
    """The same units on a random selection of the player's own hexes."""
    units = list(player.board.values())
    hexes = sorted(player._own_hexes)
    return dict(zip(rng.sample(hexes, len(units)), units, strict=True))


def probe_state(env, other, rng, layouts: int, seeds: int) -> tuple[list, list]:
    """Spread from rearranging, and spread from reseeding the same layout."""
    player = env.player
    match = env.match
    board = player.hex_board
    data = player.data
    original = dict(player.board)

    fixed_seed = rng.randrange(2**31)
    layout_values = []
    for _ in range(layouts):
        # Build the new layout *before* clearing: `rearranged` reads
        # `player.board`, and clearing first meant every "layout" was an empty
        # board and every fight value identical -- which read as "positioning
        # does not matter" rather than as a bug.
        layout = rearranged(player, rng)
        player.board.clear()
        player.board.update(layout)
        try:
            layout_values.append(
                fight_value(
                    data, board,
                    clone_board(match, player, 0),
                    clone_board(match, other, 1),
                    fixed_seed,
                )
            )
        finally:
            player.board.clear()
            player.board.update(original)

    # The control: one arrangement -- the player's real one -- refought under
    # different combat seeds. Any spread here is the engine's own variance.
    seed_values = [
        fight_value(
            data, board,
            clone_board(match, player, 0),
            clone_board(match, other, 1),
            rng.randrange(2**31),
        )
        for _ in range(seeds)
    ]
    return layout_values, seed_values


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--boards", type=int, default=12,
                        help="how many distinct game states to sample")
    parser.add_argument("--layouts", type=int, default=12,
                        help="random arrangements per state")
    parser.add_argument("--seeds", type=int, default=12,
                        help="combat seeds per state, for the noise control")
    parser.add_argument("--min-units", type=int, default=4)
    args = parser.parse_args()

    data = load_all()
    rng = random.Random(11)

    layout_sds: list[float] = []
    seed_sds: list[float] = []
    best_minus_worst: list[float] = []

    with timed("position_probe", episodes=args.boards, arms=1):
        env = TFTEnv(data=data)
        policy = scripted_policy(env, **FLAGS)
        sampled = 0
        game = 0
        while sampled < args.boards:
            obs, _ = env.reset(seed=500 + game)
            game += 1
            done = False
            while not done and sampled < args.boards:
                mask = env.action_mask()
                action = policy(obs, mask)
                if env.action_space_helper.decode(action).kind is ActionKind.END_PLANNING:
                    player = env.player
                    panel = opponent_panel(env.match, player, 1)
                    if panel and len(player.board) >= args.min_units:
                        layouts, seeds = probe_state(
                            env, panel[0], rng, args.layouts, args.seeds
                        )
                        if not layouts or all(v <= -99 for v in layouts):
                            raise AssertionError(
                                "every candidate layout scored as an empty "
                                "board -- the rearrangement is not taking"
                            )
                        if len(set(layouts)) > 1 or len(set(seeds)) > 1:
                            layout_sds.append(statistics.pstdev(layouts))
                            seed_sds.append(statistics.pstdev(seeds))
                            best_minus_worst.append(max(layouts) - min(layouts))
                        sampled += 1
                obs, _, done, _, _ = env.step(action)

    if not layout_sds:
        print("no usable states sampled -- try --min-units lower")
        return

    layout = statistics.mean(layout_sds)
    noise = statistics.mean(seed_sds)
    print(f"\nstates sampled: {len(layout_sds)}")
    print(f"  sd from REARRANGING (fixed combat seed) : {layout:.3f}")
    print(f"  sd from RESEEDING   (fixed arrangement) : {noise:.3f}")
    print(f"  best-minus-worst layout, mean over states: "
          f"{statistics.mean(best_minus_worst):.2f} units")
    ratio = layout / noise if noise else float("inf")
    print(f"\n  positioning signal / engine noise = {ratio:.2f}")
    if ratio < 1.2:
        print("  -> rearranging moves the result no more than reseeding does.")
        print("     Positioning is barely expressed by this engine; searching")
        print("     it would be searching noise (doc 99 entry 47).")
    else:
        print("  -> positioning moves outcomes beyond engine noise, so there")
        print("     is something for a positional search to find.")


if __name__ == "__main__":
    main()
