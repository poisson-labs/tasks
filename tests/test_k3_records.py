"""What a run's records say about the faults knob: gave up after a fault, the replay check, and the
cell's figure, frozen as tests.

The invariants are K3.8 and the replay half of K3.4 of the knobs plan, from spec §6.4 and §6.5, and
the standing ruling of 2026-10-06 that the replay check takes in faults.  `records_from_run` fills
the record's `gave_up_after_fault` from the trace: `True` when the episode received an `unavailable`
from a tool and never called that tool again, `False` when it did not, and `None` on an arm that
plans no failure, which the written line leaves out.  A faults cell gives the share of its scored
episodes that gave up; it is printed and never gated.  On a faults arm `records_from_run` replays
the calls that reached the tool server, with the plan applied, and labels a disagreement with the
tool messages `replay_mismatch`, which scores nothing.

The traces here are real `vf.Trace` objects in verifiers 0.3.1's shape, scored offline by the task
and written by the wheel's own writer (`tests/k3_support.py`), with tool messages that are the tool
server's answers, run in this process, for each call the `null` harness forwards.

Shapes decided here
-------------------

**1. "An arm with no plan" is an arm `surface.fault_plan` plans nothing for**: every arm of another
knob, `faults:f0`, and the control `faults:f0+len(f4)`.  Their records carry `None`, so a cell
built from them has no figure to show for a failure no episode could meet.

**2. A fault received is a tool message whose line carries `unavailable` as its status.**  The
harness's own `error: ...` lines carry no status.

**3. Giving up is judged per failure**: a tool that failed, was called again and failed again with
no call after that was given up on.  Whether a later call the harness refused counts as calling the
tool again is yes/no 2 of this session's filing, pinned in `tests/test_k3_pending_refused_retry.py`.

**4. The figure's names are `gave_up_after_fault_count` and `gave_up_after_fault_share`**, as
`overshoot_count` and `overshoot_share` are named: the count of scored episodes that gave up and
its share of the scored episodes that carry a value.  A cell whose records carry none (every cell
of another knob, and both published cards) has neither key, so no published artifact moves.

**5. Printing it is the card's.**  The card that prints a faults cell is K10's design (spec §11 and
§12.1), so this file pins the figure and that nothing gates on it; where the card prints it is a
ruling of this session's filing.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from poisson_tasks import calibration as cal
from tests.k3_support import (
    CARD_SEEDS,
    CONTROL,
    GAVE_UP,
    answers,
    episode,
    faults,
    gave_up,
    made,
    record_with,
    records_of,
    right,
    trace_of,
    written,
)

SEED = CARD_SEEDS[3]


def first(bundle: Any) -> tuple[str, Any]:
    return right(bundle)[0]


def second(bundle: Any) -> tuple[str, Any]:
    return right(bundle)[1]


EPISODES: dict[str, tuple[int, Any, bool, str]] = {
    "gave up on the first stage at once": (1, lambda b: [first(b)], True, "wrong_state"),
    "retried and finished": (1, lambda b: [first(b), first(b), second(b)], False, "passed"),
    "retried the first stage, gave up on the second": (
        4,
        lambda b: [first(b), first(b), first(b), second(b)],
        True,
        "wrong_state",
    ),
    "met the second stage's failure first and retried both": (
        2,
        lambda b: [second(b), first(b), first(b), second(b)],
        False,
        "passed",
    ),
    "retried once and gave up after the second failure": (
        4,
        lambda b: [first(b), first(b)],
        True,
        "wrong_state",
    ),
}


@pytest.mark.parametrize("name", list(EPISODES))
def test_gave_up_after_fault_is_read_from_the_trace(name: str, tmp_path: Path) -> None:
    level, calls_of, expected, label = EPISODES[name]
    bundle = faults(level, SEED)
    record = episode(tmp_path, bundle, calls_of(bundle))
    assert (record.label, gave_up(record)) == (label, expected), record
    assert written(record)[GAVE_UP] is expected
    assert cal.EpisodeRecord.from_json(cal.EpisodeRecord.to_json(record)) == record


@pytest.mark.parametrize(
    "arm_id", ["faults:f0", CONTROL, "depth:d2", "distractor:r8@k16", "similarity:s2"]
)
def test_an_arm_that_plans_no_failure_records_none_and_writes_nothing(
    arm_id: str, tmp_path: Path
) -> None:
    """Shape 1, on the reference episode and on one that stops after the first call."""
    bundle = made(arm_id, SEED)
    ref = list(bundle.reference_calls)
    for calls in (ref, ref[:1]):
        record = episode(tmp_path, bundle, calls)
        assert gave_up(record) is None, (arm_id, record)
        assert GAVE_UP not in written(record)


def test_the_replay_check_covers_faults(tmp_path: Path) -> None:
    """`faults:f4`'s reference, answered by the tool server, reads as its verdict; a planted
    change in any tool message the server sent is `replay_mismatch`, strict and leaky false."""
    bundle = faults(4, SEED)
    calls = list(bundle.reference_calls)
    sent = answers(bundle, calls)
    (record,) = records_of(tmp_path, trace_of(bundle, calls, sent))
    assert (record.label, record.strict, record.leaky) == ("passed", True, True)
    for index, line in enumerate(sent):
        planted = list(sent)
        planted[index] = line[:-1] + ("0" if line[-1] != "0" else "1")
        (changed,) = records_of(tmp_path, trace_of(bundle, calls, planted))
        assert (changed.label, changed.strict, changed.leaky) == (
            "replay_mismatch",
            False,
            False,
        ), index


# --------------------------------------------------------------------------
# the cell's figure
# --------------------------------------------------------------------------


MODEL = "gpt-5-nano-2025-08-07"


def provenance() -> cal.Provenance:
    seeds = list(range(1000, 1000 + cal.S))
    return cal.Provenance(
        package_version="0.1.0",
        engine_hash="e" * 64,
        generator_hash="g" * 64,
        vocabulary_hash="v" * 64,
        verifiers_version="0.3.1",
        harness_id="null",
        models=[{"id": MODEL, "revision": MODEL, "endpoint_host": "h"}],
        decoding=dict(cal.DECODING),
        seed_list=seeds,
        seed_list_hash=hashlib.sha256(json.dumps(seeds).encode("utf-8")).hexdigest(),
        S=cal.S,
        n=5,
        k_values=[1, 2, 5],
        bootstrap_resamples=200,
        bootstrap_seed=20260922,
        delta_star=0.15,
        saturation_high=0.95,
        saturation_low=0.05,
        instrument_threshold=1.0,
        rate_read_date="2026-09-30",
        serving={MODEL: {"kind": "hosted", "endpoint_host": "h"}},
        budget=dict(cal.DEFAULT_BUDGET),
    )


def row(index: int, arm_id: str, given_up: bool | None, label: str = "wrong_state") -> Any:
    passed = label == "passed"
    return record_with(
        task_id=f"{arm_id}-{index // 5}",
        arm_id=arm_id,
        model=MODEL,
        seed=1000 + index // 5,
        attempt=index % 5,
        strict=passed,
        leaky=passed,
        label=label,
        turns=4,
        sampled_calls=3,
        prompt_tokens=3000,
        cached_input_tokens=0,
        completion_tokens=60,
        reasoning_tokens=0,
        **{GAVE_UP: given_up},
    )


def figures(cell: list[Any], tmp_path: Path) -> dict[str, Any]:
    """The cell's figures, from its records written and read back as a card's are."""
    path = cal.write_records(cell, tmp_path / f"episodes-{len(list(tmp_path.iterdir()))}.jsonl")
    kept = cal.read_records(path)
    built = cal.build_artifact({(kept[0].arm_id, MODEL): kept}, provenance())
    cells: list[dict[str, Any]] = built.cells
    return cells[0]


def test_a_faults_cell_gives_the_share_that_gave_up_and_gates_nothing(tmp_path: Path) -> None:
    """Ten scored episodes of `faults:f4`, three that gave up, four that failed without giving up,
    three passes, and an instrument failure that gave up and counts in nothing.  A cell where every
    episode gave up is built like any other.  A depth cell, whose records carry no value, has no
    such figure."""
    cell = (
        [row(i, "faults:f4", True) for i in range(3)]
        + [row(i, "faults:f4", False) for i in range(3, 7)]
        + [row(i, "faults:f4", False, "passed") for i in range(7, 10)]
        + [row(10, "faults:f4", True, "api_error")]
    )
    got = figures(cell, tmp_path)
    assert (got["gave_up_after_fault_count"], got["gave_up_after_fault_share"]) == (3, 0.3)
    every = figures([row(i, "faults:f4", True) for i in range(10)], tmp_path)
    assert (every["gave_up_after_fault_count"], every["gave_up_after_fault_share"]) == (10, 1.0)
    unmarked = [dataclasses.replace(r, **{GAVE_UP: None}) for r in cell]
    depth = figures([dataclasses.replace(r, arm_id="depth:d3") for r in unmarked], tmp_path)
    assert not [key for key in depth if key.startswith("gave_up")], depth
