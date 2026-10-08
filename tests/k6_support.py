"""What the argument-difficulty knob's test files share: the arms and seeds they read, the base task
they compare with, and how a call's extra values are read back.

The test files are `tests/test_k6_*.py`; each says in its own docstring what it pins and what it
decided.  Nothing here asserts anything.  The tool server, the trace writer and the record reader
are the faults knob's (`tests/k3_support.py`), unchanged.

A stage tool's own parameters are the engine's: the two its tool lists in the vocabulary table.  A
call's extra values are the ones it carries in any other parameter.  An arm's stated values are the
extra values its reference's first stage call carries, which are the ones the verifier is to
require.
"""

from __future__ import annotations

import json
from typing import Any

from poisson_tasks.tasks import TaskBundle
from tests.k3_support import B_ARM, SPEC, made
from tests.k3_support import CARD_SEEDS as CARD_SEEDS

LEVELS = (2, 4, 6, 8)
CONTROL = "arguments:a2+len(a8)"
# Six parameters beside the engine's two, at every level.
MORE = 6
# The levels no card measures, between the card's ends.
OFF_CARD_LEVELS = (3, 5, 7)
# An arguments task costs a few milliseconds to generate, so both splits are read at every card
# seed.
SPLITS: tuple[tuple[str, tuple[int, ...]], ...] = (("eval", CARD_SEEDS), ("train", CARD_SEEDS))
SLOT = "stated_values"


def arm(level: int) -> str:
    return f"arguments:a{level}"


ARMS = tuple(arm(level) for level in LEVELS) + (CONTROL,)


def arguments(level: int, seed: int, split: str = "eval") -> TaskBundle:
    return made(arm(level), seed, split)


def control(seed: int, split: str = "eval") -> TaskBundle:
    return made(CONTROL, seed, split)


def base(seed: int, split: str = "eval") -> TaskBundle:
    """B, the base task (`distractor:r0@k16`)."""
    return made(B_ARM, seed, split)


def stated_count(arm_id: str) -> int:
    """How many values the arm's request states: its level less two, and none for the control."""
    return 0 if arm_id == CONTROL else int(arm_id.removeprefix("arguments:a")) - 2


ENGINE_PARAMETERS = frozenset(name for tool in SPEC.tools for name in tool.parameters)


def own(name: str) -> frozenset[str]:
    """The engine's parameters of the tool `name`, or none when the engine has no such tool."""
    tool = next((t for t in SPEC.tools if t.name == name), None)
    return frozenset() if tool is None else frozenset(tool.parameters)


def extras(call: Any) -> dict[str, Any]:
    """The values a call carries beside its tool's own parameters."""
    name, args = call
    if not isinstance(args, dict):
        return {}
    mine = own(str(name))
    return {key: value for key, value in args.items() if key not in mine}


def stripped(call: Any) -> tuple[str, Any]:
    """The call with only its tool's own parameters, as the engine is to see it."""
    name, args = call
    if not isinstance(args, dict):
        return str(name), args
    mine = own(str(name))
    return str(name), {key: value for key, value in args.items() if key in mine}


def stated(bundle: Any) -> dict[str, Any]:
    """The arm's stated values: the extra values its reference's first stage call carries."""
    first = next(call for call in bundle.reference_calls if call[0] in SPEC.stage_tools)
    return extras(first)


def stage_tools(bundle: Any) -> tuple[dict[str, Any], ...]:
    return tuple(tool for tool in bundle.tools if tool["name"] in SPEC.stage_tools)


def more(tool: dict[str, Any]) -> tuple[str, ...]:
    """The parameters a stage tool lists beside the engine's own, sorted."""
    return tuple(sorted(set(tool["parameters"]["properties"]) - own(str(tool["name"]))))


def in_words(name: str) -> str:
    return name.replace("_", " ")


def request(bundle: Any) -> str:
    """The user request: the prompt, which no arguments arm seeds."""
    return bundle.prompt if isinstance(bundle.prompt, str) else str(bundle.prompt[0]["content"])


def other_case(value: str) -> str:
    """The value in another case, or with a character more where it has no case."""
    changed = value.swapcase()
    return changed if changed != value else value + "0"


def table_text() -> str:
    """The vocabulary table as one lowercased string, for a word no part of it spells."""
    return json.dumps(SPEC.table).lower()
