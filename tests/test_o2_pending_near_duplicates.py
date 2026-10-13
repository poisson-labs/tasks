"""Pending a yes/no: the card's census of the set's own near-duplicates.

**Why it is open.**  Spec §6.1, similarity: the copies are synthetic, "not the near-duplicates your set
may already hold; the card reports the latter's name and description distances, descriptively".
Which distances is not said.

**Recommendation: yes.**  `own.card.near_duplicates(toolset)` gives the closest pair by name and the
closest pair by description: the name distance is the edit distance over the longer name's length,
the description distance is one less the share of words (lower-cased runs of letters and digits) the
two descriptions have in common; each `(distance, first tool, second tool)`, the first pair in the
file's order on a tie.  It is reported, and never read as a level or a claim.  A no picks other
measures.
"""

from __future__ import annotations

import pytest

from tests.o2_support import acme, card, mcp_set, write_tool


def test_the_closest_names_and_descriptions_are_reported() -> None:
    toolset = mcp_set(
        write_tool("get_order", {"k": {"type": "integer"}}, description="Look up one order."),
        write_tool("get_orders", {"k": {"type": "integer"}}, description="List every customer."),
        write_tool("ship", {"k": {"type": "integer"}}, description="Look up one order today."),
    )
    census = card().near_duplicates(toolset)
    distance, first, second = census["name"]
    assert (first, second) == ("get_order", "get_orders") and distance == pytest.approx(1 / 10)
    distance, first, second = census["description"]
    assert (first, second) == ("get_order", "ship") and distance == pytest.approx(1 - 4 / 5)
    assert set(card().near_duplicates(acme())) == {"name", "description"}
