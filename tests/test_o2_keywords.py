"""The wider list of JSON Schema keywords the readers refuse, frozen as tests.

Ruled 2026-10-07 (O1 Session B's yes/no 1): the keywords beyond spec §3's that the simulator
cannot honour are O2's to write, each with a test and an accepted control, and
`poisson_tasks.own._schema.UNCHECKABLE` is the one tuple that holds them all.  Taylor named
`if`/`then`/`else`, `dependentSchemas`, `propertyNames`, `contains`, `uniqueItems`,
`multipleOf` and `unevaluatedProperties`, "and anything else the simulator cannot honour".

Shapes decided here
-------------------

**1. The list.**  O1's five (`anyOf`, `oneOf`, `allOf`, `not`, `patternProperties`) and these:
the conditionals (`if`, `then`, `else`); the dependencies, in both their 2020-12 forms and the
draft-7 one (`dependentSchemas`, `dependentRequired`, `dependencies`); `propertyNames`; the
array containment family (`contains`, `minContains`, `maxContains`); `uniqueItems`;
`multipleOf`; the unevaluated pair (`unevaluatedProperties`, `unevaluatedItems`); the
property-count bounds (`minProperties`, `maxProperties`); the dynamic references
(`$dynamicRef`, `$recursiveRef`), which inlining cannot follow; and `contentSchema`, a schema
for decoded content that no argument check reads.  Each couples an argument's validity to
another argument's, to a count of arguments, or to a value the simulator cannot draw exactly,
so a request that states some arguments and leaves others out (the arguments knob) could not
be checked exactly.

**2. Kept as honoured**, and so controls here: `pattern` (checked on a call, and never a value a
request states, since O1's target rule counts a patterned string as free text), `const`,
`enum`, the length and numeric bounds, `format` (one the simulator does not know is plain text),
and `contentMediaType` alone.

**3. Where.**  A keyword is refused wherever it sits in the argument schema: on the argument
object itself, on an argument, and nested inside an argument's object or array, by O1's walk
(kind `schema`).  A property that merely has one of these words as its *name* is an argument
like any other.  The output schema is kept whatever it uses (O1's rule, unchanged): what the
simulator does with an output keyword it cannot fill is the pending file
`test_o2_pending_output_keywords.py`.
"""

from __future__ import annotations

from typing import Any

import pytest

from poisson_tasks.own import _schema
from tests.o1_support import PARTNER_PARAMS, mcp_file, mcp_partner, mcp_tool, read

O1_LIST = ("anyOf", "oneOf", "allOf", "not", "patternProperties")
WIDER = (
    "if", "then", "else",
    "dependentSchemas", "dependentRequired", "dependencies",
    "propertyNames",
    "contains", "minContains", "maxContains",
    "uniqueItems",
    "multipleOf",
    "unevaluatedProperties", "unevaluatedItems",
    "minProperties", "maxProperties",
    "$dynamicRef", "$recursiveRef",
    "contentSchema",
)

# Each keyword with the value it takes and the kind of schema it sits on.
OBJECT_PROPERTIES: dict[str, Any] = {"a": {"type": "string", "maxLength": 4}, "b": {"type": "integer"}}
OBJECT: dict[str, Any] = {"type": "object", "properties": OBJECT_PROPERTIES}
ARRAY = {"type": "array", "items": {"type": "string", "maxLength": 4}}
NUMBER = {"type": "number"}
STRING = {"type": "string", "contentMediaType": "application/json"}
PLACED: dict[str, tuple[dict[str, Any], Any]] = {
    "if": (OBJECT, {"properties": {"a": {"const": "x"}}}),
    "then": (OBJECT, {"required": ["b"]}),
    "else": (OBJECT, {"required": ["a"]}),
    "dependentSchemas": (OBJECT, {"a": {"required": ["b"]}}),
    "dependentRequired": (OBJECT, {"a": ["b"]}),
    "dependencies": (OBJECT, {"a": ["b"]}),
    "propertyNames": (OBJECT, {"maxLength": 3}),
    "contains": (ARRAY, {"const": "x"}),
    "minContains": (ARRAY, 1),
    "maxContains": (ARRAY, 2),
    "uniqueItems": (ARRAY, True),
    "multipleOf": (NUMBER, 0.5),
    "unevaluatedProperties": (OBJECT, False),
    "unevaluatedItems": (ARRAY, False),
    "minProperties": (OBJECT, 1),
    "maxProperties": (OBJECT, 1),
    "$dynamicRef": (OBJECT, "#node"),
    "$recursiveRef": (OBJECT, "#"),
    "contentSchema": (STRING, {"type": "object"}),
}


