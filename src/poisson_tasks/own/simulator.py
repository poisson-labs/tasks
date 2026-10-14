"""The simulator: what a user's tools answer in a Tasks episode, shaped by their schemas, and the
state a task's calls move (spec §4).

`respond` is the object an accepted call answers with: for a tool with an output schema an object
that conforms to it, every value drawn from the file's digest, the task's seed and split, the
tool's name and the call's arguments as content, and from nothing else, so the same call in one
episode always gets the same answer and the arm never enters it; without an output schema
`{"ok": true, "id": ...}`.  `success` and `error` render an answer in the format's idiom:
Tasks' own `{"error": {...}}` object for OpenAI tools, `isError` with the message as text for
MCP, `{"status": ..., "detail": ...}` for OpenAPI; an MCP tool with an output schema answers in
`structuredContent` with its text beside.  `start`, `step` and `replay` are the state machine
over a generated task (`generator.OwnBundle`): a planned fault answers `unavailable`, arguments
that break the schema `invalid_arguments`, a named read for a key the task does not hold
`not_found`, an expected step made before its prerequisite `not_ready`; otherwise the call is
accepted, a read changes nothing, the expected write moves its flag, and any other accepted
write (the expected one made again included) is a side effect.  Only calls that reach the
server go through `step`; `replay` passes over what the harness answers itself.

Pure: no clock but `CLOCK` (dates are arithmetic on it, never read from the machine), no
randomness but the keyed draw, no network.  Output schema keywords the draw cannot honour
(`OUTPUT_PASSED_OVER`) are taken out before a value is drawn; `anyOf` takes its first branch
and `oneOf` the first branch whose value no other branch accepts.  `tests/test_o2_simulator.py`
pins all of this.
"""

from __future__ import annotations

import hashlib as _hashlib
import json as _json
import math as _math
import re as _re
import uuid as _uuid
from collections.abc import Mapping as _Mapping
from collections.abc import Sequence as _Sequence
from dataclasses import dataclass as _dataclass
from typing import Any as _Any

from poisson_tasks.own._types import OwnTool as _OwnTool

__all__ = [
    "CLOCK",
    "ERROR_CODES",
    "OUTPUT_PASSED_OVER",
    "Answer",
    "State",
    "respond",
    "success",
    "error",
    "start",
    "step",
    "replay",
    "conforms",
    "canonical",
    "draw_value",
    "same",
    "reaches_the_server",
]

CLOCK = "2026-01-01T00:00:00Z"
ERROR_CODES = ("not_found", "invalid_arguments", "not_ready", "unavailable")
OUTPUT_PASSED_OVER: tuple[str, ...] = (
    "pattern", "not", "if", "then", "else", "allOf", "contains", "minContains", "maxContains",
    "propertyNames", "dependentSchemas", "dependentRequired", "dependencies",
    "unevaluatedProperties", "unevaluatedItems", "patternProperties", "minProperties",
    "maxProperties", "multipleOf", "uniqueItems",
)

# The OpenAPI status of each error code (ruled 2026-10-13, yes/no 4).
_STATUS = {"not_found": 404, "invalid_arguments": 422, "not_ready": 409, "unavailable": 503}
_FORMATS = ("openai", "mcp", "openapi")
_DRAW_KEY = b"poisson-tasks/own/simulator/1"
_LETTERS = "abcdefghijklmnopqrstuvwxyz"
_ALNUM = "abcdefghijklmnopqrstuvwxyz0123456789"
# Default spans where a schema gives none.
_DEFAULT_STRING = (4, 12)
_DEFAULT_INT_SPAN = 1000
_DEFAULT_NUMBER_SPAN = 100.0
_NUMBER_GRID = 199
_DEFAULT_ITEMS = 3
_CLOCK_YEAR = 2026
_MONTH_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_EMAIL = _re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_DATE_TIME = _re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$")
_DATE = _re.compile(r"^\d{4}-\d{2}-\d{2}$")
_OK = "ok"
_ID = "id"
_NONE_PART = "none"
# Schema keys whose children are keyed by a name, not a keyword.
_NAMED_MAPS = ("properties", "$defs", "definitions")


@_dataclass(frozen=True)
class Answer:
    """One answer: the tool message's text, the MCP result's `structuredContent` or `None`, the
    MCP result's `isError`, and the error code when the answer is an error."""

    text: str
    structured: _Mapping[str, _Any] | None
    is_error: bool
    code: str | None = None


