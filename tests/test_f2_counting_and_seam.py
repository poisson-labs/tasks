"""Counting the calls the new plans are keyed on, the seam the four readers share, and `landed`
refused on the built-in tasks, frozen as tests.

The invariants (the 0.3.0 faults spec, F2.4, F2.6 and F2.7).  A timeouts or ratelimits plan is
keyed as faults' is, per tool over the calls that reach the tool server, so K3's counting episodes
give the same answers and verdicts with the kind's word in place of `unavailable`.  The server,
`verify` and the replay check read `surface.apply_planned` through the module, and a live episode
through the `null` harness replays byte for byte.  On the built-in tasks `landed` is not built
(ruled, Q2 option a): `tasks.generate` refuses both its levels in one line, the export's arm help
says so, and the ledger's refusal of a repeated stage call, the reason, is pinned as measured.

Faults' own tests are the pattern and are reused by name: `tests/test_k3_counting.py`'s episodes,
`tests/test_k3_live.py`'s endpoint and episode shape, `tests/k3_support.py`'s helpers.

Shapes decided here
-------------------

**1. The counting episodes are K3's, unchanged**, each with its level, its calls, the statuses
the server answers and the verdict; only the word moves.  A build that keyed the new plans by
position on the path, or let a refused call take a planned answer, gets one of them wrong.

**2. The replacement in the seam passes every further argument through**, as K3's does, so a build
may hand `apply_planned` the kind as an extra argument; ignoring the plan must still make all three
readers answer as if nothing were planned.

**3. The ledger's refusal is a guard, not a red test.**  It holds on `main` and must keep holding:
it is the measured reason for the ruling (the spec's M3), and a build that made a repeated stage
call land would make Q2's ruling wrong without failing anything else.  It is listed as such in the
session's red-set table.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from poisson_tasks import export, surface
from poisson_tasks import calibration as cal
from poisson_tasks.arms import arm_from_id
from poisson_tasks.engine import apply, init_state
from poisson_tasks.tasks import generate, scenario_for
from tests.f2_support import KINDS, Kind
from tests.helpers import needs_uv, run_module
from tests.k3_support import (
    APPLY_PLANNED,
    CARD_SEEDS,
    REFUSED,
    SPEC,
    UNAVAILABLE,
    a_read,
    answers,
    base,
    forwarded,
    gave_up,
    made,
    names,
    records_of,
    right,
    seq,
    status,
    trace_of,
    verdict_of,
)
from tests.test_k3_counting import EPISODES
from tests.test_k3_live import (  # noqa: F401 - the fixture is used by name
    _Scripted,
    planted,
    scripted_endpoint,
    tool_messages,
)

SEEDS = CARD_SEEDS[:4]
KIND_IDS = list(KINDS)


# --------------------------------------------------------------------------
# counting (F2.4)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", list(EPISODES))
@pytest.mark.parametrize("kind", list(KINDS.values()), ids=KIND_IDS)
def test_the_server_and_verify_count_each_tools_calls_that_reach_the_server(
    kind: Kind, name: str
) -> None:
    """Shape 1."""
    level, calls_of, statuses, (label, leaky) = EPISODES[name]
    worded = [kind.word if s == UNAVAILABLE else s for s in statuses]
    for seed in SEEDS:
        bundle = made(kind.arm(level), seed)
        calls = calls_of(bundle)
        reached = [
            answer
            for (n, a), answer in zip(calls, answers(bundle, calls), strict=True)
            if forwarded(bundle, n, a)
        ]
        assert [status(answer) for answer in reached] == worded, (seed, reached)
        got = verdict_of(bundle, calls)
        assert (got.strict_label, got.leaky_pass) == (label, leaky), (seed, got)


# --------------------------------------------------------------------------
# the seam (F2.6)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("kind", list(KINDS.values()), ids=KIND_IDS)
def test_the_server_verify_and_the_replay_check_read_apply_planned_through_the_module(
    kind: Kind, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Shape 2, at level 1: the first right call and then the second, with no retry."""
    bundle = made(kind.arm(1), SEEDS[0])
    first, second = right(bundle)
    calls = [first, second]
    assert [status(a) for a in answers(bundle, calls)] == [kind.word, "not_ready"]
    real = vars(surface)[APPLY_PLANNED]

    def unplanned(state: Any, counts: Any, call: Any, plan: Any, *rest: Any, **named: Any) -> Any:
        return real(state, counts, call, {}, *rest, **named)

    monkeypatch.setattr(surface, APPLY_PLANNED, unplanned)
    sent = answers(bundle, calls)
    assert [status(a) for a in sent] == ["ok", "ok"]
    assert verdict_of(bundle, calls).strict_label == "passed"
    (record,) = records_of(tmp_path, trace_of(bundle, calls, sent))
    assert (record.label, record.strict) == ("passed", True)


