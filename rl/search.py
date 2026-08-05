"""Choose a board by simulating the fight, not by scoring units (doc 99 46).

Every improvement this project has ever measured came from making the teacher
better or from supplying a quantity the observation lacked, and both are now
capped: imitation cannot exceed its teacher, the teacher is at 3.030, and
45.6 showed that raising imitation agreement no longer raises placement.

What has never been tried is **search**. The engine is a fast deterministic
simulator, which is precisely the object a rollout method needs and which most
RL projects do not have. A teacher that picks its board by simulating the
fight optimises placement directly, rather than through a hand-written
lexicographic `(star, cost)` guess about what makes a unit good.

This is the cheapest honest test of that: one ply, one decision. At the end of
planning, consider swapping each benched unit onto the board, simulate the
resulting board against a panel of opponents, and keep the swap only if it
measurably wins more. Everything else about the teacher is untouched, so any
difference is attributable to the search.

**The match RNG is never touched.** `Match._simulate` draws its combat seed
from `self.rng`, so calling it during planning would consume draws the real
game expects and desynchronise everything downstream. Search runs its fights
through a private `random.Random`, which keeps the host game bit-identical to
what it would have been -- verified by a test that plays a full game with the
search running and discards its result.
"""

from __future__ import annotations

import random
from typing import Sequence

from engine.combat import CombatSimulator
from engine.player import PlayerState
from engine.unit import UnitInstance


def clone_board(
    match,
    player: PlayerState,
    team: int,
    extra: Sequence[tuple[UnitInstance, object]] = (),
    drop: object = None,
) -> list[UnitInstance]:
    """Copy a player's fielded board for a hypothetical fight.

    Delegates to ``Match._clone_board`` rather than re-deriving the own-frame to
    battlefield mapping. A first version duplicated that geometry and mirrored
    one team wrong, putting an enemy on top of one of our own units -- the
    engine raised `two units occupy Hex(2,7)` and the bug was entirely in the
    copy. The mapping is subtle enough to be worth having exactly one of, and
    the engine's is the one real ghost fights already use.

    ``drop`` and ``extra`` express a candidate swap. The player's board is
    mutated *and restored* around the call, which is the price of reusing the
    engine's mapping; the restore is unconditional so an exception cannot leave
    the board altered.
    """
    board = dict(player.board)
    try:
        if drop is not None:
            player.board.pop(drop, None)
        for unit, own_hex in extra:
            player.board[own_hex] = unit
        return match._clone_board(player, team)
    finally:
        player.board.clear()
        player.board.update(board)


def fight_value(
    data, board, team0: list[UnitInstance], team1: list[UnitInstance], seed: int
) -> float:
    """Score one hypothetical fight from team 0's point of view.

    Survivors rather than a win flag: a board that wins with four units left is
    better than one that wins with one, and the loser's surviving count is what
    the damage rule charges. Using the margin makes single fights far less noisy
    than a binary outcome, which matters because this is a one-ply search and
    every extra trial costs a full combat simulation.
    """
    if not team0:
        return -99.0
    if not team1:
        return 99.0
    sim = CombatSimulator(team0, team1, data, seed=seed, board=board)
    result = sim.run()
    ours = sum(1 for u in result.survivors if u.team == 0)
    theirs = sum(1 for u in result.survivors if u.team == 1)
    return float(ours - theirs)


def opponent_panel(match, player: PlayerState, size: int) -> list[PlayerState]:
    """Living opponents to test a candidate board against.

    Deliberately *not* the actual next opponent: the pairing is not known during
    planning, and a teacher that used it would be optimising against information
    the student's observation does not contain. Today's repeated finding is that
    a student follows a teacher only where its observation supports the decision
    (38.7, 44.4), so a teacher that cheats is a teacher that cannot be cloned.

    Strongest opponents first -- they discriminate between candidate boards more
    sharply than a nearly-dead seat with two units.
    """
    others = [
        p for p in match.players
        if p.player_id != player.player_id and p.alive and p.board
    ]
    others.sort(key=lambda p: (-len(p.board), -p.hp, p.player_id))
    return others[:size]


