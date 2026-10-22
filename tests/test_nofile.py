"""A run's open files: room made at its start, or a refusal before anything starts.

Decided 2026-10-15, after the knob probe's gpt-5-nano run crashed at its start on macOS with
`OSError` 24, too many open files (a shell's soft limit there is 256; the run was at 128 episodes
at once):
- at the start of a run, the process's soft limit on open files is raised as far as the hard
  limit allows, for the run's length only;
- when that is still not enough for the plan, the run is refused before anything starts, in one
  line with the number needed and how to raise the limit, at the front door's refusal code.

Each side is one test, made through every way a run starts (`tests/nofile_child.py`): the command
(`poisson-tasks run`), the library (`runs.run_plan`), the knob probe's driver
(`knob_probe.run_probe`) and the calibration runner (`calibration.run_cell`, which
`calibration_run` and the Colab notebook use).  Each way runs in a process of its own whose limits
the test sets before anything is imported.

**The number a run needs** is pinned here, from the measurements filed with the fix
(`evidence/mac-open-files/`): 64, and 5 for each episode in flight.  A run never has more episodes
in flight than its concurrency, nor more than one arm's episodes, since arms run one after
another.  Measured at 128 in flight, a run hit the limit with a soft limit of 448 and ran clean
at 512 (490 open at its peak); at 8 in flight it holds about 40 open at its peak, which is why
`SOFT` below (24) is too few for a run that is not given room.

**How far the soft limit goes** is read here from the system, never from the code: the hard
limit, and on macOS no further than `kern.maxfilesperproc` (a hard limit of "unlimited" is the
default there, and a process can still open no more than that).
"""

from __future__ import annotations

import json
import resource
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.fd3_support import child_env, fixture_model, needs_uv, new_mark, stub_bin
from tests.fd5_support import fixture_flags, verdict_lines, write_config

__all__ = ["fixture_model"]
"""The fixture model, as the `test_fd3_*` tests have it."""

pytestmark = needs_uv

CHILD = Path(__file__).with_name("nofile_child.py")
CONCURRENCY = 32
EPISODES = 16
"""One arm of 16 episodes at a concurrency of 32: never more than 16 in flight."""
SOFT = 24
CELL_CONCURRENCY = 128
"""The calibration runner's concurrency: its config sets none, and the runner's own is 128."""


def needed(at_once: int) -> int:
    """The open files a run with `at_once` episodes in flight needs, as measured and decided."""
    return 64 + 5 * at_once


def at_once(entry: str) -> int:
    if entry == "cell":
        return min(CELL_CONCURRENCY, EPISODES)
    if entry == "probe":
        return min(CONCURRENCY, 120)  # the probe's arms are 60 tasks at two attempts
    return min(CONCURRENCY, EPISODES)


def how_far(hard: int) -> int:
    """As far as a soft limit can go under `hard`: the hard limit, and on macOS no further than
    the system's limit per process."""
    if sys.platform != "darwin":
        return hard
    cap = int(subprocess.run(["sysctl", "-n", "kern.maxfilesperproc"], capture_output=True,
                             text=True, check=True).stdout)
    return cap if hard == resource.RLIM_INFINITY else min(hard, cap)


