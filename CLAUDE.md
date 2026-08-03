# CLAUDE.md — tft_rl

Project-local guidance. Supplements the global `~/.claude/CLAUDE.md`; where the
two conflict, this file wins for work inside this repo.

## What this project is

A Teamfight Tactics **simulator** (`engine/`) and a **reinforcement-learning
environment** built on it (`rl/`), targeting Set 17 with real Riot data.

Three spec documents are the source of truth and are treated as such:

| Doc | Covers |
|---|---|
| [`docs/01_game_mechanics_reference.md`](docs/01_game_mechanics_reference.md) | Game rules: combat, economy, traits, items, round structure |
| [`docs/02_data_schema_and_sourcing.md`](docs/02_data_schema_and_sourcing.md) | JSON schema and how Set 17 data is sourced |
| [`docs/03_engine_and_rl_architecture.md`](docs/03_engine_and_rl_architecture.md) | Repo layout, module responsibilities, milestone order |

[`docs/99_judgement_calls.md`](docs/99_judgement_calls.md) is the decision log
and learning journal — see *Working with doc 99* below. **Read it before
proposing anything that sounds new.** Most obvious ideas have been tried and
measured; several were tried, measured, and refuted.

The current state: the behaviour-cloned agent is at **parity with its scripted
teacher** (4.567 vs 4.620 average placement, n=300). Imitation is exhausted by
construction; no RL configuration tested has passed it.

## Environment and commands

Python 3.12 venv at `.venv/`. Always use `.venv/bin/python`, never bare
`python`.

```bash
.venv/bin/python -m pytest              # full suite, ~2 min
.venv/bin/ruff check .                  # lint; must be clean
.venv/bin/python scripts/smoke_test.py  # whole-game invariants
.venv/bin/python scripts/check_doc_refs.py   # doc 99 citations resolve
```

Before saying anything is done: **pytest green, ruff clean, smoke test green.**
The smoke test is not redundant with the unit tests — see *Testing* below.

## Layout

```
engine/     simulator. schema/loader (data in), unit/stats/traits/items
            (derived stats), combat (tick sim), shop/economy/player/match
            (game loop), effects + augments (two separate registries)
rl/         observation (state -> vector), action (space + mask + executor),
            env (Gymnasium), opponents (scripted bots), evaluate (metrics +
            baselines), selfplay (snapshot pool)
data/       real Set 17 JSON. config.json is hand-curated and carries a
            provenance block; the fetch script must never write it
scripts/    train_ppo.py, fetch_cdragon.py, smoke_test.py, plus one-off
            probes and experiment drivers (*.sh)
runs/       training artifacts: model.zip, metrics.json, metadata sidecar
```

## Engine conventions

These are load-bearing and enforced by tests:

- **No per-champion or per-set constants in code.** Behaviour is keyed by
  `effect_id` into `engine/effects.py`; magnitudes come from data files.
- **Unimplemented `effect_id`s warn once and no-op, never crash.** Stats
  granted by the same entry still apply.
- **Combat is deterministic** given a seed and a fixed unit-construction order.
  The global `random` module is never used.
- **All illegal actions raise `IllegalAction`** so the RL wrapper can mask
  cleanly. If the action mask and the executor ever disagree, the mask is the
  bug — it must ask the engine, not reimplement its rules.
- **Two effect registries** (`effects.py` tick-scoped, `augments.py`
  round-scoped) with identical warn-once discipline but incompatible
  signatures. Keep them separate.

## Measurement discipline

This project's expensive lessons are about measurement, not code. The full set
is in doc 99's *Lessons* section; these are the operating rules.

**Baselines have been invalidated eight times.** Engine changes shift every
number. Never compare a figure against one from an older commit — re-measure
both arms together, in the same run.

**Freeze before you measure.** Finish the engine change, then measure once.
Measuring against a moving target is how four separate experiment batches were
wasted.

**Report the distribution, not just the mean.** Average placement has hidden a
real finding three times: aggregate action match stayed flat while placement
moved 0.770; a KL arm posted fewer last places *and* fewer top-fours at an
identical mean. `EvalResult` reports placement, LP, win rate, top-4 and the
full histogram — quote enough of them to be honest.

**A rate is uninterpretable without its achievable maximum.** "48%" means
nothing until you know the ceiling. Measure the ceiling first; it usually takes
a minute and can invalidate the whole investigation.

