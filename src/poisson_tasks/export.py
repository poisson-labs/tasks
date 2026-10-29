"""The verifiers export: a generated bundle packaged as a verifiers v1 taskset.

The invariants are X1 to X9 (the `test_x*` cases in `tests/test_tg_m4_export.py`), plus
`validate`, the toolset and knob R's level axis.  Ten public names, in `__all__`'s order:

| name | what it is |
|---|---|
| `ExportTasksetConfig` | the arm spec and the declared seed list |
| `ExportTaskConfig` | the arm's strictness and id, every field defaulted |
| `ExportTaskData` | the whole bundle, as the wire carries it |
| `ExportTask` | `key`, one reward, four metrics, `toolsets`, `validate` |
| `ExportTaskset` | finite; one task per declared seed, in declared order |
| `DomainToolsetConfig`, `DomainToolset` | the task's tool block, served |
| `task_from_bundle`, `bundle_from_data` | the two directions of X2 |
| `MEASURED_HARNESS` | `"null"` (X9) |

Four things about `verifiers==0.3.1` shape this file and are not obvious from its
documentation.  Each was measured against the installed wheel.

**The bundle's seeded history is not `vf.Messages`.**  `tasks.py` writes a D control's prompt in
the OpenAI chat shape (`tool_calls[i].function.name`), and 0.3.1's `vf.ToolCall` is flat
(`name`, `arguments`), so the wheel refuses the prompt as written.  The task data therefore
carries the wheel's shape and `bundle_from_data` restores the OpenAI one; X2 is what holds
both halves honest.

**The task data crosses a JSON wire.**  A launched tool server is handed its task as
`model_dump_json`, rebuilt with `model_validate_json` on the data's own class, found by
`module:qualname` -- so every field has to survive JSON, and JSON has no tuple.  The
restoring is in `bundle_from_data` and `_deep_tuple`, not in the field types alone.

**A tool body has to be total.**  FastMCP validates a call's arguments against the
function's signature before the body runs, and a call refused there never reaches `apply`;
the live counter would then trail the engine's `replay` by one and every later observation
would differ.  `_EngineTool` hands the raw argument dict to the engine instead, so a bad
call comes back as the engine's own numbered line (tool bodies call `apply`, E5).

**The advertised schema is the bundle's, byte for byte.**  `ToolManager.add_tool` derives a
schema from a function's signature (a `title` per property, no `additionalProperties`),
which is not the bundle's, and it is the manager's only public entry point; `register`
therefore builds the `Tool` itself and puts it in the manager (X3).

One question is not settled here, and the tests do not pin it: where a call the harness
refused sorts (its tool message carries no `seq`, and it mutates nothing wherever it
lands).  `turn_limit_hit` is read from the stop reason,
`Trace.stop_condition == "max_turns"`, and not `is_truncated`, which is also true for a token
limit (`_verdict`).
"""

from __future__ import annotations

import asyncio as _asyncio
import dataclasses as _dc
import json as _json
import warnings as _warnings
from collections.abc import Iterator as _Iterator
from typing import Any as _Any

import verifiers.v1 as _vf
from mcp.server.fastmcp import FastMCP as _FastMCP
from mcp.server.fastmcp.tools import Tool as _Tool
from pydantic import Field as _Field
from pydantic import model_validator as _model_validator

from poisson_tasks import surface as _surface
from poisson_tasks.arms import _CONTROL_PAIRS, _on_a_published_card
from poisson_tasks.arms import DEFAULT_GENERATOR_VERSION as _DEFAULT_GENERATOR_VERSION
from poisson_tasks.arms import EXPERIMENTAL_KNOBS as _EXPERIMENTAL_KNOBS
from poisson_tasks.arms import arm_from_id as _arm_from_id
from poisson_tasks.engine import apply as _apply
from poisson_tasks.engine import init_state as _init_state
from poisson_tasks.knobs import ArmSpec as _ArmSpec
from poisson_tasks.knobs import PinRecord as _PinRecord
from poisson_tasks.knobs import arm_id as _arm_id
from poisson_tasks.knobs import levels as _levels
from poisson_tasks.tasks import _GENERATED_KNOBS
from poisson_tasks.tasks import FormatSpec as _FormatSpec
from poisson_tasks.tasks import TaskBundle as _TaskBundle
from poisson_tasks.tasks import Turn as _Turn
from poisson_tasks.tasks import Verdict as _Verdict
from poisson_tasks.tasks import VerifierSpec as _VerifierSpec
from poisson_tasks.tasks import generate as _generate
from poisson_tasks.tasks import scenario_for as _scenario_for
from poisson_tasks.tasks import verify as _verify

__all__ = [
    "ExportTasksetConfig",
    "ExportTaskConfig",
    "ExportTaskData",
    "ExportTask",
    "ExportTaskset",
    "DomainToolsetConfig",
    "DomainToolset",
    "task_from_bundle",
    "bundle_from_data",
    "MEASURED_HARNESS",
]

MEASURED_HARNESS = "null"
"""X9: the harness every pinned measurement was made under.  `docs/verifiers-export.md`
says what a run under another one costs."""

# The reward's own format spec.  The pass predicate is decided before the format check
# (`tasks.verify` orders them so) and the taskset does not know the serving pin's parser, so the
# export scores with no markers and leaves `malformed_call` to the adapter's own `verify`.
_EXPORT_FORMAT = _FormatSpec(name="export", markers=())


