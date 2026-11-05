"""What the 0.4.0 stale-data tests share: the two new knobs, the words their sentences carry, what
each level's answers hold, and the episodes the tests make.

The test files are `tests/test_bd_*.py`; each says in its own docstring what it pins and what it
decided.  Nothing here asserts anything.

Every name the build adds is read here by name, through `vars()` or a dictionary at call time and
never imported, so each test file collects on a tree that lacks them and each test fails there
because a name is missing or a value is wrong.  The built-in helpers are `tests/k3_support.py`'s, the
own-tools ones `tests/o2_support.py`'s and `tests/f2_support.py`'s, reused as they are.
"""

from __future__ import annotations

import dataclasses
import json
import re
from collections.abc import Sequence
from functools import lru_cache
from typing import Any

from poisson_tasks import surface
from poisson_tasks.arms import arm_from_id
from poisson_tasks.engine import EngineSpec, apply, init_state
from poisson_tasks.tasks import scenario_for
from tests.f2_support import loaded, stepped
from tests.k3_support import made, names, right
from tests.k4_support import SPLITS as CARD
from tests.o2_support import fixture_sets, generator, simulator

SPEC = EngineSpec.load()
LEVELS = (0, 1, 2, 3)
ABOVE_ZERO = (1, 2, 3)
OWN_SEEDS = (404, 55, 2121)
LETTERS = {"baddata": "b", "lagged": "g"}

# The sentences, word for word with their backticks (the spec's section 6.2).
BUILT_IN_SENTENCE = "A read can come back `ok` with a value that is out of date or wrong."
OWN_CLAUSE_BADDATA = "A read may answer with a value that is out of date or wrong."
OWN_CLAUSE_LAGGED = "A read may answer with a record as it was before your last write."
OWN_CLAUSE_TODAY = "A call may answer that the tool is unavailable; make the same call again."

# What each set reaches (the spec's section 5.1).
BADDATA_REACH = {
    "acme-mcp": (0, 1, 2, 3),
    "acme-openai": (0, 1, 2, 3),
    "acme-openapi-3.0": (0, 1, 2, 3),
    "acme-openapi-3.1": (0, 1, 2, 3),
    "petstore": (0, 2, 3),
    "everything": (0, 1, 2, 3),
}
LAGGED_REACH = {
    "acme-mcp": (),
    "acme-openai": (0, 1),
    "acme-openapi-3.0": (),
    "acme-openapi-3.1": (),
    "petstore": (0, 1),
    "everything": (),
}
SET_LABELS = tuple(BADDATA_REACH)
LAGGED_SETS = tuple(label for label, reach in LAGGED_REACH.items() if reach)
BADDATA_CASES = tuple(
    (label, level) for label, reach in BADDATA_REACH.items() for level in reach
)
BADDATA_BAD_CASES = tuple((label, level) for label, level in BADDATA_CASES if level)

# The three sentences of the spec's section 5.3, word for word, each under its name in the own
# generator, and the row `doctor` prints it under.
NEEDS = {
    "BADDATA_NEEDS_A_CARRIER": (
        "carrier read",
        "Bad data needs a read whose answer holds a value a write then takes, so baddata needs a "
        "read tool with a checkable argument and a write with a checkable argument that read's "
        "answer has a field for. This set has none.",
    ),
    "BADDATA_NEEDS_A_NAMED_KEY": (
        "named key",
        "Level 1 of baddata needs a read whose answer names what it was asked for. This set's "
        "answers do not, so it reaches 0, 2 and 3.",
    ),
    "LAGGED_NEEDS_A_SHOWING_READ": (
        "showing read",
        "A read that lags a write can only be told from a write that failed if a later read shows "
        "the write, so lagged needs a read tool that takes one of the target write's arguments and "
        "whose answer shows another of them. This set has none.",
    ),
}

# The reasons `arms.EXPERIMENTAL_KNOBS` gives (the spec's section 8).
NOT_MEASURED = "no model has been measured on it yet"
DID_NOT_BITE = "it did not make tasks harder for either calibrated model"
EXPERIMENTAL_REASONS = {
    "distractor": DID_NOT_BITE,
    "timeouts": NOT_MEASURED,
    "ratelimits": NOT_MEASURED,
    "landed": NOT_MEASURED,
    "baddata": NOT_MEASURED,
    "lagged": NOT_MEASURED,
}

# The names the build adds, read by name.
ACTED = "acted_on_bad_data"
READ_AGAIN = "read_again_after_bad"
COLUMNS = ("acted on bad data", "read again after a bad answer")
TRUSTED = "wrong_state_trusted"
SPREAD_ANSWERS = "spread_answers"
APPLY_PLANNED = "apply_planned"


def figure(record: Any, name: str) -> Any:
    """A record's field by name."""
    return vars(record)[name]