def best_swap(
    env,
    rng: random.Random,
    max_candidates: int = 4,
    panel_size: int = 2,
    margin: float = 0.5,
    trials: int = 3,
) -> tuple[int, object] | None:
    """The one-ply search: is any bench unit worth fielding, and for whom?

    Returns ``(bench_index, own_hex_to_replace_or_None)``, or ``None`` when no
    candidate beats the current board by more than ``margin``. The margin is a
    hysteresis term -- without it, noise in a single fight is enough to make the
    teacher churn its board every round.
    """
    player = env.player
    match = env.match
    if match is None or not player.board:
        return None

    panel = opponent_panel(match, player, panel_size)
    if not panel:
        return None

    board = player.hex_board
    data = player.data
    # One seed set per (opponent, trial), drawn once and reused across
    # candidates: comparing candidates on *different* fights would reintroduce
    # the noise this is here to remove.
    seeds = [[rng.randrange(2**31) for _ in range(trials)] for _ in panel]

    def score(extra=(), drop=None) -> float:
        # Both teams are rebuilt for **every** fight. `CombatSimulator.run`
        # moves units, so a team reused across simulations starts from wherever
        # the previous fight left it -- which surfaced as the engine's
        # `two units occupy Hex(2,7)` guard firing on the second evaluation.
        # Cloning is cheap next to simulating; sharing the clones is not.
        total = 0.0
        for other, trial_seeds in zip(panel, seeds, strict=True):
            for seed in trial_seeds:
                total += fight_value(
                    data,
                    board,
                    clone_board(match, player, 0, extra=extra, drop=drop),
                    clone_board(match, other, 1),
                    seed,
                )
        return total / max(trials, 1)

    baseline = score()

    benched = [
        (index, unit)
        for index, unit in enumerate(player.bench)
        if unit is not None
    ]
    if not benched:
        return None
    # Cost is one full combat simulation per candidate per panel member, so the
    # branching factor is kept small and spent on the units most likely to help.
    benched.sort(key=lambda pair: (-pair[1].star_level, -pair[1].champion.cost))
    benched = benched[:max_candidates]

    free_hexes = [h for h in sorted(player._own_hexes) if h not in player.board]
    weakest_hex = min(
        player.board,
        key=lambda h: (player.board[h].star_level, player.board[h].champion.cost),
    )

    best: tuple[float, int, object] | None = None
    for index, unit in benched:
        if len(player.board) < player.max_board_units and free_hexes:
            target, drop = free_hexes[0], None
        else:
            target, drop = weakest_hex, weakest_hex
        value = score(extra=((unit, target),), drop=drop)
        if best is None or value > best[0]:
            best = (value, index, drop)

    if best is None or best[0] <= baseline + margin:
        return None
    return best[1], best[2]


