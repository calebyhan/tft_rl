"""How many copies of one champion can the shop even offer? (doc 99 entry 68.3)

Entry 68 measured 0.0% 3-stars in every arm, at up to 44.8 rolls per game, and
attributed it to the teacher not *targeting* a champion. That is a hypothesis
about the policy. Before building a targeting teacher to test it, measure the
ceiling the policy would be working against -- lesson 2, *a rate is
uninterpretable without its achievable maximum*.

**Copies offered is a hard upper bound on copies obtainable.** A policy can at
best buy every copy the shop shows it. So if the most-offered champion over a
whole game arrives fewer than **9** times, a 3-star is unreachable by any
shopping policy whatsoever, and 68.5's targeting arm is closed before it is
written. If it clears 9 comfortably, targeting is the binding constraint and
the arm is worth building.

This counts *arrivals*, not shop contents: a slot going from X to Y is one
arrival of Y, buying (Y -> None) is not an arrival, and a reroll counts each
non-empty slot it produces. Contention is real -- the seven bots draw from the
same `SharedPool` in live games.

Two ceilings are reported, and the difference between them is the point:

``hindsight``
    Copies of the single best champion over the whole game -- the max over ~63
    champions, chosen after seeing the outcome. This is a **selection effect**
    and overstates what any policy can do, because a real reroll comp must
    commit before it knows which champion the shop will favour.
``commit@K``
    Pick the champion with the most arrivals by round ``K``, then count that
    champion's arrivals over the whole game. A policy committing at round ``K``
    with perfect play and infinite gold cannot beat this.

``bought`` is what the current non-targeting teacher actually converts, in
copies invested in its best champion (a 2-star counts 3).

    .venv/bin/python scripts/copy_ceiling.py --episodes 30 --roll-at-level 6 \
        --max-actions 60
"""

from __future__ import annotations

import argparse
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.loader import load_all  # noqa: E402
from rl.env import TFTEnv  # noqa: E402
from rl.evaluate import scripted_policy  # noqa: E402

TEACHER = {
    "sell_bench": True,
    "buy_synergy": True,
    "match_items": True,
    "corner_carry": True,
}

# A 3-star needs 3 two-stars, each of 3 copies.
COPIES_FOR_THREE_STAR = 9


