"""What each kind of run costs, from the ledger (doc 99 entry 46.5).

    .venv/bin/python scripts/timings.py
"""

from __future__ import annotations

import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rl.timing import _units, estimate, human, load  # noqa: E402


def main() -> None:
    rows = load()
    if not rows:
        print("no runs recorded yet")
        return

    by_kind: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_kind[row["kind"]].append(row)

    print(f"{'kind':<20}{'runs':>6}{'median':>10}{'range':>18}  typical shape")
    for kind in sorted(by_kind):
        entries = by_kind[kind]
        times = sorted(r["seconds"] for r in entries)
        span = f"{human(times[0])} - {human(times[-1])}"
        shape = max(entries, key=lambda r: _units(r))
        print(
            f"{kind:<20}{len(entries):>6}{human(statistics.median(times)):>10}"
            f"{span:>18}  episodes={shape.get('episodes')} "
            f"arms={shape.get('arms')} workers={shape.get('workers')}"
        )

    print("\nEstimates for common shapes:")
    for kind, meta in (
        ("expert_ab", dict(episodes=300, arms=5, workers=8)),
        ("expert_ab+search", dict(episodes=300, arms=2, workers=8)),
        ("compare_models", dict(episodes=300, arms=2)),
        ("bc_clone", dict(episodes=400, arms=1)),
    ):
        predicted, samples = estimate(kind, **meta)
        shape = " ".join(f"{k}={v}" for k, v in meta.items())
        if predicted is None:
            print(f"  {kind:<20} {shape:<38} no data")
        else:
            print(f"  {kind:<20} {shape:<38} ~{human(predicted)}  (n={samples})")


if __name__ == "__main__":
    main()
