"""The knob probe end to end: the gpt-5-nano driver against the fake model, at no cost.

The probe's design: the driver runs the eighteen arms in order through the calibration path,
phase 1 first; if phase 1 fails the probe stops and reports what it spent.  The frozen
generator's hash and the seed list's hash are written into the run folder before the first paid
call, and the driver refuses to run if the generator hash is not the frozen one.  It takes a
dollar cap and stops within it, with the run engine's cap and ledger; the arm order means a stop
costs tops, never bases.  It loads the key from `.env` at run time without printing it, and stops
with one line saying where it looked if the key is missing or refused.  It writes the outcome per
knob and model; a void arm may be re-run once.

Every run here is the smaller design (`k9_support.small_design`: every arm, phase 1 as
registered, two of the probe's seeds at two attempts) against `tests/k9_fake.py`, inside the
network guard, which refuses any connection off this machine.
"""

from __future__ import annotations

import io
import json
from collections.abc import Iterator
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any

import pytest

from poisson_tasks import calibration as cal
from tests.fd2_fakes import free_port, network_guard
from tests.k9_fake import Behaviour, running
from tests.k9_support import (
    BASES,
    KEY,
    MODEL,
    PHASE1_FAILS,
    TOPS,
    env_file,
    harness,
    ledger,
    mixed,
    needs_uv,
    outcome_of,
    small_design,
)

pytestmark = needs_uv
HASH = "b460964dc153fab4535af3b39abd41d50198f3dcc644ae3e43ddee85544b57f9"


def drive(
    where: Path,
    behaviour: Behaviour,
    cache: Path,
    *,
    cap: float = 5.0,
    concurrency: int = 8,
    folder: str = "run",
    env: Path | None = None,
    before: Any = None,
    port: int = 0,
) -> dict[str, Any]:
    """`run_probe` into `where/folder` against the fake, in this process, with its printed lines,
    its one-line refusals, the fake's requests and what the folder held at the first model call.
    A folder's record holds its endpoint, so two runs into one folder pass the same `port`."""
    from poisson_tasks import knob_probe as probe

    design = small_design()
    out, err = io.StringIO(), io.StringIO()
    seen: dict[str, Any] = {}
    with pytest.MonkeyPatch.context() as mp, harness(where, mp), network_guard(mp):
        if before is not None:
            before(mp)
        with running(
            design.arms,
            [*design.phase1_seeds, *design.probe_seeds],
            behaviour,
            cache=cache,
            port=port,
        ) as fake:
            record = where / folder / "record.json"
            fake.on_first_chat = lambda: seen.update(
                record=json.loads(record.read_text()) if record.exists() else None
            )
            with redirect_stdout(out), redirect_stderr(err):
                code = probe.run_probe(
                    where / folder,
                    cap=cap,
                    concurrency=concurrency,
                    env_file=env or env_file(where),
                    base_url=fake.base_url,
                    design=design,
                )
            chats, gets = len(fake.posts), list(fake.gets)
    return {
        "code": code,
        "out": out.getvalue(),
        "err": err.getvalue(),
        "seen": seen,
        "chats": chats,
        "gets": gets,
        "folder": where / folder,
    }


