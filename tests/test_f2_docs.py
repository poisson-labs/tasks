"""What the README, the user docs, the changelog and CONTRIBUTING say about 0.3.0, frozen as tests.

The invariants (the 0.3.0 faults spec, F2.16, with the docs of its section 11.2).  The README's dial
table names the three new dials, each "Experimental" with its reason, the `landed` row saying it is
on your own tools; it says there are twelve dials and that `--arm` reaches all twelve.  The user docs
carry the new sections; the changelog's 0.3.0 section says every task id moved, why, and what changed
in the answers on your own tools; CONTRIBUTING names the re-freeze.

What other tests already hold for every page is not repeated here (`tests/test_fd6_docs.py`): the
plain-words test over the README, `docs/` and the changelog, `docs/commands.md` against each
command's `--help`, every fenced block's marker, and the README's dial rows for the nine dials.

Shapes decided here
-------------------

**1. A page is held to the phrases the spec gives it**, each one a heading or a fixed sentence of
section 11, and to no prose beyond them, so the build writes the docs in its own words around them.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
NEW = ("timeouts", "ratelimits", "landed")


def read(name: str) -> str:
    return (REPO / name).read_text(encoding="utf-8")


def test_the_readme_dial_table_names_the_three_and_counts_fourteen() -> None:
    """Retrofitted 2026-11-04 for 0.4.0: the README says fourteen dials, the two stale-data knobs
    following (the stale-data spec's section 7.4, which names this line)."""
    text = read("README.md")
    for knob in NEW:
        rows = [line for line in text.splitlines() if line.startswith(f"| `{knob}` |")]
        assert len(rows) == 1, knob
        assert "**Experimental.** Not measured on any model yet" in rows[0], rows[0]
        assert ("on your own tools" in rows[0]) is (knob == "landed"), rows[0]
    assert "There are fourteen dials." in text and "`--arm` reaches all fourteen" in text
    assert "nine dials" not in text and "all nine" not in text


PAGES = {
    "docs/knobs-and-arms.md": ("## Three transport faults", "### Three transport faults"),
    "docs/reading-a-card.md": ("### Experimental dials", "## Experimental dials"),
}


@pytest.mark.parametrize("page", list(PAGES))
def test_each_page_carries_its_new_section(page: str) -> None:
    text = read(page)
    assert any(heading in text.splitlines() for heading in PAGES[page]), page
    if page == "docs/reading-a-card.md":
        assert "### The decoy-tools dial is experimental" not in text.splitlines()
        for knob in NEW:
            assert f"`{knob}`" in text, knob


def test_the_task_page_and_the_own_tools_page_name_the_new_answers() -> None:
    task = read("docs/the-task.md")
    for word in ("`timeout`", "`rate_limited`", "`not_ready`"):
        assert word in task, word
    own = read("docs/own-tools.md")
    dials = own[own.index("## The dials on your tools"):]
    dials = dials[: dials.index("\n## ", 1)]
    for knob in NEW:
        assert f"`{knob}`" in dials, knob
    # Retrofitted 2026-11-11 for 0.4.2 (#51): the errors table, with the 504 and 429 statuses,
    # moved with how the responses are made to docs/own-tools-reference.md.
    reference = read("docs/own-tools-reference.md")
    for code in ("504", "429", "`timeout`", "`rate_limited`"):
        assert code in reference, code


def test_the_changelog_and_contributing_say_what_0_3_0_moved() -> None:
    changelog = read("CHANGELOG.md")
    # Retrofitted 2026-11-03 for 0.3.1: 0.3.0's section is no longer the first one in the file, so
    # it is found by its heading; and CONTRIBUTING's count sentence is the newest release's.
    # Retrofitted again 2026-11-04 for 0.3.2: the count sentence may say 0.3.0, 0.3.1 or 0.3.2.
    # Retrofitted again 2026-11-04 for 0.4.0: or 0.4.0 (the stale-data spec's section 7.4).
    # Retrofitted again 2026-11-08 for 0.4.1: or 0.4.1 (the maintainer's ruling of 2026-11-08, the
    # 0.4.1 release-prep step).
    first = re.search(r"^## (0\.3\.0) \(", changelog, re.MULTILINE)
    assert first is not None and first.group(1) == "0.3.0"
    section = changelog[first.start(): changelog.index("\n## ", first.end())]
    assert "Every task id moved, and no built-in task did." in section
    assert "A write on your own tools now answers with what it was sent" in section
    assert "The generator changed to make the three" in section
    contributing = read("CONTRIBUTING.md")
    frozen = contributing[contributing.index("## The test files are frozen"):]
    frozen = frozen[: frozen.index("\n## ", 1)]
    assert "0.3.0" in frozen, frozen
    assert re.search(r"At 0\.(?:3\.[012]|4\.[01]) the suite is [\d,]+ tests", contributing)
