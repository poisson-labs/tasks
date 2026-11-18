"""What the generator-4 test files share: the sentence 0.5.0 gives the spread request, the marker
it takes out of the answers, and the levels and seeds the files read.

The test files are `tests/test_g4_*.py`; each says in its own docstring what it pins and what it
decided.  Nothing here asserts anything.

0.5.0 changes one thing about a spread task (ruled 2026-11-15).  Until then an answer that held no
part of the entry code said `none` where a part goes; the request said so, and never said to leave
the word out, and entry codes are English words, so a model joined it into the code.  From 0.5.0
such an answer has nothing before its full stop, and the request says to leave it out.  The change
moves the built-in generator to the label `"4"` and the own-tools one to `"own-4"`.

The literals here are this release's own and are held apart from `tests/k8_support.py`'s, which
were written for the first design and are retrofitted to the new one: a file here that read them
would follow whatever they said.
"""

from __future__ import annotations

from typing import Any

from tests.k8_support import answers, head_and_fill, key, listed, payload

# The sentence about an answer that holds no part, word for word, and the line it ends.
NO_PART_SENTENCE = "An answer that holds no part has nothing before its full stop: leave it out."
SENTENCE = (
    "The entry code is split across the answers of these four reads, in the order listed: join "
    "the parts. " + NO_PART_SENTENCE
)
# What 0.4.2 said in its place, and the word its no-part answers carried.
OLD_NO_PART_SENTENCE = "An answer that holds no part reads `none`."
OLD_SENTENCE = (
    "The entry code is split across the answers of these four reads, in the order listed: join "
    "the parts. " + OLD_NO_PART_SENTENCE
)
MARKER = "none"
STOP = "."
HEX = frozenset("0123456789abcdef")
READS = 4
# The levels a card measures, and every level the generator can build.
CARD_LEVELS = (1, 2, 4)
LEVELS = (1, 2, 3, 4)

# The labels, and the generators' hashes at 0.4.2 (`"3"` and `"own-3"`), which no 0.5.0 tree makes.
BUILT_IN_LABEL = "4"
OWN_LABEL = "own-4"
BUILT_IN_LABEL_BEFORE = "3"
OWN_LABEL_BEFORE = "own-3"
RELEASE = "0.5.0"
BUILT_IN_HASH_BEFORE = "38a8db83a79c9d42059b77a3ef5ba018ec715fff9dcfda3c146ad27d8ba2921c"
OWN_HASH_BEFORE = "f941d7f8d7ae1694bac834f705c9283471fc65665a467ea9e717a8c6a395933a"


def payloads(bundle: Any) -> list[str]:
    """The named reads' payloads in the reference, in the order the request lists the reads."""
    found = answers(bundle)
    return [payload(found[key(read)]) for read in listed(bundle)]


def lines(bundle: Any) -> list[str]:
    """The named reads' whole answer lines in the reference, in the listed order."""
    found = answers(bundle)
    return [found[key(read)] for read in listed(bundle)]


def split_payloads(bundle: Any) -> list[tuple[str, str]]:
    """Each named read's payload as its head and its fill, in the listed order."""
    return [head_and_fill(text) for text in payloads(bundle)]


def holds_no_part(text: str) -> bool:
    """Whether a payload is one that holds no part: nothing comes before its full stop."""
    return text.startswith(STOP)
