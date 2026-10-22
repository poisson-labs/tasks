"""Helpers the `tests/test_o1_*.py` files share: the fixture folder, builders for small tool files
in each of the three formats, and the one partner tool that keeps a set above the set-level
refusals.

Every builder returns the file's bytes, since `own.read_tools` reads bytes and digests them.
Test files import this as `tests.o1_support`, the way `pyproject.toml`'s `pythonpath` lets them.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from poisson_tasks import own

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures" / "o1"
FAKE_MCP_SERVER = FIXTURES / "fake_mcp_server.py"

# A write tool with one checkable argument: beside a tool under test it keeps the set at two
# usable tools with a target, so a test reads only the clause it is about.
PARTNER_PARAMS: dict[str, Any] = {
    "type": "object",
    "properties": {"n": {"type": "integer", "description": "A count."}},
    "required": ["n"],
}


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def function(
    name: str,
    parameters: Any = None,
    description: str | None = "Does one thing.",
) -> dict[str, Any]:
    """One OpenAI Chat Completions tool; `parameters=None` leaves the key out."""
    inner: dict[str, Any] = {"name": name}
    if description is not None:
        inner["description"] = description
    if parameters is not None:
        inner["parameters"] = parameters
    return {"type": "function", "function": inner}


def partner(name: str = "partner_write") -> dict[str, Any]:
    return function(name, PARTNER_PARAMS, "Writes one count.")


def openai_file(*tools: dict[str, Any]) -> bytes:
    """A Chat Completions tools list as a file."""
    return json.dumps(list(tools)).encode("utf-8")


def mcp_tool(
    name: str,
    input_schema: Any = None,
    *,
    description: str = "Does one thing.",
    annotations: Any = None,
    output_schema: Any = None,
    title: str | None = None,
) -> dict[str, Any]:
    tool: dict[str, Any] = {"name": name, "description": description}
    if title is not None:
        tool["title"] = title
    tool["inputSchema"] = {"type": "object", "properties": {}} if input_schema is None else input_schema
    if annotations is not None:
        tool["annotations"] = annotations
    if output_schema is not None:
        tool["outputSchema"] = output_schema
    return tool


def mcp_partner(name: str = "partner_write") -> dict[str, Any]:
    return mcp_tool(name, PARTNER_PARAMS, annotations={"readOnlyHint": False})


def mcp_file(*tools: dict[str, Any]) -> bytes:
    """A bare `tools/list` result as a file."""
    return json.dumps({"tools": list(tools)}).encode("utf-8")


def operation(
    operation_id: str | None,
    *,
    summary: str | None = "Does one thing.",
    description: str | None = None,
    parameters: list[dict[str, Any]] | None = None,
    body: Any = None,
    body_media: str = "application/json",
    body_required: bool = True,
    responses: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One OpenAPI operation object."""
    op: dict[str, Any] = {}
    if operation_id is not None:
        op["operationId"] = operation_id
    if summary is not None:
        op["summary"] = summary
    if description is not None:
        op["description"] = description
    if parameters is not None:
        op["parameters"] = parameters
    if body is not None:
        op["requestBody"] = {"required": body_required, "content": {body_media: {"schema": body}}}
    op["responses"] = {"200": {"description": "OK."}} if responses is None else responses
    return op


def param(
    name: str,
    where: str,
    schema: Any = None,
    *,
    required: bool | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {"name": name, "in": where}
    if required is not None:
        out["required"] = required
    elif where == "path":
        out["required"] = True
    if description is not None:
        out["description"] = description
    out["schema"] = {"type": "string"} if schema is None else schema
    return out


def openapi_file(
    paths: dict[str, dict[str, Any]],
    *,
    components: dict[str, Any] | None = None,
    version: str = "3.0.3",
    top: dict[str, Any] | None = None,
) -> bytes:
    """An OpenAPI document as a JSON file; `top` adds or replaces top-level keys."""
    doc: dict[str, Any] = {
        "openapi": version,
        "info": {"title": "Test", "version": "1"},
        "paths": paths,
    }
    if components is not None:
        doc["components"] = components
    if top:
        doc.update(top)
    return json.dumps(doc).encode("utf-8")


def openapi_partner_path() -> dict[str, dict[str, Any]]:
    """Two paths holding partners as POSTs with one integer in the body, so a set keeps two
    usable tools when the operation under test is refused."""
    body = {"type": "object", "properties": PARTNER_PARAMS["properties"], "required": ["n"]}
    return {
        "/partner": {"post": operation("partner_write", body=body)},
        "/partner-2": {"post": operation("partner_write_2", body=body)},
    }


def read(data: bytes, **kwargs: Any) -> own.Reading:
    return own.read_tools(data, **kwargs)


def names(reading: own.Reading) -> list[str]:
    return [tool.name for tool in reading.toolset.tools]


def refused(reading: own.Reading) -> list[tuple[str, str]]:
    return [(refusal.name, refusal.kind) for refusal in reading.refused]


def by_name(reading: own.Reading, name: str) -> own.OwnTool:
    return next(tool for tool in reading.toolset.tools if tool.name == name)