# ---------------------------------------------------------------------------
# configs
# ---------------------------------------------------------------------------


class ExportTaskConfig(_vf.TaskConfig):
    """The task's config: the strictness and the arm id.

    Every field is defaulted because 0.3.1 builds the declared config type with no
    arguments when a task is constructed without one.
    """

    strictness: str = "strict"
    arm_id: str = ""


_ARM_FIELDS = tuple(field.name for field in _dc.fields(_ArmSpec))
_STRICTNESSES = ("strict", "leaky")
_SPLITS = ("eval", "train")


def _whole_number(value: _Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _shown(value: _Any) -> str:
    """A value as the command line or a TOML file gave it, for a message: `"leakey"`, `true`."""
    try:
        return _json.dumps(value)
    except (TypeError, ValueError):
        return type(value).__name__


def _arm_mapping(arm: _Any) -> dict[str, _Any]:
    """The declared arm as the six-field mapping, checked, before the config is validated.

    An id such as `depth:d3` becomes the mapping, strict, on the eval split, at the default
    generator version: an id carries the knob, the level and the control and nothing else.

    Every arm the generator cannot make is refused here, in one line naming the field, rather
    than when the tasks are generated: a field missing, misspelled or extra; a strictness other
    than the two (a misspelled one was scored as strict); a split other than the two; a level or
    a control that is not a whole number, or outside what the knob can make.  Depth runs from 1
    to 8, distractor from 0 to 14, similarity from 0 to 3, faults from 0 to 4, history from 0
    to 2400, block from 8 to 64, arguments from 2 to 8, shape from 1 to 4 and spread from 1
    to 4, which are the ends of each knob's candidate levels: the stage ladder has eight
    stages, the tool table offers fourteen distractors, a lookalike shares at most three of a
    ledger number's four digits, four failed calls is the first level that makes a model retry
    one tool twice, 2400 tokens of earlier tool work is the most that keeps an episode of
    model B's at the turn cap under its context's headroom, sixty-four tools is the most a
    block can offer and keep model B's first request under that headroom, as eight, the two
    the task needs and six reads, is the fewest, a stage call carries the two values the
    engine needs at the least and those plus the six more its tool lists at the most, four
    stage calls advance one record, two or four side by side, and an entry code is split
    across one to all four of the reads a request names.  A shape width inside those ends that
    is not 1, 2 or 4 is refused when the arm is made, in one line.  A name that is no knob is
    refused by name.

    An arm the generator can make and no published card measured is taken, with one note.
    """
    if isinstance(arm, str):
        arm = _dc.asdict(_arm_from_id(arm))
    if not isinstance(arm, dict):
        raise ValueError(
            "arm is neither an arm id such as depth:d3 nor the six fields of an arm as one "
            f"mapping; got {type(arm).__name__}"
        )
    unknown = [str(name) for name in arm if name not in _ARM_FIELDS]
    missing = [name for name in _ARM_FIELDS if name not in arm]
    if unknown or missing:
        problems = []
        if unknown:
            problems.append("no field of an arm is named " + ", ".join(unknown))
        if missing:
            problems.append("the arm is missing " + ", ".join(missing))
        raise ValueError(
            "; ".join(problems) + ": an arm has the six fields " + ", ".join(_ARM_FIELDS)
        )

    knob, level, control = arm["knob"], arm["level"], arm["control"]
    if knob == "landed":
        raise ValueError(
            "knob 'landed' has no tasks to run on the built-in tasks: the ledger refuses a "
            "repeated stage call, so a write that landed has no duplicate to catch; landed is "
            "offered on your own tools"
        )
    if not isinstance(knob, str) or knob not in _GENERATED_KNOBS:
        raise ValueError(
            f"knob {_shown(knob)} has no tasks to run: the generator makes tasks for "
            + ", ".join(_GENERATED_KNOBS[:-1])
            + f" and {_GENERATED_KNOBS[-1]}"
        )
    lowest, highest = min(_levels(knob)), max(_levels(knob))
    if not _whole_number(level):
        raise ValueError(f"level {_shown(level)} is not a whole number")
    if not lowest <= level <= highest:
        raise ValueError(
            f"level {level} is not a {knob} level the generator can make: {knob} runs from "
            f"{lowest} to {highest}"
        )
    if control is not None:
        if not _whole_number(control):
            raise ValueError(f"control {_shown(control)} is neither null nor a whole number")
        if not level < control <= highest:
            raise ValueError(
                f"control {control} cannot stand in for {knob} level {level}: a control is a "
                f"higher level, above {level} and at most {highest}"
            )
    if arm["strictness"] not in _STRICTNESSES:
        raise ValueError(
            f"strictness {_shown(arm['strictness'])} is not a strictness: it is "
            + " or ".join(_STRICTNESSES)
        )
    if arm["split"] not in _SPLITS:
        raise ValueError(
            f"split {_shown(arm['split'])} is not a split: it is " + " or ".join(_SPLITS)
        )
    if not isinstance(arm["generator_version"], str):
        raise ValueError(
            f"generator_version {_shown(arm['generator_version'])} is not text; the published "
            f'cards\' is "{_DEFAULT_GENERATOR_VERSION}"'
        )

    spec = _ArmSpec(**arm)
    if not _on_a_published_card(spec):
        _warnings.warn(_off_the_cards(spec), UserWarning, stacklevel=2)
    return dict(arm)


def _off_the_cards(spec: _ArmSpec) -> str:
    """The note on an arm no published card measured: one line, naming the arm and why."""
    plain = _ArmSpec(
        knob=spec.knob,
        level=spec.level,
        control=spec.control,
        strictness="strict",
        split="eval",
        generator_version=_DEFAULT_GENERATOR_VERSION,
    )
    reasons = []
    if not _on_a_published_card(plain):
        if spec.knob not in _CONTROL_PAIRS:
            reasons.append(f"they measure {' and '.join(_CONTROL_PAIRS)}, not {spec.knob}")
        elif spec.control is None:
            measured = [str(level) for level in _levels(spec.knob)]
            reasons.append(
                f"they measure {spec.knob} at " + ", ".join(measured[:-1]) + f" and {measured[-1]}"
            )
        else:
            controls = [
                _arm_id(_dc.replace(plain, level=level, control=control))
                for level, control in _CONTROL_PAIRS[spec.knob]
            ]
            reasons.append(f"their {spec.knob} control arms are " + " and ".join(controls))
    if spec.strictness != plain.strictness:
        reasons.append(f"their tasks are strict and these are {spec.strictness}")
    if spec.split != plain.split:
        reasons.append(f"their tasks are on the eval split and these are on {spec.split}")
    if spec.generator_version != plain.generator_version:
        reasons.append(
            f'their tasks are at generator version "{plain.generator_version}" and these are '
            f'at "{spec.generator_version}"'
        )
    return (
        f"no published card covers the arm {_arm_id(spec)} as given here ("
        + "; ".join(reasons)
        + "), so its results cannot be read beside the published cards"
    )


class ExportTasksetConfig(_vf.TasksetConfig):
    """The taskset's config: the arm spec plus the declared seed list, which is finite.

    `arm` is the six `ArmSpec` fields as a mapping rather than the dataclass, so the
    config stays a plain pydantic model on the wire and under `--env.taskset.arm.*`.
    The `task` config is derived from the arm when the caller gives none: it carries
    exactly the strictness and the arm id, and the arm already determines both fields.

    `task` is re-declared here, narrower than the base's `SerializeAsAny[TaskConfig]`,
    and it has to be: the wheel dumps that field duck-typed (whatever subclass instance it
    holds, with that subclass's own fields) but validates it against the base, which forbids
    extras.  So a config carrying this module's task config serialises wide and loads narrow,
    and the one place it crosses a process boundary -- `serve/pool.py` shipping the env config
    to the env server -- refuses the config the wheel itself just resolved.  Measured live,
    2026-09-22: the env server died on `strictness` and `arm_id` before the first model call.
    Re-declaring the field makes the round trip a fixed point.  Reported upstream as well;
    the invariant is `test_w1` in `tests/test_tg_m5_standalone.py`.

    A declared list that repeats a seed is refused.  The refusal is forced, not chosen:
    X7 makes keys unique within a taskset, X8 makes `len(list(load()))` the list's
    length, and a repeated seed is a repeated `task_id` -- so both cannot hold for it.
    Only the *place* was open, and the earliest one is here.
    """

    arm: dict[str, _Any] = _Field(
        default_factory=dict,
        description=(
            "The arm: its id, for example depth:d3 (strict, on the eval split), or the six "
            "ArmSpec fields as one JSON object, for example "
            '{"knob": "depth", "level": 3, "control": null, "strictness": "strict", '
            f'"split": "eval", "generator_version": "{_DEFAULT_GENERATOR_VERSION}"}}. '
            "knob 'depth' (levels 1, 2, 3, 5, 8) sets how many chained calls the goal is "
            "away. "
            "knob 'distractor' (levels 0, 2, 4, 8, 14) is RETIRED and EXPERIMENTAL: on both "
            "calibrated models it does not make tasks harder, so it is not a difficulty "
            "setting. "
            "knob 'similarity' (levels 0, 1, 2, 3) sets how many digits of a four-digit ledger "
            "number each lookalike tool shares, in place, with the right tool's; no published "
            "card measures it yet. "
            "knob 'faults' (levels 0, 1, 2, 4) sets how many calls on the way answer "
            "unavailable and must be made again; its control arm faults:f0+len(f4) seeds the "
            "same length as earlier tool work; no published card measures it yet. "
            "knob 'history' (levels 0, 300, 600, 1200, 2400) sets how many tokens of earlier "
            "tool work, read calls and their answers as the reference tokenizer counts them, "
            "the conversation holds before the model's first move; no published card "
            "measures it yet. "
            "knob 'block' (levels 8, 16, 32, 64) sets how many tools the model is offered: the "
            "two the task needs and six read tools fill the first eight places at every level, "
            "and the rest are read tools, past sixteen under names of their own; its control arm "
            "block:k8+len(k64) adds the same length to the system prompt; no published card "
            "measures it yet. "
            "knob 'arguments' (levels 2, 4, 6, 8) sets how many values each stage call must "
            "carry, copied from the request: the two the task always needs and the level less "
            "two of six more its tool lists, exactly those and no other; its control arm "
            "arguments:a2+len(a8) adds the same length to the request; no published card "
            "measures it yet. "
            "knob 'shape' (levels 1, 2, 4) sets how many records four stage calls advance side "
            "by side: one record through four stages, the target and the decoy two stages "
            "each, or the target record one stage in four ledgers, the block holding exactly "
            "the stage tools the width needs; its control arm shape:w1+len(w4) adds the same "
            "length to the request; no published card measures it yet. "
            "knob 'spread' (levels 1, 2, 4) sets how many tool answers the entry code is split "
            "across: the request names four reads in place of stating the code, the first "
            "level-many answer with a part of it in order and the rest with none, and the "
            "block, the prompt and the calls are the same at every level, so it has no control "
            "arm; no published card measures it yet. "
            "knob 'timeouts' (levels 0, 1, 2, 4) sets how many calls on the way answer timeout, "
            "nothing having landed, and must be made again; its control arm timeouts:o0+len(o4) "
            "seeds the same length as earlier tool work; EXPERIMENTAL: "
            f"{_EXPERIMENTAL_KNOBS['timeouts']}. "
            "knob 'ratelimits' (levels 0, 1, 2, 4) sets how many calls on the way answer "
            "rate_limited with a retry-after of one second, nothing having landed, and must be "
            "made again; its control arm ratelimits:r0+len(r4) seeds the same length as earlier "
            f"tool work; EXPERIMENTAL: {_EXPERIMENTAL_KNOBS['ratelimits']}. "
            "knob 'landed' (levels 0, 1) sets whether the write goes through and answers timeout, "
            "so a blind retry is a duplicate; it is offered on your own tools only, whose store "
            "accepts a second write, since on the built-in ledger a repeated stage call is refused "
            f"and changes nothing; EXPERIMENTAL: {_EXPERIMENTAL_KNOBS['landed']}. "
            "See docs/calibration.md."
        ),
    )
    seeds: list[int] = _Field(
        default_factory=list,
        description="The task seeds: one task per seed, in the order given, no repeats.",
    )
    task: ExportTaskConfig = _Field(default_factory=ExportTaskConfig)

    @_model_validator(mode="before")
    @classmethod
    def _refuse_a_repeat_and_derive_the_task_config(cls, data: _Any) -> _Any:
        if not isinstance(data, dict):
            return data
        seeds = data.get("seeds") or []
        if isinstance(seeds, list) and len(set(seeds)) != len(seeds):
            repeated = sorted({seed for seed in seeds if seeds.count(seed) > 1})
            raise ValueError(
                f"the declared seed list holds {len(seeds)} entries and "
                f"{len(set(seeds))} distinct seeds; each of {repeated} appears more "
                "than once, and one seed is one task"
            )
        arm = data.get("arm")
        if arm:
            arm = data["arm"] = _arm_mapping(arm)
        if isinstance(arm, dict) and arm and data.get("task") is None:
            spec = _ArmSpec(**arm)
            data["task"] = ExportTaskConfig(
                strictness=spec.strictness, arm_id=_arm_id(spec)
            )
        return data

    def arm_spec(self) -> _ArmSpec:
        """The declared arm, as `knobs.ArmSpec`."""
        if not self.arm:
            raise ValueError(
                "this taskset config declares no arm: pass "
                "`arm=dataclasses.asdict(spec)` for the ArmSpec the seeds belong to"
            )
        return _ArmSpec(**self.arm)


# ---------------------------------------------------------------------------
# the task data, and the two directions of X2
# ---------------------------------------------------------------------------


class ExportTaskData(_vf.TaskData):
    """The whole bundle.

    X2, X4, X6, X7 and `validate` between them need all twenty-one of the bundle's
    fields, not only the eight a task's wire data would obviously carry: `task_id` is a
    content hash over every other field, so a round trip that dropped one would not hash
    equal; `verify` derives the scenario from `seed` and `split`; X6 and `validate` score
    `reference_calls`.

    `prompt`, `system_prompt`, `idx` and the rest of `vf.TaskData` come from the base.
    Nothing here is a tuple: the wire is JSON, and `bundle_from_data` restores the
    bundle's tuples on the way back.
    """

    task_id: str = ""
    arm_id: str = ""
    seed: int = 0
    split: str = ""
    scenario_hash: str = ""
    tools: list[dict[str, _Any]] = _Field(default_factory=list)
    seq_start: int = 1
    template_id: str = ""
    prompt_slots: list[list[str]] = _Field(default_factory=list)
    initial_state: list[list[_Any]] = _Field(default_factory=list)
    expected_final_state: list[list[_Any]] = _Field(default_factory=list)
    goal: list[_Any] = _Field(default_factory=list)
    reference_calls: list[list[_Any]] = _Field(default_factory=list)
    reference_observations: list[str] = _Field(default_factory=list)
    negative_controls: dict[str, list[list[_Any]]] = _Field(default_factory=dict)
    strictness: str = "strict"
    pin_arm_id: str = ""
    pin_values: dict[str, _Any] = _Field(default_factory=dict)
    pin_unmeasured: dict[str, str] = _Field(default_factory=dict)
    engine_hash: str = ""
    generator_hash: str = ""


def _deep_tuple(value: _Any) -> _Any:
    """Every list back to a tuple, all the way down.

    The bundle's own list is the tool schema's `required`, which never passes through
    here: the tools are carried as the mappings they are and rebuilt with `dict`.
    """
    if isinstance(value, (list, tuple)):
        return tuple(_deep_tuple(item) for item in value)
    return value


def _call_pair(pair: _Any) -> tuple[str, _Any]:
    """One `(name, arguments)` call, with the arguments as the engine wants them.

    A call's arguments are usually a JSON object and come back as a `dict`.  Clause 2 of
    the format check needs arguments that are *not* an object, and `tasks.py` generates a
    control whose arguments are a tuple; JSON has no tuple, so that one arrives as a
    list and is restored here.
    """
    name, arguments = pair
    return (str(name), _deep_tuple(arguments) if isinstance(arguments, list) else arguments)


def _to_wire_message(message: dict[str, _Any]) -> dict[str, _Any]:
    """One seeded message, from the bundle's OpenAI chat shape into the wheel's.

    Only an assistant message differs: 0.3.1's `vf.ToolCall` is flat, where OpenAI nests
    the name and the arguments under `function`.  An assistant message in the seeded
    history carries tool calls and no content, and the wheel's model leaves `content`
    unset rather than null, which is what makes the trip back exact.
    """
    if message["role"] != "assistant":
        return dict(message)
    return {
        "role": "assistant",
        "tool_calls": [
            {
                "id": call["id"],
                "type": call["type"],
                "name": call["function"]["name"],
                "arguments": call["function"]["arguments"],
            }
            for call in message["tool_calls"]
        ],
    }


def _from_wire_message(message: _Any) -> dict[str, _Any]:
    """The other direction: one `vf` message back into the bundle's chat shape."""
    if isinstance(message, _vf.AssistantMessage):
        return {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": call.id,
                    "type": call.type,
                    "function": {"name": call.name, "arguments": call.arguments},
                }
                for call in message.tool_calls or []
            ],
        }
    if isinstance(message, _vf.ToolMessage):
        return {
            "role": "tool",
            "tool_call_id": message.tool_call_id,
            "content": message.content,
        }
    return {"role": message.role, "content": message.content}


