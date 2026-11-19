"""C2.9: the spend cap, the stop it makes, and going on under a raised cap.

The design: a spend cap stops a run between episodes with every finished arm standing; run again
with a raised cap it goes on; and the arm order means a stop costs middle levels and own-tools
arms before any decision pair.  If a cap stops a run, the arms finished stand and the run
resumes with the cap Taylor raises.

The plan's line names `run --resume`.  The run engine has no such flag: a run started again in
its folder resumes what is owed, and a cap given then is the folder's cap from then on.  That is
what is pinned here, on `card_run.run_card` called again on the same folder.

The runs are on a smaller design (`STOP_ARMS`: two bases, two tops and a control, then three
middle levels and two own-tools arms), one episode at a time.  The cap is set from a finished
run's own recorded spend: phase 1, the five decision arms, and one more arm's worth of room.

Shapes decided here
-------------------
* `status.json` holds `verdict` (`"done"` or `"stopped"`), `stop` (the run engine's stop
  reason, `"spend_cap"` here; `null` when done), `spent`, `cap` and `owed` (episodes).
* A run a stop left unfinished exits 4.  `record.json`'s `invocations` gains one entry per call,
  each with its `cap` and `concurrency`.
* The block's `run.resumes` holds one entry for each later call that ran episodes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.c2_support import (
    DECISION_ARMS,
    LUNA,
    MIDDLES,
    OWN_ARMS,
    STOP_ARMS,
    by_arm,
    card_run,
    complete_arms,
    drive,
    lines,
    needs_uv,
    read,
    registry_cache,
    small_design,
)
from tests.fd2_fakes import free_port

pytestmark = needs_uv

DECIDING = tuple(arm for arm in STOP_ARMS if arm in DECISION_ARMS)
LATER = tuple(arm for arm in STOP_ARMS if arm in MIDDLES + OWN_ARMS)


def stop_design() -> Any:
    return small_design(arms=STOP_ARMS)


@pytest.fixture(scope="module")
def flow(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """A finished run, then the same run under a cap that ends in the later arms, the same call
    again, and the call again with the cap raised."""
    cache = registry_cache(tmp_path_factory)
    design = stop_design()
    whole = drive(tmp_path_factory.mktemp("c2-cap-whole"), cache, design=design, concurrency=1)
    assert whole["code"] == 0, whole["out"] + whole["err"]
    run = card_run().build_artifact(whole["folder"])["provenance"]["run"]
    spend = run["spend_by_arm"]
    cap = run["phase1"]["spent"] + sum(spend[arm] for arm in DECIDING) + max(
        spend[arm] for arm in DECIDING)
    total = run["phase1"]["spent"] + sum(spend.values())
    where, port = tmp_path_factory.mktemp("c2-cap"), free_port()

    def call(limit: float) -> dict[str, Any]:
        return drive(where, cache, design=design, cap=limit, concurrency=1, port=port)

    capped = call(cap)
    kept = {
        "status": read(capped["folder"] / "status.json"),
        "rows": lines(capped["folder"]),
        "complete": complete_arms(capped["folder"], design),
        "artifact": (capped["folder"] / "artifact.json").exists(),
    }
    again = call(cap)
    raised = call(round(2 * total, 4))
    return {"design": design, "cap": cap, "total": total, "whole": whole, "capped": capped,
            "kept": kept, "again": again, "raised": raised, "folder": capped["folder"]}


def test_the_design_under_test_has_decision_arms_then_later_ones() -> None:
    """A guard on the test's own design."""
    assert STOP_ARMS == DECIDING + LATER and len(DECIDING) == 5 and len(LATER) == 5
    assert tuple(stop_design().arms) == STOP_ARMS


def test_the_cap_is_below_what_the_whole_run_costs(flow: dict[str, Any]) -> None:
    assert 0 < flow["cap"] < flow["total"]


def test_a_cap_reached_stops_the_run_within_it(flow: dict[str, Any]) -> None:
    capped, status = flow["capped"], flow["kept"]["status"]
    assert capped["code"] == 4, capped["out"] + capped["err"]
    assert (status["verdict"], status["stop"]) == ("stopped", "spend_cap")
    assert 0 < status["spent"] <= flow["cap"]
    assert status["cap"] == flow["cap"] and status["owed"] > 0
    assert f"${status['spent']:.4f}" in capped["out"]


