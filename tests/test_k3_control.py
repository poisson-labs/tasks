"""The faults knob's control arm, `faults:f0+len(f4)`, frozen as tests.

The control is `faults:f0`'s task with
read pairs seeded before the model's first move, of the history knob's kind (N24: a read tool in
the block, answered `ok`, mutating nothing), whose reference tokens total `faults:f4`'s four fault
pairs at the same seed within two (N26).  It seeds the fewest pairs whose reachable totals bracket
that total: three, at the sizes the card's seeds draw.

Shapes decided here
-------------------

**1. Seeded as a depth control seeds** (`tasks.py`'s seeded messages): the user's
instruction, then one assistant message per pair carrying one read call, each answered by its tool
message; `seq_start` is the number of pairs plus one, and the reference runs from there.

**2. A pair's tokens are N9's unit**, as the ledger measures it: the tool's name, its arguments as
one compact JSON object, and the observation.  `faults:f4`'s fault pairs are its reference calls
answered `unavailable`, each with its answer.

**3. "The fewest" is not stated as its own assertion.**  At these sizes a read pair is 51 to 66
tokens and four fault pairs 160 to 176, so two pairs cannot reach the total and four overshoot it:
three pairs is what N26's band leaves, and the count is asserted to say so.

**4. The control plans no failure**: a control plans its own level's failures, and f0's are none
(`surface.fault_plan`, from the knobs' shared base).  Its reference is `faults:f0`'s two calls,
numbered from `seq_start`.

"""

from __future__ import annotations

import json
from typing import Any

from poisson_tasks.tokenizer import count_tokens
from tests.k3_support import (
    CARD_SEEDS,
    CONTROL,
    SPEC,
    UNAVAILABLE,
    faults,
    made,
    names,
    seq,
    status,
)


def pair_tokens(name: str, args: Any, observation: str) -> int:
    rendered = args if isinstance(args, str) else json.dumps(args, separators=(",", ":"))
    return count_tokens(name) + count_tokens(rendered) + count_tokens(observation)


def seeded(bundle: Any) -> list[tuple[str, Any, str]]:
    """The seeded pairs: each assistant message's one call and the tool message answering it."""
    prompt = list(bundle.prompt)
    assert prompt[0]["role"] == "user" and isinstance(prompt[0]["content"], str)
    pairs = []
    for ask, answer in zip(prompt[1::2], prompt[2::2], strict=True):
        assert ask["role"] == "assistant" and answer["role"] == "tool"
        (tool_call,) = ask["tool_calls"]
        assert answer["tool_call_id"] == tool_call["id"]
        function = tool_call["function"]
        pairs.append((function["name"], json.loads(function["arguments"]), answer["content"]))
    return pairs


def test_the_control_seeds_three_read_pairs_as_long_as_f4s_fault_pairs() -> None:
    for split in ("eval", "train"):
        for seed in CARD_SEEDS:
            control = made(CONTROL, seed, split)
            f0 = faults(0, seed, split)
            pairs = seeded(control)
            assert len(pairs) == 3, (split, seed)
            assert not isinstance(control.prompt, str) and control.prompt[0] == {
                "role": "user",
                "content": f0.prompt,
            }
            assert control.seq_start == len(pairs) + 1
            for index, (name, _args, observation) in enumerate(pairs):
                assert name in SPEC.read_tools and name in names(control), name
                assert (status(observation), seq(observation)) == ("ok", index + 1)
            f4 = faults(4, seed, split)
            fault_pairs = [
                pair_tokens(name, args, observation)
                for (name, args), observation in zip(
                    f4.reference_calls, f4.reference_observations, strict=True
                )
                if status(observation) == UNAVAILABLE
            ]
            assert len(fault_pairs) == 4
            total = sum(pair_tokens(*pair) for pair in pairs)
            assert abs(total - sum(fault_pairs)) <= 2, (split, seed, total, fault_pairs)
            assert control.reference_calls == f0.reference_calls
            assert [(status(o), seq(o)) for o in control.reference_observations] == [
                ("ok", control.seq_start),
                ("ok", control.seq_start + 1),
            ]
