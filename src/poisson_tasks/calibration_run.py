"""Model B's calibration card, run from a notebook against a model served locally by vLLM.

Model B is Qwen3-8B with thinking off, served by vLLM on a Colab L4 and paid for in Colab
compute units.  The run passes phase 1's plumbing gate, then
probes the hardest levels and stops there if the model floors, and only then runs phase 3:
model A's design, 14 arms x 60 eval-split seeds x 5 attempts, through the gate and CAL24.
A Colab runtime drops, so every step checkpoints to a durable folder and resumes from it
(CAL23), and the card records the serving stack, since the same weights served differently
give different numbers.

This module is what the notebook calls, one subcommand per cell, and everything it does
is reachable without a GPU: the serve step starts whatever `vllm` executable it is given.

The pieces
----------

* **The pin** (`QWEN3_8B`).  One 40-character revision, passed as `--revision` and inside
  `--served-model-name` (N18); vLLM 0.29.0's CUDA 12.9 wheel with its published sha256; and
  the serve flags.  The notebook types none of it: `install-vllm` and `serve` read it here.
* **Thinking off, whatever the request says.**  The calibration's declared decoding sends
  `reasoning_effort: low` to both models, and at vLLM 0.29.0 a request carrying
  `reasoning_effort` sets the chat template's `enable_thinking` to true
  (`ChatCompletionRequest.build_chat_params`), which overrides a server-side
  `--default-chat-template-kwargs`.  So the pin serves a template derived from the pinned
  revision's own (`no_think_template`): the one `enable_thinking` switch is replaced by the
  branch it takes when thinking is off, so the served prompt is byte for byte what the stock
  template renders with thinking off, and the request body stays the one model A was sent.
* **The checkpoint.**  The wheel's own `traces.jsonl` and the instrument tally are the checkpoint
  (CAL23); they live on the runtime's local disk, where `resume.load` can rewrite them
  atomically, and `Mirror` copies them to the durable folder (Google Drive on Colab) every
  few seconds and on every exit it gets to run.  A `.jsonl` is copied only up to its last
  complete line, and every copy is a temp file and a rename.  On a fresh runtime `restore`
  brings the durable copy back and the wheel's resume re-runs exactly what is owed, never
  more than `n` per task.
* **The lock and the run manifest.**  `RunLock` keeps two runtimes from writing one run.
  `check_run_manifest` records the stack a run started on and refuses a resume on another
  GPU, vLLM build, flag set, template or generator.
* **The probe** (`probe_verdict`).  Depth 5 and depth 8, the lowest strict level on model A's
  card and the longest chain, six seeds, two attempts.  It stops the run if the model floors
  there (leaky pass@1 at or below CAL12's low saturation bound), if more than CAL24's
  threshold never call a tool, if any instrument failure occurs, or if the context cap cut an
  episode or prompts came within a quarter of it.  It never switches models.
* **The card.**  `finalize` builds the artifact and the document from the per-episode records
  with `Provenance.for_run`, the served name as the model and the serving block; no rate,
  so the dollar figure is null.  `bundle` gathers the small files and a sha256 manifest into
  one zip; `verify` checks the manifest and recomputes the artifact from the records before
  anything is copied out of the bundle.
* **A cell run again.**  Every step can be run again in the same runtime.  `install-vllm`
  writes `INSTALL_RECORD` into the virtualenv as its last act: a finished install is never
  repeated, and a virtualenv without the record is an install that did not finish, which is
  removed and built again from nothing (uv will not create a virtualenv over one).  `serve`
  run again while the server it started is still loading waits for it.  A command that fails
  ends its step with a STOP that carries the command's own output (`StepFailed`), so the
  notebook shows the reason and not only an exit status.

Nothing here imports Proofload or the adapter (CAL22).
"""

from __future__ import annotations

import argparse as _argparse
import contextlib as _contextlib
import dataclasses as _dc
import datetime as _datetime
import hashlib as _hashlib
import importlib.metadata as _metadata
import json as _json
import os as _os
import pathlib as _pathlib
import re as _re
import shutil as _shutil
import signal as _signal
import socket as _socket
import subprocess as _subprocess
import sys as _sys
import tempfile as _tempfile
import threading as _threading
import time as _time
import urllib.error as _urlerror
import urllib.request as _urlrequest
import zipfile as _zipfile
from collections import Counter as _Counter
from collections import deque as _deque
from collections.abc import Callable as _Callable
from collections.abc import Iterator as _Iterator
from collections.abc import Mapping as _Mapping
from collections.abc import Sequence as _Sequence
from typing import Any as _Any

from poisson_tasks import calibration as _cal
from poisson_tasks.knobs import ArmSpec as _ArmSpec
from poisson_tasks.knobs import arm_id as _arm_id
from poisson_tasks.tasks import generate as _generate
from poisson_tasks.taskset import MAX_MODEL_CALLS as _MAX_MODEL_CALLS

__all__ = [
    "ServePin",
    "QWEN3_8B",
    "EXPECTED_GENERATOR_HASH",
    "no_think_template",
    "ServingMismatch",
    "StepFailed",
    "INSTALL_RECORD",
    "wait_healthy",
    "first_episode_error",
    "DROPPED_ENV",
    "engine_error",
    "known_cause",
    "KNOWN_CAUSES",
    "check_server",
    "check_thinking_off",
    "gpu_facts",
    "complete_lines",
    "Mirror",
    "mirroring",
    "RunLock",
    "LockHeld",
    "check_run_manifest",
    "Design",
    "design",
    "PHASE1_DESIGN",
    "PHASE1_ARMS",
    "PROBE_DESIGN",
    "PROBE_ARMS",
    "PROBE_CONTEXT_ARMS",
    "card_status",
    "CARD_DESIGN",
    "CARD_ARMS",
    "FLOOR",
    "HEADROOM",
    "CARD_MAX_MODEL_CALLS",
    "ProbeVerdict",
    "probe_verdict",
    "trace_facts",
    "finalize",
    "make_bundle",
    "verify_bundle",
    "build_parser",
    "main",
]

# ---------------------------------------------------------------------------
# the pin (N18)
# ---------------------------------------------------------------------------

_THINK_SWITCH = (
    "    {%- if enable_thinking is defined and enable_thinking is false %}\n"
    "        {{- '<think>\\n\\n</think>\\n\\n' }}\n"
    "    {%- endif %}\n"
)
"""The one place Qwen3-8B's template reads `enable_thinking`: the generation prompt."""
_THINK_OFF = "    {{- '<think>\\n\\n</think>\\n\\n' }}\n"
"""The branch that switch takes with thinking off, made unconditional."""


@_dc.dataclass(frozen=True)
class ServePin:
    """Everything that decides what model B's numbers are measured on, in one place.

    `flags()` is what the provenance block records: the environment settings the server is
    started with, as `NAME=value`, then the serve arguments without the host and port (where
    the server listens changes no number) and with the chat template named by its sha256
    instead of a path on one runtime's disk."""

    model: str
    revision: str
    vllm_version: str
    vllm_wheel_name: str
    vllm_wheel_url: str
    vllm_wheel_sha256: str
    vllm_wheel_size: int
    torch_backend: str
    python: str
    gpu: str
    quantization: str | None
    max_model_len: int
    tool_call_parser: str
    stock_template_sha256: str
    template_sha256: str
    host: str = "127.0.0.1"
    port: int = 8000
    env: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if len(self.revision) != 40 or any(c not in "0123456789abcdef" for c in self.revision):
            raise ValueError(
                f"revision must be a 40-character commit hash: {self.revision!r}"
            )

    @property
    def served_name(self) -> str:
        """`<model>@<revision>`: the revision rides every request as the model name, and the
        server answers 404 to any other."""
        return f"{self.model}@{self.revision}"

    def base_url(self, port: int | None = None) -> str:
        return f"http://{self.host}:{self.port if port is None else port}/v1"

    def endpoint_host(self, port: int | None = None) -> str:
        return f"{self.host}:{self.port if port is None else port}"

    def _flags(self, template: str) -> list[str]:
        flags = [
            "--revision", self.revision,
            "--served-model-name", self.served_name,
        ]
        if self.quantization is not None:
            flags += ["--quantization", self.quantization]
        flags += [
            "--max-model-len", str(self.max_model_len),
            "--enable-auto-tool-choice",
            "--tool-call-parser", self.tool_call_parser,
            "--chat-template", template,
            "--generation-config", "vllm",
        ]
        return flags

    def serve_args(self, template_path: str, port: int | None = None) -> list[str]:
        """The arguments after the `vllm` executable."""
        return [
            "serve", self.model, *self._flags(template_path),
            "--host", self.host, "--port", str(self.port if port is None else port),
        ]

    def flags(self) -> list[str]:
        settings = [f"{name}={value}" for name, value in self.env]
        return settings + self._flags(f"<chat template sha256:{self.template_sha256}>")

    def serve_env(self, base: _Mapping[str, str]) -> dict[str, str]:
        """The server's environment: the caller's, with the pin's settings on top."""
        return {**base, **dict(self.env)}

    def model_entry(self, port: int | None = None) -> dict[str, _Any]:
        """The provenance block's model entry.  No rate: model B costs Colab compute units,
        not dollars, so its dollar figure is null."""
        return {"id": self.served_name, "revision": self.revision,
                "endpoint_host": self.endpoint_host(port)}

    def serving_entry(self, *, stack_version: str, gpu_name: str) -> dict[str, _Any]:
        """The serving block for a locally served model: the stack and its version as the server
        reports it, the flags, the GPU as the runtime reports it, and the revision."""
        return {
            "kind": "local",
            "stack": "vllm",
            "stack_version": stack_version,
            "flags": self.flags(),
            "env": dict(self.env),
            "gpu": gpu_name,
            "revision": self.revision,
            "served_model_name": self.served_name,
            "chat_template_sha256": self.template_sha256,
            "stock_chat_template_sha256": self.stock_template_sha256,
            "vllm_wheel": self.vllm_wheel_name,
            "vllm_wheel_sha256": self.vllm_wheel_sha256,
        }