@_dataclass(frozen=True)
class State:
    """The store a task's calls move: one flag per write the task expects, one per read that
    serves a value, the accepted writes it did not expect, every call the server received, and
    how many times each tool was called (the fault plan's counter)."""

    done: tuple[bool, ...]
    side_effects: tuple[_Any, ...]
    calls: int
    served: tuple[bool, ...] = ()
    counts: tuple[tuple[str, int], ...] = ()


# ---------------------------------------------------------------------------
# the keyed draw
# ---------------------------------------------------------------------------


def canonical(value: _Any) -> str:
    """A value as content: compact JSON with sorted keys, so two spellings of one call draw
    the same answer."""
    return _json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _bits(key: bytes, salt: str) -> int:
    digest = _hashlib.blake2b(key + b"\x1f" + salt.encode("utf-8"), key=_DRAW_KEY,
                              digest_size=32).digest()
    return int.from_bytes(digest, "big")


def _choice(key: bytes, salt: str, count: int) -> int:
    """An index below `count`, from the draw at `salt`."""
    if count <= 0:
        raise ValueError("a choice needs at least one option")
    return _bits(key, salt) % count


def _key_of(digest: str, seed: int, split: str, tool: str, arguments: _Any) -> bytes:
    return f"{digest}\x1f{seed}\x1f{split}\x1f{tool}\x1f{canonical(arguments)}".encode()


# ---------------------------------------------------------------------------
# values from schemas
# ---------------------------------------------------------------------------


def _strip(schema: _Any) -> _Any:
    """The schema without the keywords the draw passes over, at every level.  The keys of
    `properties` (and of the definition maps) are names, not keywords, and are kept whatever
    they are called."""
    if isinstance(schema, dict):
        out: dict[str, _Any] = {}
        for k, v in schema.items():
            if k in OUTPUT_PASSED_OVER:
                continue
            if k in _NAMED_MAPS and isinstance(v, dict):
                out[k] = {name: _strip(sub) for name, sub in v.items()}
            else:
                out[k] = _strip(v)
        return out
    if isinstance(schema, list):
        return [_strip(v) for v in schema]
    return schema


def _types_of(schema: dict[str, _Any]) -> list[str]:
    kind = schema.get("type")
    if isinstance(kind, list):
        return [str(k) for k in kind]
    if isinstance(kind, str):
        return [kind]
    if isinstance(schema.get("properties"), dict):
        return ["object"]
    if "items" in schema or "prefixItems" in schema:
        return ["array"]
    return []


def _civil(day_of_year: int) -> tuple[int, int]:
    month = 0
    while day_of_year >= _MONTH_DAYS[month]:
        day_of_year -= _MONTH_DAYS[month]
        month += 1
    return month + 1, day_of_year + 1


def _date(key: bytes, salt: str) -> str:
    month, day = _civil(_choice(key, salt + "/day", 365))
    return f"{_CLOCK_YEAR:04d}-{month:02d}-{day:02d}"


def _date_time(key: bytes, salt: str) -> str:
    seconds = _choice(key, salt + "/second", 86400)
    hour, rest = divmod(seconds, 3600)
    minute, second = divmod(rest, 60)
    return f"{_date(key, salt)}T{hour:02d}:{minute:02d}:{second:02d}Z"


def _word(key: bytes, salt: str, length: int, alphabet: str = _LETTERS) -> str:
    return "".join(alphabet[_choice(key, f"{salt}/{index}", len(alphabet))]
                   for index in range(length))


def _length(schema: dict[str, _Any], key: bytes, salt: str) -> int:
    low = schema.get("minLength")
    high = schema.get("maxLength")
    low = int(low) if isinstance(low, int | float) and not isinstance(low, bool) else None
    high = int(high) if isinstance(high, int | float) and not isinstance(high, bool) else None
    if low is None and high is None:
        low, high = _DEFAULT_STRING
    elif low is None:
        low, high = 0, min(int(high), _DEFAULT_STRING[1])  # type: ignore[arg-type]
    elif high is None:
        high = low + _DEFAULT_STRING[1] - _DEFAULT_STRING[0]
    high = max(high, low)
    return low + _choice(key, salt + "/length", high - low + 1)


