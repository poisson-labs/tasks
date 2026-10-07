"""The three readers and the shape detection behind `format = "auto"`.

Each reader takes the parsed file and gives `RawTool`s in file order; the normal form (the
renaming, the duplicate rule, the schema rules, the set-level rules) is applied afterwards in
`poisson_tasks.own`.  A file that matches none of the three shapes, and an MCP tools list
holding an item that is no mapping, are refused here as a whole (kind `shape`).
"""

from __future__ import annotations

import importlib
import json
import re
from typing import Any

from poisson_tasks.own._schema import (
    SchemaProblem,
    describe,
    inline,
    is_object_schema,
    resolve_chain,
)
from poisson_tasks.own._types import OwnToolsError, RawTool

# The one empty argument object this package writes (spec §2.1: "a tool with none gets an
# empty object").
EMPTY_OBJECT: dict[str, Any] = {"type": "object", "properties": {}}
SHAPES = (
    "an OpenAI tools list (Chat Completions or Responses functions, bare or under a `tools` key)",
    "an MCP tools/list result (bare, in its JSON-RPC envelope, or a list of pages)",
    "an OpenAPI 3.0 or 3.1 document (JSON or YAML)",
)
# What spec §2.1's last column says of each HTTP method; methods it does not name are unknown.
METHOD_EFFECTS = {
    "get": "read",
    "head": "read",
    "post": "write",
    "put": "write",
    "patch": "write",
    "delete": "write",
    "options": "unknown",
    "trace": "unknown",
}
# Header parameters OpenAPI says to ignore in a description (compared without case).
IGNORED_HEADERS = frozenset({"accept", "content-type", "authorization"})
PARAMETER_PLACES = ("path", "query", "header")
RESPONSE_2XX = re.compile(r"2(\d\d|XX)", re.IGNORECASE)


# --------------------------------------------------------------------------
# parsing and the shape
# --------------------------------------------------------------------------


def parse(data: bytes) -> Any:
    """The file's content: JSON first, YAML second (so any format may come as YAML)."""
    try:
        return json.loads(data)
    except ValueError:
        pass
    yaml: Any = importlib.import_module("yaml")
    try:
        return yaml.safe_load(data)
    except Exception:
        raise OwnToolsError(
            "the file is neither JSON nor YAML; Tasks reads " + ", ".join(SHAPES), "shape"
        ) from None


def _is_mcp_item(item: Any) -> bool:
    return isinstance(item, dict) and "inputSchema" in item


def _mcp_page_tools(page: Any) -> list[Any] | None:
    """A page's tools list when `page` has the MCP shape (a `tools` list, bare or under
    `result`, with at least one item carrying `inputSchema`), else `None`."""
    if not isinstance(page, dict):
        return None
    tools = page.get("tools")
    if tools is None and isinstance(page.get("result"), dict):
        tools = page["result"].get("tools")
    if isinstance(tools, list) and any(_is_mcp_item(item) for item in tools):
        return tools
    return None


def _openai_items(items: Any) -> bool:
    return isinstance(items, list) and all(isinstance(t, dict) and "type" in t for t in items)


def detect(doc: Any) -> str | None:
    """Which of the three shapes `doc` has, or `None`: a mapping with an `openapi` key of
    version 3.0 or 3.1 is OpenAPI; a `tools` list whose items carry `inputSchema`, bare or
    under `result`, or a list of such pages, is MCP; a list, or a `tools` list, of mappings
    with a `type` key is OpenAI."""
    if isinstance(doc, dict):
        version = doc.get("openapi")
        if isinstance(version, str) and version.startswith(("3.0.", "3.1.")):
            return "openapi"
        if _mcp_page_tools(doc) is not None:
            return "mcp"
        if _openai_items(doc.get("tools")):
            return "openai"
        return None
    if isinstance(doc, list):
        if doc and all(_mcp_page_tools(page) is not None for page in doc):
            return "mcp"
        if _openai_items(doc):
            return "openai"
    return None


def no_shape_error() -> OwnToolsError:
    return OwnToolsError(
        "the file matches none of the three shapes Tasks reads: " + "; ".join(SHAPES), "shape"
    )


# --------------------------------------------------------------------------
# OpenAI
# --------------------------------------------------------------------------


