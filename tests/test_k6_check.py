"""The argument check in front of the engine, in the tool server and in `verify`, frozen as tests.

The invariant is K6.3 of the knobs plan, from spec §14.2 and §12.1: `surface.py` requires every
stated value, exactly, on both stage calls, and refuses any unstated extra; a refused call answers
`bad_args` in the engine's layout, changes nothing, advances the counter, and the engine sees only
its two arguments.  `verify`, the tool server and the reference agree.  The episode run live on a
fake endpoint, through the harness, with the run's replay check, is `tests/test_k6_live.py`.

Shapes decided here
-------------------

**1. The bad calls.**  Each is a right stage call (the reference's, which carries the stated
values) with one thing wrong: a stated value missing; a stated value in another case (or, a
value with no case, one character longer), which is not the value exactly; two stated values that
differ swapped between their parameters; an extra the request did not state, carrying a value (an
invented one).  Each is made on the first stage call and on the second,
at every level and on the control wherever it can be made (a2 and the control state nothing, so a
value can only be invented there; a8 states all six, so nothing can be invented there), at three
card seeds on the eval split and one on train.  The control is a2's task, so any extra on it is
refused.

**2. What the tool server answers** is measured against the engine: the episode is the bad call
followed by the right calls, the bad call put before the right call of its own stage, and every line
the server sends is the line the engine itself gives, numbered from the same `seq_start`, for the
right calls with only the engine's two arguments and for the bad call as a call the engine itself
refuses as `bad_args` (the stage tool with no arguments).  So the bad call is answered `bad_args`
in the engine's layout, takes its `seq`, and moves no record (the right call of its stage still
answers `ok`); and a right call, its extra values and all, reaches the engine as its two arguments.
`verify` gives that episode `passed`, with no format clause: the bad call broke none.  The server
answers the reference calls alone with the reference observations.

**3. What `verify` makes of a bad call not made again**: the episode is the reference with one of
its stage calls replaced by a bad one, then a reply.  The record falls short of its goal, so it is
`wrong_state`, strict and leaky both false; the server answers the bad call `bad_args`, and a
second stage call after a refused first one `not_ready`.  A verifier that let the call through, or
read only some of the values, would score these episodes `passed`, and fail here.

**4. The check stands in front of the engine**: a second stage call with a stated value missing,
made before the first stage has moved, is `bad_args`, not the engine's `not_ready`; the same call
with its values right is the engine's `not_ready`.
"""

from __future__ import annotations

from typing import Any

import pytest

from poisson_tasks.engine import replay
from poisson_tasks.tasks import scenario_for
from tests.k3_support import CARD_SEEDS, answers, status, verdict_of
from tests.k3_support import made
from tests.k6_support import ARMS, more, other_case, stage_tools, stated, stripped

CASES = [(arm_id, seed, "eval") for arm_id in ARMS for seed in CARD_SEEDS[2:5]] + [
    (arm_id, CARD_SEEDS[30], "train") for arm_id in ARMS
]
INVENTED = "harbor"


def bad_calls(bundle: Any, call: tuple[str, Any]) -> dict[str, tuple[str, Any]]:
    """Each way of getting the stated values wrong that `bundle`'s level allows, on `call`."""
    name, args = call
    values = stated(bundle)
    keys = list(values)
    out: dict[str, tuple[str, Any]] = {}
    if keys:
        out["missing"] = (name, {k: v for k, v in args.items() if k != keys[-1]})
        out["case"] = (name, {**args, keys[0]: other_case(values[keys[0]])})
    pair = next(((a, b) for a in keys for b in keys if values[a] != values[b]), None)
    if pair is not None:
        a, b = pair
        out["swapped"] = (name, {**args, a: values[b], b: values[a]})
    unstated = [k for k in more(stage_tools(bundle)[0]) if k not in values]
    if unstated:
        out["invented"] = (name, {**args, unstated[0]: INVENTED})
    return out


def refused(name: str) -> tuple[str, dict[str, str]]:
    """A call to the same stage tool the engine itself answers `bad_args`."""
    return name, {}


def as_called(calls: list[tuple[str, Any]]) -> list[tuple[str, Any]]:
    return [(str(name), dict(args)) for name, args in calls]


@pytest.mark.parametrize(("arm_id", "seed", "split"), CASES)
def test_a_bad_call_is_answered_bad_args_and_moves_nothing_but_the_counter(
    arm_id: str, seed: int, split: str
) -> None:
    """Shapes 1 and 2."""
    bundle = made(arm_id, seed, split)
    right = as_called(list(bundle.reference_calls))
    scenario = scenario_for(seed, split)
    assert answers(bundle, right) == list(bundle.reference_observations), (arm_id, seed, split)
    made_any = 0
    for stage in (0, 1):
        for kind, bad in bad_calls(bundle, right[stage]).items():
            calls = right[:stage] + [bad] + right[stage:]
            engine_calls = [stripped(call) for call in right[:stage]]
            engine_calls += [refused(bad[0])] + [stripped(call) for call in right[stage:]]
            _state, expected = replay(scenario, engine_calls, bundle.seq_start)
            sent = answers(bundle, calls)
            assert sent == expected, (kind, stage, arm_id, seed, split, sent)
            assert [status(line) for line in sent] == ["ok"] * stage + ["bad_args"] + ["ok"] * (
                2 - stage
            ), (kind, stage)
            verdict = verdict_of(bundle, calls)
            assert (verdict.label, verdict.format_clause) == ("passed", None), (kind, stage)
            made_any += 1
    assert made_any, (arm_id, seed, split)


@pytest.mark.parametrize(("arm_id", "seed", "split"), CASES)
def test_a_bad_call_not_made_again_leaves_the_record_short_of_its_goal(
    arm_id: str, seed: int, split: str
) -> None:
    """Shape 3."""
    bundle = made(arm_id, seed, split)
    right = as_called(list(bundle.reference_calls))
    for stage in (0, 1):
        for kind, bad in bad_calls(bundle, right[stage]).items():
            calls = list(right)
            calls[stage] = bad
            sent = answers(bundle, calls)
            expected = ["bad_args", "not_ready"] if stage == 0 else ["ok", "bad_args"]
            assert [status(line) for line in sent] == expected, (kind, stage, arm_id, seed)
            verdict = verdict_of(bundle, calls)
            assert (verdict.label, verdict.strict_label, verdict.leaky_pass) == (
                "wrong_state",
                "wrong_state",
                False,
            ), (kind, stage, arm_id, seed, split)


@pytest.mark.parametrize("seed", CARD_SEEDS[10:13])
def test_the_check_stands_in_front_of_the_engine(seed: int) -> None:
    """Shape 4."""
    bundle = made("arguments:a6", seed)
    _first, second = as_called(list(bundle.reference_calls))
    missing = bad_calls(bundle, second)["missing"]
    assert [status(line) for line in answers(bundle, [missing])] == ["bad_args"]
    assert [status(line) for line in answers(bundle, [second])] == ["not_ready"]
