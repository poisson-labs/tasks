"""Phase 1's no-call check on the base arms, as amended on 2026-10-13, and the recorded re-gate.

The ruling (2026-10-13, option B1, every part):

(a) The base arms' no-call check in phase 1 becomes the cards' share rule, pooled over the 21 base
    episodes: more than 0.10 of them without a tool call stops phase 1, so 3 or more stop.  Every
    other phase 1 check stays exactly as it is, and the cards' own `plumbing_gate` is unchanged.
(c) A recorded re-gate step re-reads an existing folder's phase 1 episodes under the new rule.  It
    runs no episode and makes no call, keeps the original failed verdict on record beside the new
    one, needs a reason, and is allowed once per folder.  `run` alone still refuses a failed phase
    1, and a folder whose re-gate also fails stays final.  After a passing re-gate, `run` goes on
    with the probe in the same folder, within the same cap, phase 1's spend counting toward it.
(d) It covers Qwen through the shared code: a Qwen phase 1 that passed still passes, and nothing
    here changes what Qwen's run reads or records.
(e) `outcome.md` carries a disclosure line saying what changed, when and why, with the counts.

The runs here are the smaller design (`k9_support.small_design`) against `tests/k9_fake.py`, inside
the network guard.  A folder that failed "as the first run did" is made by the driver itself with
the first gate put back (`k9_regate_support.old_phase1_verdict`, the gate as built at d5c93aa) and
the fake answering chosen base episodes in plain text.
"""

from __future__ import annotations

import hashlib
import io
import json
import random
import socket
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any

import pytest

from poisson_tasks import calibration as cal
from tests.k9_fake import running
from tests.k9_regate_support import (
    ONE,
    PHASE1,
    THREE,
    Failed,
    copy_of,
    drive,
    failed_phase1,
    ledger_total,
    old_phase1_verdict,
    phase1_records,
    regate,
    spread_silent,
    tree,
)
from tests.k9_support import (
    ARMS,
    BASES,
    CONTROLS,
    MODEL,
    OTHER,
    TOPS,
    episode,
    every_arm,
    model_run,
    needs_uv,
    small_design,
)

REASON = (
    "gpt-5-nano asked for the record id in plain text in 1 of 21 base episodes, a reply its "
    "published card shows in 2.3% of episodes; re-read under the cards' share rule"
)
NO_CALL = "made no tool call"
"""The words both gates put in their no-call reason, as the frozen phase 1 tests read them."""


def verdict(records: dict[str, list[cal.EpisodeRecord]], **kwargs: Any) -> Any:
    from poisson_tasks import knob_probe as probe

    return probe.phase1_verdict(records, kwargs.pop("tallies", {}), **kwargs)


def no_call_reasons(reasons: tuple[str, ...]) -> list[str]:
    return [r for r in reasons if r.startswith("base arms: ") and NO_CALL in r]


# ---------------------------------------------------------------------------
# (a) the rule: the share of the 21, pooled
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("silent", [0, 1, 2, 3])
def test_no_calls_on_the_base_arms_stop_phase_1_at_three_of_21(silent: int) -> None:
    """0, 1 and 2 of the 21 base episodes without a tool call pass; 3, a share of 0.143, stop.
    The three sit on three base arms, one at each seed, so they stop only pooled."""
    from poisson_tasks import knob_probe as probe

    assert probe.PHASE1_NO_CALL == cal.NO_CALL_THRESHOLD == 0.10
    found = verdict(phase1_records(spread_silent(silent)))
    assert found.bases.episodes == 21 and found.bases.no_call == silent
    assert found.passed is (silent < 3), found.reasons
    assert found.bases.passed is (silent < 3)
    assert len(no_call_reasons(found.reasons)) == (1 if silent >= 3 else 0)
    assert found.plumbing == {}


