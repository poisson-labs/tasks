"""What the four named reads answer at each information-spread level: the entry code in parts,
frozen as tests.

It rests on the pin ledger's N35 and N8.  At level P
exactly P of the four answers carry a non-empty part, in order, joining to the scenario's entry
code, split as evenly as possible with the earlier parts longer; the rest answer `none`; each
payload is the part (or `none`), a `.` and keyed hex to 32 bytes; every such answer is `L_obs`
bytes with its tokens inside N8's band (`outputs/spread_payload.txt` measured 16 to 27 over every
drawable code and level, inside 14 to 35).

Shapes decided here
-------------------

**1. An answer** is the named read's observation in the reference: the engine's layout (`L_obs`
bytes, its `seq` the reference's own count from `seq_start`, the status `ok`), and a payload as wide
as the table's payload field, whose head is what comes before its first full stop and whose fill
is what comes after it.  The fill is lowercase hex, at least one character, and is keyed: across
the card seeds of a split the first listed read's fill takes more than one value, so it is no
constant (zeros would look like the engine's error payload).

**2. The parts**: in the order the request lists the reads (`tests/k8_support.py`), exactly P heads
are not `none`, and those P, in that order, are the entry code split into P parts as evenly as it
goes, the earlier parts longer; every other head is `none`.  At every level the generator can
build, the card's three and 3 between them.  Which of the four carry the parts is pending a decision
(`tests/test_k8_pending_parts.py`); how the fill is keyed is another
(`tests/test_k8_pending_fill.py`).

**3. N8**: every answer's reference-token count is inside the table's band, at the card seeds and,
because the card seeds draw thirty of the thirty-one entry codes the generator can draw (`type`
is never drawn), also at one eval seed for every code no tool name carries, the codes the
scenario draws from (the design's measurement claims every code at every level).
"""

from __future__ import annotations

from poisson_tasks.tasks import scenario_for
from poisson_tasks.tokenizer import count_tokens
from tests.k3_support import SPEC, seq, status
from tests.k8_support import (
    LEVELS,
    NONE,
    SPLITS,
    answers,
    entry_code,
    head_and_fill,
    heads,
    key,
    listed,
    parts,
    payload,
    spread,
)

LOW, HIGH = SPEC.table["token_band"]
WIDTH = SPEC.layout["payload_width"]
HEX = set("0123456789abcdef")


def test_every_answer_is_the_engines_layout_with_a_head_a_stop_and_keyed_hex() -> None:
    """Shapes 1 and 3."""
    for split, seeds in SPLITS:
        first_fills = set()
        for seed in seeds:
            for level in LEVELS:
                bundle = spread(level, seed, split)
                where = (level, seed, split)
                found = answers(bundle)
                positions = {
                    key((str(name), dict(args))): index
                    for index, (name, args) in enumerate(bundle.reference_calls)
                }
                for read in listed(bundle):
                    observation = found[key(read)]
                    assert len(observation.encode("utf-8")) == SPEC.L_obs, (observation, *where)
                    assert status(observation) == "ok", (observation, *where)
                    assert seq(observation) == bundle.seq_start + positions[key(read)], where
                    assert LOW <= count_tokens(observation) <= HIGH, (observation, *where)
                    text = payload(observation)
                    assert len(text) == WIDTH, (text, *where)
                    head, fill = head_and_fill(text)
                    assert head and fill and set(fill) <= HEX, (text, *where)
                first = payload(found[key(listed(bundle)[0])])
                first_fills.add(head_and_fill(first)[1][:8])
        assert len(first_fills) > 1, split


def test_exactly_the_levels_parts_in_order_join_to_the_code_and_the_rest_read_none() -> None:
    """Shape 2."""
    for split, seeds in SPLITS:
        for seed in seeds:
            for level in LEVELS:
                bundle = spread(level, seed, split)
                where = (level, seed, split)
                said = heads(bundle)
                held = [head for head in said if head != NONE]
                assert held == parts(entry_code(bundle), level), (said, *where)
                assert said.count(NONE) == len(said) - level, (said, *where)


def a_seed_for_every_code() -> dict[str, int]:
    """The first eval seed drawing each entry code no tool name carries."""
    tools = [tool.name for tool in SPEC.tools]
    codes = {c for c in SPEC.table["entry_codes"] if not any(c in name for name in tools)}
    found: dict[str, int] = {}
    seed = 0
    while set(found) != codes:
        (code,) = set(scenario_for(seed, "eval").records.values())
        found.setdefault(str(code), seed)
        seed += 1
    return found


def test_every_drawable_code_answers_inside_the_band_at_every_level() -> None:
    """Shapes 2 and 3, over the codes."""
    for code, seed in sorted(a_seed_for_every_code().items()):
        for level in LEVELS:
            bundle = spread(level, seed)
            where = (code, level, seed)
            for observation in answers(bundle).values():
                assert len(observation.encode("utf-8")) == SPEC.L_obs, (observation, *where)
                assert LOW <= count_tokens(observation) <= HIGH, (observation, *where)
            assert [h for h in heads(bundle) if h != NONE] == parts(code, level), where