def read_openai(doc: Any) -> list[RawTool]:
    items = doc if isinstance(doc, list) else doc["tools"]
    out: list[RawTool] = []
    for item in items:
        kind = item["type"]
        if kind != "function":
            out.append(
                RawTool(
                    str(kind),
                    "",
                    None,
                    None,
                    "unknown",
                    problem=(
                        "builtin",
                        f"{kind} is one of the Responses API's built-in tools, not a"
                        " function Tasks can simulate",
                    ),
                )
            )
            continue
        inner = item["function"] if isinstance(item.get("function"), dict) else item
        description = inner.get("description")
        parameters = inner.get("parameters")
        out.append(
            RawTool(
                inner.get("name", ""),
                description if isinstance(description, str) else "",
                EMPTY_OBJECT if parameters is None else parameters,
                None,
                "unknown",
            )
        )
    return out


# --------------------------------------------------------------------------
# MCP
# --------------------------------------------------------------------------


def read_mcp(doc: Any) -> list[RawTool]:
    pages = doc if isinstance(doc, list) else [doc]
    out: list[RawTool] = []
    for page in pages:
        for item in _mcp_page_tools(page) or []:
            if not isinstance(item, dict):
                raise OwnToolsError(
                    "an item of the MCP tools list is not a mapping, so the file is not a"
                    " tools/list result",
                    "shape",
                )
            description = item.get("description")
            title = item.get("title")
            problem = None
            if "inputSchema" not in item:
                problem = ("not_object", "it has no inputSchema, so its arguments are not known")
            if "annotations" in item and item["annotations"] is not None:
                annotations = item["annotations"]
                read_only = (
                    isinstance(annotations, dict) and annotations.get("readOnlyHint") is True
                )
                effect = "read" if read_only else "write"
            else:
                effect = "unknown"
            out.append(
                RawTool(
                    item.get("name", ""),
                    description if isinstance(description, str) else "",
                    item.get("inputSchema"),
                    item.get("outputSchema"),
                    effect,
                    title=title if isinstance(title, str) else None,
                    problem=problem,
                )
            )
    return out


# --------------------------------------------------------------------------
# OpenAPI
# --------------------------------------------------------------------------


def _media_type(key: Any) -> str:
    return str(key).split(";", 1)[0].strip().lower()


def _is_json_media(media: str) -> bool:
    return media == "application/json" or media.endswith("/json") or media.endswith("+json")


def _is_file_media(media: str) -> bool:
    return (
        media == "application/octet-stream"
        or media.startswith("multipart/")
        or media == "text/event-stream"
    )


def read_openapi(doc: Any) -> list[RawTool]:
    paths = doc.get("paths")
    out: list[RawTool] = []
    if not isinstance(paths, dict):
        return out
    for path, item in paths.items():
        try:
            item = resolve_chain(item, doc)
        except SchemaProblem as problem:
            out.append(
                RawTool(
                    str(path), "", None, None, "unknown", problem=(problem.kind, problem.reason)
                )
            )
            continue
        if not isinstance(item, dict):
            continue
        path_parameters = item.get("parameters")
        for method, operation in item.items():
            if method in METHOD_EFFECTS and isinstance(operation, dict):
                out.append(
                    _operation(
                        doc,
                        str(path),
                        method,
                        operation,
                        path_parameters if isinstance(path_parameters, list) else [],
                    )
                )
    return out


def _operation(
    doc: Any, path: str, method: str, operation: dict[str, Any], path_parameters: list[Any]
) -> RawTool:
    operation_id = operation.get("operationId")
    name = operation_id if isinstance(operation_id, str) and operation_id else f"{method}_{path}"
    summary = operation.get("summary")
    description = operation.get("description")
    if isinstance(summary, str) and summary:
        words = summary
    elif isinstance(description, str):
        words = description
    else:
        words = ""
    effect = METHOD_EFFECTS[method]
    try:
        own_parameters = operation.get("parameters")
        parameters = _parameters(
            doc, path_parameters, own_parameters if isinstance(own_parameters, list) else []
        )
        body = _body(doc, operation.get("requestBody"))
        input_schema = _compose(parameters, body)
        output_schema = _output(doc, operation.get("responses"))
    except SchemaProblem as problem:
        return RawTool(name, words, None, None, effect, problem=(problem.kind, problem.reason))
    return RawTool(name, words, input_schema, output_schema, effect)


