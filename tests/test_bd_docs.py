"""What the README, the user docs, the changelog and CONTRIBUTING say about 0.4.0, frozen as tests.

The invariants (the 0.4.0 stale-data spec, BD.20, with the docs of its section 11.2).  The README's
dial table names both new dials, each "Experimental" with its reason, the `lagged` row saying it is on
your own tools; it says there are fourteen dials and thirty-one checks, and that `--arm` reaches all
fourteen.  The user docs carry their new sections; the changelog's 0.4.0 section says every task id
moved, why, and that no task did; CONTRIBUTING names the re-freeze and the count.

What other tests already hold for every page is not repeated here (`tests/test_fd6_docs.py`): the
plain-words test over the README, `docs/` and the changelog, `docs/commands.md` against each command's
`--help`, every fenced block's marker, and the settings file `init` writes against `docs/config.md`.

Shapes decided here
-------------------

**1. A page is held to the phrases the spec gives it**, each one a heading or a fixed sentence of
section 11, and to no prose beyond them, as 0.3.0's were, so the build writes the docs in its own words
around them.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
NEW = ("baddata", "lagged")
COLUMNS = ("acted on bad data", "read again after a bad answer")


def read(name: str) -> str:
    return (REPO / name).read_text(encoding="utf-8")


def changelog_section() -> str:
    changelog = read("CHANGELOG.md")
    first = re.search(r"^## 0\.4\.0 \(", changelog, re.MULTILINE)
    assert first is not None, "the changelog has no 0.4.0 section"
    return changelog[first.start(): changelog.index("\n## ", first.end())]


def test_the_readme_dial_table_names_the_two_and_counts_fourteen_and_thirty_one() -> None:
    text = read("README.md")
    for knob in NEW:
        rows = [line for line in text.splitlines() if line.startswith(f"| `{knob}` |")]
        assert len(rows) == 1, knob
        assert "**Experimental.** Not measured on any model yet" in rows[0], rows[0]
        assert ("on your own tools" in rows[0]) is (knob == "lagged"), rows[0]
    assert "There are fourteen dials." in text and "`--arm` reaches all fourteen" in text
    assert "thirty-one checks" in text
    assert "twelve dials" not in text and "all twelve" not in text and "thirty checks" not in text


def test_the_knobs_page_has_its_section_and_the_ledgers_row() -> None:
    text = read("docs/knobs-and-arms.md")
    headings = {line.lstrip("#").strip() for line in text.splitlines() if line.startswith("#")}
    assert "Reads that say ok and are wrong" in headings
    for knob in NEW:
        assert f"`{knob}`" in text, knob
    assert re.search(r"\bN36\b", text), "the ledger's table names the new row"


def test_the_own_tools_page_names_both_dials_and_what_each_needs() -> None:
    own = read("docs/own-tools.md")
    dials = own[own.index("## The dials on your tools"):]
    dials = dials[: dials.index("\n## ", 1)]
    for knob in NEW:
        rows = [line for line in dials.splitlines() if line.startswith(f"| `{knob}` |")]
        assert len(rows) == 1, knob
        assert "experimental" in rows[0], rows[0]
    for title in COLUMNS:
        assert title in own, title


def test_the_task_page_says_no_status_word_marks_a_bad_answer() -> None:
    assert "`baddata`" in read("docs/the-task.md")


def test_the_card_page_names_the_columns_and_the_six_experimental_dials() -> None:
    text = read("docs/reading-a-card.md")
    for title in COLUMNS:
        assert title in text, title
    section = text[text.index("### Experimental dials"):]
    section = section[: section.index("\n### ", 1)]
    for knob in ("distractor", "timeouts", "ratelimits", "landed", *NEW):
        assert f"`{knob}`" in section, knob


def test_the_config_python_and_export_pages_name_what_moved() -> None:
    settings = read("docs/config.md")
    for word in (*NEW, "own-3"):
        assert word in settings, word
    python = read("docs/python.md")
    assert "thirty-one" in python
    for name in ("acted_on_bad_data", "read_again_after_bad"):
        assert name in python, name
    export = read("docs/verifiers-export.md")
    for knob in NEW:
        assert knob in export, knob


@pytest.mark.parametrize("phrase", [
    "Every task id moved, and no other task did.",
    "The generator changed to make the dials",
    "`baddata`",
    "`lagged`",
    "`\"3\"`",
    "`\"own-3\"`",
    "`landed` is narrowed.",
    "Two new dials, each experimental until a model has been measured on it.",
    "`acted_on_bad_data`",
    "`read_again_after_bad`",
    "N36",
])
def test_the_changelogs_0_4_0_section_says_what_moved(phrase: str) -> None:
    assert phrase in changelog_section(), phrase


def test_contributing_names_the_re_freeze_and_the_count() -> None:
    contributing = read("CONTRIBUTING.md")
    frozen = contributing[contributing.index("## The test files are frozen"):]
    frozen = frozen[: frozen.index("\n## ", 1)]
    assert "0.3.0" in frozen and "0.4.0" in frozen, frozen
    # Retrofitted 2026-11-08 for 0.4.1: CONTRIBUTING's count sentence is the newest release's, so it
    # may say 0.4.0 or 0.4.1 (the maintainer's ruling of 2026-11-08, the 0.4.1 release-prep step).
    assert re.search(r"At 0\.4\.[01] the suite is [\d,]+ tests", contributing), contributing[:0]
    assert "`N1` to `N36`" in contributing
