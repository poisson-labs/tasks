"""Poisson Tasks on a user's own tools: the readers and the normal form.

A user brings the tool definitions they already have, as an OpenAI tools file (Chat Completions
or Responses shape), an MCP `tools/list` result, or an OpenAPI 3.0 or 3.1 document, and this
package reads them into one normal form, refusing in one line each what it cannot handle.  It
never calls a user's endpoint or tool: `list_mcp_tools` starts a user's MCP server only to list
its tools, with their consent, and stops it.

What a reading does, in order, for every tool the file lists: the name is renamed once by
`safe_name` and the original kept as the title when that changed; a name that is empty, not
text, or already taken by an earlier usable tool is refused; what the reader itself found wrong
(a built-in OpenAI tool type, a request body that is a file or no object, two OpenAPI names that
would merge into one) is refused; every `$ref` in the argument schema is inlined and the schema
must be a JSON object schema obeying spec §3's rules; the output schema is inlined and otherwise
kept as written.  The usable tools must then be 2 to 256 and one of them must be a possible
target, or the file is refused as a whole with the per-tool refusals attached.  The set's digest
is SHA-256 over the file's bytes.

Importing this package imports no `verifiers`, no `mcp` and none of the generator; the MCP
client is imported inside `list_mcp_tools`, and the YAML parser inside the reader when a file is
not JSON.  `tests/test_o1_*.py` pin what each name does.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from dataclasses import replace

from poisson_tasks.own import _readers
from poisson_tasks.own._schema import (
    SchemaProblem,
    check_argument_schema,
    describe,
    inline,
    is_free_text,
    is_object_schema,
    without_definitions,
)
from poisson_tasks.own._server import list_mcp_tools
from poisson_tasks.own._types import (
    EFFECTS,
    ERROR_KINDS,
    FORMATS,
    REFUSAL_KINDS,
    OwnTool,
    OwnToolsError,
    OwnToolSet,
    RawTool,
    Reading,
    Refusal,
)

__all__ = [
    "EFFECTS",
    "ERROR_KINDS",
    "FORMATS",
    "REFUSAL_KINDS",
    "OwnTool",
    "OwnToolSet",
    "OwnToolsError",
    "Reading",
    "Refusal",
    "apply_effects",
    "can_target",
    "is_write",
    "list_mcp_tools",
    "read_tools",
    "safe_name",
    "summary",
]

# A legal tool name (the providers' rule, spec §3): 1 to 64 of these characters.
_ILLEGAL = re.compile(r"[^A-Za-z0-9_-]")
_MAX_NAME = 64
_KEPT_OF_LONG_NAME = 55
_HEX_OF_LONG_NAME = 8
# A set needs this many usable tools, and holds at most that many (spec §3).
_FEWEST_TOOLS = 2
_MOST_TOOLS = 256
_FORMAT_WORDS = {
    "openai": "an OpenAI tools file",
    "mcp": "an MCP tool list",
    "openapi": "an OpenAPI document",
}
_READERS = {
    "openai": _readers.read_openai,
    "mcp": _readers.read_mcp,
    "openapi": _readers.read_openapi,
}


def read_tools(data: bytes, *, format: str = "auto", name: str = "own-tools") -> Reading:
    """Read a tool file's bytes into the normal form.

    `format` is `auto` (decide by shape) or one of `FORMATS`, which must then match the
    file's shape; `name` is the set's name, the caller's.  A file of no shape, a format word
    that is not one, and a set outside spec §3's limits raise `OwnToolsError`."""
    if format != "auto" and format not in FORMATS:
        raise OwnToolsError(
            f"the format {format!r} is not one Tasks reads: auto, openai, mcp or openapi", "format"
        )
    doc = _readers.parse(data)
    detected = _readers.detect(doc)
    if detected is None:
        raise _readers.no_shape_error()
    if format != "auto" and format != detected:
        raise OwnToolsError(
            f"the file is {_FORMAT_WORDS[detected]}, not {_FORMAT_WORDS[format]}; read it with"
            f" format auto or {detected}",
            "format",
        )
    tools: list[OwnTool] = []
    refused: list[Refusal] = []
    taken: set[str] = set()
    for raw in _READERS[detected](doc):
        result = _normalise(raw, taken)
        if isinstance(result, Refusal):
            refused.append(result)
        else:
            taken.add(result.name)
            tools.append(result)
    if len(tools) < _FEWEST_TOOLS:
        raise OwnToolsError(
            f"{len(tools)} usable tool{'' if len(tools) == 1 else 's'} after {len(refused)}"
            f" refused; a set needs at least {_FEWEST_TOOLS}",
            "too_few",
            refused,
        )
    if len(tools) > _MOST_TOOLS:
        raise OwnToolsError(
            f"{len(tools)} usable tools; a set holds at most {_MOST_TOOLS}", "too_many", refused
        )
    if not any(can_target(tool) for tool in tools):
        raise OwnToolsError(
            "no usable tool can be a task's target: each takes no arguments, or only free text"
            " (strings with no format, enum or bound), so no exact call can be checked",
            "no_target",
            refused,
        )
    digest = hashlib.sha256(data).hexdigest()
    return Reading(OwnToolSet(name, tuple(tools), detected, digest), tuple(refused))


