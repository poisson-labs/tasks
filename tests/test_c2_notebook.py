"""C2.10: the Colab notebook's version 2 design, for the open model.

The design: the notebook's `DESIGN` gains `"card-v2"`, whose design equals `arm_specs("card-v2")`;
it serves `Qwen/Qwen3.8-27B-FP8` at a pinned revision with a pinned vLLM and the model's tool-call
and reasoning parsers, thinking on at effort low; its probe phase checks context headroom on
`history:t2400` and on `faults:f4`, the arms with the most tokens; its wall-clock budget is set
from phase 1's measured throughput; and it resumes across runtimes, reading stored verdicts back.
The request it sends is the design's row for vLLM (C2.4): temperature 1.0, top_p 1.0, effort low,
8,192 completion tokens.

The rig is `tests/helpers.Rig` running the version 2 design on fewer arms and tasks
(`c2_support.card_v2_rig`), with `tests/c2_fake.py` in vLLM's place and the rig's chat template
standing in for the pinned revision's.

Shapes decided here
-------------------
* `calibration_run.DESIGNS` gains `"card-v2"`, and every step that takes the run's folders takes
  it.  `"card"` stays the default and stays the generator-0 design on Qwen3-8B.
* `calibration_run.QWEN3_8_27B` is the pin (a `ServePin` with a `reasoning_parser`), and
  `CARD_V2_RUN_DIR`, `CARD_V2_RESULTS_DIR` and `CARD_V2_BUNDLE_ZIP` name where the design's arms
  run, where its record, records and artifact are written, and its bundle.
* The steps are the card's own: `preflight`, `phase1` (every arm at phase 1's three seeds, once,
  gated by the four stops of C2.8), `probe` (no episode: phase 1's facts read against the
  context cap), `phase3` (the arms at the card's seeds) and `bundle`.
* `phase1.json` adds `seconds_per_episode` and `projected_hours` (the registered 16,800 episodes
  at that pace); `probe.json` holds `headroom_arms` and `prompt_cap`.

Readings made here: thinking on at its default means the pinned revision's own chat template is
served unchanged; the GPU is an A100 80GB or an H100, and an L4 is refused; the context is at
least the 16,384 tokens Qwen3-8B's card had.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import types
import zipfile
from typing import Any

import pytest

from poisson_tasks import calibration as cal
from poisson_tasks import calibration_run as run
from poisson_tasks.knobs import arm_id
from tests.c2_fake import Play
from tests.c2_support import (
    ARMS,
    BUILT_IN_HASH,
    DECODING,
    DESIGN,
    MAX_TOKENS,
    NOTEBOOK,
    OWN_HASH,
    PHASE1_SEEDS,
    QWEN,
    QWEN_REPO,
    QWEN_REVISION,
    RECORD_FIELDS,
    card_run,
    card_v2_rig,
    needs_uv,
    registry_cache,
    small_design,
)

CONFIG_MARK = "# Configuration: the only cell to edit."
# Retrofitted 2026-11-18, ruled yes by Taylor in the build session: in the order the design runs
# them, faults before history among the tops.  The rig's design is `small_design(arms=RIG_ARMS)`,
# which is in that order, so the list as first written (history before faults) could not equal
# the arms any build reports.
RIG_ARMS = ("depth:d1", "faults:f4", "history:t2400", "spread:p4", "landed:l1")
VLLM_BODY = {
    "model": QWEN,
    "temperature": 1.0,
    "top_p": 1.0,
    "reasoning_effort": "low",
    "max_completion_tokens": MAX_TOKENS,
}


def code_cells() -> list[str]:
    nb = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    return ["".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code"]


def configuration(design: str | None = None) -> dict[str, Any]:
    (source,) = [text for text in code_cells() if text.startswith(CONFIG_MARK)]
    assert source.count('DESIGN = "card"') == 1
    if design is not None:
        source = source.replace('DESIGN = "card"', f'DESIGN = "{design}"')
    ns: dict[str, Any] = {}
    exec(source, ns)
    return ns


# ---------------------------------------------------------------------------
# the notebook
# ---------------------------------------------------------------------------


def test_the_design_switch_gains_card_v2_with_folders_and_a_bundle_of_its_own() -> None:
    card, probe, v2 = configuration(), configuration("knob-probe"), configuration(DESIGN)
    assert card["DESIGN"] == "card", "the default stays the card that is published"
    assert v2["COMMON"][-2:] == ["--design", DESIGN]
    for name in ("DRIVE_DIR", "LOCAL_DIR", "BUNDLE_ZIP"):
        assert len({card[name], probe[name], v2[name]}) == 3, name
    assert v2["BUNDLE_ZIP"] == run.CARD_V2_BUNDLE_ZIP


def test_the_driver_takes_the_design_on_every_step_that_takes_the_run_folders() -> None:
    assert tuple(run.DESIGNS) == ("card", "knob-probe", DESIGN)
    parser = run.build_parser()
    (sub,) = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
    for name, step in dict(sub.choices).items():
        if not any("--local" in action.option_strings for action in step._actions):
            continue
        (design,) = [a for a in step._actions if "--design" in a.option_strings]
        assert DESIGN in tuple(design.choices or ()), name
        extra = (["--wall-clock-hours", "1"] if name == "phase3" else []) + (
            ["--arm", "a", "--cause", "c"] if name == "rerun-void" else [])
        args = parser.parse_args([name, "--local", "l", "--durable", "d", "--design", DESIGN,
                                  *extra])
        assert args.design == DESIGN, name


def test_the_notebooks_design_is_the_registered_one() -> None:
    """`CARD_V2_DESIGN` is unset in the package, so the notebook runs `card_run.DESIGN`, whose
    arms are `arm_specs("card-v2")` in order."""
    assert run.CARD_V2_DESIGN is None
    assert card_run().DESIGN.arms == ARMS == tuple(arm_id(s) for s in cal.arm_specs(DESIGN))
    assert tuple(card_run().DESIGN.seeds) == tuple(cal.seed_list())


def test_the_gpu_cell_takes_an_a100_or_an_h100_for_card_v2_and_still_an_l4_for_the_card() -> None:
    (source,) = [text for text in code_cells() if "nvidia-smi" in text and "--query-gpu" in text]

    def gpu_cell(design: str | None, name: str) -> None:
        fake = types.SimpleNamespace(
            run=lambda *a, **k: types.SimpleNamespace(stdout=f"{name}, 580.82.07, 81920 MiB\n"))
        exec(source, {**configuration(design), "subprocess": fake, "print": lambda *a, **k: None})

    gpu_cell(DESIGN, "NVIDIA A100-SXM4-80GB")
    gpu_cell(DESIGN, "NVIDIA H100 80GB HBM3")
    gpu_cell(None, "NVIDIA L4")
    with pytest.raises(SystemExit):
        gpu_cell(DESIGN, "NVIDIA L4")
    with pytest.raises(SystemExit):
        gpu_cell(None, "NVIDIA A100-SXM4-80GB")


# ---------------------------------------------------------------------------
# the pin
# ---------------------------------------------------------------------------


def test_the_pin_is_the_fp8_checkpoint_at_one_revision() -> None:
    pin = run.QWEN3_8_27B
    assert (pin.model, pin.revision) == (QWEN_REPO, QWEN_REVISION)
    assert pin.served_name == QWEN
    assert "--revision" in pin.flags() and QWEN_REVISION in pin.flags()


def test_the_pin_names_one_vllm_build_by_its_wheels_digest() -> None:
    pin = run.QWEN3_8_27B
    assert re.fullmatch(r"\d+\.\d+\.\d+", pin.vllm_version)
    assert pin.vllm_version in pin.vllm_wheel_name and pin.vllm_wheel_name.endswith(".whl")
    assert pin.vllm_wheel_url.startswith("https://") and pin.vllm_wheel_url.endswith(
        pin.vllm_wheel_name)
    assert re.fullmatch(r"[0-9a-f]{64}", pin.vllm_wheel_sha256) and pin.vllm_wheel_size > 0


def test_the_pin_serves_with_the_models_tool_call_and_reasoning_parsers() -> None:
    pin = run.QWEN3_8_27B
    flags = pin.flags()
    assert pin.tool_call_parser and pin.reasoning_parser
    assert flags[flags.index("--tool-call-parser") + 1] == pin.tool_call_parser
    assert flags[flags.index("--reasoning-parser") + 1] == pin.reasoning_parser
    assert "--enable-auto-tool-choice" in flags
    assert flags[flags.index("--generation-config") + 1] == "vllm"


def test_the_pin_serves_the_revisions_own_template_so_thinking_stays_on() -> None:
    pin = run.QWEN3_8_27B
    assert re.fullmatch(r"[0-9a-f]{64}", pin.stock_template_sha256)
    assert pin.template_sha256 == pin.stock_template_sha256
    assert pin.template_sha256 != run.QWEN3_8B.template_sha256


def test_the_pin_leaves_room_for_8192_tokens_and_is_a_pre_quantized_checkpoint() -> None:
    pin = run.QWEN3_8_27B
    assert pin.max_model_len >= 16384 and pin.max_model_len > MAX_TOKENS
    assert pin.serving_entry(stack_version=pin.vllm_version, gpu_name="x")["quantization"] == "fp8"
    assert run.QWEN3_8B.model == "Qwen/Qwen3-8B", "the generator-0 card's pin is untouched"


def test_the_open_models_decoding_is_the_designs_row() -> None:
    assert dict(card_run().QWEN_DECODING) == DECODING[QWEN]


# ---------------------------------------------------------------------------
# the design, run on the rig
# ---------------------------------------------------------------------------


def rig_design() -> Any:
    return small_design(tasks=1, attempts=2, arms=RIG_ARMS)


def requests(rig: Any) -> list[dict[str, Any]]:
    if not rig.requests.exists():
        return []
    return [json.loads(line) for line in rig.requests.read_text().splitlines() if line]


def phase_1_requests(rig: Any) -> int:
    """How many requests so far were for a task at one of phase 1's seeds."""
    return len([line for line in requests(rig) if line["seed"] in PHASE1_SEEDS])