def _data_from_bundle(bundle: _TaskBundle) -> ExportTaskData:
    """X2's forward direction, field for field."""
    prompt: _Any = (
        bundle.prompt
        if isinstance(bundle.prompt, str)
        else [_to_wire_message(message) for message in bundle.prompt]
    )
    return ExportTaskData(
        prompt=prompt,
        system_prompt=bundle.system_prompt,
        task_id=bundle.task_id,
        arm_id=bundle.arm_id,
        seed=bundle.seed,
        split=bundle.split,
        scenario_hash=bundle.scenario_hash,
        tools=[dict(tool) for tool in bundle.tools],
        seq_start=bundle.seq_start,
        template_id=bundle.template_id,
        prompt_slots=[list(slot) for slot in bundle.prompt_slots],
        initial_state=[list(row) for row in bundle.initial_state],
        expected_final_state=[list(row) for row in bundle.expected_final_state],
        goal=list(bundle.goal),
        reference_calls=[list(call) for call in bundle.reference_calls],
        reference_observations=list(bundle.reference_observations),
        negative_controls={
            label: [list(call) for call in calls]
            for label, calls in bundle.negative_controls.items()
        },
        strictness=bundle.verifier.strictness,
        pin_arm_id=bundle.pins.arm_id,
        pin_values=dict(bundle.pins.values),
        pin_unmeasured=dict(bundle.pins.unmeasured),
        engine_hash=bundle.engine_hash,
        generator_hash=bundle.generator_hash,
    )


