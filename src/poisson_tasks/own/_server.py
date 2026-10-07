"""`--mcp-command`: start a user's MCP server once, list its tools, stop it.

The MCP client is imported here, inside the function, so `import poisson_tasks.own` stays
light.  Tasks asks the server `initialize`, sends `notifications/initialized`, and asks
`tools/list` once per page; it calls no tool, and the server has been stopped (its stdin
closed, then the process ended if it did not exit) before the function returns.
"""

from __future__ import annotations

import json
import os
import shlex
from typing import Any

from poisson_tasks.own._types import OwnToolsError

# How long one answer from the server may take.  A server that is still installing itself
# (an `npx -y ...` command on a cold cache) can need most of this.
ANSWER_SECONDS = 15.0
# No server lists more pages than this; a cursor that repeats, or more pages, is a server
# that does not page as MCP says, and is refused rather than listed forever.
MAX_PAGES = 1000


def list_mcp_tools(command: str, *, consent: bool) -> bytes:
    """The merged `tools/list` result of the server `command` starts, pages in the server's
    order, as this package's canonical JSON (`{"tools": [...]}`): the bytes `init` saves as
    `tools.mcp.json` and the MCP reader reads.  Without `consent` nothing starts.  A command
    that cannot start, or a program that is not an MCP server, is refused in one line."""
    if not consent:
        raise OwnToolsError(
            "the server was not started: Tasks starts your MCP server only with your consent,"
            " to list its tools and nothing else",
            "consent",
        )
    try:
        words = shlex.split(command)
    except ValueError as error:
        raise OwnToolsError(
            f"the command could not be split into words: {error}", "server"
        ) from None
    if not words:
        raise OwnToolsError("the command is empty", "server")
    try:
        tools = _list(words)
    except OwnToolsError:
        raise
    except Exception as error:
        raise OwnToolsError(
            f"could not list the tools of `{command}`: {_one_line(error)}", "server"
        ) from None
    return json.dumps({"tools": tools}, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _list(words: list[str]) -> list[Any]:
    from datetime import timedelta

    import anyio
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def go() -> list[Any]:
        server = StdioServerParameters(command=words[0], args=words[1:], env=dict(os.environ))
        tools: list[Any] = []
        async with stdio_client(server) as (read_stream, write_stream):
            session = ClientSession(
                read_stream, write_stream, read_timeout_seconds=timedelta(seconds=ANSWER_SECONDS)
            )
            async with session:
                await session.initialize()
                cursor: str | None = None
                seen: set[str] = set()
                for _ in range(MAX_PAGES):
                    page = await session.list_tools(cursor)
                    # `exclude_unset`: the keys the server sent and no other, so the saved
                    # file is the server's listing and not the client's model of it.
                    dumped = page.model_dump(mode="json", by_alias=True, exclude_unset=True)
                    tools.extend(dumped.get("tools", []))
                    cursor = page.nextCursor
                    if not cursor:
                        return tools
                    if cursor in seen:
                        raise OwnToolsError(
                            "the server repeats a tools/list cursor, so its pages never end",
                            "server",
                        )
                    seen.add(cursor)
        raise OwnToolsError(f"the server lists more than {MAX_PAGES} pages of tools", "server")

    result: list[Any] = anyio.run(go)
    return result


def _one_line(error: BaseException) -> str:
    """The first leaf of an exception (groups opened) in one line."""
    while isinstance(error, BaseExceptionGroup) and error.exceptions:
        error = error.exceptions[0]
    text = str(error).strip() or type(error).__name__
    return " ".join(text.splitlines()[0].split())
