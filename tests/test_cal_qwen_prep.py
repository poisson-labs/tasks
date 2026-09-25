"""Model B's card, prepared: Qwen3-8B served by vLLM inside a Colab notebook.

Taylor's decisions of 2026-09-25: model B is Qwen3-8B with thinking off, served by vLLM on a
Colab L4 with his existing credits; the run probes the hardest levels first and stops if the
model floors there; phase 3 is model A's design (14 arms x 60 seeds x 5 attempts, through the
plumbing gate and CAL24); a dropped runtime must never lose a finished episode or run one
twice (R4, CAL23); and the card records the serving stack as R12 requires.

These tests pin the driver the notebook calls, `poisson_tasks.calibration_run`, with no GPU
and nothing off loopback:

* the serving pin (R12, N18): one 40-character revision through `--revision` and
  `--served-model-name`, the vLLM version, the flags, and the provenance block they fill
* thinking off: at vLLM 0.29.0 a request that carries `reasoning_effort` sets the template's
  `enable_thinking` to true, overriding a server-side default, and the calibration's declared
  decoding sends `reasoning_effort: low` to both models.  The pin therefore serves a template
  derived from the pinned revision's own, which renders what the stock template renders with
  thinking off, whatever the request says.  The equivalence is checked by rendering, against
  a control that shows the switch is real
* the checkpoint: a mirror from the runtime's local disk to a durable folder, a lock, and a
  run manifest that refuses a resume on a different stack or GPU
* the probe's stop rule, and the end-to-end path against a fake vLLM server launched through
  the driver's own `serve` step: an uninterrupted run, a runtime drop (SIGKILL) and a resume
  on a fresh local disk, a Stop-button interrupt (SIGINT), and the bundle's verification
* the notebook calls only commands the driver has, in the order the run needs them
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import textwrap
import time
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from poisson_tasks import calibration as cal

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
FIXTURE = HERE / "fixtures" / "qwen3-8b-chat-template.json"
NOTEBOOK = REPO / "notebooks" / "calibration_model_b.ipynb"
FAKE = HERE / "fake_vllm.py"

REVISION = "b968826d9c46dd6066d109eabc6255188de91218"
SERVED = f"Qwen/Qwen3-8B@{REVISION}"
STOCK_SHA = "a55ee1b1660128b7098723e0abcd92caa0788061051c62d51cbe87d9cf1974d8"

NAMES = (
    "ServePin", "QWEN3_8B", "no_think_template", "ServingMismatch", "check_server",
    "check_thinking_off", "wait_healthy", "complete_lines", "Mirror", "mirroring",
    "RunLock", "LockHeld", "check_run_manifest", "Design", "design", "probe_verdict",
    "ProbeVerdict", "trace_facts", "main", "PHASE1_DESIGN", "PHASE1_ARMS", "PROBE_DESIGN",
    "PROBE_ARMS", "FLOOR", "HEADROOM", "verify_bundle",
)


def run_module() -> Any:
    import importlib

    return importlib.import_module("poisson_tasks.calibration_run")


def stock_template() -> str:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    template: str = data["chat_template"]
    return template


def have_uv() -> bool:
    return shutil.which("uv") is not None


# ---------------------------------------------------------------------------
# the surface
# ---------------------------------------------------------------------------


def test_the_driver_exports_the_names_these_tests_reach() -> None:
    module = run_module()
    missing = [name for name in NAMES if not hasattr(module, name)]
    assert missing == [], missing


def test_the_driver_imports_no_proofload_and_no_adapter() -> None:
    """CAL22 reaches the driver too: model B's card is computed by Tasks alone."""
    import ast

    source = Path(run_module().__file__).read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        else:
            continue
        for name in names:
            assert not name.startswith("proofload"), name
            assert name != "poisson_tasks.adapter", name


# ---------------------------------------------------------------------------
# the serving pin (R12, N18)
# ---------------------------------------------------------------------------


