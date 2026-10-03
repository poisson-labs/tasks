"""Helpers more than one test file uses, kept in one place.

Each was copied between test files before, or imported from one test file into another.
The fixtures that go with them (`rig`, `code_cell`) are in `tests/conftest.py`.  Test files
import these as `tests.helpers`, the way `pyproject.toml`'s `pythonpath` lets them.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import textwrap
import threading
from collections.abc import Iterable, Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest
import verifiers.v1 as vf

from poisson_tasks import calibration as cal
from poisson_tasks.engine import apply, init_state
from poisson_tasks.tasks import TaskBundle, Turn, scenario_for

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
FIXTURE = HERE / "fixtures" / "qwen3-8b-chat-template.json"
NOTEBOOK = REPO / "notebooks" / "calibration_model_b.ipynb"
FAKE = HERE / "fake_vllm.py"


def run_module() -> Any:
    import importlib

    return importlib.import_module("poisson_tasks.calibration_run")


# ---------------------------------------------------------------------------
# skip markers
# ---------------------------------------------------------------------------

needs_uv = pytest.mark.skipif(shutil.which("uv") is None,
                              reason="the `null` harness launches its program through uv")
needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="the clone cell runs git")


# ---------------------------------------------------------------------------
# synthetic traces: what each call's tool message holds, the seeded prompt, the turns
# ---------------------------------------------------------------------------


def turns_of(calls: Iterable[tuple[str, Any]], reply: bool) -> tuple[Turn, ...]:
    turns = [Turn(content="", calls=(call,), finish_reason="tool_calls") for call in calls]
    if reply:
        turns.append(Turn(content="Done.", calls=(), finish_reason="stop"))
    return tuple(turns)


def live_observations(bundle: TaskBundle, calls: Iterable[tuple[str, Any]]) -> list[str]:
    """What each call's tool message holds under the `null` harness at 0.3.1.

    The two `error:` strings are the harness's own, from `harnesses/null/program.py`.  A
    call the harness refuses never reaches the server, so the engine's counter stays put.
    """
    state = init_state(scenario_for(bundle.seed, bundle.split), bundle.seq_start)
    names = {str(tool["name"]) for tool in bundle.tools}
    out: list[str] = []
    for name, args in calls:
        if not isinstance(args, dict):
            out.append(
                "error: tool arguments must be a JSON object, got "
                f"{type(json.loads(json.dumps(args))).__name__}; resend as an object"
            )
        elif name not in names:
            out.append(f"error: unknown tool {name!r}")
        else:
            state, observation = apply(state, (name, args))
            out.append(observation)
    return out


def seeded_nodes(task: Any) -> list[Any]:
    """The prompt as the trace holds it: every message prompt-supplied, `sampled=False`."""
    prompt = task.data.prompt
    if isinstance(prompt, str):
        return [vf.MessageNode(parent=None, message=vf.UserMessage(content=prompt), sampled=False)]
    return [
        vf.MessageNode(parent=index - 1 if index else None, message=message, sampled=False)
        for index, message in enumerate(prompt)
    ]


# ---------------------------------------------------------------------------
# a stub OpenAI-compatible endpoint on loopback
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def recording_endpoint() -> Iterator[tuple[str, list[dict[str, Any]]]]:
    """An OpenAI-compatible chat endpoint on loopback that ends every episode on its first
    turn and keeps each request body whole."""
    bodies: list[dict[str, Any]] = []

    class Stub(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:
            pass

        def do_POST(self) -> None:
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            bodies.append(body)
            out = {
                "id": "chatcmpl-stub", "object": "chat.completion", "created": 0,
                "model": body.get("model"),
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": "Done."},
                    "finish_reason": "stop",
                }],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }
            data = json.dumps(out).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = HTTPServer(("127.0.0.1", 0), Stub)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1", bodies
    finally:
        server.shutdown()
        server.server_close()


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
        return port


# ---------------------------------------------------------------------------
# the committed calibration cards
# ---------------------------------------------------------------------------

Cells = dict[tuple[str, str], list[cal.EpisodeRecord]]


def rebuild_committed_card(folder: Path) -> tuple[cal.Artifact, Cells]:
    """A committed card's artifact rebuilt from its folder's records alone, under the
    provenance block its `artifact.json` recorded, with the instrument tally from
    `tallies.json` where the folder has one; and the cells it was built from."""
    stored = json.loads((folder / "artifact.json").read_text())
    cells: Cells = {}
    for record in cal.read_records(folder / "episodes.jsonl"):
        cells.setdefault((record.arm_id, record.model), []).append(record)
    tallies_path = folder / "tallies.json"
    tallies = json.loads(tallies_path.read_text()) if tallies_path.exists() else {}
    artifact = cal.build_artifact(cells, cal.Provenance(**stored["provenance"]),
                                  tally={key: tallies.get(key[0], {}) for key in cells})
    return artifact, cells


# The plain-words checks' pattern: identifiers of internal decisions and test groups, spec
# section numbers, and the names of private places and people.  Whole words only, so a model
# name or a version number does not trip it.
INTERNAL = re.compile(
    r"\b(?:R(?:[1-9]|1[0-7])|CAL\d+|MP\d+|[XNGAE]\d+)\b"
    r"|\b2\.\d defines\b|§|\bTG-(?:ADR|M)\d*|\b[Vv]ault\b|\bTaylor\b|\bruling\b|\bhandoff\b"
)


# ---------------------------------------------------------------------------
# model B's notebook: its cells, and the run on a laptop (the `rig` fixture's Rig)
# ---------------------------------------------------------------------------

HELPER_MARK = "# the driver helper"
CODE_MARK = "# The code: poisson-tasks at REPO_REF"

GIT = ["git", "-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid",
       "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null"]


def notebook_cell(mark: str) -> str:
    nb = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    found = ["".join(c["source"]) for c in nb["cells"]
             if c["cell_type"] == "code" and "".join(c["source"]).startswith(mark)]
    assert len(found) == 1, f"one code cell opens with {mark!r}"
    return found[0]


def driver_helper() -> dict[str, Any]:
    ns: dict[str, Any] = {"DRIVER": [sys.executable, "-c", "pass"], "COMMON": []}
    exec(notebook_cell(HELPER_MARK), ns)
    return ns


def run_code_cell(world: dict[str, Any]) -> None:
    """Run the notebook's clone cell in the `code_cell` fixture's world."""
    ns = driver_helper()
    ns.update({"REPO": "poisson-labs/tasks", "REPO_REF": "main", "TASKS": str(world["tasks"]),
               "DRIVE_DIR": str(world["drive"])})
    exec(notebook_cell(CODE_MARK), ns)


REDUCED = textwrap.dedent("""
    import sys
    from poisson_tasks import calibration as cal
    from poisson_tasks import calibration_run as run

    # The reduced design: the notebook's commands and code path, on fewer tasks.
    run.PHASE1_DESIGN = run.Design(seeds=(404, 55), n=2, k_values=(1, 2))
    run.PROBE_DESIGN = run.Design(seeds=(404, 55), n=2, k_values=(1, 2))
    run.CARD_DESIGN = run.Design(seeds=(404, 55, 2121), n=2, k_values=(1, 2))
    run.CARD_ARMS = ("depth:d1", "distractor:r0@k16")
    sys.exit(run.main(sys.argv[1:]))
