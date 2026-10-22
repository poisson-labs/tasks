"""Pending a decision: the arguments knob counts only the target's checkable parameters.

**Why it is open.**  The design counts "the target tool's own parameters", and says no exact value
of a free-text parameter can be checked.  Whether a free-text parameter counts towards a level, and is
stated, is not said.

**Recommended.**  Free text is never stated or checked; the level counts checkable parameters
only.  If it is declined, the build states free text too and checks it byte for byte.
"""

from __future__ import annotations

from tests.o2_support import arm, generator, mcp_set, write_tool


def test_free_text_is_never_stated_and_does_not_count() -> None:
    only_one = mcp_set(
        write_tool("tag", {"code": {"type": "string", "maxLength": 5}, "note": {"type": "string"},
                           "label": {"type": "string"}}, ["code", "note"]),
        write_tool("untag", {"code": {"type": "string", "maxLength": 5}}, ["code"]),
    )
    assert generator().knob_levels(only_one, "arguments") == ()
    two = mcp_set(
        write_tool("tag", {"code": {"type": "string", "maxLength": 5}, "n": {"type": "integer"},
                           "note": {"type": "string"}}, ["code"]),
        write_tool("untag", {"code": {"type": "string", "maxLength": 5}}, ["code"]),
    )
    assert generator().knob_levels(two, "arguments") == (2,)
    for seed in range(5):
        bundle = generator().generate(two, arm("arguments", 2), seed)
        assert {name for name, _v in bundle.stated} == {"code", "n"}
