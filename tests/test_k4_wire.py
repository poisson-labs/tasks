"""The history knob on the wire: the top level's bundle through the export, frozen as tests.

A `history:t2400` bundle survives the export round trip
(X2), and its seeded messages are well formed (G13).  The frozen X2 and G13 tests run over the
published cards' arms, whose longest seeded prompt is the depth control's seven pairs; a history
task at the top level carries forty-two, the longest prompt the generator makes, so the round
trip and the shape are pinned on it here.

Shapes decided here
-------------------

**1. X2 is measured as the frozen tests measure it**: the task data rebuilds the bundle equal
field for field, and again after the JSON wire the launched tool server receives it through;
the data's prompt is the wheel's `Messages`, a user message then assistant and tool messages in
turn, each carrying what the bundle's does.

**2. G13 on the top level**: a user message first, then one assistant message per pair carrying
one `tool_calls` entry whose arguments are a JSON string of an object, each matched by the tool
message that follows it with that call's id; the ids distinct; every observation `L_obs` bytes
and inside the engine's token band; the `seq`s 1 to the pair count, the server starting after
them.
"""

from __future__ import annotations

import json

import verifiers.v1 as vf

from poisson_tasks import export
from poisson_tasks.tokenizer import count_tokens
from tests.k3_support import CARD_SEEDS, SPEC
from tests.k4_support import history, messages_of

SEEDS = CARD_SEEDS[:6]
TOP = 2400


def test_the_top_level_survives_the_export_round_trip() -> None:
    """X2 on `history:t2400`, in the process and over the JSON wire."""
    for seed in SEEDS:
        bundle = history(TOP, seed)
        task = export.task_from_bundle(bundle)
        assert export.bundle_from_data(task.data) == bundle, seed
        rebuilt = type(task.data).model_validate_json(task.data.model_dump_json())
        assert export.bundle_from_data(rebuilt) == bundle, seed
        prompt = task.data.prompt
        assert not isinstance(prompt, str) and len(prompt) == len(bundle.prompt)
        assert [type(m) for m in prompt] == [vf.UserMessage] + [
            vf.AssistantMessage,
            vf.ToolMessage,
        ] * ((len(prompt) - 1) // 2)
        for theirs, ours in zip(messages_of(bundle), prompt, strict=True):
            if theirs["role"] == "assistant":
                (call,) = theirs["tool_calls"]
                (flat,) = ours.tool_calls
                assert (flat.id, flat.name, flat.arguments) == (
                    call["id"],
                    call["function"]["name"],
                    call["function"]["arguments"],
                )
            elif theirs["role"] == "tool":
                assert (ours.tool_call_id, ours.content) == (
                    theirs["tool_call_id"],
                    theirs["content"],
                )


def test_the_top_levels_seeded_messages_are_well_formed() -> None:
    """G13 on `history:t2400`."""
    low, high = SPEC.table["token_band"]
    for seed in SEEDS:
        bundle = history(TOP, seed)
        messages = messages_of(bundle)
        assert messages[0]["role"] == "user" and isinstance(messages[0]["content"], str)
        rest = messages[1:]
        assert rest and len(rest) % 2 == 0
        ids = []
        for index, (assistant, tool) in enumerate(zip(rest[0::2], rest[1::2], strict=True)):
            assert set(assistant) == {"role", "tool_calls"} and assistant["role"] == "assistant"
            (call,) = assistant["tool_calls"]
            assert call["type"] == "function"
            assert isinstance(call["function"]["arguments"], str)
            assert isinstance(json.loads(call["function"]["arguments"]), dict)
            assert tool == {"role": "tool", "tool_call_id": call["id"], "content": tool["content"]}
            content = tool["content"]
            assert len(content.encode("utf-8")) == SPEC.L_obs
            assert low <= count_tokens(content) <= high
            assert int(content.split()[0]) == index + 1
            ids.append(call["id"])
        assert len(set(ids)) == len(ids)
        assert bundle.seq_start == len(ids) + 1
