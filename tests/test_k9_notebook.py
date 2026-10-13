"""K9.8, Qwen's run: the Colab notebook's probe-only design, and the driver steps it calls.

The spec: the notebook's probe-only design applies the plumbing and instrument checks and the
context checks (no context stop; the headroom gate) to every arm, and its leaky floor and no-call
stop to the seven base arms only.  Serving settings are the card's.  The notebook keeps model B's
card as it was and gains a design switch: what changes for the probe is the configuration cell
(the design, its Drive folder, its local folder, its allowance, its bundle and the arm a void may
re-run), `--design` passed to every step that takes the run's folders, one cell for the re-run,
the bundle cell's file name, and words.

The rig is `tests/helpers.Rig` running the knob probe's design on fewer tasks
(`k9_support.knob_rig`), with `tests/k9_fake.py` in vLLM's place.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import types
import zipfile
from pathlib import Path
from typing import Any

import pytest

from poisson_tasks import calibration_run as run
from tests.k9_fake import Behaviour, cached_registry
from tests.k9_support import (
    ARMS,
    BASES,
    MODEL,
    OTHER,
    REPO,
    every_arm,
    knob_rig,
    model_run,
    needs_uv,
)

NOTEBOOK = REPO / "notebooks" / "calibration_model_b.ipynb"
CONFIG_MARK = "# Configuration: the only cell to edit."
RERUN_MARK = "# The knob probe only, and only when RERUN_ARM names an arm"


def cell(mark: str) -> str:
    nb = json.loads(NOTEBOOK.read_text())
    found = [
        "".join(c["source"])
        for c in nb["cells"]
        if c["cell_type"] == "code" and "".join(c["source"]).startswith(mark)
    ]
    assert len(found) == 1, mark
    return found[0]


def configuration(design: str | None = None) -> dict[str, Any]:
    source = cell(CONFIG_MARK)
    assert source.count('DESIGN = "card"') == 1
    if design is not None:
        source = source.replace('DESIGN = "card"', f'DESIGN = "{design}"')
    ns: dict[str, Any] = {}
    exec(source, ns)
    return ns


# ---------------------------------------------------------------------------
# the notebook
# ---------------------------------------------------------------------------


def test_the_card_stays_the_default_and_the_probe_gets_its_own_folders() -> None:
    card = configuration()
    assert card["DESIGN"] == "card"
    assert card["DRIVE_DIR"] == "/content/drive/MyDrive/poisson-tasks/calibration-model-b"
    assert card["LOCAL_DIR"] == "/content/cal-local"
    assert card["WALL_CLOCK_HOURS"] == 6.0
    assert card["BUNDLE_ZIP"] == run.BUNDLE_ZIP
    assert card["COMMON"][-2:] == ["--design", "card"]
    probe = configuration("knob-probe")
    assert probe["COMMON"][-2:] == ["--design", "knob-probe"]
    assert probe["DRIVE_DIR"] != card["DRIVE_DIR"] and probe["LOCAL_DIR"] != card["LOCAL_DIR"]
    assert probe["BUNDLE_ZIP"] == run.KNOB_BUNDLE_ZIP != run.BUNDLE_ZIP
    assert probe["RERUN_ARM"] == "" and probe["RERUN_CAUSE"] == ""


def test_every_step_that_takes_the_run_folders_takes_the_design() -> None:
    parser = run.build_parser()
    (sub,) = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
    choices: dict[str, argparse.ArgumentParser] = dict(sub.choices)
    with_folders = [
        name
        for name, sub in choices.items()
        if any("--local" in action.option_strings for action in sub._actions)
    ]
    assert {
        "serve",
        "preflight",
        "phase1",
        "probe",
        "phase3",
        "bundle",
        "status",
        "rerun-void",
    } <= set(with_folders)
    for name in with_folders:
        args = parser.parse_args(
            [
                name,
                "--local",
                "l",
                "--durable",
                "d",
                *(["--wall-clock-hours", "1"] if name == "phase3" else []),
                *(["--arm", "a", "--cause", "c"] if name == "rerun-void" else []),
            ]
        )
        assert args.design == "card", name
        design = [a for a in choices[name]._actions if "--design" in a.option_strings]
        assert design and tuple(design[0].choices or ()) == ("card", "knob-probe"), name


def test_the_re_run_cell_runs_its_step_only_when_an_arm_is_named() -> None:
    calls: list[tuple[str, ...]] = []
    ns: dict[str, Any] = {
        "step": lambda *args: calls.append(args),
        "RERUN_ARM": "",
        "RERUN_CAUSE": "",
    }
    exec(cell(RERUN_MARK), ns)
    assert calls == []
    ns.update(RERUN_ARM="history:t2400", RERUN_CAUSE="the server answered 500")
    exec(cell(RERUN_MARK), ns)
    assert calls == [("rerun-void", "--arm", "history:t2400", "--cause", "the server answered 500")]
    nb = json.loads(NOTEBOOK.read_text())
    sources = ["".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code"]
    rerun_at = sources.index(cell(RERUN_MARK))
    assert sources[rerun_at + 1].startswith('step("phase3"')


def test_the_bundle_cell_downloads_the_designs_zip(monkeypatch: pytest.MonkeyPatch) -> None:
    got: list[str] = []
    colab = types.ModuleType("google.colab")
    colab.files = types.SimpleNamespace(download=got.append)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "google", types.ModuleType("google"))
    monkeypatch.setitem(sys.modules, "google.colab", colab)
    nb = json.loads(NOTEBOOK.read_text())
    (bundle,) = [
        "".join(c["source"])
        for c in nb["cells"]
        if c["cell_type"] == "code" and 'step("bundle")' in "".join(c["source"])
    ]
    for design in ("card", "knob-probe"):
        ns = {**configuration(design), "step": lambda *args: 0}
        exec(bundle, ns)
        assert got[-1] == f"{ns['DRIVE_DIR']}/{ns['BUNDLE_ZIP']}"


def test_rerun_void_is_the_knob_probes_step_alone(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = run.main(
        [
            "rerun-void",
            "--local",
            str(tmp_path / "local"),
            "--durable",
            str(tmp_path / "durable"),
            "--arm",
            "spread:p4",
            "--cause",
            "the key",
        ]
    )
    err = capsys.readouterr().err
    assert code == 1 and err.count("\n") == 1 and "--design knob-probe" in err
    assert not (tmp_path / "local").exists()


# ---------------------------------------------------------------------------
# the probe's design, run on the rig
# ---------------------------------------------------------------------------

QWEN = Behaviour.from_mapping(
    {
        "fail": {"arguments:a8": 1.0, "shape:w4": 1.0},
        "give_up": {"faults:f4": 1.0},
    }
)
"""Faults and argument difficulty bite on this stand-in for Qwen, shape bites with `w4` the harder,
and every `history:t2400` task at the probe's seeds is answered with a server error."""