@pytest.fixture(scope="module")
def cache(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("k9-cache") / "registry"


@pytest.fixture(scope="module")
def mixed_run(tmp_path_factory: pytest.TempPathFactory, cache: Path) -> dict[str, Any]:
    return drive(tmp_path_factory.mktemp("k9-mixed"), mixed(), cache)


def read(path: Path) -> Any:
    return json.loads(path.read_text())


# ---------------------------------------------------------------------------
# the run, phase 1 first, the record before the first paid call
# ---------------------------------------------------------------------------


def test_the_run_finishes_phase_1_then_every_arm_and_writes_the_outcome(
    mixed_run: dict[str, Any],
) -> None:
    folder = mixed_run["folder"]
    assert mixed_run["code"] == 0, mixed_run["out"] + mixed_run["err"]
    phase1 = read(folder / "phase1.json")
    assert phase1["passed"] and phase1["episodes"] == 54
    assert read(folder / "phase1" / "plan.json")["plan"]["seeds"] == [
        1180681854,
        601375552,
        2652385879,
    ]
    assert (folder / "phase1.json").stat().st_mtime_ns < (
        folder / "probe" / "plan.json"
    ).stat().st_mtime_ns
    lines = [
        json.loads(line)
        for line in (folder / "records" / "episodes.jsonl").read_text().splitlines()
    ]
    assert len(lines) == 72 and {row["arm_id"] for row in lines} == set(small_design().arms)


def test_the_record_is_in_the_folder_before_the_first_model_call(
    mixed_run: dict[str, Any],
) -> None:
    from poisson_tasks import knob_probe as probe

    record = mixed_run["seen"]["record"]
    assert record is not None, "no record when the first model call was made"
    assert record["frozen_generator_hash"] == HASH
    assert record["probe_seed_list_hash"] == cal._seed_list_digest(small_design().probe_seeds)
    assert record["phase1_seed_list_hash"] == probe.PHASE1_SEED_LIST_HASH
    assert record["arms"] == list(small_design().arms)
    assert record["invocations"][0]["cap"] == 5.0
    assert record["invocations"][0]["concurrency"] == 8


def test_the_outcome_is_written_per_knob_and_model(mixed_run: dict[str, Any]) -> None:
    result = read(mixed_run["folder"] / "outcome.json")
    per_model = {row["knob"]: row["per_model"][MODEL]["status"] for row in result["outcomes"]}
    assert per_model == {
        "similarity": "bites",
        "faults": "bites",
        "history": "does not bite",
        "block": "bites",
        "arguments": "does not bite",
        "shape": "bites",
        "spread": "top easier",
    }
    assert outcome_of(result, "shape")["per_model"][MODEL]["harder"] == "shape:w1"
    overall = {row["knob"]: row["outcome"] for row in result["outcomes"]}
    assert overall["spread"] == "does not ship" and overall["shape"] == "ships"
    assert overall["similarity"] == "waiting"
    page = (mixed_run["folder"] / "outcome.md").read_text()
    assert "| spread | does not ship |" in page
    assert "similarity: bites on gpt-5-nano-2025-08-07; waiting" in mixed_run["out"]


def test_what_it_spent_is_the_two_ledgers_and_inside_the_cap(mixed_run: dict[str, Any]) -> None:
    folder = mixed_run["folder"]
    spent = sum(line["dollars"] for name in ("phase1", "probe") for line in ledger(folder / name))
    status = read(folder / "status.json")
    assert abs(status["spent"] - spent) < 1e-9 and 0 < spent <= 5.0
    assert read(folder / "records" / "facts.json")["dollars"] == status["spent"]
    assert f"spent ${spent:.4f} of the $5.00 cap" in mixed_run["out"]


def test_the_key_is_sent_and_never_written_or_printed(mixed_run: dict[str, Any]) -> None:
    texts = [mixed_run["out"], mixed_run["err"]]
    for path in mixed_run["folder"].rglob("*"):
        if path.is_file():
            texts.append(path.read_bytes().decode("utf-8", "replace"))
    assert not any(KEY[4:12] in text for text in texts)
    assert any(path.endswith(f"/models/{MODEL}") for path in mixed_run["gets"])


# ---------------------------------------------------------------------------
# refusals, each one line, before anything is spent
# ---------------------------------------------------------------------------


def test_it_refuses_a_generator_that_is_not_the_frozen_one(tmp_path: Path, cache: Path) -> None:
    from poisson_tasks import knob_probe as probe

    found = drive(
        tmp_path,
        Behaviour(),
        cache,
        before=lambda mp: mp.setattr(probe, "FROZEN_GENERATOR_HASH", "0" * 64),
    )
    assert found["code"] == 1
    assert found["err"].count("\n") == 1 and found["err"].startswith("error: ")
    assert HASH in found["err"] and "0" * 64 in found["err"]
    assert found["chats"] == 0 and found["gets"] == []
    assert not found["folder"].exists()


def test_a_missing_key_stops_in_one_line_naming_where_it_looked(
    tmp_path: Path, cache: Path
) -> None:
    nowhere = tmp_path / "keys" / ".env"
    absent = drive(tmp_path, Behaviour(), cache, env=nowhere)
    assert absent["code"] == 1 and absent["err"].count("\n") == 1
    assert str(nowhere.resolve()) in absent["err"] and "MODEL_API_KEY" in absent["err"]
    nowhere.parent.mkdir(parents=True)
    nowhere.write_text("OPENAI_API_KEY=sk-not-this-one\n")
    unnamed = drive(tmp_path, Behaviour(), cache, env=nowhere)
    assert unnamed["code"] == 1 and str(nowhere.resolve()) in unnamed["err"]
    assert "sk-not-this-one" not in unnamed["err"] + unnamed["out"]
    assert absent["gets"] == unnamed["gets"] == [] and not (tmp_path / "run").exists()


def test_a_refused_key_stops_in_one_line_and_nothing_is_spent(tmp_path: Path, cache: Path) -> None:
    found = drive(tmp_path, Behaviour(refuse_key=True), cache)
    assert found["code"] == 1 and found["err"].count("\n") == 1
    assert "refused the key in MODEL_API_KEY" in found["err"]
    assert str((tmp_path / ".env").resolve()) in found["err"]
    assert KEY[4:12] not in found["err"] + found["out"]
    assert found["chats"] == 0 and not (found["folder"] / "record.json").exists()


def test_a_folder_that_holds_another_runs_settings_is_refused(tmp_path: Path) -> None:
    """The record is written once; a later run into the folder must be the same probe."""
    from poisson_tasks import knob_probe as probe

    path = tmp_path / "record.json"
    record = probe.probe_record(probe.DESIGN, model=probe.MODEL, base_url=probe.BASE_URL, extra={})
    probe.check_record(path, record, {"when": "first"})
    for field, value in (
        ("base_url", "http://127.0.0.1:9/v1"),
        ("model", "gpt-5-mini"),
        ("probe_seeds", [1, 2]),
        ("arms", list(reversed(record["arms"]))),
        ("frozen_generator_hash", "0" * 64),
        ("decoding", {**record["decoding"], "temperature": 0.5}),
        ("max_model_calls", 64),
    ):
        with pytest.raises(ValueError):
            probe.check_record(path, {**record, field: value}, {"when": "again"})
    held = probe.check_record(path, record, {"when": "resumed"})
    assert [entry["when"] for entry in held["invocations"]] == ["first", "resumed"]


# ---------------------------------------------------------------------------
# phase 1 fails
# ---------------------------------------------------------------------------


def test_a_failed_phase_1_stops_the_probe_and_reports_what_it_spent(
    tmp_path: Path, cache: Path
) -> None:
    found = drive(tmp_path, PHASE1_FAILS, cache)
    folder = found["folder"]
    assert found["code"] == 2
    phase1 = read(folder / "phase1.json")
    assert not phase1["passed"]
    assert any(reason.startswith("base arms: ") for reason in phase1["reasons"])
    spent = sum(line["dollars"] for line in ledger(folder / "phase1"))
    assert spent > 0 and abs(phase1["spent"] - spent) < 1e-12
    assert f"${spent:.4f} spent" in found["out"]
    assert not (folder / "probe").exists() and not (folder / "outcome.json").exists()


# ---------------------------------------------------------------------------
# the cap: the run engine's, and a stop costs tops, never bases
# ---------------------------------------------------------------------------


def test_a_cap_reached_stops_within_it_after_the_bases_and_leaves_tops_undecided(
    tmp_path: Path,
    cache: Path,
    mixed_run: dict[str, Any],
) -> None:
    """The cap is set from the finished run's own ledgers: phase 1, the seven bases and two of
    their dearest episodes.  The same run under it stops in the tops."""
    source = mixed_run["folder"]
    first = sum(line["dollars"] for line in ledger(source / "phase1"))
    probe_lines = ledger(source / "probe")
    bases = [line["dollars"] for line in probe_lines if line["arm"] in BASES]
    cap = first + sum(bases) + 2 * max(bases)
    assert cap < first + sum(line["dollars"] for line in probe_lines)
    port = free_port()
    found = drive(tmp_path, mixed(), cache, cap=cap, concurrency=1, port=port)
    folder = found["folder"]
    assert found["code"] == 4, found["out"]
    status = read(folder / "status.json")
    assert status["stop"] == "spend_cap" and status["spent"] <= cap
    arms = read(folder / "outcome.json")["arms"][MODEL]
    assert all(arms[arm]["complete"] for arm in BASES)
    assert not all(arms[arm]["complete"] for arm in TOPS)
    undecided = [
        row["knob"]
        for row in read(folder / "outcome.json")["outcomes"]
        if row["per_model"][MODEL]["status"] == "undecided"
    ]
    assert undecided and "STOPPED (spend_cap)" in found["out"]
    again = drive(tmp_path, mixed(), cache, cap=cap, concurrency=1, port=port)
    assert again["code"] == 4 and again["chats"] == 0
    assert read(folder / "status.json")["spent"] == status["spent"]


# ---------------------------------------------------------------------------
# the one re-run of a void arm
# ---------------------------------------------------------------------------


def test_a_void_arm_is_re_run_once_and_the_re_run_is_recorded(tmp_path: Path, cache: Path) -> None:
    from poisson_tasks import knob_probe as probe

    seeds = small_design().probe_seeds
    broken = Behaviour.from_mapping({"error": {"similarity:s3": list(seeds)}})
    port = free_port()
    first = drive(tmp_path, broken, cache, port=port)
    arms = read(first["folder"] / "outcome.json")["arms"][MODEL]
    assert arms["similarity:s3"]["void"] and first["code"] == 0
    out = io.StringIO()
    with redirect_stdout(out):
        assert (
            probe.rerun_void(
                first["folder"],
                "similarity:s3",
                "the server answered 500 to every call",
                design=small_design(),
            )
            == 0
        )
    assert (first["folder"] / "void" / "similarity-s3-1" / "traces.jsonl").exists()
    assert not (first["folder"] / "probe" / "similarity-s3").exists()
    second = drive(tmp_path, Behaviour(), cache, port=port)
    assert second["code"] == 0
    result = read(second["folder"] / "outcome.json")
    s3 = result["arms"][MODEL]["similarity:s3"]
    assert s3["complete"] and not s3["void"]
    assert s3["rerun"]["cause"] == "the server answered 500 to every call"
    assert second["chats"] > 0
    err = io.StringIO()
    with redirect_stderr(err):
        assert (
            probe.rerun_void(first["folder"], "similarity:s3", "again", design=small_design()) == 1
        )
    assert "one re-run" in err.getvalue()


@pytest.fixture(autouse=True)
def _no_stray_key() -> Iterator[None]:
    yield
    import os

    assert os.environ.get("MODEL_API_KEY") in (None, ""), "the run left its key in the environment"
