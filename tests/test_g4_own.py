"""Spread on a user's own tools from 0.5.0: an answer that holds no part holds nothing in its field,
frozen as tests.

The own-tools generator had the defect the built-in one had: at level P, the 4 - P named reads that
hold no part of the split value answered `"none"` in the field a part goes in, and the request said
so and never said to leave it out.  Ruled 2026-11-15: own tools get the same fix in the same change,
and the own-tools label moves to `"own-4"`.

An own-tools answer is the tool's own JSON, not the built-in ledger's line: it has a field, and no
full stop and no filler.  So the built-in invariants are read here as what they mean for a field.

Shapes decided here
-------------------

**1. An answer that holds no part** (the built-in "starts with its full stop") is a named read
whose field holds the empty string.  On each of the six fixture sets, at thirteen seeds and at the
three levels a set reaches, exactly 4 - P of the four named reads' fields are empty, in the
reference and in what the simulator answers; `none` is the value of no named read's field.

**2. The request** (the built-in "the new sentence, and the same at every level") no longer says
that an answer that holds no part reads `"none"`, and `none` is no word of it.  The request, the
prompt, the block and the reference's calls are the same at levels 1, 2 and 4.  What the new
sentence says, word for word, the design gives for the built-in request only; the own-tools words
are pending a decision (`tests/test_g4_pending_own_wording.py`).

**3. The join** (the built-in "joining the four heads gives the entry code"): the four fields
joined in the listed order, the empty ones included, are the value the target call carries, at
every level; the reference, which carries it, is `passed`.

**4. A join that keeps anything else is refused** (the built-in "a join that keeps filler"): the
target call carrying the four answers joined whole, or the value followed by the first answer
whole, is not `passed`, strict or leaky.  So is the join the old defect produced, the parts with
`none` for each answer that holds none (below level 4): the word is gone from the answers, and a
call that carries it is still wrong.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from tests.g4_support import MARKER, READS
from tests.o2_support import answers, arm, fixture_sets, flows_for, generator, judge
from tests.k8_support import words

SETS = ("acme-mcp", "acme-openai", "acme-openapi-3.0", "acme-openapi-3.1", "petstore", "everything")
SEEDS = (404, 55, 2121, *range(10))
OWN_LEVELS = (1, 2, 4)
OLD_SENTENCE = 'An answer that holds no part reads "none".'


def made(label: str, level: int, seed: int) -> Any:
    return generator().generate(
        fixture_sets()[label], arm("spread", level), seed, flows=flows_for(label)
    )


def field_value(text: str, path: str) -> Any:
    node: Any = json.loads(text)
    for part in path.split("."):
        node = node[part.removesuffix("[]")]
        if part.endswith("[]"):
            node = node[0]
    return node


def held(bundle: Any, texts: Any) -> list[Any]:
    """What each named read's field holds in `texts`, the answers to the four reads in order."""
    return [
        field_value(text, path)
        for text, (_tool, _args, path) in zip(texts, bundle.named_reads, strict=True)
    ]


def carried(bundle: Any) -> tuple[str, dict[str, Any], str]:
    """The target call, and the one argument of it that carries the split value."""
    name, args = bundle.reference_calls[-1]
    value = "".join(held(bundle, bundle.reference_observations[:READS]))
    (argument,) = [key for key, given in args.items() if given == value]
    return str(name), dict(args), argument


def test_every_fixture_set_reaches_spread_at_levels_1_2_and_4() -> None:
    assert tuple(sorted(fixture_sets())) == tuple(sorted(SETS))
    for label in SETS:
        levels = generator().knob_levels(fixture_sets()[label], "spread", flows=flows_for(label))
        assert tuple(levels) == OWN_LEVELS, label


@pytest.mark.parametrize("label", SETS)
def test_a_read_that_holds_no_part_answers_with_an_empty_field(label: str) -> None:
    """Shape 1."""
    for seed in SEEDS:
        for level in OWN_LEVELS:
            bundle = made(label, level, seed)
            where = (label, level, seed)
            assert len(bundle.named_reads) == READS, where
            reads = bundle.reference_calls[:READS]
            assert [(name, dict(args)) for name, args in reads] == [
                (name, dict(args)) for name, args, _path in bundle.named_reads
            ], where
            in_reference = held(bundle, bundle.reference_observations[:READS])
            live = held(bundle, [answer.text for answer in answers(bundle, reads)])
            assert live == in_reference, where
            assert all(isinstance(value, str) for value in in_reference), (in_reference, *where)
            assert sum(value == "" for value in in_reference) == READS - level, (
                in_reference,
                *where,
            )
            assert MARKER not in in_reference, (in_reference, *where)


@pytest.mark.parametrize("label", SETS)
def test_the_request_is_one_at_every_level_and_says_none_nowhere(label: str) -> None:
    """Shape 2."""
    for seed in SEEDS:
        bundles = [made(label, level, seed) for level in OWN_LEVELS]
        where = (label, seed)
        for bundle in bundles:
            assert OLD_SENTENCE not in bundle.request, where
            assert f'"{MARKER}"' not in bundle.request, where
            assert MARKER not in words(bundle.request), where
        first = bundles[0]
        for bundle in bundles[1:]:
            assert bundle.request.encode("utf-8") == first.request.encode("utf-8"), where
            assert bundle.prompt == first.prompt, where
            assert bundle.tools == first.tools, where
            assert bundle.reference_calls == first.reference_calls, where


@pytest.mark.parametrize("label", SETS)
def test_the_fields_joined_are_the_value_the_target_call_carries(label: str) -> None:
    """Shape 3."""
    for seed in SEEDS:
        for level in OWN_LEVELS:
            bundle = made(label, level, seed)
            where = (label, level, seed)
            parts = held(bundle, bundle.reference_observations[:READS])
            _name, args, argument = carried(bundle)
            assert "".join(parts) == args[argument], (parts, *where)
            assert [part for part in parts if part] == parts[: level], (parts, *where)
            assert len(bundle.reference_calls) == READS + 1, where
            found = judge(bundle, bundle.reference_calls)
            assert (found.label, found.strict_label, found.leaky_pass) == (
                "passed", "passed", True), where


@pytest.mark.parametrize("label", SETS)
def test_a_join_that_keeps_anything_else_of_an_answer_is_not_passed(label: str) -> None:
    """Shape 4."""
    for seed in SEEDS:
        for level in OWN_LEVELS:
            bundle = made(label, level, seed)
            where = (label, level, seed)
            texts = list(bundle.reference_observations[:READS])
            parts = held(bundle, texts)
            name, args, argument = carried(bundle)
            value = args[argument]
            wrong = {
                "the answers whole": "".join(texts),
                "the value and the first answer whole": value + texts[0],
            }
            if level < READS:
                wrong["the parts with none for each empty answer"] = "".join(
                    part or MARKER for part in parts
                )
            assert len(wrong) == (3 if level < READS else 2), where
            for said, join in wrong.items():
                assert join != value, (said, *where)
                calls = [*bundle.reference_calls[:READS], (name, {**args, argument: join})]
                found = judge(bundle, calls)
                assert found.label != "passed" and found.strict_label != "passed", (said, *where)
                assert found.leaky_pass is False, (said, *where)