def _string(schema: dict[str, _Any], key: bytes, salt: str) -> str:
    fmt = schema.get("format")
    if fmt == "uuid":
        return str(_uuid.UUID(bytes=_bits(key, salt + "/uuid").to_bytes(32, "big")[:16],
                              version=4))
    if fmt == "email":
        return f"{_word(key, salt + '/user', 6)}{_choice(key, salt + '/n', 100)}@example.com"
    if fmt == "date-time":
        return _date_time(key, salt)
    if fmt == "date":
        return _date(key, salt)
    return _word(key, salt + "/word", _length(schema, key, salt))


def _bounds(schema: dict[str, _Any], integer: bool) -> tuple[float | None, float | None,
                                                           bool, bool]:
    """(low, high, low exclusive, high exclusive), reading 2020-12 and OpenAPI 3.0 alike."""
    low = schema.get("minimum")
    high = schema.get("maximum")
    low_open = False
    high_open = False
    ex_low = schema.get("exclusiveMinimum")
    ex_high = schema.get("exclusiveMaximum")
    if isinstance(ex_low, bool):
        low_open = ex_low
    elif isinstance(ex_low, int | float):
        if low is None or ex_low >= low:
            low, low_open = ex_low, True
    if isinstance(ex_high, bool):
        high_open = ex_high
    elif isinstance(ex_high, int | float):
        if high is None or ex_high <= high:
            high, high_open = ex_high, True
    low_value = float(low) if isinstance(low, int | float) and not isinstance(low, bool) else None
    high_value = (float(high) if isinstance(high, int | float) and not isinstance(high, bool)
                  else None)
    return low_value, high_value, low_open, high_open


def _number(schema: dict[str, _Any], key: bytes, salt: str, integer: bool) -> int | float:
    low, high, low_open, high_open = _bounds(schema, integer)
    if integer:
        lo = None if low is None else (_math.floor(low) + 1 if low_open else _math.ceil(low))
        hi = None if high is None else (_math.ceil(high) - 1 if high_open else _math.floor(high))
        if lo is None and hi is None:
            lo, hi = 0, _DEFAULT_INT_SPAN
        elif lo is None:
            lo = hi - _DEFAULT_INT_SPAN  # type: ignore[operator]
        elif hi is None:
            hi = lo + _DEFAULT_INT_SPAN
        if hi < lo:  # type: ignore[operator]
            hi = lo
        return int(lo) + _choice(key, salt + "/int", int(hi) - int(lo) + 1)  # type: ignore[arg-type]
    if low is None and high is None:
        bottom, top = 0.0, _DEFAULT_NUMBER_SPAN
    elif low is None:
        assert high is not None
        bottom, top = high - _DEFAULT_NUMBER_SPAN, high
    elif high is None:
        bottom, top = low, low + _DEFAULT_NUMBER_SPAN
    else:
        bottom, top = low, high
    if top < bottom:
        top = bottom
    if top == bottom:
        return float(bottom)
    k = _choice(key, salt + "/num", _NUMBER_GRID)
    value = bottom + (top - bottom) * (k + 1) / (_NUMBER_GRID + 1)
    rounded = round(value, 2)
    inside_low = rounded > bottom if low_open else rounded >= bottom
    inside_high = rounded < top if high_open else rounded <= top
    return rounded if inside_low and inside_high else value


def draw_value(schema: _Any, key: bytes, salt: str = "") -> _Any:
    """A value conforming to `schema` (a 2020-12 or OpenAPI 3.0 schema with the passed-over
    keywords taken out), drawn at `key` and `salt`; `salt` names the value's place."""
    if schema is True or schema is None or not isinstance(schema, dict):
        return _word(key, salt + "/any", 4)
    if "const" in schema:
        return schema["const"]
    if isinstance(schema.get("enum"), list) and schema["enum"]:
        options = schema["enum"]
        return options[_choice(key, salt + "/enum", len(options))]
    if isinstance(schema.get("anyOf"), list) and schema["anyOf"]:
        return draw_value(schema["anyOf"][0], key, salt + "/anyOf")
    if isinstance(schema.get("oneOf"), list) and schema["oneOf"]:
        branches = schema["oneOf"]
        for index, branch in enumerate(branches):
            value = draw_value(branch, key, f"{salt}/oneOf/{index}")
            if not any(conforms(value, other) for j, other in enumerate(branches) if j != index):
                return value
        return draw_value(branches[0], key, salt + "/oneOf/0")
    kinds = _types_of(schema)
    if not kinds:
        return _word(key, salt + "/any", 4)
    kind = kinds[_choice(key, salt + "/type", len(kinds))] if len(kinds) > 1 else kinds[0]
    if kind == "null":
        return None
    if kind == "boolean":
        return bool(_choice(key, salt + "/bool", 2))
    if kind == "integer":
        return _number(schema, key, salt, integer=True)
    if kind == "number":
        return _number(schema, key, salt, integer=False)
    if kind == "string":
        return _string(schema, key, salt)
    if kind == "array":
        return _array(schema, key, salt)
    if kind == "object":
        return _object(schema, key, salt)
    return _word(key, salt + "/any", 4)


