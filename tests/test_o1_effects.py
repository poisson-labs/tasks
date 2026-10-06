"""Read or write: what each format says of a tool's effect, frozen as tests (O1.2).

The invariant is O1.2 of the knobs plan, from the own-tools spec §2.1's last column and §2.3.
MCP's annotations and OpenAPI's HTTP methods say which tools change state; OpenAI schemas do not,
so an OpenAI tool's effect is `unknown` and is treated as a write (the safe reading) until the
user says otherwise in `tasks.toml`.

Shapes decided here
-------------------

**1. `annotations` present means present**, even empty: an author who wrote an annotations object
and did not say `readOnlyHint: true` has a write (the MCP default for the hint is false), and a
value that is not the boolean `true` is not true.  No `annotations` key at all is `unknown`.

**2. Methods the spec does not list** (`options`, `trace`) are `unknown`, not guessed.

**3. `is_write` is the verifier's question**: does a stray call to this tool count against the
model?  It is true for `write` and for `unknown`, false for `read`.

**4. `apply_effects` is where `tasks.toml`'s `read = [...]` and `write = [...]` land** (§2.3 and
§8.2).  It gives a new set with the named tools' effects set, the rest untouched, and the set's
name, format and digest unchanged (the file did not change).  It refuses a name the set does not
hold (a typo would otherwise be silent) and a name in both lists.
"""

from __future__ import annotations

from typing import Any

import pytest

from poisson_tasks import own
from tests.o1_support import (
    PARTNER_PARAMS,
    by_name,
    fixture,
    mcp_file,
    mcp_partner,
    mcp_tool,
    openai_file,
    openapi_file,
    operation,
    partner,
    read,
)


@pytest.mark.parametrize(
    "annotations, effect",
    [
        ({"readOnlyHint": True}, "read"),
        ({"readOnlyHint": True, "destructiveHint": True}, "read"),
        ({}, "write"),
        ({"readOnlyHint": False}, "write"),
        ({"destructiveHint": True}, "write"),
        ({"idempotentHint": True}, "write"),
        ({"readOnlyHint": "yes"}, "write"),
        ({"readOnlyHint": 1}, "write"),
        (None, "unknown"),
    ],
    ids=["read-only", "read-only-and-destructive", "empty", "not-read-only", "destructive",
         "idempotent-only", "string-yes", "one", "absent"],
)
def test_mcp_annotations_decide_the_effect(annotations: Any, effect: str) -> None:
    reading = read(mcp_file(mcp_tool("alpha", PARTNER_PARAMS, annotations=annotations), mcp_partner()))
    assert reading.refused == ()
    assert by_name(reading, "alpha").effect == effect


def test_http_methods_decide_the_effect() -> None:
    body = {"type": "object", "properties": {"n": {"type": "integer"}}, "required": ["n"]}
    methods = ("get", "head", "post", "put", "patch", "delete", "options", "trace")
    paths = {
        f"/{method}": {method: operation(f"op_{method}", body=body if method in ("post", "put", "patch") else None)}
        for method in methods
    }
    reading = read(openapi_file(paths))
    assert reading.refused == ()
    assert {t.name: t.effect for t in reading.toolset.tools} == {
        "op_get": "read", "op_head": "read",
        "op_post": "write", "op_put": "write", "op_patch": "write", "op_delete": "write",
        "op_options": "unknown", "op_trace": "unknown",
    }


def test_openai_tools_are_unknown_and_unknown_counts_as_a_write() -> None:
    reading = read(fixture("acme-openai-chat.json"))
    assert {t.effect for t in reading.toolset.tools} == {"unknown"}
    assert all(own.is_write(t) for t in reading.toolset.tools)
    mcp = read(fixture("acme-mcp-tools-list.json"))
    assert [own.is_write(t) for t in mcp.toolset.tools] == [False, False, True, True, False]
    assert [t.effect for t in mcp.toolset.tools] == ["read", "read", "write", "write", "read"]


def test_apply_effects_sets_what_the_user_says_and_refuses_what_it_cannot() -> None:
    before = read(openai_file(partner("alpha"), partner("beta"), partner("gamma"))).toolset
    after = own.apply_effects(before, read=["alpha"], write=["beta"])
    assert isinstance(after, own.OwnToolSet)
    assert [t.effect for t in after.tools] == ["read", "write", "unknown"]
    assert [t.effect for t in before.tools] == ["unknown"] * 3  # the input is not changed in place
    assert (after.name, after.source_format, after.file_digest) == (before.name, before.source_format, before.file_digest)
    assert [(t.name, t.description, t.input_schema, t.output_schema, t.title) for t in after.tools] == [
        (t.name, t.description, t.input_schema, t.output_schema, t.title) for t in before.tools
    ]
    assert own.apply_effects(before) == before
    # a read declared on a tool the format already called a write is the user's call to make
    mcp = read(mcp_file(mcp_tool("alpha", PARTNER_PARAMS, annotations={}), mcp_partner())).toolset
    assert [t.effect for t in own.apply_effects(mcp, read=["alpha"]).tools] == ["read", "write"]
    with pytest.raises(own.OwnToolsError) as unknown:
        own.apply_effects(before, read=["delta"])
    assert unknown.value.kind == "effects"
    with pytest.raises(own.OwnToolsError) as both:
        own.apply_effects(before, read=["alpha"], write=["alpha"])
    assert both.value.kind == "effects"
    # a renamed tool is named by its name in the set, not by its title
    renamed = read(openai_file(partner("my.tool"), partner("beta"))).toolset
    assert [t.effect for t in own.apply_effects(renamed, read=["my_tool"]).tools] == ["read", "unknown"]
    with pytest.raises(own.OwnToolsError):
        own.apply_effects(renamed, read=["my.tool"])
