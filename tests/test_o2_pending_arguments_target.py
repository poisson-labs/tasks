"""Pending a decision: the arguments knob's target on a user's own tools.

**Why it is open.**  The design: the levels run "from the target's required count up to its
parameter count".  A set's writes differ in those counts, so a target drawn per seed would give
levels some seeds' targets cannot reach, and the levels could not be one design.

**Recommended.**  The target is the write that can be a target with the most checkable parameters,
the first in the file on a tie, the same for every seed.  If it is declined, the build draws the
target per seed among the writes that admit every level of the design.
"""

from __future__ import annotations

from poisson_tasks import own
from tests.o2_support import arm, fixture_sets, generator


def checkable(tool: own.OwnTool) -> list[str]:
    """The arguments that are not free text (the tool-file readers' rule: a string, or untyped, with
    none of format, enum, const, minLength and maxLength is free text)."""
    out = []
    for name, schema in tool.input_schema.get("properties", {}).items():
        kind = schema.get("type") if isinstance(schema, dict) else None
        if isinstance(kind, list) and set(kind) - {"null"} <= {"string"}:
            kind = "string"
        free = not isinstance(schema, dict) or kind in (None, "string") and not any(
            key in schema for key in ("format", "enum", "const", "minLength", "maxLength"))
        if not free:
            out.append(name)
    return out


def test_the_target_is_the_write_with_the_most_checkable_arguments() -> None:
    for label in ("acme-mcp", "petstore", "everything"):
        toolset = fixture_sets()[label]
        writes = [t for t in toolset.tools if own.is_write(t) and own.can_target(t)]
        best = max(writes, key=lambda t: (len(checkable(t)), -writes.index(t)))
        for level in generator().knob_levels(toolset, "arguments"):
            for seed in range(6):
                assert generator().generate(toolset, arm("arguments", level), seed).target == best.name