""")


class Rig:
    """The notebook's filesystem and processes, on a laptop: a local disk, a durable folder,
    a fake `vllm` and a fake `nvidia-smi` on PATH, and the driver run as a subprocess."""

    def __init__(self, tmp: Path, mode: str = "reference", delay: float = 0.0) -> None:
        self.tmp = tmp
        self.local = tmp / "local"
        self.durable = tmp / "durable"
        self.bin = tmp / "bin"
        self.bin.mkdir()
        vllm = self.bin / "vllm"
        vllm.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKE}" "$@"\n')
        vllm.chmod(0o755)
        smi = self.bin / "nvidia-smi"
        smi.write_text("#!/bin/sh\necho 'NVIDIA L4, 580.82.07'\n")
        smi.chmod(0o755)
        self.driver = tmp / "driver.py"
        self.driver.write_text(REDUCED)
        self.port = free_port()
        self.env = {
            **os.environ,
            "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            "FAKE_MODE": mode, "FAKE_DELAY": str(delay), "FAKE_SEEDS": "404,55,2121",
            "PYTHONPATH": str(REPO / "src"),
        }
        self.env.pop("FAKE_VERSION", None)
        self.started: list[subprocess.Popen[bytes]] = []
        self.server_pids: list[int] = []

    def argv(self, command: str, *extra: str) -> list[str]:
        if command == "verify":  # the laptop's step, after the download: no runtime folders
            return [sys.executable, str(self.driver), command, *extra]
        common = ["--local", str(self.local), "--durable", str(self.durable),
                  "--port", str(self.port), "--mirror-interval", "0.2"]
        return [sys.executable, str(self.driver), command, *common, *extra]

    def run(self, command: str, *extra: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        done = subprocess.run(self.argv(command, *extra), env=self.env, capture_output=True,
                              text=True, timeout=600)
        if check and done.returncode != 0:
            raise AssertionError(f"{command} exited {done.returncode}\n{done.stdout}\n{done.stderr}")
        return done

    def start(self, command: str, *extra: str) -> subprocess.Popen[bytes]:
        proc = subprocess.Popen(self.argv(command, *extra), env=self.env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.started.append(proc)
        return proc

    def serve(self) -> None:
        self.run("serve", "--vllm", str(self.bin / "vllm"), "--tokenizer-config",
                 str(self.tmp / "tokenizer_config.json"), "--timeout", "60")
        self.server_pids.append(int((self.local / "vllm.pid").read_text()))

    def stop_server(self) -> None:
        self.run("stop-server", check=False)

    def close(self) -> None:
        """Stop every process this rig started, by the PIDs it recorded."""
        for proc in self.started:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=30)
        self.stop_server()
        for pid in self.server_pids:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                continue

    def durable_ids(self, phase: str) -> set[str]:
        ids: set[str] = set()
        for path in (self.durable / phase).glob("*/traces.jsonl"):
            for line in path.read_bytes().splitlines():
                if line.strip():
                    ids.add(json.loads(line)["id"])
        return ids