def test_the_boundary_is_exactly_three_and_the_first_runs_one_passes() -> None:
    """The first run's own episode (`block:k8`, phase 1's first seed) alone passes; with two more
    on other base arms it stops, and with one more it does not."""
    two = verdict(phase1_records(ONE + (("history:t0", 601375552),)))
    three = verdict(phase1_records(THREE))
    assert verdict(phase1_records(ONE)).passed
    assert two.passed and two.bases.no_call == 2
    assert not three.passed and three.bases.no_call == 3
    assert three.reasons == tuple(no_call_reasons(three.reasons))


def test_the_rule_is_the_share_above_the_cards_threshold_not_a_count_of_three() -> None:
    """On a phase 1 of ten seeds (70 base episodes) 7 without a call is a share of exactly 0.10,
    which the cards publish (more than 0.10 refuses), and 8 stop."""
    from poisson_tasks import knob_probe as probe

    seeds = tuple(probe.PROBE_SEEDS[:10])
    design = probe.Design(arms=probe.ARMS, phase1_seeds=seeds, probe_seeds=probe.PROBE_SEEDS[:2])
    at = verdict(phase1_records(spread_silent(7, seeds), seeds=seeds), design=design)
    above = verdict(phase1_records(spread_silent(8, seeds), seeds=seeds), design=design)
    assert at.bases.episodes == 70 and at.passed, at.reasons
    assert above.bases.no_call == 8 and not above.passed
    assert len(no_call_reasons(above.reasons)) == 1


def test_no_calls_on_tops_and_controls_still_never_stop_phase_1() -> None:
    every_other = tuple((arm, seed) for arm in TOPS + CONTROLS for seed in PHASE1)
    found = verdict(phase1_records(every_other + ONE + (("faults:f0", 601375552),)))
    assert found.passed and found.bases.no_call == 2, found.reasons


OTHER_FAILURES: dict[str, dict[str, Any]] = {
    "a base episode labelled": {"labelled": [("history:t0", 601375552)]},
    "a top episode labelled": {"labelled": [("similarity:s3", 1180681854)]},
    "a base episode missing": {"skip": [("spread:p1", 2652385879)]},
    "a control episode missing": {"skip": [("shape:w1+len(w4)", 601375552)]},
    "most bases short": {"short": ["similarity:s0", "faults:f0", "history:t0", "block:k8"]},
    "a base tally": {"tallies": {"block:k8": {"api_error": 1}}},
    "a control tally": {"tallies": {"arguments:a2+len(a8)": {"wall_timeout": 2}}},
}


@pytest.mark.parametrize("silent", [1, 3])
@pytest.mark.parametrize("failure", sorted(OTHER_FAILURES))
def test_every_other_phase_1_check_is_unchanged(failure: str, silent: int) -> None:
    """Beside one or three no-calls, each other failure stops phase 1 with exactly the reasons the
    first gate gave for it; only the no-call reason moves (gone at one, the share's at three)."""
    options = dict(OTHER_FAILURES[failure])
    tallies = options.pop("tallies", {})
    records = phase1_records(spread_silent(silent), **options)
    found = verdict(records, tallies=tallies)
    first = old_phase1_verdict(records, tallies)
    assert not found.passed and not first.passed
    kept = [r for r in first.reasons if r not in no_call_reasons(first.reasons)]
    assert [r for r in found.reasons if r not in no_call_reasons(found.reasons)] == kept
    assert len(no_call_reasons(found.reasons)) == (1 if silent >= 3 else 0)
    assert found.plumbing == first.plumbing


def test_the_cards_own_plumbing_gate_is_unchanged() -> None:
    """The cards' phase 1 (six episodes at `depth:d3`) still stops on one episode without a tool
    call, and the gate read alone on the probe's 21 base episodes still stops on one."""
    six = [episode("depth:d3", seed, attempt, passed=True, calls=3) for seed in PHASE1
           for attempt in (0, 1)]
    six[3] = episode("depth:d3", PHASE1[1], 1, calls=0)
    card = cal.plumbing_gate(six)
    assert not card.passed and card.reasons == ("1 of 6 episodes made no tool call",)
    assert cal.plumbing_gate([r for r in six if r.sampled_calls]).passed
    records = phase1_records(ONE)
    pooled = cal.plumbing_gate([row for arm in BASES for row in records[arm]])
    assert not pooled.passed and pooled.reasons == ("1 of 21 episodes made no tool call",)
    assert verdict(records).passed


