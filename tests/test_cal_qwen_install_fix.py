"""Model B's notebook, run again in the same runtime: the install fix.

On Colab the notebook's `install-vllm` cell stopped at its first command, `uv venv --python
3.12 /content/vllm-venv`, with exit status 2.  The notebook had been started once before in
that runtime, so `/content/vllm-venv` already existed.  uv 0.11.14, the version the notebook
installs, refuses to create a virtualenv where one exists, or where any non-empty directory
is, unless it is given `--clear`, and exits 2.  The driver skipped the install only when the
old virtualenv already passed its check, so every earlier attempt that stopped short, and
every finished install whose check failed, made the next attempt fail at its first command.
The cell showed a traceback and an exit status; uv's own reason was above it.

These tests pin the fix, with no GPU and nothing off the machine:

* `install-vllm` on a fresh path, again after it finished, after an attempt that created the
  virtualenv and stopped, after an install cut off part way, and after a finished install
  whose check fails.  An unfinished virtualenv is rebuilt from nothing, a finished one is
  never installed again, and a path that is not a virtualenv this step made is left alone.
  The real uv runs every command, through a shim that records each one, against a stand-in
  wheel served from a file URL and checked against its sha256
* a failing command's own output (uv's, the check's, the template fetch's) is in the STOP
  message, not only its exit status
* the notebook's setup cells, run the way Colab runs them: the helper's `run` shows a failing
  command's output with the token scrubbed; a clone cut off part way is never taken for a
  finished one; the tasks environment is rebuilt when it did not finish and never when it
  did; and a failed setup does not pin the run to the commit that failed
* `serve` run again while the server that an interrupted `serve` started is still loading
"""

from __future__ import annotations

import base64
import dataclasses
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import types
import zipfile
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SRC = REPO / "src"
NOTEBOOK = REPO / "notebooks" / "calibration_model_b.ipynb"
FAKE = HERE / "fake_vllm.py"
FIXTURE = HERE / "fixtures" / "qwen3-8b-chat-template.json"

REAL_UV = shutil.which("uv")
REAL_GIT = shutil.which("git")
needs_uv = pytest.mark.skipif(REAL_UV is None, reason="the install runs the real uv")
needs_git = pytest.mark.skipif(REAL_GIT is None, reason="the clone cell runs git")


def run_module() -> Any:
    import importlib

    return importlib.import_module("poisson_tasks.calibration_run")


def _driver(*args: str) -> list[str]:
    return [sys.executable, "-m", "poisson_tasks.calibration_run", *args]


def _driver_env(**extra: str) -> dict[str, str]:
    return {**os.environ, "PYTHONPATH": str(SRC), **extra}


def _after_stop(output: str) -> str:
    """What the driver printed from its STOP line on; empty if it printed none."""
    at = output.find("STOP:")
    return output[at:] if at >= 0 else ""


# ---------------------------------------------------------------------------
# install-vllm: a stand-in wheel, the real uv behind a recording shim
# ---------------------------------------------------------------------------

DIST = "vllm-0.29.0+cu129.dist-info"
WHEEL_NAME = "vllm-0.29.0+cu129-py3-none-any.whl"
WHEEL_FILES = {
    # The release wheel's own vllm/_version.py says '0.29.0' (read from the wheel, 2026-09-26).
    "vllm/__init__.py": (
        "import os\n"
        "if os.environ.get('FAKE_VLLM_IMPORT_ERROR'):\n"
        "    raise ImportError(os.environ['FAKE_VLLM_IMPORT_ERROR'])\n"
        "__version__ = '0.29.0'\n"
    ),
    "torch/__init__.py": (
        "import os\n"
        "__version__ = '2.13.0+cu129'\n"
        "class version:\n"
        "    cuda = '12.9'\n"
        "class cuda:\n"
        "    @staticmethod\n"
        "    def is_available():\n"
        "        return os.environ.get('FAKE_CUDA', '1') == '1'\n"
    ),
    f"{DIST}/METADATA": "Metadata-Version: 2.1\nName: vllm\nVersion: 0.29.0+cu129\n",
    f"{DIST}/WHEEL": (
        "Wheel-Version: 1.0\nGenerator: tests\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
    ),
}

