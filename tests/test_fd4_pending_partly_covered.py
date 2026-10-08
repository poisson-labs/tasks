"""Pending a yes/no (`evidence/front-door-fd4-a/rulings.md`, yes/no 3): a plan with some of its
levels on a published card is covered.

The ruling says a card for a plan no published card covers says so plainly.  This reads "no
published card covers" as "no published card holds a cell of any of the plan's arms": a plan of
depth 3 and depth 4 is covered, by its depth-3 level, and its card does not carry the
`not_covered` line, though its depth-4 level is on no published card (side by side, only depth 3
can be read beside a published card).  The other reading, "every level on a published card",
would flag it.  The control is the plan of depth 4 alone (`test_fd4_claims.py`), which is
flagged.
"""

from __future__ import annotations

from tests.fd3_support import calibration, needs_uv
from tests.fd4_support import RunFolders, fd4_runs, shipped_artifacts

__all__ = ["fd4_runs"]

pytestmark = needs_uv


def test_fd4_4_a_plan_with_one_published_level_is_covered(fd4_runs: RunFolders) -> None:
    artifact = calibration().card_from_run(fd4_runs["partly_covered"].folder).artifact
    arms = {cell["arm_id"] for cell in artifact.cells}
    published = {cell["arm_id"] for other in shipped_artifacts() for cell in other.cells}
    assert arms & published and arms - published
    assert "not_covered" not in calibration().card_claims(artifact).flags
    assert "not_covered" in calibration().card_claims(
        calibration().card_from_run(fd4_runs["uncovered"].folder).artifact).flags
