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

import hashlib
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
    drops: Sequence = (),
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
        # `drops` is the multi-swap form (entry 106). Kept separate from
        # `drop` rather than overloading it: a Hex is tuple-like, so
        # "is this one hex or a sequence of hexes" cannot be decided by
        # isinstance without a latent bug.
        for extra_drop in drops:
            player.board.pop(extra_drop, None)
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
    def visible_board_signature(opponent: PlayerState):
        """Canonical tie-break made only of facts present in scout tokens."""
        return tuple(
            (
                hex_.q,
                hex_.r,
                unit.champion.id,
                unit.star_level,
                tuple(item.id for item in unit.items),
            )
            for hex_, unit in sorted(opponent.board.items())
        )

    others = [
        p for p in match.players
        if p.player_id != player.player_id and p.alive and p.board
    ]
    # The earlier final ``player_id`` tie-break made the teacher's label depend
    # on an arbitrary hidden implementation field.  When equal-HP, equal-size
    # boards exchanged ids, the token observation was identical but ``best_buy``
    # changed (doc 99 entry 160.25).  The signature is purely visible board
    # data, so it retains deterministic selection without leaking a policy
    # score or an unobservable seat feature into the student.
    others.sort(key=lambda p: (-len(p.board), -p.hp, visible_board_signature(p)))
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


def best_board(
    env,
    rng: random.Random,
    max_swaps: int = 3,
    max_candidates: int = 6,
    panel_size: int = 2,
    margin: float = 0.5,
    trials: int = 3,
    panel_fn=None,
) -> list[tuple[UnitInstance, object]] | None:
    """Multi-action board search: change several units at once, not one.

    `best_swap` moves a single bench unit onto the board. That is *one action*,
    and entry 91 measured 1,098 single-action counterfactuals at max |t| = 1.82
    -- single actions do not move placement. So 54's +0.307 is roughly the
    ceiling of that shape of search, and widening it buys precision on a
    decision that does not matter (105.3).

    91 only tested single actions. This changes up to ``max_swaps`` at once for
    the same **one combat per candidate**, which is the untested hypothesis: that
    placement responds to board-level changes while being insensitive to
    unit-level ones, as "board size dominates" (67, 68, 72) would predict.

    Returns the swaps as ``(unit, target_hex)`` pairs -- by *unit*, not bench
    index, because executing the first swap displaces a board unit back onto the
    bench and renumbers everything after it.
    """
    player = env.player
    match = env.match
    if match is None or not player.board:
        return None

    # `panel_fn` lets a caller supply opponents it did not have to observe --
    # the bridge uses it to fight a mirror of the player's own board when no
    # opponents were entered (entry 137.2). Defaults to the real field, so the
    # teacher's behaviour is unchanged.
    panel = (panel_fn or opponent_panel)(match, player, panel_size)
    if not panel:
        return None

    board = player.hex_board
    data = player.data
    seeds = [[rng.randrange(2**31) for _ in range(trials)] for _ in panel]

    def score(extra=(), drops=()) -> float:
        total = 0.0
        for other, trial_seeds in zip(panel, seeds, strict=True):
            for seed in trial_seeds:
                total += fight_value(
                    data, board,
                    clone_board(match, player, 0, extra=extra, drops=drops),
                    clone_board(match, other, 1),
                    seed,
                )
        return total / max(trials, 1)

    benched = [u for u in player.bench if u is not None]
    if not benched:
        return None
    benched.sort(key=lambda u: (-u.star_level, -u.champion.cost))
    benched = benched[:max_candidates]

    weakest = sorted(
        player.board,
        key=lambda h: (player.board[h].star_level, player.board[h].champion.cost),
    )

    def build(units) -> tuple[tuple, tuple] | None:
        """Place `units`, filling free hexes first then replacing weak ones."""
        free = [h for h in sorted(player._own_hexes) if h not in player.board]
        room = player.max_board_units - len(player.board)
        extra, drops, taken = [], [], 0
        for unit in units:
            if room > 0 and free:
                extra.append((unit, free.pop(0)))
                room -= 1
            elif taken < len(weakest):
                hex_ = weakest[taken]
                taken += 1
                extra.append((unit, hex_))
                drops.append(hex_)
            else:
                return None
        return tuple(extra), tuple(drops)

    baseline = score()
    best: tuple[float, tuple] | None = None
    seen: set[tuple] = set()
    for size in range(1, min(max_swaps, len(benched)) + 1):
        # The strongest `size` benched units, plus one random subset of the same
        # size for diversity -- greedy-by-strength alone would never try a
        # trait-completing combination of weaker units.
        subsets = [tuple(benched[:size])]
        if len(benched) > size:
            subsets.append(tuple(rng.sample(benched, size)))
        for units in subsets:
            key = tuple(id(u) for u in units)
            if key in seen:
                continue
            seen.add(key)
            built = build(units)
            if built is None:
                continue
            extra, drops = built
            value = score(extra=extra, drops=drops)
            if best is None or value > best[0]:
                best = (value, extra)

    if best is None or best[0] <= baseline + margin:
        return None
    return list(best[1])