def start(entry: str, where: Path, base_url: str, *, soft: int, hard: int | None,
          tmp: Path, episodes: int = EPISODES) -> dict[str, Any]:
    """`entry` in a process of its own with the limits given; what it returned, raised and
    printed."""
    job_dir = tmp / f"job-{entry}-{soft}-{hard}"
    job_dir.mkdir(parents=True)
    result = job_dir / "result.json"
    job = {"entry": entry, "where": str(where), "base_url": base_url, "soft": soft, "hard": hard,
           "concurrency": CONCURRENCY, "episodes": episodes, "result": str(result)}
    (job_dir / "job.json").write_text(json.dumps(job), encoding="utf-8")
    home = tmp / "home"
    home.mkdir(parents=True, exist_ok=True)
    env = child_env(home=home, stubs=stub_bin(tmp / "stub-bin"), mark=new_mark(),
                    extra={"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "100"})
    done = subprocess.run([sys.executable, str(CHILD), str(job_dir / "job.json")],
                          cwd=tmp, env=env, capture_output=True, timeout=900, check=False)
    assert result.exists(), done.stderr.decode("utf-8", "replace")[-3000:]
    body: dict[str, Any] = json.loads(result.read_text(encoding="utf-8"))
    body["stdout"] = done.stdout.decode("utf-8", "replace")
    body["stderr"] = done.stderr.decode("utf-8", "replace")
    return body


def place(entry: str, tmp: Path, base_url: str, name: str) -> Path:
    """Where `entry` runs: a working folder holding `tasks.toml` for the command, else a folder
    not yet made."""
    if entry != "command":
        return tmp / name
    work = tmp / name
    work.mkdir()
    write_config(work / "tasks.toml",
                 fixture_flags(base_url, tasks_per_level=EPISODES, concurrency=CONCURRENCY))
    return work


def tree(root: Path) -> list[str]:
    return sorted(str(path.relative_to(root)) for path in root.rglob("*")) if root.exists() \
        else []


def kept(folder: Path) -> int:
    """The `ok` rows of every `traces.jsonl` under `folder`."""
    rows = 0
    for traces in folder.rglob("traces.jsonl"):
        rows += sum(1 for line in traces.read_text(encoding="utf-8").splitlines()
                    if json.loads(line).get("ok"))
    return rows


@pytest.mark.parametrize("entry", ["command", "library", "cell"])
def test_with_room_to_raise_the_limit_is_raised_for_the_run_and_the_run_goes_ahead(
    entry: str, tmp_path: Path, fixture_model: Any
) -> None:
    """A soft limit too low for the run, under a hard limit with room: the run goes ahead and
    keeps every episode, with the soft limit as far as the hard limit allows while it runs, and
    the soft limit is back where it was after."""
    model = fixture_model
    where = place(entry, tmp_path, model.base_url, "run")
    ran = start(entry, where, model.base_url, soft=SOFT, hard=None, tmp=tmp_path)
    assert "raised" not in ran, ran
    assert ran["limits_before"][0] == SOFT
    assert ran["limits_after"] == ran["limits_before"], ran
    assert kept(where) == EPISODES, ran
    if entry == "command":
        assert ran["code"] == 0, ran
        assert [word for word, _ in verdict_lines(ran["stdout"], "run")] == ["plan", "done"], ran
    elif entry == "library":
        assert (ran["verdict"], ran["owed"]) == ("done", 0), ran
        assert ran["soft_during"] == [how_far(ran["limits_before"][1])], ran
    else:
        assert (ran["stop"], ran["owed"]) == (None, 0), ran


@pytest.mark.parametrize("entry", ["command", "library", "probe", "cell"])
def test_without_room_the_run_is_refused_in_one_line_and_nothing_starts(
    entry: str, tmp_path: Path, fixture_model: Any
) -> None:
    """A hard limit one short of what the run needs: refused in one line naming the number and
    how to raise the limit, with no request to the model, no file written and the soft limit as
    it was; the command and the driver print it as an `error:` line and exit 1, the library's
    words.  The control, a hard limit of exactly the number, gets past the check."""
    model = fixture_model
    need = needed(at_once(entry))
    # the library's words for the same number in flight, refused the same way
    library = start("library", tmp_path / "library-run", model.base_url, soft=need - 1,
                    hard=need - 1, tmp=tmp_path / "library",
                    episodes=at_once(entry)) if entry in ("command", "probe") else None
    assert library is None or "message" in library, library
    seen = len(model.requests)
    where = place(entry, tmp_path, model.base_url, "refused")
    before = tree(where)
    ran = start(entry, where, model.base_url, soft=need - 1, hard=need - 1, tmp=tmp_path)
    assert model.requests[seen:] == [], ran
    assert tree(where) == before, ran
    assert ran["limits_after"] == ran["limits_before"] == [need - 1, need - 1], ran
    if entry in ("command", "probe"):
        assert library is not None
        assert ran["code"] == 1, ran
        assert ran["stdout"] == "", ran
        assert ran["stderr"].splitlines() == ["error: " + library["message"]], ran
    else:
        assert "OSError" in ran["raised"], ran
        line = ran["message"]
        assert "\n" not in line and f"{need:,}" in line and f"ulimit -Hn {need}" in line, ran

    control_where = place(entry, tmp_path, model.base_url, "control")
    control = start(entry, control_where, model.base_url, soft=need, hard=need,
                    tmp=tmp_path / "control")
    if entry == "probe":
        assert control["code"] == 1 and "no-such.env" in control["stderr"], control
    else:
        assert "raised" not in control, control
        assert kept(control_where) == EPISODES, control


def test_where_there_is_no_resource_module_a_run_goes_ahead_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without `resource` (Windows), neither the check nor the room refuses, even for more
    episodes at once than any limit allows, and nothing is changed."""
    from poisson_tasks import _open_files

    monkeypatch.setitem(sys.modules, "resource", None)
    _open_files.check(10**9)
    with _open_files.room(10**9):
        pass
