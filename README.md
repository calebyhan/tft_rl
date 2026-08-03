# tft_rl

A Teamfight Tactics simulator and reinforcement-learning environment, in Python.

The specs in [docs/](docs/) are the source of truth:

- [01_game_mechanics_reference.md](docs/01_game_mechanics_reference.md) — game rules
- [02_data_schema_and_sourcing.md](docs/02_data_schema_and_sourcing.md) — data schema + how real Set 17 data is fetched
- [03_engine_and_rl_architecture.md](docs/03_engine_and_rl_architecture.md) — module layout and build order

[99_judgement_calls.md](docs/99_judgement_calls.md) is a **temporary** log of every
decision the specs did not fully determine — to be reviewed, then folded into
docs 01–03 or deleted.

## Setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest
```

## Progress

Following doc 03 section 4's build order.

| # | Milestone | Status |
|---|-----------|--------|
| 1 | `hexgrid.py` + `schema.py` + `loader.py`, starter dataset | done |
| 2 | `unit.py` + `traits.py` + `items.py`, derived stats | done |
| 3 | `combat.py`, deterministic tick simulation | done |
| 4 | `economy.py` + `shop.py` + `player.py` | done |
| 5 | `match.py` + `scripts/smoke_test.py` | done |
| 6 | `rl/env.py` + `rl/opponents.py` | done |
| 7 | PPO training loop | harness done; agent reaches 6.10 vs 4.36 scripted |
| 8 | Full data swap via `scripts/fetch_cdragon.py` | done — real Set 17: 63 champions, 35 traits, 65 items |
| 9 | Stretch: augments, self-play, board scouting | built; both A/B verdicts later **withdrawn** by milestone 12 |
| 10 | Item acquisition: real PvE fights, loot, equipping | done — items now actually reach units |
| 11 | Realm of the Gods: HP-ordered contested draft | done — lowest HP picks first from a shared line-up |
| 12 | Re-measurement against a frozen engine | done — see the results table below |

## Trying it out

Print an annotated combat log for a deterministic scripted fight:

```bash
python scripts/demo_combat.py --scenario duel --seed 1
python scripts/demo_combat.py --scenario skirmish --seed 3
```

Run full 8-player games and check every engine invariant:

```bash
python scripts/smoke_test.py --games 25 --policy mixed
python scripts/smoke_test.py --games 1 --trace     # round-by-round table
```

Train and evaluate:

```bash
python scripts/train_ppo.py --baseline-only          # measure the baselines
python scripts/train_ppo.py --timesteps 250000 --envs 8 --reward-shaping

