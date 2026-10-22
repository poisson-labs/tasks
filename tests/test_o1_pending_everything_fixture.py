"""Pending a decision: the MCP Everything reference server's `tools/list` reads as recorded.

`tests/fixtures/o1/mcp-everything-tools-list.json` is the one-page `tools/list` result of
`@modelcontextprotocol/server-everything` (npm 2026.8.31, which names itself 2.0.0), recorded once
on 2026-10-06 from the server started over stdio and asked only to list its tools.  It is the
"public MCP server" fixture of the own-tools design, and the one real tool list with titles,
annotations on every tool and an output schema.  Its licence is in doubt (the MCP servers
repository is moving from MIT to Apache-2.0 and says some contributions remain MIT), so the fixture,
this test and its `NOTICE` entry are one commit, which are dropped together if it is declined.

What it pins that the acme fixtures cannot: thirteen real tools read with their titles kept, their
`inputSchema` kept as written (a `$schema` key and all), `outputSchema` carried for the one tool that
has it and `None` for the rest, and every effect read off the annotations (nine reads, four writes).
"""

from __future__ import annotations

import json

from poisson_tasks import own
from tests.o1_support import by_name, fixture, names, read


def test_the_everything_servers_list_reads_with_titles_and_schemas_as_written() -> None:
    data = fixture("mcp-everything-tools-list.json")
    listed = json.loads(data)["tools"]
    reading = read(data)
    assert reading.toolset.source_format == "mcp"
    assert reading.refused == ()
    assert names(reading) == [t["name"] for t in listed]
    for tool, item in zip(reading.toolset.tools, listed, strict=True):
        assert tool.title == item["title"]
        assert tool.description == item["description"]
        assert tool.input_schema == item["inputSchema"]
        assert tool.output_schema == item.get("outputSchema")
    assert [t.name for t in reading.toolset.tools if t.output_schema is not None] == ["get-structured-content"]
    assert "$schema" in by_name(reading, "get-sum").input_schema
    assert [t.effect for t in reading.toolset.tools] == (
        ["read"] * 8 + ["write", "write", "write", "read", "write"])
    assert {t.name for t in reading.toolset.tools if not own.can_target(t)} == {
        "echo", "get-env", "get-tiny-image", "toggle-simulated-logging", "toggle-subscriber-updates"}
    assert own.summary(reading).splitlines()[0] == "13 tools: 9 read, 4 write, 0 not known (treated as write), 0 refused"
