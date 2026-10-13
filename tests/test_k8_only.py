"""Only the four named reads answer with parts, everywhere a task is answered: the tool server, and
a run's replay, frozen as tests.

The invariant is K8.3 of the knobs plan, from spec §14.4: `surface.py` answers exactly the four
named reads, matched on facet, item and page; every other read, the same read on another page
included, is the engine's.  With it, Taylor's standing ruling for a knob that gains tasks: when a
run's records are read, the calls that reached the tool server are replayed and a disagreement is
`replay_mismatch`, which scores nothing; the tool server, `verify` and the run's replay agree.
The stage-1 tool's description is K8.3's other half, held with the block in
`tests/test_k8_fixed.py`.

Shapes decided here
-------------------

**1. The tool server** of a spread task answers each named read with the payload the reference
holds for it, `ok`, at the server's own `seq`, whichever order the reads come in and however often
one is made.  The engine answers every other read: the same tool and item on another page, the
same tool and page with another item, and another named read's tool on this one's item and page,
each with the catalogue's own value for the item and the facet.  At every level the generator can
build, at six card seeds.  Whether a named read with any other argument object (a key more, a
value in another case) is the engine's is pending a yes/no (`tests/test_k8_pending_exact.py`).

**2. The run's replay**: an episode whose tool messages are the server's answers (a read on another
page first, the named reads in reverse order, one of them again, then the reference's two stage
calls) reads back as `passed`, so the replay answered every read as the server did; the same
episode with a named read's message replaced by the engine's value for it, or with the read on
another page answered by a named read's payload, reads back as `replay_mismatch`.  At every level,
at two card seeds.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tests import k3_support as k3
from tests.k3_support import CARD_SEEDS, SPEC, seq, status
from tests.k8_support import (
    ITEM,
    LEVELS,
    PAGE,
    Read,
    answers,
    catalogue_value,
    key,
    listed,
    payload,
    spread,
)

PAGES = sorted(SPEC.page_keys)
ITEMS = list(SPEC.table["catalogue_items"])


def other(values: list[str], taken: str) -> str:
    return next(value for value in values if value != taken)


def elsewhere(bundle: Any, read: Read) -> list[Read]:
    """Reads the engine answers: the read on another page, the read with another item, and every
    other named read's tool on this read's item and page, leaving out any that is a named read."""
    name, args = read
    tools = sorted({tool for tool, _args in listed(bundle)} - {name})
    found = answers(bundle)
    return [
        candidate
        for candidate in [
            (name, {ITEM: args[ITEM], PAGE: other(PAGES, args[PAGE])}),
            (name, {ITEM: other(ITEMS, args[ITEM]), PAGE: args[PAGE]}),
            *[(tool, dict(args)) for tool in tools],
        ]
        if key(candidate) not in found
    ]


def test_the_server_answers_the_four_named_reads_and_the_engine_every_other() -> None:
    """Shape 1."""
    for seed in CARD_SEEDS[:6]:
        for level in LEVELS:
            bundle = spread(level, seed)
            where = (level, seed)
            reads = listed(bundle)
            found = answers(bundle)
            mcp = k3.started(bundle)
            made = bundle.seq_start
            for name, args in [*reversed(reads), *reads, reads[0]]:
                line = k3.call(mcp, name, args)
                assert (status(line), seq(line)) == ("ok", made), (line, *where)
                assert payload(line) == payload(found[key((name, args))]), (line, *where)
                made += 1
            for read in reads:
                for name, args in elsewhere(bundle, read):
                    line = k3.call(mcp, name, args)
                    assert (status(line), seq(line)) == ("ok", made), (line, *where)
                    assert payload(line) == catalogue_value((name, args)), (line, *where)
                    made += 1


def episode_calls(bundle: Any) -> list[tuple[str, Any]]:
    reads = listed(bundle)
    stages = [(str(n), dict(a)) for n, a in bundle.reference_calls if n in SPEC.stage_tools]
    return [elsewhere(bundle, reads[0])[0], *reversed(reads), reads[1], *stages]


def test_a_runs_replay_answers_every_read_as_the_server_did(tmp_path: Path) -> None:
    """Shape 2."""
    for seed in CARD_SEEDS[:2]:
        for level in LEVELS:
            bundle = spread(level, seed)
            where = (level, seed)
            calls = episode_calls(bundle)
            sent = k3.answers(bundle, calls)
            (record,) = k3.records_of(tmp_path, k3.trace_of(bundle, calls, sent))
            assert (record.label, record.strict, record.leaky) == ("passed", True, True), where

            named_at = 1
            engine_said = list(sent)
            line = sent[named_at]
            engine_said[named_at] = line[: -len(payload(line))] + catalogue_value(calls[named_at])
            part_said = list(sent)
            part_said[0] = sent[0][: -len(payload(sent[0]))] + payload(sent[named_at])
            for planted in (engine_said, part_said):
                (changed,) = k3.records_of(tmp_path, k3.trace_of(bundle, calls, planted))
                assert (changed.label, changed.strict, changed.leaky) == (
                    "replay_mismatch",
                    False,
                    False,
                ), where
