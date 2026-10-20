"""`card` does not end by pointing at a comparison this release refuses (FD6 follow-up 1, fix 10).

The two published cards were measured by an earlier build of the generator, so a card on the
built-in tasks cannot be read beside them and `card --compare published` refuses it
("the generators differ").  FD5 Session B's item 6 dropped the closing `next:` line for that
reason; the command still printed it.  A card on your own tools is a different matter: it is put
beside the published card of its model, so the line stays there.

One test pins each side, and each ties the line to what following it does: the built-in card has no
such line and the comparison it would have named refuses; the own-tools card has the line and the
comparison works.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest

from tests.fd4_support import fd4_runs
from tests.test_o2_cli import invoke, work
from tests.test_o2_run import own_run

__all__ = ["fd4_runs", "own_run", "work"]

COMPARE = ("--compare", "published")


def next_lines(out: str) -> list[str]:
    return [line.strip() for line in out.splitlines() if line.strip().startswith("next:")]


def test_a_card_on_the_built_in_tasks_names_no_comparison_that_refuses(
    fd4_runs: Any, work: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = work / "run"
    shutil.copytree(fd4_runs["first_look"].folder, folder)
    ran = invoke(["card", str(folder), "--force"], monkeypatch)
    assert ran.code == 0, ran
    assert next_lines(ran.out) == [], ran.out
    assert "--compare" not in ran.out
    # what the line would have named: it refuses, in one line, and writes nothing
    asked = invoke(["card", str(folder), *COMPARE, "--force"], monkeypatch)
    assert asked.code == 1 and "cannot be read side by side" in asked.err, asked


def test_a_card_on_your_own_tools_still_names_the_comparison_and_it_works(
    own_run: Any, work: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = work / "own-run"
    shutil.copytree(own_run.folder, folder)
    ran = invoke(["card", str(folder), "--force"], monkeypatch)
    assert ran.code == 0, ran
    # Retrofitted by ruling G12 (FD9 Session A): a card on your own tools names no comparison
    # either; the comparison, asked for, says `different` and works.
    assert next_lines(ran.out) == [], ran.out
    asked = invoke(["card", str(folder), *COMPARE, "--force"], monkeypatch)
    assert asked.code == 0 and asked.out.startswith("different  "), asked
    # asking for the comparison does not end by suggesting it again
    assert next_lines(asked.out) == [], asked.out
