"""What Tasks refuses when it reads a tool file, frozen as tests (O1.3).

The invariant is O1.3 of the knobs plan, from the own-tools spec §3: every refusal of §3 that
belongs to reading fires, per tool where it can, naming the tool and the reason in one line, and
the set-level refusals fire.  Every refusal here is pinned against an accepted control that
differs in the one thing under test, never by the words of its message: a refusal is a
`Refusal` in `reading.refused` (per tool) or an `OwnToolsError` (the set), and which one fired is
read off `Refusal.kind`, one of `REFUSAL_KINDS`.

Shapes decided here
-------------------

**1. The renaming** (§3's first bullet).  Characters outside letters, digits, `_` and `-` become
`_`; then a name over 64 characters is cut to its first 55 characters, `_`, and the first 8 hex
digits of the SHA-256 of the original name's UTF-8 bytes (the one hash this package uses; "its
digest" in §3 is the name's).  A legal name is unchanged and has no title; a renamed tool's title
is its original name.  After the renaming only an empty name, or a name that is not text, is
illegal (kind `name`); a name that then repeats an earlier tool's, whether the file wrote it twice
or two names renamed to one, is refused as the later one, in file order (kind `duplicate`), and
the earlier tool is kept.

**2. "A JSON object schema"** (kind `not_object`) is a mapping whose `type` is `"object"`, or
with no `type` and a `properties` mapping; anything else, a list type included, is not.

**3. The schema rule applies to the argument schema** (kind `schema`): `anyOf`, `oneOf`, `allOf`,
`not`, `patternProperties`, a mapping-valued `additionalProperties` (a boolean is fine), a `$ref`
cycle, or nesting deeper than three levels, anywhere in it.  The argument object is level 0, its
properties' schemas level 1, their properties or items level 2, theirs level 3, and a schema at
level 4 is one too deep; an array's `items` counts a level as an object's properties do.  The
output schema is not held to it (the simulator generates from it and checks nothing against it),
except that a `$ref` cycle there is refused too, since it cannot be inlined.

**4. A file, a binary string or a stream** (kind `binary`): `format: binary` or a `contentEncoding`
anywhere in the argument schema, or an OpenAPI request body whose media types are all
`application/octet-stream`, `multipart/*` or `text/event-stream`.  `format: byte` is base64 text
and is not refused.

**5. The OpenAPI merge** (kind `merge`): a name that would appear twice in the merged object, from
a parameter and a body field or from two parameters in different places.

**6. A target** (`can_target`) is a tool with at least one argument that is not free text: a
parameter whose schema is not a string, or a string with a `format`, an `enum` or `const`, or a
`minLength` or `maxLength`.  A `pattern` is not one of §3's three (format, enum or bound) and does
not make a target; a tool with no arguments has nothing to check and is not one either.  Only the
tool's own (top-level) parameters count.

**7. The set** (`OwnToolsError`): fewer than 2 usable tools or more than 256, or no usable tool
that can be a target.  The error carries the per-tool refusals found on the way, so `init` can
still list them, and its `kind` (one of `ERROR_KINDS`: `shape`, `format`, `too_few`, `too_many`,
`no_target`, `effects`, `consent`, `server`) says which whole-file refusal it is, so a test can
tell them apart without reading the message.  An empty tools list is a file of the OpenAI shape
with no tools, refused as too few.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from poisson_tasks import own
from tests.o1_support import (
    PARTNER_PARAMS,
    by_name,
    function,
    mcp_file,
    mcp_partner,
    mcp_tool,
    names,
    openai_file,
    openapi_file,
    openapi_partner_path,
    operation,
    param,
    partner,
    read,
    refused,
)

LEGAL = r"^[A-Za-z0-9_-]{1,64}$"


def integer_params(*fields: str) -> dict[str, Any]:
    return {"type": "object", "properties": {f: {"type": "integer"} for f in fields}, "required": list(fields)}


# --------------------------------------------------------------------------
# the renaming
# --------------------------------------------------------------------------


def test_a_name_is_renamed_once_and_the_original_is_kept_as_the_title() -> None:
    long = "x" * 70
    long_odd = "a.b" * 30  # 90 characters, renamed and then cut
    reading = read(openai_file(partner("my.tool"), partner("my tool!"), partner("fine_name-1"),
                               partner(long), partner(long_odd)))
    assert reading.refused == ()
    assert names(reading)[:3] == ["my_tool", "my_tool_", "fine_name-1"]
    assert by_name(reading, "my_tool").title == "my.tool"
    assert by_name(reading, "my_tool_").title == "my tool!"
    assert by_name(reading, "fine_name-1").title is None
    cut = names(reading)[3]
    assert cut == "x" * 55 + "_" + hashlib.sha256(long.encode()).hexdigest()[:8]
    assert by_name(reading, cut).title == long
    cut_odd = names(reading)[4]
    assert cut_odd == ("a_b" * 30)[:55] + "_" + hashlib.sha256(long_odd.encode()).hexdigest()[:8]
    assert by_name(reading, cut_odd).title == long_odd
    assert own.safe_name("my.tool") == "my_tool" and own.safe_name("fine_name-1") == "fine_name-1"
    assert own.safe_name(long) == cut and own.safe_name(long_odd) == cut_odd
    assert own.safe_name("x" * 64) == "x" * 64
    assert own.safe_name("") == ""


@settings(max_examples=300)
@given(st.text(min_size=1, max_size=200))
def test_safe_name_always_gives_a_legal_name_and_leaves_one_alone(original: str) -> None:
    import re

    renamed = own.safe_name(original)
    assert re.fullmatch(LEGAL, renamed), (original, renamed)
    assert own.safe_name(renamed) == renamed
    if re.fullmatch(LEGAL, original):
        assert renamed == original


def test_an_empty_or_non_text_name_is_refused_after_the_renaming() -> None:
    bad = openai_file(partner(""), partner("alpha"), partner("beta"))
    reading = read(bad)
    assert names(reading) == ["alpha", "beta"]
    assert refused(reading) == [("", "name")]
    numbered = json.loads(openai_file(partner("x"), partner("alpha"), partner("beta")))
    numbered[0]["function"]["name"] = 7
    reading = read(json.dumps(numbered).encode())
    assert names(reading) == ["alpha", "beta"]
    assert [r.kind for r in reading.refused] == ["name"]
    control = read(openai_file(partner("x"), partner("alpha"), partner("beta")))
    assert control.refused == () and names(control) == ["x", "alpha", "beta"]


def test_a_name_that_repeats_an_earlier_ones_is_refused_and_the_earlier_tool_is_kept() -> None:
    twice = read(openai_file(partner("alpha"), function("alpha", integer_params("other")), partner("beta")))
    assert names(twice) == ["alpha", "beta"]
    assert by_name(twice, "alpha").input_schema == PARTNER_PARAMS
    assert refused(twice) == [("alpha", "duplicate")]
    collided = read(openai_file(partner("a.b"), partner("a_b"), partner("beta")))
    assert names(collided) == ["a_b", "beta"]
    assert by_name(collided, "a_b").title == "a.b"
    assert refused(collided) == [("a_b", "duplicate")]
    control = read(openai_file(partner("a.b"), partner("a_c"), partner("beta")))
    assert control.refused == () and names(control) == ["a_b", "a_c", "beta"]
    # a refused tool does not keep its name from a later tool
    after_refused = read(openai_file(function("alpha", {"type": "array"}), partner("alpha"), partner("beta")))
    assert names(after_refused) == ["alpha", "beta"]
    assert refused(after_refused) == [("alpha", "not_object")]


# --------------------------------------------------------------------------
# the argument schema
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "parameters",
    [{"type": "array", "items": {"type": "string"}}, {"type": "string"}, "not a mapping", 7,
     {"type": ["object", "null"], "properties": {}}, {"type": "integer", "properties": {}}],
    ids=["array", "string", "text", "number", "type-list", "integer-with-properties"],
)
def test_an_argument_schema_that_is_not_an_object_is_refused(parameters: Any) -> None:
    reading = read(openai_file(function("alpha", parameters), partner(), partner("gamma")))
    assert names(reading) == ["partner_write", "gamma"]
    assert refused(reading) == [("alpha", "not_object")]


def test_an_object_schema_may_leave_its_type_implicit() -> None:
    implicit = {"properties": {"n": {"type": "integer"}}, "required": ["n"]}
    reading = read(openai_file(function("alpha", implicit), partner(), partner("gamma")))
    assert reading.refused == () and by_name(reading, "alpha").input_schema == implicit
    bare_object = read(openai_file(function("alpha", {"type": "object"}), partner(), partner("gamma")))
    assert bare_object.refused == () and by_name(bare_object, "alpha").input_schema == {"type": "object"}
    array_body = openapi_file({"/users": {"post": operation("createUsers", body={"type": "array", "items": {"type": "object"}})},
                               "/counts": {"post": operation("countThings", body=implicit)},
                               **openapi_partner_path()})
    assert refused(read(array_body)) == [("createUsers", "not_object")]
    assert names(read(array_body)) == ["countThings", "partner_write", "partner_write_2"]


def nested(inner: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": {"outer": {"type": "object", "properties": {"k": inner}}}}


@pytest.mark.parametrize(
    "bad, control",
    [
        ({"anyOf": [{"type": "string"}, {"type": "integer"}]}, {"type": "string", "format": "date"}),
        ({"oneOf": [{"type": "string"}, {"type": "integer"}]}, {"type": "string", "format": "date"}),
        ({"allOf": [{"type": "string"}]}, {"type": "string", "format": "date"}),
        ({"type": "string", "not": {"enum": ["x"]}}, {"type": "string", "enum": ["x"]}),
        ({"type": "object", "patternProperties": {"^x": {"type": "string"}}}, {"type": "object", "properties": {"x": {"type": "string"}}}),
        ({"type": "object", "additionalProperties": {"type": "string"}}, {"type": "object", "additionalProperties": False}),
        ({"type": "object", "additionalProperties": {}}, {"type": "object", "additionalProperties": True}),
    ],
    ids=["anyOf", "oneOf", "allOf", "not", "patternProperties", "additionalProperties-schema",
         "additionalProperties-empty-schema"],
)
def test_schema_features_the_simulator_cannot_check_exactly_are_refused(bad: dict[str, Any], control: dict[str, Any]) -> None:
    for wrap in (lambda s: {"type": "object", "properties": {"k": s}}, nested):
        reading = read(openai_file(function("alpha", wrap(bad)), partner(), partner("gamma")))
        assert refused(reading) == [("alpha", "schema")]
        accepted = read(openai_file(function("alpha", wrap(control)), partner(), partner("gamma")))
        assert accepted.refused == () and by_name(accepted, "alpha").input_schema == wrap(control)
    # at the top of the argument object itself
    top_bad = {"properties": {}, **bad, "type": "object"}
    assert refused(read(openai_file(function("alpha", top_bad), partner(), partner("gamma")))) == [("alpha", "schema")]


def test_a_ref_cycle_is_refused_and_a_resolvable_ref_is_inlined() -> None:
    cyclic = {
        "type": "object",
        "properties": {"node": {"$ref": "#/$defs/Node"}},
        "$defs": {"Node": {"type": "object", "properties": {"next": {"$ref": "#/$defs/Node"}}}},
    }
    acyclic = {
        "type": "object",
        "properties": {"node": {"$ref": "#/$defs/Node"}},
        "$defs": {"Node": {"type": "object", "properties": {"leaf": {"$ref": "#/$defs/Leaf"}}},
                  "Leaf": {"type": "integer"}},
    }
    bad = read(mcp_file(mcp_tool("alpha", cyclic), mcp_partner(), mcp_partner("gamma")))
    assert refused(bad) == [("alpha", "schema")]
    good = read(mcp_file(mcp_tool("alpha", acyclic), mcp_partner(), mcp_partner("gamma")))
    assert good.refused == ()
    assert by_name(good, "alpha").input_schema == {
        "type": "object",
        "properties": {"node": {"type": "object", "properties": {"leaf": {"type": "integer"}}}},
    }
    # a dangling `$ref` is a schema the simulator cannot read either
    dangling = {"type": "object", "properties": {"node": {"$ref": "#/$defs/Missing"}}}
    assert refused(read(mcp_file(mcp_tool("alpha", dangling), mcp_partner(), mcp_partner("gamma")))) == [("alpha", "schema")]
    # the output: a cycle is refused, a composition is not
    out_cycle = read(mcp_file(mcp_tool("alpha", PARTNER_PARAMS, output_schema=cyclic), mcp_partner(), mcp_partner("gamma")))
    assert refused(out_cycle) == [("alpha", "schema")]
    out_any = {"type": "object", "properties": {"v": {"anyOf": [{"type": "string"}, {"type": "integer"}]}}}
    out_ok = read(mcp_file(mcp_tool("alpha", PARTNER_PARAMS, output_schema=out_any), mcp_partner(), mcp_partner("gamma")))
    assert out_ok.refused == () and by_name(out_ok, "alpha").output_schema == out_any


def test_nesting_deeper_than_three_levels_is_refused() -> None:
    def levels(depth: int, via_array: bool = False) -> dict[str, Any]:
        """An argument object whose deepest schema sits at level `depth`."""
        schema: dict[str, Any] = {"type": "integer"}
        for level in range(depth, 0, -1):
            if via_array and level == 2:
                schema = {"type": "array", "items": schema}
            else:
                schema = {"type": "object", "properties": {f"p{level}": schema}}
        return schema

    three = read(openai_file(function("alpha", levels(3)), partner(), partner("gamma")))
    assert three.refused == () and by_name(three, "alpha").input_schema == levels(3)
    assert refused(read(openai_file(function("alpha", levels(4)), partner(), partner("gamma")))) == [("alpha", "schema")]
    three_array = read(openai_file(function("alpha", levels(3, via_array=True)), partner(), partner("gamma")))
    assert three_array.refused == ()
    assert refused(read(openai_file(function("alpha", levels(4, via_array=True)), partner(), partner("gamma")))) == [("alpha", "schema")]
    # a deep output is not refused
    deep_out = read(mcp_file(mcp_tool("alpha", PARTNER_PARAMS, output_schema=levels(5)), mcp_partner(), mcp_partner("gamma")))
    assert deep_out.refused == ()


# --------------------------------------------------------------------------
# files, binary strings and streams
# --------------------------------------------------------------------------


def test_a_tool_taking_a_file_a_binary_string_or_a_stream_is_refused() -> None:
    binary: dict[str, Any] = {"type": "object", "properties": {"blob": {"type": "string", "format": "binary"}}}
    encoded: dict[str, Any] = {"type": "object", "properties": {"blob": {"type": "string", "contentEncoding": "base64"}}}
    byte_format = {"type": "object", "properties": {"blob": {"type": "string", "format": "byte"}}}
    for bad in (binary, encoded, nested(binary["properties"]["blob"]), nested(encoded["properties"]["blob"])):
        assert refused(read(openai_file(function("alpha", bad), partner(), partner("gamma")))) == [("alpha", "binary")]
    for ok in (byte_format, {"type": "object", "properties": {"blob": {"type": "string", "format": "uuid"}}}):
        assert read(openai_file(function("alpha", ok), partner(), partner("gamma"))).refused == ()
    body = {"type": "string", "format": "binary"}
    for media in ("application/octet-stream", "multipart/form-data", "text/event-stream"):
        paths = {"/up": {"post": operation("upload", body=body, body_media=media)}, **openapi_partner_path()}
        assert refused(read(openapi_file(paths))) == [("upload", "binary")], media
    multipart_object = {"type": "object", "properties": {"name": {"type": "string"}, "file": {"type": "string", "format": "binary"}}}
    paths = {"/up": {"post": operation("upload", body=multipart_object, body_media="multipart/form-data")}, **openapi_partner_path()}
    assert refused(read(openapi_file(paths))) == [("upload", "binary")]
    control = {"/up": {"post": operation("upload", body={"type": "object", "properties": {"name": {"type": "string"}}})},
               **openapi_partner_path()}
    assert read(openapi_file(control)).refused == ()
    # a body offering a file type beside a form is read from the form
    mixed = operation("upload", body=multipart_object, body_media="multipart/form-data")
    mixed["requestBody"]["content"]["application/x-www-form-urlencoded"] = {
        "schema": {"type": "object", "properties": {"name": {"type": "string"}}}}
    mixed_reading = read(openapi_file({"/up": {"post": mixed}, **openapi_partner_path()}))
    assert mixed_reading.refused == () and by_name(mixed_reading, "upload").input_schema["properties"] == {"name": {"type": "string"}}


# --------------------------------------------------------------------------
# the OpenAPI merge
# --------------------------------------------------------------------------


def test_an_openapi_parameter_sharing_a_body_fields_name_is_refused() -> None:
    body = {"type": "object", "properties": {"id": {"type": "integer"}, "note": {"type": "string"}}}
    clash = {"/things/{id}": {"put": operation("rename", parameters=[param("id", "path", {"type": "integer"})], body=body)},
             **openapi_partner_path()}
    assert refused(read(openapi_file(clash))) == [("rename", "merge")]
    two_places = {"/things/{id}": {"get": operation("readThing", parameters=[
        param("id", "path", {"type": "integer"}), param("id", "query", {"type": "integer"}, required=False)])},
        **openapi_partner_path()}
    assert refused(read(openapi_file(two_places))) == [("readThing", "merge")]
    control_body = {"type": "object", "properties": {"thing_id": {"type": "integer"}, "note": {"type": "string"}}}
    control = {"/things/{id}": {"put": operation("rename", parameters=[param("id", "path", {"type": "integer"})], body=control_body)},
               **openapi_partner_path()}
    reading = read(openapi_file(control))
    assert reading.refused == ()
    merged: dict[str, Any] = by_name(reading, "rename").input_schema
    assert set(merged["properties"]) == {"id", "thing_id", "note"}


# --------------------------------------------------------------------------
# a set with refused tools, and the set-level refusals
# --------------------------------------------------------------------------


def test_a_set_with_refused_tools_still_reads_the_rest_and_each_refusal_is_one_line() -> None:
    reading = read(openai_file(partner("alpha"), function("beta", {"type": "array"}), partner("gamma"),
                               function("delta", {"type": "object", "properties": {"k": {"anyOf": []}}}),
                               partner("epsilon")))
    assert names(reading) == ["alpha", "gamma", "epsilon"]
    assert refused(reading) == [("beta", "not_object"), ("delta", "schema")]
    for refusal in reading.refused:
        assert isinstance(refusal, own.Refusal)
        assert refusal.kind in own.REFUSAL_KINDS
        assert refusal.line.count("\n") == 0 and refusal.line.strip() == refusal.line
        assert refusal.name in refusal.line and refusal.reason in refusal.line
        assert refusal.reason.strip()


def test_a_set_needs_two_to_256_usable_tools() -> None:
    with pytest.raises(own.OwnToolsError) as caught:
        read(openai_file(partner("alpha"), function("beta", {"type": "array"})))
    assert [(r.name, r.kind) for r in caught.value.refused] == [("beta", "not_object")]
    assert caught.value.kind == "too_few" and caught.value.kind in own.ERROR_KINDS
    assert str(caught.value).count("\n") == 0
    assert isinstance(caught.value, ValueError)
    with pytest.raises(own.OwnToolsError) as empty:
        read(b"[]")
    assert empty.value.kind == "too_few"
    two = read(openai_file(partner("alpha"), partner("beta")))
    assert names(two) == ["alpha", "beta"]
    many = [partner(f"tool_{i:03d}") for i in range(257)]
    assert len(names(read(openai_file(*many[:256])))) == 256
    with pytest.raises(own.OwnToolsError) as caught:
        read(openai_file(*many))
    assert caught.value.kind == "too_many"
    # the limit counts usable tools: 256 usable beside one refused is within it
    assert len(names(read(openai_file(*many[:256], function("bad", {"type": "array"}))))) == 256


def test_a_set_needs_a_tool_that_can_be_a_target() -> None:
    free = {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}
    with pytest.raises(own.OwnToolsError) as caught:
        read(openai_file(function("alpha", free), function("beta", free)))
    assert caught.value.kind == "no_target"
    with pytest.raises(own.OwnToolsError) as no_args:
        read(openai_file(function("alpha", free), function("beta")))
    assert no_args.value.kind == "no_target"
    bounded = {"type": "object", "properties": {"query": {"type": "string", "maxLength": 40}}, "required": ["query"]}
    reading = read(openai_file(function("alpha", free), function("beta", bounded)))
    assert names(reading) == ["alpha", "beta"]
    assert [own.can_target(t) for t in reading.toolset.tools] == [False, True]


@pytest.mark.parametrize(
    "properties, expected",
    [
        ({"query": {"type": "string"}}, False),
        ({"query": {"type": "string", "description": "Words."}}, False),
        ({"query": {}}, False),
        ({"query": {"type": "string", "pattern": "^[a-z]+$"}}, False),
        ({"query": {"type": "string"}, "note": {"type": "string"}}, False),
        ({}, False),
        ({"when": {"type": "string", "format": "date"}}, True),
        ({"kind": {"type": "string", "enum": ["a", "b"]}}, True),
        ({"kind": {"type": "string", "const": "a"}}, True),
        ({"code": {"type": "string", "minLength": 4}}, True),
        ({"code": {"type": "string", "maxLength": 4}}, True),
        ({"n": {"type": "integer"}}, True),
        ({"x": {"type": "number"}}, True),
        ({"flag": {"type": "boolean"}}, True),
        ({"tags": {"type": "array", "items": {"type": "string"}}}, True),
        ({"where": {"type": "object", "properties": {"q": {"type": "string"}}}}, True),
        ({"query": {"type": "string"}, "n": {"type": "integer"}}, True),
    ],
    ids=["free-string", "described-string", "untyped", "pattern-only", "two-free-strings", "no-arguments",
         "format", "enum", "const", "minLength", "maxLength", "integer", "number", "boolean", "array",
         "object", "free-and-integer"],
)
def test_can_target_needs_one_argument_that_is_not_free_text(properties: dict[str, Any], expected: bool) -> None:
    schema = {"type": "object", "properties": properties}
    reading = read(openai_file(function("alpha", schema), partner(), partner("gamma")))
    assert reading.refused == ()
    assert own.can_target(by_name(reading, "alpha")) is expected