def _normalise(raw: RawTool, taken: set[str]) -> OwnTool | Refusal:
    """One raw tool through the rules of spec §3, in the order the module docstring gives."""
    if not isinstance(raw.name, str):
        return Refusal("" if raw.name is None else str(raw.name), "name", "its name is not text")
    renamed = safe_name(raw.name)
    if not renamed:
        return Refusal(raw.name, "name", "its name is empty")
    title = raw.name if renamed != raw.name else raw.title
    if renamed in taken:
        reason = "its name repeats an earlier tool's"
        if renamed != raw.name:
            reason += f" once renamed to {renamed}"
        return Refusal(raw.name, "duplicate", reason)
    if raw.problem is not None:
        return Refusal(raw.name, raw.problem[0], raw.problem[1])
    try:
        input_schema = without_definitions(
            inline(raw.input_schema, raw.input_schema if raw.root is None else raw.root)
        )
        if not is_object_schema(input_schema):
            return Refusal(
                raw.name,
                "not_object",
                f"its argument schema is not a JSON object schema but {describe(input_schema)}",
            )
        check_argument_schema(input_schema)
        output_schema = None
        if raw.output_schema is not None:
            output_schema = without_definitions(
                inline(raw.output_schema, raw.output_schema if raw.root is None else raw.root)
            )
    except SchemaProblem as problem:
        return Refusal(raw.name, problem.kind, problem.reason)
    return OwnTool(renamed, raw.description, input_schema, output_schema, raw.effect, title)


def safe_name(original: str) -> str:
    """The one fixed renaming of a tool's name (spec §3): characters outside letters, digits,
    `_` and `-` become `_`; a name then over 64 characters is cut to its first 55, `_`, and
    the first 8 hex digits of the SHA-256 of the original name.  A legal name is unchanged."""
    renamed = _ILLEGAL.sub("_", original)
    if len(renamed) > _MAX_NAME:
        digest = hashlib.sha256(original.encode("utf-8")).hexdigest()
        renamed = renamed[:_KEPT_OF_LONG_NAME] + "_" + digest[:_HEX_OF_LONG_NAME]
    return renamed


def can_target(tool: OwnTool) -> bool:
    """Whether a task may require a call to this tool with particular values: it has at least
    one argument that is not free text (spec §3).  Only the tool's own, top-level, arguments
    count; a tool with none has nothing to check."""
    properties = tool.input_schema.get("properties")
    if not isinstance(properties, dict):
        return False
    return any(not is_free_text(schema) for schema in properties.values())


def is_write(tool: OwnTool) -> bool:
    """Whether a stray call to this tool counts as a side effect: a write, or an effect that
    is not known (spec §2.3's safe reading)."""
    return tool.effect != "read"


def apply_effects(
    toolset: OwnToolSet, *, read: Sequence[str] = (), write: Sequence[str] = ()
) -> OwnToolSet:
    """The set with the effects the user declared in `tasks.toml`: the named tools (by their
    names in the set) read or write, the rest as they were.  A name the set does not hold, or
    one in both lists, is refused (kind `effects`)."""
    names = {tool.name for tool in toolset.tools}
    for declared in (*read, *write):
        if declared not in names:
            raise OwnToolsError(
                f"{declared!r} is not a tool of the set {toolset.name}; the names are those the"
                " summary shows",
                "effects",
            )
    both = sorted(set(read) & set(write))
    if both:
        raise OwnToolsError(
            f"{both[0]!r} is declared both read and write; a tool is one or the other", "effects"
        )
    effects = {**{name: "read" for name in read}, **{name: "write" for name in write}}
    tools = tuple(
        replace(tool, effect=effects[tool.name]) if tool.name in effects else tool
        for tool in toolset.tools
    )
    return replace(toolset, tools=tools)


def summary(reading: Reading) -> str:
    """The summary `init` and `doctor` print: spec §8.1's counts on the first line (the first
    number is the usable tools), then each refusal in one line, then the file's digest, then
    every renamed tool with its original name."""
    tools = reading.toolset.tools
    counts = {effect: sum(tool.effect == effect for tool in tools) for effect in EFFECTS}
    refused = len(reading.refused)
    first = (
        f"{len(tools)} tools: {counts['read']} read, {counts['write']} write,"
        f" {counts['unknown']} not known (treated as write), {refused} refused"
    )
    lines = [first + (" (one line each below)" if refused else "")]
    lines.extend(refusal.line for refusal in reading.refused)
    lines.append(
        f"file: {_FORMAT_WORDS[reading.toolset.source_format]},"
        f" sha256 {reading.toolset.file_digest}"
    )
    for tool in tools:
        if (
            tool.title is not None
            and tool.title != tool.name
            and safe_name(tool.title) == tool.name
        ):
            lines.append(f"renamed: {tool.title} is offered as {tool.name}")
    return "\n".join(lines)
