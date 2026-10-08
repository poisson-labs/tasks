"""What the block-size knob's test files share: the arms and seeds they read, the base task they
compare with, and how a block's tools are read back.

The test files are `tests/test_k5_*.py`; each says in its own docstring what it pins and what it
decided.  Nothing here asserts anything.  The tool server, the trace writer and the record reader
are the faults knob's (`tests/k3_support.py`), unchanged.
"""

from __future__ import annotations

import json
from typing import Any

from poisson_tasks.tasks import TaskBundle
from poisson_tasks.tokenizer import count_tokens
from tests.k3_support import CARD_SEEDS as CARD_SEEDS
from tests.k3_support import SPEC, made, names

LEVELS = (8, 16, 32, 64)
CONTROL = "block:k8+len(k64)"
# The first eight slots: the target ledger's two stage tools and six reads, at every level.
HEAD = 8
VERBS: tuple[str, ...] = tuple(SPEC.table["read_verbs"])
FACETS: tuple[str, ...] = tuple(SPEC.table["facets"])
# The engine's reads in table order: its verbs and facets zipped, one read per facet.
READS: tuple[str, ...] = tuple(SPEC.read_tools)
ENGINE_TOOLS = frozenset(tool.name for tool in SPEC.tools)
# A block task costs a few milliseconds to generate (the control under a second), so both splits
# are read at every card seed.
SPLITS: tuple[tuple[str, tuple[int, ...]], ...] = (("eval", CARD_SEEDS), ("train", CARD_SEEDS))


def arm(level: int) -> str:
    return f"block:k{level}"


ARMS = tuple(arm(level) for level in LEVELS) + (CONTROL,)


def block(level: int, seed: int, split: str = "eval") -> TaskBundle:
    return made(arm(level), seed, split)


def control(seed: int, split: str = "eval") -> TaskBundle:
    return made(CONTROL, seed, split)


def size_of(arm_id: str) -> int:
    """How many tools the arm offers: its level, and k8's for the control."""
    return HEAD if arm_id == CONTROL else int(arm_id.removeprefix("block:k"))


def read_of(facet: str) -> str:
    """The engine's read of `facet`."""
    return next(name for name, own in SPEC.read_tools.items() if own == facet)


def pair_of(name: str) -> tuple[str, str] | None:
    """`(verb, facet)` when `name` is `{verb}_{facet}` for one of the table's read verbs and one
    of its facets, else `None`."""
    for verb in VERBS:
        for facet in FACETS:
            if name == f"{verb}_{facet}":
                return verb, facet
    return None


def copies(bundle: Any) -> tuple[str, ...]:
    """The block's tools that are no engine tool, in slot order."""
    return tuple(name for name in names(bundle) if name not in ENGINE_TOOLS)


def engine_schema(engine: str) -> dict[str, Any]:
    """An engine tool's parameters as every generated block renders them."""
    tool = next(t for t in SPEC.tools if t.name == engine)
    keys = sorted(tool.parameters)
    return {
        "type": "object",
        "properties": {k: {"type": tool.parameters[k]} for k in keys},
        "required": keys,
        "additionalProperties": False,
    }


def block_tokens(bundle: Any) -> int:
    """The block's reference tokens as the ledger counts them (N5, N20, N29): the schemas in slot
    order, canonically rendered."""
    return count_tokens(json.dumps(list(bundle.tools), sort_keys=True, separators=(",", ":")))
