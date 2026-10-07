"""Counting the calls a fault plan is keyed on, in the tool server and in `verify`, frozen as tests.

The invariants are K3.3 and K3.4 of the knobs plan, from spec §6.2 and §6.4.  A planned failure is
keyed on how many times the episode has called that tool, whatever the arguments, counting only
calls that reach the tool server.  The tool server and `verify` both apply the plan through one
function, `surface.apply_planned(state, counts, call, plan) -> (state, counts, observation)`, so the
records `verify` replays to are the ones the server left.

Shapes decided here
-------------------

**1. What reaches the server is measured, not assumed.**  verifiers 0.3.1's `null` harness
(`harnesses/null/program.py`) answers a call itself, with an `error: ...` line and no `seq`, when
its arguments do not parse as JSON, parse to anything but an object, or name a tool the block does
not show; it forwards every other call, empty arguments as `{}`.  `verify` gets parsed turns, so it
applies the same rule per call: arguments a JSON object and a name the block shows.  The live
episode in `tests/test_k3_live.py` pins the harness's half; this file pins `verify`'s against the
tool server run in this process, with each refused call kept out of the server as the harness keeps
it out.

**2. The episodes.**  Each one below is a pattern spec §6.2 and plan K3.4 name, written as calls
(the right first and second stage calls, the first stage call with arguments the engine refuses, the
first stage call with arguments that are not an object, and a read in the block), with what the
server answers each call it receives and the verdict `verify` gives.  Each verdict is one a build
that counted the calls another way would get wrong: by position on the reference path rather than
per tool, only calls whose arguments the engine accepts, calls the harness refused, or the read.

**3. The seam is `poisson_tasks.surface.apply_planned`, read through the module** by the tool server,
by `verify` and by `records_from_run`'s replay check, as K1 made `display_map` the seam for names.
Only a replaced function shows that none of the three applies a plan of its own: under one that
ignores the plan, all three answer as if the arm planned nothing.  The replacement passes any
further argument through, so a build may hand the function more than spec §6.4's four: the frozen
`tests/test_tg_m4_export.py::test_ts3_concurrent_calls_are_numbered_without_a_gap_or_a_repeat`
watches the tool server's engine step as `export._apply`, under the toolset's lock, so the server
has to give the engine step it calls by that name.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from poisson_tasks import surface
from tests.k3_support import (
    APPLY_PLANNED,
    CARD_SEEDS,
    UNAVAILABLE,
    a_read,
    answers,
    faults,
    forwarded,
    records_of,
    right,
    status,
    trace_of,
    verdict_of,
)

SEEDS = CARD_SEEDS[:4]
NOT_AN_OBJECT = ("not", "an", "object")

Calls = Callable[[Any], list[tuple[str, Any]]]


def first(bundle: Any) -> tuple[str, Any]:
    return right(bundle)[0]


def second(bundle: Any) -> tuple[str, Any]:
    return right(bundle)[1]


def short_first(bundle: Any) -> tuple[str, Any]:
    """The first stage call missing its entry code: the engine would answer `bad_args`."""
    name, args = first(bundle)
    return name, {key: value for key, value in args.items() if key == "record_id"}


EPISODES: dict[str, tuple[int, Calls, list[str], tuple[str, bool]]] = {
    "gives up at once": (1, lambda b: [first(b)], [UNAVAILABLE], ("wrong_state", False)),
    "gives up after one retry": (
        4,
        lambda b: [first(b), first(b), first(b), second(b)],
        [UNAVAILABLE, UNAVAILABLE, "ok", UNAVAILABLE],
        ("wrong_state", False),
    ),
    "a failure taken by arguments the engine refuses": (
        1,
        lambda b: [short_first(b), first(b), second(b)],
        [UNAVAILABLE, "ok", "ok"],
        ("passed", True),
    ),
    "a call the harness refuses takes no failure": (
        1,
        lambda b: [(first(b)[0], NOT_AN_OBJECT), first(b), second(b)],
        [UNAVAILABLE, "not_ready"],
        ("malformed_call", False),
    ),
    "the second stage called first takes its own failure": (
        2,
        lambda b: [second(b), first(b), first(b), second(b)],
        [UNAVAILABLE, UNAVAILABLE, "ok", "ok"],
        ("passed", True),
    ),
    "a read takes no failure": (
        1,
        lambda b: [a_read(b), first(b), first(b), second(b)],
        ["ok", UNAVAILABLE, "ok", "ok"],
        ("passed", True),
    ),
}


@pytest.mark.parametrize("name", list(EPISODES))
def test_the_server_and_verify_count_each_tools_calls_that_reach_the_server(name: str) -> None:
    level, calls_of, statuses, (label, leaky) = EPISODES[name]
    for seed in SEEDS:
        bundle = faults(level, seed)
        calls = calls_of(bundle)
        reached = [
            answer
            for (n, a), answer in zip(calls, answers(bundle, calls), strict=True)
            if forwarded(bundle, n, a)
        ]
        assert [status(answer) for answer in reached] == statuses, (seed, reached)
        got = verdict_of(bundle, calls)
        assert (got.strict_label, got.leaky_pass) == (label, leaky), (seed, got)


def test_the_server_verify_and_the_replay_check_read_apply_planned_through_the_module(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Shape 3.  `faults:f1`'s first right call and then its second, with no retry: under the real
    function the server answers `unavailable`, `not_ready` and the episode fails; under one that
    ignores the plan the server answers `ok`, `ok`, `verify` passes the episode, and the replay
    check takes the server's answers, so the record is a pass and not `replay_mismatch`."""
    bundle = faults(1, SEEDS[0])
    calls = [first(bundle), second(bundle)]
    assert [status(a) for a in answers(bundle, calls)] == [UNAVAILABLE, "not_ready"]
    real = vars(surface)[APPLY_PLANNED]

    def unplanned(state: Any, counts: Any, call: Any, plan: Any, *rest: Any, **named: Any) -> Any:
        return real(state, counts, call, {}, *rest, **named)

    monkeypatch.setattr(surface, APPLY_PLANNED, unplanned)
    sent = answers(bundle, calls)
    assert [status(a) for a in sent] == ["ok", "ok"]
    assert verdict_of(bundle, calls).strict_label == "passed"
    (record,) = records_of(tmp_path, trace_of(bundle, calls, sent))
    assert (record.label, record.strict) == ("passed", True)
