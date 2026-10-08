"""Pending a yes/no (`evidence/front-door-fd4-a/rulings.md`, yes/no 4): a run's card says its budget
was not recorded.

Spec §9.2 lists "the budget" among what `Provenance.for_plan` records, and every card prints it
("budget: 100000000 tokens, 43200 s wall clock, or the provider out of credit, whichever
first").  A run of a plan has no such budget: it stops on the spend cap, the token cap, the
provider, a failure streak or the watchdog (spec §8.7), and its caps are in no file of its folder
(they are not part of the plan, and raising one resumes the same run).  A card that printed the
published design's twelve-hour budget would state a limit the run never had.  So `for_plan`'s
budget, when the caller gives none, is `{"tokens": None, "wall_clock_seconds": None}`, and the
card prints it as not recorded, as it prints time it did not keep.
"""

from __future__ import annotations

from tests.fd3_support import calibration, needs_uv
from tests.fd4_support import RunFolders, fd4_runs

__all__ = ["fd4_runs"]

pytestmark = needs_uv


def test_fd4_2_a_runs_card_records_no_budget_it_did_not_have(fd4_runs: RunFolders) -> None:
    built = calibration().card_from_run(fd4_runs["first_look"].folder)
    assert dict(built.artifact.provenance.budget) == {"tokens": None, "wall_clock_seconds": None}
    (line,) = [text for text in built.document.splitlines() if text.startswith("- budget:")]
    assert calibration().NOT_RECORDED in line
    assert "None" not in line and str(calibration().DEFAULT_BUDGET["tokens"]) not in line
