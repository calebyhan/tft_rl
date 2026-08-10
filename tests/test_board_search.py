"""Multi-action board search (doc 99 entry 106).

`best_swap` changes one unit; `best_board` changes several for the same one
combat per candidate. Two things here would fail silently if wrong.

**Multi-drop cloning.** `clone_board` grew a `drops` sequence alongside the
existing single `drop`. They are deliberately separate parameters: a `Hex` is
tuple-like, so "one hex or a sequence of hexes" cannot be decided by
`isinstance` without a latent bug. If `drops` were ignored, every multi-swap
candidate would be scored on a board that still contained the units it was
supposed to replace -- a search evaluating boards it never proposes, producing
plausible numbers.

**Index staleness.** Executing the first swap displaces a board unit back onto
the bench, renumbering every later slot. Swaps are therefore carried as
`(unit, hex)` and the bench index is resolved at execution time. Carrying
indices instead would field the wrong units from the second swap onward.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.loader import load_all  # noqa: E402
from rl.env import TFTEnv  # noqa: E402
from rl.evaluate import scripted_policy  # noqa: E402
from rl.search import best_board, clone_board, search_policy  # noqa: E402
from tests.paths import REAL_DATA_DIR  # noqa: E402


@pytest.fixture(scope="module")
def data():
    return load_all(REAL_DATA_DIR)


def _advance(env, steps: int = 3000):
    """Play the teacher to a **mid-game** state, which is the only place where
    a multi-unit swap is even expressible.

    An earlier version stopped at the first board of 3 with a bench of 3. That
    is level 3, where `max_board_units` is also 3 and the bench holds 1-star
    1-costs -- room is zero, every bench unit is worse than everything fielded,
    and one swap is trivially the least-bad choice. `best_board` returned a
    single swap every time and the test read as a bug in the search. It was a
    bug in the fixture: at level 7 with a nine-unit bench the same code
    proposes 1, 2 and 3 swaps across seeds.
    """
    policy = scripted_policy(env, sell_bench=True)
    obs, _info = env.reset(seed=3)
    for _ in range(steps):
        action = int(policy(obs, env.action_masks()))
        obs, _r, term, trunc, _i = env.step(action)
        if term or trunc:
            return False
        player = env.player
        if player.level >= 7 and sum(u is not None for u in player.bench) >= 3:
            return True
    return False


def test_drops_removes_every_named_hex(data):
    """The multi-drop path must actually drop all of them."""
    env = TFTEnv(data=data)
    assert _advance(env), "fixture never reached a board with a stocked bench"
    player, match = env.player, env.match

    occupied = sorted(player.board)[:2]
    full = clone_board(match, player, 0)
    dropped = clone_board(match, player, 0, drops=tuple(occupied))

    assert len(dropped) == len(full) - 2, (
        f"drops={occupied} removed {len(full) - len(dropped)} units, not 2 -- "
        "the multi-swap candidates are being scored on boards they do not propose"
    )
    # And the player's own board is restored, as the single-drop path promises.
    assert len(player.board) == len(full)


def test_drops_and_drop_compose(data):
    env = TFTEnv(data=data)
    assert _advance(env)
    player, match = env.player, env.match
    hexes = sorted(player.board)
    if len(hexes) < 3:
        pytest.skip("needs a board of at least 3 to drop 1 + 2")

    full = clone_board(match, player, 0)
    both = clone_board(match, player, 0, drop=hexes[0], drops=tuple(hexes[1:3]))
    assert len(both) == len(full) - 3


def test_best_board_returns_units_not_indices(data):
    """Swaps are keyed by unit so execution survives bench renumbering."""
    env = TFTEnv(data=data)
    assert _advance(env)
    swaps = best_board(env, random.Random(0), max_swaps=3, max_candidates=6,
                       panel_size=2, trials=1, margin=-99.0)
    assert swaps, "margin=-99 should force a proposal"
    for unit, target_hex in swaps:
        assert not isinstance(unit, int), (
            "swaps must carry the unit, not a bench index: executing the first "
            "swap renumbers the bench and a stale index fields the wrong unit"
        )
        assert unit in env.player.bench
        assert target_hex in env.player._own_hexes


def test_best_board_can_propose_more_than_one_swap(data):
    """Otherwise this is `best_swap` with extra steps and the A/B is vacuous."""
    env = TFTEnv(data=data)
    assert _advance(env)
    sizes = set()
    for seed in range(8):
        swaps = best_board(env, random.Random(seed), max_swaps=3,
                           max_candidates=6, panel_size=2, trials=1,
                           margin=-99.0)
        if swaps:
            sizes.add(len(swaps))
    assert max(sizes) >= 2, (
        f"best_board only ever proposed {sizes} swaps -- it is not searching "
        "multi-action boards, so entry 106's comparison would measure nothing"
    )


def test_margin_suppresses_marginal_boards(data):
    """A high margin must return nothing, as the hysteresis term promises."""
    env = TFTEnv(data=data)
    assert _advance(env)
    assert best_board(env, random.Random(0), panel_size=2, trials=1,
                      margin=999.0) is None


@pytest.mark.parametrize("mode", ["move", "swap", "board"])
def test_reconstructed_search_configs_are_callable(data, tmp_path, mode):
    """The sidecar round-trip must produce kwargs the search actually accepts.

    Three places have to agree for a search clone to be measured against the
    teacher that labelled it: the training flag, `vars(args)` in the sidecar,
    and `teacher_gap.search_config`. Doc 99 entry 79.5 records this exact
    disagreement shipping three times (37.4, 38.9, 45.2), each time printing a
    plausible table.

    The new failure mode is narrower and louder: `state_seeded` belongs to
    `best_move` alone, so carrying it into `swap` raises TypeError inside a
    `spawn` worker. Checking the dict shape is not enough -- this calls the
    policy, which is what a measurement run does.
    """
    import json

    from scripts.teacher_gap import teacher_config

    run = tmp_path / "run"
    run.mkdir()
    (run / "metadata.json").write_text(json.dumps({"hyperparameters": {
        "expert_reposition": True,
        "expert_reposition_mode": mode,
        "expert_reposition_candidates": 4,
        "expert_reposition_panel": 1,
        "expert_reposition_state_seeded": True,
    }}))
    _expert, _env, search_kwargs = teacher_config(run)
    assert search_kwargs is not None and search_kwargs["mode"] == mode

    env = TFTEnv(data=data)
    policy = search_policy(env, rng_seed=0, trials=1, **search_kwargs)
    obs, _info = env.reset(seed=7)
    for _ in range(400):
        mask = env.action_masks()
        action = int(policy(obs, mask))
        assert mask[action]
        obs, _r, term, trunc, _i = env.step(action)
        if term or trunc:
            break


def test_board_mode_emits_only_legal_actions(data):
    """The executor must never return a masked-out action."""
    env = TFTEnv(data=data)
    policy = search_policy(env, rng_seed=0, mode="board", max_swaps=3,
                           max_candidates=4, panel_size=1, trials=1)
    obs, _info = env.reset(seed=5)
    for _ in range(600):
        mask = env.action_masks()
        action = int(policy(obs, mask))
        assert mask[action], f"search proposed illegal action {action}"
        obs, _r, term, trunc, _i = env.step(action)
        if term or trunc:
            break