def test_the_revision_is_forty_hex_and_goes_through_both_flags() -> None:
    pin = run_module().QWEN3_8B
    assert pin.model == "Qwen/Qwen3-8B"
    assert pin.revision == REVISION
    assert len(pin.revision) == 40 and all(c in "0123456789abcdef" for c in pin.revision)
    assert pin.served_name == SERVED
    args = pin.serve_args("/tmp/t.jinja")
    assert args[:2] == ["serve", "Qwen/Qwen3-8B"]
    assert args[args.index("--revision") + 1] == REVISION
    assert args[args.index("--served-model-name") + 1] == SERVED


def test_the_serve_flags_are_the_pinned_ones() -> None:
    """Tool calling on through Qwen3's own `<tool_call>` format (hermes), the context the
    tasks need, the declared decoding and nothing from the repository's
    `generation_config.json` (whose `top_k: 20` would otherwise apply unseen), and the
    thinking-off template."""
    pin = run_module().QWEN3_8B
    args = pin.serve_args("/tmp/t.jinja")

    def value(flag: str) -> str:
        return args[args.index(flag) + 1]

    assert "--enable-auto-tool-choice" in args
    assert value("--tool-call-parser") == "hermes"
    assert value("--max-model-len") == str(pin.max_model_len) == "8192"
    assert value("--generation-config") == "vllm"
    assert value("--chat-template") == "/tmp/t.jinja"
    assert value("--quantization") == "fp8"
    assert value("--host") == "127.0.0.1"
    assert pin.vllm_version == "0.29.0"
    # A server-side default is overridden by the request's reasoning_effort at 0.29.0, and
    # no reasoning parser is needed with thinking off.
    assert "--default-chat-template-kwargs" not in args
    assert "--reasoning-parser" not in args


def test_the_provenance_flags_name_the_template_by_hash_not_by_path() -> None:
    pin = run_module().QWEN3_8B
    flags = pin.flags()
    assert "/tmp/t.jinja" not in " ".join(flags)
    assert f"sha256:{pin.template_sha256}" in " ".join(flags)
    assert flags[flags.index("--revision") + 1] == REVISION


def test_the_pin_fills_a_provenance_block_that_the_artifact_accepts() -> None:
    """R12: a local model's block carries the stack and its version, the flags, the GPU and
    the revision, and `Provenance` refuses it without any of them.  No rate is declared, so
    model B's dollar figure is null (compute units, R1 and R3)."""
    pin = run_module().QWEN3_8B
    entry = pin.serving_entry(stack_version="0.29.0+cu129", gpu_name="NVIDIA L4")
    assert entry["kind"] == "local"
    for field in cal.SERVING_FIELDS_LOCAL:
        assert field in entry, field
    assert entry["revision"] == REVISION and entry["gpu"] == "NVIDIA L4"
    model = pin.model_entry()
    assert model["id"] == SERVED and model["revision"] == REVISION
    assert not any(field in model for field in ("input_rate", "cached_input_rate", "output_rate"))
    prov = cal.Provenance.for_run(
        models=[model], serving={SERVED: entry}, rate_read_date="2026-09-25"
    )
    assert prov.rates_for(SERVED) is None
    broken = {key: value for key, value in entry.items() if key != "gpu"}
    with pytest.raises(ValueError):
        cal.Provenance.for_run(models=[model], serving={SERVED: broken},
                               rate_read_date="2026-09-25")


# ---------------------------------------------------------------------------
# thinking off
# ---------------------------------------------------------------------------


def test_the_fixture_is_the_pinned_revisions_template() -> None:
    assert hashlib.sha256(stock_template().encode("utf-8")).hexdigest() == STOCK_SHA
    assert run_module().QWEN3_8B.stock_template_sha256 == STOCK_SHA


def test_the_derivation_refuses_any_other_template() -> None:
    derive = run_module().no_think_template
    with pytest.raises(ValueError):
        derive(stock_template() + "\n")
    with pytest.raises(ValueError):
        derive(stock_template().replace("enable_thinking is false", "enable_thinking is true"))


def test_the_derived_template_is_the_pinned_one() -> None:
    module = run_module()
    derived = module.no_think_template(stock_template())
    assert hashlib.sha256(derived.encode("utf-8")).hexdigest() == module.QWEN3_8B.template_sha256
    assert "enable_thinking" not in derived