def bundle_from_data(data: ExportTaskData) -> _TaskBundle:
    """X2's other direction: "task data re-serialised to a bundle".

    The result is equal to the generated bundle, not merely equal under a canonical hash
    -- and the difference is load-bearing.  A rebuilt bundle whose state rows came back
    as lists is refused by `tasks.verify` as a defective bundle (`verifier_error`), so
    a consumer that rebuilds one needs the stronger statement.  Every tuple the bundle
    holds is restored here, the pin record's nested ones included; the tool schemas'
    `required` lists stay lists, because that is what the bundle has.
    """
    prompt: _Any = (
        data.prompt
        if isinstance(data.prompt, str)
        else tuple(_from_wire_message(message) for message in data.prompt or [])
    )
    return _TaskBundle(
        task_id=data.task_id,
        arm_id=data.arm_id,
        seed=data.seed,
        split=data.split,
        scenario_hash=data.scenario_hash,
        system_prompt=data.system_prompt or "",
        prompt=prompt,
        tools=tuple(dict(tool) for tool in data.tools),
        seq_start=data.seq_start,
        template_id=data.template_id,
        prompt_slots=tuple(_deep_tuple(slot) for slot in data.prompt_slots),
        initial_state=tuple(_deep_tuple(row) for row in data.initial_state),
        expected_final_state=tuple(_deep_tuple(row) for row in data.expected_final_state),
        goal=_deep_tuple(data.goal),
        reference_calls=tuple(_call_pair(call) for call in data.reference_calls),
        reference_observations=tuple(data.reference_observations),
        negative_controls={
            label: tuple(_call_pair(call) for call in calls)
            for label, calls in data.negative_controls.items()
        },
        verifier=_VerifierSpec(strictness=data.strictness),
        pins=_PinRecord(
            arm_id=data.pin_arm_id,
            values={key: _deep_tuple(value) for key, value in data.pin_values.items()},
            unmeasured=dict(data.pin_unmeasured),
        ),
        engine_hash=data.engine_hash,
        generator_hash=data.generator_hash,
    )


