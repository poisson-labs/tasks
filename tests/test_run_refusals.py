"""A real run with no arm, or with an empty seed list, stops before any model call and says what
to pass.

`eval poisson-tasks` lists the taskset before it starts anything that could call a model, and
that listing is the taskset's own iteration. The refusal sits there, and in neither of the two
places that must keep accepting both:
- the config: `eval --dry-run` validates it and stops, and four tests in
  `tests/test_tg_m5_standalone.py` dry-run the id with no arm and no seeds;
- `load`, which `test_x8_2` calls directly and which yields nothing for an empty seed list.

So a dry run still exits 0, and a real run of the same command refuses.

Each real run here goes through the wheel's own command line against a fake OpenAI-compatible
endpoint on loopback, which counts every request it is sent. The control is the same command
with an arm and a seed: it does reach the endpoint, so a count of zero means something. The
control runs an episode through the `null` harness, which launches its program through uv, so
the run tests skip without uv, as every test that runs an episode does.

The messages are pinned for what they tell a command-line user, not for their wording: the
option to pass and, for the arm, an example that the option accepts. How `eval` prints them is
the wheel's business.
"""

from __future__ import annotations

import dataclasses
import importlib
import json
import os
import shutil
import subprocess
import sys
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from poisson_tasks.knobs import ArmSpec

TASKSET_ID = "poisson-tasks"
EVAL_MAIN = "import sys; from verifiers.v1.cli.eval.main import main; main(sys.argv[1:])"
KEY_VAR = "POISSON_TASKS_FAKE_KEY"
ARM = {"knob": "depth", "level": 1, "control": None, "strictness": "strict",
       "split": "eval", "generator_version": "0"}
SEED = 404

needs_uv = pytest.mark.skipif(
    shutil.which("uv") is None, reason="the `null` harness launches its program through uv"
)


def taskset(arm: dict[str, Any], seeds: list[int]) -> Any:
    """The taskset a run lists, built the way `eval` builds it: its config type and its class
    found by the id, through the wheel's own loader."""
    loaders = importlib.import_module("verifiers.v1.utils.loaders")
    config = loaders.taskset_config_type(TASKSET_ID)(id=TASKSET_ID, arm=arm, seeds=seeds)
    return loaders.load_taskset(config)


def refusal(arm: dict[str, Any], seeds: list[int]) -> str:
    with pytest.raises(ValueError) as refused:
        list(taskset(arm, seeds))
    return str(refused.value)


# --------------------------------------------------------------------------
# what the taskset says, in this process
# --------------------------------------------------------------------------


def test_listing_a_taskset_with_no_arm_names_the_option_and_an_arm_it_accepts() -> None:
    message = refusal({}, [SEED])
    assert "--env.taskset.arm" in message, message
    example = json.loads(message[message.index("{"):message.rindex("}") + 1])
    assert set(example) == {field.name for field in dataclasses.fields(ArmSpec)}, example
    # The example is an arm the option takes: with it, the same seed lists as one task.
    assert len(list(taskset(example, [SEED]))) == 1
    assert not [word for word in ("dataclasses", "asdict") if word in message], message


def test_listing_a_taskset_with_no_seeds_refuses_in_one_line_while_load_yields_nothing() -> None:
    assert list(taskset(ARM, []).load()) == []
    message = refusal(ARM, [])
    assert "\n" not in message and "--env.taskset.seeds" in message, message
    assert len(list(taskset(ARM, [SEED]))) == 1


# --------------------------------------------------------------------------
# a real run, through the wheel's command line, against a fake endpoint
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def endpoint() -> Iterator[tuple[str, list[str]]]:
    """A fake chat endpoint on loopback that answers every request with a plain reply, which
    ends an episode, and records the path of each request it is sent."""
    seen: list[str] = []
    reply = json.dumps({
        "id": "chatcmpl-fake", "object": "chat.completion", "created": 0, "model": "fake/model",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "Done."},
                     "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }).encode("utf-8")

    class Fake(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:
            pass

        def do_GET(self) -> None:
            seen.append(self.path)
            self.send_response(404)
            self.end_headers()

        def do_POST(self) -> None:
            seen.append(self.path)
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(reply)))
            self.end_headers()
            self.wfile.write(reply)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/v1", seen
    finally:
        server.shutdown()
        server.server_close()


def run(url: str, out: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """`eval poisson-tasks` against the fake endpoint, writing under `out`."""
    out.mkdir(parents=True, exist_ok=True)
    return subprocess.run(
        [sys.executable, "-c", EVAL_MAIN, TASKSET_ID, "--model", "fake/model",
         "--client.base-url", url, "--client.api-key-var", KEY_VAR, "--no-push",
         "-o", str(out), *args],
        cwd=out, env={**os.environ, KEY_VAR: "fake-secret"},
        capture_output=True, text=True, timeout=600,
    )


@pytest.fixture(scope="module")
def reached(endpoint: tuple[str, list[str]], tmp_path_factory: pytest.TempPathFactory) -> None:
    """The control: the same command with an arm and a seed reaches the endpoint."""
    url, seen = endpoint
    seen.clear()
    done = run(url, tmp_path_factory.mktemp("control"),
               "--env.taskset.arm", json.dumps(ARM), "--env.taskset.seeds", str(SEED))
    assert done.returncode == 0, (done.stdout + done.stderr)[-3000:]
    assert seen, "the control run sent the endpoint nothing, so a count of zero shows nothing"


@needs_uv
@pytest.mark.parametrize("case", ["no-arm", "no-seeds"])
def test_a_real_run_refuses_before_any_model_call_and_a_dry_run_still_passes(
    case: str, endpoint: tuple[str, list[str]], reached: None, tmp_path: Path
) -> None:
    url, seen = endpoint
    arm, seeds = ({}, [SEED]) if case == "no-arm" else (ARM, [])
    args = ["--env.taskset.arm", json.dumps(arm)] if arm else []
    args += ["--env.taskset.seeds", *map(str, seeds)] if seeds else []
    dry = run(url, tmp_path / "dry", *args, "--dry-run")
    assert dry.returncode == 0, (dry.stdout + dry.stderr)[-3000:]
    seen.clear()
    done = run(url, tmp_path / "real", *args)
    assert done.returncode != 0, (done.stdout + done.stderr)[-3000:]
    assert seen == []
    assert refusal(arm, seeds) in done.stdout + done.stderr, (done.stdout + done.stderr)[-3000:]
