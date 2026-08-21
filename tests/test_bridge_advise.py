"""Validation and the advisory CLI (doc 04 milestone 4).

Until a vision pipeline exists, `ObservedState` files are typed by a person
(doc 04 sec 3), so the most likely failure is a misspelled `champion_id`. It
must produce an actionable message naming the value and the nearest real ids --
not a `KeyError` from inside the adapter.
"""

from __future__ import annotations

import dataclasses
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from bridge.adapter import validate  # noqa: E402
from bridge.state import ObservedSeat, ObservedState, ObservedUnit  # noqa: E402
from engine.loader import load_all  # noqa: E402
from tests.paths import REAL_DATA_DIR  # noqa: E402


@pytest.fixture(scope="module")
def data():
    return load_all(REAL_DATA_DIR)


def _state(data, **hero) -> ObservedState:
    real = sorted(data.champions)[0]
    seat = ObservedSeat(board=[ObservedUnit(champion_id=real, star_level=1)],
                        bench=[], bench_slots=9)
    return ObservedState(stage=4, round=2,
                         hero=dataclasses.replace(seat, **hero))


def test_a_valid_state_reports_nothing(data):
    """Guards the others: a clean state must not produce noise."""
    assert validate(_state(data), data) == []


def test_a_misspelled_champion_names_the_nearest_real_ids(data):
    """The typo must not *contain* the real id, or the test proves nothing.

    A first version used `real + "x"`, so the real name was a substring of the
    misspelling and `real in problems[0]` passed on the quoted bad value alone
    -- a mutation removing the suggestions survived. Transposing the last
    character keeps the ids close enough for `difflib` while making the real
    name absent from the bad one.
    """
    real = sorted(data.champions)[0]
    typo = real[:-1] + "z"
    assert real not in typo, "the typo still contains the real id"
    bad = _state(data, board=[ObservedUnit(champion_id=typo)])
    problems = validate(bad, data)
    assert len(problems) == 1
    assert typo in problems[0], "the offending value is not quoted back"
    assert "Did you mean" in problems[0], "no suggestion offered"
    assert real in problems[0], (
        f"the nearest real id is not suggested: {problems[0]!r}"
    )


def test_a_four_star_is_rejected_and_explained(data):
    """Real TFT has 4-stars and this engine does not (doc 99 entry 132.4)."""
    real = sorted(data.champions)[0]
    bad = _state(data, board=[ObservedUnit(champion_id=real, star_level=4)])
    problems = validate(bad, data)
    assert problems and "4" in problems[0]
    assert "132.4" in problems[0], (
        "a 4-star must point at the entry explaining why it is unsupported"
    )


def test_unknown_items_and_shop_entries_are_caught(data):
    real = sorted(data.champions)[0]
    state = _state(data, board=[ObservedUnit(champion_id=real,
                                             items=("not_an_item",))])
    state.shop = ["not_a_champion"]
    problems = validate(state, data)
    assert any("not_an_item" in p for p in problems)
    assert any("not_a_champion" in p for p in problems)


