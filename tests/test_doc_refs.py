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


# --- teacher reconstruction (doc 99 entry 74) ----------------------------


def test_sidecar_round_trips_the_teacher_econ(tmp_path):
    """A run's econ plan must survive into `teacher_gap`'s reconstruction.

    `teacher_gap` and `teacher_check` rebuild the teacher from the sidecar to
    score a clone against it. If `expert_econ` is dropped they silently rebuild
    a *no-econ* teacher, which places 4.823 against `standard`'s 4.213 -- the
    clone would be scored against a policy that never labelled it, and the
    resulting gap would look plausible and mean nothing.
    """
    import json
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from rl.opponents import STANDARD
    from scripts.teacher_gap import teacher_config

    run = tmp_path / "run"
    run.mkdir()
    (run / "metadata.json").write_text(json.dumps({
        "hyperparameters": {
            "expert_sell": True,
            "expert_flags": True,
            "expert_roll_at_level": 0,
            "expert_econ": "standard",
        }
    }))
    expert, _env, _search = teacher_config(run)
    assert expert["econ"] is STANDARD, (
        f"econ lost in reconstruction: {expert.get('econ')!r}"
    )

    # And absent means absent, so pre-entry-74 runs still reproduce.
    (run / "metadata.json").write_text(json.dumps({"hyperparameters": {}}))
    assert teacher_config(run)[0]["econ"] is None


def test_sidecar_round_trips_the_repositioning_budget(tmp_path):
    """The search budget must survive too, and the *budget* specifically.

    Entry 78.2: c12/p1 is worth -0.330 (t=-2.53) while c6/p1 reads -0.113
    (t=-0.87), indistinguishable from no search. So reconstructing a search
    teacher at the wrong budget is not a rounding error -- it rebuilds a
    teacher that measurably is not the one that produced the labels.
    """
    import json
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from scripts.teacher_gap import teacher_config

    run = tmp_path / "run"
    run.mkdir()

    def written(**hyper):
        (run / "metadata.json").write_text(json.dumps({"hyperparameters": hyper}))
        return teacher_config(run)[2]

    assert written(expert_reposition=False) is None
    assert written() is None, "a run with no reposition key must rebuild no search"

    search = written(expert_reposition=True, expert_reposition_candidates=12,
                     expert_reposition_panel=3,
                     expert_reposition_state_seeded=True)
    assert search == {"mode": "move", "max_candidates": 12, "panel_size": 3,
                      "state_seeded": True}

    # Runs predating the flags hardcoded 6/1 and were labelled by the
    # free-running stream; they must still reproduce. `state_seeded` defaulting
    # True in `best_move` but False here is deliberate (entry 79.4).
    assert written(expert_reposition=True) == {
        "mode": "move", "max_candidates": 6, "panel_size": 1,
        "state_seeded": False,
    }

    # `swap` and `board` do not sample candidates, so they take no
    # `state_seeded` -- and `best_swap` would raise TypeError on the key. A
    # reconstruction that rebuilds an *uncallable* teacher is the same class of
    # defect as one that rebuilds the wrong teacher (entry 79.5), and it is why
    # `test_reconstructed_search_configs_are_callable` exists as well.
    swap = written(expert_reposition=True, expert_reposition_mode="swap",
                   expert_reposition_candidates=4, expert_reposition_panel=2,
                   expert_reposition_state_seeded=True)
    assert swap == {"mode": "swap", "max_candidates": 4, "panel_size": 2}, (
        "swap mode must not carry state_seeded even when the flag is set"
    )
    assert written(expert_reposition=True, expert_reposition_mode="board")[
        "mode"] == "board"