@needs_uv
@pytest.mark.parametrize("kind", list(KINDS.values()), ids=KIND_IDS)
def test_a_live_episode_takes_planned_answers_only_on_forwarded_calls_and_replays(
    kind: Kind, scripted_endpoint: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    """`tests/test_k3_live.py`'s episode at level 2 of each kind: two calls the harness refuses, a
    tool outside the block, a read with empty arguments, the right first stage call (its planned
    answer), a read, the right second stage call (its planned answer) and the same call again;
    the record gives up after a fault, and a planted change to any message the server sent is
    `replay_mismatch`."""
    import verifiers.v1 as vf

    seed = CARD_SEEDS[7]
    bundle = made(kind.arm(2), seed)
    (first, first_args), (second, second_args) = right(bundle)
    outside = next(name for name in SPEC.stage_tools if name not in names(bundle))
    read, read_args = a_read(bundle)
    _Scripted.script = [
        (first, "{" + json.dumps(first_args)),
        (first, "[]"),
        (outside, json.dumps(first_args)),
        (read, ""),
        (first, json.dumps(first_args)),
        (read, json.dumps(read_args)),
        (second, json.dumps(second_args)),
        (second, json.dumps(second_args)),
    ]
    monkeypatch.setenv("F2_KEY", "EMPTY")
    driver = run_module()
    spec = driver.spec_for(kind.arm(2))
    client = vf.EvalClientConfig(base_url=scripted_endpoint, api_key_var="F2_KEY")
    with driver.design(driver.Design(seeds=(seed,), n=1, k_values=(1,))):
        outcome = cal.run_arm(spec, output_dir=tmp_path, model="scripted", client=client)

    sent = tool_messages(outcome.run_dir)
    assert len(sent) == 8, sent
    assert all(line.startswith(REFUSED) for line in sent[:3]), sent[:3]
    reached = sent[3:]
    assert [status(line) for line in reached] == [
        "bad_args", kind.word, "ok", kind.word, "not_ready"]
    assert [seq(line) for line in reached] == [1, 2, 3, 4, 5]
    (record,) = cal.records_from_run(outcome.run_dir, model="scripted")
    assert (record.label, record.strict, record.leaky) == ("malformed_call", False, False)
    assert gave_up(record) is True
    traces = outcome.run_dir / cal.TRACES_FILE
    original = traces.read_bytes()
    for index in range(3, 8):
        planted(outcome.run_dir, index)
        (changed,) = cal.records_from_run(outcome.run_dir, model="scripted")
        assert (changed.label, changed.strict, changed.leaky) == (
            "replay_mismatch", False, False), index
        traces.write_bytes(original)


# --------------------------------------------------------------------------
# landed on the built-in tasks (F2.7, Q2 option a)
# --------------------------------------------------------------------------


def arm_help() -> str:
    description = export.ExportTasksetConfig.model_fields["arm"].description
    assert isinstance(description, str)
    return description


@pytest.mark.parametrize("level", [0, 1])
def test_generate_refuses_landed_in_one_line_naming_own_tools(level: int) -> None:
    """The arm is an arm (`tests/test_f2_arms.py`); the built-in generator refuses it, and builds
    the timeouts arm at the same level and seed beside it."""
    landed = arm_from_id(f"landed:l{level}")
    generate(arm_from_id(f"timeouts:o{level}"), CARD_SEEDS[0])
    with pytest.raises(ValueError) as refused:
        generate(landed, CARD_SEEDS[0])
    said = str(refused.value)
    assert "\n" not in said and "own tools" in said, said


def test_the_exports_arm_help_says_landed_is_on_own_tools_only() -> None:
    """The export's arm help gives `landed` a sentence of its own, as it gives each knob, and that
    sentence names own tools."""
    words = arm_help()
    assert "knob 'landed'" in words
    sentence = words[words.index("knob 'landed'"):].split(" knob '")[0]
    assert "own tools" in sentence, sentence


def test_the_ledger_refuses_a_repeated_stage_call_and_the_episode_passes() -> None:
    """Shape 3, the spec's M3 at three card seeds: B's last reference call made again answers
    `not_ready` and moves no record, and `verify` passes the episode."""
    for seed in CARD_SEEDS[:3]:
        b = base(seed)
        state = init_state(scenario_for(seed, b.split), b.seq_start)
        for call in b.reference_calls:
            state, _line = apply(state, call)
        again, line = apply(state, b.reference_calls[-1])
        assert status(line) == "not_ready", line
        assert again.records == state.records
        calls = [*b.reference_calls, b.reference_calls[-1]]
        got = verdict_of(b, calls)
        assert (got.strict_label, got.leaky_pass) == ("passed", True), (seed, got)