# ---------------------------------------------------------------------------
# (d) Qwen: what passed still passes, and what its run reads and records is unmoved
# ---------------------------------------------------------------------------


def test_every_phase_1_the_first_gate_passed_still_passes_and_only_one_or_two_no_calls_change() -> (
    None
):
    """Over 600 made-up phase 1s (no-calls, short episodes, labels, missing episodes and tallies on
    any arm), the amended gate passes every one the first passed, and its reasons are the first's
    with the no-call reason dropped at one or two and kept, as the share, at three or more."""
    rng = random.Random(20261013)
    passed_both = changed = 0
    for _ in range(600):
        silent = [(a, s) for a in ARMS for s in PHASE1 if rng.random() < 0.04]
        labelled = [(a, s) for a in ARMS for s in PHASE1 if rng.random() < 0.004]
        skip = [(a, s) for a in ARMS for s in PHASE1 if rng.random() < 0.004]
        short = [a for a in ARMS if rng.random() < 0.15]
        tallies = {a: {"api_error": 1} for a in ARMS if rng.random() < 0.005}
        records = phase1_records(silent, labelled=labelled, skip=skip, short=short)
        first, found = old_phase1_verdict(records, tallies), verdict(records, tallies=tallies)
        base_silent = sum(1 for row in (r for a in BASES for r in records[a])
                          if row.sampled_calls == 0)
        if first.passed:
            assert found.passed
            passed_both += 1
        others = [r for r in first.reasons if r not in no_call_reasons(first.reasons)]
        assert [r for r in found.reasons if r not in no_call_reasons(found.reasons)] == others
        assert len(no_call_reasons(found.reasons)) == (1 if base_silent >= 3 else 0)
        changed += found.passed and not first.passed
    assert passed_both > 50 and changed > 50, (passed_both, changed)


def notebook_ctx(tmp_path: Path) -> Any:
    from poisson_tasks import calibration_run as run

    ctx = run.Context(
        local=tmp_path / "local",
        durable=tmp_path / "durable",
        port=1,
        mirror_interval=3600.0,
        design="knob-probe",
    )
    ctx.local.mkdir(parents=True)
    return ctx


def notebook_phase1(
    tmp_path: Path, mp: pytest.MonkeyPatch, records: dict[str, list[cal.EpisodeRecord]]
) -> tuple[int, dict[str, Any]]:
    """The notebook's knob phase 1 step (`calibration_run.knob_phase1`) on `records`, with the
    server, the episodes and the trace reading stood in for."""
    from poisson_tasks import calibration_run as run

    ctx = notebook_ctx(tmp_path)
    facts = {arm: {"episodes": 3, "max_prompt_tokens": 4000, "context_stops": 0} for arm in ARMS}
    mp.setattr(run, "_serving", lambda ctx: {"stack_version": "0.29.0+cu129", "gpu": "L4",
                                             "flags": [], "template_sha256": "b4d28698"})
    mp.setattr(run, "_run_arms", lambda *args, **kwargs: None)
    mp.setattr(run, "_knob_rows", lambda root, arms, served: (records, {}, facts))
    code = run.knob_phase1(ctx)
    return code, json.loads((ctx.local / "phase1.json").read_text())