def _render(template: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]],
            **kwargs: Any) -> str:
    jinja2 = pytest.importorskip("jinja2")
    from jinja2.sandbox import ImmutableSandboxedEnvironment

    env = ImmutableSandboxedEnvironment(
        trim_blocks=True, lstrip_blocks=True, extensions=["jinja2.ext.loopcontrols"]
    )
    env.filters["tojson"] = lambda value, indent=None: json.dumps(
        value, ensure_ascii=False, indent=indent
    )
    assert jinja2 is not None
    rendered: str = env.from_string(template).render(
        messages=messages, tools=tools, add_generation_prompt=True, **kwargs
    )
    return rendered


def _conversations() -> list[tuple[str, list[dict[str, Any]], list[dict[str, Any]]]]:
    """The first turn of every arm, from the generator, and a three-turn tool conversation."""
    from poisson_tasks.knobs import arm_id
    from poisson_tasks.tasks import generate

    out = []
    seed = cal.seed_list()[0]
    for spec in cal.arm_specs():
        bundle = generate(spec, seed)
        tools = [{"type": "function", "function": dict(tool)} for tool in bundle.tools]
        prompt = bundle.prompt
        history = [dict(m) for m in prompt] if not isinstance(prompt, str) else [
            {"role": "user", "content": prompt}
        ]
        first = [{"role": "system", "content": bundle.system_prompt}, *history]
        out.append((arm_id(spec), first, tools))
        if spec.knob == "depth" and spec.level == 3 and spec.control is None:
            convo = list(first)
            for i, ((name, arguments), observation) in enumerate(
                zip(bundle.reference_calls, bundle.reference_observations, strict=False)
            ):
                convo.append({"role": "assistant", "content": "", "tool_calls": [{
                    "id": f"c{i}", "type": "function",
                    "function": {"name": name, "arguments": json.dumps(arguments)},
                }]})
                convo.append({"role": "tool", "tool_call_id": f"c{i}", "content": str(observation)})
            out.append(("depth:d3 three turns", convo, tools))
    return out


@pytest.mark.parametrize("kwargs", [
    {"enable_thinking": True, "reasoning_effort": "low"},
    {"enable_thinking": False},
    {},
], ids=["request_sets_thinking_on", "thinking_off", "unset"])
def test_the_derived_template_renders_what_the_stock_one_renders_with_thinking_off(
    kwargs: dict[str, Any],
) -> None:
    """Whatever the request makes of `enable_thinking`, the served prompt is the stock
    template's thinking-off prompt, byte for byte, at every arm and deep into a chain."""
    derived = run_module().no_think_template(stock_template())
    for name, messages, tools in _conversations():
        want = _render(stock_template(), messages, tools, enable_thinking=False)
        got = _render(derived, messages, tools, **kwargs)
        assert got == want, name
        assert got.endswith("<|im_start|>assistant\n<think>\n\n</think>\n\n"), name


def test_control_the_stock_template_really_thinks_when_the_request_says_so() -> None:
    """The control that keeps the equivalence from being green by construction: under the
    stock template, `enable_thinking: true` (what `reasoning_effort: low` becomes at vLLM
    0.29.0) renders a different prompt, one with no empty think block."""
    name, messages, tools = _conversations()[0]
    on = _render(stock_template(), messages, tools, enable_thinking=True)
    off = _render(stock_template(), messages, tools, enable_thinking=False)
    assert on != off, name
    assert not on.endswith("</think>\n\n")


# ---------------------------------------------------------------------------
# the server checks, against the fake
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("FAKE_MODE", "reference")
    monkeypatch.delenv("FAKE_VERSION", raising=False)
    monkeypatch.delenv("FAKE_SEEDS", raising=False)
    yield


