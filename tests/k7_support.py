"""What the task-shape knob's test files share: the arms and seeds they read, the base task they
compare with, and a task's targets and goal lines read back from its fields.

The test files are `tests/test_k7_*.py`; each says in its own docstring what it pins and what it
decided.  Nothing here asserts anything.  The tool server, the trace writer and the record reader
are the faults knob's (`tests/k3_support.py`), unchanged.

A task's targets are the records whose stage differs between its initial and its expected
records, each with the stage it is to reach: read from the bundle's own
fields, as `verify` reads them.  A request's goal lines are its lines that name a record id the
scenario holds.
"""

from __future__ import annotations

import json
import re
from typing import Any

from poisson_tasks.tasks import TaskBundle, scenario_for
from tests.k3_support import B_ARM, SPEC, made
from tests.k3_support import CARD_SEEDS as CARD_SEEDS

WIDTHS = (1, 2, 4)
CONTROL = "shape:w1+len(w4)"
# Four stage calls at every width, and sixteen tools.
CALLS = 4
TOOLS = 16
# A shape task costs a few milliseconds to generate, so both splits are read at every card seed.
SPLITS: tuple[tuple[str, tuple[int, ...]], ...] = (("eval", CARD_SEEDS), ("train", CARD_SEEDS))
# The knob's own prompt slot, the one N6 leaves out (`knobs._OWN_SLOT`), and its template.
SLOT = "goal_lines"
TEMPLATE_ID = "ledger-goals/v1"


def arm(width: int) -> str:
    return f"shape:w{width}"


ARMS = tuple(arm(width) for width in WIDTHS) + (CONTROL,)


def shape(width: int, seed: int, split: str = "eval") -> TaskBundle:
    return made(arm(width), seed, split)


def control(seed: int, split: str = "eval") -> TaskBundle:
    return made(CONTROL, seed, split)


def base(seed: int, split: str = "eval") -> TaskBundle:
    """B, the base task (`distractor:r0@k16`)."""
    return made(B_ARM, seed, split)


def width_of(arm_id: str) -> int:
    """The width an arm's task is built at: its level, and the control's own level."""
    return int(arm_id.removeprefix("shape:w").split("+")[0])


def targets(bundle: Any) -> dict[tuple[str, str], int]:
    """The records whose stage differs between the initial and the expected records, with the
    stage each is to reach."""
    before = {(cls, record): stage for cls, record, stage, _token in bundle.initial_state}
    return {
        (cls, record): stage
        for cls, record, stage, _token in bundle.expected_final_state
        if before.get((cls, record)) != stage
    }


def records(bundle: Any) -> tuple[str, str]:
    """The scenario's two record ids: the seed's own (the target's) and the decoy's."""
    held = sorted({record for _cls, record in scenario_for(bundle.seed, bundle.split).records})
    target = str(bundle.goal[1])
    (decoy,) = [record for record in held if record != target]
    return target, decoy


def entry_code(bundle: Any) -> str:
    scenario = scenario_for(bundle.seed, bundle.split)
    (code,) = set(scenario.records.values())
    return str(code)


def ledger_of(tool: str) -> str:
    """The ledger a stage tool advances records of."""
    return str(SPEC.stage_tools[tool][1])


def stage_of(tool: str) -> int:
    """The stage a stage tool moves a record to, counted from 1."""
    return int(SPEC.stage_tools[tool][0]) + 1


def stage_tool(ledger: str, stage: int) -> str:
    """The ledger's stage tool that moves a record to `stage`, counted from 1."""
    (name,) = [
        name for name, (index, q) in SPEC.stage_tools.items() if q == ledger and index == stage - 1
    ]
    return str(name)


def names(bundle: Any) -> tuple[str, ...]:
    return tuple(str(tool["name"]) for tool in bundle.tools)


def stage_names_in(bundle: Any) -> tuple[str, ...]:
    return tuple(name for name in names(bundle) if name in SPEC.stage_tools)


def request(bundle: Any) -> str:
    """The user request: the prompt, which no shape arm seeds."""
    return bundle.prompt if isinstance(bundle.prompt, str) else str(bundle.prompt[0]["content"])


def goal_lines(bundle: Any) -> list[str]:
    """The request's lines that name a record id the scenario holds."""
    held = records(bundle)
    return [line for line in request(bundle).split("\n") if any(r in line for r in held)]


def words(text: str) -> set[str]:
    return set(re.findall(r"[a-z]+", text.lower()))


def engine_schema(name: str) -> dict[str, Any]:
    """An engine tool as a block shows it under its own name: its description, its parameters
    each typed as the table types them, all of them required, nothing else allowed."""
    tool = next(t for t in SPEC.tools if t.name == name)
    return {
        "name": tool.name,
        "description": tool.description,
        "parameters": {
            "type": "object",
            "properties": {p: {"type": tool.parameters[p]} for p in sorted(tool.parameters)},
            "required": sorted(tool.parameters),
            "additionalProperties": False,
        },
    }


def table_text() -> str:
    """The vocabulary table as one lowercased string, for a word no part of it spells."""
    return json.dumps(SPEC.table).lower()
