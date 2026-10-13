"""What a run does to the machine, and what it writes down, frozen as tests.

The invariants are FD3.12, FD3.13 and FD3.16 of the front door's plan (spec §8.5 and §8.6), with
ruling 21 (2026-10-02) and ruling 45:
- **FD3.12** with `HOME` a temporary folder, a run touches nothing outside the run folder except
  `HOME/.cache/verifiers`, `HOME/.local/bin`, `HOME/.cache/uv`, one `/tmp/vf-port-<hex>` file per
  episode, and the files the measurement found the installer leaves;
- **FD3.13** the harness's environment carries `PIP_REQUIRE_VIRTUALENV=1` and
  `UV_NO_MODIFY_PATH=1`, each pinned only once the measurements show it does what spec §8.6 says;
- **FD3.16** `run.log` holds `run`'s own progress lines, verifiers' log records and any traceback,
  and never the key.  Amended, ruled 2026-10-12 (`tests/keymask_support.py` states the rule): no
  four characters of the key's secret part in a row are in a text that can carry the key (the
  run's log, its result and every error its traces record), and no twelve in a row, the key's
  wherever they are, in any file of its folder or on either stream.

**Measured** (`evidence/front-door-fd3-a/measurements/bootstrap/`
and `installer/`), on macOS and on
Linux (python:3.11-slim, aarch64), each case in a throwaway `HOME`, with verifiers 0.3.1's own
bootstrap command and uv's installer 0.12.23:
- without `PIP_REQUIRE_VIRTUALENV`, an environment's script run by its path and a pipx-style `PATH`
  take `pip install --user uv` (uv lands in the user's site-packages, `~/.local/lib/...`, and
  `~/.local/bin`); an activated environment takes astral's installer.  With it set, all three
  take astral's installer.  So the setting does what §8.6 says: the bootstrap's branch no longer
  depends on the first `pip` on `PATH`;
- astral's installer leaves `~/.local/bin/uv`, `~/.local/bin/uvx` and `~/.config/uv/uv-receipt.json`
  (the last is the file FD3.12 left open).  Run without `~/.local/bin` on `PATH`, it edits
  `.profile`, `.bashrc`, `.bash_profile`, `.zshrc` and fish's config, and writes
  `~/.local/bin/env` and `env.fish`; with `UV_NO_MODIFY_PATH=1` it edits and writes none of them.
  So the setting does what §8.6 says.  (The bootstrap already puts `~/.local/bin` first on `PATH`,
  and with it there the 0.12.23 installer edits nothing either; the setting holds that whatever
  the installer's version does.)

**The machine check.**  The run is made in a process of its own whose `HOME`, working folder and
`TMPDIR` are the test's, and an audit hook in it records every path that process opens for
writing, creates, renames to or removes.  The bootstrap's `pip` is the test's (it records the
environment it was started with and installs nothing), so nothing is installed and `HOME/.local`
stays as it was; `uv` is the one on `PATH`, with its cache where this process keeps it
(`UV_CACHE_DIR`), so the harness's packages are not fetched again.  Not covered here: `/tmp`,
which other processes on this machine write to as well, so a file there cannot be told to be the
run's; the clean-install check (FD7) watches it, on a machine running nothing else.

**Measured here, and not in FD3.12's list:** uv leaves one empty lock file, `uv-<16 hex>.lock`,
in `TMPDIR` for the harness's script environment, and keeps it (`uv sync --script` run twice on
the prepared script, measurements/uv-lock.txt).  It is a file "uv writes for itself" (spec §8.5),
so the test allows exactly that name, empty, in `TMPDIR`; adding it to the README's list and to
FD7's machine check is a yes/no in `evidence/front-door-fd3-a/rulings.md`.

Shapes decided here
-------------------

**1. An exception that is not the run's own** (here, from the `events` callback) ends `run_plan`
by raising it, with its traceback written to `run.log` first.

**2. `run.log`'s progress lines name the arm** they are about (`depth:d1`); their wording is not
pinned.  Verifiers' records of warning level and above are in it, with any part of the key masked.
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from tests.fd2_fakes import KEY_BODY, SENTINEL, leaked
from tests.fd3_support import (
    KEY,
    KEY_VAR,
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
    snapshot,
    start_child,
    stub_bin,
    wait_until,
)
from tests.fixtures.model_server import FixtureModel
from tests.keymask_support import error_texts, key_runs

__all__ = ["fixture_model", "harness_env"]

pytestmark = needs_uv

RECORDING_PIP = """#!/bin/sh
env > "{record}"
exit 0
"""

HOME_ALLOWED = (".cache/verifiers/", ".local/bin/", ".cache/uv/", ".config/uv/")
UV_LOCK = re.compile(r"uv-[0-9a-f]{16}\.lock")
"""uv's own lock for a script's environment, empty, left in TMPDIR (measured; see above)."""


@contextmanager
def records_of(name: str) -> Iterator[list[logging.LogRecord]]:
    """Every record that reaches the logger `name`, from it or a logger under it, while active:
    a handler on that logger itself, so nothing depends on where its records propagate."""
    records: list[logging.LogRecord] = []

    class Keep(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(logging.makeLogRecord(record.__dict__))

    logger = logging.getLogger(name)
    handler = Keep(level=logging.WARNING)
    logger.addHandler(handler)
    try:
        yield records
    finally:
        logger.removeHandler(handler)


@pytest.fixture(scope="module")
def machine_run(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Any]]:
    """One run of two episodes, in a process with a home, a working folder and a TMPDIR of its
    own; the snapshots before and after, the paths it wrote, and the environment the harness's
    bootstrap was started with."""
    base = tmp_path_factory.mktemp("machine")
    home, cwd, tmp = base / "home", base / "cwd", base / "tmp"
    for folder in (home, cwd, tmp):
        folder.mkdir()
    record = base / "bootstrap-env.txt"
    stubs = stub_bin(base / "bin", pip=RECORDING_PIP.format(record=record))
    writes = base / "writes.txt"
    mark = new_mark()
    model = FixtureModel()
    model.start()
    try:
        before = {name: snapshot(path) for name, path in (("home", home), ("cwd", cwd),
                                                          ("tmp", tmp))}
        env = child_env(home=home, stubs=stubs, mark=mark,
                        extra={"TMPDIR": str(tmp), "PYTHONDONTWRITEBYTECODE": "1"})
        plan = make_plan(model.base_url, seeds=(404, 55))
        job = {"plan": plan_spec(plan), "runs_dir": str(cwd / "runs"),
               "caps": {"spend_usd": 1.0, "tokens": None}, "concurrency": 2,
               "audit_writes": str(writes)}
        process, result_path = start_child(job, env=env, cwd=cwd, work=base / "child")
        with reaped(process, mark):
            process.wait(300)
            wait_until(lambda: not marked_processes(mark), 10.0, 0.2)
        after = {name: snapshot(path) for name, path in (("home", home), ("cwd", cwd),
                                                         ("tmp", tmp))}
        yield {
            "home": home, "cwd": cwd, "tmp": tmp, "work": base / "child", "before": before,
            "after": after,
            "result": child_result(result_path) if result_path.exists() else None,
            "stderr": (base / "child" / "stderr.txt").read_text(encoding="utf-8",
                                                                  errors="replace")[-2000:],
            "writes": writes.read_text(encoding="utf-8").splitlines() if writes.exists()
            else [],
            "bootstrap_env": record.read_text(encoding="utf-8") if record.exists() else None,
            "episodes": model.episodes_started(),
        }
    finally:
        model.close()


def changed(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    return sorted(path for path in after if before.get(path) != after[path])


def test_fd3_12_a_run_touches_nothing_outside_its_folder_but_the_listed_places(
    machine_run: dict[str, Any],
) -> None:
    result = machine_run["result"]
    assert result is not None, machine_run["stderr"]
    assert result["verdict"] == "done", result
    assert machine_run["episodes"] == 2
    folder = Path(result["folder"])
    assert folder.parent == machine_run["cwd"] / "runs"

    before, after = machine_run["before"], machine_run["after"]
    home = changed(before["home"], after["home"])
    assert home, "the run wrote nothing under HOME: the check did not see the run"
    outside = [path for path in home if not path.startswith(HOME_ALLOWED)]
    assert outside == [], outside
    cwd = changed(before["cwd"], after["cwd"])
    prefix = str(folder.relative_to(machine_run["cwd"])) + os.sep
    assert cwd and all(path.startswith(prefix) for path in cwd), cwd
    left = changed(before["tmp"], after["tmp"])
    assert all(UV_LOCK.fullmatch(path) and after["tmp"][path][0] == 0 for path in left), (
        "the run left files in TMPDIR", left)

    allowed = [folder, machine_run["tmp"], machine_run["work"]] + [
        machine_run["home"] / place for place in HOME_ALLOWED]
    resolved = [Path(os.path.realpath(path)) for path in allowed]
    home_root = Path(os.path.realpath(machine_run["home"]))
    parents = {parent for root in resolved if root.is_relative_to(home_root)
               for parent in root.parents if parent.is_relative_to(home_root)}
    strays = sorted({
        path for path in machine_run["writes"]
        if not path.startswith("/dev/")
        and Path(os.path.realpath(path)) not in parents
        and not any(Path(os.path.realpath(path)).is_relative_to(root) for root in resolved)
    })
    assert machine_run["writes"], "the audit hook recorded nothing: the check did not run"
    assert strays == [], strays


def test_fd3_13_the_bootstrap_runs_with_pip_kept_in_a_virtualenv_and_shell_files_left_alone(
    machine_run: dict[str, Any],
) -> None:
    """The environment the harness's bootstrap was started with (its `pip` wrote it down).  The
    key is not in it: verifiers drops every variable whose name holds `API_KEY`, and the config
    refuses any other name (spec §7.3)."""
    assert machine_run["result"] is not None, machine_run["stderr"]
    text = machine_run["bootstrap_env"]
    assert text is not None, "the bootstrap never ran"
    variables = dict(line.split("=", 1) for line in text.splitlines() if "=" in line)
    assert variables.get("PIP_REQUIRE_VIRTUALENV") == "1"
    assert variables.get("UV_NO_MODIFY_PATH") == "1"
    assert KEY not in text and KEY_VAR not in variables


# ---------------------------------------------------------------------------
# FD3.16 run.log
# ---------------------------------------------------------------------------


def test_fd3_16_run_log_holds_the_runs_progress_and_verifiers_records_and_never_the_key(
    tmp_path: Path, harness_env: Path, fixture_model: FixtureModel,
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str],
) -> None:
    """The fixture refuses the key and quotes it back, whole and masked, as a provider's 401
    does; verifiers puts that answer in its warnings and on the trace.  None of it reaches the
    run's log, its result or the errors its traces record, and the key reaches no file of its
    folder and neither stream (amended, ruled 2026-10-12)."""
    monkeypatch.setenv(KEY_VAR, SENTINEL)
    plan = make_plan(fixture_model.base_url, model="fixture-401", seeds=(404, 55))
    with records_of("verifiers") as captured:
        folder, result = run_here(plan, tmp_path, monkeypatch, concurrency=1)
    assert any(seen.headers.get("authorization") == f"Bearer {SENTINEL}"
               for seen in fixture_model.posts()), "the key never reached the endpoint"
    assert result.verdict == "stopped"
    path = Path(folder.path)
    log = (path / "run.log").read_text(encoding="utf-8")
    assert leaked(log) == []
    assert leaked(repr(result)) == [] and leaked(str(result.first_error)) == []
    rows = [json.loads(line) for line in (path / "depth-d1" / "traces.jsonl").read_text(
        encoding="utf-8").splitlines()]
    assert rows and all(error_texts(row) for row in rows), "no trace recorded the refusal"
    assert all(leaked(text) == [] for row in rows for text in error_texts(row))
    for file in sorted(path.rglob("*")):
        if file.is_file():
            assert key_runs(file.read_bytes().decode("utf-8", "replace"), KEY_BODY) == [], file
    out, err = capfd.readouterr()
    assert key_runs(out, KEY_BODY) == [] and key_runs(err, KEY_BODY) == []

    assert "depth:d1" in log, "run.log has no progress line for the arm"
    theirs = [record.getMessage() for record in captured if record.levelno >= logging.WARNING]
    assert theirs, "verifiers logged no warning: the test did not reach its case"
    for message in theirs:
        starts = [message.find(gram) for gram in leaked(message)]
        if "sk-proj" in message:
            starts.append(message.find("sk-proj"))
        cut = min(starts + [len(message)])
        head = message[:cut].splitlines()[0] if message[:cut] else ""
        assert len(head) >= 20 and head in log, ("a verifiers record is not in run.log", head)
    assert KEY_BODY[:4] not in log


def test_fd3_16_run_log_holds_the_traceback_of_a_failure_that_is_not_the_runs(
    tmp_path: Path, harness_env: Path, fixture_model: FixtureModel,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = make_plan(fixture_model.base_url, seeds=(404, 55))

    def broken(event: Any) -> None:
        raise RuntimeError("fd3-a-callback-that-breaks")

    folder = runs().find_run(plan, tmp_path)
    with pytest.raises(RuntimeError):
        run_here(plan, tmp_path, monkeypatch, events=broken)
    log = (Path(folder.path) / "run.log").read_text(encoding="utf-8")
    assert "Traceback" in log and "fd3-a-callback-that-breaks" in log
    assert json.loads((Path(folder.path) / "plan.json").read_text(encoding="utf-8"))