UV_SHIM = """#!/bin/sh
printf '%s\\n' "$*" >> "$UV_CALLS"
if [ -n "$FAKE_UV_FAIL" ] && [ "$1" = "$FAKE_UV_FAIL" ]; then
  echo "error: planted uv failure, in uv's own words" >&2
  exit 2
fi
if [ -n "$FAKE_UV_SLOW" ] && [ "$1" = "$FAKE_UV_SLOW" ]; then
  echo $$ > "$UV_SLOW_PID"
  exec sleep 60
fi
exec "{real}" "$@"
"""


def _build_wheel(path: Path, extra: dict[str, str] | None = None) -> None:
    record = []
    with zipfile.ZipFile(path, "w") as archive:
        for name, text in {**WHEEL_FILES, **(extra or {})}.items():
            data = text.encode("utf-8")
            digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=")
            record.append(f"{name},sha256={digest.decode()},{len(data)}")
            archive.writestr(name, data)
        record.append(f"{DIST}/RECORD,,")
        archive.writestr(f"{DIST}/RECORD", "\n".join(record) + "\n")


class Install:
    """A runtime's `/content` on a laptop: the vLLM virtualenv's path, the real uv behind a
    shim that records every command it is given, and a stand-in for the 548 MB wheel at a
    file URL, pinned by its own sha256 and size.  The stand-in is a pure-Python wheel with a
    `vllm` and a `torch` module that answer the install's check the way the real stack
    does; `FAKE_CUDA=0` makes CUDA unavailable and `FAKE_VLLM_IMPORT_ERROR` makes the import
    fail.  uv runs offline, with its own cache, so nothing leaves the machine."""

    def __init__(self, tmp: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        assert REAL_UV is not None
        self.tmp = tmp
        self.content = tmp / "content"
        self.content.mkdir()
        self.venv = self.content / "vllm-venv"
        release = tmp / "release"
        release.mkdir()
        self.source = release / WHEEL_NAME
        _build_wheel(self.source)
        data = self.source.read_bytes()
        self.pin = dataclasses.replace(
            run_module().QWEN3_8B,
            vllm_wheel_name=WHEEL_NAME,
            vllm_wheel_url=self.source.as_uri(),
            vllm_wheel_sha256=hashlib.sha256(data).hexdigest(),
            vllm_wheel_size=len(data),
            python=sys.executable,
        )
        self.bin = tmp / "bin"
        self.bin.mkdir()
        shim = self.bin / "uv"
        shim.write_text(UV_SHIM.replace("{real}", REAL_UV))
        shim.chmod(0o755)
        self.log = tmp / "uv-calls.log"
        self.env = {
            "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            "UV_CALLS": str(self.log),
            "UV_CACHE_DIR": str(tmp / "uv-cache"),
            "UV_OFFLINE": "1",
            "UV_NO_CONFIG": "1",
            "UV_PYTHON_DOWNLOADS": "never",
        }
        for name, value in self.env.items():
            monkeypatch.setenv(name, value)
        for name in ("FAKE_CUDA", "FAKE_VLLM_IMPORT_ERROR", "FAKE_UV_FAIL", "FAKE_UV_SLOW",
                     "VIRTUAL_ENV"):
            monkeypatch.delenv(name, raising=False)

    def install(self) -> int:
        return int(run_module().cmd_install_vllm(self.venv, dry_run=False, pin=self.pin))

    def stopped(self) -> BaseException:
        """The install run once more, expected to stop: the error it stopped with."""
        try:
            self.install()
        except Exception as error:
            return error
        raise AssertionError("the install did not stop")

    def uv_calls(self) -> list[str]:
        return self.log.read_text().splitlines() if self.log.exists() else []

    def installs(self) -> list[str]:
        """The recorded commands that make or fill a virtualenv."""
        return [c for c in self.uv_calls() if c.startswith(("venv", "pip install"))]

    def forget_calls(self) -> None:
        self.log.unlink(missing_ok=True)

    def uv_directly(self, *args: str) -> None:
        """uv run by the test itself, not recorded: an earlier attempt's leftovers."""
        assert REAL_UV is not None
        subprocess.run([REAL_UV, *args], check=True, capture_output=True, text=True)

    def site_packages(self) -> Path:
        found = sorted(self.venv.glob("lib/python*/site-packages"))
        assert len(found) == 1, found
        return found[0]


@pytest.fixture
def inst(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Install:
    return Install(tmp_path, monkeypatch)


CHECK_LINE = "0.29.0 2.13.0+cu129 12.9 True"


@needs_uv
def test_control_a_fresh_install_then_a_rerun_that_installs_nothing(
    inst: Install, capsys: pytest.CaptureFixture[str]
) -> None:
    """The rig works and the driver's first run works: a fresh path gets the virtualenv, the
    wheel checked against its sha256, the install and the check.  Run again, the finished
    install is kept and nothing is installed a second time."""
    assert inst.install() == 0
    assert CHECK_LINE in capsys.readouterr().out
    assert [c.split()[0] for c in inst.installs()] == ["venv", "pip"]
    assert (inst.content / WHEEL_NAME).read_bytes() == inst.source.read_bytes()
    inst.forget_calls()
    assert inst.install() == 0
    assert CHECK_LINE in capsys.readouterr().out
    assert inst.installs() == [], "a finished install was installed again"


@needs_uv
def test_a_rerun_after_an_attempt_that_created_the_venv_and_stopped(
    inst: Install, capsys: pytest.CaptureFixture[str]
) -> None:
    """The Colab failure, reproduced: the first attempt made `/content/vllm-venv` and got no
    further, and uv 0.11.14 exits 2 on `uv venv` over it.  The rerun must finish the job."""
    inst.uv_directly("venv", "--quiet", "--python", sys.executable, str(inst.venv))
    assert inst.install() == 0
    assert CHECK_LINE in capsys.readouterr().out
    assert [c.split()[0] for c in inst.installs()] == ["venv", "pip"]


@needs_uv
def test_a_rerun_after_an_install_cut_off_part_way_rebuilds_it_from_nothing(
    inst: Install, capsys: pytest.CaptureFixture[str]
) -> None:
    """An install cut off while uv was filling the virtualenv leaves some packages and not
    others.  Nothing in it is trusted: the rerun rebuilds it whole."""
    inst.uv_directly("venv", "--quiet", "--python", sys.executable, str(inst.venv))
    inst.uv_directly("pip", "install", "--quiet", "--python", str(inst.venv / "bin" / "python"),
                     str(inst.source))
    shutil.rmtree(inst.site_packages() / "torch")
    assert inst.install() == 0
    assert CHECK_LINE in capsys.readouterr().out
    assert (inst.site_packages() / "torch" / "__init__.py").exists()
    assert [c.split()[0] for c in inst.installs()] == ["venv", "pip"]


@needs_uv
def test_an_install_whose_uv_pip_install_failed_is_built_again(
    inst: Install, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The install is only finished once uv has filled the virtualenv: an attempt whose
    `uv pip install` failed is not taken for a finished one on the rerun."""
    monkeypatch.setenv("FAKE_UV_FAIL", "pip")
    inst.stopped()
    monkeypatch.delenv("FAKE_UV_FAIL")
    inst.forget_calls()
    assert inst.install() == 0
    assert CHECK_LINE in capsys.readouterr().out
    assert [c.split()[0] for c in inst.installs()] == ["venv", "pip"]


@needs_uv
def test_a_venv_installed_for_another_pin_is_built_again(
    inst: Install, capsys: pytest.CaptureFixture[str]
) -> None:
    """A finished install counts only for the pin it installed: with another wheel pinned,
    the virtualenv is built again from nothing, from the new wheel."""
    assert inst.install() == 0
    other = inst.tmp / "release-2" / WHEEL_NAME
    other.parent.mkdir()
    _build_wheel(other, extra={"vllm/_rebuilt.py": "PIN = 2\n"})
    data = other.read_bytes()
    inst.pin = dataclasses.replace(inst.pin, vllm_wheel_url=other.as_uri(),
                                   vllm_wheel_sha256=hashlib.sha256(data).hexdigest(),
                                   vllm_wheel_size=len(data))
    inst.forget_calls()
    assert inst.install() == 0
    assert CHECK_LINE in capsys.readouterr().out
    assert [c.split()[0] for c in inst.installs()] == ["venv", "pip"]
    assert (inst.site_packages() / "vllm" / "_rebuilt.py").exists()


@needs_uv
def test_a_finished_install_whose_check_fails_is_not_installed_again(
    inst: Install, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A finished install whose check fails (here CUDA is unavailable) is not a reason to
    install again: the same wheel would fail the same way.  The rerun stops, and says what
    the check said."""
    assert inst.install() == 0
    inst.forget_calls()
    monkeypatch.setenv("FAKE_CUDA", "0")
    error = inst.stopped()
    assert inst.installs() == [], "a finished install was installed again"
    assert "0.29.0 2.13.0+cu129 12.9 False" in str(error), repr(error)
    run = run_module()
    assert isinstance(error, (run.ServingMismatch, run.StepFailed)), repr(error)


@needs_uv
def test_the_checks_own_error_output_is_in_the_stop_message(
    inst: Install, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the check itself fails (vLLM does not import), the STOP says why, in the
    check's own words, not only its exit status."""
    planted = "libcuda.so.1: cannot open shared object file (planted)"
    monkeypatch.setenv("FAKE_VLLM_IMPORT_ERROR", planted)
    error = inst.stopped()
    assert planted in str(error), repr(error)
    assert isinstance(error, run_module().StepFailed), repr(error)


@needs_uv
def test_a_failing_uv_commands_own_output_is_in_the_stop_message(
    inst: Install, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_UV_FAIL", "venv")
    error = inst.stopped()
    assert "planted uv failure, in uv's own words" in str(error), repr(error)
    assert isinstance(error, run_module().StepFailed), repr(error)


@needs_uv
def test_a_path_holding_someone_elses_files_is_refused_and_left_alone(inst: Install) -> None:
    """Replacing an unfinished virtualenv deletes a directory, so only a virtualenv, or what
    uv leaves while it makes one, is ever replaced.  Anything else stops the step before any
    command runs, and nothing in it is touched."""
    inst.venv.mkdir()
    notes = inst.venv / "notes.txt"
    notes.write_text("not a virtualenv\n")
    error = inst.stopped()
    assert notes.read_text() == "not a virtualenv\n"
    assert inst.installs() == [], "a command ran against someone else's directory"
    assert str(inst.venv) in str(error)
    assert isinstance(error, run_module().StepFailed), repr(error)


@needs_uv
def test_control_a_wheel_with_another_sha256_is_refused(inst: Install) -> None:
    """The pin holds: a download whose sha256 is not the pinned one is refused, nothing is
    installed from it, and it is not kept."""
    inst.pin = dataclasses.replace(inst.pin, vllm_wheel_sha256="0" * 64)
    error = inst.stopped()
    assert isinstance(error, run_module().ServingMismatch), repr(error)
    assert not any(c.startswith("pip install") for c in inst.uv_calls())
    assert not (inst.content / WHEEL_NAME).exists()


@needs_uv
def test_the_command_line_prints_a_stop_with_uvs_own_words_and_no_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What the notebook shows: `install-vllm` as the helper cell runs it, with uv failing
    at its first command.  The driver ends with a STOP line followed by uv's own output,
    and no Python traceback in between."""
    inst = Install(tmp_path, monkeypatch)
    done = subprocess.run(
        _driver("install-vllm", "--venv", str(inst.venv)),
        env=_driver_env(FAKE_UV_FAIL="venv"), stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, timeout=120,
    )
    assert done.returncode == 1, done.stdout
    assert "Traceback" not in done.stdout, done.stdout
    assert "planted uv failure, in uv's own words" in _after_stop(done.stdout), done.stdout


@needs_uv
def test_the_stop_button_during_the_install_stops_uv_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The helper passes the Stop button to the driver as SIGINT, and to the driver alone.
    The driver must stop the uv command it is running, or uv goes on writing into the
    virtualenv unseen while the next attempt removes and rebuilds it."""
    inst = Install(tmp_path, monkeypatch)
    pid_file = tmp_path / "uv-slow.pid"
    proc = subprocess.Popen(
        _driver("install-vllm", "--venv", str(inst.venv)),
        env=_driver_env(FAKE_UV_SLOW="venv", UV_SLOW_PID=str(pid_file)),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    child = 0
    try:
        _wait_for(lambda: pid_file.exists() and pid_file.read_text().strip() != "", 60)
        child = int(pid_file.read_text())
        proc.send_signal(signal.SIGINT)
        out, _ = proc.communicate(timeout=60)
        assert proc.returncode == 130, out
        _wait_for(lambda: not _alive(child), 10)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=30)
        if child and _alive(child):
            os.kill(child, signal.SIGKILL)


# ---------------------------------------------------------------------------
# serve: run again while the earlier server loads; the template fetch's own words
# ---------------------------------------------------------------------------


def _free_port() -> int:
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
        return port


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _wait_for(predicate: Callable[[], bool], timeout_s: float) -> None:
    deadline = time.monotonic() + timeout_s
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("timed out")
        time.sleep(0.05)


@pytest.fixture
def served(tmp_path: Path) -> Iterator[dict[str, Any]]:
    """A `vllm` that takes five seconds to load before it listens, the pinned template's
    tokenizer config, and the runtime's folders.  Teardown stops every process started
    here, by the PIDs recorded."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    vllm = bin_dir / "vllm"
    vllm.write_text(f'#!/bin/sh\nsleep 5\nexec "{sys.executable}" "{FAKE}" "$@"\n')
    vllm.chmod(0o755)
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    tokenizer = tmp_path / "tokenizer_config.json"
    tokenizer.write_text(json.dumps({"chat_template": data["chat_template"]}), encoding="utf-8")
    common = ["--local", str(tmp_path / "local"), "--durable", str(tmp_path / "durable"),
              "--port", str(_free_port())]
    state: dict[str, Any] = {
        "bin": bin_dir, "vllm": vllm, "tokenizer": tokenizer, "common": common,
        "local": tmp_path / "local", "env": _driver_env(FAKE_SEEDS="404"),
        "drivers": [], "server_pids": [],
    }
    yield state
    for proc in state["drivers"]:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=30)
    subprocess.run(_driver("stop-server", *common), env=state["env"], capture_output=True,
                   timeout=120)
    for pid in state["server_pids"]:
        if _alive(pid):
            os.kill(pid, signal.SIGTERM)


def test_serve_again_while_the_interrupted_serves_server_is_still_loading(
    served: dict[str, Any],
) -> None:
    """The Stop button (or a closed tab) during `serve` interrupts the driver while vLLM,
    started in a session of its own, keeps loading the weights.  Run again, `serve` finds
    the server it started alive and must wait for it to become healthy, not ask it for its
    version at once and fail."""
    argv = _driver("serve", *served["common"], "--vllm", str(served["vllm"]),
                   "--tokenizer-config", str(served["tokenizer"]), "--timeout", "60")
    first = subprocess.Popen(argv, env=served["env"], stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True)
    served["drivers"].append(first)
    pid_file = served["local"] / "vllm.pid"
    _wait_for(pid_file.exists, 60)
    _wait_for(lambda: pid_file.read_text().strip() != "", 10)
    server = int(pid_file.read_text())
    served["server_pids"].append(server)
    first.send_signal(signal.SIGINT)
    first.communicate(timeout=60)
    assert _alive(server), "the server should outlive the interrupted serve step"
    again = subprocess.run(argv, env=served["env"], capture_output=True, text=True, timeout=180)
    assert again.returncode == 0, again.stdout + again.stderr
    assert int(pid_file.read_text()) == server, "a second server was started"


def test_a_failed_template_fetch_stops_with_its_own_words(served: dict[str, Any]) -> None:
    """`serve` fetches the pinned revision's template through the vLLM environment's own
    Python.  If that fails (no network, the Hub refusing), the STOP carries its error."""
    python = served["bin"] / "python"
    python.write_text('#!/bin/sh\necho "OSError: planted Hub failure" >&2\nexit 1\n')
    python.chmod(0o755)
    done = subprocess.run(
        _driver("serve", *served["common"], "--vllm", str(served["vllm"]), "--timeout", "60"),
        env=served["env"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        timeout=120,
    )
    assert done.returncode == 1, done.stdout
    assert "Traceback" not in done.stdout, done.stdout
    assert "OSError: planted Hub failure" in _after_stop(done.stdout), done.stdout
    assert not (served["local"] / "vllm.pid").exists(), "a server was started anyway"


# ---------------------------------------------------------------------------
# the notebook's setup cells, run the way Colab runs them
# ---------------------------------------------------------------------------

HELPER_MARK = "# the driver helper"
CODE_MARK = "# The code: poisson-tasks at REPO_REF"
ENV_MARK = "# The tasks environment:"


def _cell(mark: str) -> str:
    nb = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    found = ["".join(c["source"]) for c in nb["cells"]
             if c["cell_type"] == "code" and "".join(c["source"]).startswith(mark)]
    assert len(found) == 1, f"one code cell opens with {mark!r}"
    return found[0]


def _helper() -> dict[str, Any]:
    ns: dict[str, Any] = {"DRIVER": [sys.executable, "-c", "pass"], "COMMON": []}
    exec(_cell(HELPER_MARK), ns)
    return ns


def test_the_helpers_run_stops_with_the_commands_own_output_and_no_token(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The setup cells run their commands through the helper's `run`: a failure halts the
    notebook with the command's own output, and a secret on the command line (the GitHub
    token in the clone's URL) appears nowhere."""
    ns = _helper()
    assert "run" in ns, "the helper cell defines no run() for the setup cells"
    # The error is put together at run time, so it is on the command line in no form and
    # only the command's own output can carry it into the STOP.
    failing = [sys.executable, "-c",
               "import sys; print('said on stdout'); "
               "sys.stderr.write('fatal: ' + 'planted failure near ' + sys.argv[1] + '\\n'); "
               "sys.exit(3)", "tok-123"]
    with pytest.raises(SystemExit) as stop:
        ns["run"](failing, secret="tok-123")
    message = str(stop.value)
    printed = capsys.readouterr().out
    assert message.startswith("STOP:"), message
    assert "fatal: planted failure near ***" in message, message
    assert "exited with 3" in message, message
    assert "tok-123" not in message + printed
    out = ns["run"]([sys.executable, "-c", "print('ok-line')"])
    assert "ok-line" in out and "ok-line" in capsys.readouterr().out


class Recorder:
    """Stands in for the helper's `run` in the tasks-environment cell: records each command
    and runs none, except that `uv venv` makes its directory, as the real one does; `fail_on`
    makes one command stop the notebook."""

    def __init__(self, fail_on: str | None = None) -> None:
        self.calls: list[list[str]] = []
        self.fail_on = fail_on

    def __call__(self, argv: list[str], secret: str | None = None) -> str:
        self.calls.append([str(a) for a in argv])
        if self.fail_on and any(self.fail_on in str(a) for a in argv):
            raise SystemExit(f"STOP: planted failure of {argv[0]}")
        if "venv" in argv:
            Path(argv[-1]).mkdir(parents=True, exist_ok=True)
        return "usage: stand-in\n"

    def built(self) -> bool:
        return any("requirements-colab.txt" in " ".join(c) for c in self.calls)


def _run_env_cell(tmp: Path, recorder: Recorder, monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("the cell ran a command outside the helper's run()")

    venv = tmp / "tasks-venv"
    ns: dict[str, Any] = {
        "TASKS": str(tmp / "tasks"), "TASKS_VENV": str(venv),
        "DRIVER": [str(venv / "bin" / "python"), "-m", "poisson_tasks.calibration_run"],
        "run": recorder,
    }
    with monkeypatch.context() as patch:
        patch.setattr(subprocess, "run", refuse)
        patch.setattr(subprocess, "Popen", refuse)
        exec(_cell(ENV_MARK), ns)


def test_the_tasks_environment_is_rebuilt_when_it_did_not_finish_and_kept_when_it_did(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An environment whose Python exists but whose install did not finish is the same trap
    as the vLLM one: it used to be skipped as done.  It is rebuilt from nothing (uv 0.11.14
    exits 2 on `uv venv` over an existing directory without `--clear`), and once it has
    finished it is never built again.  The driver's import is checked through `run`, so a
    broken environment stops the notebook here, with its error."""
    (tmp_path / "tasks-venv" / "bin").mkdir(parents=True)
    (tmp_path / "tasks-venv" / "bin" / "python").write_text("")
    first = Recorder()
    _run_env_cell(tmp_path, first, monkeypatch)
    assert first.built(), first.calls
    creates = [c for c in first.calls if "venv" in c and str(tmp_path / "tasks-venv") in c]
    assert creates and all("--clear" in c for c in creates), first.calls
    driver = [str(tmp_path / "tasks-venv" / "bin" / "python"), "-m",
              "poisson_tasks.calibration_run", "--help"]
    assert first.calls[-1] == driver, first.calls
    again = Recorder()
    _run_env_cell(tmp_path, again, monkeypatch)
    assert not again.built(), again.calls
    assert again.calls == [driver], again.calls


def test_a_tasks_environment_build_that_stopped_is_built_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    failing = Recorder(fail_on="requirements-colab.txt")
    with pytest.raises(SystemExit):
        _run_env_cell(tmp_path, failing, monkeypatch)
    again = Recorder()
    _run_env_cell(tmp_path, again, monkeypatch)
    assert again.built(), again.calls


GIT = ["git", "-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid",
       "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null"]

GIT_SHIM = """#!/bin/sh
if [ "$1" = "clone" ]; then
  for arg in "$@"; do dest=$arg; done
  if [ -n "$FAKE_CLONE_CUT" ]; then
    mkdir -p "$dest/.git"
    echo "fatal: early EOF (planted: the clone was cut off)" >&2
    exit 128
  fi
  exec "{real}" clone --quiet "{origin}" "$dest"
fi
exec "{real}" "$@"
"""


@pytest.fixture
def code_cell(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """The clone cell's world: a stand-in origin with one commit on `main`, a fake
    `google.colab.userdata` holding a token, a Drive folder, and git kept inside tmp."""
    origin = tmp_path / "origin"
    subprocess.run([*GIT, "init", "--quiet", "-b", "main", str(origin)], check=True)
    (origin / "README").write_text("stand-in\n")
    subprocess.run([*GIT, "-C", str(origin), "add", "README"], check=True)
    subprocess.run([*GIT, "-C", str(origin), "commit", "--quiet", "-m", "stand-in"], check=True)
    head = subprocess.run(["git", "-C", str(origin), "rev-parse", "HEAD"], check=True,
                          capture_output=True, text=True).stdout.strip()
    colab = types.ModuleType("google.colab")
    colab.userdata = types.SimpleNamespace(get=lambda name: "tok-123")  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "google.colab", colab)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    drive = tmp_path / "drive"
    drive.mkdir()
    return {"origin": origin, "head": head, "drive": drive, "tasks": tmp_path / "tasks",
            "tmp": tmp_path}


def _run_code_cell(world: dict[str, Any]) -> None:
    ns = _helper()
    ns.update({"REPO": "poisson-labs/tasks", "REPO_REF": "main", "TASKS": str(world["tasks"]),
               "DRIVE_DIR": str(world["drive"])})
    exec(_cell(CODE_MARK), ns)


@needs_git
def test_a_failed_setup_does_not_pin_the_run_to_the_commit_that_failed(
    code_cell: dict[str, Any],
) -> None:
    """The clone cell records the commit a run started on and refuses to resume on another.
    The first Colab attempt recorded one, then failed at install-vllm, before the run had
    started.  Pinning that commit would send the rerun back to the code that failed.  Until
    preflight writes the run manifest (`run.json`), the record follows the checkout."""
    subprocess.run(["git", "clone", "--quiet", str(code_cell["origin"]), str(code_cell["tasks"])],
                   check=True)
    source = code_cell["drive"] / "source.json"
    source.write_text(json.dumps({"repo": "poisson-labs/tasks", "ref": "main", "commit": "f" * 40}))
    _run_code_cell(code_cell)
    assert json.loads(source.read_text())["commit"] == code_cell["head"]


@needs_git
def test_control_a_started_run_stays_on_the_commit_it_started_on(
    code_cell: dict[str, Any],
) -> None:
    subprocess.run(["git", "clone", "--quiet", str(code_cell["origin"]), str(code_cell["tasks"])],
                   check=True)
    source = code_cell["drive"] / "source.json"
    first = json.dumps({"repo": "poisson-labs/tasks", "ref": "main", "commit": "f" * 40})
    source.write_text(first)
    (code_cell["drive"] / "run.json").write_text("{}")
    with pytest.raises(SystemExit) as stop:
        _run_code_cell(code_cell)
    assert "f" * 40 in str(stop.value)
    assert source.read_text() == first


@needs_git
def test_a_clone_cut_off_part_way_is_not_taken_for_a_finished_one(
    code_cell: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A clone cut off part way leaves a directory behind.  The next attempt must clone again,
    not check out inside the remains; and the token never reaches the output."""
    assert REAL_GIT is not None
    shim_dir = code_cell["tmp"] / "git-bin"
    shim_dir.mkdir()
    shim = shim_dir / "git"
    shim.write_text(GIT_SHIM.replace("{real}", REAL_GIT).replace("{origin}", str(code_cell["origin"])))
    shim.chmod(0o755)
    monkeypatch.setenv("PATH", f"{shim_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_CLONE_CUT", "1")
    with pytest.raises(SystemExit) as stop:
        _run_code_cell(code_cell)
    assert "tok-123" not in str(stop.value)
    monkeypatch.delenv("FAKE_CLONE_CUT")
    _run_code_cell(code_cell)
    tasks = code_cell["tasks"]
    assert (tasks / "README").read_text() == "stand-in\n"
    head = subprocess.run(["git", "-C", str(tasks), "rev-parse", "HEAD"], check=True,
                          capture_output=True, text=True).stdout.strip()
    assert head == code_cell["head"]
    remote = subprocess.run(["git", "-C", str(tasks), "remote", "get-url", "origin"], check=True,
                            capture_output=True, text=True).stdout.strip()
    assert remote == "https://github.com/poisson-labs/tasks.git", "the token stayed in the remote"
    leftovers = sorted(p.name for p in code_cell["tmp"].iterdir() if p.name.startswith("tasks"))
    assert leftovers == ["tasks"], leftovers
