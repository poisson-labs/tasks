"""How a run stops when it cannot work, frozen as tests: the failure streak, the start-up
watchdog and the provider out of credit, through `runs.run_plan`.

The invariants are FD3.9, FD3.10 and FD3.15 of the front door's plan (spec §8.7), with ruling 20
(2026-10-02: a 600-second start-up watchdog and a five-episode failure streak):
- **FD3.9** a fixture answering 429 to every call stops the run after five episodes, with the first
  error's status and message in `first_error`, and the verdict is never done.  So does a toolset
  whose server never reports its port, with the launch poll shortened; its trace's `ToolsetError`
  text is the `first_error`.  A run in which every episode failed never returns done;
- **FD3.10** with no model call and no finished episode within the watchdog's limit, the run
  stops, quoting the last lines of `run.log`.  The limit is a parameter, 600 s by default and short
  here.  A launch failure reaches the failure streak before the default limit;
- **FD3.15** the provider's 402, or a 429 naming quota or billing, still stops the run cleanly
  (`calibration._provider_exhausted`'s cases).

**Measured** (`evidence/front-door-fd3-a/measurements/`): a 429 reaches the episode as verifiers' `ProviderError`
with `status_code` 429 and the provider's body in its message, after the harness's SDK has retried
it twice; a 402 is not retried.  A tool server that never reports its port fails in-process after
verifiers' 180-second poll, with no model call: the trace carries `ToolsetError: server did not
report its port at /tmp/vf-port-<hex> in its runtime: <the server's log tail>` and the episode
ends as `api_error`.  Here the server is made to exit before it binds (a `sitecustomize` on the
tool server's `PYTHONPATH` that acts only where `MCP_PORT_FILE` is set) and the poll is cut to two
seconds by replacing verifiers' `_read_back_port` with the same loop, shorter.

**The watchdog's run never makes a model call**: the harness's bootstrap hangs (a `pip` that
sleeps), the case the watchdog is for, "stuck before its first model call for any other reason"
(spec §8.7).  It runs in a process of its own, because the bootstrap runs once per process.

Shapes decided here
-------------------

**1. The stop reasons** are `"failure_streak"`, `"watchdog"` and `"provider_exhausted"`, with
verdict `"stopped"`.

**2. `first_error`** is one string carrying the first failed episode's status and the provider's
own words, or the trace's own error text where there is no status.  How they are put together is
not pinned.

**3. A run whose every episode failed** before any was scored stops as `"failure_streak"` even
when it had fewer than five episodes: it is the same streak, cut short by the end of the plan.
Once an episode has been scored, failures no longer stop the run (spec §8.7: "before any episode
is scored").

**4. `log_tail`** on `RunResult` holds the quoted lines when the watchdog stops the run: lines of
`run.log` as written, one after another, among them the arm the run was serving (the run writes
its own progress there, FD3.16).

**5. The watchdog's limit** is `run_plan`'s keyword `watchdog_seconds`, 600 by default.
"""

from __future__ import annotations

import importlib
import inspect
import json
import time
from pathlib import Path
from typing import Any

import pytest

from tests.fd3_support import (
    child_env,
    child_result,
    fixture_model,
    harness_env,
    make_plan,
    marked_processes,
    needs_uv,
    new_mark,
    plan_spec,
    reaped,
    run_here,
    runs,
    start_child,
    stub_bin,
    total_episodes,
    trace_lines,
    wait_until,
)
from tests.fixtures.model_server import (
    CREDIT_MESSAGE,
    QUOTA_MESSAGE,
    RATE_LIMIT_MESSAGE,
    FixtureModel,
)

__all__ = ["fixture_model", "harness_env"]

pytestmark = needs_uv

SEEDS = (404, 55, 2121, 7, 8, 9, 10, 11, 12, 13, 14, 15)


def outside(text: str, *parts: str) -> str:
    """`text` without the provider's words and the model's name, both of which may hold the
    status's digits (`fixture-429`), so that what is left shows whether the status is there."""
    for part in parts:
        text = text.replace(part, "")
    return text


