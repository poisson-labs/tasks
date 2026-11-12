"""A run closes every child process it started before its event loop closes (#52).

The flaky `test_fd5_19_nothing_happening_stops_with_exit_3_quoting_run_log` failed now and then
with three raw lines on the run's stderr:

    Exception ignored in: <function BaseSubprocessTransport.__del__ at 0x…>
    …
    RuntimeError: Event loop is closed

The start-up watchdog cancels the episode whose bootstrap hangs, and the harness kills that
bootstrap's process group as the cancellation passes (verifiers' `SubprocessRuntime.run`), but
nothing waits for the killed processes to be gone.  The run then returned, and `asyncio.run`
closed its loop at once.  If the killed processes had not yet let go of the ends of their output
pipes, the loop had not seen those pipes end, so the pipes were still open on the loop when it
closed; the process's transport, dropped later, tried to close them on the closed loop.  How long
a killed process takes to let go depends on how busy the machine is, which is why the test failed
in 2 of 5 runs of a loaded shard and not alone.

The fix: before its loop closes, a run waits (up to a limit) for every child process it started to
be reported ended, and closes each one's transport, pipes and all, while the loop can still do it.

The test takes the timing out: the stuck bootstrap leaves behind a process in a session of its own,
so the kill misses it, that holds the bootstrap's pipes open for a few seconds after the kill.
Before the fix the three lines appeared on every run.
"""

from __future__ import annotations

import os
import signal
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.fd3_support import KEY, KEY_VAR, MARK, marked_processes, needs_uv, stub_bin, wait_until
from tests.fd5_support import (
    World,
    assert_clean,
    fixture_flags,
    fresh,
    prog,
    world,
    write_config,
)
from tests.fixtures.model_server import FixtureModel

__all__ = ["prog", "world"]

HOLD_SECONDS = 4

FREQUENT_GC = "import gc\ngc.set_threshold(100, 1, 1)\n"
"""A `sitecustomize` for the child: the cyclic collector runs every few hundred allocations, so an
object left in a cycle is collected soon after it is dropped, not whenever the collector next
happens to run."""


@pytest.fixture
def fixture() -> Any:
    model = FixtureModel(slow_seconds=1.0)
    model.start()
    try:
        yield model
    finally:
        model.close()


def frequent_gc(where: Path) -> Path:
    where.mkdir(parents=True, exist_ok=True)
    (where / "sitecustomize.py").write_text(FREQUENT_GC, encoding="utf-8")
    return where


def stuck_bootstrap_with_a_holder(where: Path, started: Path) -> Path:
    """A `pip` that hangs, and before it does starts a process in a session of its own that keeps
    the bootstrap's stdout and stderr open until `HOLD_SECONDS` after the `pip` is killed: the
    harness's kill, which reaches
    the bootstrap's process group, does not reach it."""
    holder = (f'"{sys.executable}" -c "import os, time; os.setsid(); parent = os.getppid()\n'
              f'while os.getppid() == parent: time.sleep(0.05)\n'
              f'time.sleep({HOLD_SECONDS})" &')
    return stub_bin(where, pip=f"#!/bin/sh\necho $$ > {started}\n{holder}\nsleep 300\n",
                    old_uv=True)


@needs_uv
def test_a_run_the_watchdog_stops_closes_its_killed_bootstrap_before_the_loop_closes(
    fixture: FixtureModel, prog: str, world: World, tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """The stuck-bootstrap stop of `test_fd5_19_nothing_happening…`, with the bootstrap's pipes
    still open when the run's work is done: the stop is the same (exit 3, `stopped`, `run.log`
    quoted), and stderr holds only `note:` lines, nothing raw."""
    mark = "fx-reap-" + os.urandom(6).hex()
    started = tmp_path_factory.mktemp("hanging-pip-ran") / "pid"
    stubs = stuck_bootstrap_with_a_holder(tmp_path_factory.mktemp("hanging-pip"), started)
    write_config(world.work / "tasks.toml", fixture_flags(fixture.base_url))
    try:
        ran = fresh(["run", "--yes"], prog=prog, world=world,
                    package_root=frequent_gc(tmp_path_factory.mktemp("frequent-gc")),
                    job={"watchdog_seconds": 8},
                    env={"PATH": f"{stubs}{os.pathsep}{os.environ['PATH']}", KEY_VAR: KEY,
                         MARK: mark})
        assert started.exists(), "the stuck bootstrap never started"
        assert ran.code == 3, ran
        assert "stopped  nothing happened" in ran.out, ran
        assert "Event loop is closed" not in ran.err, ran
        assert "Exception ignored" not in ran.err, ran
        assert_clean(ran, "run")
        assert len([p for p in (world.work / "runs").iterdir() if p.is_dir()]) == 1
        assert wait_until(lambda: not marked_processes(mark), HOLD_SECONDS + 20), (
            marked_processes(mark))
    finally:
        for pid in marked_processes(mark):
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