@pytest.fixture(scope="module")
def flow(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    from poisson_tasks import knob_probe as probe

    behaviour = Behaviour.from_mapping(
        {**QWEN.as_mapping(), "error": {"history:t2400": list(probe.PROBE_SEEDS[:2])}}
    )
    cache = tmp_path_factory.mktemp("k9-rig-cache") / "registry"
    # The fake's task list is built here, into the cache the fake reads, so the served fake
    # answers at once: built inside `serve`, it can outlast the helper's wait under heavy load.
    cached_registry(list(probe.ARMS), [*probe.PHASE1_SEEDS, *probe.PROBE_SEEDS[:2]], cache)
    rig = knob_rig(tmp_path_factory.mktemp("k9-rig"), behaviour, cache)
    found: dict[str, Any] = {"rig": rig}
    try:
        rig.serve()
        for step in ("preflight", "phase1", "probe"):
            found[step] = rig.run(step, check=False)
        found["phase3"] = rig.run("phase3", "--wall-clock-hours", "1", check=False)
        found["bundle"] = rig.run("bundle", check=False)
        found["card preflight"] = subprocess.run(
            run_argv(rig, "preflight"), env=rig.env, capture_output=True, text=True, timeout=600
        )
        found["rerun"] = rig.run(
            "rerun-void",
            "--arm",
            "history:t2400",
            "--cause",
            "the server answered 500 to every call",
            check=False,
        )
        found["after rerun"] = {
            "local": (rig.local / "void" / "history-t2400-1").exists(),
            "durable": (rig.durable / "void" / "history-t2400-1").exists(),
            "gone": not (rig.local / "knob-probe" / "history-t2400").exists()
            and not (rig.durable / "knob-probe" / "history-t2400").exists(),
            "phase3": json.loads((rig.local / "phase3.json").read_text()),
        }
        found["phase3 again"] = rig.run("phase3", "--wall-clock-hours", "1", check=False)
        found["rerun again"] = rig.run(
            "rerun-void", "--arm", "history:t2400", "--cause", "x", check=False
        )
        rig.stop_server()
    finally:
        rig.close()
    return found


def run_argv(rig: Any, command: str) -> list[str]:
    """The rig's command line for the card's design, as the card's notebook runs it."""
    from tests.helpers import Rig

    return Rig.argv(rig, command)


def read(rig: Any, name: str) -> Any:
    return json.loads((rig.local / name).read_text())


@needs_uv
def test_preflight_records_the_design_and_a_card_will_not_resume_on_its_folder(
    flow: dict[str, Any],
) -> None:
    assert flow["preflight"].returncode == 0, flow["preflight"].stdout + flow["preflight"].stderr
    assert json.loads((flow["rig"].durable / "run.json").read_text())["design"] == "knob-probe"
    card = flow["card preflight"]
    assert card.returncode == 1 and "design" in card.stdout and "STOP" in card.stdout


@needs_uv
def test_phase_1_runs_every_arm_at_phase_1s_seeds_once_and_writes_the_record_first(
    flow: dict[str, Any],
) -> None:
    from poisson_tasks import knob_probe as probe

    assert flow["phase1"].returncode == 0, flow["phase1"].stdout
    report = read(flow["rig"], "phase1.json")
    assert report["design"] == "knob-probe" and report["passed"]
    assert report["arms"] == list(ARMS) and report["seeds"] == list(probe.PHASE1_SEEDS)
    assert report["n"] == 1 and report["episodes"] == 54
    record = read(flow["rig"], "knob-probe-results/record.json")
    assert record["frozen_generator_hash"] == run.EXPECTED_GENERATOR_HASH
    assert record["phase1_seed_list_hash"] == probe.PHASE1_SEED_LIST_HASH
    assert record["model"] == run.QWEN3_8B.served_name
    assert record["serving"]["flags"] == run.QWEN3_8B.flags()
    assert record["serving"]["template_sha256"] == run.QWEN3_8B.template_sha256
    assert record["concurrency"] == 128
    assert record["invocations"][0]["step"] == "phase1"


@needs_uv
def test_the_probe_step_runs_no_episode_and_reads_the_notebooks_gates_on_phase_1(
    flow: dict[str, Any],
) -> None:
    assert flow["probe"].returncode == 0, flow["probe"].stdout
    gate = read(flow["rig"], "probe.json")
    assert gate["design"] == "knob-probe" and gate["proceed"]
    assert gate["floor_arms"] == list(BASES) and gate["prompt_cap"] == 16384 - 2048
    assert set(gate["per_arm_facts"]) == set(ARMS)
    assert not (flow["rig"].local / "probe").exists()


@needs_uv
def test_phase_3_runs_the_arms_and_writes_qwens_records_and_its_outcome(
    flow: dict[str, Any],
) -> None:
    assert flow["phase3"].returncode == 0, flow["phase3"].stdout
    rig = flow["rig"]
    assert read(rig, "phase3.json")["status"] == "complete"
    rows = [
        json.loads(line)
        for line in (rig.local / "knob-probe-results" / "episodes.jsonl").read_text().splitlines()
    ]
    assert len(rows) == 72 and {row["model"] for row in rows} == {run.QWEN3_8B.served_name}
    assert read(rig, "knob-probe-results/facts.json")["concurrency"] == 128
    outcome = read(rig, "knob-probe-results/outcome.json")
    statuses = {
        row["knob"]: row["per_model"][run.QWEN3_8B.served_name]["status"]
        for row in outcome["outcomes"]
    }
    assert statuses == {
        "similarity": "does not bite",
        "faults": "bites",
        "history": "void",
        "block": "does not bite",
        "arguments": "bites",
        "shape": "bites",
        "spread": "does not bite",
    }
    assert "void: history:t2400" in flow["phase3"].stdout
    assert (rig.durable / "knob-probe-results" / "outcome.json").exists()


@needs_uv
def test_the_bundle_holds_the_probes_files_and_its_manifest(flow: dict[str, Any]) -> None:
    assert flow["bundle"].returncode == 0, flow["bundle"].stdout
    archive = flow["rig"].durable / run.KNOB_BUNDLE_ZIP
    with zipfile.ZipFile(archive) as handle:
        names = set(handle.namelist())
    for name in (
        "knob-probe-results/record.json",
        "knob-probe-results/episodes.jsonl",
        "knob-probe-results/tallies.json",
        "knob-probe-results/outcome.json",
        "knob-probe-results/outcome.md",
        "phase1.json",
        "probe.json",
        "phase3.json",
        "run.json",
        "serving.json",
        run.MANIFEST,
    ):
        assert name in names, name
    assert not any(name.startswith("knob-probe/") for name in names)
    unpacked = flow["rig"].tmp / "unpacked"
    with zipfile.ZipFile(archive) as handle:
        handle.extractall(unpacked)
    assert run.verify_bundle(unpacked)["files"] == len(names) - 1


@needs_uv
def test_a_void_arm_is_set_aside_on_both_folders_once_and_run_again(flow: dict[str, Any]) -> None:
    assert flow["rerun"].returncode == 0, flow["rerun"].stdout + flow["rerun"].stderr
    after = flow["after rerun"]
    assert after["local"] and after["durable"] and after["gone"]
    assert after["phase3"]["status"] == "rerun"
    assert flow["phase3 again"].returncode == 0, flow["phase3 again"].stdout
    reruns = read(flow["rig"], "knob-probe-results/reruns.json")
    assert [entry["arm"] for entry in reruns] == ["history:t2400"]
    assert reruns[0]["cause"] == "the server answered 500 to every call"
    outcome = read(flow["rig"], "knob-probe-results/outcome.json")
    t2400 = outcome["arms"][run.QWEN3_8B.served_name]["history:t2400"]
    assert t2400["rerun"]["arm"] == "history:t2400" and t2400["void"]
    assert flow["rerun again"].returncode == 0
    assert "one re-run" in flow["rerun again"].stdout
    assert len(read(flow["rig"], "knob-probe-results/reruns.json")) == 1


def test_the_command_line_reads_both_models_records_into_one_outcome(tmp_path: Path) -> None:
    from poisson_tasks import knob_probe as probe

    for model, passes in ((MODEL, {"similarity:s3": 30}), (OTHER, {"faults:f4": 30})):
        made = model_run(every_arm(passes, model=model))
        probe.write_model_records(
            tmp_path / model.split("/")[0], made["records"], {}, reruns=[], facts={"concurrency": 8}
        )
    done = subprocess.run(
        [
            sys.executable,
            "-m",
            "poisson_tasks.knob_probe",
            "analyse",
            "--records",
            str(tmp_path / "Qwen"),
            "--records",
            str(tmp_path / MODEL),
            "--out",
            str(tmp_path / "out"),
        ],
        capture_output=True,
        text=True,
        timeout=600,
        env={"PYTHONPATH": str(REPO / "src"), "PATH": "/usr/bin:/bin"},
    )
    assert done.returncode == 0, done.stderr
    result = json.loads((tmp_path / "out" / "outcome.json").read_text())
    assert result["models"][:2] == [MODEL, OTHER]
    overall = {row["knob"]: row["outcome"] for row in result["outcomes"]}
    assert overall["similarity"] == overall["faults"] == "ships"
    assert overall["history"] == "does not ship"
    assert "| faults | ships |" in (tmp_path / "out" / "outcome.md").read_text()
    assert "faults: ships" in done.stdout


@needs_uv
def test_qwens_records_from_the_notebook_read_beside_gpt_5_nanos(flow: dict[str, Any]) -> None:
    from poisson_tasks import knob_probe as probe
    from tests.k9_support import cell, small_design

    design = small_design()
    nano = {
        arm: cell(arm, 0 if arm == "similarity:s3" else 2, seeds=design.probe_seeds)
        for arm in design.arms
    }
    qwen = probe.read_model_records(flow["rig"].local / "knob-probe-results")
    result = probe.analyse({MODEL: model_run(nano), run.QWEN3_8B.served_name: qwen}, design=design)
    overall = {row["knob"]: row["outcome"] for row in result["outcomes"]}
    assert overall["similarity"] == "ships" and overall["faults"] == "ships"
    assert overall["history"] == "does not ship"
    history = next(row for row in result["outcomes"] if row["knob"] == "history")
    assert history["per_model"][run.QWEN3_8B.served_name]["status"] == "void"
