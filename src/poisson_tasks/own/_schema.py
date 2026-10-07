"""JSON Schema handling shared by the readers: `$ref` inlining, the object test, the rules of
spec §3 on an argument schema, and the free-text test behind `can_target`.

Nothing here knows the formats.  A schema that cannot be used raises `SchemaProblem` with the
refusal kind (`schema`, `binary` or `not_object`) and a one-line reason; the caller turns it
into a `Refusal` naming the tool.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import unquote

# JSON Schema keywords the simulator cannot check exactly (spec §3, third bullet), beside a
# schema-valued `additionalProperties`, a `$ref` cycle and the depth, which are tested apart.
UNCHECKABLE = ("anyOf", "oneOf", "allOf", "not", "patternProperties")
# The argument object is level 0; a schema at this level is one too deep (spec §3, "nesting
# deeper than three levels"; the frozen test counts an array's items as a level).
TOO_DEEP = 4
# The keys a free-text string lacks (spec §3: "free text with no format, enum or bound").
NOT_FREE = ("format", "enum", "const", "minLength", "maxLength")
# Where a schema keeps the subschemas its `$ref`s name; dropped once they are inlined.
DEFINITION_KEYS = ("$defs", "definitions")


class SchemaProblem(Exception):
    """A schema the simulator cannot use: `kind` is one of the refusal kinds, `reason` one line."""

    def __init__(self, kind: str, reason: str) -> None:
        super().__init__(reason)
        self.kind = kind
        self.reason = reason


def resolve_pointer(root: Any, reference: str) -> Any:
    """What a local `$ref` (`#/a/b`, RFC 6901 escapes and percent-encoding allowed) names in
    `root`; `KeyError` when it names nothing."""
    if not reference.startswith("#"):
        raise KeyError(reference)
    pointer = unquote(reference[1:])
    if pointer == "":
        return root
    if not pointer.startswith("/"):
        raise KeyError(reference)
    node = root
    for part in pointer[1:].split("/"):
        key = part.replace("~1", "/").replace("~0", "~")
        if isinstance(node, dict):
            if key not in node:
                raise KeyError(reference)
            node = node[key]
        elif isinstance(node, list):
            try:
                node = node[int(key)]
            except (ValueError, IndexError):
                raise KeyError(reference) from None
        else:
            raise KeyError(reference)
    return node


def inline(node: Any, root: Any, _active: tuple[str, ...] = ()) -> Any:
    """`node` with every `$ref` under it replaced by what it names in `root`, at any depth,
    the keys beside a `$ref` winning over the referenced schema's.  A new structure: the
    parsed file is not changed.  A `$ref` that names nothing, one that is not inside the
    file, or a cycle of references raises `SchemaProblem("schema", ...)`."""
    if isinstance(node, dict):
        reference = node.get("$ref")
        if isinstance(reference, str):
            if reference in _active:
                raise SchemaProblem("schema", f"its schema has a $ref cycle through {reference}")
            try:
                target = resolve_pointer(root, reference)
            except KeyError:
                raise SchemaProblem(
                    "schema", f"its schema has a $ref that names nothing in the file: {reference}"
                ) from None
            resolved = inline(target, root, (*_active, reference))
            siblings = {k: inline(v, root, _active) for k, v in node.items() if k != "$ref"}
            if isinstance(resolved, dict):
                return {**resolved, **siblings}
            return resolved
        return {k: inline(v, root, _active) for k, v in node.items()}
    if isinstance(node, list):
        return [inline(v, root, _active) for v in node]
    return node


def resolve_chain(node: Any, root: Any) -> Any:
    """`node` itself with a `$ref` at its top followed (and followed again), the keys beside
    it winning; nothing below the top is touched.  For the objects around a schema (a path
    item, a parameter, a request body, a response), which large documents write by reference."""
    seen: tuple[str, ...] = ()
    while isinstance(node, dict) and isinstance(node.get("$ref"), str):
        reference = node["$ref"]
        if reference in seen:
            raise SchemaProblem("schema", f"its definition has a $ref cycle through {reference}")
        try:
            target = resolve_chain(resolve_pointer(root, reference), root)
        except KeyError:
            raise SchemaProblem(
                "schema", f"its definition has a $ref that names nothing in the file: {reference}"
            ) from None
        siblings = {k: v for k, v in node.items() if k != "$ref"}
        node = {**target, **siblings} if isinstance(target, dict) else target
        seen = (*seen, reference)
    return node


def without_definitions(schema: Any) -> Any:
    """The schema without its top-level `$defs` and `definitions`, which inlining made dead."""
    if isinstance(schema, dict) and any(key in schema for key in DEFINITION_KEYS):
        return {k: v for k, v in schema.items() if k not in DEFINITION_KEYS}
    return schema


def is_object_schema(schema: Any) -> bool:
    """A JSON object schema: a mapping whose `type` is `"object"`, or with no `type` and a
    `properties` mapping.  A type list, a bare `{}` and anything that is not a mapping are not."""
    if not isinstance(schema, dict):
        return False
    if "type" in schema:
        return bool(schema["type"] == "object")
    return isinstance(schema.get("properties"), dict)


def describe(schema: Any) -> str:
    """What a value that should have been an object schema is, for a refusal's reason."""
    if isinstance(schema, dict):
        if "type" in schema:
            return f"a schema whose type is {schema['type']!r}"
        return "a mapping with neither a type nor properties"
    if isinstance(schema, list):
        return "a list"
    if isinstance(schema, str):
        return "text"
    if isinstance(schema, bool):
        return "a boolean"
    if isinstance(schema, int | float):
        return "a number"
    if schema is None:
        return "nothing"
    return type(schema).__name__


