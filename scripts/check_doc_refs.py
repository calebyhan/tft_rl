"""Verify every `doc 99 entry N.M` citation in the codebase resolves.

~77 comments cite `docs/99_judgement_calls.md` by entry number, which is why
entries are never renumbered. Nothing enforced that the numbers existed: a
citation of `8.5` sat in `scripts/fetch_cdragon.py` pointing at a section that
had no numbered items at all (it meant 9.5). Doc rot is silent by nature --
the comment still reads plausibly.

Run it as a test (`tests/test_doc_refs.py`) or directly:

    python scripts/check_doc_refs.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "99_judgement_calls.md"
SEARCH = ("engine", "rl", "scripts", "tests", "docs")

# `doc 99 entry 29.1`, `doc 99 22`, `doc 99 entry 6c.3`,
# `doc 99 entries 22.3 and 23.7`, `doc 99 25-29` (a range), `doc 99 18.3/18.4`.
CITATION = re.compile(
    r"(?:docs/99_judgement_calls\.md|doc 99)"
    r"(?:\s+(?:entry|entries|section|sec))?\s*"
    r"((?:\d+[a-z]?(?:\.\d+)?)(?:\s*(?:[-/,]|and)\s*\d+[a-z]?(?:\.\d+)?)*)",
    re.IGNORECASE,
)
IDS = re.compile(r"\d+[a-z]?(?:\.\d+)?")


def known_entries(text: str) -> set[str]:
    """Every entry id the document actually defines."""
    found = set()
    for line in text.splitlines():
        # `## 29. Title`, `## 6b. Title`, `### 29.1 Title`
        match = re.match(r"#{2,3}\s+(\d+[a-z]?(?:\.\d+)?)[.\s]", line)
        if match:
            found.add(match.group(1))
        # Table rows: `| 9.5 | ...` and `| 3.1 ✅ | ...`
        row = re.match(r"\|\s*(\d+[a-z]?\.\d+)\s*(?:✅)?\s*\|", line)
        if row:
            found.add(row.group(1))
    # A section number alone is a valid citation of the whole section.
    found |= {i.split(".")[0] for i in found}
    return found


def citations() -> list[tuple[Path, int, str]]:
    out = []
    for area in SEARCH:
        for path in sorted((ROOT / area).rglob("*")):
            if path.suffix not in {".py", ".sh", ".md"} or path == DOC:
                continue
            for number, line in enumerate(
                path.read_text(errors="ignore").splitlines(), 1
            ):
                for match in CITATION.finditer(line):
                    for entry in IDS.findall(match.group(1)):
                        out.append((path, number, entry))
    return out


def main() -> int:
    known = known_entries(DOC.read_text())
    broken = [
        (path, line, entry)
        for path, line, entry in citations()
        if entry not in known
    ]
    total = len(citations())
    if broken:
        print(f"{len(broken)} of {total} citations do not resolve:\n")
        for path, line, entry in broken:
            print(f"  {path.relative_to(ROOT)}:{line}  ->  entry {entry}")
        return 1
    print(f"all {total} citations resolve ({len(known)} entries defined)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