# milestone 9 switches -- both measured, neither recommended (see below)
python scripts/train_ppo.py --timesteps 200000 --self-play --self-play-mix 0.5
python scripts/train_ppo.py --timesteps 200000 --scouting full
```

### Baselines (100 games vs 7 heuristic bots, seat 0)

Warm start 400 episodes / 50 epochs, PPO 120k steps.

All rows below are from the **milestone 12 pass**: one frozen engine, one
shared 400/50 warm start, n=300 each.

| policy | avg placement | top 4 | last place |
|---|---|---|---|
| do nothing | 8.000 | 0% | 100% |
| random legal action | 8.000 | 0% | 100% |
| BC + PPO 120k | 6.527 ±0.206 | 13.7% | 43.3% |
| BC + PPO + `--scouting full` | 6.257 ±0.213 | 17.0% | 36.3% |
| BC + PPO + `--self-play` | 5.947 ±0.220 | 20.0% | 28.7% |
| behaviour cloning only | 5.907 ±0.226 | 25.3% | 27.7% |
| scripted heuristic | **4.620 ±0.251** | 46.3% | — |

The scripted heuristic plays *through the action space* and beats parity with
the bots (4.5 = average), which is the check that the environment isn't
handicapping the agent seat.

**PPO makes the agent significantly worse than its own warm start:** +0.620
placement, t=3.97, top-4 halved and last-place up 27.7% → 43.3%, monotone
downhill across twelve checkpoints. Earlier readings called this "no better
than BC"; it is worse than BC. The three confounds that used to explain it —
the floor effect, an untrained critic, and a game with no reachable items —
have all been removed, and the effect grew. See doc 99 entry 22.1.

The one thing that stops it is `--self-play`, which lands statistically level
with the warm start (+0.040, t=0.25) where every other arm degrades. **Nobody
knows why yet** (doc 99 22.3).

### Twelve floats took the clone from 5.833 to teacher parity

The largest result in this project. Four **relational** observation features —
comparisons between things, not descriptions of things:

| clone | placement | top 4 | win | added |
|---|---|---|---|---|
| baseline | 5.833 ±0.238 | 27.3% | 3.7% | — |
| + shop `owned`, `synergy` | 5.063 ±0.263 | 43.0% | 6.3% | 10 floats |
| + unit star/cost rank, `board_full` | **4.567 ±0.247** | **47.0%** | 8.3% | 2 floats |
| scripted teacher | 4.620 ±0.251 | 46.3% | 10.3% | — |

The clone is now **statistically indistinguishable from the policy it imitates**
(−0.053 against ±0.25 intervals). That is parity, not a win. Win rate is still
behind (8.3% vs 10.3%) — a real gap that average placement hides.

All on an unchanged 400-episode budget. For contrast, the `features` encoding
added ~1800 floats across three attempts and lost every time.

**The lesson, after nine milestones of observation work:** every widening that
failed added *description* of entities; every one that worked added a
*comparison* between entities — an identity match against the roster, a dot
product with board trait counts, an ordering among owned units, a threshold
against the unit cap. What located them was feature ablation on ~1k-parameter
probes, not a better architecture. Doc 99 entries 29–30.

#### Step one: the shop features

The single most effective change measured here: **10 extra floats**, two per
shop slot — `owned` (do I already hold this champion?) and `synergy` (how many
of my units share a trait with it?).

| clone | placement | top 4 | BUY match | data |
|---|---|---|---|---|
| baseline | 5.833 ±0.238 | 27.3% | 45.9% | 400 ep |
| more data | 5.533 ±0.231 | 28.0% | 48.2% | 1500 ep |
| **+ derived features** | **5.063 ±0.263** | **43.0%** | **82.3%** | 400 ep |
| scripted teacher | 4.620 | 46.3% | — | — |

BUY had been stuck at a coin flip through 3.75× more data, DAgger, and the
`features` encoding's full trait multi-hot — all of which moved it under 2.5
points. These two features moved it **+36**.

The reason is that they are *relational*: comparisons between a shop slot and
the current roster, not descriptions of a champion. `features` supplies
strictly more raw information (2056 dims vs 240) and never helped, because
raw description is not the comparison. Doc 99 entry 29.

**Aggregate action match did not move** (51.2% → 51.5%) while placement improved
0.770 — the composition changed underneath it. Any evaluation of this project
that tracks average match alone will score its best change as noise.

### The bottleneck is BUY, and it is structural

Per-`ActionKind` agreement with the scripted expert, measured on the states the
policy *actually reaches* (`scripts/action_match.py`). BUY's achievable ceiling is **67.7%**: the expert declines its own top-ranked
candidate 32% of the time, because its buy rule is a cascade gated on saving
gold rather than a plain argmax. (An earlier 90.7% figure counted *ambiguity*
instead of *agreement* — corrected in doc 99 entry 28.)

| clone | BUY | SELECT | PLACE | EQUIP | BUY_XP | overall | placement |
|---|---|---|---|---|---|---|---|
| index, 400 ep | 45.9% | 29.1% | 56.9% | 77.8% | 84.8% | 51.2% | 5.833 |
| index, 1500 ep | **48.2%** | 55.9% | 89.7% | 93.5% | 99.4% | 78.0% | **5.533** |
| features, 1500 ep | **48.1%** | 28.5% | 55.8% | 75.8% | 96.2% | 51.7% | 5.887 |

At 1500 episodes every action kind improves substantially — PLACE +32.8 points,
overall +26.8 — **except BUY, which moves 2.3 points against a 20-point gap.**
Giving the network an explicit trait multi-hot per shop slot (`features`)
changes it by 0.1 points.

So BUY is not an information problem. It is a **relational argmax over a
candidate set**: score ~3.4 affordable shop slots against the board's trait
counts, take the best. Every other action is a classification over a fixed
layout, and all of them respond to data. An offline probe of five head architectures failed to resolve whether that is
really the cause — the high-capacity heads memorised (100% train accuracy) and
the lean ones could not fit at all, so the set/attention encoder is **not** yet
justified by evidence. Doc 99 entries 27–28.

Note the clone at 1500 episodes (**5.533**) is the best agent measured here and
the first genuine *gain* any intervention has produced — self-play and
`--target-kl` only ever avoided a loss. It also corrects an earlier claim that
expert data stops paying: it does not, above ~700 episodes (doc 99 27.3).

### The imitation gap, and why DAgger doesn't close it

The agent's ceiling is set by the clone, not by PPO. The clone imitates a 4.620
scripted teacher and places 5.833 — a 1.2 placement gap. Two ways of attacking
it, budget-matched (seed 21, n=300, no PPO phase):

| arm | placement | expert action match |
|---|---|---|
| BC 400 episodes | 5.833 ±0.238 | 81.8% |
| BC 700 episodes | 5.867 ±0.214 | 84.6% |
| BC 400 + 3×100 DAgger | 5.803 ±0.228 | **88.7%** |

**Imitation improved by 38% (disagreement 18.2% → 11.3%); play did not move at
all** — every contrast under t=0.5. More expert data does nothing either. The
`bc700` arm exists precisely so that DAgger's extra labels can't masquerade as
a distribution-shift effect.

This is the fourth independent time that fitting the expert *more closely* has
failed to improve play (see also the champion-encoding and scouting A/Bs). It
should be read as a property of the setup: the bottleneck is what the agent can
see, or the teacher it copies — not how it's trained. Doc 99 entry 24.

### PPO from a clone at parity

Re-run of every PPO arm once the clone reached its teacher. 120k steps, n=300.

| arm | placement | 1st | top 4 | last |
|---|---|---|---|---|
| clone (no PPO) | 4.567 ±0.247 | 8.3% | 47.0% | 11.7% |
| PPO, `--target-kl 0.02` | 5.360 ±0.257 | 6.0% | 34.7% | 26.3% |
| PPO, no leash | 4.637 ±0.264 | **12.3%** | **51.0%** | 16.0% |
| PPO + self-play | 5.107 ±0.261 | 8.7% | 40.3% | 20.0% |
| scripted teacher | 4.620 ±0.251 | 10.3% | 46.3% | — |

**`--target-kl 0.02` has been reverted as the default.** It was made the
default on evidence from a much weaker clone, where it removed a degradation
(−0.500, t=−3.37). From a parity clone the same setting is the *worst* arm
measured (+0.793, t=+4.36). A setting justified by evidence from a policy that
no longer exists is not justified.

**Self-play degrades at parity** (+0.540, t=+2.95) — under precisely the
condition earlier entries said would make it useful. That precondition was
wrong: the snapshot pool is still weaker than the scripted bots regardless of
how the learner compares to them.

**Unleashed PPO reshapes the distribution rather than shifting it.** Mean
placement is flat, firsts go 8.3% → 12.3% and top-4 47.0% → 51.0% — but last
place also rises 11.7% → 16.0%. Scored in ranked LP, which prices both tails,
the two cancel: **+0.63 vs the clone's +0.75, a null**. Runs are now scored on
LP as well as placement; across 23 recorded runs the two metrics disagree on
one pair of statistically-indistinguishable arms. Doc 99 entries 31–32.

#### Earlier: why PPO degraded a weak clone

PPO makes the agent **significantly worse than its own warm start**, replicated
on two independent seeds (+0.620 t=3.97 seed 12; +0.520 t=3.31 seed 21). A
five-arm screen located the cause: the policy drifts off a clone that took 400
episodes to build. Three arms restraining drift all recovered ground; the one
arm that wasn't about drift (dropping reward shaping) did not.

At 250k steps, n=300:

| arm | placement | top 4 | last | vs BC clone |
|---|---|---|---|---|
| default PPO | 6.353 ±0.195 | 14.3% | 32.7% | +0.520 t=+3.31 |
| `--learning-rate 5e-5` | 6.093 ±0.222 | 21.7% | 33.7% | +0.260 t=+1.56 |
| `--target-kl 0.02` | **5.853 ±0.215** | 24.3% | **25.3%** | +0.020 t=+0.12 |

`--target-kl 0.02` removes the degradation entirely (−0.500 vs the control,
t=−3.37). The low-LR arm looked like the winner at 60k and turned out to be
**slowness, not a fix** — it tracked the clone to 150k and then broke. A 3-seed
replication of that screen would have confirmed an artefact three times over;
duration was the test that mattered.

**No intervention has ever produced a gain.** Self-play (+0.040, t=0.25) and a
KL trust region (+0.020, t=0.12) share no mechanism and land on the same
number: exactly level with the warm start, never past it. The reading is that
PPO's step size was never the binding constraint — it was the thing breaking
something already at its ceiling. See doc 99 entries 22–23.

One nuance the mean hides: the KL arm has the lowest last-place rate measured
anywhere here (25.3% vs the clone's 29.3%) *and* fewer top-4s (24.3% vs 27.3%).
Same mean, compressed distribution — measurably more risk-averse play, and
invisible to the statistic this project optimises.

### Milestone 9 features — both verdicts withdrawn

The original milestone 9 A/Bs ran before items existed. Re-measured against the
frozen engine, **both reversed**:

| feature | milestone 9 verdict | milestone 12 re-measurement |
|---|---|---|
| `--self-play` (mix 0.5) | inert (−0.147, CI spans 0) | **protective**: −0.580 vs the PPO control, t=−3.78 |
| `--scouting full` | harmful (−0.303, t=−2.34) | sign reversed: +0.270 better, t=−1.79, **not significant** |

Neither is a claim that the flag *helps*. Both arms are still worse than doing
no PPO at all. What changed is that the old verdicts no longer have support.

The scouting reversal costs more than the number. Entry 19.1 generalised from
it that *widening this flat observation vector is a known-harmful operation*,
pairing it with the champion-encoding A/B. That inference now rests on one
surviving data point. A plausible reason it moved: scouting was measured on a
game where opponents' boards carried **no items**, so the added features
encoded far less than they do now.

⚠️ **Single training seed per arm.** n=300 gives tight *evaluation* intervals
but captures no seed variance, and PPO is seed-sensitive. These two rows are
sound as withdrawals of the old claims and are **not yet** established as new
ones — they need 3-seed replication (doc 99 22.4).

Both switches remain in the codebase: correct, tested, and cheap to re-measure.
See [docs/99_judgement_calls.md](docs/99_judgement_calls.md) 22.

### The floor effect — read this before running an A/B

A policy that finishes last in most games has almost no outcome variance, so
**no comparison built on it can resolve anything.** Four consecutive experiments
were wasted this way before it was caught (doc 99 entry 18.3): at a 150-episode
warm start the cloned policy places 8th in 84% of games, and its
suspiciously-tight ±0.18 CI reads like precision when it is really degeneracy.

Two guardrails now exist:

- `--warm-start` defaults to **400** (the measured minimum), `--warm-start-epochs` to 50.
- `EvalResult` reports `ci95` and `floor_rate`, and `summary()` prints a loud
  `!! FLOOR EFFECT` warning above 50% last-place finishes.

Always report the placement *distribution*, not just the mean.

**These numbers are only comparable within a run.** Engine changes have shifted
the baselines **seven** times (scripted has read 4.30 / 4.65 / 4.36 / 4.68 /
4.26 / 4.56 / 4.62), and milestone 17's observation change invalidates every
agent number measured before it, so never compare a figure here against one
from an older commit —
re-measure both arms together. Milestone 10 was the largest shift: adding items
raised the teacher *and* widened its CI (0.27 → 0.47), because items add real
outcome variance where board strength alone used to decide everything.

Placement against **self-play** opponents is not comparable to either: an
untrained model places 3.67 against seven copies of itself and 8.00 against the
scripted bots, because self-play makes the opposition exactly as weak as the
learner. Only placement against the fixed bots is a progress metric.

With a terminal-only reward, episode reward variance is exactly **zero** — an
untrained policy places 8th every game, so PPO has no gradient. `--reward-shaping`
adds a dense board-strength term to bootstrap out of that; see
[docs/99_judgement_calls.md](docs/99_judgement_calls.md) entries 6c.2–6c.4.

## Data

`data/` holds the **real Set 17 dataset** produced by
`scripts/fetch_cdragon.py` from Community Dragon: 63 champions, 35 traits, 65
items. The original hand-authored 13-champion sample is preserved as a frozen
fixture at `tests/fixtures/starter_data/`, because the hand-calculated
expectations in `test_units.py` and `test_combat.py` are written against it.

`data/config.json` holds every set/patch-specific table (shop odds, pool sizes,
XP thresholds, economy, combat tunables, augment schedule). Riot publishes none
of them, so **the fetch script never writes this file.** Its `provenance` block
classifies every constant as `riot_published` / `community_documented` /
`engine_artifact`, and its `unverified` list names tables whose exact values are
unconfirmed — the loader logs these at startup so an approximation cannot
quietly harden into an assumed fact.

`config.json`'s `realm` block schedules the Realm of the Gods draft (1-1, 2-4,
3-4, 4-4). Those rounds have **no combat** — they sit between fights, as in real
TFT — and the offerings are drawn from the shared champion pool, so a drafted
unit is one fewer copy in everyone's shop.

`data/creeps.json` holds the PvE monsters and creep waves. The monster **stats
are Riot's** (`TFT17_PVE_Krug` and friends, which the playable-unit filter had
been hiding); wave composition and drop rates are judgement calls. Without this
file PvE rounds fall back to free wins that drop nothing — which is how the item
system used to be completely unreachable (doc 99 entry 20.1).

`data/augments.json` is **the one data file not sourced from Riot.** The Set 17
payload carries no augment tier field and no mechanically simple augments, so
the shipped 14 are generic archetypes exercising the hooks the system supports.
The augment *system* is complete and general; see doc 02 sec 4c and
[docs/99_judgement_calls.md](docs/99_judgement_calls.md) entry 17.1.

## Conventions

- **No per-champion or per-set constants in code.** Behaviour is keyed by
  `effect_id` into `engine/effects.py`; magnitudes come from the data files.
- **Unimplemented `effect_id`s warn once and no-op**, never crash. Stats
  granted by the same entry still apply.
- **Combat is deterministic** given a seed and a fixed unit-construction order.
  The global `random` module is never used. A whole match, augment offers
  included, replays from its seed.
- **Two effect registries, same discipline.** `engine/effects.py` holds
  tick-scoped combat effects; `engine/augments.py` holds round-scoped,
  player-scoped augment hooks. They are separate because the call signatures
  are incompatible — one lookup for both would turn a data typo into a
  `TypeError` inside combat.
- **New capabilities ship off by default until measured.** Three structural
  hypotheses about the agent's weakness (observation encoding, reward shape,
  action space) were tested and *rejected* by measurement, so `--scouting full`
  and `--self-play` are opt-in until numbers say otherwise.
