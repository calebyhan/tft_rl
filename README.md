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
| 7 | PPO training loop | harness done; agent reaches 6.25 vs 4.47 scripted |
| 8 | Full data swap via `scripts/fetch_cdragon.py` | not started |
| 9 | Stretch: augments, self-play, board scouting | not started |

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
```

### Baselines (20 games vs 7 heuristic bots, seat 0)

| policy | avg placement | win rate | top 4 |
|---|---|---|---|
| do nothing | 8.00 | 0% | 0% |
| random legal action | 8.00 | 0% | 0% |
| PPO from scratch (150k steps) | 8.00 | 0% | 0% |
| behaviour cloning only | 6.45 | 0% | 20% |
| BC warm start + PPO (120k) | 6.25 | 0% | 25% |
| scripted heuristic | **4.47** | 27% | 47% |

The scripted heuristic plays *through the action space* and reaches parity with
the bots (4.5 = average), which is the check that the environment isn't
handicapping the agent seat.

With a terminal-only reward, episode reward variance is exactly **zero** — an
untrained policy places 8th every game, so PPO has no gradient. `--reward-shaping`
adds a dense board-strength term to bootstrap out of that; see
[docs/99_judgement_calls.md](docs/99_judgement_calls.md) entries 6c.2–6c.4.

## Data

`data/` currently holds a **hand-authored starter sample** (doc 02 sec 5): 13
champions across all five cost tiers, 8 traits, 19 items. It is not real Set 17
data — its schema is identical to the full schema, so
`scripts/fetch_cdragon.py` (milestone 8) can replace it with no code changes.

`data/config.json` holds every set/patch-specific table (shop odds, pool sizes,
XP thresholds, economy, combat tunables). Its `unverified` list names the
constants doc 01 sec 9 flags as unconfirmed against the live client.

## Conventions

- **No per-champion or per-set constants in code.** Behaviour is keyed by
  `effect_id` into `engine/effects.py`; magnitudes come from the data files.
- **Unimplemented `effect_id`s warn once and no-op**, never crash. Stats
  granted by the same entry still apply.
- **Combat is deterministic** given a seed and a fixed unit-construction order.
  The global `random` module is never used.
