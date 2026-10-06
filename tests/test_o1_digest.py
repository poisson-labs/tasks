"""The file digest and the summary, frozen as tests (O1.4), and the package's import footprint.

The invariant is O1.4 of the knobs plan, from the own-tools spec §2.2 and §8.1: the set's digest is
over the file's bytes, it appears in the summary, and a user never types it.

Shapes decided here
-------------------

**1. The digest is SHA-256 of the file's bytes**, as hex: the one hash this package already takes
its ids and its generator hash with.  Because it is over the bytes and not the parsed content, a
file re-saved with other whitespace has another digest, which is right: `doctor` says the tasks
changed when the file changed (§8.2), and the file is what the user keeps.

**2. The summary.**  Its first line is §8.1's, with every count always present so the line can be
read back: `N tools: R read, W write, U not known (treated as write), X refused`, where N is the
number of usable tools (R + W + U; the example in §8.1 adds up that way) and the suffix ` (one
line each below)` follows only when X is not 0.  The next X lines are the refusals' lines, in
file order.  The digest appears on a line of its own after them, and every renamed tool is listed
with its original, so `init` and `doctor` show both as §3 asks.  The words of those later lines
are not pinned.

**3. "Never typed."**  No public function of the package takes a digest from its caller: the
digest is computed by `read_tools` from the bytes it was given, and that is the only way one is
made.

**4. The import footprint.**  `import poisson_tasks.own` imports no `verifiers`, no `mcp` and none
of the generator (`poisson_tasks.tasks`): `init` and `doctor` read a tool file in a process with
nothing else loaded, and O1 changes no generator (its hash is K1's business).  `list_mcp_tools`
imports what it needs when it is called.
"""

from __future__ import annotations

import hashlib
import inspect
import subprocess
import sys

from poisson_tasks import own
from tests.o1_support import fixture, function, mcp_file, mcp_partner, mcp_tool, openai_file, partner, read


def test_the_digest_is_sha256_over_the_files_bytes() -> None:
    data = fixture("acme-openai-chat.json")
    first = read(data).toolset.file_digest
    assert first == hashlib.sha256(data).hexdigest()
    assert read(data).toolset.file_digest == first
    respaced = data.replace(b"\n", b"\n ")  # the same content, other bytes
    assert read(respaced).toolset.tools == read(data).toolset.tools
    assert read(respaced).toolset.file_digest == hashlib.sha256(respaced).hexdigest() != first
    digests = {name: read(fixture(name)).toolset.file_digest for name in
               ("acme-openai-chat.json", "acme-mcp-tools-list.json", "acme-openapi-3.0.json")}
    assert len(set(digests.values())) == 3


def test_the_summary_counts_the_tools_lists_each_refusal_and_shows_the_digest() -> None:
    reading = read(
        mcp_file(
            mcp_tool("alpha", annotations={"readOnlyHint": True}),
            mcp_tool("beta", annotations={"readOnlyHint": True}),
            mcp_partner("gamma"),
            mcp_tool("delta"),
            mcp_tool("my.epsilon", {"type": "string"}),
            mcp_tool("my.zeta"),
        )
    )
    assert [r.name for r in reading.refused] == ["my.epsilon"]
    text = own.summary(reading)
    lines = text.splitlines()
    assert lines[0] == "5 tools: 2 read, 1 write, 2 not known (treated as write), 1 refused (one line each below)"
    assert lines[1] == reading.refused[0].line
    assert "\n" not in reading.refused[0].line and "my.epsilon" in reading.refused[0].line
    assert reading.toolset.file_digest in text
    assert "my_zeta" in text and "my.zeta" in text
    clean = read(openai_file(partner("alpha"), partner("beta")))
    clean_lines = own.summary(clean).splitlines()
    assert clean_lines[0] == "2 tools: 0 read, 0 write, 2 not known (treated as write), 0 refused"
    assert clean.toolset.file_digest in own.summary(clean)
    two = read(openai_file(partner("alpha"), function("bad", {"type": "array"}), partner("gamma"),
                           function("worse", {"type": "string"})))
    two_lines = own.summary(two).splitlines()
    assert two_lines[0].startswith("2 tools: 0 read, 0 write, 2 not known (treated as write), 2 refused")
    assert two_lines[1:3] == [r.line for r in two.refused]


def test_nothing_takes_a_digest_from_the_user() -> None:
    for name in ("read_tools", "apply_effects", "summary", "list_mcp_tools", "safe_name", "can_target", "is_write"):
        parameters = inspect.signature(getattr(own, name)).parameters
        assert not any("digest" in p.lower() or "hash" in p.lower() for p in parameters), name
    assert "data" in inspect.signature(own.read_tools).parameters


def test_importing_the_package_imports_no_verifiers_no_mcp_and_none_of_the_generator() -> None:
    code = (
        "import sys, poisson_tasks.own\n"
        "loaded = {m.split('.')[0] for m in sys.modules} | set(sys.modules)\n"
        "bad = sorted(m for m in ('verifiers', 'mcp', 'poisson_tasks.tasks', 'poisson_tasks.surface',"
        " 'poisson_tasks.knobs', 'poisson_tasks.engine', 'poisson_tasks.export') if m in loaded)\n"
        "print(bad)\n"
    )
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert done.stdout.strip() == "[]"
