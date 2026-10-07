"""What the history knob's test files share: the arms and seeds they read, the base task they
compare with, and the seeded pairs of a bundle's prompt as a list.

The test files are `tests/test_k4_*.py`; each says in its own docstring what it pins and what it
decided.  Nothing here asserts anything.  The tool server, the trace writer and the record
reader are the faults knob's (`tests/k3_support.py`), unchanged.
"""

from __future__ import annotations

import json
import statistics
from typing import Any

from poisson_tasks.engine import Scenario, apply, init_state
from poisson_tasks.tasks import TaskBundle
from poisson_tasks.tokenizer import count_tokens
from tests.k3_support import CARD_SEEDS as CARD_SEEDS
from tests.k3_support import SPEC, made, names

LEVELS = (0, 300, 600, 1200, 2400)
# The eval split is the card's, measured at every card seed; the train split at twelve of them,
# because a history task costs about a second to generate at the top level.
TRAIN_SEEDS: tuple[int, ...] = CARD_SEEDS[:12]
SPLITS: tuple[tuple[str, tuple[int, ...]], ...] = (("eval", CARD_SEEDS), ("train", TRAIN_SEEDS))


def arm(level: int) -> str:
    return f"history:t{level}"


def history(level: int, seed: int, split: str = "eval") -> TaskBundle:
    return made(arm(level), seed, split)


Pair = tuple[str, dict[str, Any], str]


def messages_of(bundle: Any) -> list[dict[str, Any]]:
    """A `Messages` prompt as a list of its messages; empty for a plain string prompt."""
    if isinstance(bundle.prompt, str):
        return []
    return [dict(message) for message in bundle.prompt]


def seeded(bundle: Any) -> list[Pair]:
    """The seeded pairs of a `Messages` prompt: each assistant message's one call, with its
    arguments parsed, and the tool message answering it.  Empty for a plain string prompt."""
    prompt = messages_of(bundle)
    pairs: list[Pair] = []
    for ask, answer in zip(prompt[1::2], prompt[2::2], strict=True):
        (tool_call,) = ask["tool_calls"]
        function = tool_call["function"]
        pairs.append((function["name"], json.loads(function["arguments"]), answer["content"]))
    return pairs


def pair_tokens(name: str, args: Any, observation: str) -> int:
    """N9's unit: the name bare, the arguments as one compact JSON object, the observation."""
    rendered = args if isinstance(args, str) else json.dumps(args, separators=(",", ":"))
    return count_tokens(name) + count_tokens(rendered) + count_tokens(observation)


def seeded_tokens(bundle: Any) -> int:
    return sum(pair_tokens(*pair) for pair in seeded(bundle))


def block_reads(bundle: Any) -> tuple[str, ...]:
    return tuple(name for name in names(bundle) if name in SPEC.read_tools)


def median_pair_total(bundle: Any) -> float:
    """`m`: the median reference-token total of every read pair the block can seed at the
    first seeded position, over every read tool in the block, every catalogue item and every
    page the engine answers `ok`.  A read's observation is the catalogue's own value, so the
    table is the vocabulary's, not a scenario's."""
    items = tuple(SPEC.table["catalogue_items"])
    scenario = Scenario(records={}, token_key=b"k4-median", visible_items=items)
    state = init_state(scenario, 1)
    item_param, page_param = SPEC.parameter_names["item"], SPEC.parameter_names["page"]
    totals = []
    for name in block_reads(bundle):
        for item in items:
            for page in SPEC.page_keys:
                args = {item_param: item, page_param: page}
                _after, observation = apply(state, (name, args))
                if observation.split()[1] == "ok":
                    totals.append(pair_tokens(name, args, observation))
    return statistics.median(totals)
