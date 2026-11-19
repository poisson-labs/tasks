"""C2.11: the whole run against fake models, for each hosted model and for the notebook: a clean
run, a run stopped by its cap and resumed, and a failed phase 1.

The design asks for these at full size: 16,968 episodes (168 of phase 1 and 16,800 of the card)
for each API model and for the notebook.  An episode goes through the real harness, so one
full-size case takes hours.  This file runs the same three cases through the same code two ways:

* **By default**, on the smaller designs of `tests/c2_support.py`: claude-haiku-5-5 here, and the
  open model's failed phase 1.  The same cases for gpt-6-luna are `tests/test_c2_phase1.py` and
  `tests/test_c2_cap.py`, its clean run of every arm is `c2_support.clean_run`, and the notebook's
  clean run and its stop and resume are `tests/test_c2_notebook.py`.
* **With `POISSON_TASKS_C2_FULL_SIZE=1`**, at the registered size: every case, for gpt-6-luna,
  claude-haiku-5-5 and the notebook, on `card_run.DESIGN`.  Nothing is skipped either way.

What each case holds is the same at both sizes, and is stated once, in `hosted_cases` and
`notebook_cases`.
"""

from __future__ import annotations

import json
import shutil
from typing import Any

import pytest

from poisson_tasks import calibration_run as run
from tests.c2_fake import CLAUDE_LIKE, OPENAI_LIKE, Play
from tests.c2_support import (
    ARMS,
    BASES,
    DECISION_ARMS,
    GATE_ARMS,
    HAIKU,
    LUNA,
    MIDDLES,
    OWN_ARMS,
    PROVIDERS,
    QWEN,
    STOP_ARMS,
    card_run,
    card_v2_rig,
    complete_arms,
    drive,
    full_size,
    lines,
    needs_uv,
    read,
    registry_cache,
    small_design,
)
from tests.fd2_fakes import free_port
from tests.k9_fake import Behaviour

pytestmark = needs_uv

HOSTED = (LUNA, HAIKU) if full_size() else (HAIKU,)
CONCURRENCY = 64 if full_size() else 1


def designs() -> tuple[Any, Any]:
    """The design the clean and the capped run use, and the one the failed phase 1 uses."""
    if full_size():
        return card_run().DESIGN, card_run().DESIGN
    return small_design(arms=STOP_ARMS), small_design(arms=GATE_ARMS)


def per_arm(design: Any) -> int:
    return len(design.seeds) * design.attempts


def hosted_cases(model: str, factory: pytest.TempPathFactory) -> dict[str, Any]:
    cache = registry_cache(factory)
    design, gate = designs()
    provider = PROVIDERS[model]
    clean = drive(factory.mktemp("c2-full-clean"), cache, model=model, design=design,
                  play=Play(provider=provider), cap=500.0, concurrency=CONCURRENCY)
    found: dict[str, Any] = {"model": model, "design": design, "gate": gate, "clean": clean}
    if clean["code"] != 0:
        return found
    spent = card_run().build_artifact(clean["folder"])["provenance"]["run"]
    deciding = [arm for arm in design.arms if arm in DECISION_ARMS]
    spend = spent["spend_by_arm"]
    cap = spent["phase1"]["spent"] + sum(spend[arm] for arm in deciding) + max(
        spend[arm] for arm in deciding)
    total = spent["phase1"]["spent"] + sum(spend.values())
    where, port = factory.mktemp("c2-full-cap"), free_port()

    def call(limit: float) -> dict[str, Any]:
        return drive(where, cache, model=model, design=design, play=Play(provider=provider),
                     cap=limit, concurrency=CONCURRENCY, port=port)

    capped = call(cap)
    found.update(
        cap=cap,
        total=total,
        deciding=deciding,
        capped=capped,
        capped_status=read(capped["folder"] / "status.json"),
        capped_complete=complete_arms(capped["folder"], design),
        resumed=call(round(2 * total, 4)),
    )
    silent = Play(behaviour=Behaviour.from_mapping({"no_call": list(BASES)}), provider=provider)
    found["failed"] = drive(factory.mktemp("c2-full-failed"), cache, model=model, design=gate,
                            play=silent, cap=500.0, concurrency=CONCURRENCY)
    return found


