"""One-ply board search (doc 99 entry 46).

Two properties carry the whole approach, and both are the kind that fail
silently:

* the search must not perturb the game it is thinking about -- it runs
  hypothetical fights inside a live match, and a single draw taken from the
  match RNG would desynchronise every round after it;
* the candidate boards it scores must be *copies*, so a search that considers
  fielding a unit does not actually field it.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.loader import load_all  # noqa: E402
from rl.action import ActionKind  # noqa: E402
from rl.env import TFTEnv  # noqa: E402
from rl.evaluate import evaluate, scripted_policy  # noqa: E402
from rl.search import best_move, best_swap, clone_board, search_policy  # noqa: E402
from tests.paths import REAL_DATA_DIR  # noqa: E402

FLAGS = dict(sell_bench=True, buy_synergy=True, match_items=True, corner_carry=True)


@pytest.fixture(scope="module")
def data():
    return load_all(REAL_DATA_DIR)


def _placements(env, policy, seeds):
    return evaluate(env, policy, seeds=seeds).placements


def test_searching_does_not_change_the_game_it_searches_in(data):
    """The load-bearing test: run the search, throw the answer away.

    If the search consumed the match RNG or left the board mutated, the game
    would diverge from the identical game played without it. `Match._simulate`
    draws its combat seed from `self.rng`, so this is a live hazard rather than
    a theoretical one.
    """
    seeds = range(3)

    plain_env = TFTEnv(data=data)
    plain = _placements(plain_env, scripted_policy(plain_env, **FLAGS), seeds)

    probe_env = TFTEnv(data=data)
    inner = scripted_policy(probe_env, **FLAGS)
    space = probe_env.action_space_helper
    rng = random.Random(7)
    calls = [0]

    def searching_but_ignoring(obs, mask):
        action = inner(obs, mask)
        if space.decode(action).kind is ActionKind.END_PLANNING:
            best_swap(probe_env, rng)
            calls[0] += 1
        return action

    probed = _placements(probe_env, searching_but_ignoring, seeds)

    assert calls[0] > 0, "the search never ran, so this asserts nothing"
    assert probed == plain, "searching perturbed the game it was searching in"


def test_scoring_a_candidate_does_not_field_the_unit(data):
    """`clone_board` mutates the player's board and must restore it exactly."""
    env = TFTEnv(data=data)
    policy = scripted_policy(env, **FLAGS)
    obs, _ = env.reset(seed=4)

    checked = 0
    for _ in range(600):
        mask = env.action_mask()
        action = policy(obs, mask)
        player = env.player
        if player.board and any(u is not None for u in player.bench):
            before = dict(player.board)
            bench_unit = next(u for u in player.bench if u is not None)
            target = next(iter(sorted(player.board)))
            clone_board(env.match, player, 0, extra=((bench_unit, target),))
            clone_board(env.match, player, 0, drop=target)
            assert player.board == before, "the board was left modified"
            checked += 1
        obs, _, terminated, truncated, _ = env.step(action)
        if terminated or truncated:
            break
    assert checked > 0, "no state exercised the candidate path"


def test_clone_board_restores_even_when_cloning_raises(data):
    """The restore is in a `finally`, so this must hold through an exception."""
    env = TFTEnv(data=data)
    policy = scripted_policy(env, **FLAGS)
    obs, _ = env.reset(seed=5)
    for _ in range(400):
        if env.player.board:
            break
        obs, _, done, _, _ = env.step(policy(obs, env.action_mask()))
        if done:
            pytest.skip("game ended before a board existed")

    player = env.player
    before = dict(player.board)

    class Boom:
        def __getattr__(self, name):
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        clone_board(Boom(), player, 0, drop=next(iter(sorted(player.board))))
    assert player.board == before


def test_the_search_policy_only_emits_legal_actions(data):
    """It queues a PLACE behind a SELECT; both must still pass the mask."""
    env = TFTEnv(data=data)
    policy = search_policy(env, base=scripted_policy(env, **FLAGS))
    result = evaluate(env, policy, seeds=range(3))
    assert result.illegal_actions == 0
    assert len(result.placements) == 3


