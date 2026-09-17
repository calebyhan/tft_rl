"""`ObservedState`: what an observer can see, independent of how it saw it.

Doc 04 sec 2. This is deliberately a *description*, not an engine object: it
carries champion ids and star levels rather than `UnitInstance`s, so it can be
produced by a fixture, a human, an API or a vision pipeline without any of them
importing the engine. `bridge.adapter` is the only thing that turns it into a
`PlayerState`.

Positions are axial `(q, r)` hex coordinates -- the engine's `Hex` -- and are
**optional**: real match data
carries board composition without geometry (doc 04 sec 3), so `None` means "not
observed" and the adapter places the unit itself. That distinction has to
survive serialisation, which is why it is `None` and not a default hex.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ObservedUnit:
    """One champion an observer can see."""

    champion_id: str
    star_level: int = 1
    items: tuple[str, ...] = ()
    # Axial (q, r). None = position not observed, not "position (0, 0)".
    position: tuple[int, int] | None = None


@dataclass
class ObservedSeat:
    """One player's visible state. Opponents fill in far less than the hero."""

    player_id: int = 0
    gold: int = 0
    level: int = 1
    xp: int = 0
    hp: int = 100
    streak_count: int = 0
    streak_type: str = "none"
    board: list[ObservedUnit] = field(default_factory=list)
    # **Positional, with holes.** `ObservationEncoder` reads the bench by index
    # (`player.bench[i]`), so collapsing gaps shifts every later slot and
    # changes the encoded vector. The round-trip test caught exactly that. An
    # observer that can see the bench sees its gaps too, so `None` is a slot.
    bench: list[ObservedUnit | None] = field(default_factory=list)
    bench_slots: int = 0
    # The seat's chosen augments, by id. Part of the observation vector (its
    # own section), and visible to a real observer for their own seat -- the
    # round-trip test caught their absence.
    augments: tuple[str, ...] = ()
    # Unequipped items, in bag order, by id. Visible to a player for their own
    # seat, and read by item search by index (doc 99 entry 160.111), so the
    # order is part of the observation. The encoder never read it, which is why
    # the milestone 1 round trip passed without it.
    item_bag: tuple[str, ...] = ()


@dataclass
class ObservedState:
    """A whole observation: the hero seat, the opponents, and the round."""

    stage: int = 1
    round: int = 1
    hero: ObservedSeat = field(default_factory=ObservedSeat)
    opponents: list[ObservedSeat] = field(default_factory=list)
    shop: list[str | None] = field(default_factory=list)

    def to_json(self, indent: int | None = 1) -> str:
        return json.dumps(asdict(self), indent=indent)

    @classmethod
    def from_json(cls, text: str) -> "ObservedState":
        return cls.from_dict(json.loads(text))

    @classmethod
    def from_dict(cls, raw: dict) -> "ObservedState":
        def seat(entry: dict) -> ObservedSeat:
            fields = dict(entry)
            def unit(u):
                if u is None:
                    return None          # an empty bench slot, not a missing one
                return ObservedUnit(
                    champion_id=u["champion_id"],
                    star_level=u.get("star_level", 1),
                    items=tuple(u.get("items") or ()),
                    position=(tuple(u["position"])
                              if u.get("position") is not None else None),
                )

            fields["board"] = [unit(u) for u in entry.get("board", [])]
            fields["bench"] = [unit(u) for u in entry.get("bench", [])]
            fields["augments"] = tuple(entry.get("augments") or ())
            fields["item_bag"] = tuple(entry.get("item_bag") or ())
            return ObservedSeat(**fields)

        return cls(
            stage=raw.get("stage", 1),
            round=raw.get("round", 1),
            hero=seat(raw.get("hero", {})),
            opponents=[seat(o) for o in raw.get("opponents", [])],
            shop=list(raw.get("shop", [])),
        )

    def write(self, path: Path) -> None:
        path.write_text(self.to_json())

    @classmethod
    def read(cls, path: Path) -> "ObservedState":
        return cls.from_json(path.read_text())
