"""Pending a yes/no: how an information-spread request is worded, and its slots.

Spec §14.4 names the template (`ledger-spread/v1`), says the request names four reads by item, facet
and page, gives its two sentences ("The entry code is split across the answers of these four
reads, in the order listed: join the parts. An answer that holds no part reads `none`."), and says
the request describes the answer's shape; it gives no other words.  If the answer is yes, the
request is B's first three lines, then `The four reads:`, then one line per named read in the
listed order, `<n>. the <facet> field of catalogue item "<item>" on page "<page>"` (the facet as
the engine's own read describes it, the item and the page in double quotes as B quotes the record
id), then the spec's two sentences on one line, then `Each answer's payload is its part, a full
stop, then filler.`, then B's last line with the code taken out: `Open with the joined entry code;
each later stage needs what the stage before returned.`  The slots are B's but the entry code, in
B's order, and then the four read lines in a slot of the knob's own, `named_reads`.  Dropped if the
answer is no: the words and the slots are then the build's, inside the frozen tests (four reads
named, each on its own line; spec §14.4's sentences; no entry code stated; every line of B's but
the code's kept), and nothing then pins that the request describes the answer's shape, which spec
§14.4 asks for in no words of its own.
"""

from __future__ import annotations

from tests.k3_support import SPEC
from tests.k8_support import ITEM, LEVELS, PAGE, SENTENCE, SPLITS, base, listed, request, spread

SLOTS = ("record_id", "ledger_class", "stage_ladder", "goal_stage", "named_reads")


def test_the_request_is_bs_lines_the_reads_the_sentences_and_bs_last_line_less_the_code() -> None:
    for split, seeds in SPLITS:
        for seed in seeds:
            b_lines = request(base(seed, split)).split("\n")
            b_slots = dict(base(seed, split).prompt_slots)
            for level in LEVELS:
                bundle = spread(level, seed, split)
                where = (level, seed, split)
                reads = [
                    f'{index}. the {SPEC.read_tools[name]} field of catalogue item "{args[ITEM]}" '
                    f'on page "{args[PAGE]}"'
                    for index, (name, args) in enumerate(listed(bundle), start=1)
                ]
                assert request(bundle).split("\n") == [
                    *b_lines[:3],
                    "The four reads:",
                    *reads,
                    SENTENCE,
                    "Each answer's payload is its part, a full stop, then filler.",
                    "Open with the joined entry code; each later stage needs what the stage "
                    "before returned.",
                ], where
                assert tuple(name for name, _value in bundle.prompt_slots) == SLOTS, where
                slots = dict(bundle.prompt_slots)
                assert {name: slots[name] for name in SLOTS[:-1]} == {
                    name: b_slots[name] for name in SLOTS[:-1]
                }, where
                assert slots["named_reads"] == "\n".join(reads), where