@pytest.fixture(scope="module", params=HOSTED)
def hosted(request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
           ) -> dict[str, Any]:
    return hosted_cases(str(request.param), tmp_path_factory)


def test_the_registered_size_is_16_968_episodes_a_model() -> None:
    design = card_run().DESIGN
    assert len(design.arms) * len(design.phase1_seeds) == 168
    assert len(design.arms) * per_arm(design) == 16_800
    if full_size():
        assert designs() == (design, design)


def test_a_clean_run_scores_every_planned_episode(hosted: dict[str, Any]) -> None:
    clean, design = hosted["clean"], hosted["design"]
    assert clean["code"] == 0, clean["out"] + clean["err"]
    folder = clean["folder"]
    rows = lines(folder)
    assert len(rows) == len(design.arms) * per_arm(design)
    assert complete_arms(folder, design) == list(design.arms)
    assert {row["label"] for row in rows} == {"passed"}
    assert {row["model"] for row in rows} == {hosted["model"]}
    phase1 = read(folder / "phase1.json")
    assert phase1["passed"] is True and phase1["episodes"] == 3 * len(design.arms)
    status = read(folder / "status.json")
    assert (status["verdict"], status["stop"], status["owed"]) == ("done", None, 0)
    card_run().check_provenance(read(folder / "artifact.json")["provenance"])
    if full_size():
        assert len(rows) == 16_800 and phase1["episodes"] == 168
        assert tuple(design.arms) == ARMS


def test_a_run_stopped_by_its_cap_keeps_every_decision_arm(hosted: dict[str, Any]) -> None:
    assert "capped" in hosted, "the clean run did not finish"
    capped, design = hosted["capped"], hosted["design"]
    assert capped["code"] == 4, capped["out"] + capped["err"]
    status = hosted["capped_status"]
    assert (status["verdict"], status["stop"]) == ("stopped", "spend_cap")
    # Retrofitted 2026-11-19, ruled yes by Taylor after the full-size run: at the registered
    # size the run has 64 episodes in flight, and the run engine's cap is a bound, the cap plus
    # the cost of the calls in flight when it was reached.  So at full size the spend may pass
    # the cap by at most one episode of the costliest arm for each episode in flight; one
    # episode at a time, at the smaller size, it may not pass it at all, as first written.
    allowance = 0.0
    if full_size():
        spend = read(hosted["clean"]["folder"] / "artifact.json")["provenance"]["run"][
            "spend_by_arm"]
        allowance = CONCURRENCY * max(spend.values()) / per_arm(design)
    assert status["spent"] <= hosted["cap"] + allowance
    assert hosted["cap"] < hosted["total"]
    complete = hosted["capped_complete"]
    assert complete[: len(hosted["deciding"])] == hosted["deciding"]
    owed = [arm for arm in design.arms if arm not in complete]
    assert owed and set(owed) <= set(MIDDLES + OWN_ARMS)


def test_the_stopped_run_resumed_under_a_raised_cap_finishes_with_nothing_run_twice(
    hosted: dict[str, Any],
) -> None:
    assert "resumed" in hosted, "the clean run did not finish"
    resumed, design = hosted["resumed"], hosted["design"]
    assert resumed["code"] == 0, resumed["out"] + resumed["err"]
    rows = lines(resumed["folder"])
    assert len(rows) == len(design.arms) * per_arm(design)
    assert len({(row["arm_id"], row["seed"], row["attempt"]) for row in rows}) == len(rows)
    assert complete_arms(resumed["folder"], design) == list(design.arms)
    block = read(resumed["folder"] / "artifact.json")["provenance"]
    assert len(block["run"]["resumes"]) == 1
    assert read(resumed["folder"] / "status.json")["spent"] <= hosted["total"] * 1.10


def test_a_failed_phase_1_stops_the_run_and_reports_what_it_spent(hosted: dict[str, Any]) -> None:
    assert "failed" in hosted, "the clean run did not finish"
    failed, gate = hosted["failed"], hosted["gate"]
    assert failed["code"] == 2, failed["out"] + failed["err"]
    phase1 = read(failed["folder"] / "phase1.json")
    assert phase1["passed"] is False and phase1["stops"] == ["no_call"]
    assert phase1["no_call_share"] == 1.0 and phase1["episodes"] == 3 * len(gate.arms)
    assert phase1["spent"] > 0 and f"${phase1['spent']:.4f}" in failed["out"]
    assert not (failed["folder"] / "records" / "episodes.jsonl").exists()