def search_policy(env, rng_seed: int = 0, base=None, mode: str = "swap", **search_kwargs):
    """Wrap a scripted teacher with a one-ply board search.

    The search fires once per planning phase, at the moment the base policy
    would end it, and its result is executed **through the action space** as a
    SELECT then a PLACE. That matters: a teacher whose decisions cannot be
    expressed as actions is a teacher the student cannot imitate, however good
    its boards are.
    """
    from rl.action import ActionKind
    from rl.evaluate import scripted_policy

    space = env.action_space_helper
    inner = base if base is not None else scripted_policy(env)
    rng = random.Random(rng_seed)
    queued: list[int] = []
    searched_this_phase = [False]

    def act(obs, mask):
        if queued:
            action = queued.pop(0)
            return action if mask[action] else space.end_index

        action = inner(obs, mask)
        if space.decode(action).kind is not ActionKind.END_PLANNING:
            return action

        if searched_this_phase[0]:
            searched_this_phase[0] = False
            return action

        searched_this_phase[0] = True

        if mode == "move":
            moved = best_move(env, rng, **search_kwargs)
            if moved is None:
                searched_this_phase[0] = False
                return action
            source, target = moved
            select = space.select_offset + space.slot_for_hex(source)
            place = space.place_offset + space.slot_for_hex(target)
            if not mask[select]:
                searched_this_phase[0] = False
                return action
            queued.append(place)
            return select

        found = best_swap(env, rng, **search_kwargs)
        if found is None:
            searched_this_phase[0] = False
            return action

        bench_index, drop_hex = found
        select = space.select_offset + space.slot_for_bench(bench_index)
        if not mask[select]:
            searched_this_phase[0] = False
            return action

        if drop_hex is not None:
            target = space.place_offset + space.slot_for_hex(drop_hex)
        else:
            free = [h for h in sorted(env.player._own_hexes)
                    if h not in env.player.board]
            if not free:
                searched_this_phase[0] = False
                return action
            target = space.place_offset + space.slot_for_hex(free[0])

        queued.append(target)
        return select

    # Exposed so callers can reseed per episode. The stream is created once per
    # policy, and `evaluate_scripted_parallel` builds one policy per *worker*;
    # with `imap_unordered` the episodes a worker takes -- and their order --
    # vary run to run, so the search's draws did too. Two runs of an identical
    # configuration returned 3.333 and 3.257 (doc 99 entry 54.1). Every search
    # number in 46, 47 and 53 carries that instability.
    act.rng = rng
    return act


def best_move(
    env,
    rng: random.Random,
    max_candidates: int = 6,
    panel_size: int = 1,
    margin: float = 0.5,
    trials: int = 3,
) -> tuple[object, object] | None:
    """Search *where* a unit stands rather than *which* unit is fielded.

    Returns ``(from_hex, to_hex)`` or ``None``. One move per planning phase, so
    it is expressible as a single SELECT then PLACE and a clone can copy it.

    This is the axis 47.2 measured: rearranging the same units moves the fight
    outcome by 2.8x the engine's own noise, and the gap between the best and
    worst arrangement of one board averages 5.78 surviving units. The incumbent
    is `_preferred_hex` -- melee to the front rows, ranged to the back -- which
    is two rules against a space nobody has ever optimised.

    Candidates are sampled rather than enumerated: with 9 fielded units and 28
    own hexes the full move set is far larger than the simulation budget, and
    every candidate costs `panel_size * trials` full fights.
    """
    player = env.player
    match = env.match
    if match is None or len(player.board) < 2:
        return None

    panel = opponent_panel(match, player, panel_size)
    if not panel:
        return None

    board = player.hex_board
    data = player.data
    seeds = [[rng.randrange(2**31) for _ in range(trials)] for _ in panel]
    occupied = sorted(player.board)
    free = [h for h in sorted(player._own_hexes) if h not in player.board]

    def score(layout: dict) -> float:
        original = dict(player.board)
        try:
            player.board.clear()
            player.board.update(layout)
            total = 0.0
            for other, trial_seeds in zip(panel, seeds, strict=True):
                for seed in trial_seeds:
                    total += fight_value(
                        data,
                        board,
                        clone_board(match, player, 0),
                        clone_board(match, other, 1),
                        seed,
                    )
            return total / max(trials, 1)
        finally:
            player.board.clear()
            player.board.update(original)

    baseline = score(dict(player.board))

    # A move is either onto an empty hex or a swap with another unit. Both are
    # one SELECT + one PLACE, so both stay expressible in the action space.
    moves: list[tuple[object, object]] = []
    for source in occupied:
        for target in free:
            moves.append((source, target))
        for target in occupied:
            if target != source:
                moves.append((source, target))
    if not moves:
        return None
    rng.shuffle(moves)

    best: tuple[float, object, object] | None = None
    for source, target in moves[:max_candidates]:
        layout = dict(player.board)
        moving = layout.pop(source)
        displaced = layout.pop(target, None)
        layout[target] = moving
        if displaced is not None:
            layout[source] = displaced
        value = score(layout)
        if best is None or value > best[0]:
            best = (value, source, target)

    if best is None or best[0] <= baseline + margin:
        return None
    return best[1], best[2]
