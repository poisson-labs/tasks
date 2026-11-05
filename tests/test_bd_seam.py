"""The seam `baddata` answers through on the built-in tasks: the tool server, `verify` and the replay
check read one function through the module, and a live episode replays, frozen as tests.

The invariant (the 0.4.0 stale-data spec, BD.6).  The server, `verify` and the replay check read
`surface.spread_answers` and `surface.apply_planned` through the module, none edited, and a
replacement that ignores the sequence makes all three answer as if nothing were bad.  A live episode
through the `null` harness at `baddata:b2` (trust, read again, a page off, a harness-refused call)
replays to the server's observations byte for byte; a planted change to any sent message is
`replay_mismatch`; `baddata` is in `_REPLAY_CHECKED`.

Faults' own seam tests are the pattern: `tests/test_f2_counting_and_seam.py`, `tests/test_k3_live.py`.

Shapes decided here
-------------------

**1. A read moves no record, so `verify`'s verdict cannot show which answer it gave.**  So the case for
`verify` counts the calls the replacement received while the verdict was made, beside the verdict; the
server's and the replay check's show in what they answer.

**2. The replacement passes every further argument through**, as 0.3.0's does, so a build may hand
either function more.  It drops every entry of a read but its last, which is what "ignoring the
sequence" leaves: the true answer on every call.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from poisson_tasks import calibration as cal
from poisson_tasks import surface
from tests.bd_support import (
    APPLY_PLANNED,
    SPREAD_ANSWERS,
    another_page,
    bad_read,
    baddata,
    figures,
    payload_of,
    read_pairs,
    stage_calls_on,
    target_and_decoy,
    the_two_reads,
)
from tests.helpers import needs_uv, run_module
from tests.k3_support import (
    CARD_SEEDS,
    REFUSED,
    answers,
    records_of,
    right,
    seq,
    status,
    trace_of,
    verdict_of,
)
from tests.test_k3_live import (  # noqa: F401 - the fixture is used by name
    _Scripted,
    planted,
    scripted_endpoint,
    tool_messages,
)

SEED = CARD_SEEDS[7]


def last_entries(spread: Any) -> Any:
    """Every entry of each read but its last dropped: the sequence ignored."""
    if spread is None:
        return None
    by_call: dict[str, Any] = {}
    for entry in spread:
        by_call[json.dumps([entry[0], entry[1]], sort_keys=True)] = entry
    return tuple(by_call.values())


@pytest.mark.parametrize("name", [APPLY_PLANNED, SPREAD_ANSWERS])
def test_a_replacement_that_ignores_the_sequence_makes_all_three_answer_as_if_nothing_were_bad(
    name: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Shapes 1 and 2, on the trusting episode at `b2`.  Beside it, with nothing replaced, the first
    answer is the bad one, and the replayed trace made under the replacement is `replay_mismatch`."""
    bundle = baddata(2, SEED)
    target, _decoy = target_and_decoy(bundle)
    calls = [*the_two_reads(bundle), *stage_calls_on(bundle, target)]
    bad, true = [payload_of(line) for call, line in read_pairs(bundle) if call == bad_read(bundle)]
    assert payload_of(answers(bundle, calls)[0]) == bad
    real = vars(surface)[name]
    received: list[int] = []

    def ignoring(*args: Any, **named: Any) -> Any:
        received.append(1)
        if name == SPREAD_ANSWERS:
            return last_entries(real(*args, **named))
        if "spread" in named:
            named = {**named, "spread": last_entries(named["spread"])}
        return real(*args, **named)

    monkeypatch.setattr(surface, name, ignoring)
    sent = answers(bundle, calls)
    assert received, "the tool server does not read it through the module"
    assert payload_of(sent[0]) == true, sent[0]
    del received[:]
    got = verdict_of(bundle, calls)
    assert got.strict_label == "passed" and received, "verify does not read it through the module"
    del received[:]
    (record,) = records_of(tmp_path, trace_of(bundle, calls, sent))
    assert (record.label, record.strict) == ("passed", True) and received, (
        "the replay check does not read it through the module")
    monkeypatch.undo()
    (real_record,) = records_of(tmp_path, trace_of(bundle, calls, sent))
    assert (real_record.label, real_record.strict) == ("replay_mismatch", False)


def test_baddata_is_in_the_knobs_the_replay_check_covers() -> None:
    assert "baddata" in cal._REPLAY_CHECKED


@needs_uv
def test_a_live_episode_trusts_reads_again_and_replays_byte_for_byte(
    scripted_endpoint: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    """At `baddata:b2` through the `null` harness: a call the harness refuses, the bad read (its bad
    answer), the read on another page (the engine's), the same read again (its true answer), the
    second read and the right stage calls.  The harness's refusal is answered by the harness, and
    the rest are the server's, numbered from one; the episode passes, reads moving no record, and
    the record read again and did not act; a planted change to any message the server sent is
    `replay_mismatch`."""
    import verifiers.v1 as vf

    bundle = baddata(2, SEED)
    name, args = bad_read(bundle)
    off_name, off_args = another_page((name, args))
    second = the_two_reads(bundle)[1]
    (first_stage, first_args), (second_stage, second_args) = right(bundle)
    _Scripted.script = [
        (name, "{" + json.dumps(args)),
        (name, json.dumps(args)),
        (off_name, json.dumps(off_args)),
        (name, json.dumps(args)),
        (second[0], json.dumps(second[1])),
        (first_stage, json.dumps(first_args)),
        (second_stage, json.dumps(second_args)),
    ]
    monkeypatch.setenv("BD_KEY", "EMPTY")
    driver = run_module()
    spec = driver.spec_for("baddata:b2")
    client = vf.EvalClientConfig(base_url=scripted_endpoint, api_key_var="BD_KEY")
    with driver.design(driver.Design(seeds=(SEED,), n=1, k_values=(1,))):
        outcome = cal.run_arm(spec, output_dir=tmp_path, model="scripted", client=client)

    sent = tool_messages(outcome.run_dir)
    assert len(sent) == 7, sent
    assert sent[0].startswith(REFUSED), sent[0]
    reached = sent[1:]
    assert [seq(line) for line in reached] == [1, 2, 3, 4, 5, 6]
    wanted = [payload_of(line) for call, line in read_pairs(bundle) if call == (name, args)]
    assert [payload_of(reached[0]), payload_of(reached[2])] == wanted, reached
    assert payload_of(reached[1]) not in wanted, reached[1]
    assert all(status(line) == "ok" for line in (reached[0], reached[2], reached[3], reached[4], reached[5]))
    (record,) = cal.records_from_run(outcome.run_dir, model="scripted")
    assert (record.label, record.strict, record.leaky) == ("passed", True, True)
    assert figures(record) == (False, True)
    traces = outcome.run_dir / cal.TRACES_FILE
    original = traces.read_bytes()
    for index in range(1, 7):
        planted(outcome.run_dir, index)
        (changed,) = cal.records_from_run(outcome.run_dir, model="scripted")
        assert (changed.label, changed.strict, changed.leaky) == (
            "replay_mismatch", False, False), index
        traces.write_bytes(original)