# ---------------------------------------------------------------------------
# the notebook
# ---------------------------------------------------------------------------


def notebook_design(arms: tuple[str, ...]) -> Any:
    return card_run().DESIGN if full_size() else small_design(tasks=1, attempts=1, arms=arms)


def notebook_cases(factory: pytest.TempPathFactory) -> dict[str, Any]:
    cache = registry_cache(factory)
    found: dict[str, Any] = {}
    silent = Play(behaviour=Behaviour.from_mapping({"no_call": list(BASES)}), provider=OPENAI_LIKE)
    gate = notebook_design(GATE_ARMS)
    rig = card_v2_rig(factory.mktemp("c2-full-rig-failed"), silent, cache, gate)
    try:
        rig.serve()
        steps = {step: rig.run(step, check=False) for step in ("preflight", "phase1")}
        steps["phase3"] = rig.run("phase3", "--wall-clock-hours", "1", check=False)
        rig.stop_server()
    finally:
        rig.close()
    found["failed"] = {"rig": rig, "design": gate, **steps}
    if not full_size():
        return found
    design = notebook_design(ARMS)
    rig = card_v2_rig(factory.mktemp("c2-full-rig"), Play(), cache, design)
    try:
        rig.serve()
        steps = {step: rig.run(step, check=False) for step in ("preflight", "phase1", "probe")}
        steps["short"] = rig.run("phase3", "--wall-clock-hours", "0.05", check=False)
        rig.stop_server()
        shutil.rmtree(rig.local)
        rig.serve()
        for step in ("preflight", "phase1", "probe"):
            rig.run(step, check=False)
        steps["phase3"] = rig.run("phase3", "--wall-clock-hours", "200", check=False)
        rig.stop_server()
    finally:
        rig.close()
    found["clean"] = {"rig": rig, "design": design, **steps}
    return found


@pytest.fixture(scope="module")
def notebook(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    return notebook_cases(tmp_path_factory)


def test_the_notebooks_failed_phase_1_stops_it_before_phase_3(notebook: dict[str, Any]) -> None:
    failed = notebook["failed"]
    assert failed["phase1"].returncode == 2, failed["phase1"].stdout + failed["phase1"].stderr
    report = json.loads((failed["rig"].durable / "phase1.json").read_text())
    assert report["passed"] is False and report["stops"] == ["no_call"]
    assert report["episodes"] == 3 * len(failed["design"].arms)
    assert failed["phase3"].returncode != 0
    assert not (failed["rig"].local / run.CARD_V2_RESULTS_DIR / "episodes.jsonl").exists()
    assert not list((failed["rig"].local).glob(f"{run.CARD_V2_RUN_DIR}/*/traces.jsonl"))


def test_the_notebooks_run_stopped_by_its_allowance_and_resumed_scores_every_episode(
    notebook: dict[str, Any],
) -> None:
    """At the registered size only; on the smaller design this is
    `tests/test_c2_notebook.py`'s flow, which is the same steps."""
    if not full_size():
        assert "clean" not in notebook
        return
    clean = notebook["clean"]
    assert clean["short"].returncode == 4, clean["short"].stdout
    assert clean["phase3"].returncode == 0, clean["phase3"].stdout
    rows = [json.loads(line) for line in (
        clean["rig"].local / run.CARD_V2_RESULTS_DIR / "episodes.jsonl").read_text().splitlines()]
    assert len(rows) == 16_800
    assert len({(row["arm_id"], row["seed"], row["attempt"]) for row in rows}) == 16_800
    assert {row["model"] for row in rows} == {QWEN}
    assert json.loads((clean["rig"].durable / "phase1.json").read_text())["episodes"] == 168


def test_the_fakes_answer_as_each_models_provider() -> None:
    """A guard on what the cases above were run against."""
    assert PROVIDERS[LUNA] == OPENAI_LIKE and PROVIDERS[HAIKU] == CLAUDE_LIKE
    assert CLAUDE_LIKE.reasoning is None and "top_p" in CLAUDE_LIKE.refuses
