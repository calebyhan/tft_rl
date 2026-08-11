"""Fight the boards the archetypes actually build (doc 99 entry 113).

No idealisation: capture each seat's final board -- champions, star levels and
items -- from real games, then replay one archetype's boards against another's.
Placement statistics carry an economy, a shop and an elimination order; this
carries none of them.

**The same-archetype rows are controls and are not optional.** They must land
near 50% and 0.00 by symmetry. The first version of this probe mirrored the
board twice -- `place_team` treats row 0 as the front line for *both* teams and
`Board.to_combat` does the flip -- which put team 0's melee in its back row. The
control read 35.6% with a -2.38 margin and would otherwise have been reported as
a finding about archetypes (doc 99 entry 113.1).

    .venv/bin/python scripts/board_matchup_probe.py 150 400
"""
import dataclasses
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from collections import defaultdict

from engine.combat import CombatSimulator, place_team
from engine.hexgrid import Board
from engine.items import ItemRegistry
from engine.loader import load_all
from engine.match import Match
from engine.unit import UnitInstance
from rl.opponents import DEFAULT_FIELD, GreedyPolicy

GAMES = int(sys.argv[1]) if len(sys.argv) > 1 else 150
FIGHTS = int(sys.argv[2]) if len(sys.argv) > 2 else 400
# Third argument strips every champion's traits, so no breakpoint can activate
# on either side (doc 99 entry 113.5). Boards are still *captured* from normal
# games -- the archetypes must build what they really build -- and only the
# replayed fight is trait-free, which isolates the traits' contribution to the
# slot's worth from their contribution to how the board was assembled.
NO_TRAITS = len(sys.argv) > 3 and sys.argv[3] == "--no-traits"
data = load_all()
capture_data = data
if NO_TRAITS:
    # Emptying `data.traits` instead would make `active_traits` warn once per
    # unknown trait per call; stripping the champions' trait tuples produces no
    # traits to look up at all.
    data = dataclasses.replace(data, champions={
        cid: dataclasses.replace(c, traits=())
        for cid, c in data.champions.items()
    })

# --- capture -------------------------------------------------------------
boards = defaultdict(list)
for game in range(GAMES):
    match = Match(capture_data,
                  [GreedyPolicy(seed=s, econ=DEFAULT_FIELD[s]) for s in range(8)],
                  seed=game)
    final = {}
    while not match.finished:
        for p in match.living_players:
            final[p.player_id] = [
                (u.champion.id, u.star_level, tuple(i.id for i in u.items))
                for u in p.board_units]
        match.play_round()
    for i, p in enumerate(match.players):
        spec = final.get(p.player_id)
        if spec:
            boards[DEFAULT_FIELD[i].name].append(spec)

# place_team: row 0 is the front line for BOTH teams; to_combat mirrors.
FRONT = [(0, c) for c in range(7)]
BACK = [(1, c) for c in range(7)]
EFRONT = FRONT
EBACK = BACK

def build(spec, registry, board, team):
    units, slots = [], []
    f = FRONT if team == 0 else EFRONT
    b = BACK if team == 0 else EBACK
    nf = nb = 0
    for cid, star, item_ids in spec:
        champ = data.champions[cid]
        if champ.stats.attack_range <= 1 and nf < len(f):
            slots.append(f[nf])
            nf += 1
        elif nb < len(b):
            slots.append(b[nb])
            nb += 1
        else:
            slots.append(f[nf])
            nf += 1
        units.append(UnitInstance(
            champ, star, [data.items[i] for i in item_ids], registry=registry))
    return place_team(units, slots, team=team, board=board)

def fight(spec_l, spec_r, seed):
    reg = ItemRegistry(data.items, data.config.max_items_per_unit)
    bd = Board()
    t0 = build(spec_l, reg, bd, 0)
    t1 = build(spec_r, reg, bd, 1)
    CombatSimulator(t0, t1, data, seed=seed, board=bd).run()
    return sum(1 for u in t0 if u.alive), sum(1 for u in t1 if u.alive)

def value(spec):
    return sum(data.champions[c].cost * 3 ** (s - 1) for c, s, _ in spec)

def items(spec):
    return sum(len(i) for _, _, i in spec)

rng = random.Random(0)
def series(a, b, label):
    wins = marg = 0.0
    va = vb = ua = ub = ia = ib = 0.0
    for k in range(FIGHTS):
        sl = rng.choice(boards[a])
        sr = rng.choice(boards[b])
        al, ar = fight(sl, sr, seed=k)
        wins += 1.0 if al > ar else 0.5 if al == ar else 0.0
        marg += al - ar
        va += value(sl)
        vb += value(sr)
        ua += len(sl)
        ub += len(sr)
        ia += items(sl)
        ib += items(sr)
    print(f"{label:<34}{wins/FIGHTS:>8.1%}{marg/FIGHTS:>+9.2f}"
          f"{va/FIGHTS:>9.1f}{vb/FIGHTS:>9.1f}{ua/FIGHTS:>8.2f}{ub/FIGHTS:>8.2f}"
          f"{ia/FIGHTS:>8.2f}{ib/FIGHTS:>8.2f}")

print(f"{GAMES} games captured; {FIGHTS} fights per row"
      + ("  [TRAITS DISABLED in the replayed fight]" if NO_TRAITS else "") + "\n")
for k in sorted(boards):
    print(f"  {k}: {len(boards[k])} boards")
print(f"\n{'matchup':<34}{'win':>8}{'margin':>9}{'valL':>9}{'valR':>9}"
      f"{'nL':>8}{'nR':>8}{'itemL':>8}{'itemR':>8}")
series("slowroll6", "standard", "slowroll6 vs standard")
series("standard", "standard", "standard vs standard (control)")
series("slowroll6", "slowroll6", "slowroll6 vs slowroll6 (control)")
series("fast8", "standard", "fast8 vs standard")