def _list_of(schema: dict[str, _Any], name: str) -> list[_Any]:
    found = schema.get(name)
    return list(found) if isinstance(found, list) else []


def _map_of(schema: dict[str, _Any], name: str) -> dict[str, _Any]:
    found = schema.get(name)
    return dict(found) if isinstance(found, dict) else {}


def _array(schema: dict[str, _Any], key: bytes, salt: str) -> list[_Any]:
    prefix = _list_of(schema, "prefixItems")
    low = schema.get("minItems")
    high = schema.get("maxItems")
    low = int(low) if isinstance(low, int | float) and not isinstance(low, bool) else 0
    high = (int(high) if isinstance(high, int | float) and not isinstance(high, bool)
            else max(low, len(prefix)) + _DEFAULT_ITEMS)
    high = max(high, low)
    count = low + _choice(key, salt + "/count", high - low + 1)
    items = schema.get("items")
    out: list[_Any] = []
    for index in range(count):
        if index < len(prefix):
            out.append(draw_value(prefix[index], key, f"{salt}/{index}"))
        elif items is False:
            break
        else:
            out.append(draw_value(items if items is not None else {}, key, f"{salt}/{index}"))
    return out


def _object(schema: dict[str, _Any], key: bytes, salt: str) -> dict[str, _Any]:
    properties = _map_of(schema, "properties")
    required = _list_of(schema, "required")
    out: dict[str, _Any] = {}
    for name in sorted(properties):
        out[name] = draw_value(properties[name], key, f"{salt}/{name}")
    for name in required:
        if name not in out and schema.get("additionalProperties") is not False:
            out[str(name)] = _word(key, f"{salt}/{name}/required", 4)
    return out


def respond(tool: _OwnTool, arguments: _Mapping[str, _Any], *, digest: str, seed: int,
            split: str) -> _Any:
    """The object an accepted call to `tool` answers with, drawn from the call's content."""
    key = _key_of(digest, seed, split, tool.name, arguments)
    if tool.output_schema is None:
        return {_OK: True, _ID: _word(key, "/id", 16, _ALNUM)}
    value: _Any = draw_value(_strip(tool.output_schema), key, "")
    return value


# ---------------------------------------------------------------------------
# the argument check (also the output check `oneOf` needs)
# ---------------------------------------------------------------------------


def same(a: _Any, b: _Any) -> bool:
    """Two values compared as the verdict compares arguments: strings byte for byte, numbers by
    value, booleans and enums exactly (a boolean is never a number), lists and objects member by
    member."""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, int | float) and isinstance(b, int | float):
        return float(a) == float(b)
    if isinstance(a, str) and isinstance(b, str):
        return a == b
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b, strict=True))
    if isinstance(a, dict) and isinstance(b, dict):
        return set(a) == set(b) and all(same(a[k], b[k]) for k in a)
    return a is None and b is None


def _is_type(value: _Any, kind: str) -> bool:
    if kind == "null":
        return value is None
    if kind == "boolean":
        return isinstance(value, bool)
    if kind == "integer":
        return (isinstance(value, int) and not isinstance(value, bool)) or (
            isinstance(value, float) and value.is_integer())
    if kind == "number":
        return isinstance(value, int | float) and not isinstance(value, bool)
    if kind == "string":
        return isinstance(value, str)
    if kind == "array":
        return isinstance(value, list)
    if kind == "object":
        return isinstance(value, dict)
    return True


