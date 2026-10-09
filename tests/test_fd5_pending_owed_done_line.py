"""Pending a yes/no: what `run` prints when every episode ran and some failed.

FD3 Session A's yes/no 2, ruled yes 2026-10-05: such a run ends `done`, exit 0, and its folder is
resumed, not complete (pinned in `tests/test_fd5_run.py`).  Spec §8.7 leaves the line to FD5 ("what
the done line says for it … is FD5's") and gives, for a run with nothing owed, `done  30 of 30
episodes, $0.021 spent` and `next: poisson-tasks card`.  Read beside a run that owes episodes, that
line says every episode was kept, which is not so: the spec's example is right only when nothing
is owed.

**Recommended yes:** the done line of a run that owes episodes says how many of the plan's
episodes were kept, out of how many, and how many failed and are owed again
(`done  29 of 30 episodes kept; 1 failed and is owed again, $0.021 spent`); it never says `N of N`
then; and its first `next:` command is the run again, which runs only the owed ones.  A card can
still be made (it is partial).

**A no** drops this file's commit; the done line is then the build's choice.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

import pytest

from tests.fd3_support import harness_env, needs_uv
from tests.fd5_support import (
    World,
    fixture_flags,
    invoke,
    next_commands,
    prog,
    verdict_lines,
    world,
    write_config,
)
from tests.fixtures.model_server import FixtureModel

__all__ = ["prog", "world", "harness_env"]


@needs_uv
def test_fd5_19_a_done_run_that_owes_episodes_says_how_many_and_runs_again_next(
    harness_env: Path, prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    with FixtureModel() as fixture:
        write_config(world.work / "tasks.toml",
                     fixture_flags(fixture.base_url, model="fixture-429-after-5",
                                   tasks_per_level=3, concurrency=1))
        ran = invoke(["run", "--yes"], prog=prog, monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    word, sentence = verdict_lines(ran.out, "run")[-1]
    assert word == "done"
    assert re.search(r"(?<!\d)2 of 3(?!\d)", sentence), sentence
    assert re.search(r"(?<![\d.$])1(?![\d.])", sentence.replace("2 of 3", "")), sentence
    assert "3 of 3" not in sentence
    first = shlex.split(next_commands(ran.out)[0])
    words = shlex.split(prog)
    assert first[: len(words) + 1] == [*words, "run"], first
