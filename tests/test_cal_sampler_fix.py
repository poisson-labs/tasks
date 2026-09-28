"""Model B's server starts on a Colab L4, and a server that does not start says why.

On Colab (an L4, driver 580.82), `serve` stopped with "the server process exited before it
became healthy" after vLLM had loaded the weights and sized the KV cache.  The STOP printed
the last 3,000 characters of `vllm.log`: the API server's traceback, ending in "Engine core
initialization failed. See root cause above".  The root cause was above it, in the engine
process's own traceback: warming up the sampler, FlashInfer compiled its top-k/top-p kernel
on the spot and could not find `ninja` (`FileNotFoundError: [Errno 2] No such file or
directory: 'ninja'`).  With `VLLM_USE_FLASHINFER_SAMPLER=0` the same runtime served healthy
after 142 s, vLLM logging "FlashInfer top-p/top-k sampling disabled".

So the pin now carries that setting.  It goes into vLLM's environment, and into the flags the
card's provenance prints, since the card has to say how the model was served.  It moves no
number: at temperature 1.0 and top_p 1.0 both samplers draw from the same distribution, and
FlashInfer's kernel is a faster route to that draw.  And the STOP now names the engine's own
exception and what to do about a known one, not the tail.

`fixtures/vllm-serve-ninja-failure.log` is rebuilt from the log lines of that Colab run.  The
engine's traceback is abridged; the exception line is verbatim.  The API server's traceback is
printed twice, so that the tail the old STOP showed does not reach the cause, as it did not on
Colab.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SRC = REPO / "src"
TEMPLATE_FIXTURE = HERE / "fixtures" / "qwen3-8b-chat-template.json"
FAILURE_LOG = HERE / "fixtures" / "vllm-serve-ninja-failure.log"
NINJA = "FileNotFoundError: [Errno 2] No such file or directory: 'ninja'"
SETTING = "VLLM_USE_FLASHINFER_SAMPLER"


def run_module() -> Any:
    import importlib

    return importlib.import_module("poisson_tasks.calibration_run")


def _driver(*args: str) -> list[str]:
    return [sys.executable, "-m", "poisson_tasks.calibration_run", *args]


def _after_stop(output: str) -> str:
    at = output.find("STOP:")
    return output[at:] if at >= 0 else ""


# ---------------------------------------------------------------------------
# the pin
# ---------------------------------------------------------------------------


def test_the_pin_turns_the_flashinfer_sampler_off() -> None:
    pin = run_module().QWEN3_8B
    assert dict(pin.env) == {SETTING: "0"}


def test_the_setting_is_in_the_provenance_flags_and_the_serving_block() -> None:
    """The card prints the serving block's flags; a setting that is not there is a way the
    model was served that the card does not say."""
    pin = run_module().QWEN3_8B
    assert f"{SETTING}=0" in pin.flags()
    entry = pin.serving_entry(stack_version="0.29.0+cu129", gpu_name="NVIDIA L4")
    assert f"{SETTING}=0" in entry["flags"]
    assert entry["env"] == {SETTING: "0"}


def test_the_setting_is_not_an_argument_to_vllm() -> None:
    """It is an environment variable; `vllm serve` has no such flag."""
    args = run_module().QWEN3_8B.serve_args("/tmp/t.jinja")
    assert not any(SETTING in arg for arg in args)
    assert args[:2] == ["serve", "Qwen/Qwen3-8B"]


def test_the_serve_environment_keeps_the_callers_and_the_pin_wins() -> None:
    pin = run_module().QWEN3_8B
    env = pin.serve_env({"PATH": "/usr/bin", SETTING: "1"})
    assert env["PATH"] == "/usr/bin"
    assert env[SETTING] == "0"


# ---------------------------------------------------------------------------
# reading the engine's own error out of vllm.log
# ---------------------------------------------------------------------------


def test_the_fixture_reproduces_a_tail_that_misses_the_cause() -> None:
    """The control: what the old STOP printed does not contain the cause."""
    text = FAILURE_LOG.read_text(encoding="utf-8")
    assert NINJA in text
    assert "ninja" not in text[-3000:]


def test_the_engine_error_is_the_engines_own_exception() -> None:
    text = FAILURE_LOG.read_text(encoding="utf-8")
    found = run_module().engine_error(text)
    assert found is not None and NINJA in found
    assert "Engine core initialization failed" not in found


def test_without_an_engine_error_the_last_exception_is_reported() -> None:
    text = (
        "(APIServer pid=1) INFO starting\n"
        "(APIServer pid=1) Traceback (most recent call last):\n"
        '(APIServer pid=1)   File "x.py", line 1, in f\n'
        "(APIServer pid=1) ValueError: planted API server failure\n"
    )
    found = run_module().engine_error(text)
    assert found is not None and "ValueError: planted API server failure" in found


def test_a_clean_log_has_no_engine_error() -> None:
    text = "(EngineCore pid=1) INFO 09-28 16:23:49 [core.py:361] init engine took 103.37 s\n"
    assert run_module().engine_error(text) is None


def test_the_missing_ninja_names_the_setting_that_avoids_it() -> None:
    hint = run_module().known_cause(NINJA)
    assert hint is not None and SETTING in hint


# ---------------------------------------------------------------------------
# serve, end to end, with a stand-in vllm
# ---------------------------------------------------------------------------


@pytest.fixture
def runtime(tmp_path: Path) -> Iterator[dict[str, Any]]:
    """The pinned template's tokenizer config, the runtime's folders, and an environment that
    sets the sampler the other way, so the pin has to win."""
    data = json.loads(TEMPLATE_FIXTURE.read_text(encoding="utf-8"))
    tokenizer = tmp_path / "tokenizer_config.json"
    tokenizer.write_text(json.dumps({"chat_template": data["chat_template"]}), encoding="utf-8")
    local = tmp_path / "local"
    common = ["--local", str(local), "--durable", str(tmp_path / "durable"), "--port", "1"]
    env = {**os.environ, "PYTHONPATH": str(SRC), SETTING: "1"}
    state: dict[str, Any] = {"tmp": tmp_path, "tokenizer": tokenizer, "local": local,
                             "common": common, "env": env}
    yield state
    pid_file = local / "vllm.pid"
    if pid_file.exists():
        try:
            os.kill(int(pid_file.read_text()), signal.SIGTERM)
        except (ProcessLookupError, ValueError):
            pass


def _serve_with(runtime: dict[str, Any], script: str) -> subprocess.CompletedProcess[str]:
    vllm = runtime["tmp"] / "vllm"
    vllm.write_text("#!/bin/sh\n" + script)
    vllm.chmod(0o755)
    return subprocess.run(
        _driver("serve", *runtime["common"], "--vllm", str(vllm),
                "--tokenizer-config", str(runtime["tokenizer"]), "--timeout", "30"),
        env=runtime["env"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        timeout=120,
    )


def test_serve_starts_vllm_with_the_sampler_setting(runtime: dict[str, Any]) -> None:
    done = _serve_with(runtime, f'echo "sampler=${SETTING}"\nexit 1\n')
    assert done.returncode == 1, done.stdout
    log = (runtime["local"] / "vllm.log").read_text(encoding="utf-8")
    assert "sampler=0" in log, log


def test_a_server_that_dies_stops_with_the_engines_error(runtime: dict[str, Any]) -> None:
    done = _serve_with(runtime, f'cat "{FAILURE_LOG}"\nexit 1\n')
    assert done.returncode == 1, done.stdout
    stop = _after_stop(done.stdout)
    assert NINJA in stop, done.stdout
    assert SETTING in stop, done.stdout


def test_the_error_reported_is_this_starts_not_an_earlier_ones(runtime: dict[str, Any]) -> None:
    """vLLM's log is appended to across starts, so a failure from an earlier start is still
    in it.  The STOP reads only what this start wrote.  The earlier start's log here is just
    its engine traceback, short enough to sit inside any tail of the file."""
    runtime["local"].mkdir(parents=True)
    earlier = [line for line in FAILURE_LOG.read_text(encoding="utf-8").splitlines()
               if line.startswith("(EngineCore")]
    assert len("\n".join(earlier)) < 3000
    (runtime["local"] / "vllm.log").write_text("\n".join(earlier) + "\n", encoding="utf-8")
    planted = "ValueError: planted failure of the second start"
    done = _serve_with(
        runtime,
        f'echo "(EngineCore pid=9) ERROR 09-28 17:00:00 [core.py:1374] {planted}"\nexit 1\n',
    )
    assert done.returncode == 1, done.stdout
    stop = _after_stop(done.stdout)
    assert planted in stop, done.stdout
    assert NINJA not in stop, done.stdout
