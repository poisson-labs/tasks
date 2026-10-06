"""Poisson Tasks on a user's own tools: the readers and the normal form.

A user brings the tool definitions they already have, as an OpenAI tools file (Chat Completions
or Responses shape), an MCP `tools/list` result, or an OpenAPI 3.0 or 3.1 document, and this
package reads them into one normal form, refusing in one line each what it cannot handle.  It
never calls a user's endpoint or tool: `list_mcp_tools` starts a user's MCP server only to list
its tools, with their consent, and stops it.

Names only: each body is the build's.  `tests/test_o1_*.py` say what each name does.  Importing
this package imports no `verifiers`, no `mcp` and none of the generator.
"""

from __future__ import annotations

from collections.abc import Sequence as _Sequence
from dataclasses import dataclass as _dataclass
from typing import Any as _Any

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

EFFECTS = ("read", "write", "unknown")
FORMATS = ("openai", "mcp", "openapi")
REFUSAL_KINDS = ("name", "duplicate", "not_object", "schema", "binary", "merge", "builtin")
ERROR_KINDS = (
    "shape", "format", "too_few", "too_many", "no_target", "effects", "consent", "server"
)


@_dataclass(frozen=True)
class OwnTool:
    """One tool in the normal form: its (possibly renamed) name, its description, its argument
    schema with every `$ref` inlined, its output schema when the format has one, its effect
    (`read`, `write` or `unknown`), and its title: the original name when the name was renamed,
    else the format's own title when it has one, else `None`."""

    name: str
    description: str
    input_schema: dict[str, _Any]
    output_schema: dict[str, _Any] | None
    effect: str
    title: str | None = None


@_dataclass(frozen=True)
class OwnToolSet:
    """A set of tools read from one file: the caller's name for it, the usable tools in file
    order, the format they were read from, and the digest of the file's bytes."""

    name: str
    tools: tuple[OwnTool, ...]
    source_format: str
    file_digest: str


@_dataclass(frozen=True)
class Refusal:
    """One refused tool: its name as the file gave it, the kind of refusal (one of
    `REFUSAL_KINDS`) and the reason in plain words."""

    name: str
    kind: str
    reason: str

    @property
    def line(self) -> str:
        """The refusal as `init` and `doctor` print it: one line naming the tool."""
        raise NotImplementedError


@_dataclass(frozen=True)
class Reading:
    """What reading a file gives: the usable tools as a set, and the refused tools."""

    toolset: OwnToolSet
    refused: tuple[Refusal, ...]


class OwnToolsError(ValueError):
    """A file, a set, a declaration or a command is refused as a whole: `str(error)` is one
    line, `kind` is one of `ERROR_KINDS`, and `refused` carries the per-tool refusals found
    before a set was refused."""

    def __init__(self, message: str, kind: str, refused: _Sequence[Refusal] = ()) -> None:
        super().__init__(message)
        self.kind = kind
        self.refused: tuple[Refusal, ...] = tuple(refused)


def read_tools(data: bytes, *, format: str = "auto", name: str = "own-tools") -> Reading:
    """Read a tool file's bytes into the normal form."""
    raise NotImplementedError


def safe_name(original: str) -> str:
    """The one fixed renaming of a tool's name."""
    raise NotImplementedError


def can_target(tool: OwnTool) -> bool:
    """Whether a task may require a call to this tool with particular values."""
    raise NotImplementedError


def is_write(tool: OwnTool) -> bool:
    """Whether a stray call to this tool counts as a side effect."""
    raise NotImplementedError


def apply_effects(
    toolset: OwnToolSet, *, read: _Sequence[str] = (), write: _Sequence[str] = ()
) -> OwnToolSet:
    """The set with the effects the user declared in `tasks.toml`."""
    raise NotImplementedError


def summary(reading: Reading) -> str:
    """The summary `init` and `doctor` print: the counts, then each refusal in one line."""
    raise NotImplementedError


def list_mcp_tools(command: str, *, consent: bool) -> bytes:
    """Start the user's MCP server once, list its tools, stop it; the merged result as
    canonical JSON bytes."""
    raise NotImplementedError