def _format_holds(value: str, fmt: _Any) -> bool:
    if fmt == "email":
        return bool(_EMAIL.match(value))
    if fmt == "uuid":
        try:
            _uuid.UUID(value)
        except ValueError:
            return False
        return True
    if fmt == "date-time":
        return bool(_DATE_TIME.match(value))
    if fmt == "date":
        return bool(_DATE.match(value))
    return True


def conforms(value: _Any, schema: _Any) -> bool:
    """Whether `value` conforms to `schema`: types (a list of them too), `const`, `enum`, the
    numeric bounds (2020-12's numeric and OpenAPI 3.0's boolean exclusive forms), the length
    bounds, `pattern`, the four formats the draw knows, `properties`, `required`,
    `additionalProperties: false`, `items`, `prefixItems`, the item-count bounds, `anyOf`,
    `oneOf`, `allOf`, `not`, and 3.0's `nullable`.  Keywords it does not know are not checked."""
    if schema is True or schema is None:
        return True
    if schema is False:
        return False
    if not isinstance(schema, dict):
        return True
    if value is None and schema.get("nullable") is True:
        return True
    if "const" in schema and not same(value, schema["const"]):
        return False
    if isinstance(schema.get("enum"), list) and not any(same(value, v) for v in schema["enum"]):
        return False
    kinds = schema.get("type")
    if isinstance(kinds, str):
        if not _is_type(value, kinds):
            return False
    elif isinstance(kinds, list):
        if not any(_is_type(value, str(kind)) for kind in kinds):
            return False
    if isinstance(schema.get("anyOf"), list) and not any(
        conforms(value, branch) for branch in schema["anyOf"]
    ):
        return False
    if isinstance(schema.get("oneOf"), list) and sum(
        1 for branch in schema["oneOf"] if conforms(value, branch)
    ) != 1:
        return False
    if isinstance(schema.get("allOf"), list) and not all(
        conforms(value, branch) for branch in schema["allOf"]
    ):
        return False
    if "not" in schema and conforms(value, schema["not"]):
        return False
    if isinstance(value, bool):
        return True
    if isinstance(value, int | float):
        low, high, low_open, high_open = _bounds(schema, False)
        if low is not None and (value <= low if low_open else value < low):
            return False
        if high is not None and (value >= high if high_open else value > high):
            return False
        return True
    if isinstance(value, str):
        low = schema.get("minLength")
        high = schema.get("maxLength")
        if isinstance(low, int) and len(value) < low:
            return False
        if isinstance(high, int) and len(value) > high:
            return False
        pattern = schema.get("pattern")
        if isinstance(pattern, str):
            try:
                if _re.search(pattern, value) is None:
                    return False
            except _re.error:
                pass
        return _format_holds(value, schema.get("format"))
    if isinstance(value, list):
        low = schema.get("minItems")
        high = schema.get("maxItems")
        if isinstance(low, int) and len(value) < low:
            return False
        if isinstance(high, int) and len(value) > high:
            return False
        prefix = _list_of(schema, "prefixItems")
        items = schema.get("items")
        for index, item in enumerate(value):
            if index < len(prefix):
                if not conforms(item, prefix[index]):
                    return False
            elif items is False:
                return False
            elif items is not None and not conforms(item, items):
                return False
        return True
    if isinstance(value, dict):
        properties = _map_of(schema, "properties")
        required = _list_of(schema, "required")
        if any(name not in value for name in required):
            return False
        for name, item in value.items():
            if name in properties:
                if not conforms(item, properties[name]):
                    return False
            elif schema.get("additionalProperties") is False:
                return False
        return True
    return True


# ---------------------------------------------------------------------------
# the answers in each format's idiom
# ---------------------------------------------------------------------------


def _text(value: _Any) -> str:
    return _json.dumps(value, sort_keys=True, separators=(",", ":"))


def success(source_format: str, tool: _OwnTool, value: _Any) -> Answer:
    """An accepted call's answer in the format's idiom."""
    if source_format not in _FORMATS:
        raise ValueError(f"{source_format!r} is not a format: openai, mcp or openapi")
    structured = None
    if source_format == "mcp" and tool.output_schema is not None and isinstance(value, dict):
        structured = dict(value)
    return Answer(_text(value), structured, False)


