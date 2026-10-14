"""The verdict on a user's own tools: the built-in outcome vocabulary, judged by replaying an
episode's calls through the simulator (spec §5.2).

`verify(task, turns, ended_with_reply, turn_limit_hit, fmt)` takes `tasks.Turn`s and a
`tasks.FormatSpec` and returns a `tasks.Verdict`, as `tasks.verify` does, so the export and the
card read both alike.  The pass predicate is decided first: every write the task expects was
accepted, nothing else was, and the episode ended with a reply.  Then the labels in the table's
order: `malformed_call` when a format clause fired (clause 1 the format's markers in a reply
with no call, 2 arguments that are not a JSON object, 3 a name outside the block, 4 arguments
that break the tool's schema), `turn_limit` when the limit was hit without a reply,
`wrong_state` when the goal was not reached, `collateral_mutation` when it was and another write
was accepted.  A user's write has no stage past its goal, so `overshoot` never occurs.  Leaky
accepts collateral.  Every raise inside is `verifier_error`, and so is an episode that neither
replied nor hit the limit.  `Verdict.mutations` holds one entry per accepted write, expected or
not.  `tests/test_o2_verdict.py` pins all of this.
"""

from __future__ import annotations

from collections.abc import Sequence as _Sequence
from typing import Any as _Any

from poisson_tasks.own import simulator as _sim
from poisson_tasks.tasks import Verdict as _Verdict

__all__ = ["verify"]

_PASSED = "passed"
_MALFORMED = "malformed_call"
_TURN_LIMIT = "turn_limit"
_WRONG_STATE = "wrong_state"
_COLLATERAL = "collateral_mutation"
_VERIFIER_ERROR = "verifier_error"
_LEAKY = "leaky"


def verify(
    task: _Any, turns: _Any, ended_with_reply: bool, turn_limit_hit: bool, fmt: _Any
) -> _Any:
    """The `tasks.Verdict` on one episode of `task`, a pure function of its arguments."""
    try:
        return _verdict(task, tuple(turns), bool(ended_with_reply), bool(turn_limit_hit), fmt)
    except Exception:
        return _Verdict(
            strict_label=_VERIFIER_ERROR, leaky_pass=False, label=_VERIFIER_ERROR,
            mutations=(), format_clause=None,
        )


def _clauses(turns: _Sequence[_Any], fmt: _Any, block: dict[str, _Any]) -> set[int]:
    """Every clause that fired over the whole episode; the lowest is reported."""
    fired: set[int] = set()
    for turn in turns:
        content = str(turn.content)
        if not turn.calls and any(marker in content for marker in fmt.markers):
            fired.add(1)
        for name, args in turn.calls:
            if not isinstance(args, dict):
                fired.add(2)
            tool = block.get(name) if isinstance(name, str) else None
            if tool is None:
                fired.add(3)
            elif isinstance(args, dict) and not _sim.conforms(args, dict(tool["parameters"])):
                fired.add(4)
    return fired


def _verdict(
    task: _Any, turns: tuple[_Any, ...], ended_with_reply: bool, turn_limit_hit: bool, fmt: _Any
) -> _Verdict:
    block = {str(tool["name"]): tool for tool in task.tools}
    if not block or not task.steps:
        raise ValueError("a task without a block or without an expected step is defective")
    fired = _clauses(turns, fmt, block)
    clause = min(fired) if fired else None
    state = _sim.start(task)
    mutations: list[tuple[str, str, str]] = []
    for turn in turns:
        for name, args in turn.calls:
            if not _sim.reaches_the_server(name, args, block):
                continue
            before = state
            state, _answer = _sim.step(task, state, (str(name), args))
            if state.done != before.done:
                mutations.append((str(name), _sim.canonical(args), "expected"))
            if len(state.side_effects) > len(before.side_effects):
                mutations.append((str(name), _sim.canonical(args), "side_effect"))
    changed = tuple(mutations)
    goal = all(state.done)
    clean = not state.side_effects
    if not ended_with_reply and not turn_limit_hit:
        return _Verdict(
            strict_label=_VERIFIER_ERROR, leaky_pass=False, label=_VERIFIER_ERROR,
            mutations=changed, format_clause=clause,
        )
    if goal and clean and ended_with_reply:
        strict_label = _PASSED
    elif clause is not None:
        strict_label = _MALFORMED
    elif turn_limit_hit and not ended_with_reply:
        strict_label = _TURN_LIMIT
    elif not goal:
        strict_label = _WRONG_STATE
    else:
        strict_label = _COLLATERAL
    leaky_pass = goal
    if task.strictness == _LEAKY and leaky_pass:
        label = _PASSED
    else:
        label = strict_label
    return _Verdict(
        strict_label=strict_label, leaky_pass=leaky_pass, label=label, mutations=changed,
        format_clause=clause,
    )
