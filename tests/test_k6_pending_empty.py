"""Pending a yes/no: an empty value in a parameter the request did not state is refused.

**This file waits on a yes/no** and is its own commit, so a "no" drops it whole.

Spec §14.2: "An extra that the request did not state must be absent: inventing a value is wrong."
A model often fills an optional text field with an empty string.  Read by "must be absent", an
empty string sent for an unstated parameter is an extra that is present, and is refused; read by
"inventing a value", it arguably invents nothing.  The frozen `tests/test_k6_check.py` tests an
invented word only, so either reading passes it, and the choice changes what the probe measures.
Recommended: "must be absent" wins, so the call is answered `bad_args` in front of the engine like
any other wrong extra, and a verifier that let it through would be scoring a call the server
refused.  Pinned at the tool server and in `verify`, on a2, a4 and the control, the first stage
call and the second.  If the answer is no, an empty unstated value is the build's to take or
refuse, and this file is dropped.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.k3_support import CARD_SEEDS, answers, made, status, verdict_of
from tests.k6_support import CONTROL, arm, more, stage_tools, stated


@pytest.mark.parametrize("arm_id", [arm(2), arm(4), CONTROL])
def test_an_empty_value_in_an_unstated_parameter_is_refused(arm_id: str) -> None:
    for seed in CARD_SEEDS[:3]:
        bundle = made(arm_id, seed)
        right: list[tuple[str, Any]] = [(str(n), dict(a)) for n, a in bundle.reference_calls]
        unstated = [k for k in more(stage_tools(bundle)[0]) if k not in stated(bundle)]
        for stage in (0, 1):
            name, args = right[stage]
            empty = (name, {**args, unstated[0]: ""})
            sent = answers(bundle, right[:stage] + [empty] + right[stage:])
            assert [status(line) for line in sent][stage] == "bad_args", (arm_id, seed, stage)
            calls = list(right)
            calls[stage] = empty
            verdict = verdict_of(bundle, calls)
            assert verdict.label == "wrong_state", (arm_id, seed, stage, verdict)
