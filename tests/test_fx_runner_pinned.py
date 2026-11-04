"""CI runs on a runner image that does not move (issue #36).

`ubuntu-latest` is the image GitHub points at the newest Ubuntu it has decided to support, and it
moves without a commit here: the run's annotation of 2026-10-27 said the label is moving to Ubuntu
26.  The fast lane and the whole-suite workflow are green on 24.04, so every job names that image,
and a move to a newer one is a commit that is seen, with a run behind it.

- **FX36.1** every job of every workflow file has `runs-on: ubuntu-24.04`, written as that string:
  not a `-latest` label, not a matrix value, not a list.
- **FX36.2** the workflow files are found, not listed, so a workflow added later is held to the
  same rule without a test being edited, and there are workflows to hold (the test does not pass
  on an empty folder).
"""

from __future__ import annotations

from typing import Any

import pytest
import yaml

from tests.fd6_support import REPO

WORKFLOWS = REPO / ".github" / "workflows"
IMAGE = "ubuntu-24.04"


def jobs() -> list[tuple[str, str, Any]]:
    """Every job of every workflow file, as (file name, job key, its `runs-on`)."""
    found = []
    for path in sorted(WORKFLOWS.glob("*.y*ml")):
        workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
        for key, job in workflow["jobs"].items():
            found.append((path.name, key, job.get("runs-on")))
    return found


def test_fx36_2_there_are_workflows_and_jobs_to_hold() -> None:
    names = {name for name, _key, _runs_on in jobs()}
    assert {"ci.yml", "suite.yml"} <= names, names
    assert len(jobs()) >= 6, jobs()


@pytest.mark.parametrize(("name", "key", "runs_on"), jobs(), ids=lambda value: str(value))
def test_fx36_1_every_job_runs_on_the_pinned_image(name: str, key: str, runs_on: Any) -> None:
    assert runs_on == IMAGE, f"{name}: job {key} runs on {runs_on!r}, not {IMAGE}"