# ---------------------------------------------------------------------------
# the verdict: X4's ordering, then the task layer's own verifier
# ---------------------------------------------------------------------------


def _seq_of(content: _Any) -> int | None:
    """The `seq` a tool message's observation opens with, or `None`.

    `None` is not an error: under the `null` harness a call whose arguments are not a
    JSON object, or whose name is outside the advertised block, never reaches the tool
    server.  The harness answers it itself with an `error: ...` line that carries no
    number, and the engine's counter does not move.
    """
    if not isinstance(content, str):
        return None
    head = content.split(" ", 1)[0]
    return int(head) if head.isdigit() else None


def _sampled_exchanges(trace: _Any) -> list[tuple[_Any, tuple[str, _Any]]]:
    """Every sampled tool call with the content of the tool message that answers it, or
    `None` when none does.

    `Trace.assistant_messages` is sampled-only, so a control arm's pre-seeded messages
    are excluded by construction (X4) -- but the *tool* messages are not, and the seeded
    history's call ids are `call_0`, `call_1`, ..., which a model's ids can collide with.
    Walking the nodes and consuming each tool message once matches a call to the message
    that follows it rather than to the first one that shares its id.
    """
    open_calls: list[tuple[str, _Any]] = []
    open_ids: list[str] = []
    found: dict[int, _Any] = {}
    for node in trace.nodes:
        message = node.message
        if node.sampled and isinstance(message, _vf.AssistantMessage):
            for call in message.tool_calls or []:
                try:
                    arguments: _Any = _json.loads(call.arguments or "{}")
                except ValueError:
                    arguments = call.arguments
                open_ids.append(call.id)
                open_calls.append((call.name, _deep_tuple(arguments)
                                   if isinstance(arguments, list) else arguments))
        elif isinstance(message, _vf.ToolMessage):
            for index, call_id in enumerate(open_ids):
                if call_id == message.tool_call_id and index not in found:
                    found[index] = message.content
                    break
    return [(found.get(index), call) for index, call in enumerate(open_calls)]


