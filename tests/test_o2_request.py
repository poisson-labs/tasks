"""The request's words on a user's own tools, frozen as tests.

Spec §7: a task's request names what to do without naming the tool, or selection becomes a word
match.  With intents (`[own.intents]`, one line per tool) the request uses the intent; without,
the first sentence of the tool's description, and the card says selection was partly a word match
(the card's line is in `tests/test_o2_card.py`).  Values come from the schemas, drawn per
parameter type and format, and are stated in the request.  Tasks never invents a tool's meaning.

Shapes decided here
-------------------

**1. `OwnBundle.request`** is the request's text, the user message; on a history arm it is the
first message of `prompt`, which is otherwise `request` itself (`tests/test_o2_knobs.py`).

**2. A value is stated as JSON**: a string in double quotes, as the built-in template quotes its
record ids, a number or a boolean as JSON writes it.  So the request holds `json.dumps(value)` for
each `(name, value)` of `stated`.  How it says which argument each value is for is the build's
(spec §7's own example says "amount 12.50", not the argument's name).

**3. No tool's name** (any name the block shows, and any name of the set) appears in the request
as a word, even where an intent or a description says it: such a word is not the request's to
keep.  A word here is a run of letters, digits, `_` and `-`.

**4. An intent naming a tool the set does not hold is refused** (`ValueError`, one line).
"""

from __future__ import annotations

import json
import re

import pytest

from tests.o2_support import (
    acme,
    acme_flows,
    every_arm,
    fixture_sets,
    flows_for,
    generator,
    make,
    mcp_set,
    read_tool,
    write_tool,
)

INTENTS = {
    "get_order": "look up an order to see its status",
    "search_orders": "find orders by the words in their notes",
    "refund_order": "refund a customer's order",
    "notify_customer": "let a customer know about their order",
    "list_channels": "see which ways a customer can be reached",
}


def words(text: str) -> set[str]:
    """The request's words, a hyphenated name (`get-env`) whole as well as its parts."""
    return set(re.findall(r"[A-Za-z0-9_]+", text)) | set(re.findall(r"[A-Za-z0-9_-]+", text))


def first_sentence(description: str) -> str:
    return re.split(r"(?<=[.!?])\s", " ".join(description.split()), maxsplit=1)[0].rstrip(".!?")


def sentence_in(sentence: str, request: str) -> bool:
    """The sentence is in the request, its first letter's case aside."""
    return sentence in request or (sentence[:1].upper() + sentence[1:]) in request


@pytest.mark.parametrize("label", ["acme-mcp", "acme-openai", "acme-openapi-3.0", "petstore", "everything"])
def test_no_request_names_a_tool(label: str) -> None:
    toolset, flows = fixture_sets()[label], flows_for(label)
    every_name = {tool.name for tool in toolset.tools}
    for spec in every_arm(toolset, flows):
        for seed in range(15):
            bundle = generator().generate(toolset, spec, seed, flows=flows)
            shown = {str(tool["name"]) for tool in bundle.tools}
            assert not (words(bundle.request) & (shown | every_name)), (label, spec, seed, bundle.request)


def test_without_intents_the_request_uses_the_first_sentence_of_the_targets_description() -> None:
    toolset = acme()
    descriptions = {tool.name: tool.description for tool in toolset.tools}
    for knob, level in (("faults", 0), ("history", 300), ("similarity", 2)):
        for seed in range(10):
            bundle = make(toolset, knob, level, seed=seed)
            assert sentence_in(first_sentence(descriptions[bundle.target_tool]), bundle.request), bundle.request


def test_with_intents_the_request_uses_the_intent_and_not_the_description() -> None:
    toolset = acme()
    descriptions = {tool.name: tool.description for tool in toolset.tools}
    gen = generator()
    for spec in every_arm(toolset, acme_flows()):
        for seed in range(5):
            plain = gen.generate(toolset, spec, seed, flows=acme_flows())
            bundle = gen.generate(toolset, spec, seed, intents=INTENTS, flows=acme_flows())
            original = bundle.target_tool
            assert sentence_in(INTENTS[original], bundle.request), (spec, bundle.request)
            assert not sentence_in(first_sentence(descriptions[original]), bundle.request)
            assert bundle.task_id != plain.task_id
            assert bundle.reference_calls == plain.reference_calls


def test_every_stated_value_is_in_the_request_as_json() -> None:
    for label in ("acme-mcp", "petstore", "everything"):
        toolset, flows = fixture_sets()[label], flows_for(label)
        for spec in every_arm(toolset, flows):
            for seed in range(5):
                bundle = generator().generate(toolset, spec, seed, flows=flows)
                assert bundle.stated or spec.knob == "spread"
                for name, value in bundle.stated:
                    assert json.dumps(value) in bundle.request, (label, spec, name, value)


def test_only_the_first_sentence_of_a_description_is_used() -> None:
    toolset = mcp_set(
        write_tool("close_ticket", {"ticket": {"type": "string", "minLength": 6, "maxLength": 6}},
                   ["ticket"], description="Close a support ticket. Only staff may do this. It cannot be undone."),
        read_tool("peek_ticket", {"ticket": {"type": "string", "minLength": 6, "maxLength": 6}},
                  ["ticket"], description="Show a ticket. Read only."),
    )
    for seed in range(5):
        bundle = make(toolset, "faults", 0, seed=seed)
        assert "Close a support ticket" in bundle.request
        assert "Only staff may do this" not in bundle.request and "cannot be undone" not in bundle.request


def test_a_description_that_names_its_tool_does_not_put_the_name_in_the_request() -> None:
    toolset = mcp_set(
        write_tool("archive_ticket", {"ticket": {"type": "string", "minLength": 6, "maxLength": 6}},
                   ["ticket"], description="archive_ticket moves a ticket to the archive. It is final."),
        read_tool("peek_ticket", {"ticket": {"type": "string", "minLength": 6, "maxLength": 6}},
                  ["ticket"], description="Shows a ticket, unlike archive_ticket."),
    )
    for spec in every_arm(toolset):
        for seed in range(10):
            bundle = generator().generate(toolset, spec, seed)
            assert "archive_ticket" not in words(bundle.request), bundle.request
            assert "peek_ticket" not in words(bundle.request), bundle.request


def test_an_intent_for_a_tool_the_set_does_not_hold_is_refused() -> None:
    from tests.o2_support import arm

    with pytest.raises(ValueError):
        generator().generate(acme(), arm("faults", 0), 1, intents={"no_such_tool": "do a thing"})
