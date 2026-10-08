"""Pending a yes/no (`evidence/front-door-fd4-a/rulings.md`, yes/no 1): the published page does not
gain a run's claims block.

A run's card carries what it means and what it does not claim (spec §9.4: "`card.md` carries
them"), rendered by `render_document(artifact, claims=True)`.  The published page,
`docs/calibration.md`, renders each published card with `render_document(artifact)`, and stays as
it is: the new cards replace it, and the frozen `tests/test_cal_combined_card.py` holds it to its
rendering, so a build that changed the default rendering and the page together would pass every
other test.  This pins the page's bytes.  The new cards change the digest (listed in the session's
filing).

Green on the skeleton by construction: it guards what the build must not move.
"""

from __future__ import annotations

from tests.fd4_support import REPO, sha256

PAGE_SHA256 = "12bd406be5d91e48aa38cb2e81a19e442b2fc8d0fbb9d9e8d857ef5e1060cbaa"
"""`docs/calibration.md` as published before FD4."""


def test_fd4_10_the_published_page_does_not_move() -> None:
    assert sha256(REPO / "docs" / "calibration.md") == PAGE_SHA256