def _parameters(doc: Any, path_level: list[Any], own: list[Any]) -> list[tuple[str, Any, bool]]:
    """The operation's parameters as `(name, schema, required)`, path-level ones first in
    their order, an operation's parameter of the same name and place replacing one in place;
    cookie parameters and the ignored headers left out; the parameter's description put into
    its schema when the schema has none."""
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for group in (path_level, own):
        for raw in group:
            parameter = resolve_chain(raw, doc)
            if (
                not isinstance(parameter, dict)
                or not isinstance(parameter.get("name"), str)
                or not isinstance(parameter.get("in"), str)
            ):
                raise SchemaProblem("merge", "one of its parameters has no name or no place (in)")
            merged[(parameter["name"], parameter["in"])] = parameter
    out: list[tuple[str, Any, bool]] = []
    for (name, place), parameter in merged.items():
        if place not in PARAMETER_PLACES:
            continue
        if place == "header" and name.lower() in IGNORED_HEADERS:
            continue
        schema = parameter.get("schema")
        if schema is None and isinstance(parameter.get("content"), dict):
            for media in parameter["content"].values():
                schema = media.get("schema") if isinstance(media, dict) else None
                break
        schema = inline({} if schema is None else schema, doc)
        description = parameter.get("description")
        if (
            isinstance(schema, dict)
            and "description" not in schema
            and isinstance(description, str)
        ):
            schema = {**schema, "description": description}
        out.append((name, schema, parameter.get("required") is True or place == "path"))
    return out


def _body(doc: Any, request_body: Any) -> Any:
    """The request body's object schema, inlined: from its JSON content first, else from the
    first media type that is not a file's or a stream's and holds an object schema.  A body
    offering only files or streams is refused (kind `binary`); one whose schema is no object
    is refused (kind `not_object`)."""
    if request_body is None:
        return None
    request_body = resolve_chain(request_body, doc)
    if not isinstance(request_body, dict) or not isinstance(request_body.get("content"), dict):
        return None
    content = [(_media_type(key), value) for key, value in request_body["content"].items()]
    if not content:
        return None
    for media, value in content:
        if _is_json_media(media):
            schema = inline(value.get("schema") if isinstance(value, dict) else None, doc)
            if not is_object_schema(schema):
                raise SchemaProblem(
                    "not_object",
                    f"its request body ({media}) is not a JSON object schema but"
                    f" {describe(schema)}",
                )
            return schema
    for media, value in content:
        if _is_file_media(media):
            continue
        schema = inline(value.get("schema") if isinstance(value, dict) else None, doc)
        if is_object_schema(schema):
            return schema
    files = [media for media, _ in content if _is_file_media(media)]
    if files:
        raise SchemaProblem(
            "binary", f"it takes a file or a stream (its request body is {files[0]})"
        )
    raise SchemaProblem(
        "not_object",
        f"its request body ({content[0][0]}) is not a JSON object schema and no other media"
        " type of it holds one",
    )


def _compose(
    parameters: list[tuple[str, Any, bool]], body: dict[str, Any] | None
) -> dict[str, Any]:
    """The one argument object: every kept parameter, then the body's fields; `required`
    lists the required parameters in document order, then the body's list, and is left out
    when empty.  A name that would appear twice is refused (kind `merge`)."""
    properties: dict[str, Any] = {}
    required: list[str] = []
    for name, schema, is_required in parameters:
        if name in properties:
            raise SchemaProblem(
                "merge",
                f"the name {name} is used by two of its parameters in different places,"
                " so the merged object would hold it twice",
            )
        properties[name] = schema
        if is_required:
            required.append(name)
    if body is not None:
        fields = body.get("properties")
        for name, schema in fields.items() if isinstance(fields, dict) else ():
            if name in properties:
                raise SchemaProblem(
                    "merge",
                    f"the name {name} is both a parameter and a field of its request body,"
                    " so the merged object would hold it twice",
                )
            properties[name] = schema
        body_required = body.get("required")
        if isinstance(body_required, list):
            required.extend(str(name) for name in body_required)
    merged: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        merged["required"] = required
    if body is not None and "additionalProperties" in body:
        merged["additionalProperties"] = body["additionalProperties"]
    return merged


def _output(doc: Any, responses: Any) -> Any:
    """The schema of the first response in document order whose code is 2xx (or 2XX) and has
    JSON content with a schema, inlined; `None` with none."""
    if not isinstance(responses, dict):
        return None
    for code, response in responses.items():
        if not RESPONSE_2XX.fullmatch(str(code)):
            continue
        response = resolve_chain(response, doc)
        if not isinstance(response, dict) or not isinstance(response.get("content"), dict):
            continue
        for key, value in response["content"].items():
            if _is_json_media(_media_type(key)) and isinstance(value, dict) and "schema" in value:
                return inline(value["schema"], doc)
    return None
