"""Pending a yes/no: how similarity names and describes the copies of a user's tool.

**Why it is open.**  Spec §6.1: lookalikes are "copies of the target tool scoped to other accounts:
the same name and description with a different four-digit number, as the knobs spec's ledger numbers;
the request names the account".  Two tools of one block cannot share a name, so the number is in the
name; where, and in what words the description carries it, is not said.

**Recommendation: yes.**  The target and its six copies are named `<name>_<number>` (the name cut
to its first 59 characters where that would pass 64) and described as the target is, then
` (account <number>)`; the request says `for account <number>` of the target's.  The target is
not shown under its own name on a similarity arm.  A no puts the number elsewhere (a prefix, or the
description alone with names `<name>_1` to `<name>_7`).
"""

from __future__ import annotations

from poisson_tasks import surface
from tests.o2_support import acme, generator, arm, mcp_set, write_tool


def test_names_descriptions_and_the_account_in_the_request() -> None:
    toolset = acme()
    descriptions = {t.name: t.description for t in toolset.tools}
    for level in (0, 3):
        for seed in range(6):
            bundle = generator().generate(toolset, arm("similarity", level), seed)
            number = surface.target_number(seed, "eval")
            original = bundle.target[: -len(number) - 1]
            assert bundle.target == f"{original}_{number}"
            shown = {str(t["name"]): str(t["description"]) for t in bundle.tools}
            for each in (number, *surface.lookalike_numbers(seed, "eval", level)):
                assert shown[f"{original}_{each}"] == f"{descriptions[original]} (account {each})"
            assert f"for account {number}" in bundle.request


def test_a_long_name_is_cut_to_fit() -> None:
    long = "a" * 62
    toolset = mcp_set(write_tool(long, {"k": {"type": "string", "enum": ["x", "y"]}}, ["k"]),
                      write_tool("other", {"k": {"type": "string", "enum": ["x", "y"]}}, ["k"]))
    for seed in range(10):
        bundle = generator().generate(toolset, arm("similarity", 2), seed)
        if bundle.target.startswith("a"):
            assert bundle.target == "a" * 59 + "_" + surface.target_number(seed, "eval")
            assert all(len(str(t["name"])) <= 64 for t in bundle.tools)
            return
    raise AssertionError("no seed drew the long-named tool")
