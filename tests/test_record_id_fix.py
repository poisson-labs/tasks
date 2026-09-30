"""The record-id fix: no record-id word is carried by a tool name, and knob R's top
contrast holds at every first word.

**The comparison that breaks.**  N7 holds the prompt-to-tool-name overlap *set* equal
across the arms of one knob, measured as a substring over the user
instruction's reference-tokenizer tokens.  Knob R's block loses read tools and gains
other classes' stage tools as `r` rises, so any instruction token some tool name carries
can enter or leave that set with the level.  Generation holds the set still in the three
places it has freedom -- the prompt's prose, the designated slots and the entry-code draw
(see `tasks.py`) -- and has none in the fourth: G14 makes the record id an injective function
of the task seed, so a seed whose **first** record-id word a tool name carries puts that
word into the set and `generate_contrast` refuses.  Six of the 512 words are carried by
some tool name and four of them refuse, all at `r14`, the one level whose block keeps no
orthogonal read tool at all: `city` (`eval`) at 60 of 60 seeds, `grad` and `port`
(`train`) at 60 of 60, and `disc` (`train`) at 43 of 60 (measured at 60 seeds per word;
`face` and `elect` refuse none, and nothing below `r14` refuses for any of the six).

**The fix.**  The table's coverage requirements, the entry-code draw's escape hatch and
the measurement all say the same thing: it closes outright the day a vocabulary version
draws its record-id word lists disjoint from every tool name.  `RI1` is that check -- a
one-time check nobody will think to run unless it is written down -- and `RI2` to `RI4`
are the comparison itself, at the contrast and the density first measured.

**Which of two counts this file is written against.**  The task layer's six design
choices can be counted two ways, and the counts differ by one: one counts the entry-code
draw, `tasks.py`'s docstring counts opaque slot values masked by slot name and documents
the draw under `_drawable_entry_codes` instead.  This file is written against **the six
that count the entry-code draw**.  The entry-code draw is the same invariant one table field
away -- *draw only from strings no tool name carries* -- and it is the rule this fix
generalises from the 32 entry codes to the 512 record-id words, so it is the shape `RI1`
stands beside and the docstring this fix has to rewrite.  The docstring's sixth, opaque
slot values, is about G15's fingerprint and not about N7's overlap set, and nothing here
reaches it.  Which count is the right one is not settled and is not settled here.

**Green before and after**: `RI5` alone.  It is a guard, not
coverage -- it holds on the table as frozen and on the revised one -- and it is here so
that the new coverage item cannot be met by breaking VT2's.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from poisson_tasks.engine import EngineSpec
from poisson_tasks.knobs import ArmSpec
from poisson_tasks.tasks import decode_record_id, encode_record_id, generate_contrast
from poisson_tasks.tokenizer import count_tokens

# --------------------------------------------------------------------------
# frozen literals
# --------------------------------------------------------------------------

DATA = pathlib.Path(__file__).resolve().parent.parent / "src" / "poisson_tasks" / "data"
TABLE_PATH = DATA / "vocabulary-v2.json"
TABLE = json.loads(TABLE_PATH.read_text())

SPLITS = ("eval", "train")
GEN_VERSION = "tg-m3-v1"

# The measured table: the six record-id words some tool name carries as a substring, and
# the four of them that refuse a knob R contrast holding `r14`.  Named here so that the
# fix is stated against the measurement it closes and not against itself.
CARRIED = {"eval": ("city", "face"), "train": ("disc", "elect", "grad", "port")}
REFUSING = {"eval": ("city",), "train": ("disc", "grad", "port")}

# The words this fix puts in their place, each drawn by the same rule the entry-code draw
# uses: a word no tool name carries.  Each is one token in every id position (VT2), sorts
# where the list it joins is sorted, and belongs to neither list already.
REPLACEMENTS = {
    "eval": {"city": "circle", "face": "email"},
    "train": {"disc": "disable", "elect": "east", "grad": "gray", "port": "point"},
}


def tool_names() -> tuple[str, ...]:
    return tuple(tool.name for tool in EngineSpec.load().tools)


def arms_r0_r14(split: str) -> tuple[ArmSpec, ...]:
    """Knob R's plain arms at `r0` and `r14`: the one contrast the four words refuse."""
    return tuple(
        ArmSpec(
            knob="distractor",
            level=level,
            control=None,
            strictness="strict",
            split=split,
            generator_version=GEN_VERSION,
        )
        for level in (0, 14)
    )


def first_word(seed: int, split: str) -> str:
    return encode_record_id(seed, split).split(TABLE["record_id_separator"])[0]


def word_seed(word: str, split: str, k: int = 0) -> int:
    """A seed whose first record-id word is `word`.  The id is base-256 in the list's
    order and the first word is the top digit, so the word's index shifted by 24 bits is
    the bottom of its range and `k` moves inside it."""
    index = TABLE["record_id_words"][split].index(word)
    return (index << 24) + k