@pytest.mark.parametrize(("silent", "code"), [(0, 0), (1, 0), (2, 0), (3, 2)])
def test_the_qwen_notebooks_phase_1_reads_the_same_amended_rule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, silent: int, code: int
) -> None:
    found, report = notebook_phase1(
        tmp_path, monkeypatch, phase1_records(spread_silent(silent), model=OTHER)
    )
    assert (found, report["passed"]) == (code, code == 0), report["reasons"]
    assert len(no_call_reasons(tuple(report["reasons"]))) == (1 if silent >= 3 else 0)


def test_a_qwen_phase_1_that_passed_is_read_back_and_not_gated_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A resumed Qwen run finds its passed phase 1 on disk and goes on: nothing is run, nothing
    is gated again, and the stored verdict is not rewritten."""
    from poisson_tasks import calibration_run as run
    from poisson_tasks import knob_probe as probe

    ctx = notebook_ctx(tmp_path)
    stored = json.dumps({"passed": True, "reasons": [], "episodes": 54}, indent=2) + "\n"
    (ctx.local / "phase1.json").write_text(stored)

    def refused(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("a passed phase 1 was run or gated again")

    monkeypatch.setattr(run, "_run_arms", refused)
    monkeypatch.setattr(run, "_knob_rows", refused)
    monkeypatch.setattr(probe, "phase1_verdict", refused)
    assert run.knob_phase1(ctx) == 0
    assert (ctx.local / "phase1.json").read_text() == stored


def write_outcome_of(folder: Path, models: dict[str, dict[str, Any]]) -> dict[str, str]:
    """Each model's records written and read back, the outcome analysed and written, as the
    notebook's phase 3 and the `analyse` step do; the sha256 of the two files written."""
    from poisson_tasks import knob_probe as probe

    read: dict[str, dict[str, Any]] = {}
    for model, given in models.items():
        records = folder / model.split("/")[0].split("-")[0]
        probe.write_model_records(
            records, given["records"], given["tallies"], reruns=given["reruns"],
            facts=given["facts"],
        )
        read[model] = probe.read_model_records(records)
    outcome = probe.analyse(read, design=probe.DESIGN)
    probe.write_outcome(folder, outcome)
    return {name: hashlib.sha256((folder / name).read_bytes()).hexdigest()
            for name in ("outcome.json", "outcome.md")}


def qwen_run() -> dict[str, Any]:
    """A Qwen run as the notebook's phase 3 records it: some knobs bite, one arm is void."""
    cells = every_arm(
        {"similarity:s3": 30, "block:k64": 20, "faults:f4": 36, "arguments:a8": 50,
         "shape:w4": 30, "spread:p4": 54},
        model=OTHER,
        options={"history:t2400": {"instrument": [(0, 0), (1, 0), (2, 0)]},
                 "block:k64": {"no_call": range(30, 40)}},
    )
    return model_run(cells, facts={
        "model": OTHER, "concurrency": 128, "dollars": None, "rates": None,
        "wall_clock_hours": 2.0, "elapsed_s": 3600.0, "stop": None, "per_arm_facts": {},
    })


def nano_run(**facts: Any) -> dict[str, Any]:
    cells = every_arm({"similarity:s3": 20, "faults:f4": 54, "history:t2400": 40},
                      options={"spread:p1": {"no_call": [5]}})
    return model_run(cells, facts={
        "model": MODEL, "base_url": "https://api.openai.com/v1", "concurrency": 128,
        "concurrencies": [128], "dollars": 1.7, "stop": None, **facts,
        "rates": {"input_rate": 0.05, "cached_input_rate": 0.005, "output_rate": 0.4},
    })


