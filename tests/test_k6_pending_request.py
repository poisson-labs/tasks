"""Pending a decision: how the request states a value.

**This file waits on a decision** and is its own commit, so if it is declined it is dropped whole.

The design gives the request's words by example only ("with lot code "x"..."), and says
the request states the values; the frozen tests hold every stated value to appear in the request
and no other of the six to be named there (`tests/test_k6_stated.py`), and a2's request to be B's
(`tests/test_k6_fixed.py`).  Recommended, from the design's example and the template's own rule for
the values a model copies (the record id and the entry code are in double quotes, which took model
A's first replies from asking for the values to making the call): B's request comes first,
unchanged, and after it each stated value appears once, in double quotes, directly after its
parameter's name in words (`lot code "amber"`), so a model reads which field takes which value as
it reads which record takes which code.  The sentence around them is the build's.  If the answer is
no, the request's form is the build's within the frozen tests, and this file is dropped.
"""

from __future__ import annotations

from tests.k3_support import made
from tests.k6_support import LEVELS, SPLITS, arm, base, in_words, request, stated


def test_b_s_request_comes_first_and_each_value_follows_its_name_in_quotes() -> None:
    for split, seeds in SPLITS:
        for seed in seeds:
            first = request(base(seed, split))
            for level in LEVELS:
                bundle = made(arm(level), seed, split)
                text = request(bundle)
                assert text.startswith(first), (level, seed, split)
                rest = text[len(first) :]
                for name, value in stated(bundle).items():
                    assert rest.count(f'{in_words(name)} "{value}"') == 1, (name, level, seed)
                    assert rest.count(f'"{value}"') == 1, (name, level, seed)
