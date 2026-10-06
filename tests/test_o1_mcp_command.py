"""`--mcp-command`: Tasks starts a user's MCP server once to list its tools, stops it and calls
nothing else, frozen as tests (O1.5).

The invariant is O1.5 of the knobs plan, from the own-tools spec §2.1, §3 ("Tasks will not call
your endpoints, your MCP server's tools or anything else on your network; `--mcp-command` starts
your server only to list its tools, with your consent, and stops it") and §8.2 (the merged
`tools/list` result, pages in the server's order, saved as canonical JSON, which the digest then
covers).  The server here is `tests/fixtures/o1/fake_mcp_server.py`, a stdio JSON-RPC server with
no MCP library behind it, which logs every request it receives and leaves a marker file if any
tool is called.  Nothing here touches the network.

Shapes decided here
-------------------

**1. `list_mcp_tools(command, *, consent)`** takes the command as one string, split into words as
a POSIX shell would (`shlex.split`), and a boolean consent the caller (`init`) has obtained;
without consent it starts nothing and refuses (`OwnToolsError`).

**2. What it returns is the file** `init` saves beside `tasks.toml` as `tools.mcp.json` (§8.2):
the bytes of `{"tools": [...]}`, the pages' tools in the server's order, as this package's
canonical JSON (`json.dumps(..., sort_keys=True, separators=(",", ":"))`, the rendering every
hash in `tasks.py` is taken over), so `read_tools` on those bytes is the MCP reader and the digest
is over them.

**3. What it asks the server** is `initialize`, the `initialized` notification, and `tools/list`
once per page, following `nextCursor`; nothing else, and no `tools/call` whatever the server
offers.  The server has exited before the function returns.

**4. A command that cannot start, or a program that is not an MCP server**, is refused in one
line (`OwnToolsError`), never a traceback from the transport.
"""

from __future__ import annotations

import json
import os
import shlex
import sys
import time
from pathlib import Path

import pytest

from poisson_tasks import own
from tests.o1_support import FAKE_MCP_SERVER, read


def fake_command(tmp_path: Path) -> tuple[str, Path, Path]:
    log = tmp_path / "requests.log"
    marker = tmp_path / "called.marker"
    command = " ".join(shlex.quote(part) for part in (sys.executable, str(FAKE_MCP_SERVER), str(log), str(marker)))
    return command, log, marker


def process_gone(pid: int, within: float = 5.0) -> bool:
    deadline = time.monotonic() + within
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            return False
        # a child the function has waited on is gone; one it has not is a zombie that still answers
        try:
            done_pid, _ = os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            return True
        if done_pid == pid:
            return True
        time.sleep(0.05)
    return False


def test_the_command_lists_the_servers_tools_across_pages_stops_it_and_calls_nothing(tmp_path: Path) -> None:
    command, log, marker = fake_command(tmp_path)
    data = own.list_mcp_tools(command, consent=True)
    lines = log.read_text().splitlines()
    pid = int(lines[0])
    assert process_gone(pid)
    assert lines[1:] == ["initialize", "notifications/initialized", "tools/list cursor=None", "tools/list cursor='page-2'"]
    assert not marker.exists()
    merged = json.loads(data)
    assert [t["name"] for t in merged["tools"]] == ["get_shelf", "move.crate", "count_crates"]
    assert set(merged) == {"tools"}
    assert data == json.dumps(merged, sort_keys=True, separators=(",", ":")).encode("utf-8")
    reading = read(data)
    assert reading.toolset.source_format == "mcp"
    assert [t.name for t in reading.toolset.tools] == ["get_shelf", "move_crate", "count_crates"]
    assert [t.effect for t in reading.toolset.tools] == ["read", "write", "unknown"]
    assert [t.title for t in reading.toolset.tools] == ["Get shelf", "move.crate", None]
    assert reading.toolset.tools[2].output_schema == {
        "type": "object", "properties": {"count": {"type": "integer"}}, "required": ["count"]}
    # the same server listed again gives the same bytes, so the digest is stable
    assert own.list_mcp_tools(command, consent=True) == data


def test_without_consent_nothing_starts(tmp_path: Path) -> None:
    command, log, marker = fake_command(tmp_path)
    with pytest.raises(own.OwnToolsError) as caught:
        own.list_mcp_tools(command, consent=False)
    assert caught.value.kind == "consent"
    assert not log.exists() and not marker.exists()


def test_a_command_that_is_not_an_mcp_server_is_refused_in_one_line(tmp_path: Path) -> None:
    with pytest.raises(own.OwnToolsError) as missing:
        own.list_mcp_tools(str(tmp_path / "no-such-program"), consent=True)
    assert str(missing.value).count("\n") == 0 and missing.value.kind == "server"
    quiet = tmp_path / "quiet.py"
    quiet.write_text("import sys\nsys.stdin.read()\n")  # answers nothing, ever
    with pytest.raises(own.OwnToolsError) as silent:
        own.list_mcp_tools(f"{shlex.quote(sys.executable)} {shlex.quote(str(quiet))}", consent=True)
    assert str(silent.value).count("\n") == 0 and silent.value.kind == "server"
    chatty = tmp_path / "chatty.py"
    chatty.write_text("print('hello, not json')\nimport sys\nsys.stdin.read()\n")
    with pytest.raises(own.OwnToolsError):
        own.list_mcp_tools(f"{shlex.quote(sys.executable)} {shlex.quote(str(chatty))}", consent=True)
    command, _, _ = fake_command(tmp_path)
    own.list_mcp_tools(command, consent=True)  # the control: the fake server lists
