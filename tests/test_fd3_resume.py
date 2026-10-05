"""Resume and Ctrl-C, frozen as tests: a stopped run loses nothing, and runs nothing twice.
These protect the user's work.

The invariants are FD3.7 and FD3.8 of the front door's plan (spec §8.5), with ruling 19
(2026-10-02): the first interrupt stops dispatching and gives the episodes in flight up to 10
seconds to finish and be recorded; a second stops at once.
- **FD3.7** after an interrupt following k finished episodes, for several k, and one in the middle
  of an episode, a resume gives the same multiset of (task id, attempt) as an uninterrupted run;
  no episode runs twice, and the lines already kept are byte for byte the same;
- **FD3.8** a SIGINT to a running `run_plan` process ends it with the interrupted verdict and the
  ledger written; a second SIGINT ends it at once, and a later resume completes the run under
  FD3.7; a torn last line is skipped or trimmed, as measured.

**Measured** (`evidence/front-door-fd3-a/measurements/torn-line.txt`): the wheel's own `resume.load` skips a
torn last line of `traces.jsonl` and owes that episode again (its own words: "a torn or
malformed row is owed again, never a crash"; frozen CAL23_4 pins it).  It also rewrites the file
to the rows it keeps, grouped by task, copying each kept row's bytes.  So "the lines already kept
are byte for byte the same" is pinned line by line, not as a prefix of the file.  The ledger is
this package's own file, append only: its whole lines before a resume are the start of it after.

**The interrupts.**  k is set by a spend cap in this process, with one episode at a time, so it
lands where the cap falls; the test checks it landed at three or more different points.  The
interrupt in the middle of an episode is a real one: two SIGINTs to a run in its own process
while its episodes are part way through (the fixture answers slowly).

**Ctrl-C in a process of its own** (`fd3_support.start_child`), sent as a terminal sends it: to
the run's whole process group (`fd3_support.interrupt`).  The run's processes carry a marker in
their environment; when the run has ended, none of them may still be running.  The fixture does
not count a held call whose client has gone, so an episode the interrupt abandoned is never
counted as started.

Shapes decided here
-------------------

**1. The interrupted verdict** is `RunResult.verdict == "stopped"` with `stop_reason ==
"interrupted"`, returned by `run_plan` after the first SIGINT.  After a second SIGINT `run_plan`
raises `KeyboardInterrupt` once it has stopped its episodes; the CLI maps both to exit 130
(FD5).

**2. "No episode runs twice"** is read off the fixture: the episodes a resume starts are exactly
the ones the stopped run owed.  An episode cut short by the interrupt or the cap was not kept, so
it is owed and run again as a fresh attempt (spec §8.5).
"""

from __future__ import annotations

import json
import time
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from tests.fd3_support import (
    arm_dir,
    call_dollars,
    child_env,
    child_result,
    fixture_model,
    harness_env,
    interrupt,
    ledger_count,
    ledger_lines,
    make_plan,
    marked_processes,
    needs_uv,
    new_mark,
    ok_lines,
    plan_spec,
    planned_tasks,
    reaped,
    run_here,
    scored_tasks,
    start_child,
    stub_bin,
    total_episodes,
    wait_until,
)
from tests.fixtures.model_server import FixtureModel

__all__ = ["fixture_model", "harness_env"]

pytestmark = needs_uv

EPS = 1e-9


def kept_lines(plan: Any, folder: Path) -> Counter[bytes]:
    out: Counter[bytes] = Counter()
    for spec in plan.arms:
        out.update(ok_lines(folder / arm_dir(spec)))
    return out


def ledger_bytes(folder: Path) -> bytes:
    path = folder / "spend.jsonl"
    return path.read_bytes() if path.exists() else b""


def whole_lines(data: bytes) -> bytes:
    return data[: data.rfind(b"\n") + 1]