def test_the_stop_is_between_episodes_and_every_finished_arm_stands(flow: dict[str, Any]) -> None:
    """Every recorded episode is whole and scored, each planned attempt at most once, and no
    episode carries an instrument label because the cap cut it."""
    design, rows = flow["design"], flow["kept"]["rows"]
    planned = {(seed, attempt) for seed in design.seeds for attempt in range(design.attempts)}
    for arm, cell in by_arm(rows).items():
        made = [(row["seed"], row["attempt"]) for row in cell]
        assert len(made) == len(set(made)) and set(made) <= planned, arm
    assert {row["label"] for row in rows} <= {"passed", "wrong_state"}
    assert flow["kept"]["artifact"], "a stopped run still writes what it has"


def test_the_stop_costs_middle_levels_and_own_tools_arms_before_any_decision_pair(
    flow: dict[str, Any],
) -> None:
    complete = flow["kept"]["complete"]
    assert list(DECIDING) == complete[: len(DECIDING)]
    assert len(complete) < len(STOP_ARMS)
    owed = [arm for arm in STOP_ARMS if arm not in complete]
    assert set(owed) <= set(LATER)
    # the arms run in order: what is owed is the end of the list
    assert owed == list(STOP_ARMS[len(STOP_ARMS) - len(owed):])


def test_the_same_call_again_makes_no_model_call(flow: dict[str, Any]) -> None:
    again = flow["again"]
    assert again["code"] == 4 and again["chats"] == 0


def test_with_the_cap_raised_it_goes_on_to_the_end(flow: dict[str, Any]) -> None:
    raised, design = flow["raised"], flow["design"]
    assert raised["code"] == 0, raised["out"] + raised["err"]
    assert raised["chats"] > 0
    assert complete_arms(flow["folder"], design) == list(STOP_ARMS)
    status = read(flow["folder"] / "status.json")
    assert (status["verdict"], status["stop"], status["owed"]) == ("done", None, 0)
    assert status["spent"] <= status["cap"]


def test_no_finished_episode_is_run_again_and_none_is_lost(flow: dict[str, Any]) -> None:
    design = flow["design"]
    rows = lines(flow["folder"])
    assert len(rows) == len(STOP_ARMS) * len(design.seeds) * design.attempts
    kept = {(row["arm_id"], row["seed"], row["attempt"]): row for row in flow["kept"]["rows"]}
    now = {(row["arm_id"], row["seed"], row["attempt"]): row for row in rows}
    assert len(now) == len(rows)
    for key, row in kept.items():
        assert now[key] == row, key
    # phase 1 was not run a second time either
    assert not [pair for pair in flow["raised"]["matched"]
                if pair is not None and pair[1] in design.phase1_seeds]


def test_the_resumed_run_costs_what_the_whole_run_cost(flow: dict[str, Any]) -> None:
    """The same episodes against the same fake: the folder's spend is the unbroken run's, plus
    at most the calls of an episode the cap cut in flight, which is owed and run again."""
    spent = read(flow["folder"] / "status.json")["spent"]
    assert flow["total"] * 0.999 <= spent <= flow["total"] * 1.10


def test_each_call_and_its_cap_is_on_the_record(flow: dict[str, Any]) -> None:
    record = read(flow["folder"] / "record.json")
    caps = [entry["cap"] for entry in record["invocations"]]
    assert caps == [flow["cap"], flow["cap"], round(2 * flow["total"], 4)]
    assert {entry["concurrency"] for entry in record["invocations"]} == {1}
    run = card_run().build_artifact(flow["folder"])["provenance"]["run"]
    assert len(run["resumes"]) == 1
    assert list(run["spend_by_arm"]) == list(STOP_ARMS)


def test_a_cap_of_nothing_is_refused_before_anything_is_spent(
    tmp_path: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    found = drive(tmp_path, registry_cache(tmp_path_factory), design=stop_design(), cap=0.0)
    assert found["code"] == 1 and found["chats"] == 0
    assert found["err"].startswith("error: ") and found["err"].count("\n") == 1
    assert not found["folder"].exists()


def test_each_registered_model_has_the_cap_taylor_set() -> None:
    from tests.c2_support import CAPS, HAIKU, NANO

    models = card_run().MODELS
    assert {name: models[name].cap for name in (NANO, LUNA, HAIKU)} == CAPS
    assert CAPS == {NANO: 15.0, LUNA: 50.0, HAIKU: 65.0}