def test_the_search_actually_changes_what_gets_played(data):
    """A search that never alters a decision would be an expensive no-op."""
    seeds = range(4)
    plain_env = TFTEnv(data=data)
    plain = _placements(plain_env, scripted_policy(plain_env, **FLAGS), seeds)

    search_env = TFTEnv(data=data)
    searched = _placements(
        search_env, search_policy(search_env, base=scripted_policy(search_env, **FLAGS)),
        seeds,
    )
    assert searched != plain, "the search changed nothing at all"


# --- positional search (doc 99 entry 47) ---------------------------------


def test_positional_search_does_not_change_the_game_it_searches_in(data):
    """Same hazard as the swap search, and `best_move` mutates the board more.

    It rewrites the whole arrangement per candidate rather than adding one
    unit, so a missed restore would corrupt the real board rather than merely
    misreport a score.
    """
    seeds = range(3)

    plain_env = TFTEnv(data=data)
    plain = _placements(plain_env, scripted_policy(plain_env, **FLAGS), seeds)

    probe_env = TFTEnv(data=data)
    inner = scripted_policy(probe_env, **FLAGS)
    space = probe_env.action_space_helper
    rng = random.Random(5)
    calls = [0]

    def searching_but_ignoring(obs, mask):
        action = inner(obs, mask)
        if space.decode(action).kind is ActionKind.END_PLANNING:
            best_move(probe_env, rng)
            calls[0] += 1
        return action

    probed = _placements(probe_env, searching_but_ignoring, seeds)
    assert calls[0] > 0, "the search never ran, so this asserts nothing"
    assert probed == plain, "positional search perturbed its own game"


def test_a_candidate_move_never_loses_or_duplicates_a_unit(data):
    """A swap must permute the board, not drop the displaced unit."""
    env = TFTEnv(data=data)
    policy = scripted_policy(env, **FLAGS)
    obs, _ = env.reset(seed=6)
    rng = random.Random(2)

    checked = 0
    for _ in range(600):
        mask = env.action_mask()
        action = policy(obs, mask)
        player = env.player
        if len(player.board) >= 2:
            before = sorted(id(u) for u in player.board.values())
            best_move(env, rng)
            after = sorted(id(u) for u in player.board.values())
            assert after == before, "the board's units changed during search"
            checked += 1
        obs, _, terminated, truncated, _ = env.step(action)
        if terminated or truncated:
            break
    assert checked > 0


def test_positional_search_emits_only_legal_actions(data):
    env = TFTEnv(data=data)
    policy = search_policy(env, base=scripted_policy(env, **FLAGS), mode="move")
    result = evaluate(env, policy, seeds=range(3))
    assert result.illegal_actions == 0


def test_positional_search_actually_moves_units(data):
    seeds = range(4)
    plain_env = TFTEnv(data=data)
    plain = _placements(plain_env, scripted_policy(plain_env, **FLAGS), seeds)

    moved_env = TFTEnv(data=data)
    moved = _placements(
        moved_env,
        search_policy(moved_env, base=scripted_policy(moved_env, **FLAGS), mode="move"),
        seeds,
    )
    assert moved != plain, "positional search changed nothing at all"


def test_search_policy_exposes_a_reseedable_stream():
    """Parallel evaluation must be able to make the search reproducible.

    `search_policy` owns a `random.Random`, and `evaluate_scripted_parallel`
    builds one policy per worker. With `imap_unordered` the episodes a worker
    receives vary between runs, so without a per-episode reseed the search's
    draws vary too -- two runs of one configuration returned 3.333 and 3.257
    (doc 99 entry 54.1).
    """
    import random as _random

    from engine.loader import load_all
    from rl.env import TFTEnv
    from rl.search import search_policy
    from tests.paths import REAL_DATA_DIR

    env = TFTEnv(data=load_all(REAL_DATA_DIR))
    policy = search_policy(env, mode="move")
    assert isinstance(getattr(policy, "rng", None), _random.Random), (
        "search_policy must expose its stream as `.rng` so callers can reseed "
        "it per episode"
    )
    policy.rng.seed(5)
    first = [policy.rng.random() for _ in range(4)]
    policy.rng.seed(5)
    assert [policy.rng.random() for _ in range(4)] == first


def test_parallel_evaluation_reseeds_a_search_policy_per_episode():
    """The consumer side of the contract above."""
    from pathlib import Path

    source = (Path(__file__).resolve().parent.parent / "rl" / "evaluate.py").read_text()
    assert 'getattr(_WORKER["policy"], "rng", None)' in source, (
        "_parallel_episode must reseed a search policy's stream per episode"
    )