def buy_candidates(player: PlayerState, match, max_candidates: int = 5):
    """Legal first-shop purchases as their exact hypothetical board changes.

    This is intentionally a fact-level expansion of a legal action, not a
    score.  Search, advisors, and candidate-value supervision must construct
    the identical resulting board (including a pair completion) before they
    can make comparable decisions (doc 99 entry 160.33).
    """
    from engine.unit import UnitInstance

    free = [hex_ for hex_ in sorted(player._own_hexes) if hex_ not in player.board]
    weakest = min(
        player.board,
        key=lambda hex_: (player.board[hex_].star_level, player.board[hex_].champion.cost),
    )
    for slot, champion_id in enumerate(player.shop.slots[:max_candidates]):
        if champion_id is None or not player.can_buy(slot):
            continue
        champion = player.data.champions[champion_id]
        held = sum(
            1 for unit in player.all_units
            if unit.champion.id == champion_id and unit.star_level == 1
        )
        star = 2 if held >= 2 else 1
        unit = UnitInstance(champion, star, [], registry=match.registry)
        if len(player.board) < player.max_board_units and free:
            extra, drops = ((unit, free[0]),), ()
        else:
            extra, drops = ((unit, weakest),), (weakest,)
        if star == 2:
            pair = [
                hex_ for hex_, board_unit in player.board.items()
                if board_unit.champion.id == champion_id and board_unit.star_level == 1
            ]
            drops = tuple({*drops, *pair[:2]})
        yield slot, extra, drops


def item_candidates(player: PlayerState, max_candidates: int = 4):
    """First bagged item and bounded legal board targets, without a score.

    This is the candidate contract for both the existing direct item search and
    item-value supervision: component combination is evaluated only after the
    item is equipped on a clone, never approximated by an item-strength rule
    (doc 99 entry 160.58).
    """
    if not player.item_bag or not player.board:
        return None
    item = player.item_bag[0]
    cap = player.config.max_items_per_unit
    targets = [
        hex_ for hex_ in sorted(player.board)
        if len(player.board[hex_].items) < cap
        and player.can_equip_from_bag(item.id, player.board[hex_])
    ]
    targets.sort(key=lambda hex_: (-player.board[hex_].star_level, -player.board[hex_].champion.cost))
    if not targets:
        return None
    return item, tuple(targets[:max_candidates])


def best_buy(env, rng: random.Random, panel_size: int = 2, trials: int = 2,
             margin: float = 0.25, max_candidates: int = 5) -> int | None:
    """Which shop slot to buy, decided by simulating the fight (entry 150).

    Returns a shop slot index, or `None` when no affordable unit beats the
    current board by `margin` per fight. Mirrors `scripts/search_teacher_ab.py`'s
    `SearchBuyPolicy`, which measured −1.355 placement at n=200 (144), but
    expressed so it can be reached **through the action space** -- a teacher
    whose decisions cannot be emitted as actions is a teacher no student can
    imitate, which is the whole point of 75's 89% transmission.

    **A purchase is worth what it becomes.** Holding two 1-star copies makes the
    third a 2-star and consumes the pair, so a board copy leaves the board. A
    model that scored every buy as a 1-star would rank the pair-completing
    purchase alongside a filler, which is the most common real decision to get
    wrong (143.1).
    """
    player, match = env.player, env.match
    if match is None or not player.board or not player.free_bench_slots:
        return None
    panel = opponent_panel(match, player, panel_size)
    if not panel:
        return None

    board, data = player.hex_board, player.data
    seeds = [[rng.randrange(2**31) for _ in range(trials)] for _ in panel]

    def score(extra=(), drops=()) -> float:
        total = 0.0
        for other, trial_seeds in zip(panel, seeds, strict=True):
            for seed in trial_seeds:
                total += fight_value(
                    data, board,
                    clone_board(match, player, 0, extra=extra, drops=drops),
                    clone_board(match, other, 1), seed)
        return total / max(trials, 1)

    baseline = score()
    best: tuple[float, int] | None = None
    for slot, extra, drops in buy_candidates(player, match, max_candidates):
        value = score(extra=extra, drops=drops)
        if best is None or value > best[0]:
            best = (value, slot)

    if best is None or best[0] <= baseline + margin * len(panel):
        return None
    return best[1]


