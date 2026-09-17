"""Advice for one TFT board state (doc 04 milestone 4).

Read-only and advisory. This prints suggestions for a person to act on; it
never touches a game client (doc 04 sec 0, doc 99 entry 131.1).

Riot exposes no live TFT state (entry 132.1), so until a vision pipeline exists
the input is a JSON file describing what you can see. `--template` writes a
skeleton to fill in, and `--capture` produces a real one from an engine game,
which is how the format is best learned.

    .venv/bin/python scripts/advise.py --template my_board.json
    .venv/bin/python scripts/advise.py my_board.json --run runs/bc-econ-s0
    .venv/bin/python scripts/advise.py --capture --run runs/bc-econ-s0
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from bridge.adapter import validate  # noqa: E402
from bridge.decide import board_advice, load_advisor  # noqa: E402
from bridge.state import ObservedSeat, ObservedState, ObservedUnit  # noqa: E402
from engine.loader import load_all  # noqa: E402


def template(data) -> ObservedState:
    """A skeleton with two real champion ids in it, so the format is obvious.

    An empty template teaches nothing about what a `champion_id` looks like,
    and a wrong id is the most likely mistake a person filling this in by hand
    will make.
    """
    ids = sorted(data.champions)[:2]
    # A real own hex. The first template shipped `(0, 0)`, which is not one:
    # it encodes fine and crashes the board search, so the example a person
    # copies has to be valid (doc 99 entry 135.2).
    from engine.hexgrid import Board

    front = sorted(((h.q, h.r) for h in Board().half_board_hexes(0)))[0]
    return ObservedState(
        stage=4, round=2,
        hero=ObservedSeat(
            player_id=0, gold=30, level=7, hp=60,
            board=[ObservedUnit(champion_id=ids[0], star_level=2,
                                position=front)],
            bench=[ObservedUnit(champion_id=ids[1]), None, None,
                   None, None, None, None, None, None],
            bench_slots=9,
        ),
        opponents=[ObservedSeat(player_id=i, level=7, hp=50)
                   for i in range(1, 8)],
        shop=[ids[0], ids[1], None, None, None],
    )


def capture(data, seed: int, stage: int) -> ObservedState:
    """A real state from an engine game -- the format, by example."""
    from bridge.adapter import from_player_state
    from rl.env import TFTEnv
    from rl.evaluate import scripted_policy

    env = TFTEnv(data=data)
    policy = scripted_policy(env, sell_bench=True, buy_synergy=True,
                             match_items=True, corner_carry=True)
    obs, _info = env.reset(seed=seed)
    for _ in range(6000):
        rid = env.match.round_id
        if rid.stage >= stage and env.player.board:
            return from_player_state(
                env.player, rid,
                [p for p in env.match.players
                 if p.player_id != env.player.player_id])
        action = int(policy(obs, env.action_masks()))
        obs, _r, term, trunc, _i = env.step(action)
        if term or trunc:
            break
    raise SystemExit(f"no state reached stage {stage} on seed {seed}")


def show_board(state: ObservedState, data, registry) -> None:
    """Simulated-combat advice: which bench units to field.

    Separate from the policy's ranking because it answers a different question
    and by a different method -- the engine is used here as a **combat
    surrogate** (doc 99 entry 135), not as a learned policy. An empty result is
    a real answer: the search found nothing worth its margin.
    """
    swaps = board_advice(state, data, registry)
    print("\nboard search (simulated fights vs the opponents you listed):")
    if not swaps:
        print("  no change worth making -- your board is fine")
        return
    for champion, where in swaps:
        print(f"  field {champion} -> {where}")


def show_comps(state: ObservedState, band: str = "challenger") -> None:
    """Real-data advice: what challenger boards like yours were holding.

    The only advice in this tool with **no engine in the loop** (entry 148).
    Everything else simulates fights in a simulator whose fidelity to real TFT
    is limited (111-128); this reads 8,000 real seats and reports association.

    Counts are printed with every line on purpose: a recommendation drawn from
    nine boards is noise and the reader cannot tell otherwise.
    """
    from bridge.composition import (
        champion_weights,
        load_seats,
        what_winners_added,
    )

    try:
        seats = load_seats(band)
    except FileNotFoundError as problem:
        print(f"\nno real-game data: {problem}")
        return

    hero = state.hero
    mine = {u.champion_id for u in hero.board}
    mine |= {u.champion_id for u in hero.bench if u is not None}

    weights = champion_weights(seats)
    print(f"\nreal {band} data ({len(seats)} seats) -- association, not cause:")
    held = [(c, *weights[c]) for c in sorted(mine) if c in weights]
    if held:
        print("  your units, by placement association (negative is better):")
        for champion, weight, support in sorted(held, key=lambda r: r[1]):
            print(f"    {champion:<28}{weight:>+7.2f}   n={support}")

    rows, matched, winners = what_winners_added(seats, mine, min_overlap=2)
    if not rows:
        print(f"  no real boards share 2+ of your units (matched {matched})")
        return
    print(f"  of {matched} boards sharing 2+ of your units, {winners} "
          f"top-foured. They also held:")
    for champion, count, share in rows:
        print(f"    {champion:<28}{share:>6.0%} of them   ({count})")


def show_shop(state: ObservedState, data, registry) -> None:
    """Simulated-combat advice: which shop unit to buy.

    Same method as `show_board` and the same caveat -- this is the engine
    fighting with each candidate purchase, not a learned policy ranking it.
    `value` is survivor margin per fight against the board the buy can reach,
    so a negative number is a real answer: that purchase makes the board worse.
    """
    from bridge.decide import shop_advice

    rows = shop_advice(state, data, registry)
    print("\nshop search (survivor margin per fight, best board reachable):")
    if not rows:
        print("  nothing affordable and recognised in the shop")
        return
    for champion, cost, value in rows:
        print(f"  {champion:<28}{cost:>3}g{value:>+8.2f}")


def show_plan(state: ObservedState, data, registry) -> None:
    """The established teacher's four searches, applied in its phase order.

    Buy, then one fielding swap, then the item prefix and the default rule for
    the rest of the bag, then one positioning move -- each applied before the
    next search sees the board, at the teacher's own budgets (doc 99 entry
    160.152). What it does not cover is printed, so a gap reads as a gap.
    """
    from bridge.decide import plan_advice

    plan = plan_advice(state, data, registry)
    print("\nplan -- the established teacher's four searches, in its phase order:")
    if plan.mirror:
        print("  (no opponent boards entered: fought a mirror of your own board,"
              " measured at about 85-89% of the value of entering them;"
              " doc 99 entry 160.161.)")
    if not plan.steps:
        print("  no change worth making")
    for number, step in enumerate(plan.steps, 1):
        print(f"  {number}. {step.phase:<6} {step.detail}")
    if plan.declined:
        print(f"  searched, nothing worth its margin: {', '.join(plan.declined)}")
    for problem in plan.problems:
        print(f"  problem: {problem}")
    print("  not advised here: levelling, rolling, and the base scheduler's "
          "own buys and fielding")


def show(state: ObservedState, advisor, top_k: int) -> None:
    hero = state.hero
    print(f"\nround {state.stage}-{state.round}   level {hero.level}   "
          f"gold {hero.gold}   hp {hero.hp}")
    board = ", ".join(f"{u.champion_id}{'*' * u.star_level}"
                      for u in hero.board) or "(empty)"
    print(f"board: {board}")
    shop = ", ".join(str(s) for s in state.shop if s) or "(empty)"
    print(f"shop:  {shop}")

    recs = advisor.recommend(state, top_k=top_k)
    if not recs:
        print("\nno legal action available.")
        return
    print(f"\n{'#':<3}{'action':<14}{'detail':<38}{'confidence':>11}")
    for rank, rec in enumerate(recs, 1):
        print(f"{rank:<3}{rec.kind:<14}{rec.detail:<38}{rec.probability:>10.1%}")
    if advisor.model is None:
        print("\n(no --run given: these are uniform over legal actions, "
              "not advice)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("state", nargs="?", type=Path,
                        help="JSON file describing the board you can see")
    parser.add_argument("--run", type=Path, default=None,
                        help="a trained run directory; without it, no policy")
    parser.add_argument("--template", type=Path, default=None,
                        help="write a skeleton state file and exit")
    parser.add_argument("--capture", action="store_true",
                        help="advise on a state captured from an engine game")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--stage", type=int, default=3)
    parser.add_argument("--top", type=int, default=6)
    parser.add_argument("--comps", action="store_true",
                        help="what real challenger boards like yours held "
                             "(no engine; entry 148)")
    parser.add_argument("--shop", action="store_true",
                        help="rank shop buys by simulated combat (entry 143)")
    parser.add_argument("--search", action="store_true",
                        help="also run the board search (simulated combat)")
    parser.add_argument("--plan", action="store_true",
                        help="the established teacher's buy, swap, item and "
                             "move searches, in its phase order (entry 160.152)")
    args = parser.parse_args()

    data = load_all()

    if args.template is not None:
        args.template.write_text(template(data).to_json())
        print(f"wrote {args.template}. Champion ids look like "
              f"{sorted(data.champions)[0]!r}.")
        return

    if args.capture:
        state = capture(data, args.seed, args.stage)
    elif args.state is not None:
        state = ObservedState.read(args.state)
    else:
        parser.error("give a state file, --capture, or --template")

    problems = validate(state, data)
    if problems:
        print("this state file cannot be read:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        raise SystemExit(1)

    show(state, load_advisor(data, args.run), args.top)
    if args.comps:
        show_comps(state)
    if args.search or args.shop or args.plan:
        from engine.items import ItemRegistry

        registry = ItemRegistry(data.items, data.config.max_items_per_unit)
        if args.search:
            show_board(state, data, registry)
        if args.shop:
            show_shop(state, data, registry)
        if args.plan:
            show_plan(state, data, registry)


if __name__ == "__main__":
    main()