def refusals(split: str, seeds: tuple[int, ...]) -> list[int]:
    """The seeds of `seeds` at which the `r0`-against-`r14` contrast is refused."""
    arms = arms_r0_r14(split)
    refused = []
    for seed in seeds:
        try:
            generate_contrast(arms, seed)
        except ValueError:
            refused.append(seed)
    return refused


def spaced(count: int, offset: int = 3) -> tuple[int, ...]:
    step = 2**32 // count
    return tuple((offset + i * step) % 2**32 for i in range(count))


SPREAD = (0, 1, 2, 55, 404, 2121, 65535, 2**24, 2**31 - 1, 2**32 - 1)


# ===========================================================================
# RI1 · the coverage item any future vocabulary version owes
# ===========================================================================


@pytest.mark.parametrize("split", SPLITS)
def test_ri1_no_record_id_word_is_carried_by_a_tool_name(split):
    """RI1: the coverage item, as a one-time check over the whole table.

    Stated over the whole list and not over the six the measurement names: a revision that
    swapped one collision for another would satisfy a test written about `city` and
    leave the gap open.
    """
    names = tool_names()
    carried = [
        (word, [name for name in names if word in name])
        for word in TABLE["record_id_words"][split]
        if any(word in name for name in names)
    ]
    assert carried == [], carried


def test_ri1_2_the_six_words_the_record_names_are_gone_and_their_places_are_filled():
    """RI1.2: the edit itself, against the measured table.

    `RI1` is the invariant and this is the change that establishes it, so a later reader
    can see which words moved without diffing the table.
    """
    for split in SPLITS:
        words = TABLE["record_id_words"][split]
        assert [w for w in CARRIED[split] if w in words] == []
        assert [w for w in REPLACEMENTS[split].values() if w not in words] == []


# ===========================================================================
# RI2-RI4 · the comparison, at the contrast and the densities first measured
# ===========================================================================


@pytest.mark.parametrize("split", SPLITS)
def test_ri2_the_top_contrast_holds_at_every_first_word(split):
    """RI2: `r0` against `r14`, four seeds inside each of the 256 first-word ranges.

    The gap is a property of the *first* word alone, so this is the whole of it: every
    word the id's top digit can take, and not a sample of words.
    """
    seeds = tuple(
        word_seed(word, split, k * 7919)
        for word in TABLE["record_id_words"][split]
        for k in range(4)
    )
    assert len(seeds) == 1024
    assert refusals(split, seeds) == []


@pytest.mark.parametrize("split", SPLITS)
def test_ri3_the_top_contrast_holds_across_a_dense_spread_with_nothing_excluded(split):
    """RI3: `test_ct5`'s shape (tests/test_tg_m5_scripted.py) with its exclusion removed.

    `test_ct5` drops the seeds whose first word is one of the four before it counts.
    This is the same spread with nothing dropped, which is what "the comparison is
    fixed" means for a caller who does not know the gap ever existed.
    """
    seeds = SPREAD + spaced(160)
    assert refusals(split, seeds) == []


@pytest.mark.parametrize("split", SPLITS)
def test_ri4_sixty_seeds_per_replaced_word_refuse_nothing(split):
    """RI4: the original measurement's density, over the words that took the six places.

    The original measurement took 60 seeds per word over this contrast and wrote the table
    `city` 60/60, `grad` 60/60, `port` 60/60, `disc` 43/60, `face` 0/60, `elect` 0/60.
    The same measurement over the replacements is the row that supersedes it.
    """
    table = {}
    for word in REPLACEMENTS[split].values():
        seeds = tuple(word_seed(word, split, k * 7919) for k in range(60))
        table[word] = len(refusals(split, seeds))
    assert table == dict.fromkeys(REPLACEMENTS[split].values(), 0), table


# ===========================================================================
# RI5 · the guard.  Green before and after: it holds on the frozen table too.
# ===========================================================================


def test_ri5_the_revised_lists_still_meet_vt2s_freeze():
    """RI5: 256 words a side, disjoint, unique, one token in every id position with and
    without a leading space, and `encode_record_id` still a bijection on the seed space.

    VT2 is written against the table as frozen.  The new coverage item is added to it
    rather than traded against it: a revision that made the lists disjoint from the tool
    names by taking a word that tokenizes as two would move G14's id out of the token
    band and break N6 two modules away.
    """
    lists = {split: TABLE["record_id_words"][split] for split in SPLITS}
    count = TABLE["record_id_word_count"]
    separator = TABLE["record_id_separator"]
    for words in lists.values():
        assert len(words) == len(set(words)) == 256
    assert set(lists["eval"]).isdisjoint(lists["train"])
    assert 256**count == 2**32
    for words in lists.values():
        filler = [words[(i * 61) % 256] for i in range(count)]
        for position in range(count):
            for word in words:
                parts = list(filler)
                parts[position] = word
                rid = separator.join(parts)
                assert count_tokens(rid) == count, (position, word, rid)
                assert count_tokens(" " + rid) == count, (position, word, rid)
    for split in SPLITS:
        for seed in SPREAD + spaced(64):
            assert decode_record_id(encode_record_id(seed, split), split) == seed