def check_argument_schema(schema: Any) -> None:
    """Spec §3's rules on an argument schema, every `$ref` already inlined: no file or binary
    string anywhere in it (kind `binary`), none of `UNCHECKABLE`, no schema-valued
    `additionalProperties`, and nothing deeper than three levels (kind `schema`)."""
    _walk(schema, 0)


def _walk(node: Any, level: int) -> None:
    if not isinstance(node, dict):
        return
    if level >= TOO_DEEP:
        raise SchemaProblem(
            "schema",
            "its argument schema nests deeper than three levels, which the simulator"
            " cannot fill exactly",
        )
    if node.get("format") == "binary":
        raise SchemaProblem("binary", "it takes a binary string (a schema with format: binary)")
    if "contentEncoding" in node:
        raise SchemaProblem(
            "binary", "it takes an encoded binary string (a schema with contentEncoding)"
        )
    for key in UNCHECKABLE:
        if key in node:
            raise SchemaProblem(
                "schema",
                f"its argument schema uses {key}, which the simulator cannot check exactly",
            )
    if isinstance(node.get("additionalProperties"), dict):
        raise SchemaProblem(
            "schema",
            "its argument schema gives additionalProperties a schema, which the"
            " simulator cannot check exactly",
        )
    properties = node.get("properties")
    if isinstance(properties, dict):
        for child in properties.values():
            _walk(child, level + 1)
    for key in ("items", "prefixItems"):
        children = node.get(key)
        if isinstance(children, dict):
            _walk(children, level + 1)
        elif isinstance(children, list):
            for child in children:
                _walk(child, level + 1)


def is_free_text(schema: Any) -> bool:
    """Whether an argument is free text, so no exact value of it can be checked: a string, or
    an argument with no type, that has none of `NOT_FREE`.  A `pattern` does not count."""
    if not isinstance(schema, dict):
        return True
    kind = schema.get("type")
    if isinstance(kind, list):
        kinds = set(kind) - {"null"}
        if kinds and kinds != {"string"}:
            return False
    elif kind is not None and kind != "string":
        return False
    return not any(key in schema for key in NOT_FREE)
