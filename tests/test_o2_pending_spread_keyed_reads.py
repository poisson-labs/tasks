"""Pending a yes/no: spread's named reads are reads with a checkable argument.

**Why it is open.**  Spec §6.1: spread needs "a read tool taking an argument".  A read whose only
arguments are free text takes one, but a request cannot name one call of it apart from another by a
value the simulator can match exactly (spec §3's reason a free-text tool is no target).

**Recommendation: yes.**  The named reads are reads with at least one checkable argument; a set whose
reads take only free text has no spread levels.  A no names free-text reads by their text, matched
byte for byte.
"""

from __future__ import annotations

from tests.o2_support import generator, mcp_set, read_tool, write_tool


def test_a_read_that_takes_only_free_text_gives_no_spread() -> None:
    write = write_tool("open_case", {"code": {"type": "string", "minLength": 8, "maxLength": 8}}, ["code"])
    free = mcp_set(write, *(read_tool(f"find_{each}", {"query": {"type": "string"}}, ["query"])
                            for each in ("one", "two", "three", "four", "five")))
    assert generator().knob_levels(free, "spread") == ()
