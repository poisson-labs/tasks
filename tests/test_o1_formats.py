"""The three input formats and the normal form they become, frozen as tests.

Fixture files in each format read to the same `OwnToolSet` where they describe the same tools;
`format = "auto"` decides by shape; a file that matches none of the three shapes is refused.  The
acme-support fixtures (`tests/fixtures/o1/acme-*`) are one set of five tools written in six shapes:
OpenAI Chat Completions, OpenAI Responses wrapped in a `tools` object, a bare MCP `tools/list`
result, its JSON-RPC envelope, OpenAPI 3.0 as JSON and OpenAPI 3.1 as YAML.  The MCP Everything
reference server's `tools/list` (`mcp-everything-tools-list.json`, server version 2.0.0) and the
Swagger Petstore document (`petstore-openapi-3.0.json`, OpenAPI 3.0.4) are the two public fixtures
the design names, read as recorded.

Shapes decided here
-------------------

**1. "The same `OwnToolSet`" is the same tools.**  The set's `source_format` and `file_digest`
differ by file, so the equality is over the tools: name, description, argument schema, output
schema and effect, in file order.  OpenAI tools have no output shape and no effect in the format,
so for them the equality leaves out the output (`None`) and the effect (`unknown`).

**2. Schemas are kept as written, with every `$ref` inlined.**  The reader does not rewrite a
schema: an MCP `inputSchema` with a `$schema` key keeps it, and an OpenAPI parameter's schema is
the parameter's own, with the parameter's `description` put into it when the schema has none, so
the model reads what the author wrote.  A `$ref` is replaced by what it names, at any depth, in
parameters, request bodies, responses and schemas alike; sibling keys beside a `$ref` win over the
referenced schema's.  An OpenAI tool with no `parameters` key is `{"type": "object", "properties":
{}}`, the one empty object this package writes.

**3. The OpenAPI merged object.**  `{"type": "object", "properties": {...}}` holding every path,
query and header parameter and every field of the JSON request body; `required` lists the
parameters marked required, in document order, then the body schema's `required` list, and is left
out when empty.  Path-level parameters apply to every operation under the path, and an operation's
parameter of the same name and place replaces it.  Cookie parameters, and header parameters named
`Accept`, `Content-Type` or `Authorization` (which OpenAPI says to ignore), are left out.  A body is
read from its `application/json` content (any `*/json` or `*+json` media type); a body with no JSON
content is read from its first media type that is not a file's or a stream's and holds an object
schema.

**4. The output.**  The first response in document order whose code is `2xx` (or `2XX`) and has
JSON content gives the output schema; with none, the output is `None`.  Codes outside `2xx` and
`default` are not read.

**5. `method_path made safe`.**  An operation without an `operationId` is named
`safe_name(f"{method}_{path}")`, the method in lower case, and the unsafe `f"{method}_{path}"` is
its title, so the original is kept as the design says of every renamed tool.

**6. Shapes, for `auto`.**  A mapping with a top-level `openapi` key whose value starts with
`3.0.` or `3.1.` is OpenAPI.  A mapping with a `tools` list whose items have `inputSchema`, the same
under a `result` key, or a list of such pages, is MCP; the pages are merged in order.  A list, or a
mapping with a `tools` list, whose items are mappings with a `type` key is OpenAI.  Anything else,
including a file that is neither JSON nor YAML, a YAML scalar, Swagger 2.0 and OpenAPI versions
outside 3.0 and 3.1, matches none and is refused.  An explicit format that does not match the
file's shape is refused the same way.  JSON is read first and YAML second, so any format may come as
YAML, though only OpenAPI is promised that way.

**7. OpenAI shapes.**  Chat Completions and Responses items may mix in one list.  An item whose
`type` is not `function` is one of the Responses API's built-in tools and is refused per tool
(kind `builtin`), named by its type; the functions beside it still read.  A missing `description`
is the empty string.  `strict` is not carried: the normal form has no field for it.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from poisson_tasks import own
from tests.o1_support import (
    by_name,
    fixture,
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

ACME = {
    "acme-openai-chat.json": "openai",
    "acme-openai-responses.json": "openai",
    "acme-mcp-tools-list.json": "mcp",
    "acme-mcp-envelope.json": "mcp",
    "acme-openapi-3.0.json": "openapi",
    "acme-openapi-3.1.yaml": "openapi",
}
ACME_NAMES = ["get_order", "search_orders", "refund_order", "notify_customer", "list_channels"]
EMPTY_OBJECT: dict[str, Any] = {"type": "object", "properties": {}}


def normal(reading: own.Reading) -> list[tuple[str, str, dict[str, Any], dict[str, Any] | None, str]]:
    return [
        (t.name, t.description, t.input_schema, t.output_schema, t.effect)
        for t in reading.toolset.tools
    ]


def has_ref(value: Any) -> bool:
    if isinstance(value, dict):
        return "$ref" in value or any(has_ref(v) for v in value.values())
    if isinstance(value, list):
        return any(has_ref(v) for v in value)
    return False


# --------------------------------------------------------------------------
# the three formats to one normal form
# --------------------------------------------------------------------------


def test_the_six_acme_files_read_to_the_same_tools() -> None:
    readings = {name: read(fixture(name), name="acme") for name in ACME}
    for name, reading in readings.items():
        assert names(reading) == ACME_NAMES, name
        assert reading.refused == (), name
        assert reading.toolset.name == "acme"
        assert reading.toolset.source_format == ACME[name]
        assert not any(has_ref(t.input_schema) or has_ref(t.output_schema) for t in reading.toolset.tools)
    full = [normal(readings[n]) for n in ACME if ACME[n] != "openai"]
    assert full[0] == full[1] == full[2] == full[3]
    mcp = full[0]
    assert [t[4] for t in mcp] == ["read", "read", "write", "write", "read"]
    assert mcp[3][3] is None and all(t[3] is not None for i, t in enumerate(mcp) if i != 3)
    # OpenAI: the same names, descriptions and argument schemas; no output; unknown effect
    for n in ACME:
        if ACME[n] == "openai":
            assert [(t[0], t[1], t[2]) for t in normal(readings[n])] == [(t[0], t[1], t[2]) for t in mcp]
            assert [(t[3], t[4]) for t in normal(readings[n])] == [(None, "unknown")] * 5
    # the one empty object, from `parameters` absent (OpenAI), `{}` properties (MCP) and no
    # parameters (OpenAPI) alike
    assert mcp[4][2] == EMPTY_OBJECT
    # the 3.1 YAML's `$ref`s are inlined: its merged refund object is the MCP one, byte for byte
    assert mcp[2][2] == {
        "type": "object",
        "properties": {
            "order_id": {
                "type": "string",
                "description": "The order's id, six characters such as A-3317.",
                "minLength": 6,
                "maxLength": 6,
            },
            "amount": {"type": "number", "description": "The amount to refund, in dollars.", "minimum": 0},
            "reason": {
                "type": "string",
                "description": "Why the order is refunded.",
                "enum": ["damaged", "late", "other"],
            },
        },
        "required": ["order_id", "amount"],
    }


@pytest.mark.parametrize("name", sorted(ACME))
def test_auto_decides_by_shape_and_an_explicit_format_must_match(name: str) -> None:
    data = fixture(name)
    expected = ACME[name]
    by_auto = read(data)
    assert by_auto.toolset.source_format == expected
    assert normal(read(data, format=expected)) == normal(by_auto)
    for other in own.FORMATS:
        if other != expected:
            with pytest.raises(own.OwnToolsError) as caught:
                read(data, format=other)
            assert caught.value.kind == "format"
    with pytest.raises(own.OwnToolsError) as bogus:
        read(data, format="swagger")
    assert bogus.value.kind == "format"


@pytest.mark.parametrize(
    "data",
    [
        b'{"foo": 1}',
        b'"just text"',
        b"[1, 2]",
        b"{",
        b"key: [unclosed",
        json.dumps({"swagger": "2.0", "info": {}, "paths": {}}).encode(),
        json.dumps({"openapi": "4.0.0", "info": {}, "paths": {}}).encode(),
        json.dumps({"openapi": "2.0", "info": {}, "paths": {}}).encode(),
        json.dumps({"tools": "no"}).encode(),
        json.dumps({"tools": [{"inputSchema": {}}, "x"]}).encode(),
        json.dumps({"result": {"error": "x"}}).encode(),
    ],
    ids=["mapping", "scalar", "numbers", "not-json", "not-yaml", "swagger-2",
         "openapi-4", "openapi-2", "tools-not-list", "mcp-item-not-mapping", "envelope-without-tools"],
)
def test_a_file_that_matches_none_of_the_three_shapes_is_refused(data: bytes) -> None:
    with pytest.raises(own.OwnToolsError) as caught:
        read(data)
    assert caught.value.kind == "shape" and caught.value.kind in own.ERROR_KINDS
    read(fixture("acme-openai-chat.json"))  # the control: a file of one of the shapes reads


# --------------------------------------------------------------------------
# OpenAI
# --------------------------------------------------------------------------


def test_openai_items_come_in_both_shapes_and_a_tool_without_parameters_gets_the_empty_object() -> None:
    chat = function("alpha", {"type": "object", "properties": {"k": {"type": "integer"}}, "required": ["k"]})
    responses_shape = {"type": "function", "name": "beta", "parameters": chat["function"]["parameters"], "strict": True}
    bare = function("gamma", None, None)
    reading = read(openai_file(chat, responses_shape, bare, partner()))
    assert names(reading) == ["alpha", "beta", "gamma", "partner_write"]
    assert by_name(reading, "beta").input_schema == chat["function"]["parameters"]
    assert by_name(reading, "beta").description == ""
    assert by_name(reading, "gamma").input_schema == EMPTY_OBJECT
    assert by_name(reading, "gamma").description == ""
    for tool in reading.toolset.tools:
        assert tool.effect == "unknown" and tool.output_schema is None and tool.title is None
    wrapped = json.dumps({"tools": [chat, responses_shape, bare, partner()]}).encode()
    assert normal(read(wrapped)) == normal(reading)


def test_openai_built_in_tool_types_are_refused_per_tool_and_the_functions_still_read() -> None:
    alpha = function("alpha", {"type": "object", "properties": {"k": {"type": "integer"}}})
    with_builtins = openai_file(
        alpha, {"type": "web_search"}, partner(), {"type": "file_search", "vector_store_ids": ["vs_1"]}
    )
    reading = read(with_builtins)
    assert names(reading) == ["alpha", "partner_write"]
    assert refused(reading) == [("web_search", "builtin"), ("file_search", "builtin")]
    control = read(openai_file(alpha, partner()))
    assert control.refused == () and normal(control) == normal(reading)


# --------------------------------------------------------------------------
# MCP
# --------------------------------------------------------------------------


def test_mcp_pages_merge_in_order_and_the_envelope_reads_as_the_bare_result() -> None:
    first = mcp_tool("alpha", {"type": "object", "properties": {"k": {"type": "integer"}}})
    second = mcp_partner()
    third = mcp_tool("gamma")
    one_page = mcp_file(first, second, third)
    pages = json.dumps(
        [
            {"tools": [first], "nextCursor": "p2"},
            {"jsonrpc": "2.0", "id": 2, "result": {"tools": [second, third]}},
        ]
    ).encode()
    envelope = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"tools": [first, second, third]}}).encode()
    expected = normal(read(one_page))
    assert names(read(one_page)) == ["alpha", "partner_write", "gamma"]
    for data in (pages, envelope):
        reading = read(data)
        assert reading.toolset.source_format == "mcp"
        assert normal(reading) == expected


# --------------------------------------------------------------------------
# OpenAPI
# --------------------------------------------------------------------------


def test_openapi_names_fall_back_to_method_and_path_and_the_summary_comes_first() -> None:
    integer = {"type": "object", "properties": {"n": {"type": "integer"}}, "required": ["n"]}
    paths = {
        "/pets/{pet_id}": {
            "get": operation(None, summary="Read a pet.", parameters=[param("pet_id", "path", {"type": "integer"})]),
            "delete": operation("dropPet", summary="Drop a pet.", description="The long form.",
                                parameters=[param("pet_id", "path", {"type": "integer"})]),
        },
        "/pets": {
            "post": operation("addPet", summary=None, description="Only a description.", body=integer),
            "put": operation("renamePet", summary=None, body=integer),
        },
    }
    reading = read(openapi_file(paths))
    assert names(reading) == ["get__pets__pet_id_", "dropPet", "addPet", "renamePet"]
    fallback = by_name(reading, "get__pets__pet_id_")
    assert fallback.name == own.safe_name("get_/pets/{pet_id}")
    assert fallback.title == "get_/pets/{pet_id}"
    assert by_name(reading, "dropPet").title is None
    assert [t.description for t in reading.toolset.tools] == ["Read a pet.", "Drop a pet.", "Only a description.", ""]


def test_openapi_parameters_and_the_body_merge_into_one_object() -> None:
    body = {
        "type": "object",
        "properties": {"amount": {"type": "number"}, "note": {"type": "string"}},
        "required": ["amount"],
    }
    paths = {
        "/accounts/{account}/orders/{order}": {
            "parameters": [
                param("account", "path", {"type": "string", "minLength": 4}),
                param("order", "path", {"type": "string", "maxLength": 9}, description="Path-level order."),
                param("trace", "header", {"type": "string", "format": "uuid"}, required=False),
            ],
            "post": operation(
                "pay",
                parameters=[
                    param("order", "path", {"type": "string", "maxLength": 6}, description="The order."),
                    param("dry_run", "query", {"type": "boolean"}, required=True, description="Only check."),
                    param("page", "query", {"type": "integer"}, required=False),
                    param("session", "cookie"),
                    param("Authorization", "header"),
                    param("Content-Type", "header"),
                    param("Accept", "header"),
                ],
                body=body,
            ),
        },
        **openapi_partner_path(),
    }
    reading = read(openapi_file(paths))
    assert reading.refused == ()
    assert by_name(reading, "pay").input_schema == {
        "type": "object",
        "properties": {
            "account": {"type": "string", "minLength": 4},
            "order": {"type": "string", "maxLength": 6, "description": "The order."},
            "trace": {"type": "string", "format": "uuid"},
            "dry_run": {"type": "boolean", "description": "Only check."},
            "page": {"type": "integer"},
            "amount": {"type": "number"},
            "note": {"type": "string"},
        },
        "required": ["account", "order", "dry_run", "amount"],
    }
    # a parameter's own description does not replace one its schema already has
    paths2 = {
        "/x/{k}": {"get": operation("readX", parameters=[
            param("k", "path", {"type": "integer", "description": "Schema's."}, description="Parameter's.")])},
        **openapi_partner_path(),
    }
    assert by_name(read(openapi_file(paths2)), "readX").input_schema["properties"]["k"]["description"] == "Schema's."
    # no parameters and no body: the empty object, with no `required`
    paths3 = {"/x": {"get": operation("listX")}, **openapi_partner_path()}
    assert by_name(read(openapi_file(paths3)), "listX").input_schema == EMPTY_OBJECT


def test_openapi_refs_are_inlined_at_every_depth_and_siblings_win() -> None:
    components = {
        "parameters": {"Id": param("id", "path", {"$ref": "#/components/schemas/Id"}, description="An id.")},
        "requestBodies": {"Move": {"required": True, "content": {"application/json": {
            "schema": {"$ref": "#/components/schemas/Move"}}}}},
        "schemas": {
            "Id": {"type": "integer", "minimum": 1},
            "Move": {"type": "object", "properties": {"to": {"$ref": "#/components/schemas/Shelf"}},
                     "required": ["to"]},
            "Shelf": {"type": "object", "properties": {"code": {"type": "string", "maxLength": 4}},
                      "description": "A shelf."},
            "Crate": {"type": "object", "properties": {"id": {"$ref": "#/components/schemas/Id"},
                                                       "shelf": {"$ref": "#/components/schemas/Shelf",
                                                                 "description": "Where it stands."}}},
        },
    }
    paths = {
        "/crates/{id}": {"post": operation(
            "move", parameters=[{"$ref": "#/components/parameters/Id"}],
            body={"$ref": "#/components/requestBodies/Move"},
            responses={"200": {"description": "OK.", "content": {"application/json": {
                "schema": {"$ref": "#/components/schemas/Crate"}}}}})},
        **openapi_partner_path(),
    }
    doc = json.loads(openapi_file(paths, components=components))
    doc["paths"]["/crates/{id}"]["post"]["requestBody"] = {"$ref": "#/components/requestBodies/Move"}
    # the whole response by reference too, as large documents write it
    doc["components"]["responses"] = {"Crate": doc["paths"]["/crates/{id}"]["post"]["responses"]["200"]}
    doc["paths"]["/crates/{id}"]["post"]["responses"] = {"200": {"$ref": "#/components/responses/Crate"}}
    reading = read(json.dumps(doc).encode())
    assert reading.refused == ()
    move = by_name(reading, "move")
    assert move.input_schema == {
        "type": "object",
        "properties": {
            "id": {"type": "integer", "minimum": 1, "description": "An id."},
            "to": {"type": "object", "properties": {"code": {"type": "string", "maxLength": 4}},
                   "description": "A shelf."},
        },
        "required": ["id", "to"],
    }
    assert move.output_schema == {
        "type": "object",
        "properties": {
            "id": {"type": "integer", "minimum": 1},
            "shelf": {"type": "object", "properties": {"code": {"type": "string", "maxLength": 4}},
                      "description": "Where it stands."},
        },
    }


def test_openapi_output_is_the_first_2xx_responses_json_schema() -> None:
    made = {"type": "object", "properties": {"id": {"type": "integer"}}}
    shown = {"type": "object", "properties": {"name": {"type": "string"}}}
    integer = {"type": "object", "properties": {"n": {"type": "integer"}}, "required": ["n"]}

    def post(responses: dict[str, Any], name: str) -> dict[str, Any]:
        return {"post": operation(name, body=integer, responses=responses)}

    paths = {
        "/a": post({"404": {"description": "No.", "content": {"application/json": {"schema": shown}}},
                    "201": {"description": "Made.", "content": {"application/json": {"schema": made}}},
                    "200": {"description": "OK.", "content": {"application/json": {"schema": shown}}}}, "a"),
        "/b": post({"204": {"description": "Gone."}}, "b"),
        "/c": post({"200": {"description": "Text.", "content": {"text/plain": {"schema": {"type": "string"}}}}}, "c"),
        "/d": post({"default": {"description": "Any.", "content": {"application/json": {"schema": shown}}}}, "d"),
        "/e": post({"2XX": {"description": "Any 2xx.", "content": {"application/problem+json": {"schema": shown}}}}, "e"),
        "/f": post({"200": {"description": "Two media types.", "content": {
            "application/xml": {"schema": made}, "application/json": {"schema": shown}}}}, "f"),
    }
    reading = read(openapi_file(paths))
    outputs = {t.name: t.output_schema for t in reading.toolset.tools}
    assert outputs == {"a": made, "b": None, "c": None, "d": None, "e": shown, "f": shown}


def test_openapi_bodies_are_read_from_json_content_first() -> None:
    json_body = {"type": "object", "properties": {"amount": {"type": "number"}}, "required": ["amount"]}
    form_body = {"type": "object", "properties": {"amount_as_text": {"type": "string"}}}
    both = operation("pay", body=json_body)
    both["requestBody"]["content"] = {
        "application/x-www-form-urlencoded": {"schema": form_body},
        "application/json": {"schema": json_body},
    }
    form_only = operation("pay_form", body=form_body, body_media="application/x-www-form-urlencoded")
    reading = read(openapi_file({"/pay": {"post": both}, "/pay-form": {"post": form_only}}))
    assert reading.refused == ()
    assert by_name(reading, "pay").input_schema["properties"] == json_body["properties"]
    assert by_name(reading, "pay_form").input_schema["properties"] == form_body["properties"]


def test_the_petstore_document_reads_as_recorded() -> None:
    """Swagger Petstore (OpenAPI 3.0.4, fetched 2026-10-06 from petstore3.swagger.io, version
    1.0.27): nineteen operations, three of them refused by the reading rules as they stand in a real
    document: `uploadFile` takes an `application/octet-stream` body, `createUsersWithListInput`
    takes an array, and `updateUser` puts `username` both in its path and in its `User` body."""
    data = fixture("petstore-openapi-3.0.json")
    reading = read(data, name="petstore")
    assert reading.toolset.source_format == "openapi"
    assert refused(reading) == [
        ("uploadFile", "binary"),
        ("createUsersWithListInput", "not_object"),
        ("updateUser", "merge"),
    ]
    assert names(reading) == [
        "updatePet", "addPet", "findPetsByStatus", "findPetsByTags", "getPetById", "updatePetWithForm",
        "deletePet", "getInventory", "placeOrder", "getOrderById", "deleteOrder", "createUser",
        "loginUser", "logoutUser", "getUserByName", "deleteUser",
    ]
    assert {t.name: t.effect for t in reading.toolset.tools} == {
        "updatePet": "write", "addPet": "write", "findPetsByStatus": "read", "findPetsByTags": "read",
        "getPetById": "read", "updatePetWithForm": "write", "deletePet": "write", "getInventory": "read",
        "placeOrder": "write", "getOrderById": "read", "deleteOrder": "write", "createUser": "write",
        "loginUser": "read", "logoutUser": "read", "getUserByName": "read", "deleteUser": "write",
    }
    assert {t.name for t in reading.toolset.tools if not own.can_target(t)} == {
        "getInventory", "loginUser", "logoutUser", "getUserByName", "deleteUser",
    }
    assert all(t.title is None for t in reading.toolset.tools)
    assert not any(has_ref(t.input_schema) or has_ref(t.output_schema) for t in reading.toolset.tools)
    assert by_name(reading, "getPetById").input_schema == {
        "type": "object",
        "properties": {"petId": {"type": "integer", "format": "int64", "description": "ID of pet to return"}},
        "required": ["petId"],
    }
    pet = by_name(reading, "getPetById").output_schema
    assert pet is not None and sorted(pet["properties"]) == ["category", "id", "name", "photoUrls", "status", "tags"]
    assert pet["properties"]["tags"]["items"]["properties"]["name"] == {"type": "string"}
    assert by_name(reading, "addPet").input_schema["required"] == ["name", "photoUrls"]
    assert sorted(by_name(reading, "deletePet").input_schema["properties"]) == ["api_key", "petId"]
    assert by_name(reading, "deletePet").output_schema is None
    assert by_name(reading, "findPetsByStatus").input_schema["properties"]["status"]["enum"] == ["available", "pending", "sold"]
    # an output schema is kept whatever it uses: the simulator generates from it and checks nothing
    assert by_name(reading, "getInventory").output_schema == {
        "type": "object", "additionalProperties": {"type": "integer", "format": "int32"}}
    assert own.summary(reading).splitlines()[0] == (
        "16 tools: 8 read, 8 write, 0 not known (treated as write), 3 refused (one line each below)")
