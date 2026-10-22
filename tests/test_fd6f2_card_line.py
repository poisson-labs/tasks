"""A card on your own tools names the comparison with the published cards only when it works
(decided with the documentation's second round of fixes).

The first round of fixes left the line `next: poisson-tasks card --compare published` on every card
made from your own tools.  The comparison puts your card beside the published card of the same
model, so for a model no published card measured it refuses in one line ("no published card measured
…"), and a user following the line got that refusal.  Now the line is there exactly when following
it works.

Three runs on the acme tools, each played by the scripted endpoint, differ only in the model the
settings name:

- `gpt-5-nano-2025-08-07`, a model a published card measured;
- `Qwen/Qwen3-8B`, which the other published card records with a revision
  (`Qwen/Qwen3-8B@b968826d…`), so the match must ignore the revision, as the comparison does;
- `scripted`, which no published card measured.

The test ties the line to what following it does in each: the line is there if and only if the
comparison exits 0, and where it is there the comparison prints the published card beside the
run's, and where it is not the comparison exits 1 with the one-line reason.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tests.helpers import needs_uv
from tests.o1_support import fixture
from tests.o2_support import reference_model, runs
from tests.test_o2_cli import invoke, work
from tests.test_o2_run import own_bundles, plan_for

__all__ = ["work"]

COMPARE = ("--compare", "published")
PUBLISHED_MODEL = "gpt-5-nano-2025-08-07"
REVISIONED_MODEL = "Qwen/Qwen3-8B"


def next_lines(out: str) -> list[str]:
    return [line.strip() for line in out.splitlines() if line.strip().startswith("next:")]


def run_on_own_tools(tmp_path_factory: pytest.TempPathFactory, model: str | None) -> Iterator[Path]:
    """One run of `first-look` on the acme set, two tasks a level, under `model` (or the scripted
    endpoint's own name when none is given); its folder."""
    if shutil.which("uv") is None:
        pytest.skip("the `null` harness launches its program through uv")
    folder_work = tmp_path_factory.mktemp("own-run")
    (folder_work / "tools.json").write_bytes(fixture("acme-mcp-tools-list.json"))
    saved = os.environ.get("O2_API_KEY")
    os.environ["O2_API_KEY"] = "EMPTY"
    try:
        with reference_model() as served:
            plan = plan_for(folder_work, served.base_url, *(["--model", model] if model else []))
            bundles = own_bundles(plan)
            for bundle in bundles:
                served.register(bundle)
            folder = runs().find_run(plan, folder_work / "runs")
            result = runs().run_plan(plan, folder, caps={"spend_usd": None, "tokens": 1_000_000},
                                     concurrency=1, watchdog_seconds=300)
            assert (result.verdict, result.episodes_run) == ("done", len(bundles))
        yield Path(folder.path)
    finally:
        if saved is None:
            os.environ.pop("O2_API_KEY", None)
        else:
            os.environ["O2_API_KEY"] = saved


@pytest.fixture(scope="module")
def published_run(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    yield from run_on_own_tools(tmp_path_factory, PUBLISHED_MODEL)


@pytest.fixture(scope="module")
def revisioned_run(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    yield from run_on_own_tools(tmp_path_factory, REVISIONED_MODEL)


@pytest.fixture(scope="module")
def unpublished_run(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    yield from run_on_own_tools(tmp_path_factory, None)


@needs_uv
@pytest.mark.parametrize(
    ("which", "measured"),
    [("published_run", True), ("revisioned_run", True), ("unpublished_run", False)],
    ids=["published-model", "published-model-with-a-revision", "no-published-card"],
)
def test_the_comparison_line_is_there_exactly_when_following_it_works(
    which: str, measured: bool, request: pytest.FixtureRequest, work: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source: Any = request.getfixturevalue(which)
    folder = work / "run"
    shutil.copytree(source, folder)
    ran = invoke(["card", str(folder), "--force"], monkeypatch)
    assert ran.code == 0, ran
    lines = next_lines(ran.out)
    followed = invoke(["card", str(folder), *COMPARE, "--force"], monkeypatch)
    # Retrofitted with the guided session: no card on your own tools names the comparison;
    # asked for, it says `different` and exits 0, and where a published card measured the model,
    # `compare.md` holds that card beside the run's.
    assert lines == [], lines
    assert followed.code == 0 and followed.out.startswith("different  "), followed
    if measured:
        compare = (folder / "card" / "compare.md").read_text(encoding="utf-8")
        assert "The published card" in compare, compare[:400]