def with_keyword(base: dict[str, Any], keyword: str | None, value: Any) -> dict[str, Any]:
    schema = dict(base)
    if keyword is not None:
        schema[keyword] = value
    return schema


def placements(keyword: str, *, keep_it: bool = True) -> dict[str, dict[str, Any]]:
    """The argument schema with the keyword (or, with `keep_it` false, the same schema without it)
    at three depths, four for an object keyword: on the argument object itself; on one argument;
    on an argument's own object; and inside an array argument's items."""
    base, value = PLACED[keyword]
    inner = with_keyword(base, keyword if keep_it else None, value)
    keep = {"n": PARTNER_PARAMS["properties"]["n"]}
    out = {
        "argument": {"type": "object", "properties": {**keep, "v": inner}, "required": ["n"]},
        "nested": {"type": "object", "properties": {
            **keep, "w": {"type": "object", "properties": {"v": inner}}}, "required": ["n"]},
        "in-items": {"type": "object", "properties": {
            **keep, "w": {"type": "array", "items": inner}}, "required": ["n"]},
    }
    if base is OBJECT:
        top = with_keyword({"type": "object", "properties": {**keep, **OBJECT_PROPERTIES},
                            "required": ["n"]}, keyword if keep_it else None, value)
        out["top"] = top
    return out


def refusals(schema: dict[str, Any]) -> list[tuple[str, str]]:
    reading = read(mcp_file(mcp_tool("alpha", schema), mcp_partner(), mcp_partner("gamma")))
    return [(refusal.name, refusal.kind) for refusal in reading.refused]


def test_uncheckable_is_the_one_tuple_holding_o1s_five_and_the_wider_list() -> None:
    assert isinstance(_schema.UNCHECKABLE, tuple)
    assert len(set(_schema.UNCHECKABLE)) == len(_schema.UNCHECKABLE)
    assert set(_schema.UNCHECKABLE) == set(O1_LIST) | set(WIDER)


@pytest.mark.parametrize("keyword", WIDER)
def test_each_keyword_the_simulator_cannot_honour_is_refused_wherever_it_sits(keyword: str) -> None:
    for where, schema in placements(keyword).items():
        assert refusals(schema) == [("alpha", "schema")], (keyword, where)


@pytest.mark.parametrize("keyword", WIDER)
def test_the_same_schema_without_the_keyword_is_read(keyword: str) -> None:
    """The accepted control: every placement above, the keyword removed and the schema it sat on
    kept (an array argument for `uniqueItems`, a number for `multipleOf`, and so on)."""
    for where, schema in placements(keyword, keep_it=False).items():
        assert refusals(schema) == [], (keyword, where)


def test_an_argument_named_after_a_keyword_is_an_argument() -> None:
    properties = {word: {"type": "string", "maxLength": 8} for word in (*O1_LIST, *WIDER)}
    schema = {"type": "object", "properties": properties, "required": ["if", "contains"]}
    reading = read(mcp_file(mcp_tool("alpha", schema), mcp_partner(), mcp_partner("gamma")))
    assert reading.refused == ()
    (alpha,) = [tool for tool in reading.toolset.tools if tool.name == "alpha"]
    assert alpha.input_schema == schema


@pytest.mark.parametrize(
    "honoured",
    [
        {"type": "string", "pattern": "^[A-Z]-[0-9]{4}$"},
        {"const": "fixed"},
        {"type": "string", "enum": ["a", "b"]},
        {"type": "string", "minLength": 2, "maxLength": 6},
        {"type": "integer", "minimum": 0, "maximum": 9, "exclusiveMaximum": 10},
        {"type": "string", "format": "duration"},
        {"type": "string", "contentMediaType": "application/json"},
    ],
    ids=["pattern", "const", "enum", "lengths", "numeric-bounds", "unknown-format", "media-type"],
)
def test_what_the_simulator_honours_is_read(honoured: dict[str, Any]) -> None:
    schema = {"type": "object", "properties": {"n": PARTNER_PARAMS["properties"]["n"], "v": honoured},
              "required": ["n"]}
    assert refusals(schema) == []


@pytest.mark.parametrize("keyword", WIDER)
def test_an_output_schema_is_kept_whatever_it_uses(keyword: str) -> None:
    base, value = PLACED[keyword]
    output = {"type": "object", "properties": {"v": with_keyword(base, keyword, value)}}
    reading = read(mcp_file(mcp_tool("alpha", PARTNER_PARAMS, output_schema=output),
                            mcp_partner(), mcp_partner("gamma")))
    assert reading.refused == ()
    (alpha,) = [tool for tool in reading.toolset.tools if tool.name == "alpha"]
    assert alpha.output_schema == output
