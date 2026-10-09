"""What the information-spread knob's test files share: the arms and seeds they read, the base task
they compare with, and a task's named reads and their answers read back from its fields.

The test files are `tests/test_k8_*.py`; each says in its own docstring what it pins and what it
decided.  Nothing here asserts anything.  The tool server, the trace writer and the record reader
are the faults knob's (`tests/k3_support.py`), unchanged.

A task's named reads are the read calls its reference makes (the ledger's N35 measures them so):
each a read tool's name with an item and a page.  The order the request lists them in is read off
the request: each named read is on a line of its own that names its facet, its item and its page,
and the lines' order is the listed order (`listed`).  A read's answer is its observation in the
reference; its payload is the observation's third field, a head (the part, or `none`), a full
stop and a fill.
"""

from __future__ import annotations

import json
import re
from typing import Any

from poisson_tasks.tasks import TaskBundle, scenario_for
from tests.k3_support import B_ARM, SPEC, made
from tests.k3_support import CARD_SEEDS as CARD_SEEDS

# The card's levels, and the one level between them the generator can build and no card measures:
# a spread level is how many of the four named reads answer with a part, from 1 to 4 (spec §3.2).
CARD_LEVELS = (1, 2, 4)
LEVELS = (1, 2, 3, 4)
READS = 4
TEMPLATE_ID = "ledger-spread/v1"
# Spec §14.4's two sentences, as the spec prints them.
SENTENCE = (
    "The entry code is split across the answers of these four reads, in the order listed: join "
    "the parts. An answer that holds no part reads `none`."
)
NONE = "none"
STOP = "."
# A spread task costs a few milliseconds to generate, so both splits are read at every card seed.
SPLITS: tuple[tuple[str, tuple[int, ...]], ...] = (("eval", CARD_SEEDS), ("train", CARD_SEEDS))
ITEM = str(SPEC.parameter_names["item"])
PAGE = str(SPEC.parameter_names["page"])


def arm(level: int) -> str:
    return f"spread:p{level}"


ARMS = tuple(arm(level) for level in LEVELS)


def spread(level: int, seed: int, split: str = "eval") -> TaskBundle:
    return made(arm(level), seed, split)


def base(seed: int, split: str = "eval") -> TaskBundle:
    """B, the base task (`distractor:r0@k16`)."""
    return made(B_ARM, seed, split)


def request(bundle: Any) -> str:
    """The user request: the prompt, which no spread arm seeds."""
    return bundle.prompt if isinstance(bundle.prompt, str) else str(bundle.prompt[0]["content"])


def entry_code(bundle: Any) -> str:
    scenario = scenario_for(bundle.seed, bundle.split)
    (code,) = set(scenario.records.values())
    return str(code)


def names(bundle: Any) -> tuple[str, ...]:
    return tuple(str(tool["name"]) for tool in bundle.tools)


Read = tuple[str, dict[str, Any]]


def named(bundle: Any) -> list[Read]:
    """The read calls the reference makes, in the reference's order."""
    return [
        (str(name), dict(args)) for name, args in bundle.reference_calls if name in SPEC.read_tools
    ]


def key(read: Read) -> str:
    """One read as a string: its tool and its arguments, canonically."""
    return json.dumps([read[0], read[1]], sort_keys=True)


def words(text: str) -> set[str]:
    return set(re.findall(r"[a-z]+", text.lower()))


def lines_naming(bundle: Any, read: Read) -> list[int]:
    """The request's lines that name the read: its facet as a word, its item and its page."""
    facet = str(SPEC.read_tools[read[0]])
    return [
        index
        for index, line in enumerate(request(bundle).split("\n"))
        if facet in words(line)
        and str(read[1].get(ITEM)) in line
        and str(read[1].get(PAGE)) in line
    ]


def listed(bundle: Any) -> list[Read]:
    """The named reads in the order the request lists them, each by the one line naming it."""
    placed = []
    for read in named(bundle):
        (line,) = lines_naming(bundle, read)
        placed.append((line, read))
    return [read for _line, read in sorted(placed, key=lambda pair: pair[0])]


def answers(bundle: Any) -> dict[str, str]:
    """Each named read's observation in the reference, by the read."""
    return {
        key((str(name), dict(args))): str(observation)
        for (name, args), observation in zip(
            bundle.reference_calls, bundle.reference_observations, strict=True
        )
        if name in SPEC.read_tools
    }


def payload(observation: str) -> str:
    return observation.split()[2]


def head_and_fill(text: str) -> tuple[str, str]:
    """A payload's head (what is before its first full stop) and its fill (what is after it)."""
    head, _stop, fill = text.partition(STOP)
    return head, fill


def heads(bundle: Any) -> list[str]:
    """The heads of the named reads' answers, in the listed order."""
    found = answers(bundle)
    return [head_and_fill(payload(found[key(read)]))[0] for read in listed(bundle)]


def parts(code: str, level: int) -> list[str]:
    """The code in `level` parts as evenly as it goes, the earlier parts longer."""
    size, extra = divmod(len(code), level)
    out, start = [], 0
    for index in range(level):
        length = size + (1 if index < extra else 0)
        out.append(code[start : start + length])
        start += length
    return out


def catalogue_value(read: Read) -> str:
    """What the engine's read of the read's facet answers for its item."""
    return str(SPEC.catalogue_values[read[1][ITEM]][SPEC.read_tools[read[0]]])