def assert_resumed_cleanly(
    plan: Any, folder: Path, *, kept_before: Counter[bytes], ledger_before: bytes,
    owed_before: int, started_by_resume: int, resumed: Any,
) -> None:
    """FD3.7's three statements, after a resume ran a stopped run to its end."""
    assert (resumed.verdict, resumed.episodes_owed) == ("done", 0), resumed
    assert scored_tasks(plan, folder) == planned_tasks(plan), "not the uninterrupted multiset"
    after = kept_lines(plan, folder)
    missing = kept_before - after
    assert not missing, f"{sum(missing.values())} kept line(s) changed or lost"
    assert started_by_resume == owed_before, ("episodes run twice or skipped",
                                              started_by_resume, owed_before)
    assert resumed.episodes_run == owed_before
    assert resumed.episodes_kept == total_episodes(plan) - owed_before
    final = ledger_bytes(folder)
    assert final.startswith(whole_lines(ledger_before)), "the ledger was rewritten"
    for line in final.splitlines():
        json.loads(line)


# ---------------------------------------------------------------------------
# FD3.7 resume after k episodes
# ---------------------------------------------------------------------------


def test_fd3_7_a_resume_after_k_finished_episodes_gives_the_uninterrupted_run(
    tmp_path: Path, harness_env: Path, fixture_model: FixtureModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """depth:d1 then depth:d2, two tasks, two attempts: eight episodes, twenty cents.  Three caps,
    one episode at a time, stop it after different numbers of finished episodes; each is then
    resumed with the cap raised.  Every cap is above the reservation a run makes before its first
    episode (see `test_fd3_cap.py`), so each run moves before the cap stops it."""
    plan = make_plan(fixture_model.base_url, arms=("depth:d1", "depth:d2"), seeds=(404, 55),
                     attempts=2)
    base = tmp_path / "uninterrupted"
    whole_folder, whole = run_here(plan, base, monkeypatch, concurrency=1)
    assert whole.verdict == "done"
    assert scored_tasks(plan, Path(whole_folder.path)) == planned_tasks(plan)

    points: set[int] = set()
    for index, cap in enumerate((0.12, 0.15, 0.18)):
        runs_dir = tmp_path / f"interrupted-{index}"
        folder, stopped = run_here(plan, runs_dir, monkeypatch,
                                   caps={"spend_usd": cap, "tokens": None}, concurrency=1)
        assert stopped.stop_reason == "spend_cap", stopped
        path = Path(folder.path)
        kept_before = kept_lines(plan, path)
        points.add(sum(kept_before.values()))
        ledger_before = ledger_bytes(path)
        started = fixture_model.episodes_started()
        resumed_folder, resumed = run_here(plan, runs_dir, monkeypatch,
                                           caps={"spend_usd": 10.0, "tokens": None},
                                           concurrency=1)
        assert Path(resumed_folder.path) == path and resumed_folder.status == "resume"
        assert_resumed_cleanly(
            plan, path, kept_before=kept_before, ledger_before=ledger_before,
            owed_before=stopped.episodes_owed,
            started_by_resume=fixture_model.episodes_started() - started, resumed=resumed,
        )
    assert len(points) >= 3, f"the interrupts landed at only {sorted(points)}"


# ---------------------------------------------------------------------------
# FD3.8 Ctrl-C, in a process of its own
# ---------------------------------------------------------------------------


def child_job(plan: Any, runs_dir: Path, concurrency: int) -> dict[str, Any]:
    return {"plan": plan_spec(plan), "runs_dir": str(runs_dir),
            "caps": {"spend_usd": 10.0, "tokens": None}, "concurrency": concurrency}


def launch(tmp_path: Path, plan: Any, concurrency: int) -> tuple[Any, Path, str, Path]:
    mark = new_mark()
    stubs = stub_bin(tmp_path / "child-bin")
    env = child_env(home=tmp_path / "home", stubs=stubs, mark=mark)
    (tmp_path / "home").mkdir(exist_ok=True)
    runs_dir = tmp_path / "runs"
    process, result = start_child(child_job(plan, runs_dir, concurrency), env=env, cwd=tmp_path,
                                  work=tmp_path / "child")
    return process, result, mark, runs_dir


def folder_of(runs_dir: Path) -> Path:
    (folder,) = [path for path in runs_dir.iterdir() if path.is_dir()]
    return folder


def no_process_left(mark: str) -> bool:
    return wait_until(lambda: not marked_processes(mark), 10.0, 0.2)


def just_called(model: FixtureModel) -> bool:
    """A call reached the fixture in the last tenth of a second: every episode in flight is then
    at least a second from its end."""
    posts = model.posts()
    return bool(posts) and time.time() - max(seen.at for seen in posts) < 0.1


def reached(process: Any, condition: Callable[[], bool], work: Path) -> None:
    """Wait for `condition` while the child runs; a child that ended first fails the test with
    the end of its stderr."""
    met: list[bool] = []

    def check() -> bool:
        if condition():
            met.append(True)
            return True
        return process.poll() is not None

    wait_until(check, 120, 0.02)
    if not met:
        err = (work / "stderr.txt").read_text(encoding="utf-8", errors="replace")[-2000:]
        raise AssertionError(f"the run never got there (exit {process.poll()}):\n{err}")


def test_fd3_8_the_first_interrupt_lets_the_episodes_in_flight_finish(
    tmp_path: Path, harness_env: Path, fixture_model: FixtureModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Six episodes of three calls, two at a time, each call answered after a second and a half.
    Ctrl-C once the first episode is in the ledger, sent just after a call has reached the
    fixture, so that no episode is about to finish while the signal is being handled: the two in
    flight finish and are recorded, no other starts, and the run ends with the interrupted verdict
    well inside ten seconds.  A resume then runs the rest, keeping what the interrupted run kept."""
    fixture_model.slow_seconds = 1.5
    plan = make_plan(fixture_model.base_url, model="fixture-slow", arms=("depth:d2",),
                     seeds=(404, 55, 2121), attempts=2)
    process, result_path, mark, runs_dir = launch(tmp_path, plan, 2)
    with reaped(process, mark):
        reached(process, lambda: runs_dir.exists() and any(
            ledger_count(path) >= 1 for path in runs_dir.iterdir() if path.is_dir()),
            tmp_path / "child")
        reached(process, lambda: just_called(fixture_model), tmp_path / "child")
        interrupt(process)
        sent = time.monotonic()
        finished_at_interrupt = ledger_count(folder_of(runs_dir))
        process.wait(60)
        elapsed = time.monotonic() - sent
        assert no_process_left(mark), marked_processes(mark)
    result = child_result(result_path)
    assert (result["verdict"], result["stop_reason"]) == ("stopped", "interrupted"), result
    assert elapsed < 10.0, elapsed
    folder = folder_of(runs_dir)
    lines = ledger_lines(folder)
    started = fixture_model.episodes_started()
    assert started == len(lines) == result["episodes_run"], (started, len(lines), result)
    assert started <= finished_at_interrupt + 2, "episodes were started after the interrupt"
    assert result["episodes_owed"] == total_episodes(plan) - result["episodes_run"] > 0
    spent = fixture_model.calls() * call_dollars()
    assert abs(result["spend"] - spent) < EPS
    assert abs(sum(line["dollars"] for line in lines) - spent) < EPS

    kept_before = kept_lines(plan, folder)
    assert sum(kept_before.values()) == result["episodes_run"]
    ledger_before = ledger_bytes(folder)
    fixture_model.slow_seconds = 0.02
    started = fixture_model.episodes_started()
    _, resumed = run_here(plan, runs_dir, monkeypatch, concurrency=2)
    assert_resumed_cleanly(
        plan, folder, kept_before=kept_before, ledger_before=ledger_before,
        owed_before=result["episodes_owed"],
        started_by_resume=fixture_model.episodes_started() - started, resumed=resumed,
    )


def test_fd3_8_the_first_interrupt_waits_ten_seconds_and_no_longer(
    tmp_path: Path, harness_env: Path, fixture_model: FixtureModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same run with each call held for a minute: the episodes in flight cannot finish.  The
    run waits ten seconds for them, then stops them, records what it spent, and leaves nothing
    running; a resume then runs every episode.  The upper bound leaves room for stopping the
    harness's processes and the interpreter's own exit."""
    fixture_model.slow_seconds = 60.0
    plan = make_plan(fixture_model.base_url, model="fixture-slow", arms=("depth:d2",),
                     seeds=(404, 55, 2121), attempts=2)
    process, result_path, mark, runs_dir = launch(tmp_path, plan, 2)
    with reaped(process, mark):
        reached(process, lambda: len(fixture_model.posts()) >= 2, tmp_path / "child")
        interrupt(process)
        sent = time.monotonic()
        process.wait(60)
        elapsed = time.monotonic() - sent
        assert no_process_left(mark), marked_processes(mark)
    result = child_result(result_path)
    assert (result["verdict"], result["stop_reason"]) == ("stopped", "interrupted"), result
    assert 9.0 <= elapsed <= 20.0, elapsed
    folder = folder_of(runs_dir)
    assert result["episodes_run"] == 0 and result["episodes_owed"] == total_episodes(plan)
    assert abs(result["spend"] - sum(line["dollars"] for line in ledger_lines(folder))) < EPS

    fixture_model.slow_seconds = 0.02
    started = fixture_model.episodes_started()
    _, resumed = run_here(plan, runs_dir, monkeypatch, concurrency=2)
    assert_resumed_cleanly(
        plan, folder, kept_before=Counter(), ledger_before=ledger_bytes(folder),
        owed_before=total_episodes(plan), started_by_resume=fixture_model.episodes_started()
        - started, resumed=resumed,
    )


def test_fd3_8_a_second_interrupt_stops_at_once_and_a_resume_completes_the_run(
    tmp_path: Path, harness_env: Path, fixture_model: FixtureModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FD3.7's interrupt in the middle of an episode, after some were kept.  depth:d1 then
    depth:d8, two tasks each, two at a time, each call answered after three seconds.  Once both
    depth:d1 episodes are in the ledger and the depth:d8 ones have had a call answered, Ctrl-C
    twice: the run stops within a few seconds of the second, well before the ten the first allows
    (the episodes in flight would need some twenty more), and leaves nothing running.  A process
    killed mid-write is then imitated: half a line at the end of the trace file and of the
    ledger.  The resume skips or trims both, keeps the two kept episodes' lines, and gives the
    uninterrupted run."""
    fixture_model.slow_seconds = 3.0
    plan = make_plan(fixture_model.base_url, model="fixture-slow", arms=("depth:d1", "depth:d8"),
                     seeds=(404, 55))
    process, result_path, mark, runs_dir = launch(tmp_path, plan, 2)
    with reaped(process, mark):
        reached(process, lambda: fixture_model.calls() >= 2 * 2 + 2, tmp_path / "child")
        interrupt(process)
        time.sleep(0.3)
        interrupt(process)
        sent = time.monotonic()
        process.wait(60)
        elapsed = time.monotonic() - sent
        assert no_process_left(mark), marked_processes(mark)
    assert elapsed < 6.0, elapsed
    assert child_result(result_path) == {"keyboard_interrupt": True}
    folder = folder_of(runs_dir)
    kept_before = kept_lines(plan, folder)
    assert sum(kept_before.values()) == 2, "the depth:d1 episodes were not kept"
    arm = folder / arm_dir(plan.arms[1])
    arm.mkdir(exist_ok=True)
    with (arm / "traces.jsonl").open("a", encoding="utf-8") as handle:
        handle.write('{"task": {"hash": "')
    with (folder / "spend.jsonl").open("a", encoding="utf-8") as handle:
        handle.write('{"arm": "depth:d8", "se')
    ledger_before = ledger_bytes(folder)

    fixture_model.slow_seconds = 0.02
    started = fixture_model.episodes_started()
    found, resumed = run_here(plan, runs_dir, monkeypatch, concurrency=2)
    assert Path(found.path) == folder and found.status == "resume"
    assert_resumed_cleanly(
        plan, folder, kept_before=kept_before, ledger_before=ledger_before, owed_before=2,
        started_by_resume=fixture_model.episodes_started() - started, resumed=resumed,
    )