def test_the_cli_refuses_a_bad_state_with_a_useful_message(tmp_path, data):
    """End to end, because the message only helps if the CLI actually prints it."""
    real = sorted(data.champions)[0]
    bad = _state(data, board=[ObservedUnit(champion_id=real + "x")])
    path = tmp_path / "bad.json"
    path.write_text(bad.to_json())

    result = subprocess.run(
        [sys.executable, "scripts/advise.py", str(path)],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert result.returncode != 0, "a bad state file exited successfully"
    assert "unknown champion" in result.stderr
    assert "Traceback" not in result.stderr, (
        "a hand-editable file must fail with a message, not a stack trace"
    )


def test_the_cli_advises_on_a_captured_state(tmp_path):
    """The template -> advise path a person actually walks."""
    path = tmp_path / "template.json"
    made = subprocess.run(
        [sys.executable, "scripts/advise.py", "--template", str(path)],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert made.returncode == 0, made.stderr[-2000:]
    assert path.exists()

    shown = subprocess.run(
        [sys.executable, "scripts/advise.py", str(path)],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert shown.returncode == 0, shown.stderr[-2000:]
    assert "action" in shown.stdout
    assert "not advice" in shown.stdout, (
        "without a model the output must say it is not advice"
    )


# --- board search at inference (doc 99 entry 135) -------------------------

def _own_hexes():
    from engine.hexgrid import Board

    return sorted((h.q, h.r) for h in Board().half_board_hexes(0))


def _registry(data):
    from engine.items import ItemRegistry

    return ItemRegistry(data.items, data.config.max_items_per_unit)


def test_an_invalid_hex_position_is_caught_before_it_reaches_combat(data):
    """`(0, 0)` is not an own hex, and the first template shipped it.

    It encodes fine and then raises "slot (row=-4, col=0) is outside the 7x4
    half-board" from inside `Match._clone_board` the moment the board search
    runs. The message has to arrive where the person can act on it.
    """
    real = sorted(data.champions)[0]
    bad = _state(data, board=[ObservedUnit(champion_id=real, position=(0, 0))])
    problems = validate(bad, data)
    assert problems and "position" in problems[0]
    assert "own-half" in problems[0]


def test_a_valid_hex_position_passes(data):
    """Guards the case above: real coordinates must not be reported."""
    real = sorted(data.champions)[0]
    ok = _state(data, board=[ObservedUnit(champion_id=real,
                                          position=_own_hexes()[0])])
    assert validate(ok, data) == []


def test_the_template_is_itself_valid(data):
    """The example a person copies must not be the one that breaks.

    The first template used `(0, 0)`. This is the regression test for that,
    and it checks the shipped artefact rather than a reconstruction of it.
    """
    from scripts.advise import template

    assert validate(template(data), data) == []


def test_board_search_fields_an_obviously_better_unit(data):
    """A search that can only answer "no change" proves nothing.

    Two 1-cost 1-stars on the board and two 5-cost 3-stars on the bench: an
    engine that cannot find this improvement is broken, not agreeing. This is
    the case that found the invalid-hex bug.
    """
    from bridge.decide import board_advice

    own = _own_hexes()
    cheap = sorted(c.id for c in data.champions.values() if c.cost == 1)
    strong = sorted(c.id for c in data.champions.values() if c.cost == 5)
    hero = ObservedSeat(
        player_id=0, gold=50, level=8, hp=80,
        board=[ObservedUnit(cheap[0], 1, position=own[0]),
               ObservedUnit(cheap[1], 1, position=own[1])],
        bench=[ObservedUnit(strong[0], 3), ObservedUnit(strong[1], 3)],
        bench_slots=9)
    opponent = ObservedSeat(player_id=1, level=8, hp=80,
                            board=[ObservedUnit(cheap[2], 1, position=own[0])])
    state = ObservedState(stage=4, round=2, hero=hero,
                          opponents=[opponent, opponent, opponent])

    swaps = board_advice(state, data, _registry(data))
    assert swaps, "the search found no improvement over two 1-cost 1-stars"
    fielded = {champion.rstrip("*") for champion, _where in swaps}
    assert fielded <= {strong[0], strong[1]}, (
        f"search fielded something other than the 5-cost 3-stars: {swaps}"
    )


def test_board_search_declines_when_the_board_is_full_and_strong(data):
    """The other half: "no change" must be reachable.

    Without it, the test above is also satisfied by a search that always swaps
    something. The board must be **full** for this: level sets
    `max_board_units`, so at level 8 with two units there are six free slots
    and fielding *any* spare body is a real improvement -- the first version of
    this test asserted "no change" on a two-unit level-8 board and failed
    correctly. Level 2 makes two units a full board.
    """
    from bridge.decide import board_advice

    own = _own_hexes()
    strong = sorted(c.id for c in data.champions.values() if c.cost == 5)
    cheap = sorted(c.id for c in data.champions.values() if c.cost == 1)
    hero = ObservedSeat(
        player_id=0, level=2, hp=80,
        board=[ObservedUnit(strong[0], 3, position=own[0]),
               ObservedUnit(strong[1], 3, position=own[1])],
        bench=[ObservedUnit(cheap[0], 1)], bench_slots=9)
    opponent = ObservedSeat(player_id=1, level=2, hp=80,
                            board=[ObservedUnit(cheap[1], 1, position=own[0])])
    state = ObservedState(stage=4, round=2, hero=hero,
                          opponents=[opponent, opponent])
    assert board_advice(state, data, _registry(data)) == []


def test_advisor_search_margin_tracks_panel_size():
    """`margin` is not panel-invariant, so the two must move together (136.3).

    `best_board.score()` divides by `trials` but not by `panel_size`, so its
    `margin` is a threshold on the summed margin over the panel. Widening the
    advisor's panel without raising `margin` would silently loosen the firing
    rule -- the search would fire more often rather than search better, which
    is the confound that made the first budget table unreadable.
    """
    from bridge.decide import ADVISOR_SEARCH

    per_fight = 0.25          # 0.5 summed over `best_board`'s default panel of 2
    assert ADVISOR_SEARCH["margin"] == per_fight * ADVISOR_SEARCH["panel_size"], (
        "the advisor's margin no longer matches its panel size; see entry 136.3"
    )


def test_board_advice_works_with_no_opponents_entered(data):
    """A state with no opponents still gets advice, via the mirror panel (137.2).

    This is the typed path's load-bearing case: entering eight opponent boards
    per round is not something a person will do, and before the mirror fallback
    this state returned nothing at all -- `opponent_panel` came back empty and
    `best_board` bailed immediately.
    """
    from bridge.decide import board_advice

    own = _own_hexes()
    cheap = sorted(c.id for c in data.champions.values() if c.cost == 1)
    strong = sorted(c.id for c in data.champions.values() if c.cost == 5)
    hero = ObservedSeat(
        player_id=0, gold=50, level=8, hp=80,
        board=[ObservedUnit(cheap[0], 1, position=own[0]),
               ObservedUnit(cheap[1], 1, position=own[1])],
        bench=[ObservedUnit(strong[0], 3), ObservedUnit(strong[1], 3)],
        bench_slots=9)
    state = ObservedState(stage=4, round=2, hero=hero, opponents=[])

    advice = board_advice(state, data, _registry(data))
    assert advice, (
        "no advice without opponents -- the mirror fallback is not firing"
    )
    assert all(where.startswith("board ") for _champion, where in advice)


def test_shop_advice_prefers_completing_a_pair(data):
    """A third copy is a 2-star; a lone 1-cost is not (entry 143).

    The case that must return something: the shop offers a champion the player
    already holds two 1-star copies of, alongside an unrelated 1-cost. If the
    pair-completing buy does not rank first, the star-level modelling is wrong
    and the advice is worse than useless -- it would send a player's gold at
    the unit that helps least.

    **The board must be full**, which the first version of this test got wrong
    in exactly the way 135.3 did. With a free slot, buying any body makes the
    board bigger while completing a pair keeps it the same size, and board size
    dominates (67, 68, 72) -- so the filler correctly wins and the test proves
    nothing about star levels. At level 2 with two units fielded the choice is
    upgrade-in-place against swap-one-for-one, which is the question asked.
    """
    from bridge.decide import shop_advice

    own = _own_hexes()
    cheap = sorted(c.id for c in data.champions.values() if c.cost == 1)
    pair, filler, other = cheap[0], cheap[1], cheap[2]
    hero = ObservedSeat(
        player_id=0, gold=50, level=2, hp=80,
        board=[ObservedUnit(pair, 1, position=own[0]),
               ObservedUnit(filler, 1, position=own[1])],
        bench=[ObservedUnit(pair, 1)], bench_slots=9)
    opponent = ObservedSeat(player_id=1, level=2, hp=80,
                            board=[ObservedUnit(other, 1, position=own[0])])
    state = ObservedState(stage=3, round=2, hero=hero, opponents=[opponent],
                          shop=[pair, other, None, None, None])

    advice = shop_advice(state, data, _registry(data))
    assert advice, "no shop advice at all"
    top = advice[0][0]
    assert top == f"{pair}**", (
        f"the pair-completing buy did not rank first: {advice}"
    )


def test_shop_advice_skips_unaffordable_and_unknown(data):
    """Gold is a hard constraint; unknown ids must not crash the advisor."""
    from bridge.decide import shop_advice

    own = _own_hexes()
    cheap = sorted(c.id for c in data.champions.values() if c.cost == 1)
    dear = sorted(c.id for c in data.champions.values() if c.cost == 5)[0]
    hero = ObservedSeat(
        player_id=0, gold=1, level=6, hp=80,
        board=[ObservedUnit(cheap[0], 1, position=own[0])],
        bench=[], bench_slots=9)
    opponent = ObservedSeat(player_id=1, level=6, hp=80,
                            board=[ObservedUnit(cheap[1], 1, position=own[0])])
    state = ObservedState(stage=3, round=2, hero=hero, opponents=[opponent],
                          shop=[dear, "TFT17_NotAChampion", cheap[0]])

    advice = shop_advice(state, data, _registry(data))
    names = {champion.rstrip("*") for champion, _cost, _value in advice}
    assert dear not in names, "advised a purchase the player cannot afford"
    assert "TFT17_NotAChampion" not in names, "an unknown id reached the output"
    assert names <= {cheap[0]}
