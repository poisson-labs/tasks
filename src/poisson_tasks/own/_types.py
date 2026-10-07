"""The normal form's types, apart so the readers and the public module share them."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

EFFECTS = ("read", "write", "unknown")
FORMATS = ("openai", "mcp", "openapi")
REFUSAL_KINDS = ("name", "duplicate", "not_object", "schema", "binary", "merge", "builtin")
ERROR_KINDS = (
    "shape",
    "format",
    "too_few",
    "too_many",
    "no_target",
    "effects",
    "consent",
    "server",
)


@dataclass(frozen=True)
class OwnTool:
    """One tool in the normal form: its (possibly renamed) name, its description, its argument
    schema with every `$ref` inlined, its output schema when the format has one, its effect
    (`read`, `write` or `unknown`), and its title: the original name when the name was renamed,
    else the format's own title when it has one, else `None`."""

    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None
    effect: str
    title: str | None = None


@dataclass(frozen=True)
class OwnToolSet:
    """A set of tools read from one file: the caller's name for it, the usable tools in file
    order, the format they were read from, and the digest of the file's bytes."""

    name: str
    tools: tuple[OwnTool, ...]
    source_format: str
    file_digest: str


@dataclass(frozen=True)
class Refusal:
    """One refused tool: its name as the file gave it, the kind of refusal (one of
    `REFUSAL_KINDS`) and the reason in plain words."""

    name: str
    kind: str
    reason: str

    @property
    def line(self) -> str:
        """The refusal as `init` and `doctor` print it: one line naming the tool."""
        shown = " ".join(self.name.splitlines()) or "(a tool with no name)"
        return f"{shown}: refused, {' '.join(self.reason.splitlines())}"


@dataclass(frozen=True)
class Reading:
    """What reading a file gives: the usable tools as a set, and the refused tools."""

    toolset: OwnToolSet
    refused: tuple[Refusal, ...]


class OwnToolsError(ValueError):
    """A file, a set, a declaration or a command is refused as a whole: `str(error)` is one
    line, `kind` is one of `ERROR_KINDS`, and `refused` carries the per-tool refusals found
    before a set was refused."""

    def __init__(self, message: str, kind: str, refused: Sequence[Refusal] = ()) -> None:
        super().__init__(message)
        self.kind = kind
        self.refused: tuple[Refusal, ...] = tuple(refused)


@dataclass
class RawTool:
    """One tool as a reader hands it to the normal form, before the renaming and the schema
    rules: the name as the file gave it (perhaps not text), the description, the argument
    schema (the OpenAPI reader's merged object; `None` when the reader found none), the output
    schema or `None`, the effect the format states, the format's title, the document the
    schemas' `$ref`s resolve against (`None`: each schema is its own document), and a problem
    the reader already found as `(kind, reason)`."""

    name: Any
    description: str
    input_schema: Any
    output_schema: Any
    effect: str
    title: str | None = None
    root: Any = None
    problem: tuple[str, str] | None = None