QWEN3_8B = ServePin(
    model="Qwen/Qwen3-8B",
    revision="b968826d9c46dd6066d109eabc6255188de91218",
    vllm_version="0.29.0",
    vllm_wheel_name="vllm-0.29.0+cu129-cp38-abi3-manylinux_2_28_x86_64.whl",
    vllm_wheel_url=(
        "https://github.com/vllm-project/vllm/releases/download/v0.29.0/"
        "vllm-0.29.0+cu129-cp38-abi3-manylinux_2_28_x86_64.whl"
    ),
    vllm_wheel_sha256="22e8d8fec755986b3ad964004a1f8c65a55626ec948354bdbe95993e6b0289fe",
    vllm_wheel_size=548_493_389,
    torch_backend="cu129",
    python="3.12",
    gpu="L4",
    quantization="fp8",
    max_model_len=16384,
    tool_call_parser="hermes",
    stock_template_sha256="a55ee1b1660128b7098723e0abcd92caa0788061051c62d51cbe87d9cf1974d8",
    template_sha256="b4d28698abae82732da6a74bb08a623934fa81b775aea50908246e9fc1323333",
    env=(("VLLM_USE_FLASHINFER_SAMPLER", "0"),),
)
"""Model B, pinned 2026-09-25.

* `Qwen/Qwen3-8B` at `b968826d`, the repository's head since 2025-07-26 (8.19B parameters,
  BF16, Apache-2.0).
* vLLM 0.29.0, the version the pilot's serving stack is pinned to,
  as the release's CUDA 12.9 wheel: PyPI's default wheel pulls torch's CUDA 13 build, which
  needs a newer driver than a runtime may have, and CUDA 12.9 runs on both.
* `--quantization fp8`: the BF16 weights quantized at load, as the pilot's serving stack does
  for its Qwen on the same GPU.  About 9 GB of weights instead of 16.4, which leaves an L4 roughly
  three times the KV cache and so roughly three times the concurrent episodes.
* `--max-model-len 16384` (raised from 8192 on 2026-09-28): Qwen's chat template spells the
  sixteen tool schemas out as JSON, and the two history controls (`depth:d1+h8`,
  `depth:d2+h5`) open with five and eight seeded turns.  On Colab their prompts reached 6,129
  and 6,081 tokens against the 6,144 that 8,192 leaves beside the declared 2,048-token
  completion limit, and 38 episodes ended at the cap.  A prompt past the cap ends the episode
  as `context_length` with the trace not ok, and the card counts that as an instrument
  failure: the cap is a serving choice, not the model's difficulty.  So the cap has to clear
  every arm, and the probe runs the history controls and refuses to go on if an episode
  ends at the cap or a prompt passes 75% of the room it leaves.  Qwen3-8B's native context
  is 32,768; the L4's KV cache (67,504 tokens at FP8) still holds four full-length requests.
* `--enable-auto-tool-choice --tool-call-parser hermes`: Qwen3's `<tool_call>` JSON format.
* `--generation-config vllm`: nothing from the repository's `generation_config.json`, whose
  `top_k: 20` would otherwise apply to every request unseen.  The request's declared decoding
  is the whole decoding.
* `--chat-template`: `no_think_template` of the revision's own template.
* `VLLM_USE_FLASHINFER_SAMPLER=0` (added 2026-09-28): vLLM samples with its own PyTorch
  top-k/top-p sampler, not FlashInfer's.  FlashInfer compiles its sampling kernel at warmup,
  which needs `ninja` and a CUDA compiler on the server's path; on Colab it found no `ninja`
  and the engine died before it was healthy.  With the setting the same L4 served healthy.  It
  moves no number: at temperature 1.0 and top_p 1.0 both samplers draw from the same
  distribution.
"""

EXPECTED_GENERATOR_HASH = "8edd01f39f9ae897f54e757fc62381a5319ce36426f2aff5198cbe10ff719ada"
"""The generator this driver expects the installed package to be: the package's own.  Results
are only comparable on one generator, so preflight refuses a package whose generator differs."""


def no_think_template(stock: str, pin: ServePin = QWEN3_8B) -> str:
    """The pinned revision's chat template with its `enable_thinking` switch fixed off.

    Refuses any template but the pinned one, and refuses if the result is not the pinned
    derivation, so a moved revision or an edited template cannot slip through."""
    digest = _hashlib.sha256(stock.encode("utf-8")).hexdigest()
    if digest != pin.stock_template_sha256:
        raise ValueError(
            f"the chat template's sha256 is {digest}, not the pinned revision's "
            f"{pin.stock_template_sha256}"
        )
    if stock.count(_THINK_SWITCH) != 1:
        raise ValueError("the template does not carry exactly one enable_thinking switch")
    derived = stock.replace(_THINK_SWITCH, _THINK_OFF)
    got = _hashlib.sha256(derived.encode("utf-8")).hexdigest()
    if got != pin.template_sha256 or "enable_thinking" in derived:
        raise ValueError(f"the derived template's sha256 is {got}, not {pin.template_sha256}")
    return derived


# ---------------------------------------------------------------------------
# talking to the server
# ---------------------------------------------------------------------------


class ServingMismatch(RuntimeError):
    """The server, the GPU or the run's recorded stack is not the pinned one."""


class StepFailed(RuntimeError):
    """A step cannot go on.  Either a command it ran failed, and the message carries the end
    of that command's own output, or it found something that is not its own at a path it
    would replace."""


_TAIL_LINES = 40
"""How much of a failed command's output its STOP repeats: the end, where the reason is."""


def _failure(argv: _Sequence[str], code: int, output: str) -> StepFailed:
    lines = output.rstrip("\n").splitlines()[-_TAIL_LINES:]
    said = "\n".join(lines) if lines else "(it printed nothing)"
    return StepFailed(f"`{' '.join(argv)}` exited with {code}; the end of its output:\n{said}")


def _run(argv: _Sequence[str]) -> None:
    """Run one command, printing its output and errors as they come, in order (uv reports
    progress and errors on stderr).  A non-zero exit raises `StepFailed` with the last lines
    it printed.  An interrupt stops the command too, so nothing goes on writing unseen."""
    _say("$ " + " ".join(argv))
    try:
        proc = _subprocess.Popen(list(argv), stdout=_subprocess.PIPE,
                                 stderr=_subprocess.STDOUT, text=True, bufsize=1)
    except FileNotFoundError as error:
        raise StepFailed(f"`{argv[0]}` was not found on this runtime's PATH") from error
    tail: _deque[str] = _deque(maxlen=_TAIL_LINES)
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            print(line, end="", flush=True)
            tail.append(line)
        code = proc.wait()
    except BaseException:
        proc.kill()
        proc.wait()
        raise
    if code != 0:
        raise _failure(argv, code, "".join(tail))


def _output(argv: _Sequence[str], *, timeout: float | None = None) -> str:
    """Run one command and return its standard output, for reading.  A non-zero exit raises
    `StepFailed` with the end of what it printed, its errors included."""
    _say("$ " + " ".join(argv))
    try:
        done = _subprocess.run(list(argv), capture_output=True, text=True, check=False,
                               timeout=timeout)
    except FileNotFoundError as error:
        raise StepFailed(f"`{argv[0]}` was not found") from error
    except _subprocess.TimeoutExpired as error:
        raise StepFailed(f"`{' '.join(argv)}` did not finish in {timeout:.0f} s") from error
    if done.returncode != 0:
        raise _failure(argv, done.returncode, done.stdout + done.stderr)
    return done.stdout


def _root(base_url: str) -> str:
    return base_url[: -len("/v1")] if base_url.endswith("/v1") else base_url


def _http(method: str, url: str, body: _Any = None, timeout: float = 30.0) -> tuple[int, _Any]:
    data = None if body is None else _json.dumps(body).encode("utf-8")
    request = _urlrequest.Request(url, data=data, method=method)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with _urlrequest.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            status = int(response.status)
    except _urlerror.HTTPError as error:
        raw = error.read()
        status = int(error.code)
    try:
        return status, _json.loads(raw) if raw else None
    except ValueError:
        return status, raw.decode("utf-8", "replace")


def wait_healthy(
    base_url: str,
    *,
    timeout_s: float,
    poll_s: float = 1.0,
    alive: _Callable[[], bool] | None = None,
) -> float:
    """Poll `/health` until it answers 200.  Raises if the server process died first or the
    timeout passes; returns the seconds waited."""
    start = _time.monotonic()
    while True:
        try:
            status, _ = _http("GET", _root(base_url) + "/health", timeout=5.0)
            if status == 200:
                return _time.monotonic() - start
        except (OSError, _urlerror.URLError):
            pass
        if alive is not None and not alive():
            raise RuntimeError("the server process exited before it became healthy")
        if _time.monotonic() - start > timeout_s:
            raise TimeoutError(f"the server was not healthy after {timeout_s:.0f} s")
        _time.sleep(poll_s)


def check_server(pin: ServePin, base_url: str) -> dict[str, _Any]:
    """The server is the pinned stack serving the pinned name, or refuse."""
    status, version = _http("GET", _root(base_url) + "/version")
    reported = version.get("version") if isinstance(version, dict) else None
    if status != 200 or not isinstance(reported, str):
        raise ServingMismatch(f"/version answered {status}: {version!r}")
    rest = reported[len(pin.vllm_version):]
    if not reported.startswith(pin.vllm_version) or (rest and rest[0] not in "+"):
        raise ServingMismatch(f"the server is vLLM {reported}, not the pinned {pin.vllm_version}")
    status, models = _http("GET", base_url + "/models")
    ids = [m.get("id") for m in (models or {}).get("data", [])] if isinstance(models, dict) else []
    if status != 200 or pin.served_name not in ids:
        raise ServingMismatch(f"the server serves {ids}, not {pin.served_name}")
    return {"stack_version": reported, "served_name": pin.served_name}


def _probe_spec() -> _ArmSpec:
    return spec_for("depth:d3")


