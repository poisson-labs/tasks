"""Shared ground for FD3's tests: plans that run against the fixture model, the harness's
environment, a run in a process of its own, and what a run leaves behind.  Frozen with them.

**The fixture model** (`tests/fixtures/model_server.py`) answers every model call with the same
usage, so one call costs `call_dollars()` at `PRICE` and `CALL_TOKENS` tokens, and a task of depth
d takes d + 1 calls.  So a test knows what a run spends without asking the code under test.

**The harness's bootstrap.**  Before the first episode of every process, verifiers 0.3.1 runs
`pip install --user uv`, or astral's installer when that pip refuses (spec §1.2 item 1), and
`run` makes it refuse (FD3.13).  So that no test installs anything, `harness_env` puts a `pip`
first on `PATH` that does nothing and succeeds; the bootstrap then finds the `uv` already on
`PATH` (the CI job installs one).  `uv sync --script` still fetches the harness program's
packages, or finds them in uv's cache: that is the harness's own documented fetch (plan §2 item
4).  Nothing the tests themselves do leaves this machine: every run in this process is made
inside `network_guard`, which refuses any connection that is not to loopback.

**A run in a process of its own** (`start_child`, `tests/fd3_child.py`) is how a test sends
Ctrl-C, gives the run a home of its own, or sees a bootstrap that hangs: the bootstrap runs once
per process.  The child carries a marker in its environment, `FD3_MARK`, which every process it
starts inherits, so `marked_processes` finds anything it left running.
"""

from __future__ import annotations

import importlib
import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import time
import types
import uuid
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from tests.fd2_fakes import network_guard
from tests.fixtures.model_server import FixtureModel, usage_per_call

REPO = Path(__file__).resolve().parents[1]
CHILD = Path(__file__).with_name("fd3_child.py")

KEY_VAR = "FIXTURE_API_KEY"
KEY = "sk-NMRTLNMRTLNRMTLRNMTLRNMLTRNMTL"
"""The key the runs send: no four characters of it in a row occur in any other text a run
writes, so a run that hides its key hides nothing else.  The tests that look for a key leak use
`fd2_fakes.SENTINEL`."""

PRICE_FIELDS: dict[str, Any] = {
    "input": 10.0, "cached_input": 5.0, "output": 20.0, "read_on": "2026-10-05",
}
"""Dollars per million tokens: with the fixture's usage, one call costs one cent."""

DECODING = {"temperature": 1.0, "top_p": 1.0, "reasoning_effort": "low", "max_tokens": 2048}

CALL_TOKENS = sum(usage_per_call().values())
MARK = "FD3_MARK"


def runs() -> Any:
    return importlib.import_module("poisson_tasks.runs")


def config() -> Any:
    return importlib.import_module("poisson_tasks.config")


def calibration() -> Any:
    return importlib.import_module("poisson_tasks.calibration")


def arms_module() -> Any:
    return importlib.import_module("poisson_tasks.arms")


def knobs() -> Any:
    return importlib.import_module("poisson_tasks.knobs")


def rates() -> dict[str, float]:
    return {
        "input_rate": float(PRICE_FIELDS["input"]),
        "cached_input_rate": float(PRICE_FIELDS["cached_input"]),
        "output_rate": float(PRICE_FIELDS["output"]),
    }


def call_dollars() -> float:
    """What one of the fixture's calls costs at `PRICE_FIELDS`, by the card's own arithmetic."""
    value = calibration().dollars(usage_per_call(), rates())
    assert isinstance(value, float)
    return value


def make_plan(
    base_url: str,
    *,
    model: str = "fixture-reference",
    arms: Sequence[str] = ("depth:d1",),
    seeds: Sequence[int] = (404,),
    attempts: int = 1,
    priced: bool = True,
    decoding: Mapping[str, Any] | None = None,
    max_model_calls: int = 32,
    preset: str = "custom",
    strictness: str = "strict",
    generator_version: str | None = None,
    key_var: str = KEY_VAR,
) -> Any:
    """A plan against the fixture model, made the way `resolve_plan` makes one: arms through
    `arms.arm_from_id`, the decoding as a read-only mapping."""
    cfg = config()
    version = generator_version or arms_module().DEFAULT_GENERATOR_VERSION
    specs = tuple(
        arms_module().arm_from_id(arm, strictness=strictness, generator_version=version)
        for arm in arms
    )
    price = cfg.PriceConfig(**PRICE_FIELDS) if priced else None
    model_config = cfg.ModelConfig(
        provider="openai-compatible", name=model, base_url=base_url, api_key_env=key_var,
        price=price,
    )
    return cfg.Plan(
        preset=preset, arms=specs, seeds=tuple(seeds), attempts=attempts, model=model_config,
        decoding=types.MappingProxyType(dict(DECODING if decoding is None else decoding)),
        max_model_calls=max_model_calls,
    )