def error(source_format: str, code: str, message: str) -> Answer:
    """An error in the format's idiom; `code` is one of `ERROR_CODES`."""
    if source_format not in _FORMATS:
        raise ValueError(f"{source_format!r} is not a format: openai, mcp or openapi")
    if code not in ERROR_CODES:
        raise ValueError(f"{code!r} is not an error code: " + ", ".join(ERROR_CODES))
    if source_format == "mcp":
        return Answer(message, None, True, code)
    if source_format == "openapi":
        return Answer(_text({"status": _STATUS[code], "detail": message}), None, False, code)
    return Answer(_text({"error": {"code": code, "message": message}}), None, False, code)


# ---------------------------------------------------------------------------
# the state machine over a generated task
# ---------------------------------------------------------------------------


def reaches_the_server(name: _Any, arguments: _Any, block: _Mapping[str, _Any]) -> bool:
    """Whether the harness forwards a call to the tool server: the name one the block shows and
    the arguments a JSON object.  Any other call the harness answers itself."""
    return isinstance(name, str) and name in block and isinstance(arguments, dict)


def _place(value: _Any, path: str, placed: _Any, schema: _Any, key: bytes) -> _Any:
    """`value` with `placed` at `path` (`a.b[].c`: `[]` marks an array, whose first element
    takes it, made from the schema when the draw made none)."""
    parts = path.split(".")
    node = value
    node_schema = schema
    for index, part in enumerate(parts):
        last = index == len(parts) - 1
        name = part.removesuffix("[]")
        if not isinstance(node, dict):
            raise ValueError(f"the path {path} does not fit the answer")
        properties = _map_of(node_schema, "properties") if isinstance(node_schema, dict) else {}
        child_schema = properties.get(name)
        if part.endswith("[]"):
            items = child_schema.get("items") if isinstance(child_schema, dict) else None
            if not isinstance(node.get(name), list) or not node[name]:
                node[name] = [draw_value(_strip(items if items is not None else {}), key,
                                         f"/placed/{name}/0")]
            if last:
                node[name][0] = placed
                return value
            if not isinstance(node[name][0], dict):
                node[name][0] = draw_value(_strip(items if items is not None else {}), key,
                                           f"/placed/{name}/0")
            node = node[name][0]
            node_schema = items
            continue
        if last:
            node[name] = placed
            return value
        if not isinstance(node.get(name), dict):
            node[name] = draw_value(_strip(child_schema if child_schema is not None else {}), key,
                                    f"/placed/{name}")
            if not isinstance(node[name], dict):
                node[name] = {}
        node = node[name]
        node_schema = child_schema
    return value


def _tool_of(task: _Any, name: str) -> _OwnTool:
    block = {str(t["name"]): t for t in task.tools}
    outputs = dict(task.output_schemas)
    effects = dict(task.effects)
    spec = block[name]
    return _OwnTool(name, str(spec["description"]), dict(spec["parameters"]), outputs.get(name),
                    effects.get(name, "unknown"))


def start(task: _Any) -> State:
    """The store before a task's first call."""
    writes = sum(1 for s in task.steps if s["effect"] == "write")
    reads = sum(1 for s in task.steps if s["effect"] == "read")
    return State(done=(False,) * writes, side_effects=(), calls=0, served=(False,) * reads)


def _indices(task: _Any) -> tuple[dict[int, int], dict[int, int]]:
    """Step index to flag index, for writes and for reads."""
    writes: dict[int, int] = {}
    reads: dict[int, int] = {}
    for index, step_ in enumerate(task.steps):
        if step_["effect"] == "write":
            writes[index] = len(writes)
        else:
            reads[index] = len(reads)
    return writes, reads


def _matches(step_: _Mapping[str, _Any], name: str, arguments: _Mapping[str, _Any],
             checkable: _Sequence[str]) -> bool:
    if step_["tool"] != name:
        return False
    match = step_["match"]
    if any(key not in arguments or not same(arguments[key], value)
           for key, value in match.items()):
        return False
    if step_.get("exact"):
        return not any(key in arguments and key not in match for key in checkable)
    return True


def _met(task: _Any, state: State, step_: _Mapping[str, _Any], writes: dict[int, int],
         reads: dict[int, int]) -> bool:
    for needed in step_["needs"]:
        other = task.steps[needed]
        if other["effect"] == "write":
            if not state.done[writes[needed]]:
                return False
        elif not state.served[reads[needed]]:
            return False
    return True


