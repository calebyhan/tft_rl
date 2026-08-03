"""Citations into `docs/99_judgement_calls.md` must resolve.

~80 comments across the codebase cite that document by entry number, which is
why entries are never renumbered. Nothing enforced that the numbers existed:
`scripts/fetch_cdragon.py` carried a citation of `8.5` pointing at a section
with no numbered items (it meant 9.5), and it read perfectly plausibly.

Doc rot is silent by construction -- a stale reference still looks like a
reference. This makes it loud.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.check_doc_refs import DOC, citations, known_entries  # noqa: E402


def test_every_citation_resolves():
    known = known_entries(DOC.read_text())
    broken = [
        f"{path.name}:{line} -> entry {entry}"
        for path, line, entry in citations()
        if entry not in known
    ]
    assert not broken, "unresolved doc 99 citations:\n  " + "\n  ".join(broken)


def test_the_checker_would_notice_a_bad_citation():
    """A checker that passes everything is worse than none at all."""
    known = known_entries(DOC.read_text())
    assert "99.9" not in known
    assert "29.1" in known, "a known-good entry must resolve"


def test_citations_are_actually_being_found():
    """Guards against the regex silently matching nothing."""
    assert len(citations()) > 50