def run_arm(data, episodes: int, flags: dict, env_kwargs: dict,
            commit_rounds: tuple[int, ...]) -> dict:
    env = TFTEnv(data=data, **env_kwargs)
    policy = scripted_policy(env, **(TEACHER | flags))

    per_game_offered: list[int] = []
    per_game_bought: list[int] = []
    per_game_commit: dict[int, list[int]] = {k: [] for k in commit_rounds}
    rolls: list[int] = []
    reached = 0

    for seed in range(episodes):
        obs, _info = env.reset(seed=seed)
        offered: Counter[str] = Counter()
        # Arrivals restricted to rounds <= k, for each commit point.
        by_commit: dict[int, Counter[str]] = {k: Counter() for k in commit_rounds}
        previous = list(env.player.shop.slots)

        def record(champion_id: str, played: int,
                   offered: Counter = offered,
                   by_commit: dict = by_commit) -> None:
            """One arrival, credited to every commit point it precedes."""
            offered[champion_id] += 1
            for k in commit_rounds:
                if played <= k:
                    by_commit[k][champion_id] += 1

        # The shop rolled during reset is itself a set of arrivals.
        for champion_id in previous:
            if champion_id is not None:
                record(champion_id, 0)

        n_rolls = 0
        peak_bought = 0
        done = False
        while not done:
            action = policy(obs, env.action_masks())
            if action == env.action_space_helper.reroll_index:
                n_rolls += 1
            obs, _reward, done, _trunc, _info = env.step(action)
            if env.match is None:
                break
            played = env.match.rounds_played
            current = list(env.player.shop.slots)
            # A slot changing to a non-empty champion is one arrival. Buying
            # empties a slot, so it never counts; a reroll replaces every slot
            # at once and counts each one it fills.
            for before, after in zip(previous, current, strict=False):
                if after is not None and after != before:
                    record(after, played)
            previous = current

            # Peak copies invested in one champion, sampled while alive. An
            # end-of-episode tally reads 0 for a dead seat, which is a vacuous
            # zero indistinguishable from "converted nothing" -- and it lands
            # on exactly the arms that place worst.
            if env.player.alive:
                held: Counter[str] = Counter()
                for unit in env.player.all_units:
                    held[unit.champion.id] += 3 ** (unit.star_level - 1)
                if held:
                    peak_bought = max(peak_bought, max(held.values()))

        for k in commit_rounds:
            # Commit to the champion leading at round k, then bank everything
            # that champion goes on to be offered for the rest of the game.
            if by_commit[k]:
                choice = max(by_commit[k], key=lambda c: (by_commit[k][c], c))
                per_game_commit[k].append(offered[choice])
            else:
                per_game_commit[k].append(0)

        best_offered = max(offered.values()) if offered else 0
        per_game_offered.append(best_offered)
        per_game_bought.append(peak_bought)
        rolls.append(n_rolls)
        reached += best_offered >= COPIES_FOR_THREE_STAR

    return {
        "max_offered": per_game_offered,
        "max_bought": per_game_bought,
        "commit": per_game_commit,
        "rolls": rolls,
        "reach_rate": reached / episodes,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episodes", type=int, default=30)
    parser.add_argument("--roll-at-level", type=int, nargs="*", default=[0, 6])
    parser.add_argument("--level-cap", type=int, nargs="*", default=[0, 7])
    parser.add_argument(
        "--max-actions",
        type=int,
        nargs="*",
        default=[12, 60],
        help="`max_actions_per_round` values; 12 is the default the agent runs",
    )
    parser.add_argument(
        "--commit-rounds",
        type=int,
        nargs="*",
        default=[6, 10, 14],
        help="rounds at which a targeting policy would pick its champion",
    )
    args = parser.parse_args()

    commit_rounds = tuple(args.commit_rounds)
    data = load_all()
    commit_header = "".join(f"{f'c@{k}':>8}" for k in commit_rounds)
    print(f"{'arm':<22}{'rolls/g':>9}{'hindsight':>11}{commit_header}"
          f"{'bought':>8}{'hs>=9':>7}")
    for budget in args.max_actions:
        for cap in args.level_cap:
            for roll in args.roll_at_level:
                flags = {}
                if roll:
                    flags["roll_at_level"] = roll
                if cap:
                    flags["level_cap"] = cap
                name = (f"a{budget}"
                        + (f"+cap{cap}" if cap else "")
                        + (f"+roll@{roll}" if roll else ""))
                r = run_arm(data, args.episodes, flags,
                            {"max_actions_per_round": budget}, commit_rounds)
                commits = "".join(
                    f"{statistics.mean(r['commit'][k]):>8.2f}"
                    for k in commit_rounds
                )
                print(f"{name:<22}"
                      f"{statistics.mean(r['rolls']):>9.1f}"
                      f"{statistics.mean(r['max_offered']):>11.2f}{commits}"
                      f"{statistics.mean(r['max_bought']):>8.2f}"
                      f"{r['reach_rate']:>7.0%}", flush=True)

    print(f"\nA 3-star needs {COPIES_FOR_THREE_STAR} copies. 'hindsight' is the "
          "best champion chosen after\nthe fact -- a max over ~63 champions, so "
          "it overstates any real policy.\n'c@K' is the honest ceiling: commit "
          "at round K, bank that champion's whole\ngame. If c@K sits well below "
          f"{COPIES_FOR_THREE_STAR}, targeting cannot reach a 3-star and doc 99"
          "\nentry 68.5's arm is closed on arithmetic rather than on a "
          "measurement.")


if __name__ == "__main__":
    main()