def figures(record: Any) -> tuple[Any, Any]:
    """A record's two new fields: acted on bad data, and read again after a bad answer."""
    return figure(record, ACTED), figure(record, READ_AGAIN)


def needs(name: str) -> str:
    """One of the own generator's three new sentences."""
    return str(vars(generator())[name])


# --------------------------------------------------------------------------
# the built-in tasks
# --------------------------------------------------------------------------


def arm(level: int) -> str:
    return f"baddata:b{level}"


def baddata(level: int, seed: int, split: str = "eval") -> Any:
    return made(arm(level), seed, split)


def card_seeds() -> list[tuple[str, int]]:
    """The sixty published seeds on eval and twelve on train (the spec's section 10.1)."""
    return [(split, seed) for split, seeds in CARD for seed in seeds]


def line_of(number: int, status_word: str, payload: str) -> str:
    """The engine's layout at `number`."""
    layout = SPEC.layout
    return str(layout["separator"]).join(
        (
            str(number).rjust(int(layout["seq_width"]), str(layout["seq_fill"])),
            status_word.ljust(int(layout["status_width"]), str(layout["status_fill"])),
            payload,
        )
    )


def word_of(item_or_record: str) -> str:
    """The first word of a catalogue item or a record id."""
    return item_or_record.split(str(SPEC.table["record_id_separator"]))[0]


def telling(record: str, other: str) -> str:
    """As many of the id's words, from the first, as tell it from the other's (section 1.3)."""
    separator = str(SPEC.table["record_id_separator"])
    words, others = record.split(separator), other.split(separator)
    for count in range(1, len(words) + 1):
        if words[:count] != others[:count]:
            return separator.join(words[:count])
    raise AssertionError((record, other))


def target_and_decoy(bundle: Any) -> tuple[str, str]:
    """The goal's record, and the other record of its ledger in the scenario."""
    ledger, target, _stage = bundle.goal
    others = [record for (held, record) in scenario_for(bundle.seed, bundle.split).records
              if held == ledger and record != target]
    (decoy,) = others
    return str(target), str(decoy)


def is_read(call: tuple[str, Any]) -> bool:
    return call[0] in SPEC.read_tools


def read_pairs(bundle: Any) -> list[tuple[tuple[str, Any], str]]:
    """Each read call of the reference, with its observation, in the reference's order."""
    return [
        (call, observation)
        for call, observation in zip(bundle.reference_calls, bundle.reference_observations,
                                     strict=True)
        if is_read(call)
    ]


def payload_of(observation: str) -> str:
    return observation.split()[2]


def parts_of(observation: str) -> tuple[str, str, str]:
    """A named read's payload as `<item word>/<head>.<hex>` holds it: the three parts."""
    held = re.fullmatch(r"([^/.\s]+)/([^/.\s]+)\.([0-9a-f]+)", payload_of(observation))
    assert held is not None, observation
    return held.group(1), held.group(2), held.group(3)


def the_two_reads(bundle: Any) -> tuple[tuple[str, Any], tuple[str, Any]]:
    """The two reads, once each, in the reference's order: the record's, then the stage's."""
    seen: list[tuple[str, Any]] = []
    for call, _observation in read_pairs(bundle):
        if call not in seen:
            seen.append(call)
    first, second = seen
    return first, second


def bad_read(bundle: Any) -> tuple[str, Any]:
    """The read the reference makes twice, above level 0."""
    calls = [call for call, _observation in read_pairs(bundle)]
    (twice,) = [call for index, call in enumerate(calls) if call in calls[index + 1:]]
    return twice


def stage_calls_on(bundle: Any, record: str) -> list[tuple[str, Any]]:
    """The two stage calls B's reference makes, on `record`, with the token the ledger answers."""
    (first, first_args), (second, second_args) = right(bundle)
    record_param = SPEC.parameter_names["record"]
    token_param = SPEC.parameter_names["token"]
    state = init_state(scenario_for(bundle.seed, bundle.split), 1)
    opening = {**first_args, record_param: record}
    _state, line = apply(state, (first, opening))
    return [(first, opening), (second, {**second_args, record_param: record,
                                        token_param: payload_of(line)})]


def another_page(call: tuple[str, Any]) -> tuple[str, Any]:
    """The same read on another page."""
    name, args = call
    page_param = SPEC.parameter_names["page"]
    other = next(page for page in sorted(SPEC.page_keys) if page != args[page_param])
    return name, {**args, page_param: other}


def replayed(bundle: Any, calls: Sequence[tuple[str, Any]]) -> list[str]:
    """Each call's answer through `surface.apply_planned`, as the readers derive what it is handed:
    the fast way to the answers.  The tool server is `tests/k3_support.py`'s `answers`."""
    shown = surface.display_map(bundle.seed, bundle.split, bundle.arm_id, bundle.goal,
                                names(bundle))
    plan = surface.reference_plan(bundle.arm_id, shown, bundle.reference_calls)
    spread = vars(surface)[SPREAD_ANSWERS](bundle.arm_id, shown, bundle.reference_calls,
                                           bundle.reference_observations)
    state = init_state(scenario_for(bundle.seed, bundle.split), bundle.seq_start)
    counts: dict[str, int] = {}
    out = []
    for name, args in calls:
        state, counts, line = vars(surface)[APPLY_PLANNED](
            state, counts, (surface.engine_name(shown, name), args), plan, spread=spread
        )
        out.append(line)
    return out


