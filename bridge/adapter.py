"""`ObservedState` <-> `PlayerState` (doc 04 milestone 1).

The bridge's load-bearing component. An adapter that is not provably faithful
makes every measurement downstream of it meaningless, so its test is a
**round-trip through the observation vector**, not a field-by-field comparison:
engine state -> `ObservedState` -> JSON -> engine state -> encode, and the two
vectors must be identical. Comparing fields would pass while silently dropping
whatever the encoder reads and the comparison forgot to check.

`from_player_state` exists for that test and for capturing fixtures. Live use
runs the other direction only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from bridge.state import ObservedSeat, ObservedState, ObservedUnit
from engine.economy import RoundId
from engine.hexgrid import Board, Hex
from engine.player import PlayerState
from engine.unit import UnitInstance

if TYPE_CHECKING:
    from engine.shop import SharedPool


def _unit_to_observed(unit: UnitInstance, position: Hex | None) -> ObservedUnit:
    return ObservedUnit(
        champion_id=unit.champion.id,
        star_level=unit.star_level,
        items=tuple(item.id for item in unit.items),
        position=None if position is None else (position.q, position.r),
    )


def seat_from_player(player: PlayerState) -> ObservedSeat:
    """Capture one seat. Bench gaps are preserved positionally."""
    return ObservedSeat(
        player_id=player.player_id,
        gold=player.gold,
        level=player.level,
        xp=player.xp,
        hp=player.hp,
        streak_count=player.streak_count,
        streak_type=player.streak_type,
        board=[_unit_to_observed(unit, hex_)
               for hex_, unit in sorted(player.board.items(),
                                        key=lambda kv: (kv[0].q, kv[0].r))],
        bench=[None if unit is None else _unit_to_observed(unit, None)
               for unit in player.bench],
        bench_slots=len(player.bench),
        augments=tuple(aug.id for aug in player.augments),
        item_bag=tuple(item.id for item in player.item_bag),
    )


def from_player_state(player: PlayerState, round_id: RoundId,
                      opponents: list[PlayerState] | None = None
                      ) -> ObservedState:
    """Capture a whole observation from engine state (fixtures and tests)."""
    return ObservedState(
        stage=round_id.stage,
        round=round_id.round,
        hero=seat_from_player(player),
        opponents=[seat_from_player(p) for p in (opponents or [])],
        shop=list(player.shop.slots),
    )


def canonicalize_board(player: PlayerState) -> None:
    """Re-insert the board in hex order.

    Search tie-breaks such as ``min(player.board, key=...)`` iterate this dict,
    so its insertion order is a hidden input: the order units happened to enter
    the board. No observer can see it, and the same board typed in a different
    order, or changed by one applied step, would get different advice.
    """
    ordered = sorted(player.board.items())
    player.board.clear()
    player.board.update(ordered)


def seat_to_player(seat: ObservedSeat, data, registry,
                   hex_board: Board | None = None) -> PlayerState:
    """Rebuild a `PlayerState`. Unobserved positions are filled deterministically.

    A unit with `position=None` still has to go *somewhere* for the encoder to
    see it, so free own-hexes are assigned in board order. That is a fabrication
    and it is why `ObservedState` keeps `None` distinct from a real coordinate:
    a caller measuring positional features on reconstructed real-match data
    (doc 04 milestone 2) must be able to tell which positions it invented.
    """
    board_obj = hex_board or Board()
    player = PlayerState(
        data=data,
        registry=registry,
        player_id=seat.player_id,
        gold=seat.gold,
        level=seat.level,
        xp=seat.xp,
        hp=seat.hp,
        streak_count=seat.streak_count,
        streak_type=seat.streak_type,
        bench=[None] * (seat.bench_slots or data.config.bench_size),
        augments=[data.augments[a] for a in seat.augments],
        item_bag=[data.items[i] for i in seat.item_bag],
        hex_board=board_obj,
    )

    def build(observed: ObservedUnit) -> UnitInstance:
        return UnitInstance(
            data.champions[observed.champion_id],
            observed.star_level,
            [data.items[i] for i in observed.items],
            registry=registry,
        )

    taken = {Hex(*u.position) for u in seat.board if u.position is not None}
    free = [h for h in sorted(player._own_hexes, key=lambda h: (h.q, h.r))
            if h not in taken]
    for observed in seat.board:
        unit = build(observed)
        where = Hex(*observed.position) if observed.position else (
            free.pop(0) if free else None)
        if where is None:
            continue                      # more units than the board can hold
        player.board[where] = unit
        unit.position = where
    canonicalize_board(player)

    for index, observed in enumerate(seat.bench):
        if observed is not None and index < len(player.bench):
            player.bench[index] = build(observed)
    return player


def to_player_state(state: ObservedState, data, registry
                    ) -> tuple[PlayerState, RoundId, list[PlayerState]]:
    """The live direction: an observation becomes what the policy consumes."""
    board_obj = Board()
    hero = seat_to_player(state.hero, data, registry, board_obj)
    hero.shop.slots = list(state.shop) or hero.shop.slots
    opponents = [seat_to_player(seat, data, registry, board_obj)
                 for seat in state.opponents]
    return hero, RoundId(state.stage, state.round), opponents


def pool_for(state: ObservedState, data) -> "SharedPool":
    """A `SharedPool` consistent with everything the observation shows.

    An `ObservedState` carries no pool history, and a fresh pool is *wrong* in
    a way that bites immediately: selling a reconstructed unit tries to return
    a copy the pool never issued and raises `ShopError`. So every observed unit
    is taken out of the pool first.

    **Pool state is an inference, not an observation**, and this is the honest
    version of that inference rather than a fiction that happens not to crash:

    * A star level implies copies -- 3 per star, so a 2-star is 3 copies and a
      3-star is 9 (`3 ** (star - 1)`).
    * Only *visible* units can be deducted. An observer sees their own board
      and bench and whatever scouting shows; the rest of the lobby's holdings
      are unknown, so the real pool is always at most this full.
    * Deductions are clamped at what remains. Real data is partial and a 4-star
      unit (doc 99 entry 132.4) implies more copies than the engine models, so
      an over-deduction is possible and must not raise.
    """
    from engine.shop import SharedPool

    pool = SharedPool(data)
    for seat in [state.hero, *state.opponents]:
        for observed in [*seat.board, *seat.bench]:
            if observed is None or observed.champion_id not in data.champions:
                continue
            copies = 3 ** max(observed.star_level - 1, 0)
            pool.take(observed.champion_id,
                      min(copies, pool.remaining(observed.champion_id)))
    return pool


def validate(state: ObservedState, data) -> list[str]:
    """Problems a hand-written `ObservedState` is likely to contain.

    Until a vision pipeline exists these files are typed by a person (doc 04
    sec 3), so the most probable failure is a misspelled `champion_id` -- which
    otherwise surfaces as a bare `KeyError` from deep inside the adapter. Every
    message names the offending value and, for ids, the closest real ones.

    Returns a list of messages; empty means usable.
    """
    import difflib

    problems: list[str] = []
    known = sorted(data.champions)
    # Positions are axial (q, r) and only a subset of the plane is a legal own
    # hex. An invalid one survives encoding untouched and then crashes deep in
    # combat geometry ("slot (row=-4, col=0) is outside the 7x4 half-board")
    # the first time the board search runs -- so it is checked here, where the
    # message can name the file the person wrote.
    own = {(h.q, h.r) for h in Board().half_board_hexes(0)}
    example = sorted(own)[:3]
    seats = [("hero", state.hero)] + [
        (f"opponent {i}", seat) for i, seat in enumerate(state.opponents)]
    for label, seat in seats:
        for where, units in (("board", seat.board), ("bench", seat.bench)):
            for index, unit in enumerate(units):
                if unit is None:
                    continue
                if unit.champion_id not in data.champions:
                    near = difflib.get_close_matches(unit.champion_id, known, 3)
                    hint = f" Did you mean {', '.join(near)}?" if near else ""
                    problems.append(
                        f"{label} {where}[{index}]: unknown champion "
                        f"{unit.champion_id!r}.{hint}")
                if not 1 <= unit.star_level <= 3:
                    problems.append(
                        f"{label} {where}[{index}]: star_level "
                        f"{unit.star_level} is outside 1-3"
                        + (" (real TFT has 4-stars; this engine caps at 3 -- "
                           "doc 99 entry 132.4)" if unit.star_level > 3 else ""))
                if unit.position is not None and tuple(unit.position) not in own:
                    problems.append(
                        f"{label} {where}[{index}]: position "
                        f"{tuple(unit.position)} is not one of the 28 own-half "
                        f"hexes (axial q,r; e.g. {example})")
                for item in unit.items:
                    if item not in data.items:
                        problems.append(
                            f"{label} {where}[{index}]: unknown item {item!r}")
        for slot, item in enumerate(seat.item_bag):
            if item not in data.items:
                problems.append(f"{label} item_bag[{slot}]: unknown item {item!r}")
    for slot, champion_id in enumerate(state.shop):
        if champion_id is not None and champion_id not in data.champions:
            near = difflib.get_close_matches(champion_id, known, 3)
            hint = f" Did you mean {', '.join(near)}?" if near else ""
            problems.append(
                f"shop[{slot}]: unknown champion {champion_id!r}.{hint}")
    return problems
