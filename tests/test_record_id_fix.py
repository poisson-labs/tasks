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
one-time check nobody will think to run unless it is written down -- and `RI2`
is the comparison itself, at every first word.  Vocabulary v2 draws the lists that way:
`city` and `face` left `eval`, `disc`, `elect`, `grad` and `port` left `train`, and
`circle`, `email`, `disable`, `east`, `gray` and `point` took their places.

**Which of two counts this file is written against.**  The task layer's six design
choices can be counted two ways, and the counts differ by one: one counts the entry-code
draw, `tasks.py`'s docstring counts opaque slot values masked by slot name and documents
the draw under `_drawable_entry_codes` instead.  This file is written against **the six
that count the entry-code draw**.  The entry-code draw is the same invariant one table field
away -- *draw only from strings no tool name carries* -- and it is the rule this fix
generalises from the 32 entry codes to the 512 record-id words, so it is the shape `RI1`
stands beside.  The docstring's sixth, opaque slot values, is about G15's fingerprint
and not about N7's overlap set, and nothing here reaches it.

The lists' own shape -- 256 words a side, disjoint, one token in every id position -- is
VT2's, in the engine tests, and the round trip is G14's, in the task tests.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from poisson_tasks.engine import EngineSpec
from poisson_tasks.knobs import ArmSpec, levels
from poisson_tasks.tasks import generate_contrast

# --------------------------------------------------------------------------
# the literals these tests pin
# --------------------------------------------------------------------------

DATA = pathlib.Path(__file__).resolve().parent.parent / "src" / "poisson_tasks" / "data"
TABLE_PATH = DATA / "vocabulary-v2.json"
TABLE = json.loads(TABLE_PATH.read_text())

SPLITS = ("eval", "train")
GEN_VERSION = "tg-m3-v1"

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


# ===========================================================================
# RI1 · the coverage item every vocabulary version must meet
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


# ===========================================================================
# RI2 · the comparison, at every first word
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


# ===========================================================================
# CT · every registered arm of a knob in one contrast, across the seed space
#
# The task-layer tests build one knob R contrast, `r0` against `r8`, at three seeds.  These
# run every arm of a knob at once -- each level and both control arms, the arm sets a sweep
# registers -- over a spread of the 32-bit seed space, so a level or a control that broke the
# pin ledger at some seed would refuse here.  They need no adapter, so they run without
# Proofload.
# ===========================================================================

D_CONTROLS = ((1, 8), (2, 5))
R_CONTROLS = ((0, 8), (2, 14))
SPREAD = (0, 1, 2, 55, 404, 2121, 65535, 2**24, 2**31 - 1, 2**32 - 1)
SPACED = tuple((7 + i * (2**32 // 24)) % 2**32 for i in range(24))


def registered_arms(knob: str, controls: tuple[tuple[int, int], ...]) -> tuple[ArmSpec, ...]:
    def arm(level: int, control: int | None) -> ArmSpec:
        return ArmSpec(knob=knob, level=level, control=control, strictness="strict",
                       split="eval", generator_version="0")

    return tuple(arm(level, None) for level in levels(knob)) + tuple(
        arm(level, control) for level, control in controls)


def contrast_ok(arms: tuple[ArmSpec, ...], seeds: tuple[int, ...]) -> int:
    made = 0
    for seed in seeds:
        generate_contrast(arms, seed)  # raises ValueError if the ledger refuses
        made += 1
    return made


def test_ct1_every_registered_depth_arm_holds_the_ledger_across_the_seed_space():
    arms = registered_arms("depth", D_CONTROLS)
    assert len(arms) == 7
    assert contrast_ok(arms, SPREAD + SPACED) == len(SPREAD + SPACED)


def test_ct2_every_registered_distractor_arm_holds_the_ledger_across_the_seed_space():
    """Every level `r0` to `r14` and both controls at once: nothing here is one pair."""
    arms = registered_arms("distractor", R_CONTROLS)
    assert len(arms) == 7
    assert contrast_ok(arms, SPREAD + SPACED) == len(SPREAD + SPACED)