def _served_answer(task: _Any, tool: _OwnTool, arguments: _Mapping[str, _Any],
                   step_: _Mapping[str, _Any] | None) -> Answer:
    value = respond(tool, arguments, digest=task.file_digest, seed=task.seed, split=task.split)
    if step_ is not None and step_["serves"]:
        key = _key_of(task.file_digest, task.seed, task.split, tool.name, arguments)
        for path, placed in step_["serves"]:
            value = _place(value, str(path), placed, tool.output_schema, key)
    return success(task.source_format, tool, value)


def step(task: _Any, state: State, call: tuple[str, _Any]) -> tuple[State, Answer]:
    """One call that reached the server, answered, and the store after it."""
    name, arguments = call
    if not isinstance(arguments, dict):
        raise ValueError("a call that reaches the server carries a JSON object")
    tool = _tool_of(task, name)
    counts = dict(state.counts)
    counts[name] = counts.get(name, 0) + 1
    after = State(done=state.done, side_effects=state.side_effects, calls=state.calls + 1,
                  served=state.served, counts=tuple(sorted(counts.items())))
    fmt = task.source_format
    if dict(task.fault_plan).get(name, 0) >= counts[name]:
        return after, error(fmt, "unavailable", f"{name} is unavailable; make the call again")
    if not conforms(arguments, tool.input_schema):
        return after, error(fmt, "invalid_arguments",
                            f"the arguments do not fit {name}'s schema")
    writes, reads = _indices(task)
    properties = tool.input_schema.get("properties")
    checkable = [n for n, s in (properties.items() if isinstance(properties, dict) else ())
                 if not _free_text(s)]
    if tool.effect == "read":
        keyed = [i for i, s in enumerate(task.steps) if s["effect"] == "read" and s["tool"] == name]
        if not keyed:
            return after, _served_answer(task, tool, arguments, None)
        matching = [i for i in keyed if _matches(task.steps[i], name, arguments, checkable)]
        if not matching:
            return after, error(fmt, "not_found", f"{name} holds nothing for these arguments")
        pending = [i for i in matching if not state.served[reads[i]]]
        index = pending[0] if pending else matching[0]
        if not _met(task, state, task.steps[index], writes, reads):
            return after, error(fmt, "not_ready", f"{name} cannot answer this yet: a step it"
                                " depends on has not been made")
        served = list(after.served)
        served[reads[index]] = True
        after = State(done=after.done, side_effects=after.side_effects, calls=after.calls,
                      served=tuple(served), counts=after.counts)
        return after, _served_answer(task, tool, arguments, task.steps[index])
    expected = [i for i, s in enumerate(task.steps) if s["effect"] == "write"
                and _matches(s, name, arguments, checkable)]
    pending = [i for i in expected if not state.done[writes[i]]]
    if pending:
        index = pending[0]
        if not _met(task, state, task.steps[index], writes, reads):
            return after, error(fmt, "not_ready", f"{name} cannot be made yet: a step it"
                                " depends on has not been made")
        done = list(after.done)
        done[writes[index]] = True
        after = State(done=tuple(done), side_effects=after.side_effects, calls=after.calls,
                      served=after.served, counts=after.counts)
        return after, _served_answer(task, tool, arguments, task.steps[index])
    stray = (name, canonical(arguments))
    after = State(done=after.done, side_effects=after.side_effects + (stray,), calls=after.calls,
                  served=after.served, counts=after.counts)
    return after, _served_answer(task, tool, arguments, None)


def _free_text(schema: _Any) -> bool:
    # `own._schema.is_free_text`'s rule, repeated here so this module imports only the types.
    if not isinstance(schema, dict):
        return True
    kind = schema.get("type")
    if isinstance(kind, list):
        kinds = set(kind) - {"null"}
        if kinds and kinds != {"string"}:
            return False
    elif kind is not None and kind != "string":
        return False
    return not any(key in schema for key in ("format", "enum", "const", "minLength", "maxLength"))


def replay(task: _Any, calls: _Sequence[tuple[str, _Any]]) -> tuple[State, tuple[Answer, ...]]:
    """The calls that reach the server, in order, from the task's start."""
    block = {str(t["name"]): t for t in task.tools}
    state = start(task)
    answers: list[Answer] = []
    for name, arguments in calls:
        if not reaches_the_server(name, arguments, block):
            continue
        state, answer = step(task, state, (name, arguments))
        answers.append(answer)
    return state, tuple(answers)
