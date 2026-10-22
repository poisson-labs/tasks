"""The block-size knob's aliased read copies: their names, their words, and what answers them,
frozen as tests.

Past the table's sixteen reads
a block is filled with copies: each is named `{verb}_{facet}` for a read verb and a facet of the
table that no engine read already pairs, is described in its own words, and answers exactly as the
engine's read of its facet, through `surface.display_map`, which the verifier, the generator and
the tool server all read.  No name repeats in a block (`tests/test_k5_block.py`).

Shapes decided here
-------------------

**1. The copy's own words are pinned by what they must do, not by their spelling.**  The design
gives the description as "{Verb}s the {facet} field of the named catalogue item", which reads
badly for some of the table's verbs (`lookup`, `match`, `search`); the words are the build's.
Pinned: the description names its facet, is not the engine read's own, and no two tools of one
block share a description, so two copies of one facet are told apart by their words as by their
names.  Every engine tool in the block keeps its own name, description and parameters, and a copy
takes its read's parameters.

**2. "Answers exactly as the engine read of its facet" is measured at the tool server**, the one
place a copy's answer reaches a model: started as a launched server is, it advertises the bundle's
block byte for byte (X3), answers the reference calls with the reference observations, and answers
every copy in the block with the line the engine's read of that facet gives at that point of the
episode, `seq` included.  The run's replay check reads the same map
(`tests/test_k5_records.py`).
"""

from __future__ import annotations

from typing import Any

import pytest

from poisson_tasks.engine import apply, init_state, replay
from poisson_tasks.tasks import scenario_for
from tests.k3_support import SPEC, call, names, run, started, status
from tests.k5_support import (
    CARD_SEEDS,
    ENGINE_TOOLS,
    SPLITS,
    block,
    copies,
    engine_schema,
    pair_of,
    read_of,
)

ITEM = str(SPEC.parameter_names["item"])
PAGE = str(SPEC.parameter_names["page"])
OWN = {tool.name: tool.description for tool in SPEC.tools}


def test_each_copy_is_a_pair_the_table_does_not_name_with_its_reads_schema_and_own_words() -> None:
    """At k64, whose block holds every lower level's (`tests/test_k5_block.py`)."""
    for split, seeds in SPLITS:
        for seed in seeds:
            bundle = block(64, seed, split)
            described = [str(tool["description"]) for tool in bundle.tools]
            assert len(set(described)) == len(described), (seed, split)
            for tool in bundle.tools:
                name = str(tool["name"])
                if name in ENGINE_TOOLS:
                    assert (tool["description"], tool["parameters"]) == (
                        OWN[name],
                        engine_schema(name),
                    ), (name, seed, split)
                    continue
                pair = pair_of(name)
                assert pair is not None, (name, seed, split)
                _verb, facet = pair
                read = read_of(facet)
                assert tool["parameters"] == engine_schema(read), (name, seed, split)
                assert facet in str(tool["description"]), (name, tool["description"])
                assert tool["description"] != OWN[read], (name, seed, split)
            assert copies(bundle), (seed, split)


def ok_args(read: str, skip: int) -> dict[str, str]:
    """Arguments the engine answers `ok` for `read`, the `skip`-th such pair of item and page, so
    the copies of one episode are asked about different items."""
    scenario = scenario_for(0, "eval")
    state = init_state(scenario, 1)
    found = 0
    for item in scenario.visible_items:
        for page in sorted(SPEC.page_keys):
            args = {ITEM: item, PAGE: page}
            if apply(state, (read, args))[1].split()[1] == "ok":
                if found == skip:
                    return args
                found += 1
    raise AssertionError(f"{read} answers ok for fewer than {skip + 1} items")


@pytest.mark.parametrize("seed", [CARD_SEEDS[0], CARD_SEEDS[19], CARD_SEEDS[42]])
def test_the_tool_server_offers_the_block_and_answers_each_copy_as_its_facets_read(
    seed: int,
) -> None:
    bundle = block(64, seed)
    mcp = started(bundle)
    listed = run(mcp.list_tools())
    assert [t.name for t in listed] == list(names(bundle))
    assert [t.description for t in listed] == [t["description"] for t in bundle.tools]
    assert [t.inputSchema for t in listed] == [t["parameters"] for t in bundle.tools]

    reference = [(str(name), dict(args)) for name, args in bundle.reference_calls]
    asked: list[tuple[str, Any]] = []
    behind: list[tuple[str, Any]] = []
    for index, name in enumerate(copies(bundle)):
        pair = pair_of(name)
        assert pair is not None, name
        read = read_of(pair[1])
        args = ok_args(read, index % 3)
        asked.append((name, args))
        behind.append((read, args))
    sent = [call(mcp, name, args) for name, args in reference + asked]
    _state, expected = replay(
        scenario_for(bundle.seed, bundle.split), reference + behind, bundle.seq_start
    )
    assert sent[: len(reference)] == list(bundle.reference_observations)
    assert sent == list(expected)
    assert {status(line) for line in sent[len(reference) :]} == {"ok"}