def changed_reference(bundle: Any, calls: Sequence[tuple[str, Any]],
                      payloads: Sequence[str]) -> Any:
    """`bundle` with a reference whose read calls are `calls` answering `payloads`, numbered from
    the task's start, and B's two stage calls after them: a planted reference, for the ledger."""
    observations = [line_of(bundle.seq_start + index, "ok", payload)
                    for index, payload in enumerate(payloads)]
    stage_lines = [
        line_of(bundle.seq_start + len(calls) + index, "ok", payload_of(observation))
        for index, observation in enumerate(bundle.reference_observations[-2:])
    ]
    return dataclasses.replace(
        bundle,
        reference_calls=(*calls, *bundle.reference_calls[-2:]),
        reference_observations=(*observations, *stage_lines),
    )


# --------------------------------------------------------------------------
# own tools
# --------------------------------------------------------------------------


@lru_cache(maxsize=256)
def own_arm(knob: str, level: int, strictness: str = "strict") -> Any:
    """An own-tools arm of a new knob, at the own generator's label."""
    return arm_from_id(
        f"{knob}:{LETTERS[knob]}{level}", strictness=strictness, split="eval",
        generator_version=generator().GENERATOR_VERSION,
    )


def own_task(label_or_set: Any, knob: str, level: int, seed: int, **kwargs: Any) -> Any:
    toolset = (fixture_sets()[label_or_set] if isinstance(label_or_set, str) else label_or_set)
    return generator().generate(toolset, own_arm(knob, level, **kwargs), seed)


@dataclasses.dataclass(frozen=True)
class Carried:
    """What a baddata task carries, read off its steps and its reference: the read's call, the
    write's call, the carried argument, the field of the read's answer that holds it, and the true
    value there."""

    read: tuple[str, dict[str, Any]]
    write: tuple[str, dict[str, Any]]
    argument: str
    field: str
    value: Any
    keys: tuple[str, ...]


def carried(bundle: Any) -> Carried:
    (read_step,) = [step for step in bundle.steps if step["effect"] == "read"]
    ((field, value),) = read_step["serves"]
    read = next(call for call in bundle.reference_calls if call[0] == read_step["tool"])
    write = bundle.reference_calls[-1]
    stated = {name for name, _value in bundle.stated}
    (argument,) = [name for name in write[1] if name not in stated]
    return Carried((read[0], dict(read[1])), (write[0], dict(write[1])), argument, str(field), value,
                   tuple(read_step["match"]))


def output_properties(bundle: Any, tool: str) -> dict[str, Any] | None:
    """The tool's output schema's properties, or `None` where it has no output schema."""
    schema = dict(bundle.output_schemas).get(tool)
    if schema is None:
        return None
    properties = schema.get("properties")
    return dict(properties) if isinstance(properties, dict) else {}


def input_properties(bundle: Any, tool: str) -> dict[str, Any]:
    (shown,) = [held for held in bundle.tools if held["name"] == tool]
    return dict(shown["parameters"].get("properties") or {})


def echoes(bundle: Any, read: str, key: str) -> bool:
    """Whether a read's answer has a place for the key it was asked: the same-named output
    property, or the top level where it has no output schema (section 1.3)."""
    properties = output_properties(bundle, read)
    return properties is None or key in properties


def answers_of(bundle: Any, calls: Sequence[tuple[str, Any]]) -> list[Any]:
    """The simulator's answer to each call, loaded where it is JSON."""
    _state, answers = stepped(bundle, list(calls))
    return [loaded(answer) for answer in answers]


def is_near(schema: Any, true: Any, bad: Any) -> bool:
    """The smallest change that conforms (section 1.1): a number off by one or by a half, a string
    with its last character changed, another member of an enum."""
    if isinstance(schema, dict) and isinstance(schema.get("enum"), list):
        return bad in schema["enum"] and bad != true
    if isinstance(true, int | float):
        return abs(bad - true) in (1, 0.5)
    return bool(isinstance(true, str) and isinstance(bad, str) and len(bad) == len(true)
                and bad[:-1] == true[:-1] and bad != true)


def has_a_third_value(schema: Any) -> bool:
    return not (isinstance(schema, dict) and isinstance(schema.get("enum"), list)
                and len(schema["enum"]) < 3)


def canonical_write(call: tuple[str, Any]) -> tuple[str, str]:
    """A write as `State.writes` holds it."""
    return call[0], str(simulator().canonical(call[1]))


def compact(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))
