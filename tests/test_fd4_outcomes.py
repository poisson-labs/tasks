"""What each outcome means, frozen as tests: `poisson_tasks.outcomes`.

The invariant is FD4.11 of the front door's plan (spec §4.5): the keys of `outcomes.MEANING` are
exactly `tasks.OUTCOMES`, one plain sentence each, held outside `tasks.py`, whose bytes are part
of every task id.

Shapes decided here, where the spec leaves them open
----------------------------------------------------

**1. `describe(verdict)` takes a `tasks.Verdict` or a label**, and gives the sentence of the
verdict's strict label: what the episode did.  A leaky task's own label calls an overshoot
`passed`, and the sentence for `passed` says the model stopped at the goal, which it did not; what
`verify` prints as its verdict word for a leaky task is FD5's.  A label outside the vocabulary is
a `ValueError` of one line naming it.

**2. A sentence is plain**: one line, no internal identifier (`tests.helpers.INTERNAL`), and no
two labels share one.

`verify`, which prints these sentences, is FD5's: what it prints, and its exit codes, are FD5's
Session A's to pin.
"""

from __future__ import annotations

import importlib
from typing import Any

import pytest

from tests.fd4_support import one_line
from tests.helpers import INTERNAL


def outcomes() -> Any:
    return importlib.import_module("poisson_tasks.outcomes")


def tasks() -> Any:
    return importlib.import_module("poisson_tasks.tasks")


def test_fd4_11_every_outcome_label_has_one_plain_sentence() -> None:
    meaning = outcomes().MEANING
    assert set(meaning) == set(tasks().OUTCOMES)
    sentences = [meaning[label] for label in tasks().OUTCOMES]
    assert len(set(sentences)) == len(sentences)
    for label, sentence in zip(tasks().OUTCOMES, sentences, strict=True):
        assert isinstance(sentence, str) and one_line(sentence), label
        assert not INTERNAL.search(sentence), (label, sentence)


def test_fd4_11_describe_gives_the_sentence_of_a_verdict_or_its_label() -> None:
    """A real verdict: the reference solution of a generated task passes; the same task with no
    call made does not, and gets its own label's sentence; a leaky task's overshoot, which its own
    label calls `passed`, gets the overshoot's sentence."""
    t = tasks()
    from poisson_tasks.arms import arm_from_id

    bundle = t.generate(arm_from_id("depth:d3"), 404)
    fmt = t.FormatSpec(name="qwen3_coder", markers=("<tool_call>", "<function="))
    calls = tuple(t.Turn(content="", calls=(call,), finish_reason="tool_calls")
                  for call in bundle.reference_calls)
    reply = (t.Turn(content="Done.", calls=(), finish_reason="stop"),)
    passed = t.verify(bundle, calls + reply, ended_with_reply=True, turn_limit_hit=False,
                      fmt=fmt)
    idle = t.verify(bundle, reply, ended_with_reply=True, turn_limit_hit=False, fmt=fmt)
    assert passed.strict_label == "passed" and idle.strict_label != "passed"
    meaning = outcomes().MEANING
    assert outcomes().describe(passed) == meaning["passed"]
    assert outcomes().describe(idle) == meaning[idle.strict_label]
    leaky = t.generate(arm_from_id("depth:d3", strictness="leaky"), 404)
    past = tuple(t.Turn(content="", calls=(call,), finish_reason="tool_calls")
                 for call in leaky.negative_controls["overshoot"])
    over = t.verify(leaky, past + reply, ended_with_reply=True, turn_limit_hit=False, fmt=fmt)
    assert (over.strict_label, over.label) == ("overshoot", "passed")
    assert outcomes().describe(over) == meaning["overshoot"]
    for label in t.OUTCOMES:
        assert outcomes().describe(label) == meaning[label]
    with pytest.raises(ValueError) as refused:
        outcomes().describe("not-a-label-xq")
    assert one_line(str(refused.value)) and "not-a-label-xq" in str(refused.value)
