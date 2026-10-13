"""Pending a yes/no: what running the driver again does.

**The question.**  The spec says a stop leaves the finished arms standing; it does not say what a
second run of the driver does after a stop, a failed phase 1 or a finished probe.

**Proposed:** after a stop, the same command resumes: the run engine runs what is owed, within the
same cap over the folder's two ledgers (and, as its resume does, runs again any episode that ended
in an instrument failure, every one of which stays in its arm's tally and instrument rate).  A
failed phase 1 is final for its folder: the command reports it and runs nothing (a new folder
starts again).  A probe that finished is not run again: the command writes the outcome again and
runs nothing, so no failed episode is quietly run twice; only a recorded re-run of a void arm
reopens it.  **A no** changes any of the three.
"""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

import pytest

from tests.fd2_fakes import network_guard
from tests.k9_fake import Behaviour, running
from tests.k9_support import env_file, harness, needs_uv

pytestmark = needs_uv


def tiny() -> Any:
    from poisson_tasks import knob_probe as probe

    return probe.Design(
        arms=("similarity:s0", "similarity:s3"),
        phase1_seeds=probe.PHASE1_SEEDS,
        probe_seeds=probe.PROBE_SEEDS[:2],
    )


def twice(where: Path, first: Behaviour) -> list[tuple[int, int, str]]:
    """Run the tiny design twice into one folder; each run's exit code, model calls and lines."""
    from poisson_tasks import knob_probe as probe

    design = tiny()
    found = []
    with pytest.MonkeyPatch.context() as mp, harness(where, mp), network_guard(mp):
        with running(design.arms, [*design.phase1_seeds, *design.probe_seeds], first) as fake:
            for _ in range(2):
                before = len(fake.posts)
                out = io.StringIO()
                with redirect_stdout(out):
                    code = probe.run_probe(
                        where / "run",
                        cap=1.0,
                        concurrency=4,
                        env_file=env_file(where),
                        base_url=fake.base_url,
                        design=design,
                    )
                found.append((code, len(fake.posts) - before, out.getvalue()))
    return found


def test_a_finished_probe_is_not_run_again(tmp_path: Path) -> None:
    (code, calls, _), (again, more, said) = twice(tmp_path, Behaviour())
    assert code == 0 and calls > 0
    assert again == 0 and more == 0 and "nothing to run" in said
    assert (tmp_path / "run" / "outcome.json").exists()
    record = json.loads((tmp_path / "run" / "record.json").read_text())
    assert len(record["invocations"]) == 2


def test_a_failed_phase_1_is_final_for_its_folder(tmp_path: Path) -> None:
    behaviour = Behaviour.from_mapping({"no_call": ["similarity:s0"]})
    (code, _, _), (again, more, said) = twice(tmp_path, behaviour)
    assert code == 2 and again == 2 and more == 0
    assert "phase 1 failed in this folder" in said