def _sampled_calls(trace: _Any) -> list[tuple[int | None, tuple[str, _Any]]]:
    """Every sampled tool call with the `seq` of the tool message that follows it, which a
    call the harness answered itself does not have (`_seq_of`)."""
    return [(_seq_of(content), call) for content, call in _sampled_exchanges(trace)]


def _ordered_turns(trace: _Any) -> tuple[tuple[_Turn, ...], bool]:
    """The sampled calls as `tasks.Turn`s, ordered by X4's key, and whether the episode
    ended with a reply.

    X4 orders the calls "by the `seq` in the matching `Trace.tool_messages` content".  A
    call the harness refused has no such `seq`; it mutates nothing wherever it sorts, so
    it is kept in the position it was sampled in and nothing is pinned on the choice.
    """
    sampled = trace.assistant_messages
    rows = _sampled_calls(trace)
    keys: list[float] = []
    last = -1.0
    for seq, _call in rows:
        key = float(seq) if seq is not None else last + 0.5
        last = max(last, key)
        keys.append(key)
    order = sorted(range(len(rows)), key=lambda index: (keys[index], index))
    turns = [
        _Turn(content="", calls=(rows[index][1],), finish_reason="tool_calls")
        for index in order
    ]
    ended_with_reply = bool(sampled) and not sampled[-1].tool_calls
    if ended_with_reply:
        turns.append(
            _Turn(content=sampled[-1].content or "", calls=(), finish_reason="stop")
        )
    return tuple(turns), ended_with_reply


def _verdict(data: ExportTaskData, trace: _Any) -> _Verdict:
    """`tasks.verify`'s verdict on the trace.  The reward is never its own expectation (X4).

    `turn_limit_hit` is the stop reason and nothing wider: a trace the
    wheel stopped at `max_turns`.  `is_truncated` is also true for a token limit and for a
    length-finished reply, and neither is a turn limit -- an episode cut by one of those
    ended for a reason the verdict's five arguments cannot see, and is `verifier_error`.
    """
    turns, ended_with_reply = _ordered_turns(trace)
    return _verify(
        bundle_from_data(data),
        turns,
        ended_with_reply,
        trace.stop_condition == "max_turns",
        _EXPORT_FORMAT,
    )


# ---------------------------------------------------------------------------
# the task
# ---------------------------------------------------------------------------