def test_an_outcome_without_a_re_gate_is_byte_for_byte_what_main_wrote(tmp_path: Path) -> None:
    """Qwen's outcome on Qwen alone (what the notebook writes) and the two models' outcome (the
    `analyse` step), neither re-gated: the sha256 of each file as `main` at 0b983ef wrote it."""
    alone = write_outcome_of(tmp_path / "alone", {OTHER: qwen_run()})
    both = write_outcome_of(tmp_path / "both", {MODEL: nano_run(), OTHER: qwen_run()})
    assert alone == {
        "outcome.json": "4be72b3829addc1271db3f5b73020432824ec7787d74b1d0314b982939ce1d69",
        "outcome.md": "77ca245253cecded0885816f8be85854e5402c98916ca048b3797ca87d35d418",
    }
    assert both == {
        "outcome.json": "5f954330e61a5096e1e57ec252763cac53e84bf7fdef2bbcace069436e7aa52c",
        "outcome.md": "36ba002023b2a36f93d5bdc8c98b65c710b5c64e3d62dcfae388882eb027b0d7",
    }


# ---------------------------------------------------------------------------
# (c) the re-gate
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def cache(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("k9-regate-cache") / "registry"


@pytest.fixture(scope="module")
def one(tmp_path_factory: pytest.TempPathFactory, cache: Path) -> Failed:
    """Phase 1 failed under the first gate on 1 of 21, as the first gpt-5-nano run did."""
    return failed_phase1(tmp_path_factory.mktemp("k9-regate-one"), ONE, cache)


@pytest.fixture(scope="module")
def three(tmp_path_factory: pytest.TempPathFactory, cache: Path) -> Failed:
    """Phase 1 failed under the first gate on 3 of 21."""
    return failed_phase1(tmp_path_factory.mktemp("k9-regate-three"), THREE, cache)


def refused(code: int, err: str) -> bool:
    return code == 1 and err.count("\n") == 1 and err.startswith("error: ")


@needs_uv
def test_the_re_gate_refuses_without_a_reason(tmp_path: Path, one: Failed) -> None:
    folder = copy_of(one, tmp_path)
    before = tree(folder)
    for blank in ("", "   ", "\n\t"):
        code, _, err = regate(folder, blank)
        assert refused(code, err), (code, err)
        assert tree(folder) == before
    assert regate(folder, REASON)[0] == 0


@needs_uv
def test_the_re_gate_is_allowed_once_per_folder(tmp_path: Path, one: Failed) -> None:
    from poisson_tasks import knob_probe as probe

    folder = copy_of(one, tmp_path)
    assert regate(folder, REASON)[0] == 0
    after = tree(folder)
    code, _, err = regate(folder, "a second reading, with another reason")
    assert refused(code, err), (code, err)
    assert tree(folder) == after
    assert json.loads((folder / probe.REGATE_FILE).read_text())["reason"] == REASON


@needs_uv
def test_the_re_gate_refuses_a_folder_with_no_phase_1(tmp_path: Path, one: Failed) -> None:
    """No folder, a folder with no probe in it, and a probe whose phase 1 has no verdict (it
    stopped before the end, so `run` resumes it) are refused, writing nothing; so is a phase 1
    that passed, which has nothing to re-gate.  The same folder with its verdict is re-gated."""
    from poisson_tasks import knob_probe as probe

    assert refused(*regate(tmp_path / "nowhere", REASON)[::2])
    assert not (tmp_path / "nowhere").exists()
    (tmp_path / "empty").mkdir()
    assert refused(*regate(tmp_path / "empty", REASON)[::2])
    assert tree(tmp_path / "empty") == {}
    folder = copy_of(one, tmp_path)
    verdict_bytes = (folder / "phase1.json").read_bytes()
    (folder / "phase1.json").unlink()
    (folder / "status.json").write_text(json.dumps({"phase": 1, "verdict": "stopped"}))
    before = tree(folder)
    assert refused(*regate(folder, REASON)[::2])
    assert tree(folder) == before
    passed = json.loads(verdict_bytes)
    (folder / "phase1.json").write_text(json.dumps({**passed, "passed": True, "reasons": []}))
    before = tree(folder)
    assert refused(*regate(folder, REASON)[::2])
    assert tree(folder) == before
    (folder / "phase1.json").write_bytes(verdict_bytes)
    assert regate(folder, REASON)[0] == 0 and (folder / probe.REGATE_FILE).exists()


@needs_uv
def test_the_re_gate_refuses_episodes_that_are_not_the_ones_phase_1_was_gated_on(
    tmp_path: Path, one: Failed
) -> None:
    """It reads the same episodes the first verdict read: with one arm's episodes gone, or a
    folder of another design, it refuses and writes nothing."""
    import shutil

    from poisson_tasks import knob_probe as probe

    folder = copy_of(one, tmp_path)
    shutil.rmtree(folder / "phase1" / "shape-w4")
    before = tree(folder)
    assert refused(*regate(folder, REASON)[::2])
    assert tree(folder) == before
    other = copy_of(one, tmp_path / "other")
    before = tree(other)
    assert refused(*regate(other, REASON, design=probe.DESIGN)[::2])
    assert tree(other) == before
    assert regate(other, REASON)[0] == 0


@contextmanager
def no_call_allowed(mp: pytest.MonkeyPatch) -> Iterator[None]:
    """Every way a step could reach a model fails the test: a socket opened, a process started,
    the run engine, the free key check, the key read."""
    from poisson_tasks import knob_probe as probe
    from poisson_tasks import providers, runs

    def called(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("the re-gate made a call")

    mp.setattr(socket.socket, "connect", called)
    mp.setattr(socket.socket, "connect_ex", called)
    mp.setattr(socket, "create_connection", called)
    mp.setattr(subprocess, "Popen", called)
    mp.setattr(runs, "run_plan", called)
    mp.setattr(providers, "check_key", called)
    mp.setattr(probe, "load_key", called)
    yield


@needs_uv
def test_the_re_gate_runs_no_episode_and_makes_no_call(
    tmp_path: Path, one: Failed, cache: Path
) -> None:
    """With the fake on the folder's own endpoint and every way to a model failing the test, the
    re-gate passes, the fake sees no request, and phase 1's episodes and ledger are unchanged."""
    folder = copy_of(one, tmp_path)
    design = small_design()
    phase1_before = tree(folder / "phase1")
    with running(design.arms, [*design.phase1_seeds, *design.probe_seeds], drive_behaviour(),
                 cache=cache, port=one.port) as fake:
        with pytest.MonkeyPatch.context() as mp, no_call_allowed(mp):
            code, out, err = regate(folder, REASON)
        assert (fake.posts, fake.gets) == ([], [])
    assert code == 0, out + err
    assert tree(folder / "phase1") == phase1_before
    assert ledger_total(folder / "phase1") == pytest.approx(one.spent, abs=1e-12)
    assert not (folder / "probe").exists()


def drive_behaviour() -> Any:
    from tests.k9_support import mixed

    return mixed()


@needs_uv
def test_the_re_gate_keeps_the_first_verdict_beside_the_new_one(
    tmp_path: Path, one: Failed
) -> None:
    from poisson_tasks import knob_probe as probe

    folder = copy_of(one, tmp_path)
    first = (folder / "phase1.json").read_bytes()
    code, out, err = regate(folder, REASON)
    assert code == 0 and err == "", err
    assert (folder / "phase1.json").read_bytes() == first
    held = json.loads(first)
    record = json.loads((folder / probe.REGATE_FILE).read_text())
    assert record["original"] == {
        "passed": False,
        "reasons": held["reasons"],
        "spent": held["spent"],
        "episodes": held["episodes"],
    }
    assert held["reasons"] == ["base arms: 1 of 21 episodes made no tool call"]
    assert record["passed"] is True and record["reasons"] == []
    assert (record["no_call"], record["episodes"], record["threshold"]) == (1, 21, 0.10)
    assert record["rule_date"] == "2026-10-13" and record["reason"] == REASON
    assert record["when"] and record["per_episode"] == held["per_episode"]
    assert held["reasons"][0] in out and "1 of 21" in out


@needs_uv
def test_a_re_gate_that_fails_too_is_final(tmp_path: Path, three: Failed, cache: Path) -> None:
    """3 of 21 fails the share rule as well: the re-gate says so (exit 2) and records it, `run`
    then stops on it without a model call, and no second re-gate is allowed."""
    from poisson_tasks import knob_probe as probe

    folder = copy_of(three, tmp_path)
    code, out, _ = regate(folder, REASON)
    record = json.loads((folder / probe.REGATE_FILE).read_text())
    assert code == 2 and record["passed"] is False and record["no_call"] == 3
    assert len(no_call_reasons(tuple(record["reasons"]))) == 1
    before = tree(folder)
    found = drive(tmp_path, folder, port=three.port, cache=cache)
    assert found["code"] == 2 and found["chats"] == 0, found["out"] + found["err"]
    assert "phase 1 failed in this folder" in found["out"]
    assert not (folder / "probe").exists() and not (folder / "outcome.json").exists()
    assert tree(folder) == {**before, "record.json": (folder / "record.json").read_bytes()}
    assert refused(*regate(folder, "again")[::2])


@needs_uv
def test_run_alone_still_refuses_a_phase_1_that_failed_and_was_not_re_gated(
    tmp_path: Path, one: Failed, cache: Path
) -> None:
    """The first run's case, 1 of 21 failed under the first gate: `run` does not read it again
    under the new rule.  It stops on the stored verdict, with no model call."""
    folder = copy_of(one, tmp_path)
    first = (folder / "phase1.json").read_bytes()
    found = drive(tmp_path, folder, port=one.port, cache=cache)
    assert found["code"] == 2 and found["chats"] == 0, found["out"] + found["err"]
    assert "phase 1 failed in this folder" in found["out"]
    assert (folder / "phase1.json").read_bytes() == first
    assert not (folder / "probe").exists()


@pytest.fixture(scope="module")
def resumed(
    tmp_path_factory: pytest.TempPathFactory, one: Failed, cache: Path
) -> dict[str, Any]:
    """The 1-of-21 folder re-gated, then `run` with a $5.00 cap: the probe in the same folder."""
    where = tmp_path_factory.mktemp("k9-regate-resumed")
    folder = copy_of(one, where)
    first = tree(folder / "phase1")
    verdict_bytes = (folder / "phase1.json").read_bytes()
    assert regate(folder, REASON)[0] == 0
    regated = (folder / "phase1-regate.json").read_bytes()
    found = drive(where, folder, port=one.port, cache=cache)
    return {**found, "folder": folder, "phase1": first, "verdict": verdict_bytes,
            "regated": regated}


@needs_uv
def test_run_after_a_passing_re_gate_goes_on_in_the_same_folder(
    resumed: dict[str, Any], one: Failed
) -> None:
    folder = resumed["folder"]
    assert resumed["code"] == 0, resumed["out"] + resumed["err"]
    assert resumed["chats"] > 0
    record = json.loads((folder / "record.json").read_text())
    assert len(record["invocations"]) == 2
    assert tree(folder / "phase1") == resumed["phase1"]
    assert (folder / "phase1.json").read_bytes() == resumed["verdict"]
    assert (folder / "phase1-regate.json").read_bytes() == resumed["regated"]
    rows = (folder / "records" / "episodes.jsonl").read_text().splitlines()
    assert len(rows) == 72
    assert "phase 1 failed in this folder" not in resumed["out"]
    assert "re-gate" in resumed["out"]


@needs_uv
def test_run_after_a_re_gate_counts_phase_1s_spend_toward_the_cap(
    resumed: dict[str, Any], one: Failed, tmp_path: Path, cache: Path
) -> None:
    """The finished run's spend is phase 1's and the probe's ledgers together.  The same run under
    a cap of phase 1's spend plus half the probe's stops at the cap with the probe's ledger inside
    what phase 1 left; had phase 1's spend not counted, the probe would have had room to finish.
    It runs one episode at a time, as the frozen cap test does: at eight at once the run engine
    lets the episodes already in flight finish past its cap."""
    folder = resumed["folder"]
    probe_spend = ledger_total(folder / "probe")
    status = json.loads((folder / "status.json").read_text())
    assert status["spent"] == pytest.approx(one.spent + probe_spend, abs=1e-9)
    facts = json.loads((folder / "records" / "facts.json").read_text())
    assert facts["dollars"] == status["spent"]
    assert one.spent + probe_spend / 2 > probe_spend * 1.2
    tight = copy_of(one, tmp_path)
    assert regate(tight, REASON)[0] == 0
    cap = one.spent + probe_spend / 2
    found = drive(tmp_path, tight, port=one.port, cache=cache, cap=cap, concurrency=1)
    held = json.loads((tight / "status.json").read_text())
    assert found["code"] == 4 and held["stop"] == "spend_cap", found["out"]
    assert ledger_total(tight / "probe") <= cap - one.spent + 1e-12
    assert held["spent"] <= cap


# ---------------------------------------------------------------------------
# (e) the disclosure
# ---------------------------------------------------------------------------


@needs_uv
def test_the_outcome_carries_the_disclosure_line_with_the_counts(
    resumed: dict[str, Any],
) -> None:
    folder = resumed["folder"]
    page = (folder / "outcome.md").read_text()
    lines = [line for line in page.splitlines() if "re-gated" in line.lower()]
    assert len(lines) == 1, lines
    line = lines[0]
    for part in (MODEL, "base arms: 1 of 21 episodes made no tool call", "2026-10-13",
                 "1 of 21", "10%", "3 or more", REASON, "No episode was run again"):
        assert part in line, part
    facts = json.loads((folder / "records" / "facts.json").read_text())["phase1_regate"]
    assert (facts["no_call"], facts["episodes"], facts["passed"]) == (1, 21, True)
    assert facts["original_reasons"] == ["base arms: 1 of 21 episodes made no tool call"]


@needs_uv
def test_the_two_models_outcome_carries_the_line_for_the_re_gated_model_alone(
    resumed: dict[str, Any], tmp_path: Path
) -> None:
    """The `analyse` step on gpt-5-nano's records and Qwen's: one line, gpt-5-nano's."""
    from poisson_tasks import knob_probe as probe

    out = io.StringIO()
    qwen = tmp_path / "qwen"
    given = qwen_run()
    probe.write_model_records(qwen, given["records"], given["tallies"], reruns=[],
                              facts=given["facts"])
    with redirect_stdout(out), redirect_stderr(io.StringIO()):
        code = probe.main(["analyse", "--records", str(resumed["folder"] / "records"),
                           "--records", str(qwen), "--out", str(tmp_path / "out")])
    assert code == 0
    page = (tmp_path / "out" / "outcome.md").read_text()
    lines = [line for line in page.splitlines() if "re-gated" in line.lower()]
    assert len(lines) == 1 and MODEL in lines[0] and OTHER not in lines[0]


# ---------------------------------------------------------------------------
# the command
# ---------------------------------------------------------------------------


def test_the_re_gate_is_a_step_of_the_module_with_a_required_reason(tmp_path: Path) -> None:
    from poisson_tasks import knob_probe as probe

    args = probe.build_parser().parse_args(["regate", "--folder", "f", "--reason", "why"])
    assert (args.command, str(args.folder), args.reason) == ("regate", "f", "why")
    with pytest.raises(SystemExit), redirect_stderr(io.StringIO()):
        probe.build_parser().parse_args(["regate", "--folder", "f"])
    err = io.StringIO()
    with redirect_stderr(err), redirect_stdout(io.StringIO()):
        nowhere = probe.main(["regate", "--folder", str(tmp_path / "x"), "--reason", "why"])
    assert refused(nowhere, err.getvalue()) and str(tmp_path / "x") in err.getvalue()
