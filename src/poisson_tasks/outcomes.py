"""What each outcome label means, in one plain sentence.

The labels are `tasks.OUTCOMES`; the sentences are kept here and never in `tasks.py`, whose bytes
are part of every task id.  `tests/test_fd4_outcomes.py` says what each name does.

`describe` gives the sentence of a verdict's strict label: what the episode did.  A leaky task's
own label calls an overshoot `passed`, and the sentence for `passed` says the model stopped at the
goal, which it did not; so the strict label is the one described, whatever the task's strictness.
"""

from __future__ import annotations

import types
from collections.abc import Mapping
from typing import Any

__all__ = ["MEANING", "describe"]

MEANING: Mapping[str, str] = types.MappingProxyType({
    "verifier_error": "The verifier could not judge the attempt, so it was not scored.",
    "replay_mismatch": (
        "The tool answers the model saw are not the answers its calls would have produced, so "
        "the attempt was not scored."
    ),
    "api_error": "The model's provider returned an error, so the attempt was not scored.",
    "wall_timeout": "The attempt ran out of time before it finished, so it was not scored.",
    "malformed_call": "The model wrote a tool call the harness could not read.",
    "turn_limit": "The model used every model call it was allowed before it finished.",
    "overshoot": "The model reached the goal and then kept changing the record past it.",
    "wrong_state": "The model stopped with the record in a state that is not the goal.",
    "collateral_mutation": (
        "The model reached the goal but also changed something the task did not ask for."
    ),
    "passed": "The model reached the goal exactly and stopped there.",
})
"""One sentence per outcome label."""


def describe(verdict: Any) -> str:
    """The sentence for a verdict: a `tasks.Verdict`, by its strict label, or a label."""
    label = getattr(verdict, "strict_label", verdict)
    if not isinstance(label, str) or label not in MEANING:
        raise ValueError(f"{label!r} is not an outcome label")
    return MEANING[label]
