"""Pending a decision: a named read answers with its part only when its arguments are exactly the
read's.

The design says `surface.py` answers the four reads "when the call names the read's facet, item and
page exactly; every other read, the same read on another page included, is the engine's"; it does
not say what a call naming them with something more, or in another case, is.  If the answer is yes,
a named read's tool called with any argument object other than exactly its item and its page is
the engine's: with a key more the engine answers `bad_args`, with the item in capitals
`no_such_item`, with a space after the page `no_such_page`; and a run's replay answers them so too,
so an episode holding such calls is not `replay_mismatch`.  Dropped if the answer is no: such a
call is then the build's to answer, inside the frozen tests (the named reads exactly as the
reference makes them answer with their parts; the same read on another page, with another item,
or by another tool is the engine's).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tests import k3_support as k3
from tests.k3_support import CARD_SEEDS, SPEC, status
from tests.k8_support import ITEM, LEVELS, PAGE, listed, spread


def near_misses(read: tuple[str, dict[str, Any]]) -> list[tuple[tuple[str, Any], str]]:
    name, args = read
    return [
        ((name, {**args, "note": "x"}), "bad_args"),
        ((name, {ITEM: args[ITEM].upper(), PAGE: args[PAGE]}), "no_such_item"),
        ((name, {ITEM: args[ITEM], PAGE: args[PAGE] + " "}), "no_such_page"),
    ]


def test_a_named_read_with_other_arguments_is_the_engines(tmp_path: Path) -> None:
    for seed in CARD_SEEDS[:3]:
        for level in LEVELS:
            bundle = spread(level, seed)
            mcp = k3.started(bundle)
            misses = [miss for read in listed(bundle) for miss in near_misses(read)]
            for (name, args), said in misses:
                assert status(k3.call(mcp, name, args)) == said, (name, args, level, seed)
            stages = [(str(n), dict(a)) for n, a in bundle.reference_calls if n in SPEC.stage_tools]
            calls = [call for call, _said in misses] + stages
            sent = k3.answers(bundle, calls)
            (record,) = k3.records_of(tmp_path, k3.trace_of(bundle, calls, sent))
            assert record.label == "passed", (record.label, level, seed)