class ExportTask(_vf.Task[ExportTaskData, _vf.State, ExportTaskConfig]):
    """The task: one reward, four metrics, the domain toolset and G4.

    The generic parameters are not decoration.  0.3.1 reads a task's data and config
    types off them, and a subclass that leaves them bare gets `vf.TaskData` back -- and
    then rebuilds a launched server's task as a plain `vf.TaskData`, silently dropping
    every bundle field.
    """

    @property
    def key(self) -> str:
        """X7: `key` = `task_id`.

        The wheel's default is a content hash of the wire data, which moves with `idx`
        and with a `TasksetConfig.system_prompt` override; `task_id` is the generator's
        own durable identifier and is what the pin ledger and the adapter both quote.
        """
        return str(self.data.task_id)

    @_vf.reward(weight=1.0)
    async def strict(self, task: ExportTaskData, trace: _vf.Trace) -> float:
        """X4: 1.0 exactly when `tasks.verify` gives strict `passed`.

        The one reward, weighing 1.0.  The leaky verdict is descriptive, not a second
        pass predicate, and must not reach `Trace.reward`, which is why `leaky_pass` below
        is a metric.
        """
        return 1.0 if _verdict(task, trace).strict_label == "passed" else 0.0

    @_vf.metric
    async def leaky_pass(self, task: ExportTaskData, trace: _vf.Trace) -> float:
        """The leaky predicate, reported beside the strict one and never summed in."""
        return 1.0 if _verdict(task, trace).leaky_pass else 0.0

    @_vf.metric
    async def mutation_count(self, task: ExportTaskData, trace: _vf.Trace) -> float:
        """The mutation count: `len(Verdict.mutations)`, the verifier's own count.

        It counts `(class, id, field)` triples, three to a successful transition, and it
        still reports the audit field, because it is diagnostic and not the predicate.
        """
        return float(len(_verdict(task, trace).mutations))

    @_vf.metric
    async def sampled_calls(self, trace: _vf.Trace) -> float:
        """Sampled calls: tool calls on sampled assistant messages only."""
        return float(sum(len(message.tool_calls or []) for message in trace.assistant_messages))

    @_vf.metric
    async def turns(self, trace: _vf.Trace) -> float:
        """Turns: the trace's own count of sampled nodes."""
        return float(trace.num_turns)

    @classmethod
    def toolsets(cls, config: ExportTaskConfig) -> list[_vf.Toolset]:
        """The domain toolset, which is task-scoped (one per rollout).

        A new toolset on every call: two rollouts of one task must not share a record or
        a counter.  A classmethod, so a consumer can size placement before any task
        instance exists.
        """
        return [DomainToolset(DomainToolsetConfig())]

    async def validate(self, runtime: _Any) -> bool:
        """G4: under *both* strictnesses, `verify` on `reference_calls` gives `passed`.

        Both, whatever the arm declares.  Under a leaky arm a reference that does
        collateral damage is labelled `passed` and still fails G4, because strict does
        not pass it -- and a leaky arm's tasks are compared with a strict arm's.

        `runtime` is unused, so this scores offline with `None`; 0.3.1's signature is a
        coroutine returning `bool`.
        """
        bundle = bundle_from_data(self.data)
        turns = tuple(
            _Turn(content="", calls=(call,), finish_reason="tool_calls")
            for call in bundle.reference_calls
        ) + (_Turn(content="", calls=(), finish_reason="stop"),)
        for strictness in ("strict", "leaky"):
            probe = _dc.replace(bundle, verifier=_VerifierSpec(strictness=strictness))
            verdict = _verify(probe, turns, True, False, _EXPORT_FORMAT)
            if verdict.label != "passed" or verdict.strict_label != "passed":
                return False
        return True


def task_from_bundle(bundle: _TaskBundle) -> ExportTask:
    """One generated bundle as one task.  `ExportTaskset.load` calls this once per seed.

    It does not re-check G4: generation already refuses a bundle that fails it, and
    `validate` is where the export says so.
    """
    return ExportTask(
        _data_from_bundle(bundle),
        ExportTaskConfig(strictness=bundle.verifier.strictness, arm_id=bundle.arm_id),
    )


# ---------------------------------------------------------------------------
# the taskset
# ---------------------------------------------------------------------------


# What a run with no arm or no seeds is told, in the command line's terms: `eval` is where a
# taskset gets iterated with nothing declared.  A caller of `load` in Python still meets
# `arm_spec`'s own refusal of a missing arm, which speaks to that caller.
_NO_ARM = (
    "no arm given: pass --env.taskset.arm with the arm's id, for example "
    "--env.taskset.arm depth:d3, or with its six fields as one JSON object, for "
    "example --env.taskset.arm '{\"knob\": \"depth\", \"level\": 3, \"control\": null, "
    "\"strictness\": \"strict\", \"split\": \"eval\", "
    f"\"generator_version\": \"{_DEFAULT_GENERATOR_VERSION}\"}}'"
)
_NO_SEEDS = (
    "no seeds given: pass --env.taskset.seeds with at least one seed, for example "
    "--env.taskset.seeds 404 55 2121, and each seed is one task"
)


class ExportTaskset(_vf.Taskset[ExportTask, ExportTasksetConfig]):
    """Finite: one task per declared seed, via `generate`.

    In the order declared, and in no other: nothing here reorders a measurement's tasks,
    and the module calls nothing named `shuffle` (X8).  `Taskset.shuffle` is an
    inherited view this class cannot remove, and `eval --shuffle` is the user's flag;
    what the measurement path iterates is the adapter's concern, not this class's.
    """

    INFINITE = False

    def __iter__(self) -> _Iterator[ExportTask]:
        """The wheel's iteration, refused when the config declares no arm or no seeds.

        A real `eval` run lists its taskset through here before it starts anything that could
        call a model, so the refusal comes before any model call.  It is here and not in the
        config, because `eval --dry-run` validates the config and must keep accepting both; and
        not in `load`, which yields nothing for an empty seed list (X8).  A view the wheel makes
        (`head`, `shuffle`) is a copy of this taskset and iterates through here too.
        """
        if not self.config.arm:
            raise ValueError(_NO_ARM)
        if not self.config.seeds:
            raise ValueError(_NO_SEEDS)
        tasks: _Iterator[ExportTask] = super().__iter__()
        return tasks

    def load(self) -> _Iterator[ExportTask]:
        arm = self.config.arm_spec()
        for seed in self.config.seeds:
            yield task_from_bundle(_generate(arm, seed))


# ---------------------------------------------------------------------------
# the toolset
# ---------------------------------------------------------------------------


class DomainToolsetConfig(_vf.ToolsetConfig):
    """The toolset takes no configuration: the task's data is the whole input, and it
    arrives through `setup_task`.  `ToolsetConfig`'s own `runtime` defaults to the
    subprocess one, so the server launches locally with nothing declared."""