**Re-derive numbers before citing them.** Twice, a number measured once in one
regime became a default and then a fact (a 90.7% ceiling that was wrong, a
`--target-kl` default justified by a policy that no longer existed).

**Name the possible outcomes before the run finishes**, so a story cannot be
fitted to whatever appears afterwards.

**A probe that cannot fit its own training set** is a statement about the
feature set, not the model.

**Replication tests precision, not validity.** If a result might be an artefact
of the *setup* rather than noise, more seeds will confirm the artefact. Change
the axis that discriminates (duration, budget, distribution).

**State t-statistics and n.** Single-seed results are fine for reverting a
default to neutral, not for asserting a new claim — say which one you have.

## Observation design

The single most productive finding in this project, stated as a rule:

> **Relational beats descriptive.** Adding *description* of entities has failed
> every time (the `features` champion encoding: ~1800 extra floats, rejected
> three times). Adding a *comparison between* entities has worked every time —
> twelve floats across four comparisons closed a 1.266 placement gap.

Before widening the observation, ask whether the new features describe things
or compare them. If a quantity is technically derivable from what is already
encoded but requires an identity match, a dot product, a ranking or a threshold
across slots, a flat MLP will not derive it. Supply it.

Do **not** encode the expert's policy. `owned`, `synergy`, star/cost rank and
`board_full` are facts a player reads off the screen. A composite "strength"
score using the expert's lexicographic `(star, cost)` preference would be
copying, not learning. This line is a judgement call — state it explicitly when
you draw it.

## Testing

- **Write real tests per milestone, not at the end.** Every bug fix gets a
  regression test.
- **Mutation-test any test that pins a central claim.** Break the
  implementation deliberately and confirm the test fails. Four tests in this
  project passed against broken code, and two silently skipped on a fixture
  that could not construct the case. A test that asserts nothing reads as
  coverage.
- **`scripts/smoke_test.py` is load-bearing.** It asserts conservation across
  whole games, which per-feature tests structurally cannot. A champion pool
  leak survived 30 passing unit tests and was caught here.
- Fixtures: `tests/fixtures/starter_data/` is a frozen 13-champion sample with
  hand-calculated expectations. Use `REAL_DATA_DIR` when a test needs variety
  the sample cannot provide — and check your test does not silently skip.

## Working with doc 99

`docs/99_judgement_calls.md` is the decision log and learning journal.

**Structure:**

- **Front matter** — how to read, flags, status markers.
- **Lessons** — cross-cutting methodology findings, each pointing at the entry
  that produced it.
- **Index** — every entry with date and status, plus the arc of agent
  performance over time.
- **Part I — Standing decisions** (§1–8). Judgement calls where the specs were
  silent or were deviated from. Reference material, kept current, mostly
  tables. Flags: 🔴 deviates / 🟠 invented constant / 🟡 gap-filled / ⚪ deferred.
- **Part II — Journal** (§9 onward). Dated entries, newest last. Each records a
  question, what was measured, and what changed.

**Rules:**

- **Entry numbers are stable and never reused or renumbered.** ~80 code
  comments cite them. Cite as `doc 99 entry N.M` in code; use a markdown link
  in `.md` files. `scripts/check_doc_refs.py` and `tests/test_doc_refs.py`
  enforce that every citation resolves.
- **Never delete a wrong entry.** Keep it, add a banner naming its successor
  (`> **WITHDRAWN by entry 31.2.**`), and update its index status to ⚠️ or ❌.
  Several of this project's best conclusions came from re-checking something
  already cited as fact.
- **§8's open worklist is deliberately unnumbered** — it churns, and numbering
  it invites citations that outlive the item.
- A new journal entry gets: the question, the numbers with n and t, what it
  changes, and an explicit "still open" list. Record failed predictions as
  failed, not as vindications.

## Communication

- Report outcomes faithfully. If a prediction failed, say so plainly and move
  on — no rumination, no spin.
- Do not claim something works without evidence of it running.
- Prefer one clear recommendation over a survey of options.
- Long-running work: `runs/*.log` stays empty until the process exits (Python
  block-buffers redirected stdout). Use artifact mtimes and `metrics.json` for
  progress, not `tail`.

## Git

Do not commit or push unless explicitly asked.