# ---------------------------------------------------------------------------
# FD3.9 the failure streak
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("concurrency", [1, 4])
def test_fd3_9_five_failed_episodes_in_a_row_stop_the_run(
    tmp_path: Path, harness_env: Path, fixture_model: FixtureModel,
    monkeypatch: pytest.MonkeyPatch, concurrency: int,
) -> None:
    plan = make_plan(fixture_model.base_url, model="fixture-429", seeds=SEEDS[:6], attempts=2)
    _, result = run_here(plan, tmp_path, monkeypatch, concurrency=concurrency)
    assert (result.verdict, result.stop_reason) == ("stopped", "failure_streak"), result
    if concurrency == 1:
        assert result.episodes_run == 5
    else:
        assert 5 <= result.episodes_run <= 5 + concurrency - 1, result
    assert result.episodes_owed == total_episodes(plan) and result.episodes_kept == 0
    words = RATE_LIMIT_MESSAGE.format(model="fixture-429")
    assert result.first_error is not None and words in result.first_error
    assert "429" in outside(result.first_error, words, "fixture-429"), "no status in first_error"


def test_fd3_9_a_run_whose_every_episode_failed_is_never_done(
    tmp_path: Path, harness_env: Path, fixture_model: FixtureModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Three episodes, all failed: fewer than five, and still not done (P7's case)."""
    plan = make_plan(fixture_model.base_url, model="fixture-429", seeds=SEEDS[:3])
    _, result = run_here(plan, tmp_path, monkeypatch, concurrency=1)
    assert result.episodes_run == 3
    assert (result.verdict, result.stop_reason) == ("stopped", "failure_streak"), result
    words = RATE_LIMIT_MESSAGE.format(model="fixture-429")
    assert result.first_error is not None and words in result.first_error


def test_fd3_9_once_an_episode_is_scored_failures_do_not_stop_the_run(
    tmp_path: Path, harness_env: Path, fixture_model: FixtureModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The control: the first episode is answered (two calls) and scored, every later call is a
    429.  Six failures in a row follow a scored episode, so nothing stops the run early."""
    plan = make_plan(fixture_model.base_url, model="fixture-429-after-2", seeds=SEEDS[:7])
    _, result = run_here(plan, tmp_path, monkeypatch, concurrency=1)
    assert (result.verdict, result.stop_reason) == ("done", None), result
    assert result.episodes_run == 7
    assert result.episodes_owed == 6, "the six failed episodes are owed again (the wheel's rule)"


NO_PORT = """\
import os
if os.environ.get("MCP_PORT_FILE"):
    os._exit(3)
"""


def short_poll(launch: Any) -> Any:
    """verifiers' own `_read_back_port`, polling six times half a second apart instead of 180
    times a second apart, and failing the same way."""

    async def read_back_port(runtime: Any, path: str) -> int:
        import asyncio
        import contextlib

        for _ in range(6):
            with contextlib.suppress(Exception):
                data = (await runtime.read(path)).decode().strip()
                if data.isdigit():
                    return int(data)
            await asyncio.sleep(0.5)
        raise launch.ToolsetError(f"server did not report its port at {path} in its runtime")

    return read_back_port


def test_fd3_9_and_fd3_10_a_tool_server_that_never_starts_is_a_failure_streak_not_the_watchdog(
    tmp_path: Path, harness_env: Path, fixture_model: FixtureModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No episode ever makes a model call, and each one ends, failed, some four seconds in (three
    of polling).  The watchdog's limit is set below the time the five failures take and above the
    time the first takes, with room for this process's first harness bootstrap: a finished
    episode satisfies it, so the stop is the streak's, and its error is the trace's."""
    launch = importlib.import_module("verifiers.v1.mcp.launch")
    site = tmp_path / "no-port"
    site.mkdir()
    (site / "sitecustomize.py").write_text(NO_PORT, encoding="utf-8")
    monkeypatch.setenv("PYTHONPATH", str(site))
    monkeypatch.setattr(launch, "_read_back_port", short_poll(launch))
    plan = make_plan(fixture_model.base_url, seeds=SEEDS)
    limit = 15.0
    begun = time.monotonic()
    folder, result = run_here(plan, tmp_path / "runs", monkeypatch, concurrency=1,
                              watchdog_seconds=limit)
    took = time.monotonic() - begun
    assert fixture_model.posts() == [], "a model call was made"
    assert took > limit, f"the run took {took:.1f} s, too short to tell the watchdog's stop apart"
    assert (result.verdict, result.stop_reason) == ("stopped", "failure_streak"), result
    assert result.episodes_run == 5
    errors: list[dict[str, Any]] = []
    for line in trace_lines(Path(folder.path) / "depth-d1"):
        for trace in json.loads(line).get("traces", []):
            errors.extend(error for error in trace.get("errors", [])
                          if error.get("type") == "ToolsetError")
    assert errors, "no trace recorded the launch failure"
    head = errors[0]["message"].splitlines()[0]
    first_line = head[: head.index(" in its runtime") + len(" in its runtime")]
    assert result.first_error is not None and first_line in result.first_error, (
        first_line, result.first_error)


# ---------------------------------------------------------------------------
# FD3.10 the watchdog
# ---------------------------------------------------------------------------


def test_fd3_10_the_watchdogs_limit_is_six_hundred_seconds_by_default() -> None:
    parameter = inspect.signature(runs().run_plan).parameters["watchdog_seconds"]
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert parameter.default == 600


HANGING_PIP = """#!/bin/sh
echo $$ > "{pid}"
exec sleep 600
"""


def test_fd3_10_a_run_stuck_before_its_first_model_call_stops_quoting_run_log(
    tmp_path: Path, fixture_model: FixtureModel,
) -> None:
    """The harness's bootstrap never returns.  With a three-second limit the run stops soon
    after, having called nothing, quoting where it was; the stuck bootstrap is stopped too."""
    pid_file = tmp_path / "pip.pid"
    stubs = stub_bin(tmp_path / "bin", pip=HANGING_PIP.format(pid=pid_file))
    mark = new_mark()
    (tmp_path / "home").mkdir()
    env = child_env(home=tmp_path / "home", stubs=stubs, mark=mark)
    plan = make_plan(fixture_model.base_url, seeds=(404, 55))
    job = {"plan": plan_spec(plan), "runs_dir": str(tmp_path / "runs"),
           "caps": {"spend_usd": 1.0, "tokens": None}, "concurrency": 2,
           "watchdog_seconds": 3.0}
    process, result_path = start_child(job, env=env, cwd=tmp_path, work=tmp_path / "child")
    begun = time.monotonic()
    with reaped(process, mark):
        process.wait(120)
        took = time.monotonic() - begun
        assert wait_until(lambda: not marked_processes(mark), 10.0, 0.2), marked_processes(mark)
    result = child_result(result_path)
    assert pid_file.exists(), "the bootstrap's pip never ran"
    stuck = int(pid_file.read_text().strip())
    assert stuck not in marked_processes(mark), "the stuck bootstrap is still running"
    assert (result["verdict"], result["stop_reason"]) == ("stopped", "watchdog"), result
    assert took < 60, took
    assert fixture_model.posts() == []
    assert result["episodes_run"] == 0 and result["episodes_owed"] == total_episodes(plan)
    tail = result["log_tail"]
    assert isinstance(tail, str) and tail.strip()
    folder = Path(result["folder"])
    log = (folder / "run.log").read_text(encoding="utf-8").splitlines()
    quoted = tail.splitlines()
    assert any(log[i:i + len(quoted)] == quoted for i in range(len(log))), "not lines of run.log"
    assert "depth:d1" in tail, "the quoted lines do not say which arm the run was serving"


# ---------------------------------------------------------------------------
# FD3.15 out of credit
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("model, status, words", [
    ("fixture-402", "402", CREDIT_MESSAGE),
    ("fixture-429-quota", "429", QUOTA_MESSAGE),
])
def test_fd3_15_the_provider_out_of_credit_stops_the_run_at_once(
    tmp_path: Path, harness_env: Path, fixture_model: FixtureModel,
    monkeypatch: pytest.MonkeyPatch, model: str, status: str, words: str,
) -> None:
    """One episode at a time: the first one's answer stops the run, with no streak to wait for.
    A plain rate limit is not this stop (FD3.9's 429 runs to its streak)."""
    plan = make_plan(fixture_model.base_url, model=model, seeds=SEEDS[:6])
    _, result = run_here(plan, tmp_path, monkeypatch, concurrency=1)
    assert (result.verdict, result.stop_reason) == ("stopped", "provider_exhausted"), result
    assert result.episodes_run == 1 and result.episodes_owed == total_episodes(plan)
    assert result.first_error is not None and words in result.first_error
    assert status in outside(result.first_error, words, model), "no status in first_error"