def plan_spec(plan: Any) -> dict[str, Any]:
    """The plan as JSON, for a child process to make again with `plan_from_spec`."""
    return {
        "base_url": plan.model.base_url,
        "model": plan.model.name,
        "arms": [knobs().arm_id(spec) for spec in plan.arms],
        "strictness": plan.arms[0].strictness,
        "generator_version": plan.arms[0].generator_version,
        "seeds": list(plan.seeds),
        "attempts": plan.attempts,
        "priced": plan.model.price is not None,
        "decoding": dict(plan.decoding),
        "max_model_calls": plan.max_model_calls,
        "preset": plan.preset,
        "key_var": plan.model.api_key_env,
    }


def plan_from_spec(spec: Mapping[str, Any]) -> Any:
    return make_plan(
        spec["base_url"], model=spec["model"], arms=spec["arms"], seeds=spec["seeds"],
        attempts=spec["attempts"], priced=spec["priced"], decoding=spec["decoding"],
        max_model_calls=spec["max_model_calls"], preset=spec["preset"],
        strictness=spec["strictness"], generator_version=spec["generator_version"],
        key_var=spec["key_var"],
    )


def arm_dir(spec: Any) -> str:
    """An arm's folder inside the run folder, as `run_arm` names it (spec §8.5's `depth-d1/`)."""
    return str(knobs().arm_id(spec)).replace("/", "-").replace(":", "-").replace("@", "-")