@pytest.fixture(scope="module")
def flow(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """Serve, preflight, phase 1, the probe, phase 3 cut short by its allowance; then a new
    runtime (the local disk gone), every step again, phase 3 to its end, and the bundle."""
    design = rig_design()
    rig = card_v2_rig(tmp_path_factory.mktemp("c2-rig"), Play(),
                      registry_cache(tmp_path_factory), design)
    found: dict[str, Any] = {"rig": rig, "design": design}
    try:
        rig.serve()
        for step in ("preflight", "phase1", "probe"):
            found[step] = rig.run(step, check=False)
            found[f"requests after {step}"] = phase_1_requests(rig)
        found["phase3 short"] = rig.run("phase3", "--wall-clock-hours", "0.0000001", check=False)
        found["phase3 short report"] = json.loads((rig.durable / "phase3.json").read_text())
        rig.stop_server()
        shutil.rmtree(rig.local)
        rig.serve()
        for step in ("preflight", "phase1", "probe"):
            found[f"{step} again"] = rig.run(step, check=False)
        found["requests after the new runtime's steps"] = phase_1_requests(rig)
        found["phase3"] = rig.run("phase3", "--wall-clock-hours", "1", check=False)
        found["bundle"] = rig.run("bundle", check=False)
        rig.stop_server()
    finally:
        rig.close()
    return found


def results(flow: dict[str, Any]) -> Any:
    return flow["rig"].local / run.CARD_V2_RESULTS_DIR


def said(done: Any) -> str:
    return str(done.stdout) + str(done.stderr)


@needs_uv
def test_preflight_records_the_design_and_the_serving_facts_on_an_a100(
    flow: dict[str, Any],
) -> None:
    assert flow["preflight"].returncode == 0, said(flow["preflight"])
    rig = flow["rig"]
    manifest = json.loads((rig.durable / "run.json").read_text())
    assert manifest["design"] == DESIGN
    assert manifest["generator_hash"] == BUILT_IN_HASH
    serving = json.loads((rig.durable / "serving.json").read_text())
    assert serving["served_name"] == QWEN and "A100" in serving["gpu"]
    assert serving["stack_version"].startswith(run.QWEN3_8_27B.vllm_version)


@needs_uv
def test_phase_1_runs_every_arm_at_its_three_seeds_once_and_writes_the_record_first(
    flow: dict[str, Any],
) -> None:
    assert flow["phase1"].returncode == 0, said(flow["phase1"])
    report = json.loads((flow["rig"].durable / "phase1.json").read_text())
    assert report["design"] == DESIGN and report["passed"] is True
    assert report["arms"] == list(RIG_ARMS) and report["seeds"] == list(PHASE1_SEEDS)
    assert report["n"] == 1 and report["episodes"] == 3 * len(RIG_ARMS)
    assert report["stops"] == [] and report["answer_models"] == [QWEN]
    record = json.loads((results(flow) / "record.json").read_text())
    assert record["frozen_generator_hash"] == BUILT_IN_HASH
    assert record["own_generator_hash"] == OWN_HASH
    assert record["model"] == QWEN and record["decoding"] == DECODING[QWEN]
    assert record["serving"]["flags"] == run.QWEN3_8_27B.flags()
    assert record["invocations"][0]["step"] == "phase1"


@needs_uv
def test_phase_1_measures_its_pace_and_projects_the_whole_runs_hours(
    flow: dict[str, Any],
) -> None:
    report = json.loads((flow["rig"].durable / "phase1.json").read_text())
    pace = report["seconds_per_episode"]
    assert pace > 0 and report["projected_hours"] == pytest.approx(pace * 16_800 / 3600)


@needs_uv
def test_the_probe_step_runs_no_episode_and_checks_headroom_on_the_two_longest_arms(
    flow: dict[str, Any],
) -> None:
    assert flow["probe"].returncode == 0, said(flow["probe"])
    gate = json.loads((flow["rig"].durable / "probe.json").read_text())
    assert gate["design"] == DESIGN and gate["proceed"] is True
    assert gate["headroom_arms"] == ["history:t2400", "faults:f4"]
    assert gate["prompt_cap"] == run.QWEN3_8_27B.max_model_len - MAX_TOKENS
    assert {"history:t2400", "faults:f4"} <= set(gate["per_arm_facts"])
    assert flow["requests after probe"] == flow["requests after phase1"] > 0


@needs_uv
def test_phase_3_stops_cleanly_when_its_allowance_runs_out(flow: dict[str, Any]) -> None:
    assert flow["phase3 short"].returncode == 4, said(flow["phase3 short"])
    report = flow["phase3 short report"]
    assert (report["design"], report["status"], report["stop"]) == (DESIGN, "stopped",
                                                                   "wall_clock")


@needs_uv
def test_a_new_runtime_reads_the_stored_verdicts_back_and_runs_nothing_twice(
    flow: dict[str, Any],
) -> None:
    for step in ("preflight again", "phase1 again", "probe again"):
        assert flow[step].returncode == 0, (step, said(flow[step]))
    assert flow["requests after the new runtime's steps"] == flow["requests after phase1"]


@needs_uv
def test_phase_3_goes_on_to_the_end_and_writes_the_records(flow: dict[str, Any]) -> None:
    assert flow["phase3"].returncode == 0, said(flow["phase3"])
    design = flow["design"]
    assert json.loads((flow["rig"].local / "phase3.json").read_text())["status"] == "complete"
    rows = [json.loads(line)
            for line in (results(flow) / "episodes.jsonl").read_text().splitlines()]
    assert len(rows) == len(RIG_ARMS) * len(design.seeds) * design.attempts
    assert len({(row["arm_id"], row["seed"], row["attempt"]) for row in rows}) == len(rows)
    assert [row["arm_id"] for row in rows[:: design.attempts]] == list(RIG_ARMS)
    for row in rows:
        assert not [name for name in RECORD_FIELDS if name not in row], row["arm_id"]
        assert row["model"] == QWEN and row["answer_models"] == [QWEN]
        assert row["label"] == "passed" and row["length_stops"] == 0
        assert row["reasoning_tokens"] == 20 * row["turns"]


@needs_uv
def test_every_task_request_to_vllm_is_the_designs_row(flow: dict[str, Any]) -> None:
    sent = [line for line in requests(flow["rig"]) if line["arm"] is not None]
    assert {line["arm"] for line in sent} == set(RIG_ARMS)
    for line in sent:
        assert line["sampling"] == VLLM_BODY, line


@needs_uv
def test_the_runs_block_is_whole_and_says_how_the_model_was_served(flow: dict[str, Any]) -> None:
    artifact = json.loads((results(flow) / "artifact.json").read_text())
    block = artifact["provenance"]
    card_run().check_provenance(block)
    serving = block["serving"][QWEN]
    assert (serving["kind"], serving["stack"], serving["revision"]) == ("local", "vllm",
                                                                       QWEN_REVISION)
    assert serving["quantization"] == "fp8" and "A100" in serving["gpu"]
    assert serving["flags"] == run.QWEN3_8_27B.flags()
    assert re.fullmatch(r"[0-9a-f]{64}", serving["chat_template_sha256"])
    assert block["decoding"] == DECODING[QWEN] and block["card_version"] == 2
    assert len(block["run"]["resumes"]) >= 1 and block["run"]["phase1"]["passed"] is True
    assert "input_rate" not in block["models"][0]


@needs_uv
def test_the_bundle_holds_the_designs_files_and_verifies(flow: dict[str, Any]) -> None:
    assert flow["bundle"].returncode == 0, said(flow["bundle"])
    rig = flow["rig"]
    archive = rig.durable / run.CARD_V2_BUNDLE_ZIP
    with zipfile.ZipFile(archive) as handle:
        names = set(handle.namelist())
    folder = run.CARD_V2_RESULTS_DIR
    for name in (f"{folder}/record.json", f"{folder}/episodes.jsonl", f"{folder}/artifact.json",
                 "phase1.json", "probe.json", "phase3.json", "run.json", "serving.json",
                 run.MANIFEST):
        assert name in names, name
    assert not any(name.startswith(f"{run.CARD_V2_RUN_DIR}/") for name in names)
    unpacked = rig.tmp / "unpacked"
    with zipfile.ZipFile(archive) as handle:
        handle.extractall(unpacked)
    assert run.verify_bundle(unpacked)["files"] == len(names) - 1


@needs_uv
def test_the_probe_stops_the_run_when_a_long_arm_comes_near_the_context_cap(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """With a context that leaves a thousand tokens beside the completion limit, every prompt of
    the two long arms is past three quarters of the room."""
    design = small_design(tasks=1, attempts=1, arms=("depth:d1", "history:t2400", "faults:f4"))
    rig = card_v2_rig(tmp_path_factory.mktemp("c2-rig-cap"), Play(),
                      registry_cache(tmp_path_factory), design, max_model_len=MAX_TOKENS + 1000)
    try:
        rig.serve()
        steps = {step: rig.run(step, check=False) for step in ("preflight", "phase1", "probe")}
        rig.stop_server()
    finally:
        rig.close()
    assert steps["phase1"].returncode == 0, said(steps["phase1"])
    assert steps["probe"].returncode != 0 and "STOP" in said(steps["probe"])
    gate = json.loads((rig.durable / "probe.json").read_text())
    assert gate["proceed"] is False and gate["prompt_cap"] == 1000
    reasons = " ".join(gate["reasons"])
    assert "history:t2400" in reasons and "faults:f4" in reasons


@needs_uv
@pytest.mark.parametrize(("gpu", "code"), [("H100", 0), ("L4", 1)])
def test_preflight_takes_an_h100_and_refuses_an_l4(
    gpu: str, code: int, tmp_path_factory: pytest.TempPathFactory
) -> None:
    design = small_design(tasks=1, attempts=1, arms=("depth:d1",))
    rig = card_v2_rig(tmp_path_factory.mktemp(f"c2-rig-{gpu.lower()}"), Play(),
                      registry_cache(tmp_path_factory), design, gpu=gpu)
    try:
        rig.serve()
        done = rig.run("preflight", check=False)
        rig.stop_server()
    finally:
        rig.close()
    assert done.returncode == code, said(done)
    assert ("STOP" in said(done)) == (code == 1)
