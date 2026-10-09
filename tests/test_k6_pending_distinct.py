"""Pending a yes/no: the stated values are told apart from one another and from the request's other
values.

**This file waits on a yes/no** and is its own commit, so a "no" drops it whole.

Plan K6.2 and the ledger's N31 hold each stated value to an opaque word no tool name carries; they
say nothing of two values being the same word, or of a value being the request's record id, a word
of it, or its entry code.  Recommended: the six values a task draws are six different words, none
of them the entry code, the record id or one of the record id's words, so a call that put a value
in the wrong field, or the record's own words in a field, is wrong in a way the check can see, and
no level asks a model to tell two equal strings apart.  If the answer is no, a task may state one
word twice or reuse a word of the record id, and this file is dropped.
"""

from __future__ import annotations

from tests.k3_support import SPEC
from tests.k6_support import SPLITS, arguments, base, stated

ENTRY = str(SPEC.parameter_names["entry"])
RECORD = str(SPEC.parameter_names["record"])
SEPARATOR = str(SPEC.table["record_id_separator"])


def test_the_six_values_are_six_words_none_the_records_or_its_codes() -> None:
    for split, seeds in SPLITS:
        for seed in seeds:
            values = list(stated(arguments(8, seed, split)).values())
            assert len(values) == len(set(values)) == 6, (seed, split, values)
            first_call = base(seed, split).reference_calls[0][1]
            record, code = str(first_call[RECORD]), str(first_call[ENTRY])
            taken = {record, code, *record.split(SEPARATOR)}
            assert not taken & set(values), (seed, split, taken & set(values))
