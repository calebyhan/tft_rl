"""A ledger of how long each kind of run actually takes.

Every measurement in this project is a wall-clock commitment, and until now the
only record of that cost was whatever was remembered. That made scheduling
guesswork -- a 7-arm sweep was launched as "about an hour" and took 2h 05m, and
three separate process checks were misread partly because there was no baseline
for how long the stage should have taken.

Runs append here as JSON lines. Before a run starts, past entries for the same
``kind`` give an estimate; per-unit rates are used rather than raw totals so an
estimate transfers across different episode counts and worker counts.

    from rl.timing import timed
    with timed("expert_ab", episodes=300, arms=2, workers=8):
        ...
"""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

LEDGER = Path(__file__).resolve().parent.parent / "runs" / "timings.jsonl"


def _units(meta: dict) -> float:
    """Work in this run, in comparable units.

    Episodes times arms, divided by workers -- the quantity that actually sets
    wall clock for the evaluation scripts. Falls back to 1 so a run with no
    declared shape still records a usable total.
    """
    episodes = float(meta.get("episodes") or 1)
    arms = float(meta.get("arms") or 1)
    workers = float(meta.get("workers") or 1)
    return max(episodes * arms / max(workers, 1), 1e-9)


def load(kind: str | None = None) -> list[dict]:
    if not LEDGER.exists():
        return []
    rows = []
    for line in LEDGER.read_text().splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if kind is None or row.get("kind") == kind:
            rows.append(row)
    return rows


def record(kind: str, seconds: float, **meta) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "kind": kind,
        "seconds": round(seconds, 1),
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **meta,
    }
    with LEDGER.open("a") as handle:
        handle.write(json.dumps(row) + "\n")


def estimate(kind: str, **meta) -> tuple[float | None, int]:
    """Predicted seconds for a run of this shape, and how many runs back it.

    Uses the median per-unit rate rather than the mean: one run that shared a
    machine with two others should not drag every future estimate with it.
    """
    rows = [r for r in load(kind) if r.get("seconds")]
    if not rows:
        return None, 0
    rates = sorted(r["seconds"] / _units(r) for r in rows)
    middle = rates[len(rates) // 2]
    return middle * _units(meta), len(rates)


def human(seconds: float) -> str:
    if seconds < 90:
        return f"{seconds:.0f}s"
    if seconds < 5400:
        return f"{seconds / 60:.0f}m"
    return f"{seconds / 3600:.1f}h"


@contextmanager
def timed(kind: str, **meta):
    """Print an estimate, run, then record and print the actual."""
    predicted, samples = estimate(kind, **meta)
    shape = " ".join(f"{k}={v}" for k, v in meta.items() if v is not None)
    if predicted is None:
        print(f"[{kind}] {shape} -- no prior runs, no estimate", flush=True)
    else:
        print(
            f"[{kind}] {shape} -- estimated {human(predicted)} "
            f"(median of {samples} prior run{'s' if samples != 1 else ''})",
            flush=True,
        )
    started = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - started
        record(kind, elapsed, **meta)
        if predicted:
            drift = elapsed / predicted
            print(
                f"[{kind}] took {human(elapsed)} ({drift:.2f}x the estimate)",
                flush=True,
            )
        else:
            print(f"[{kind}] took {human(elapsed)}", flush=True)
