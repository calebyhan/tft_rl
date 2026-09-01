"""Free looks must be free, capped per round, and restored (doc 99 160.84)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import player as player_mod  # noqa: E402
from engine.loader import load_all  # noqa: E402
from scripts import free_look_probe as probe  # noqa: E402
from tests.paths import REAL_DATA_DIR  # noqa: E402


def test_free_looks_raise_rolls_without_spending_gold():
    probe._DATA = load_all(REAL_DATA_DIR)
    try:
        none = probe.play_one((0, 900, "rivals0"))
        some = probe.play_one((5, 900, "rivals0"))
    finally:
        probe._DATA = None

    # The granted resource must actually be consumed, or the probe measures
    # nothing -- the diagnostic 160.72 had to invoke after the fact.
    assert some["rolls"] > none["rolls"]
    # Free looks cost no gold, so the seat cannot end poorer for having rolled
    # more; a paid roll would have drained it.
    assert some["gold"] >= none["gold"]


def test_the_patch_is_removed_even_when_the_game_raises(monkeypatch):
    original = player_mod.PlayerState.reroll

    def explode(self, pool, rng):
        raise RuntimeError("boom")

    monkeypatch.setattr(player_mod.PlayerState, "reroll", explode)
    marker = player_mod.PlayerState.reroll
    probe._DATA = load_all(REAL_DATA_DIR)
    try:
        probe.play_one((2, 900, "rivals0"))
    except RuntimeError:
        pass
    finally:
        probe._DATA = None
    assert player_mod.PlayerState.reroll is marker
    monkeypatch.setattr(player_mod.PlayerState, "reroll", original)
