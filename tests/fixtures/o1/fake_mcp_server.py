"""A fake MCP server over stdio, for the tests of `--mcp-command`.

    python fake_mcp_server.py LOG MARKER

It speaks newline-delimited JSON-RPC 2.0 as the MCP stdio transport does.  It writes its own
pid as LOG's first line and then one line per request it receives (the method, and the
cursor for a `tools/list`), so a test can read exactly what Tasks asked it.  `tools/list`
answers two pages: the first with two tools and a `nextCursor`, the second with the third
tool.  A `tools/call` creates MARKER, which is how a test proves no tool was called.  Any
other request gets a "method not found" error.  It exits when its stdin closes.

It uses no MCP library, so what it accepts is exactly what is written here.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

LOG, MARKER = sys.argv[1], sys.argv[2]

TOOLS: list[dict[str, Any]] = [
    {
        "name": "get_shelf",
        "title": "Get shelf",
        "description": "Read one shelf of the warehouse by its code.",
        "inputSchema": {
            "type": "object",
            "properties": {"code": {"type": "string", "minLength": 4, "maxLength": 4}},
            "required": ["code"],
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "move.crate",
        "description": "Move a crate from one shelf to another.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "crate": {"type": "integer", "minimum": 1},
                "to": {"type": "string", "minLength": 4, "maxLength": 4},
            },
            "required": ["crate", "to"],
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False},
    },
    {
        "name": "count_crates",
        "description": "Count the crates on every shelf.",
        "inputSchema": {"type": "object", "properties": {}},
        "outputSchema": {
            "type": "object",
            "properties": {"count": {"type": "integer"}},
            "required": ["count"],
        },
    },
]


def log(line: str) -> None:
    with open(LOG, "a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def reply(request_id: Any, result: Any = None, error: Any = None) -> None:
    message: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id}
    if error is None:
        message["result"] = result
    else:
        message["error"] = error
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def main() -> None:
    log(str(os.getpid()))
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        request = json.loads(raw)
        method = request.get("method")
        request_id = request.get("id")
        if method == "initialize":
            log("initialize")
            reply(
                request_id,
                {
                    "protocolVersion": request["params"]["protocolVersion"],
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "fake-warehouse", "version": "0.1"},
                },
            )
        elif method == "notifications/initialized":
            log("notifications/initialized")
        elif method == "tools/list":
            cursor = (request.get("params") or {}).get("cursor")
            log(f"tools/list cursor={cursor!r}")
            if cursor is None:
                reply(request_id, {"tools": TOOLS[:2], "nextCursor": "page-2"})
            else:
                reply(request_id, {"tools": TOOLS[2:]})
        elif method == "tools/call":
            log("tools/call")
            with open(MARKER, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(request.get("params")))
            reply(request_id, {"content": [{"type": "text", "text": "called"}]})
        elif method == "ping":
            log("ping")
            reply(request_id, {})
        elif request_id is not None:
            log(f"other {method}")
            reply(request_id, error={"code": -32601, "message": "method not found"})
        else:
            log(f"other {method}")


if __name__ == "__main__":
    main()