class _EngineTool(_Tool):
    """A FastMCP tool that advertises the bundle's schema and is total over any call.

    `Tool.run` validates the arguments against the function's signature first, and a
    call refused there never reaches the body.  The engine's `apply` is total and advances
    `seq` on every call, errors included (E5), so a call that fails its own schema has
    to come back as the engine's numbered line and not as a FastMCP error: otherwise the
    live counter trails `replay` by one and every later observation differs, which
    the adapter's replay check would read as an instrument failure.
    """

    async def run(
        self,
        arguments: dict[str, _Any],
        context: _Any = None,
        convert_result: bool = False,
    ) -> _Any:
        observation = await self.fn(arguments)
        if convert_result:
            return self.fn_metadata.convert_result(observation)
        return observation


class DomainToolset(_vf.Toolset[DomainToolsetConfig, _vf.State]):
    """The toolset: the task's block, served over MCP, backed by the engine.

    `TOOL_PREFIX = None` advertises the names bare -- the block's names are the
    bundle's, and a `<server>_` prefix would rewrite the prompt's tool list.

    The engine state lives on this instance and not in `vf.State`: the
    wheel's state sync is last-write-wins around every call, and a chain of transitions
    does not compose under that.  Declaring a `State` subclass would also switch the
    sync on.
    """

    TOOL_PREFIX = None

    def __init__(self, config: DomainToolsetConfig) -> None:
        super().__init__(config)
        self._block: tuple[dict[str, _Any], ...] = ()
        self._shown: dict[str, _surface.Shown] = {}
        self._engine_state: _Any = None
        self._plan: dict[str, int] = {}
        self._kind: str | None = None
        self._stated: dict[str, str] | None = None
        self._spread: _surface._Spread | None = None
        self._counts: dict[str, int] = {}
        self._lock = _asyncio.Lock()

    async def setup_task(self, task: _Any) -> None:
        """Builds the engine state from the task data.

        `seq_start` included: a depth control's counter starts past 1, because its
        seeded history already spent the turns it stands in for.

        The block's names are what the model is shown; which engine tool each stands for
        is `surface.display_map`'s to say, read through the module as the verifier reads
        it, so the server answers a call exactly as the verifier will replay it.  A faults,
        timeouts or ratelimits arm's planned answers are `surface.reference_plan`'s, derived
        the same way and answered in the word `surface.fault_kind` gives the arm, keyed on
        how many times this server has been asked for each tool; every other arm plans none,
        and the counts start at nothing.  An arguments arm's stated values are
        `surface.stated_values`', read off the reference calls the task data carries, and
        every other arm has none.  A spread arm's named reads and their answers are
        `surface.spread_answers`', read off the reference calls and observations the task
        data carries, and every other arm has none.
        """
        self._block = tuple(dict(tool) for tool in task.tools)
        self._shown = _surface.display_map(
            task.seed,
            task.split,
            task.arm_id,
            tuple(task.goal),
            tuple(str(tool["name"]) for tool in self._block),
        )
        self._engine_state = _init_state(
            _scenario_for(task.seed, task.split), task.seq_start
        )
        reference = [(str(call[0]), call[1]) for call in task.reference_calls]
        self._plan = _surface.reference_plan(task.arm_id, self._shown, reference)
        self._kind = _surface.fault_kind(task.arm_id)
        self._stated = _surface.stated_values(task.arm_id, self._shown, reference)
        self._spread = _surface.spread_answers(
            task.arm_id, self._shown, reference, list(task.reference_observations)
        )
        self._counts = {}

    def register(self, mcp: _FastMCP) -> None:
        """The task's block, in slot order; the block is known because `setup_task` runs first.

        Not the base implementation: that discovers `@vf.tool`-decorated methods, and
        the block's names are not known until the task is.  Not `add_tool` either: it
        derives a schema from the body's signature, and X3 wants the bundle's exactly.
        """
        for spec in self._block:
            mcp._tool_manager._tools[str(spec["name"])] = self._tool(spec)

    def _tool(self, spec: dict[str, _Any]) -> _EngineTool:
        """One advertised tool, with the bundle's name, description and schema, applied
        to the engine under the engine's name for it."""
        name = str(spec["name"])
        description = str(spec["description"])
        engine = _surface.engine_name(self._shown, name)

        async def body(arguments: _Any) -> str:
            # An in-process lock: `apply` is pure, and the
            # counter lives in the state this coroutine reads and then writes, so two
            # calls that interleave between the two would take the same `seq` (E5).  The
            # planned failures, the named reads' answers and the argument check are applied
            # in front of the engine by the one function the verifier replays through, and
            # the engine step is handed in under this module's name for it, so every step the
            # server takes goes through `_apply` under the lock, planned arm or not.
            async with self._lock:
                state = self._engine_state
                after, counts, observation = _surface.apply_planned(
                    state,
                    self._counts,
                    (engine, arguments),
                    self._plan,
                    step=_apply,
                    stated=self._stated,
                    spread=self._spread,
                    **({"kind": self._kind} if self._kind is not None else {}),
                )
                self._engine_state = after
                self._counts = counts
                return observation

        derived = _Tool.from_function(body, name=name, description=description)
        return _EngineTool(
            fn=body,
            name=name,
            title=None,
            description=description,
            parameters=dict(spec["parameters"]),
            fn_metadata=derived.fn_metadata,
            is_async=True,
            context_kwarg=None,
            annotations=None,
        )


if __name__ == "__main__":
    # 0.3.1 launches a task-scoped tool server as `python -m <the toolset's module>`; the
    # child then fetches its task over the `/task` channel and registers the block.
    DomainToolset.run()