def search_policy(env, rng_seed: int = 0, base=None, mode: str = "swap",
                  buy_search: bool = False, buy_kwargs: dict | None = None,
                  **search_kwargs):
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
    bought_this_phase = [False]
    # **Keyed off the round, not the mode's control flow.** A first version
    # cleared this inside the `searched_this_phase` branch, which `mode="none"`
    # returns before reaching -- so the flag latched on the episode's first
    # phase (board still empty, so `best_buy` correctly declined) and the buy
    # search never ran again. It measured +0.000 at t=0.00: byte-identical
    # games, which is what "the feature never fires" looks like (entry 150).
    last_round: list = [None]
    pending_swaps: list[tuple] = []

    def _bench_index_of(unit) -> int | None:
        for index, candidate in enumerate(env.player.bench):
            if candidate is unit:
                return index
        return None

    def _next_swap_action(mask):
        """SELECT the next pending unit, queueing its PLACE. None if stuck."""
        while pending_swaps:
            unit, target_hex = pending_swaps.pop(0)
            index = _bench_index_of(unit)
            if index is None:
                continue  # already fielded, or combined away
            select = space.select_offset + space.slot_for_bench(index)
            if not mask[select]:
                continue
            queued.append(space.place_offset + space.slot_for_hex(target_hex))
            return select
        return None

    def act(obs, mask):
        # Collection diagnostics need to distinguish the once-per-round combat
        # recommendation from ordinary greedy buys.  This is provenance only:
        # it is reset on every action call and never participates in choosing an
        # action (doc 99 entry 160.21).
        act.last_search_buy_slot = None
        here = env.match.round_id if env.match is not None else None
        if here != last_round[0]:
            last_round[0] = here
            bought_this_phase[0] = False
        if queued:
            action = queued.pop(0)
            return action if mask[action] else space.end_index
        if pending_swaps:
            follow_up = _next_swap_action(mask)
            if follow_up is not None:
                return follow_up

        # Direct Match policies resolve a carousel pick before calling
        # ``SearchBuyPolicy.plan``.  The Gym seat sees that pick as an action,
        # so delegate it to the base scheduler before evaluating a shop.  A
        # search buy while the offering is still pending is a different phase
        # order, not an action-space limitation (doc 99 entry 157).
        if env.player.has_pending_offering:
            return inner(obs, mask)

        # The buy is searched **first in the phase**, before the inner teacher
        # spends the gold. 144 measured this worth −1.355 placement, and 149
        # showed it stacks with the board search rather than substituting for
        # it. Emitted as a real BUY so a student can imitate it (entry 150).
        if buy_search and not bought_this_phase[0]:
            bought_this_phase[0] = True
            slot = best_buy(env, rng, **(buy_kwargs or {}))
            if slot is not None:
                act.last_search_buy_slot = slot
                index = space.buy_offset + slot
                if mask[index]:
                    return index

        action = inner(obs, mask)
        if space.decode(action).kind is not ActionKind.END_PLANNING:
            return action

        if searched_this_phase[0]:
            searched_this_phase[0] = False
            return action

        searched_this_phase[0] = True

        if mode == "board":
            swaps = best_board(env, rng, **search_kwargs)
            if not swaps:
                searched_this_phase[0] = False
                return action
            # Queue as (unit, hex) and resolve the bench index at execution
            # time: the first swap displaces a board unit back onto the bench
            # and renumbers every later slot, so indices computed up front go
            # stale mid-sequence.
            pending_swaps.clear()
            pending_swaps.extend(swaps)
            return _next_swap_action(mask) or action

        # **`none` must be explicit.** Any unrecognised mode falls through to
        # `best_swap` below, so a caller asking for "buy search only" silently
        # got a board search too -- which is exactly how a port validation can
        # measure the wrong thing (entry 150).
        if mode == "none":
            searched_this_phase[0] = False
            return action

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


def search_buy_greedy_policy(
    env,
    *,
    econ=None,
    rng_seed: int = 0,
    buy_kwargs: dict | None = None,
):
    """Action-space counterpart to the direct once-per-round search buyer.

    All non-search decisions remain the faithful ``GreedyActionPolicy``.  The
    wrapper adds only ``best_buy`` before that scheduler's first buy phase;
    this is the common-base port required by doc 99 entry 156.
    """
    from rl.evaluate import greedy_action_policy

    policy = search_policy(
        env,
        rng_seed=rng_seed,
        base=greedy_action_policy(env, econ=econ),
        mode="none",
        buy_search=True,
        buy_kwargs=buy_kwargs,
    )
    # SearchBuyPolicy inherits GreedyPolicy's low-HP anvil rule and consumes
    # the same RNG stream for its search draws and anvil tie-breaks. The action
    # wrapper must therefore not use the base scheduler's independent RNG.
    from rl.opponents import _carry_unit

    def choose_component(player, offered):
        carry = _carry_unit(player)
        if carry is not None:
            for component in (item for item in carry.items if item.is_component):
                completions = [
                    candidate for candidate in offered
                    if player.registry.combine(component.id, candidate) is not None
                ]
                if completions:
                    return policy.rng.choice(sorted(completions))
        return policy.rng.choice(sorted(offered))

    policy.choose_component = choose_component
    env.register_external_policy(policy)
    return policy


