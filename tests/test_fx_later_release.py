"""The card and `init` say a later release measures the published cards again (issue #32).

The issue found two sentences promising that the next release measures the published cards again.
0.2.0 and 0.2.1 did not, and the docs say "a later release".  The two sentences already say so on
`main` (fixed in 0.2.2, `745c448`), and no test held the words: a change back to "the next release"
would have passed every test.  This guards them.

- **FX32.1** `init`'s note on a model with a published card, and the line on a card from a run that
  cannot be read beside the published cards, each say `a later release measures` the cards, and
  neither says the next release does.
- **FX32.2** the wording holds in every file a user reads or the wheel ships: the source of the
  package, the docs, the README and the two published cards, none of which promises a next release
  for this.  Held as a search of those files, so a third place that gets the old words is found.
"""

from __future__ import annotations

import re

from poisson_tasks import calibration
from poisson_tasks.cli import _init
from tests.fd6_support import REPO

PROMISE = re.compile(r"\b(?:the\s+)?next\s+(?:release|version)\s+(?:measures|will\s+measure)", re.I)


def test_fx32_1_the_two_sentences_say_a_later_release() -> None:
    for text in (_init.PUBLISHED_NOTE, calibration._LINE_EARLIER_BUILD):
        flat = " ".join(text.split())
        assert "a later release measures" in flat, flat
        assert PROMISE.search(flat) is None, flat


def test_fx32_2_no_file_promises_that_the_next_release_measures_the_cards() -> None:
    files = [REPO / "README.md", *(REPO / "docs").glob("*.md"), *(REPO / "src").rglob("*.py"),
             *(REPO / "calibration").rglob("*.md"), *(REPO / "calibration").rglob("*.json")]
    assert len(files) > 30, len(files)
    found = []
    for path in files:
        flat = re.sub(r"[\s\"'#]+", " ", path.read_text(encoding="utf-8"))
        found += [f"{path.relative_to(REPO)}: {match.group(0)}" for match in PROMISE.finditer(flat)]
    assert found == [], found
