"""Pending a yes/no (`evidence/front-door-fd3-a/rulings.md`, yes/no 2): a run whose every episode ran, one
of them failed, is not complete.  Its folder is resumed, and the resume runs that one episode
again and nothing else.

This is the wheel's own rule, which `run_arm` already follows (frozen CAL23): `resume.load` keeps
the rows that ended well and owes the failed ones again.  The instrument tally keeps the failure
(CAL16: it is written at the moment of failure and a resume never touches it), so a card still
counts it.  The other reading, "complete once every episode has run", would leave a failed
episode out of the card's attempts for good.

The failure is the provider's: the fixture answers the first four calls (two episodes of two
calls) and refuses every later one with a 429, then is made to forget its count, as a provider
whose rate limit has passed.

Shapes decided here: the run that had the failure ends `done` (its every episode ran, and one had
already been scored, so it is no failure streak) with one episode owed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fd3_support import (
    arm_dir,
    calibration,
    fixture_model,
    harness_env,
    make_plan,
    needs_uv,
    planned_tasks,
    run_here,
    runs,
    scored_tasks,
)
from tests.fixtures.model_server import FixtureModel

__all__ = ["fixture_model", "harness_env"]

pytestmark = needs_uv


def test_fd3_2_a_run_with_a_failed_episode_is_resumed_and_runs_that_episode_again(
    tmp_path: Path, harness_env: Path, fixture_model: FixtureModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = make_plan(fixture_model.base_url, model="fixture-429-after-4",
                     seeds=(404, 55, 2121))
    folder, first = run_here(plan, tmp_path, monkeypatch, concurrency=1)
    assert (first.verdict, first.episodes_run, first.episodes_owed) == ("done", 3, 1), first
    found = runs().find_run(plan, tmp_path)
    assert (Path(found.path), found.status) == (Path(folder.path), "resume")

    fixture_model.forget()
    started = fixture_model.episodes_started()
    _, resumed = run_here(plan, tmp_path, monkeypatch, concurrency=1)
    assert (resumed.verdict, resumed.episodes_run, resumed.episodes_owed) == ("done", 1, 0)
    assert fixture_model.episodes_started() - started == 1
    assert runs().find_run(plan, tmp_path).status == "complete"
    assert scored_tasks(plan, Path(folder.path)) == planned_tasks(plan)
    assert calibration().read_tally(Path(folder.path) / arm_dir(plan.arms[0])) == {"api_error": 1}