def best_move(
    env,
    rng: random.Random,
    max_candidates: int = 6,
    panel_size: int = 1,
    margin: float = 0.5,
    trials: int = 3,
    state_seeded: bool = True,
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
    context = move_search_candidates(
        env, rng, max_candidates=max_candidates, panel_size=panel_size,
        trials=trials, state_seeded=state_seeded,
    )
    if context is None or match is None:
        return None
    panel, seeds, moves = context
    # `state_seeded` decides whether this teacher is a *function of the board*.
    #
    # The candidate set is sampled from ~200 legal moves (see below), and with
    # a free-running stream two calls on a byte-identical board consider
    # different candidates. Entry 79.3 measured the consequence: across five
    # streams the search returned five different answers on 55% of states, and
    # agreed with itself only 38.7% of the time. That 38.7% is a hard ceiling
    # on how well any student can imitate it -- the map from observation to
    # action is one-to-many, so cloning can only learn the marginal, which is a
    # blur over many good moves rather than a good move.
    #
    # That last sentence used to continue "...and it is why the search teacher
    # gained 0.330 (78.2) and its clone gained nothing (79.1)". Doc 99 entry
    # 107 refuted the causal half. With seeding on, self-agreement is 100.0%
    # (107.2) -- and the clone's SELECT/PLACE fit is unchanged at 47.7%/45.5%
    # against 79.2's 47.4%/44.5%, with placement still not transmitting. The
    # ceiling was real and worth lifting; it was never what bound the fit.
    #
    # Seeding from the board layout keeps the sampling distribution -- moves
    # are still drawn uniformly, so search *quality* is untouched -- while
    # making the draw reproducible for a given state. `rng` still supplies the
    # stream when `state_seeded=False`, which reproduces every pre-79 number.
    return _best_move_from_context(player, match, panel, seeds, moves, margin, trials)


def move_search_candidates(
    env,
    rng: random.Random,
    max_candidates: int = 6,
    panel_size: int = 1,
    trials: int = 3,
    state_seeded: bool = True,
):
    """Exact legal layouts and matched combat seeds considered by ``best_move``.

    Candidate-value supervision must label the same sampled moves as the live
    teacher; this helper is the shared construction contract (doc 99 entry
    160.54).  It contains legal facts and random sampling only, never a score.
    """
    player, match = env.player, env.match
    if match is None or len(player.board) < 2:
        return None
    panel = opponent_panel(match, player, panel_size)
    if not panel:
        return None
    occupied = sorted(player.board)
    free = [h for h in sorted(player._own_hexes) if h not in player.board]
    if state_seeded:
        # `hash()` is NOT usable here: Python randomises string hashing per
        # process via PYTHONHASHSEED, so the key would differ across the spawn
        # workers `evaluate_scripted_parallel` and `collect_expert_data` use --
        # reintroducing exactly the state-dependence this removes, while
        # looking deterministic in a single-process test.
        key = hashlib.sha256(repr((
            [(str(h), player.board[h].champion.id, player.board[h].star_level)
             for h in occupied],
            [str(h) for h in free],
            [p.player_id for p in panel],
        )).encode()).digest()
        rng = random.Random(int.from_bytes(key[:8], "big"))
    seeds = [[rng.randrange(2**31) for _ in range(trials)] for _ in panel]

    moves: list[tuple[object, object]] = []
    raw_moves: list[tuple[object, object]] = []
    for source in occupied:
        for target in free:
            raw_moves.append((source, target))
        for target in occupied:
            if target != source:
                raw_moves.append((source, target))
    rng.shuffle(raw_moves)
    moves.extend(raw_moves[:max_candidates])
    return panel, seeds, moves


def _best_move_from_context(player, match, panel, seeds, moves, margin, trials):
    """Score a ``move_search_candidates`` result without resampling it."""
    board, data = player.hex_board, player.data

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

    best: tuple[float, object, object] | None = None
    for source, target in moves:
        # Construct after the baseline just as the original ``best_move`` did.
        # Candidate dicts carry unit objects, so constructing them early risks
        # retaining state that a hypothetical combat clone has touched.
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