def check_thinking_off(pin: ServePin, base_url: str) -> dict[str, _Any]:
    """One request with the calibration's own wire decoding, `reasoning_effort` included;
    the reply must carry no thinking."""
    _, config = _cal.run_config_for(_probe_spec(), model=pin.served_name)
    body: dict[str, _Any] = {
        "model": pin.served_name,
        "messages": [{"role": "user", "content": "Reply with the single word: ready"}],
        **config.sampling.wire_args(),
    }
    status, reply = _http("POST", base_url + "/chat/completions", body, timeout=300.0)
    if status != 200 or not isinstance(reply, dict):
        raise ServingMismatch(f"the chat endpoint answered {status}: {reply!r}")
    message = reply["choices"][0]["message"]
    content = message.get("content") or ""
    reasoning = message.get("reasoning_content") or message.get("reasoning")
    if "<think>" in content or "</think>" in content or reasoning:
        raise ServingMismatch(
            f"the model thinks although thinking is pinned off: {content[:200]!r}"
        )
    usage = reply.get("usage") or {}
    return {"content": content[:200], "completion_tokens": usage.get("completion_tokens")}


def gpu_facts() -> dict[str, str] | None:
    """The GPU's name and driver version as `nvidia-smi` reports them, or None."""
    try:
        done = _subprocess.run(
            ["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=30, check=False,
        )
    except (FileNotFoundError, _subprocess.TimeoutExpired):
        return None
    line = done.stdout.strip().splitlines()[0] if done.stdout.strip() else ""
    if done.returncode != 0 or not line:
        return None
    name, _, driver = line.partition(",")
    return {"name": name.strip(), "driver": driver.strip()}


# ---------------------------------------------------------------------------
# the checkpoint: mirror, lock and manifest (CAL23)
# ---------------------------------------------------------------------------


def complete_lines(data: bytes) -> bytes:
    """A JSON-lines file up to and including its last newline: a row still being written is
    not a checkpointed row."""
    end = data.rfind(b"\n")
    return data[: end + 1] if end >= 0 else b""


def _atomic_write(path: _pathlib.Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{_os.getpid()}.part")
    with tmp.open("wb") as handle:
        handle.write(data)
        handle.flush()
        _os.fsync(handle.fileno())
    _os.replace(tmp, path)


_DURABLE_ONLY = frozenset({"lock.json", "run.json", "calibration-model-b-bundle.zip"})
"""Written straight to the durable folder and never mirrored either way: the lock (a stale
local copy pushed back would overwrite a live heartbeat), the run manifest and the bundle."""


def _skipped(path: _pathlib.Path, root: _pathlib.Path) -> bool:
    rel = path.relative_to(root)
    return (
        path.suffix in (".tmp", ".part", ".pid")
        or path.name.startswith(".")
        or str(rel) in _DURABLE_ONLY
        or rel.parts[0] == "bundle"
    )


class Mirror:
    """Local disk to durable folder, and back.

    `push` copies every changed file under `local` to the same path under `durable`: a
    `.jsonl` only up to its last complete line, every file through a temp file and a rename,
    temp files and PID files never.  `restore` copies back only what the local disk lacks: on
    a fresh runtime that is everything; on the runtime that wrote them the local files are
    the newer ones (the wheel's resume may have rewritten them) and are left alone."""

    def __init__(self, local: _pathlib.Path, durable: _pathlib.Path) -> None:
        self.local = _pathlib.Path(local)
        self.durable = _pathlib.Path(durable)
        self._pushed: dict[str, tuple[int, int]] = {}
        self._lock = _threading.Lock()

    def push(self) -> int:
        written = 0
        with self._lock:
            if not self.local.exists():
                return 0
            for path in sorted(self.local.rglob("*")):
                if not path.is_file() or _skipped(path, self.local):
                    continue
                rel = path.relative_to(self.local)
                try:
                    stat = path.stat()
                    mark = (stat.st_size, stat.st_mtime_ns)
                    if self._pushed.get(str(rel)) == mark:
                        continue
                    data = path.read_bytes()
                except FileNotFoundError:
                    continue
                if path.suffix == ".jsonl":
                    data = complete_lines(data)
                target = self.durable / rel
                if target.exists() and target.read_bytes() == data:
                    self._pushed[str(rel)] = mark
                    continue
                _atomic_write(target, data)
                self._pushed[str(rel)] = mark
                written += 1
        return written

    def restore(self) -> int:
        written = 0
        if not self.durable.exists():
            return 0
        for path in sorted(self.durable.rglob("*")):
            if not path.is_file() or _skipped(path, self.durable):
                continue
            rel = path.relative_to(self.durable)
            target = self.local / rel
            if target.exists():
                continue
            data = path.read_bytes()
            if path.suffix == ".jsonl":
                data = complete_lines(data)
            _atomic_write(target, data)
            written += 1
        return written


class LockHeld(RuntimeError):
    """Another runtime has written this run within the stale window."""


class RunLock:
    """A lock file in the durable folder with a heartbeat.  The owner is the runtime's host
    name, so the runtime that wrote a run can always pick it up again, and a new runtime
    after a drop waits until the old heartbeat is `stale_after_s` old."""

    FILE = "lock.json"

    def __init__(
        self,
        durable: _pathlib.Path,
        *,
        owner: str | None = None,
        stale_after_s: float = 180.0,
        clock: _Callable[[], float] = _time.time,
    ) -> None:
        self.path = _pathlib.Path(durable) / self.FILE
        self.owner = owner or _socket.gethostname()
        self.stale_after_s = stale_after_s
        self.clock = clock

    def acquire(self) -> None:
        if self.path.exists():
            try:
                held = _json.loads(self.path.read_text(encoding="utf-8"))
            except ValueError:
                held = {}
            age = self.clock() - float(held.get("heartbeat", 0.0))
            if held.get("owner") != self.owner and age <= self.stale_after_s:
                raise LockHeld(
                    f"runtime {held.get('owner')!r} wrote this run {age:.0f} s ago; a second "
                    f"runtime must not write it too.  Stop the other one, or wait until its "
                    f"heartbeat is {self.stale_after_s:.0f} s old."
                )
        self.beat()

    def beat(self) -> None:
        _atomic_write(self.path, _json.dumps(
            {"owner": self.owner, "heartbeat": self.clock()}, sort_keys=True
        ).encode("utf-8"))

    def release(self) -> None:
        with _contextlib.suppress(FileNotFoundError, ValueError):
            held = _json.loads(self.path.read_text(encoding="utf-8"))
            if held.get("owner") == self.owner:
                self.path.unlink()


@_contextlib.contextmanager
def mirroring(
    mirror: Mirror, interval_s: float, lock: RunLock | None = None
) -> _Iterator[Mirror]:
    """Push every `interval_s` on a background thread, and once more on the way out,
    whatever the way out is: the Stop button's KeyboardInterrupt included.  Only a runtime
    that vanishes (SIGKILL, a dropped VM) skips the last push, and then at most one interval
    of finished episodes is re-run on the resume, each still recorded once."""
    stop = _threading.Event()

    def loop() -> None:
        while not stop.wait(interval_s):
            with _contextlib.suppress(OSError):
                mirror.push()
                if lock is not None:
                    lock.beat()

    thread = _threading.Thread(target=loop, name="calibration-mirror", daemon=True)
    thread.start()
    try:
        yield mirror
    finally:
        stop.set()
        thread.join(timeout=max(5.0, interval_s * 2))
        mirror.push()
        if lock is not None:
            lock.beat()


MANIFEST_FILE = "run.json"


def check_run_manifest(durable: _pathlib.Path, facts: _Mapping[str, _Any]) -> dict[str, _Any]:
    """Record the stack a run started on; refuse to go on with any other.  The same weights
    served on another GPU type, vLLM build, flag set or template are another measurement,
    and a card must not mix two."""
    path = _pathlib.Path(durable) / MANIFEST_FILE
    if not path.exists():
        record = {**dict(facts), "created": _now()}
        _atomic_write(path, (_json.dumps(record, indent=2, sort_keys=True) + "\n").encode("utf-8"))
        return record
    stored: dict[str, _Any] = _json.loads(path.read_text(encoding="utf-8"))
    keys = (set(stored) | set(facts)) - {"created"}
    differ = sorted(key for key in keys if stored.get(key) != facts.get(key))
    if differ:
        detail = "; ".join(f"{k}: run has {stored.get(k)!r}, now {facts.get(k)!r}" for k in differ)
        raise ServingMismatch(
            "this run started on another stack and must not resume on this one (" + detail + ")"
        )
    return stored


def _now() -> str:
    return _datetime.datetime.now(_datetime.UTC).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# designs and arms
# ---------------------------------------------------------------------------


@_dc.dataclass(frozen=True)
class Design:
    seeds: tuple[int, ...]
    n: int
    k_values: tuple[int, ...]


@_contextlib.contextmanager
def design(chosen: Design | None) -> _Iterator[None]:
    """Run under a smaller design than the card's, as model A's phase 1 did: the seed list,
    `n` and the `k` values are the calibration module's declared constants, set for the
    duration and restored after.  `None` is the card's own design, untouched."""
    if chosen is None:
        yield
        return
    names = ("S", "N", "_SEEDS", "K_VALUES")
    saved = {name: getattr(_cal, name) for name in names}
    chosen_values = (len(chosen.seeds), chosen.n, tuple(chosen.seeds), tuple(chosen.k_values))
    for name, value in zip(names, chosen_values, strict=True):
        setattr(_cal, name, value)
    try:
        yield
    finally:
        for name, value in saved.items():
            setattr(_cal, name, value)


PHASE1_DESIGN = Design(seeds=_cal.DOCUMENTED_SEEDS, n=2, k_values=(1, 2))
PHASE1_ARMS: tuple[str, ...] = ("depth:d3",)
"""Phase 1 as model A ran it: `depth:d3`, the documented seeds, two attempts."""
PROBE_DESIGN = Design(seeds=_cal.seed_list()[:6], n=2, k_values=(1, 2))
PROBE_ARMS: tuple[str, ...] = ("depth:d5", "depth:d8")
"""The hardest levels: `depth:d5` has model A's lowest strict pass@1 (0.177) and `depth:d8`
the longest chain.  Six of the sixty eval seeds, first in the published order, two attempts:
24 episodes, discarded after the verdict.  The floor is read on these alone."""
PROBE_CONTEXT_ARMS: tuple[str, ...] = ("depth:d1+h8", "depth:d2+h5")
"""The arms with the longest prompts: their seeded history comes before the task.  The probe
runs them for the context checks and the instrument count, not the floor (a control is not a
difficulty level).  Another 24 episodes."""
CARD_DESIGN: Design | None = None
"""The card's design is the calibration module's own: S = 60, n = 5."""
CARD_ARMS: tuple[str, ...] | None = None
"""The card's arms are `arm_specs()`, all fourteen (CAL2)."""

FLOOR = _cal.SATURATION_LOW
"""The probe floors when leaky pass@1 over its episodes is at or below CAL12's low bound."""
CARD_MAX_MODEL_CALLS = _MAX_MODEL_CALLS
"""The turn limit the taskset's env config imposes on every episode of the run, recorded on
the card (`poisson_tasks.taskset.MAX_MODEL_CALLS`)."""
HEADROOM = 0.75
"""The probe stops if any prompt reached this share of the room the context cap leaves."""


def spec_for(arm: str) -> _ArmSpec:
    """The arm an id names, as a card generates it.  Read from the id, so an arm outside
    the card design has a spec; text that is no arm's id is refused."""
    spec = _cal._spec_for(arm)
    if spec is None:
        raise ValueError(f"{arm!r} is not an arm id, for example depth:d3 or depth:d1+h8")
    return spec


def _card_arms() -> tuple[str, ...]:
    return CARD_ARMS if CARD_ARMS is not None else tuple(_arm_id(s) for s in _cal.arm_specs())


def _arm_dir(arm: str) -> str:
    """The run directory `run_arm` writes an arm to."""
    return arm.replace("/", "-").replace(":", "-").replace("@", "-")


# ---------------------------------------------------------------------------
# the probe
# ---------------------------------------------------------------------------


@_dc.dataclass(frozen=True)
class ProbeVerdict:
    proceed: bool
    reasons: tuple[str, ...]
    episodes: int
    scored: int
    strict: float
    leaky: float
    no_call: float
    max_prompt_tokens: int
    context_stops: int
    prompt_cap: int


def probe_verdict(
    records: _Sequence[_cal.EpisodeRecord],
    tally: _Mapping[str, int] | None,
    *,
    max_prompt_tokens: int,
    context_stops: int,
    prompt_cap: int,
    floor_arms: _Sequence[str] | None = None,
) -> ProbeVerdict:
    """Whether phase 3 may start.  Pooled over the probe's episodes, because the question is
    whether the model can do the hardest levels at all, not a level's number.  With
    `floor_arms`, strict and leaky (and so the floor) are read on those arms' episodes only;
    instrument failures and the no-call share are read on every episode."""
    reasons: list[str] = []
    kept = _cal.scored(records)
    labelled = len(records) - len(kept)
    failures = max(labelled, sum((tally or {}).values()))
    if not records:
        reasons.append("the probe recorded no episode")
    if failures:
        reasons.append(f"{failures} instrument failure(s): the plumbing is not clean")
    floor_kept = kept if floor_arms is None else [r for r in kept if r.arm_id in floor_arms]
    strict = sum(1 for r in floor_kept if r.strict) / len(floor_kept) if floor_kept else 0.0
    leaky = sum(1 for r in floor_kept if r.leaky) / len(floor_kept) if floor_kept else 0.0
    no_call = sum(1 for r in kept if r.sampled_calls == 0) / len(kept) if kept else 0.0
    if floor_kept and leaky <= FLOOR:
        reasons.append(
            f"floor: leaky pass@1 {leaky:.3f} on the hardest levels is at or below {FLOOR}; "
            "the model cannot do them, so the depth axis would be saturated low"
        )
    if no_call > _cal.NO_CALL_THRESHOLD:
        reasons.append(
            f"{no_call:.3f} of the probe's episodes made no tool call, above the card's "
            f"no-call threshold of {_cal.NO_CALL_THRESHOLD}: every cell like it would refuse "
            "to publish"
        )
    if context_stops:
        reasons.append(
            f"{context_stops} episode(s) ended at the context cap: raise --max-model-len "
            "before the card, or every episode the cap ends counts as an instrument failure "
            "and the card refuses"
        )
    if max_prompt_tokens > HEADROOM * prompt_cap:
        reasons.append(
            f"a prompt reached {max_prompt_tokens} tokens, past {HEADROOM:.0%} of the "
            f"{prompt_cap} the context cap leaves: raise --max-model-len before the card"
        )
    return ProbeVerdict(
        proceed=not reasons, reasons=tuple(reasons), episodes=len(records), scored=len(kept),
        strict=strict, leaky=leaky, no_call=no_call, max_prompt_tokens=max_prompt_tokens,
        context_stops=context_stops, prompt_cap=prompt_cap,
    )


def trace_facts(run_dir: _pathlib.Path) -> dict[str, int]:
    """What the per-episode records do not carry: the largest single prompt (cached tokens
    included) and how many episodes the context cap ended."""
    out = {"episodes": 0, "max_prompt_tokens": 0, "context_stops": 0}
    path = _pathlib.Path(run_dir) / _cal.TRACES_FILE
    if not path.exists():
        return out
    for line in complete_lines(path.read_bytes()).splitlines():
        if not line.strip():
            continue
        row = _json.loads(line)
        out["episodes"] += 1
        for trace in row.get("traces") or []:
            if trace.get("stop_condition") == "context_length":
                out["context_stops"] += 1
            for call in trace.get("calls") or []:
                usage = call.get("usage") or {}
                tokens = int(usage.get("prompt_tokens") or 0) + int(
                    usage.get("cached_input_tokens") or 0
                )
                out["max_prompt_tokens"] = max(out["max_prompt_tokens"], tokens)
    return out


# ---------------------------------------------------------------------------
# running a phase
# ---------------------------------------------------------------------------

KEY_VAR = "POISSON_TASKS_LOCAL_SERVER_KEY"
"""vLLM here runs without `--api-key`; the wheel still reads a key from some variable."""


@_dc.dataclass
class Context:
    local: _pathlib.Path
    durable: _pathlib.Path
    port: int
    mirror_interval: float
    pin: ServePin = QWEN3_8B

    @property
    def base_url(self) -> str:
        return self.pin.base_url(self.port)

    def client(self) -> _Any:
        import verifiers.v1 as _vf

        _os.environ.setdefault(KEY_VAR, "EMPTY")
        return _vf.EvalClientConfig(base_url=self.base_url, api_key_var=KEY_VAR)


def _read_json(path: _pathlib.Path) -> _Any:
    return _json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _write_json(path: _pathlib.Path, value: _Any) -> None:
    _atomic_write(path, (_json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def _say(message: str) -> None:
    print(message, flush=True)


DROPPED_ENV = ("UV_SYSTEM_PYTHON",)
"""Variables the driver removes from its own environment before anything runs, so no episode
inherits them.  Colab's runtime sets `UV_SYSTEM_PYTHON`, which uv reads as `--system`.  The
`null` harness prepares its program with `uv python find --script`, which uv 0.11.14 refuses
with `--system`, so every episode failed in harness setup before reaching the model.  None of
these decides anything about the model, the server or the decoding."""


def _drop_env() -> None:
    for name in DROPPED_ENV:
        if _os.environ.pop(name, None) is not None:
            _say(f"{name} removed from the driver's environment (it breaks the harness's setup)")


def first_episode_error(run_dir: _pathlib.Path) -> str | None:
    """The first error an episode in `run_dir` carries, as `type: message`, from the wheel's
    `traces.jsonl`; `None` when no episode carries one."""
    path = _pathlib.Path(run_dir) / _cal.TRACES_FILE
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = _json.loads(line)
        except ValueError:
            continue
        found = _first_error_in(row)
        if found is not None:
            return found
    return None


def _first_error_in(node: _Any) -> str | None:
    """Depth first: an `errors` list with a message, on the episode or on any of its traces
    (a failed model call or harness setup lands on the trace, not the episode)."""
    if isinstance(node, dict):
        for error in node.get("errors") or []:
            if isinstance(error, dict) and error.get("message"):
                kind = error.get("type")
                message = str(error["message"])[:1500]
                return f"{kind}: {message}" if kind else message
        for value in node.values():
            found = _first_error_in(value)
            if found is not None:
                return found
    elif isinstance(node, list):
        for value in node:
            found = _first_error_in(value)
            if found is not None:
                return found
    return None


def _arm_rows(
    run_dir: _pathlib.Path, arm: str, served: str
) -> tuple[list[_cal.EpisodeRecord], dict[str, int], dict[str, int]]:
    if not (run_dir / _cal.TRACES_FILE).exists():
        return [], {}, trace_facts(run_dir)
    return (
        _cal.records_from_run(run_dir, model=served),
        _cal.read_tally(run_dir),
        trace_facts(run_dir),
    )


def _run_arms(
    ctx: Context,
    phase: str,
    arms: _Sequence[str],
    *,
    budget_for: _Callable[[str], _Mapping[str, _Any]],
    after_arm: _Callable[[str, _Any, float], None] | None = None,
) -> str | None:
    """Each arm through `run_arm`, in order, resuming whatever is on disk.  Returns the stop
    reason if a limit stopped the phase."""
    for arm in arms:
        started = _time.monotonic()
        _say(f"[{phase}] {arm}: starting")
        outcome = _cal.run_arm(
            spec_for(arm), output_dir=ctx.local / phase, model=ctx.pin.served_name,
            client=ctx.client(), budget=budget_for(arm),
        )
        elapsed = _time.monotonic() - started
        _say(
            f"[{phase}] {arm}: {outcome.episodes_kept} kept, {outcome.episodes_run} run, "
            f"{outcome.episodes_owed} owed, {elapsed:.0f} s"
            + (f", stopped: {outcome.stop.reason}" if outcome.stop is not None else "")
        )
        if after_arm is not None:
            after_arm(arm, outcome, elapsed)
        if outcome.stop is not None:
            return str(outcome.stop.reason)
    return None


def _serving(ctx: Context) -> dict[str, _Any]:
    serving = _read_json(ctx.local / "serving.json")
    if not isinstance(serving, dict):
        raise ServingMismatch("no serving.json: run the preflight step on this runtime first")
    facts = check_server(ctx.pin, ctx.base_url)
    if facts["stack_version"] != serving["stack_version"]:
        raise ServingMismatch(
            f"the server is {facts['stack_version']}, preflight recorded {serving['stack_version']}"
        )
    return serving


@_contextlib.contextmanager
def _session(ctx: Context) -> _Iterator[Mirror]:
    """Restore from the durable folder, take the lock, mirror while the body runs."""
    mirror = Mirror(ctx.local, ctx.durable)
    ctx.local.mkdir(parents=True, exist_ok=True)
    restored = mirror.restore()
    if restored:
        _say(f"restored {restored} file(s) from {ctx.durable}")
    lock = RunLock(ctx.durable)
    lock.acquire()
    try:
        with mirroring(mirror, ctx.mirror_interval, lock):
            yield mirror
    finally:
        lock.release()


def _phase_summary(
    records: _Sequence[_cal.EpisodeRecord], facts: _Mapping[str, _Mapping[str, int]]
) -> dict[str, _Any]:
    return {
        "episodes": len(records),
        "scored": len(_cal.scored(records)),
        "labels": dict(sorted(_Counter(r.label for r in records).items())),
        "strict_passes": sum(1 for r in records if r.strict),
        "leaky_passes": sum(1 for r in records if r.leaky),
        "tool_calls": sum(r.sampled_calls for r in records),
        "model_calls": sum(r.turns for r in records),
        "prompt_tokens": sum(r.prompt_tokens for r in records),
        "cached_input_tokens": sum(r.cached_input_tokens for r in records),
        "completion_tokens": sum(r.completion_tokens for r in records),
        "max_prompt_tokens": max((f["max_prompt_tokens"] for f in facts.values()), default=0),
        "context_stops": sum(f["context_stops"] for f in facts.values()),
    }


def cmd_phase1(ctx: Context) -> int:
    report_path = ctx.local / "phase1.json"
    with _session(ctx):
        existing = _read_json(report_path)
        if isinstance(existing, dict):
            _say(f"phase 1 already ran: passed={existing['passed']}")
            return 0 if existing["passed"] else 2
        _serving(ctx)
        started = _time.monotonic()
        with design(PHASE1_DESIGN):
            stop = _run_arms(ctx, "phase1", PHASE1_ARMS, budget_for=lambda _: _cal.DEFAULT_BUDGET)
            records: list[_cal.EpisodeRecord] = []
            tally: dict[str, int] = {}
            facts: dict[str, dict[str, int]] = {}
            for arm in PHASE1_ARMS:
                rows, arm_tally, facts[arm] = _arm_rows(
                    ctx.local / "phase1" / _arm_dir(arm), arm, ctx.pin.served_name
                )
                records += rows
                for label, count in arm_tally.items():
                    tally[label] = tally.get(label, 0) + count
            verdict = _cal.plumbing_gate(records, tally)
            first_error = next(
                (found for arm in PHASE1_ARMS
                 if (found := first_episode_error(ctx.local / "phase1" / _arm_dir(arm)))),
                None,
            )
        passed = verdict.passed and stop is None
        report = {
            "phase": 1, "model": ctx.pin.served_name, "arms": list(PHASE1_ARMS),
            "seeds": list(PHASE1_DESIGN.seeds), "n": PHASE1_DESIGN.n, "passed": passed,
            "reasons": list(verdict.reasons) + ([f"stopped: {stop}"] if stop else []),
            "no_call": verdict.no_call, "reached_minimum": verdict.reached_minimum,
            "per_episode": list(verdict.per_episode), "tally": tally,
            "elapsed_seconds": round(_time.monotonic() - started, 1),
            "first_error": first_error,
            **_phase_summary(records, facts),
        }
        _write_json(report_path, report)
        _say(_json.dumps({k: report[k] for k in ("passed", "reasons", "episodes", "scored",
                                                    "tool_calls", "max_prompt_tokens")}))
        if first_error is not None:
            _say(f"first episode error: {first_error}")
        return 0 if passed else 2


def cmd_probe(ctx: Context) -> int:
    report_path = ctx.local / "probe.json"
    with _session(ctx):
        phase1 = _read_json(ctx.local / "phase1.json")
        if not (isinstance(phase1, dict) and phase1.get("passed")):
            _say("STOP: phase 1 has not passed its gate; the probe does not run")
            return 2
        existing = _read_json(report_path)
        if isinstance(existing, dict):
            _say(f"the probe already ran: proceed={existing['proceed']}")
            return 0 if existing["proceed"] else 3
        _serving(ctx)
        started = _time.monotonic()
        with design(PROBE_DESIGN):
            probe_arms = (*PROBE_ARMS, *PROBE_CONTEXT_ARMS)
            stop = _run_arms(ctx, "probe", probe_arms, budget_for=lambda _: _cal.DEFAULT_BUDGET)
            records: list[_cal.EpisodeRecord] = []
            tally: dict[str, int] = {}
            facts: dict[str, dict[str, int]] = {}
            per_arm: dict[str, _Any] = {}
            for arm in probe_arms:
                rows, arm_tally, facts[arm] = _arm_rows(
                    ctx.local / "probe" / _arm_dir(arm), arm, ctx.pin.served_name
                )
                records += rows
                for label, count in arm_tally.items():
                    tally[label] = tally.get(label, 0) + count
                kept = _cal.scored(rows)
                per_arm[arm] = {
                    "episodes": len(rows), "scored": len(kept),
                    "strict": sum(1 for r in kept if r.strict) / len(kept) if kept else None,
                    "leaky": sum(1 for r in kept if r.leaky) / len(kept) if kept else None,
                    "labels": dict(_Counter(r.label for r in rows)), **facts[arm],
                }
        cap = ctx.pin.max_model_len - int(_cal.DECODING["max_tokens"])
        verdict = probe_verdict(
            records, tally,
            max_prompt_tokens=max((f["max_prompt_tokens"] for f in facts.values()), default=0),
            context_stops=sum(f["context_stops"] for f in facts.values()),
            prompt_cap=cap, floor_arms=PROBE_ARMS,
        )
        reasons = list(verdict.reasons) + ([f"stopped: {stop}"] if stop else [])
        proceed = verdict.proceed and stop is None
        report = {
            "phase": "probe", "model": ctx.pin.served_name, "arms": list(probe_arms),
            "floor_arms": list(PROBE_ARMS),
            "seeds": list(PROBE_DESIGN.seeds), "n": PROBE_DESIGN.n, "proceed": proceed,
            "reasons": reasons, "floor": FLOOR, "headroom": HEADROOM,
            "strict": verdict.strict, "leaky": verdict.leaky, "no_call": verdict.no_call,
            "prompt_cap": cap, "per_arm": per_arm, "tally": tally,
            "elapsed_seconds": round(_time.monotonic() - started, 1),
            **_phase_summary(records, facts),
        }
        _write_json(report_path, report)
        _say(_json.dumps({k: report[k] for k in ("proceed", "reasons", "strict", "leaky",
                                                    "no_call", "max_prompt_tokens")}))
        if not proceed:
            _say("STOP: the probe says the card should not run on this model.  Report it; a "
                 "step up to a larger model (Qwen3-14B) is a separate run, decided on its own, "
                 "never an automatic switch.")
        return 0 if proceed else 3


def cmd_phase3(ctx: Context, wall_clock_hours: float) -> int:
    report_path = ctx.local / "phase3.json"
    with _session(ctx):
        probe = _read_json(ctx.local / "probe.json")
        if not (isinstance(probe, dict) and probe.get("proceed")):
            _say("STOP: the probe has not cleared phase 3; the card does not run")
            return 3
        existing = _read_json(report_path)
        if isinstance(existing, dict) and existing.get("status") in ("complete", "refused"):
            _say(f"phase 3 already finished: {existing['status']}")
            return 0 if existing["status"] == "complete" else 5
        serving = _serving(ctx)
        status_path = ctx.local / "status.json"
        status = _read_json(status_path) or {}
        p3 = status.setdefault("phase3", {"arms": {}, "elapsed_s": 0.0})
        total_s = wall_clock_hours * 3600.0
        arms = _card_arms()

        def budget_for(_arm: str) -> dict[str, _Any]:
            remaining = max(0.0, total_s - float(p3["elapsed_s"]))
            return {"tokens": _cal.DEFAULT_BUDGET["tokens"], "wall_clock_seconds": remaining}

        def after_arm(arm: str, outcome: _Any, elapsed: float) -> None:
            p3["elapsed_s"] = float(p3["elapsed_s"]) + elapsed
            prior = p3["arms"].get(arm, {})
            p3["arms"][arm] = {
                "episodes_kept": outcome.episodes_kept,
                "episodes_run": int(prior.get("episodes_run", 0)) + outcome.episodes_run,
                "episodes_owed": outcome.episodes_owed,
                "elapsed_s": float(prior.get("elapsed_s", 0.0)) + elapsed,
                "stop": None if outcome.stop is None else outcome.stop.reason,
            }
            done = [a for a in arms if p3["arms"].get(a, {}).get("episodes_owed") == 0
                    and p3["arms"].get(a, {}).get("stop") is None]
            per_arm = p3["elapsed_s"] / max(1, len(done))
            p3["projected_remaining_s"] = per_arm * (len(arms) - len(done))
            _write_json(status_path, status)
            _say(f"[phase3] {len(done)} of {len(arms)} arms done, {p3['elapsed_s'] / 3600:.2f} h "
                 f"used of {wall_clock_hours:.2f} h; about "
                 f"{p3['projected_remaining_s'] / 3600:.2f} h to go at this rate")

        with design(CARD_DESIGN):
            stop = _run_arms(ctx, "phase3", arms, budget_for=budget_for, after_arm=after_arm)
            complete = stop is None and all(
                p3["arms"].get(a, {}).get("episodes_owed") == 0 for a in arms
            )
            result = finalize(
                ctx.local, ctx.local / "card", serving=serving, arms=arms,
                wall_clock_hours=wall_clock_hours, served=ctx.pin.served_name,
                port=ctx.port, pin=ctx.pin,
            )
        state = "complete" if complete else "stopped"
        if complete and result["cal24"] == "refused":
            state = "refused"
        report = {
            "phase": 3, "model": ctx.pin.served_name, "status": state, "stop": stop,
            "wall_clock_hours": wall_clock_hours, "elapsed_s": p3["elapsed_s"],
            "arms": p3["arms"], **result,
        }
        _write_json(report_path, report)
        _say(f"phase 3 {state}" + (f" (stop: {stop})" if stop else "")
             + f"; card: {result['card']}; {card_status(result)}")
        return {"complete": 0, "stopped": 4, "refused": 5}[state]


def card_status(result: _Mapping[str, _Any]) -> str:
    """How `finalize` left the card, in words.  `result["cal24"]` is the historical name of
    the field: it says published or refused whichever rule refused (the instrument-rate gate
    or the no-call share), and `result["refusal"]` carries the rule's own sentence."""
    if result.get("cal24") == "refused":
        return f"refused: {result.get('refusal', 'no reason recorded')}"
    return str(result.get("cal24"))


# ---------------------------------------------------------------------------
# the card, the bundle and its verification
# ---------------------------------------------------------------------------


def finalize(
    root: _pathlib.Path,
    out: _pathlib.Path,
    *,
    serving: _Mapping[str, _Any],
    arms: _Sequence[str],
    wall_clock_hours: float | None,
    served: str,
    port: int | None = None,
    pin: ServePin = QWEN3_8B,
) -> dict[str, _Any]:
    """The artifact, the document, the records and the tallies from the phase 3 run
    directories under `root`.  A cell with no scored episode is left out and named; a card
    that CAL16 or CAL24 refuses is written under a REFUSED banner, as model A's first card
    was, with the refusal in the report."""
    cells: dict[tuple[str, str], list[_cal.EpisodeRecord]] = {}
    tallies: dict[str, dict[str, int]] = {}
    facts: dict[str, dict[str, int]] = {}
    empty: list[str] = []
    for arm in arms:
        rows, tally, facts[arm] = _arm_rows(root / "phase3" / _arm_dir(arm), arm, served)
        tallies[arm] = tally
        if _cal.scored(rows):
            cells[(arm, served)] = rows
        else:
            empty.append(arm)
    out.mkdir(parents=True, exist_ok=True)
    records = [row for cell in cells.values() for row in cell]
    _cal.write_records(records, out / "episodes.jsonl")
    _write_json(out / "tallies.json", tallies)
    result: dict[str, _Any] = {
        "cells": len(cells), "empty_arms": empty, "records": len(records),
        "per_arm_facts": facts, **_phase_summary(records, facts),
    }
    if not cells:
        result.update(card=None, cal24="no cells")
        return result
    budget = dict(_cal.DEFAULT_BUDGET)
    if wall_clock_hours is not None:
        budget["wall_clock_seconds"] = wall_clock_hours * 3600.0

    def provenance(
        no_call: float = _cal.NO_CALL_THRESHOLD, instrument: float = _cal.INSTRUMENT_THRESHOLD
    ) -> _cal.Provenance:
        return _cal.Provenance.for_run(
            models=[pin.model_entry(port)],
            serving={served: pin.serving_entry(
                stack_version=str(serving["stack_version"]), gpu_name=str(serving["gpu"]),
            )},
            rate_read_date=str(serving.get("date", _now()[:10])),
            budget=budget, no_call_threshold=no_call, instrument_threshold=instrument,
            max_model_calls=CARD_MAX_MODEL_CALLS,
        )

    keyed = {(arm, served): tally for arm, tally in tallies.items() if (arm, served) in cells}
    try:
        artifact = _cal.build_artifact(cells, provenance(), tally=keyed)
        document = _cal.render_document(artifact)
        result["cal24"] = "published"
    except ValueError as error:
        artifact = _cal.build_artifact(
            cells, provenance(no_call=1.0, instrument=1.0), tally=keyed
        )
        document = (
            f"> **REFUSED**: this card does not publish, because {error}.  The figures below "
            "are rendered with the no-call and instrument thresholds relaxed so the refusal "
            "can be read; they are not a card.\n\n" + _cal.render_document(artifact)
        )
        result["cal24"] = "refused"
        result["refusal"] = str(error)
    _cal.write_artifact(artifact, out / "artifact.json")
    (out / "card.md").write_text(document, encoding="utf-8")
    (out / "readme-lines.md").write_text(_cal.render_readme_lines(artifact), encoding="utf-8")
    result["card"] = str(out / "card.md")
    return result


BUNDLE_FILES = (
    "card/card.md", "card/artifact.json", "card/episodes.jsonl", "card/tallies.json",
    "card/readme-lines.md", "phase1.json", "probe.json", "phase3.json", "serving.json",
    MANIFEST_FILE, "status.json", "vllm.log",
)
BUNDLE_GLOBS = ("phase1/*/traces.jsonl", "phase1/*/instrument-tally.jsonl",
                "probe/*/traces.jsonl", "probe/*/instrument-tally.jsonl")
BUNDLE_ZIP = "calibration-model-b-bundle.zip"
MANIFEST = "MANIFEST.sha256"


def make_bundle(durable: _pathlib.Path) -> _pathlib.Path:
    """The run's card, reports and logs, flattened out of `card/`, with a sha256 manifest, zipped.
    Phase 3's raw traces are not in it; they stay in the durable folder."""
    durable = _pathlib.Path(durable)
    staging = durable / "bundle"
    if staging.exists():
        _shutil.rmtree(staging)
    staging.mkdir(parents=True)
    names: list[str] = []
    sources = [durable / name for name in BUNDLE_FILES]
    for pattern in BUNDLE_GLOBS:
        sources += sorted(durable.glob(pattern))
    for source in sources:
        if not source.is_file():
            continue
        rel = source.relative_to(durable)
        name = str(rel.relative_to("card")) if rel.parts[0] == "card" else str(rel)
        target = staging / name
        target.parent.mkdir(parents=True, exist_ok=True)
        _shutil.copyfile(source, target)
        names.append(name)
    lines = [
        f"{_hashlib.sha256((staging / name).read_bytes()).hexdigest()}  {name}"
        for name in sorted(names)
    ]
    (staging / MANIFEST).write_text("\n".join(lines) + "\n", encoding="utf-8")
    archive = durable / BUNDLE_ZIP
    with _zipfile.ZipFile(archive, "w", compression=_zipfile.ZIP_DEFLATED) as handle:
        for name in sorted([*names, MANIFEST]):
            handle.write(staging / name, arcname=name)
    return archive


def _first_mismatch(stored: _Any, rebuilt: _Any, where: str) -> str | None:
    """Where the stored artifact and the rebuilt one first disagree, or `None`.  Every value
    the stored artifact carries is checked; a figure the card gained after it was written
    is not.  Lists compare whole, so a missing cell or row is a mismatch."""
    if isinstance(stored, dict):
        if not isinstance(rebuilt, dict):
            return f"{where} is not a mapping in the rebuild"
        for key in sorted(stored):
            if key not in rebuilt:
                return f"{where}.{key} is not in the rebuild"
            found = _first_mismatch(stored[key], rebuilt[key], f"{where}.{key}")
            if found is not None:
                return found
        return None
    if isinstance(stored, list):
        if not isinstance(rebuilt, list) or len(stored) != len(rebuilt):
            return f"{where} has {len(stored)} entries and the rebuild a different number"
        for index, (mine, theirs) in enumerate(zip(stored, rebuilt, strict=True)):
            found = _first_mismatch(mine, theirs, f"{where}[{index}]")
            if found is not None:
                return found
        return None
    return None if stored == rebuilt else f"{where} is {stored!r}; it recomputes to {rebuilt!r}"


def verify_bundle(path: _pathlib.Path, *, recompute: bool = True) -> dict[str, _Any]:
    """Every file in the manifest has its digest, and (when the bundle carries a card) every
    figure the artifact carries recomputes from `episodes.jsonl` and `tallies.json` under its
    own provenance (CAL19).  A bundle written before the card gained a figure still verifies
    on the figures it has.  Refuses otherwise."""
    root = _pathlib.Path(path)
    lines = (root / MANIFEST).read_text(encoding="utf-8").splitlines()
    checked = 0
    for line in lines:
        if not line.strip():
            continue
        digest, name = line.split("  ", 1)
        got = _hashlib.sha256((root / name).read_bytes()).hexdigest()
        if got != digest:
            raise ValueError(f"{name}: sha256 {got}, the manifest says {digest}")
        checked += 1
    out: dict[str, _Any] = {"files": checked, "recomputed": False}
    if recompute and (root / "artifact.json").exists():
        stored = _json.loads((root / "artifact.json").read_text(encoding="utf-8"))
        prov = _cal.Provenance(**stored["provenance"])
        records = _cal.read_records(root / "episodes.jsonl")
        cells: dict[tuple[str, str], list[_cal.EpisodeRecord]] = {}
        for row in records:
            cells.setdefault((row.arm_id, row.model), []).append(row)
        tallies = _json.loads((root / "tallies.json").read_text(encoding="utf-8"))
        keyed = {key: tallies.get(key[0], {}) for key in cells}
        rebuilt = _json.loads(_json.dumps(_cal.build_artifact(cells, prov, tally=keyed).as_dict()))
        mismatch = _first_mismatch(stored, rebuilt, "artifact")
        if mismatch is not None:
            raise ValueError(f"artifact.json does not recompute from episodes.jsonl: {mismatch}")
        out["recomputed"] = True
    return out


def _refuse(sentence: str) -> int:
    """A refusal: one line on stderr, and exit 1."""
    print(f"error: {sentence}", file=_sys.stderr, flush=True)
    return 1


def cmd_verify(bundle: _pathlib.Path, into: _pathlib.Path | None) -> int:
    what = "a bundle is the .zip `bundle` writes, or the folder it unzips to"
    with _tempfile.TemporaryDirectory() as scratch:
        root = _pathlib.Path(bundle)
        if not root.exists():
            return _refuse(f"{bundle}: no such bundle ({what})")
        if root.is_file() and not _zipfile.is_zipfile(root):
            return _refuse(f"{bundle} is not a bundle: it is not a .zip archive ({what})")
        if root.is_file():
            with _zipfile.ZipFile(root) as handle:
                for member in handle.namelist():
                    target = (_pathlib.Path(scratch) / member).resolve()
                    if not str(target).startswith(str(_pathlib.Path(scratch).resolve())):
                        raise ValueError(f"unsafe path in the bundle: {member}")
                handle.extractall(scratch)
            root = _pathlib.Path(scratch)
        if not (root / MANIFEST).is_file():
            return _refuse(f"{bundle} is not a bundle: it holds no {MANIFEST} ({what})")
        result = verify_bundle(root)
        _say(f"{result['files']} files match the manifest"
             + ("; every number in artifact.json recomputes from episodes.jsonl"
                if result["recomputed"] else ""))
        if into is not None:
            names = [line.split("  ", 1)[1] for line in
                     (root / MANIFEST).read_text(encoding="utf-8").splitlines() if line.strip()]
            for name in [*names, MANIFEST]:
                target = _pathlib.Path(into) / name
                source = root / name
                if target.exists() and target.read_bytes() != source.read_bytes():
                    raise ValueError(f"{target} exists and differs; not overwritten")
                target.parent.mkdir(parents=True, exist_ok=True)
                _shutil.copyfile(source, target)
            _say(f"copied {len(names) + 1} files into {into}")
    return 0


# ---------------------------------------------------------------------------
# install, serve, preflight
# ---------------------------------------------------------------------------


INSTALL_RECORD = "poisson-install.json"
"""What `install-vllm` writes into the virtualenv as its last act, naming the pinned wheel it
installed.  A virtualenv without it, or with another pin's, is an install that did not
finish, however much of it is there, and is built again from nothing."""

_VENV_ENTRIES = frozenset({
    "bin", "lib", "lib64", "include", "share", "pyvenv.cfg", ".gitignore", "CACHEDIR.TAG",
    ".lock", INSTALL_RECORD,
})
"""What uv puts in a virtualenv: all an unfinished one can hold, even before its
`pyvenv.cfg` is written."""


def _install_record(pin: ServePin) -> dict[str, _Any]:
    return {"vllm_wheel": pin.vllm_wheel_name, "vllm_wheel_sha256": pin.vllm_wheel_sha256,
            "torch_backend": pin.torch_backend, "python": pin.python}


def _installed(venv: _pathlib.Path, pin: ServePin) -> bool:
    try:
        return bool(_read_json(venv / INSTALL_RECORD) == _install_record(pin))
    except (OSError, ValueError):
        return False


def _clear_unfinished(venv: _pathlib.Path) -> None:
    """Remove an install that did not finish, so it is built again from nothing.  Only a
    virtualenv (it has `pyvenv.cfg`), or a directory holding nothing but what uv puts in one,
    is removed.  Anything else at that path is not this step's: the step stops and leaves it
    alone."""
    if not _os.path.lexists(venv):
        return
    if venv.is_dir() and not venv.is_symlink():
        names = {entry.name for entry in venv.iterdir()}
        if "pyvenv.cfg" in names or names <= _VENV_ENTRIES:
            _say(f"{venv} holds an install that did not finish: removing it to build it again")
            _shutil.rmtree(venv)
            return
    raise StepFailed(f"{venv} exists and is not a virtualenv this step made; move it away "
                     "or pass another --venv")


def _fetch_wheel(pin: ServePin, wheel: _pathlib.Path) -> None:
    """The release's wheel at `wheel`, checked against its pinned sha256.  A copy already
    there is kept if it checks.  A download goes to a `.part` file and is renamed into place
    only once it checks, so a download cut off part way is never taken for the wheel."""
    if wheel.exists() and _sha256_file(wheel) == pin.vllm_wheel_sha256:
        _say(f"the pinned wheel is already here, its sha256 checked: {wheel}")
        return
    _say(f"$ download {pin.vllm_wheel_url} to {wheel}")
    partial = wheel.with_name(wheel.name + ".part")
    try:
        with _urlrequest.urlopen(pin.vllm_wheel_url, timeout=60) as response, \
                partial.open("wb") as handle:
            _shutil.copyfileobj(response, handle, length=1 << 20)
    except OSError as error:
        raise StepFailed(f"the download of {pin.vllm_wheel_url} failed: {error}") from error
    got = _sha256_file(partial)
    if got != pin.vllm_wheel_sha256:
        partial.unlink()
        raise ServingMismatch(f"the downloaded wheel's sha256 is {got}, not the pinned "
                              f"{pin.vllm_wheel_sha256}")
    _os.replace(partial, wheel)


def cmd_install_vllm(venv: _pathlib.Path, *, dry_run: bool, pin: ServePin = QWEN3_8B) -> int:
    """The pinned vLLM in a virtualenv of its own, so its pins cannot collide with the
    wheel's or the notebook's (spec 2.5): the release's wheel, checked against its sha256
    before it is installed, with the PyTorch build for the same CUDA.

    Run again, it keeps a finished install and never repeats it; the check still runs, and
    stops with its own output if the runtime cannot use the stack.  A virtualenv the install
    did not finish (`INSTALL_RECORD` missing, or another pin's) is removed and built again
    from nothing: uv 0.11.14 exits 2 rather than create a virtualenv over an existing one,
    and nothing half installed is trusted."""
    venv = _pathlib.Path(venv)
    python = venv / "bin" / "python"
    wheel = venv.parent / pin.vllm_wheel_name
    create = ["uv", "venv", "--python", pin.python, str(venv)]
    install = ["uv", "pip", "install", "--python", str(python), str(wheel),
               "--torch-backend", pin.torch_backend]
    check = [str(python), "-c", "import vllm, torch; print(vllm.__version__, torch.__version__, "
             "torch.version.cuda, torch.cuda.is_available())"]
    if dry_run:
        download = ["download", pin.vllm_wheel_url, str(wheel), f"sha256 {pin.vllm_wheel_sha256}",
                    f"{pin.vllm_wheel_size} bytes"]
        for step in (create, download, install, check):
            _say("$ " + " ".join(step))
        return 0
    if _installed(venv, pin):
        _say(f"the pinned vLLM is installed in {venv}, and a finished install is not repeated "
             f"(delete {venv} to force one)")
    else:
        _clear_unfinished(venv)
        _run(["uv", "--version"])
        _run(create)
        _fetch_wheel(pin, wheel)
        _run(install)
        _write_json(venv / INSTALL_RECORD, _install_record(pin))
    found = _output(check).strip()
    _say(found)
    fields = found.split()
    if not fields or not fields[0].startswith(pin.vllm_version) or fields[-1] != "True":
        raise ServingMismatch(f"the installed stack is not usable: {found}")
    return 0


def _sha256_file(path: _pathlib.Path) -> str:
    digest = _hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _stock_template(vllm: str, tokenizer_config: _pathlib.Path | None, pin: ServePin) -> str:
    """The pinned revision's chat template, from the given file or from the Hub through the
    vLLM environment's own `huggingface_hub`."""
    if tokenizer_config is None:
        python = _pathlib.Path(vllm).parent / "python"
        code = (
            "from huggingface_hub import hf_hub_download; "
            f"print(hf_hub_download({pin.model!r}, 'tokenizer_config.json', "
            f"revision={pin.revision!r}))"
        )
        found = _output([str(python), "-c", code], timeout=600)
        tokenizer_config = _pathlib.Path(found.strip().splitlines()[-1])
    data = _json.loads(tokenizer_config.read_text(encoding="utf-8"))
    template: str = data["chat_template"]
    return template


_EXCEPTION_LINE = _re.compile(r"\b([A-Za-z_][\w.]*(?:Error|Exception|Exit)\b(?::.*)?)$")
_ENGINE_ERROR = _re.compile(r"^\(EngineCore[^)]*\) ERROR ")

KNOWN_CAUSES: tuple[tuple[str, str], ...] = (
    ("No such file or directory: 'ninja'",
     "FlashInfer compiled a kernel at startup and found no `ninja`.  The pin turns FlashInfer's "
     "sampler off with VLLM_USE_FLASHINFER_SAMPLER=0; if this start did not have it, the "
     "server was not started by this driver's pinned stack."),
    ("CUDA out of memory",
     "the GPU ran out of memory: another process may hold it (nvidia-smi), or the runtime is "
     "not the pinned GPU."),
)
"""Causes seen on a real runtime, each with what to do about it."""


def engine_error(log: str) -> str | None:
    """The exception a failed vLLM start died of, from its log: the engine process's own, when
    it logged one, since the API server's traceback only says "see root cause above"; else the
    last exception line in the log; else `None`."""
    engine: str | None = None
    last: str | None = None
    for line in log.splitlines():
        found = _EXCEPTION_LINE.search(line.rstrip())
        if found is None or line.lstrip().startswith(("File ", "raise ")):
            continue
        if _ENGINE_ERROR.match(line) and ":" in found.group(1) and engine is None:
            engine = found.group(1)
        last = found.group(1)
    return engine if engine is not None else last


def known_cause(error: str) -> str | None:
    """What to do about an engine error seen before, or `None`."""
    for marker, hint in KNOWN_CAUSES:
        if marker in error:
            return hint
    return None


def _pid_alive(pid: int) -> bool:
    try:
        _os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def cmd_serve(
    ctx: Context, *, vllm: str, tokenizer_config: _pathlib.Path | None, timeout_s: float
) -> int:
    """Start the pinned server in the background, wait until it is healthy, check it.

    Run again while the server this runtime started is alive (an interrupted `serve` leaves
    vLLM loading in a session of its own), it starts no second server and waits for that
    one."""
    ctx.local.mkdir(parents=True, exist_ok=True)
    pid_file = ctx.local / "vllm.pid"
    if pid_file.exists() and _pid_alive(int(pid_file.read_text())):
        pid = int(pid_file.read_text())
        _say(f"a server this runtime started is running (pid {pid}): waiting until it is "
             "healthy")

        def alive() -> bool:
            return _pid_alive(pid)

        start = 0
    else:
        derived = no_think_template(_stock_template(vllm, tokenizer_config, ctx.pin), ctx.pin)
        template = ctx.local / "qwen3-8b-no-think.jinja"
        template.write_text(derived, encoding="utf-8")
        argv = [vllm, *ctx.pin.serve_args(str(template), port=ctx.port)]
        _say("$ " + " ".join([*(f"{n}={v}" for n, v in ctx.pin.env), *argv]))
        log_path = ctx.local / "vllm.log"
        start = log_path.stat().st_size if log_path.exists() else 0
        log = log_path.open("ab")
        proc = _subprocess.Popen(argv, stdout=log, stderr=_subprocess.STDOUT,
                                 env=ctx.pin.serve_env(_os.environ), start_new_session=True)
        pid = proc.pid
        pid_file.write_text(str(pid))

        def alive() -> bool:
            return proc.poll() is None
    try:
        waited = wait_healthy(ctx.base_url, timeout_s=timeout_s, alive=alive)
    except (RuntimeError, TimeoutError) as error:
        log_path = ctx.local / "vllm.log"
        this_start = ""
        if log_path.exists():
            with log_path.open("rb") as handle:
                handle.seek(start)
                this_start = handle.read().decode("utf-8", errors="replace")
        lines = [f"STOP: {error}"]
        cause = engine_error(this_start)
        if cause is not None:
            lines.append(f"the engine's error: {cause}")
            hint = known_cause(cause)
            if hint is not None:
                lines.append(hint)
        lines.append(f"--- vllm.log (this start, tail) ---\n{this_start[-3000:]}")
        _say("\n".join(lines))
        return 1
    _say(f"healthy after {waited:.0f} s (pid {pid})")
    facts = check_server(ctx.pin, ctx.base_url)
    _say(_json.dumps(facts))
    return 0


def cmd_stop_server(ctx: Context) -> int:
    """Stop the server this runtime started, by the PID it recorded, and nothing else."""
    pid_file = ctx.local / "vllm.pid"
    if not pid_file.exists():
        _say("no server was started from here")
        return 0
    pid = int(pid_file.read_text())
    if _pid_alive(pid):
        _os.kill(pid, _signal.SIGTERM)
        deadline = _time.monotonic() + 60
        while _pid_alive(pid) and _time.monotonic() < deadline:
            with _contextlib.suppress(ChildProcessError):
                _os.waitpid(pid, _os.WNOHANG)
            _time.sleep(0.5)
        if _pid_alive(pid):
            _os.kill(pid, _signal.SIGKILL)
    pid_file.unlink()
    _say(f"stopped pid {pid}")
    return 0


def cmd_preflight(ctx: Context) -> int:
    """The GPU is the pinned type, the server the pinned stack with thinking off, the
    package the generator this driver expects; the facts are recorded and a resume on
    anything else is refused."""
    gpu = gpu_facts()
    if gpu is None or ctx.pin.gpu not in gpu["name"].split():
        _say(f"STOP: the card is pinned to an {ctx.pin.gpu}; this runtime has "
             f"{gpu['name'] if gpu else 'no GPU nvidia-smi can see'}")
        return 1
    bundle = _generate(_cal.arm_specs()[0], _cal.seed_list()[0])
    if bundle.generator_hash != EXPECTED_GENERATOR_HASH:
        _say(f"STOP: this package's generator is {bundle.generator_hash}; this driver "
             f"expects {EXPECTED_GENERATOR_HASH}, and results from two generators cannot be "
             "read side by side")
        return 1
    server = check_server(ctx.pin, ctx.base_url)
    thinking = check_thinking_off(ctx.pin, ctx.base_url)
    facts = {
        "served_name": ctx.pin.served_name,
        "stack_version": server["stack_version"],
        "gpu": gpu["name"],
        "flags": ctx.pin.flags(),
        "template_sha256": ctx.pin.template_sha256,
        "generator_hash": bundle.generator_hash,
        "package_version": _metadata.version("poisson-tasks"),
        "verifiers_version": _metadata.version("verifiers"),
    }
    try:
        ctx.local.mkdir(parents=True, exist_ok=True)
        Mirror(ctx.local, ctx.durable).restore()
        check_run_manifest(ctx.durable, facts)
    except ServingMismatch as error:
        _say(f"STOP: {error}")
        return 1
    serving = {**facts, "driver": gpu["driver"], "date": _now()[:10], "checked": _now(),
               "thinking_check": thinking, "pin": _dc.asdict(ctx.pin)}
    _write_json(ctx.local / "serving.json", serving)
    Mirror(ctx.local, ctx.durable).push()
    _say(_json.dumps({k: serving[k] for k in ("served_name", "stack_version", "gpu", "driver")}))
    _say(f"thinking check: {thinking}")
    return 0


def cmd_status(ctx: Context) -> int:
    for name in ("serving.json", "phase1.json", "probe.json", "status.json", "phase3.json"):
        value = _read_json(ctx.durable / name)
        if value is None:
            _say(f"{name}: not yet")
            continue
        keys = ("passed", "proceed", "status", "stop", "reasons", "stack_version", "gpu",
                "elapsed_s", "projected_remaining_s", "cal24", "refusal")
        short = {k: v for k, v in value.items() if k in keys} if isinstance(value, dict) else value
        if name == "status.json" and isinstance(value, dict):
            short = {k: v for k, v in value.get("phase3", {}).items() if k != "arms"}
        _say(f"{name}: {_json.dumps(short)}")
    return 0


# ---------------------------------------------------------------------------
# the command line
# ---------------------------------------------------------------------------


def build_parser() -> _argparse.ArgumentParser:
    parser = _argparse.ArgumentParser(
        prog="python -m poisson_tasks.calibration_run",
        description="Model B's calibration card against a locally served model (see the "
        "module docstring).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def run_args(p: _argparse.ArgumentParser) -> None:
        p.add_argument("--local", type=_pathlib.Path, required=True,
                       help="the runtime's local working folder")
        p.add_argument("--durable", type=_pathlib.Path, required=True,
                       help="the folder that survives the runtime (Google Drive)")
        p.add_argument("--port", type=int, default=QWEN3_8B.port)
        p.add_argument("--mirror-interval", type=float, default=30.0,
                       help="seconds between pushes to the durable folder")

    p = sub.add_parser("install-vllm", help="install the pinned vLLM into its own virtualenv")
    p.add_argument("--venv", type=_pathlib.Path, required=True)
    p.add_argument("--dry-run", action="store_true")

    p = sub.add_parser("serve", help="start the pinned server and wait until it is healthy")
    run_args(p)
    p.add_argument("--vllm", default="vllm", help="the vllm executable")
    p.add_argument("--tokenizer-config", type=_pathlib.Path, default=None)
    p.add_argument("--timeout", type=float, default=1800.0)

    for name, text in (
        ("stop-server", "stop the server this runtime started, by its PID"),
        ("preflight", "check the GPU, the stack, thinking off and the generator"),
        ("phase1", "the plumbing pass, gated"),
        ("probe", "the hardest levels; stop if the model floors"),
        ("status", "what the durable folder holds"),
    ):
        run_args(sub.add_parser(name, help=text))

    p = sub.add_parser("phase3", help="the card: 14 arms x 60 seeds x 5 attempts, resumable")
    run_args(p)
    p.add_argument("--wall-clock-hours", type=float, required=True,
                   help="the compute allowance, in hours, across every resume; the run "
                        "stops cleanly at whichever of this, the token budget or the "
                        "provider's credit comes first")

    p = sub.add_parser("finalize", help="rebuild the card from a durable folder, no GPU")
    p.add_argument("--durable", type=_pathlib.Path, required=True)
    p.add_argument("--out", type=_pathlib.Path, required=True)
    p.add_argument("--port", type=int, default=QWEN3_8B.port)

    run_args(sub.add_parser(
        "bundle", help="zip the card, the reports and vLLM's log with a sha256 manifest, "
                       "for downloading and `verify`"))

    p = sub.add_parser("verify", help="check a bundle's manifest and recompute its artifact")
    p.add_argument("bundle", type=_pathlib.Path)
    p.add_argument("--into", type=_pathlib.Path, default=None)
    return parser


def main(argv: _Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(list(_sys.argv[1:] if argv is None else argv))
    _drop_env()
    try:
        if args.command == "install-vllm":
            return cmd_install_vllm(args.venv, dry_run=args.dry_run)
        if args.command == "verify":
            return cmd_verify(args.bundle, args.into)
        if args.command == "bundle":
            _say(str(make_bundle(args.durable)))
            return 0
        if args.command == "finalize":
            serving = _read_json(args.durable / "serving.json")
            if not isinstance(serving, dict):
                _say(f"STOP: no serving.json in {args.durable}")
                return 1
            status = _read_json(args.durable / "status.json") or {}
            result = finalize(
                args.durable, args.out, serving=serving, arms=_card_arms(),
                wall_clock_hours=None, served=QWEN3_8B.served_name, port=args.port,
            )
            _say(_json.dumps({k: result[k] for k in ("card", "cal24", "cells", "empty_arms")}))
            used = status.get("phase3", {}).get("elapsed_s")
            _say(f"phase 3 seconds used on the durable folder: {used}")
            return 0
        ctx = Context(local=args.local, durable=args.durable, port=args.port,
                      mirror_interval=args.mirror_interval)
        if args.command == "serve":
            return cmd_serve(ctx, vllm=args.vllm, tokenizer_config=args.tokenizer_config,
                             timeout_s=args.timeout)
        if args.command == "stop-server":
            return cmd_stop_server(ctx)
        if args.command == "preflight":
            return cmd_preflight(ctx)
        if args.command == "phase1":
            return cmd_phase1(ctx)
        if args.command == "probe":
            return cmd_probe(ctx)
        if args.command == "phase3":
            return cmd_phase3(ctx, args.wall_clock_hours)
        if args.command == "status":
            return cmd_status(ctx)
    except KeyboardInterrupt:
        _say("interrupted: everything finished is on the durable folder; run the same cell "
             "again to resume")
        return 130
    except (ServingMismatch, LockHeld, StepFailed) as error:
        _say(f"STOP: {error}")
        return 1
    raise AssertionError(args.command)


if __name__ == "__main__":
    _sys.exit(main())