def _fake() -> Any:
    import importlib.util

    spec = importlib.util.spec_from_file_location("fake_vllm", FAKE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_check_server_accepts_the_pinned_stack(fake_env: None) -> None:
    module = run_module()
    with _fake().serve_in_thread(SERVED) as (base_url, _):
        module.wait_healthy(base_url, timeout_s=10)
        facts = module.check_server(module.QWEN3_8B, base_url)
    assert facts["stack_version"] == "0.29.0+cu129"
    assert facts["served_name"] == SERVED


def test_check_server_refuses_another_vllm_version(
    fake_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = run_module()
    monkeypatch.setenv("FAKE_VERSION", "0.30.0")
    with _fake().serve_in_thread(SERVED) as (base_url, _):
        with pytest.raises(module.ServingMismatch):
            module.check_server(module.QWEN3_8B, base_url)


def test_check_server_refuses_another_served_name(fake_env: None) -> None:
    module = run_module()
    with _fake().serve_in_thread("Qwen/Qwen3-8B") as (base_url, _):
        with pytest.raises(module.ServingMismatch):
            module.check_server(module.QWEN3_8B, base_url)


def test_the_thinking_check_sends_the_calibrations_own_decoding(fake_env: None) -> None:
    module = run_module()
    with _fake().serve_in_thread(SERVED) as (base_url, log):
        module.check_thinking_off(module.QWEN3_8B, base_url)
    body = log[-1]
    assert body["model"] == SERVED
    assert body["reasoning_effort"] == cal.DECODING["reasoning_effort"]
    assert body["max_completion_tokens"] == cal.DECODING["max_tokens"]
    assert "max_tokens" not in body
    assert body["temperature"] == cal.DECODING["temperature"]


def test_the_thinking_check_refuses_a_reply_that_thinks(
    fake_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = run_module()
    monkeypatch.setenv("FAKE_MODE", "think")
    with _fake().serve_in_thread(SERVED) as (base_url, _):
        with pytest.raises(module.ServingMismatch):
            module.check_thinking_off(module.QWEN3_8B, base_url)


# ---------------------------------------------------------------------------
# the checkpoint: mirror, lock, manifest (R4, CAL23)
# ---------------------------------------------------------------------------


def test_complete_lines_drops_a_torn_tail() -> None:
    lines = run_module().complete_lines
    assert lines(b'{"a":1}\n{"b":2}\n{"c"') == b'{"a":1}\n{"b":2}\n'
    assert lines(b'{"a":1}\n') == b'{"a":1}\n'
    assert lines(b'{"a"') == b""


def test_the_mirror_pushes_complete_lines_and_skips_temp_files(tmp_path: Path) -> None:
    module = run_module()
    local, durable = tmp_path / "local", tmp_path / "durable"
    (local / "phase3" / "depth-d1").mkdir(parents=True)
    (local / "phase3" / "depth-d1" / "traces.jsonl").write_bytes(b'{"id":"1"}\n{"id":"2"')
    (local / "phase3" / "depth-d1" / "traces.jsonl.tmp").write_bytes(b"half")
    (local / "vllm.log").write_text("started\n")
    module.Mirror(local, durable).push()
    assert (durable / "phase3" / "depth-d1" / "traces.jsonl").read_bytes() == b'{"id":"1"}\n'
    assert not (durable / "phase3" / "depth-d1" / "traces.jsonl.tmp").exists()
    assert (durable / "vllm.log").read_text() == "started\n"


def test_restore_fills_a_fresh_disk_and_never_overwrites_a_newer_local_file(
    tmp_path: Path,
) -> None:
    module = run_module()
    durable = tmp_path / "durable"
    (durable / "phase3" / "a").mkdir(parents=True)
    (durable / "phase3" / "a" / "traces.jsonl").write_bytes(b'{"id":"1"}\n{"id":"2"}\n{"x')
    (durable / "phase3" / "b").mkdir(parents=True)
    (durable / "phase3" / "b" / "traces.jsonl").write_bytes(b'{"id":"9"}\n')
    fresh = tmp_path / "fresh"
    module.Mirror(fresh, durable).restore()
    assert (fresh / "phase3" / "a" / "traces.jsonl").read_bytes() == b'{"id":"1"}\n{"id":"2"}\n'
    same_vm = tmp_path / "same"
    (same_vm / "phase3" / "b").mkdir(parents=True)
    (same_vm / "phase3" / "b" / "traces.jsonl").write_bytes(b'{"id":"9"}\n{"id":"10"}\n')
    module.Mirror(same_vm, durable).restore()
    assert (same_vm / "phase3" / "b" / "traces.jsonl").read_bytes() == b'{"id":"9"}\n{"id":"10"}\n'


def test_mirroring_pushes_on_the_way_out_of_an_interrupt(tmp_path: Path) -> None:
    """The Stop button raises KeyboardInterrupt in the driver; what was written locally
    before it reaches the durable folder anyway."""
    module = run_module()
    local, durable = tmp_path / "local", tmp_path / "durable"
    local.mkdir()
    with pytest.raises(KeyboardInterrupt):
        with module.mirroring(module.Mirror(local, durable), interval_s=3600):
            (local / "traces.jsonl").write_bytes(b'{"id":"1"}\n')
            raise KeyboardInterrupt
    assert (durable / "traces.jsonl").read_bytes() == b'{"id":"1"}\n'


def test_the_lock_refuses_a_second_live_runtime_and_yields_to_a_stale_one(
    tmp_path: Path,
) -> None:
    module = run_module()
    first = module.RunLock(tmp_path, owner="vm-a:1", stale_after_s=180, clock=lambda: 1000.0)
    first.acquire()
    live = module.RunLock(tmp_path, owner="vm-b:7", stale_after_s=180, clock=lambda: 1100.0)
    with pytest.raises(module.LockHeld):
        live.acquire()
    later = module.RunLock(tmp_path, owner="vm-b:7", stale_after_s=180, clock=lambda: 1181.0)
    later.acquire()
    again = module.RunLock(tmp_path, owner="vm-a:1", stale_after_s=180, clock=lambda: 1182.0)
    with pytest.raises(module.LockHeld):
        again.acquire()


def test_the_run_manifest_refuses_a_resume_on_another_stack(tmp_path: Path) -> None:
    """A14 and KC12 carried over: a run never resumes on a different GPU type, stack version,
    revision or generator, because the same weights served differently are a different
    measurement."""
    module = run_module()
    facts = {"served_name": SERVED, "stack_version": "0.29.0+cu129", "gpu": "NVIDIA L4",
             "flags": ["--x"], "generator_hash": "g" * 64}
    module.check_run_manifest(tmp_path, facts)
    module.check_run_manifest(tmp_path, dict(facts))
    for key, other in (("gpu", "NVIDIA A100-SXM4-40GB"), ("stack_version", "0.30.0"),
                       ("generator_hash", "h" * 64), ("flags", ["--y"])):
        with pytest.raises(module.ServingMismatch):
            module.check_run_manifest(tmp_path, {**facts, key: other})


# ---------------------------------------------------------------------------
# the probe's stop rule
# ---------------------------------------------------------------------------


def _record(arm: str, seed: int, attempt: int, *, label: str, calls: int) -> cal.EpisodeRecord:
    return cal.EpisodeRecord(
        task_id=f"{arm}/{seed}", arm_id=arm, model=SERVED, seed=seed, attempt=attempt,
        strict=label == "passed", leaky=label in ("passed", "overshoot"), label=label,
        turns=calls + 1, sampled_calls=calls, prompt_tokens=10, cached_input_tokens=0,
        completion_tokens=5, reasoning_tokens=0,
    )


def _probe_records(passes: int, *, no_call: int = 0, total: int = 24) -> list[cal.EpisodeRecord]:
    out = []
    for i in range(total):
        arm = "depth:d5" if i % 2 else "depth:d8"
        if i < passes:
            out.append(_record(arm, i, 0, label="passed", calls=8))
        elif i < passes + no_call:
            out.append(_record(arm, i, 0, label="wrong_state", calls=0))
        else:
            out.append(_record(arm, i, 0, label="wrong_state", calls=3))
    return out


def test_the_probe_stops_when_the_model_floors_on_the_hardest_levels() -> None:
    module = run_module()
    verdict = module.probe_verdict(_probe_records(1), {}, max_prompt_tokens=3000,
                                   context_stops=0, prompt_cap=6144)
    assert module.FLOOR == cal.SATURATION_LOW
    assert not verdict.proceed
    assert any("floor" in reason for reason in verdict.reasons), verdict.reasons


def test_the_probe_proceeds_when_the_model_reaches_the_goal() -> None:
    module = run_module()
    verdict = module.probe_verdict(_probe_records(6), {}, max_prompt_tokens=3000,
                                   context_stops=0, prompt_cap=6144)
    assert verdict.proceed, verdict.reasons
    assert verdict.leaky == pytest.approx(6 / 24)


@pytest.mark.parametrize("case", ["no_call", "instrument", "context", "headroom"])
def test_the_probe_stops_for_what_would_spoil_the_card(case: str) -> None:
    """Above CAL24's no-call threshold every cell would refuse; an instrument failure is
    plumbing; an episode cut off by the context cap, or prompts within a quarter of it,
    would count the serving limit as the model's failure."""
    module = run_module()
    records = _probe_records(12, no_call=4 if case == "no_call" else 0)
    tally = {"api_error": 1} if case == "instrument" else {}
    verdict = module.probe_verdict(
        records, tally,
        max_prompt_tokens=5000 if case == "headroom" else 3000,
        context_stops=1 if case == "context" else 0,
        prompt_cap=6144,
    )
    assert not verdict.proceed, case
    assert verdict.reasons


# ---------------------------------------------------------------------------
# end to end against the fake server, launched through the driver's own `serve`
# ---------------------------------------------------------------------------

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
        self.port = _free_port()
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


def _free_port() -> int:
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
        return port


@pytest.fixture
def rig(tmp_path: Path) -> Iterator[Any]:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    (tmp_path / "tokenizer_config.json").write_text(
        json.dumps({"chat_template": data["chat_template"]}), encoding="utf-8"
    )
    made: list[Rig] = []

    def factory(mode: str = "reference", delay: float = 0.0) -> Rig:
        sub = tmp_path / f"rig{len(made)}"
        sub.mkdir()
        shutil.copy(tmp_path / "tokenizer_config.json", sub / "tokenizer_config.json")
        made.append(Rig(sub, mode=mode, delay=delay))
        return made[-1]

    yield factory
    for each in made:
        each.close()


def _records_by_task(path: Path) -> Counter[tuple[str, str]]:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return Counter((row["arm_id"], row["task_id"]) for row in rows)


needs_uv = pytest.mark.skipif(not have_uv(), reason="the `null` harness launches its program through uv")


@needs_uv
def test_the_whole_run_uninterrupted(rig: Any) -> None:
    """serve, preflight, phase 1 through the plumbing gate, the probe, phase 3, the bundle
    and its verification: each task with exactly n attempts, the card rendered with the
    serving stack in its provenance, and every number recomputing from the records."""
    r = rig()
    r.serve()
    r.run("preflight")
    r.run("phase1")
    assert json.loads((r.durable / "phase1.json").read_text())["passed"] is True
    r.run("probe")
    assert json.loads((r.durable / "probe.json").read_text())["proceed"] is True
    r.run("phase3", "--wall-clock-hours", "1")
    report = json.loads((r.durable / "phase3.json").read_text())
    assert report["status"] == "complete", report
    counts = _records_by_task(r.durable / "card" / "episodes.jsonl")
    assert set(counts.values()) == {2} and len(counts) == 2 * 3, counts
    card = (r.durable / "card" / "card.md").read_text()
    assert f"{SERVED} served locally: vllm 0.29.0+cu129 on NVIDIA L4" in card
    assert "--generation-config vllm" in card
    r.run("bundle")
    done = r.run("verify", str(r.durable / "calibration-model-b-bundle.zip"),
                 "--into", str(r.tmp / "vault"))
    assert "recomputes" in done.stdout
    assert (r.tmp / "vault" / "card.md").read_text() == card
    r.stop_server()


@needs_uv
def test_the_run_stops_after_phase1_when_the_model_never_calls_a_tool(rig: Any) -> None:
    r = rig(mode="no_call")
    r.serve()
    r.run("preflight")
    failed = r.run("phase1", check=False)
    assert failed.returncode == 2, failed.stdout + failed.stderr
    assert json.loads((r.durable / "phase1.json").read_text())["passed"] is False
    blocked = r.run("probe", check=False)
    assert blocked.returncode != 0 and not (r.durable / "probe.json").exists()
    r.stop_server()


@needs_uv
def test_the_run_stops_after_the_probe_when_the_model_floors(rig: Any) -> None:
    """Phase 1 passes; then the server is restarted serving a model that calls a tool and
    never reaches a goal, and the probe on the hardest levels stops the run before phase 3.
    The notebook never switches models by itself."""
    r = rig()
    r.serve()
    r.run("preflight")
    r.run("phase1")
    r.stop_server()
    r.env["FAKE_MODE"] = "wrong"
    r.serve()
    r.run("preflight")
    report = r.run("probe", check=False)
    assert report.returncode == 3, report.stdout + report.stderr
    probe = json.loads((r.durable / "probe.json").read_text())
    assert probe["proceed"] is False
    assert any("floor" in reason for reason in probe["reasons"]), probe
    blocked = r.run("phase3", "--wall-clock-hours", "1", check=False)
    assert blocked.returncode != 0 and not (r.durable / "phase3.json").exists()
    r.stop_server()


def _wait_for(predicate: Any, timeout_s: float) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.2)
    raise AssertionError("condition not reached in time")


@needs_uv
def test_a_runtime_drop_loses_nothing_mirrored_and_runs_nothing_twice(rig: Any) -> None:
    """**CAL23 on the notebook's own path.**  Phase 3 is killed outright (SIGKILL: the VM is
    gone and no handler runs) once some episodes are on the durable folder.  A fresh local
    disk, as on a new runtime, is restored from it and the run resumed.  Every episode that
    was on the durable folder at the kill is in the final record under its own id, no id
    appears twice, and every task ends with exactly its n attempts -- the same multiset as
    an uninterrupted run."""
    r = rig(delay=0.3)
    r.serve()
    r.run("preflight")
    r.run("phase1")
    r.run("probe")
    proc = r.start("phase3", "--wall-clock-hours", "1")
    _wait_for(lambda: len(r.durable_ids("phase3")) >= 3, timeout_s=300)
    proc.send_signal(signal.SIGKILL)
    proc.wait(timeout=30)
    before = r.durable_ids("phase3")
    assert before and not (r.durable / "phase3.json").exists()
    shutil.rmtree(r.local)
    r.run("phase3", "--wall-clock-hours", "1")
    after = r.durable_ids("phase3")
    assert before <= after, "an episode that was on the durable folder was lost"
    rows = []
    for path in (r.durable / "phase3").glob("*/traces.jsonl"):
        rows += [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    assert len(rows) == len({row["id"] for row in rows}), "an episode appears twice"
    counts = _records_by_task(r.durable / "card" / "episodes.jsonl")
    assert set(counts.values()) == {2} and len(counts) == 2 * 3, counts
    assert json.loads((r.durable / "phase3.json").read_text())["status"] == "complete"
    r.stop_server()


@needs_uv
def test_the_stop_button_loses_nothing_at_all(rig: Any) -> None:
    """SIGINT, the Stop button: the driver's last act is a push, so the durable folder holds
    exactly what the local disk held, and the resume finishes the card."""
    r = rig(delay=0.3)
    r.serve()
    r.run("preflight")
    r.run("phase1")
    r.run("probe")
    proc = r.start("phase3", "--wall-clock-hours", "1")
    _wait_for(lambda: len(r.durable_ids("phase3")) >= 2, timeout_s=300)
    proc.send_signal(signal.SIGINT)
    assert proc.wait(timeout=120) != 0
    for local in (r.local / "phase3").glob("*/traces.jsonl"):
        durable = r.durable / local.relative_to(r.local)
        assert durable.read_bytes() == run_module().complete_lines(local.read_bytes())
    r.run("phase3", "--wall-clock-hours", "1")
    counts = _records_by_task(r.durable / "card" / "episodes.jsonl")
    assert set(counts.values()) == {2} and len(counts) == 2 * 3, counts
    r.stop_server()


@needs_uv
def test_a_resume_on_another_gpu_is_refused(rig: Any) -> None:
    r = rig()
    r.serve()
    r.run("preflight")
    (r.bin / "nvidia-smi").write_text("#!/bin/sh\necho 'NVIDIA A100-SXM4-40GB, 580.82.07'\n")
    refused = r.run("preflight", check=False)
    assert refused.returncode != 0
    assert "L4" in refused.stdout + refused.stderr
    r.stop_server()


@needs_uv
def test_the_wall_clock_budget_stops_the_card_cleanly(rig: Any) -> None:
    """R11 for model B: the Colab allowance is a wall-clock budget.  With none left, phase 3
    stops before its first episode, says why, and exits with the stop's own code."""
    r = rig()
    r.serve()
    r.run("preflight")
    r.run("phase1")
    r.run("probe")
    stopped = r.run("phase3", "--wall-clock-hours", "0", check=False)
    assert stopped.returncode == 4, stopped.stdout + stopped.stderr
    report = json.loads((r.durable / "phase3.json").read_text())
    assert report["status"] == "stopped" and report["stop"] == "wall_clock", report
    r.stop_server()


# ---------------------------------------------------------------------------
# the bundle, as it comes back to the vault
# ---------------------------------------------------------------------------


def test_verify_refuses_a_bundle_whose_file_changed(tmp_path: Path) -> None:
    module = run_module()
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "card.md").write_text("card\n")
    digest = hashlib.sha256(b"card\n").hexdigest()
    (bundle / "MANIFEST.sha256").write_text(f"{digest}  card.md\n")
    module.verify_bundle(bundle, recompute=False)
    (bundle / "card.md").write_text("edited\n")
    with pytest.raises(ValueError):
        module.verify_bundle(bundle, recompute=False)


# ---------------------------------------------------------------------------
# the notebook
# ---------------------------------------------------------------------------


def _notebook_commands() -> list[str]:
    nb = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    commands = []
    for cell in nb["cells"]:
        if cell["cell_type"] != "code":
            continue
        for line in "".join(cell["source"]).splitlines():
            if "-m poisson_tasks.calibration_run" in line:
                after = line.split("-m poisson_tasks.calibration_run", 1)[1].split()
                commands.append(after[0])
    return commands


def test_the_notebook_is_a_valid_v4_notebook() -> None:
    nb = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    assert nb["nbformat"] == 4
    assert all(cell["cell_type"] in ("code", "markdown") for cell in nb["cells"])
    for cell in nb["cells"]:
        if cell["cell_type"] == "code":
            assert cell.get("outputs") == [] and cell.get("execution_count") is None


def test_the_notebook_runs_the_driver_in_the_order_the_run_needs() -> None:
    commands = _notebook_commands()
    order = ["install-vllm", "serve", "preflight", "phase1", "probe", "phase3", "bundle"]
    positions = [commands.index(step) for step in order]
    assert positions == sorted(positions), commands


def test_every_notebook_command_is_one_the_driver_has() -> None:
    module = run_module()
    parser = module.build_parser()
    choices = parser._subparsers._group_actions[0].choices  # noqa: SLF001
    unknown = [command for command in _notebook_commands() if command not in choices]
    assert unknown == [], unknown


def test_the_notebook_types_no_pin_of_its_own() -> None:
    """The revision, the vLLM wheel and the flags live in the driver and the notebook asks
    it for them (`install-vllm`, `serve`), so the two cannot drift."""
    text = NOTEBOOK.read_text(encoding="utf-8")
    module = run_module()
    assert REVISION not in text
    assert module.QWEN3_8B.vllm_wheel_sha256 not in text
    assert "--tool-call-parser" not in text


def test_install_vllm_names_the_pinned_wheel_its_hash_and_the_cuda_backend(tmp_path: Path) -> None:
    """The install is the driver's, so the notebook cannot install another build: the
    release's CUDA 12.9 wheel, checked against its published sha256 before it is installed,
    with the PyTorch build for the same CUDA, into a virtualenv of its own."""
    module = run_module()
    pin = module.QWEN3_8B
    done = subprocess.run(
        [sys.executable, "-m", "poisson_tasks.calibration_run", "install-vllm",
         "--venv", str(tmp_path / "vllm-venv"), "--dry-run"],
        capture_output=True, text=True, timeout=120, env={**os.environ, "PYTHONPATH": str(REPO / "src")},
    )
    assert done.returncode == 0, done.stderr
    out = done.stdout
    assert pin.vllm_wheel_url in out and pin.vllm_wheel_sha256 in out
    assert "--torch-backend cu129" in out
    assert "vllm-0.29.0+cu129" in pin.vllm_wheel_url
    assert not (tmp_path / "vllm-venv").exists(), "a dry run installs nothing"