def stub_bin(where: Path, *, pip: str = "#!/bin/sh\nexit 0\n") -> Path:
    """A folder holding one `pip`, for the bootstrap to find first on `PATH`."""
    where.mkdir(parents=True, exist_ok=True)
    script = where / "pip"
    script.write_text(pip, encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return where


def have_uv() -> bool:
    return shutil.which("uv") is not None


needs_uv = pytest.mark.skipif(
    not have_uv(), reason="the `null` harness launches its program through uv"
)


@pytest.fixture
def harness_env(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """This process's environment for a run: the do-nothing `pip` first on `PATH`, the fixture's
    key in `KEY_VAR`, and no proxy between the run and the fixture.  Returns the stub folder,
    which is not under the test's own `tmp_path`."""
    stubs = stub_bin(tmp_path_factory.mktemp("stub-bin"))
    monkeypatch.setenv("PATH", f"{stubs}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv(KEY_VAR, KEY)
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy",
                 "all_proxy"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    return stubs


@pytest.fixture
def fixture_model() -> Iterator[FixtureModel]:
    model = FixtureModel()
    model.start()
    try:
        yield model
    finally:
        model.close()


def run_here(
    plan: Any,
    runs_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    caps: Mapping[str, Any] | None = None,
    concurrency: int = 4,
    again: bool = False,
    name: str | None = None,
    **kwargs: Any,
) -> tuple[Any, Any]:
    """`find_run` then `run_plan` in this process, inside the network guard.  Returns the folder
    and the result."""
    folder = runs().find_run(plan, runs_dir, again=again, name=name)
    with network_guard(monkeypatch):
        result = runs().run_plan(
            plan, folder, caps=dict(caps or {"spend_usd": 100.0, "tokens": None}),
            concurrency=concurrency, **kwargs,
        )
    return folder, result


# ---------------------------------------------------------------------------
# what a run folder holds
# ---------------------------------------------------------------------------


def ledger_lines(folder: Path) -> list[dict[str, Any]]:
    path = folder / "spend.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def trace_lines(arm_folder: Path) -> list[bytes]:
    """The whole lines of an arm's `traces.jsonl`, each with its newline."""
    path = arm_folder / "traces.jsonl"
    if not path.exists():
        return []
    return [line for line in path.read_bytes().splitlines(keepends=True) if line.endswith(b"\n")]


def ok_lines(arm_folder: Path) -> list[bytes]:
    out = []
    for line in trace_lines(arm_folder):
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get("ok"):
            out.append(line)
    return out


def records(plan: Any, folder: Path) -> list[Any]:
    """Every arm's records, as the card reads them (`calibration.records_from_run`)."""
    out: list[Any] = []
    for spec in plan.arms:
        arm_folder = folder / arm_dir(spec)
        if (arm_folder / "traces.jsonl").exists():
            out.extend(calibration().records_from_run(arm_folder, model=plan.model.name))
    return out


def planned_tasks(plan: Any) -> list[tuple[str, int]]:
    """Every (task id, attempt) an uninterrupted run of `plan` scores, from the generator."""
    tasks = importlib.import_module("poisson_tasks.tasks")
    return sorted(
        (str(tasks.generate(spec, seed).task_id), attempt)
        for spec in plan.arms for seed in plan.seeds for attempt in range(plan.attempts)
    )


def scored_tasks(plan: Any, folder: Path) -> list[tuple[str, int]]:
    return sorted((str(row.task_id), int(row.attempt)) for row in records(plan, folder))


def total_episodes(plan: Any) -> int:
    return len(plan.arms) * len(plan.seeds) * int(plan.attempts)


def snapshot(root: Path) -> dict[str, tuple[int, int]]:
    """Every file and link under `root`, with its size and modification time."""
    out: dict[str, tuple[int, int]] = {}
    if not root.exists():
        return out
    for dirpath, dirnames, filenames in os.walk(root):
        for name in filenames + [d for d in dirnames if os.path.islink(os.path.join(dirpath, d))]:
            path = os.path.join(dirpath, name)
            try:
                info = os.lstat(path)
            except FileNotFoundError:
                continue
            out[os.path.relpath(path, root)] = (info.st_size, info.st_mtime_ns)
    return out


def tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*")) if path.is_file()
    }


# ---------------------------------------------------------------------------
# a run in a process of its own
# ---------------------------------------------------------------------------


def child_env(
    *, home: Path, stubs: Path, mark: str, extra: Mapping[str, str] | None = None
) -> dict[str, str]:
    """The child's environment: its own home, the stub folder first on `PATH`, the fixture's
    key, the marker, and uv's cache where this process's uv keeps it (so a child with a home of
    its own does not fetch the harness's packages again)."""
    env = {
        name: value for name, value in os.environ.items()
        if not name.upper().endswith("_PROXY") and name != "PYTHONPATH"
    }
    uv = shutil.which("uv")
    if uv is not None and "UV_CACHE_DIR" not in env:
        found = subprocess.run([uv, "cache", "dir"], capture_output=True, text=True, check=False)
        if found.returncode == 0 and found.stdout.strip():
            env["UV_CACHE_DIR"] = found.stdout.strip()
    env.update({
        "HOME": str(home),
        "PATH": f"{stubs}{os.pathsep}{os.environ.get('PATH', '')}",
        KEY_VAR: KEY,
        "NO_PROXY": "127.0.0.1,localhost",
        MARK: mark,
        "PYTHONUNBUFFERED": "1",
    })
    env.update(extra or {})
    return env


def new_mark() -> str:
    return "fd3-" + uuid.uuid4().hex


def start_child(
    job: Mapping[str, Any], *, env: Mapping[str, str], cwd: Path, work: Path
) -> tuple[subprocess.Popen[bytes], Path]:
    """Start `tests/fd3_child.py` on `job`.  Returns the process and the file its result will be
    written to.  Its output goes to files in `work`, never to pipes.  It leads a process group of
    its own, as a command started from a terminal does, so `interrupt` reaches what a Ctrl-C
    there reaches."""
    work.mkdir(parents=True, exist_ok=True)
    result = work / "result.json"
    job_path = work / "job.json"
    job_path.write_text(json.dumps({**job, "result_path": str(result)}), encoding="utf-8")
    out = (work / "stdout.txt").open("wb")
    err = (work / "stderr.txt").open("wb")
    process = subprocess.Popen(
        [sys.executable, str(CHILD), str(job_path)], cwd=cwd, env=dict(env),
        stdout=out, stderr=err, start_new_session=True,
    )
    out.close()
    err.close()
    return process, result


def interrupt(process: subprocess.Popen[bytes]) -> None:
    """Ctrl-C, as a terminal sends it: SIGINT to the child's whole process group."""
    os.killpg(process.pid, signal.SIGINT)


def ledger_count(folder: Path) -> int:
    """The whole lines in a run folder's ledger, read while the run may be writing it."""
    path = folder / "spend.jsonl"
    return path.read_bytes().count(b"\n") if path.exists() else 0


def child_result(path: Path) -> dict[str, Any]:
    """The child's result; a child that wrote none fails the test with the end of its stderr."""
    if not path.exists():
        err = path.with_name("stderr.txt")
        tail = err.read_text(encoding="utf-8", errors="replace")[-2000:] if err.exists() else ""
        raise AssertionError(f"the child wrote no result:\n{tail}")
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def wait_until(condition: Callable[[], bool], timeout: float, interval: float = 0.05) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(interval)
    return condition()


def marked_processes(mark: str) -> list[int]:
    """Every process still running whose environment carries `FD3_MARK=mark`."""
    needle = f"{MARK}={mark}".encode()
    found: list[int] = []
    if sys.platform.startswith("linux"):
        for entry in Path("/proc").iterdir():
            if not entry.name.isdigit() or int(entry.name) == os.getpid():
                continue
            try:
                environ = (entry / "environ").read_bytes()
                state = (entry / "stat").read_text()
            except OSError:
                continue
            if needle in environ.split(b"\0") and ") Z " not in state:
                found.append(int(entry.name))
        return found
    listing = subprocess.run(
        ["ps", "-E", "-ww", "-ax", "-o", "pid=,stat=,command="], capture_output=True, check=False
    ).stdout
    for line in listing.splitlines():
        fields = line.split(None, 2)
        if len(fields) < 3 or not fields[0].isdigit():
            continue
        pid = int(fields[0])
        if pid == os.getpid() or fields[1].startswith(b"Z"):
            continue
        if needle in fields[2].split():
            found.append(pid)
    return found


def kill_marked(mark: str) -> None:
    """A test's own clean-up: stop whatever a failed test left running."""
    for pid in marked_processes(mark):
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass


@contextmanager
def reaped(process: subprocess.Popen[bytes], mark: str) -> Iterator[None]:
    try:
        yield
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(10)
        kill_marked(mark)
