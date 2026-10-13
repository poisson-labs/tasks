"""The argument-difficulty knob's schema: eight parameters on each stage tool at every level, frozen
as tests.

The invariant is K6.1 of the knobs plan, from spec §14.2 and §3.6 (N4, N7, N30): at every level
each stage tool's schema lists the same eight parameters, the same two required, the two the engine
knows and six more, opaque `*_code` fields named so that no tool name carries their words; so the
block is the same at every level.  Spec §3.1: the knob's base level, a2, is B (`distractor:r0@k16`)
with the eight-parameter schema.

Shapes decided here
-------------------

**1. The block is B's but for the stage tools' parameters**, at every level and the control, every
card seed, both splits: the same tools in the same slots, every read as B shows it, each stage tool
under B's name and description, with B's parameter types, B's `required` list (the engine's two)
and B's other schema keys, and six more properties, each a string, the same six on both stage
tools (the request's values are to be carried on both calls), none a parameter of any engine tool;
each rendered as B renders a parameter, its type and nothing else.
The schemas are equal across the levels and the control, which is N30 and N4 as the ledger holds
them (`tests/test_k6_stated.py` runs the ledger over the contrast).

**2. "Carry no instruction token a tool name carries" is read over every tool the table defines**
and every name any task lists,
not only the block's, and over each name as written and in words, as a request might state it: no
reference-tokenizer token of either is a substring of any tool name.  The ledger's N7 sees only the
tokens a request adds; a name made of a word the request already carries at a2 (a stage name, say)
moves no overlap set and is still the name the spec rules out.
"""

from __future__ import annotations

from typing import Any

from poisson_tasks.tokenizer import reference_encoding
from tests.k3_support import SPEC, made, names
from tests.k6_support import (
    ARMS,
    ENGINE_PARAMETERS,
    MORE,
    SPLITS,
    arguments,
    base,
    in_words,
    more,
    stage_tools,
)


def outside(schema: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in schema.items() if key != "properties"}


def test_each_stage_tool_lists_the_engines_two_and_the_same_six_more_at_every_level() -> None:
    """Shape 1."""
    for split, seeds in SPLITS:
        for seed in seeds:
            b = base(seed, split)
            first: Any = None
            for arm_id in ARMS:
                bundle = made(arm_id, seed, split)
                assert names(bundle) == names(b), (arm_id, seed, split)
                six: set[tuple[str, ...]] = set()
                for tool, b_tool in zip(bundle.tools, b.tools, strict=True):
                    if tool["name"] not in SPEC.stage_tools:
                        assert tool == b_tool, (tool["name"], arm_id, seed, split)
                        continue
                    assert tool["description"] == b_tool["description"], (arm_id, seed, split)
                    schema, b_schema = tool["parameters"], b_tool["parameters"]
                    assert outside(schema) == outside(b_schema), (arm_id, seed, split)
                    engine = b_schema["properties"]
                    assert {k: schema["properties"][k] for k in engine} == engine
                    added = more(tool)
                    assert len(added) == MORE, (added, arm_id, seed, split)
                    assert len(schema["properties"]) == len(engine) + MORE
                    for name in added:
                        assert schema["properties"][name] == {"type": "string"}, name
                        assert name.endswith("_code") and name not in ENGINE_PARAMETERS, name
                    six.add(added)
                assert len(six) == 1, (six, arm_id, seed, split)
                schemas = [tool["parameters"] for tool in stage_tools(bundle)]
                assert len(schemas) == 2, (arm_id, seed, split)
                if first is None:
                    first = schemas
                assert schemas == first, (arm_id, seed, split)


def pieces(text: str) -> list[str]:
    encoding = reference_encoding()
    out = []
    for token in encoding.encode_ordinary(text):
        piece = encoding.decode([token]).strip().lower()
        if piece:
            out.append(piece)
    return out


def test_no_tool_name_carries_a_token_of_the_six_names() -> None:
    """Shape 2."""
    tool_names = [tool.name.lower() for tool in SPEC.tools]
    names_seen: set[str] = set()
    for split, seeds in SPLITS:
        for seed in seeds:
            for tool in stage_tools(arguments(8, seed, split)):
                names_seen.update(more(tool))
    assert len(names_seen) >= MORE
    for name in sorted(names_seen):
        for text in (name, in_words(name)):
            for piece in pieces(text):
                carried = [tool_name for tool_name in tool_names if piece in tool_name]
                assert carried == [], (name, piece, carried[:3])
