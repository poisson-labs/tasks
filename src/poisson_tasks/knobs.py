"""The knobs, control arms and the pin ledger: a declared ledger, and the two measurements
a bundle supports.

The invariants this file is built against are N1-N18, tested in `tests/test_tg_m2_knobs.py`;
where a requirement could not be used as written, that file's module docstring is
authoritative.

The public surface is the interface's names plus the three type names its signatures use,
and nothing else.  "Both knobs' transforms" are reached through `ArmSpec`'s derived values
and through `check_pins`, never as symbols of their own.

Shapes the requirements name but do not define, decided here:

* **`ArmSpec.control` is the reference level, not a flag.**  It holds the level the
  control stands in for -- `8` in `depth:d1+h8` and in `distractor:r0+len(r8)@k16` -- and
  `None` on a plain arm.  The arm id formats forced it: each control id renders exactly
  that one extra number.
* **Validation lives in `ArmSpec.__post_init__`.**  N15's own words are that `d3+h3` and
  `d8+h1` are "construction errors rather than arms that generate and then fail a pin", so
  an arm spec that cannot be rendered cannot be built.  The knob and the control relation
  are checked; **the level is not checked against `levels(knob)`**, because those are the
  *candidate* levels, and the choice among them belongs to a study's pre-registration, not
  here.  The escape hatch, if a later module wants an arm spec it
  validates itself, is to move both checks into `arm_id` -- which every test that exercises
  them already calls.
* **A refusal is a `PinReport` that says so.**  The interface is
  `check_pins(...) -> PinReport | refusal`; the ledger's job is to report and the *On
  violation* column says **generation** refuses, so `refused` is a field and not an
  exception.  `check_pins` raises `ValueError` only for a caller error -- arms from two
  knobs, or fewer than two arms -- because a caller error is not a pin violation and must
  not come back as one.
* **`PinRow` carries `stage` and `applies_to`.**  The ledger's *On violation* column states
  where a row is enforced in prose, and a caller cannot act on prose.  `applies_to` names
  the knobs a row constrains: N4 is knob D's, N5 is knob R's, and N9 is knob D's because
  only knob D's control seeds history at all.
* **The arm id is parsed back in `check_pins`.**  A bundle carries an `arm_id` string and
  no arm spec, so the knob CP1 refuses on and the `(dL, H)` pair N9 compares are read off
  the key.  `_render_arm_id` is the one renderer, used by `arm_id` and by N9's lookup of
  the high arm, so the two can never disagree.

`measure_pins` is a read: it never writes to the bundle it is handed (P3).  Every entry
point is pure -- no clock, no RNG, no IO beyond the frozen vocabulary table the engine
already loads, and no network (SF5).  `L_obs` and the token band are the engine's
literals, cited here and never re-minted (SF6).
"""

from __future__ import annotations

import hashlib as _hashlib
import json as _json
import re as _re
from collections.abc import Mapping as _Mapping
from dataclasses import dataclass as _dataclass
from typing import Any as _Any
from typing import Protocol as _Protocol

from poisson_tasks.engine import EngineSpec as _EngineSpec
from poisson_tasks.tokenizer import count_tokens as _count_tokens
from poisson_tasks.tokenizer import reference_encoding as _reference_encoding

__all__ = [
    "ArmSpec",
    "PinRow",
    "PinRecord",
    "PinReport",
    "arm_id",
    "levels",
    "pin_ledger",
    "measure_pins",
    "check_pins",
]

# The engine's frozen literals, cited and not re-minted (SF6).  `L_obs` and the token band are
# properties of the vocabulary table; a second copy here would be a number read back and
# compared with itself.
_SPEC = _EngineSpec.load()
_L_OBS = _SPEC.L_obs
_BAND_LO, _BAND_HI = _SPEC.table["token_band"]

_DEPTH = "depth"
_DISTRACTOR = "distractor"
_KNOBS = (_DEPTH, _DISTRACTOR)

# Candidate levels, not the pilot defaults: the pilot picks {1, 3, 8} for depth, and that
# choice lives in its pre-registration.
_DEPTH_LEVELS = (1, 2, 3, 5, 8)
_DISTRACTOR_LEVELS = (0, 2, 4, 8, 14)
_LEVELS = {_DEPTH: _DEPTH_LEVELS, _DISTRACTOR: _DISTRACTOR_LEVELS}

# The fixed block sizes, and knob R's fixed chain depth.
_K_D = 16
_K_R = 16
_D_R = 2

# N9's declared band, in reference-tokenizer tokens, over the aggregate.  Minted with
# the tests, at a measured residual of 0 over 256 blocks of seven pairs across two disjoint
# scenarios; the same two-token margin, and the same empirical footing, as the engine's
# observation band.  It is an aggregate and explicitly not a per-pair equality: 51.4% of
# chain calls are cheaper on arguments than any read call and 3.0% of chain pairs fall
# below the read pair floor, so a per-pair equality could never pass.
_N9_BAND = 2

_REFUSE = "refuse"
_REPORT = "report"
_ENGINE_TEST = "engine_test"
_STOP_RUN = "stop_run"
_REFUSE_START = "refuse_start"
_VOID_CONTRAST = "void_contrast"

_GENERATION = "generation"
_ENGINE = "engine"
_ADAPTER = "adapter"
_ANALYSIS = "analysis"

_BOTH = (_DEPTH, _DISTRACTOR)

_DEPTH_ID = _re.compile(r"^depth:d(\d+)(?:\+h(\d+))?$")
_DISTRACTOR_ID = _re.compile(r"^distractor:r(\d+)(?:\+len\(r(\d+)\))?@k(\d+)$")


class _Verifier(_Protocol):
    """`tasks.VerifierSpec`, reduced to the one field N11 reads."""

    strictness: str


class _Bundle(_Protocol):
    """The bundle fields the ledger reads.

    `tasks.py` owns `TaskBundle` and imports this module, so this states the shape rather
    than naming the type.  Without `template_id`, `prompt_slots` and
    `reference_observations`, N6 and N9 have no measurement.
    """

    arm_id: str
    scenario_hash: str
    system_prompt: str
    prompt: object
    tools: tuple[_Any, ...]
    reference_calls: tuple[_Any, ...]
    reference_observations: tuple[_Any, ...]
    verifier: _Verifier
    engine_hash: str
    generator_hash: str
    template_id: str
    prompt_slots: tuple[_Any, ...]


@_dataclass(frozen=True)
class ArmSpec:
    """An arm: `(knob, level, control, strictness, split, generator version)`.

    Six fields and no seventh: `S` is a run's configuration axis and `seq_start` is an
    argument to `init_state`, so neither belongs here.
    """

    knob: str
    level: int
    control: int | None
    strictness: str
    split: str
    generator_version: str

    def __post_init__(self) -> None:
        if self.knob not in _KNOBS:
            raise ValueError(f"unknown knob {self.knob!r}: the v0 knobs are {_KNOBS}")
        if self.control is not None and self.control <= self.level:
            raise ValueError(
                f"a control stands in for a higher level: {self.knob} d{self.level} "
                f"against h{self.control} seeds nothing or a negative number of pairs"
            )

    @property
    def reference_turns(self) -> int:
        """N16's minimum: one call per turn, plus the reply turn.

        Depth level `d` needs `d + 1`; every R level needs `d_R + 1`.  The depth control
        follows its own `dL` and never the level it stands in for, because seeded history
        uses no turns.
        """
        if self.knob == _DEPTH:
            return self.level + 1
        return _D_R + 1

    def max_turns(self, slack: int) -> int:
        """N16's budget: the needed turns plus one slack constant `S`.

        `S` is a run's configuration axis and not one of the six fields, so it is an argument here;
        A5 writes `max_turns(arm)` as though it were nullary.
        """
        return self.reference_turns + slack


@_dataclass(frozen=True)
class PinRow:
    """One ledger row.

    `stage` is where the row is enforced and `on_violation` is what happens when it
    fails; the ledger's table states both in one prose column, and a caller cannot act on
    prose.  `applies_to` is the knobs the row constrains.
    """

    row_id: str
    held: str
    measured: str
    tolerance: str
    on_violation: str
    stage: str
    applies_to: tuple[str, ...]


@_dataclass(frozen=True)
class PinRecord:
    """One bundle's measurements.

    `values` maps a row id to its measured value; `unmeasured` maps a row id to the reason
    it cannot be measured from a bundle at generation time.  Every ledger row appears in
    exactly one of the two, so a row nobody checks is impossible to write.
    """

    arm_id: str
    values: dict[str, _Any]
    unmeasured: dict[str, str]


@_dataclass(frozen=True)
class PinReport:
    """The artefact a pre-registration files.

    `violations` and `reported` are `(row_id, detail)` pairs in ledger order.  `refused`
    is true when any violated row's action is something other than `report`; N5 is the
    only reporting row, and collapsing the five actions to a boolean is exactly where
    that distinction gets lost, which is why the rows keep their own.
    """

    knob: str
    refused: bool
    violations: tuple[tuple[str, str], ...]
    reported: tuple[tuple[str, str], ...]
    records: dict[str, PinRecord]


@_dataclass(frozen=True)
class _ParsedArm:
    """What an arm id renders, read back: the knob, the level and the reference level."""

    knob: str
    level: int
    control: int | None


def _render_arm_id(knob: str, level: int, control: int | None) -> str:
    """The four arm id formats, and the only place any of them is written."""
    if knob == _DEPTH:
        return f"depth:d{level}" if control is None else f"depth:d{level}+h{control}"
    if control is None:
        return f"distractor:r{level}@k{_K_R}"
    return f"distractor:r{level}+len(r{control})@k{_K_R}"


def _parse_arm_id(rendered: str) -> _ParsedArm:
    """The inverse of `_render_arm_id`.

    A bundle carries an arm id and no arm spec, so `check_pins` reads the knob and the
    `(dL, H)` pair off the key.  The `@k` field is parsed and not enforced: the block is
    fixed at 16 and the renderer is the only thing that writes it.
    """
    depth = _DEPTH_ID.match(rendered)
    if depth is not None:
        high = depth.group(2)
        return _ParsedArm(_DEPTH, int(depth.group(1)), None if high is None else int(high))
    distractor = _DISTRACTOR_ID.match(rendered)
    if distractor is not None:
        high = distractor.group(2)
        return _ParsedArm(
            _DISTRACTOR, int(distractor.group(1)), None if high is None else int(high)
        )
    raise ValueError(f"{rendered!r} is not an arm id 2.2 defines")


def arm_id(spec: ArmSpec) -> str:
    """The canonical id of an arm.

    Canonical means one id per `(knob, level, control)`.  Strictness, split and generator
    version are pinned by N11, G12 and N12 and do not enter the id: an id that rendered
    all six fields would silently break `diff`'s cell matching.
    """
    return _render_arm_id(spec.knob, spec.level, spec.control)


def levels(knob: str) -> tuple[int, ...]:
    """The knob's candidate levels, never the pilot's chosen subset."""
    if knob not in _LEVELS:
        raise ValueError(f"unknown knob {knob!r}: the v0 knobs are {_KNOBS}")
    return _LEVELS[knob]


def pin_ledger(knob: str) -> list[PinRow]:
    """The thirteen rows, in the ledger's order.

    The same ledger is used for both knobs, so the row set does not vary with the knob;
    what varies is `applies_to`, which `check_pins` reads to decide whether a row is
    evaluated for this contrast.
    """
    if knob not in _LEVELS:
        raise ValueError(f"unknown knob {knob!r}: the v0 knobs are {_KNOBS}")
    return [
        PinRow(
            row_id="N1",
            held="Scenario (every seed-drawn field)",
            measured="`scenario_hash` of the same seed generated under every arm of the knob",
            tolerance="equal",
            on_violation=_REFUSE,
            stage=_GENERATION,
            applies_to=_BOTH,
        ),
        PinRow(
            row_id="N2",
            held="Required-tool slot positions",
            measured=(
                "slot indices per seed, across arms: the name and the index of every tool "
                "the reference solution calls, compared on the tools two arms share"
            ),
            tolerance="equal",
            on_violation=_REFUSE,
            stage=_GENERATION,
            applies_to=_BOTH,
        ),
        PinRow(
            row_id="N3",
            held="System prompt",
            measured=(
                "sha256 across arms.  The only permitted difference is the R control "
                "filler, which is appended at the end, so it is a suffix of a plain arm's"
            ),
            tolerance="equal",
            on_violation=_REFUSE,
            stage=_GENERATION,
            applies_to=_BOTH,
        ),
        PinRow(
            row_id="N4",
            held="Tool block (knob D)",
            measured="sha256 of the rendered schemas in slot order, across levels",
            tolerance=f"equal; the block is K_D = {_K_D} tools, identical at every level",
            on_violation=_REFUSE,
            stage=_GENERATION,
            applies_to=(_DEPTH,),
        ),
        PinRow(
            row_id="N5",
            held="Tool-block token count (knob R)",
            measured="reference tokenizer, per arm",
            tolerance=(
                "declared band, fixed in the pre-registration; the difference is reported "
                "and never refused, because knob R's block must change by definition"
            ),
            on_violation=_REPORT,
            stage=_GENERATION,
            applies_to=(_DISTRACTOR,),
        ),
        PinRow(
            row_id="N6",
            held="User prompt",
            measured=(
                "template id equal; token count of the variable slots under the reference "
                "tokenizer, both read from the bundle's `template_id` and `prompt_slots` "
                "(2.3, TG-ADR-38)"
            ),
            tolerance="equal; the slot values are free and the goal stage name is the knob",
            on_violation=_REFUSE,
            stage=_GENERATION,
            applies_to=_BOTH,
        ),
        PinRow(
            row_id="N7",
            held="Prompt-to-tool-name lexical overlap",
            measured=(
                "the set of user-instruction tokens that occur in any tool name, across "
                "arms.  The user instruction only: a D control's seeded history names "
                "tools it did not choose"
            ),
            tolerance="equal",
            on_violation=_REFUSE,
            stage=_GENERATION,
            applies_to=_BOTH,
        ),
        PinRow(
            row_id="N8",
            held="Observation size",
            measured="E2, over the bundle's `reference_observations` (2.3, TG-ADR-38)",
            tolerance=(
                f"L_obs == {_L_OBS} bytes exact; tokens in [{_BAND_LO}, {_BAND_HI}].  A "
                "per-arm property: d1 and d8 carry different numbers of observations, so "
                "a cross-arm equality would refuse a clean contrast"
            ),
            on_violation=_ENGINE_TEST,
            stage=_ENGINE,
            applies_to=_BOTH,
        ),
        PinRow(
            row_id="N9",
            held="Seeded history (control arms)",
            measured=(
                "reference-tokenizer tokens of the seeded pairs vs the expected (H - dL) "
                "stage pairs, which are the bundle's `reference_calls` paired with its "
                "`reference_observations` (2.3, TG-ADR-38)"
            ),
            tolerance=(
                f"declared band of +/- {_N9_BAND} tokens on the **aggregate** over the "
                "(H - dL) pairs, at a measured residual of 0.  Never a per-pair equality: "
                "that is unsatisfiable against this table (TG-ADR-37)"
            ),
            on_violation=_REFUSE,
            stage=_GENERATION,
            applies_to=(_DEPTH,),
        ),
        PinRow(
            row_id="N10",
            held=(
                "The serving pin (A14): model id and revision (N18); vLLM version and "
                "serve flags (parser, reasoning parser, quantization, --max-model-len, "
                "--language-model-only); thinking mode; decoding settings; GPU type.  Also "
                "the harness id and version, endpoint type, slack S, horizon H, token "
                "limits and runtime type"
            ),
            measured=(
                "cfg (single-valued axes, one sweep file per model), the arm spec, and the "
                "serving-pin hash in every episode's `meta`"
            ),
            tolerance="equal across all of a model's runs",
            on_violation=_STOP_RUN,
            stage=_ADAPTER,
            applies_to=_BOTH,
        ),
        PinRow(
            row_id="N11",
            held="Verifier strictness",
            measured="arm spec, carried on the bundle's verifier",
            tolerance="equal",
            on_violation=_REFUSE_START,
            stage=_ADAPTER,
            applies_to=_BOTH,
        ),
        PinRow(
            row_id="N12",
            held="Engine, vocabulary and generator hashes",
            measured=(
                "recorded per task.  The vocabulary is inside `engine_hash` by E10, so two "
                "bundle fields carry three hashes"
            ),
            tolerance="equal",
            on_violation=_REFUSE_START,
            stage=_ADAPTER,
            applies_to=_BOTH,
        ),
        PinRow(
            row_id="N13",
            held="Realised first-request input tokens, per model",
            measured="server-reported usage from the trace, per episode",
            tolerance="pre-registered band",
            on_violation=_VOID_CONTRAST,
            stage=_ANALYSIS,
            applies_to=_BOTH,
        ),
    ]


def _compact(arguments: _Any) -> str:
    """A call's arguments as the wire carries them: one compact JSON object.

    A seeded history already holds the serialised form, because that is what an
    OpenAI-compatible chat completion sends; a reference call holds the mapping.
    """
    if isinstance(arguments, str):
        return arguments
    return _json.dumps(arguments, separators=(",", ":"))


def _pair_tokens(name: str, arguments: _Any, observation: str) -> int:
    """One `(assistant tool call, tool observation)` pair, in reference-tokenizer tokens.

    The tool name counted bare, the arguments as one compact JSON object, the observation
    as it stands.  This is N9's unit and the only place it is defined.
    """
    return _count_tokens(name) + _count_tokens(_compact(arguments)) + _count_tokens(observation)


def _messages(prompt: object) -> tuple[_Any, ...]:
    """The prompt as `Messages`, or empty when it is a plain string (`str | Messages`)."""
    if isinstance(prompt, (list, tuple)):
        return tuple(prompt)
    return ()


def _user_instruction(prompt: object) -> str:
    """The user instruction, and never the seeded history.

    N7 is measured over this alone.  A D control's seeded pairs name the read tools it was
    given, so an overlap set read from the whole prompt would refuse every control arm on
    history the model did not write.
    """
    if isinstance(prompt, str):
        return prompt
    parts = [
        str(message.get("content", ""))
        for message in _messages(prompt)
        if isinstance(message, _Mapping) and message.get("role") == "user"
    ]
    return "\n".join(parts)


def _seeded_pairs(prompt: object) -> tuple[tuple[str, _Any, str], ...]:
    """The seeded `(assistant tool call, tool observation)` pairs of a `Messages` prompt.

    The shape is the OpenAI chat shape, because N18 pins the endpoint type to
    OpenAI-compatible chat completions: an assistant message carrying `tool_calls`,
    then the `tool` message holding that call's observation.
    """
    pending: list[tuple[str, _Any]] = []
    pairs: list[tuple[str, _Any, str]] = []
    for message in _messages(prompt):
        if not isinstance(message, _Mapping):
            continue
        role = message.get("role")
        if role == "assistant":
            for call in message.get("tool_calls") or ():
                function = call.get("function", {}) if isinstance(call, _Mapping) else {}
                pending.append((str(function.get("name", "")), function.get("arguments", "")))
        elif role == "tool" and pending:
            name, arguments = pending.pop(0)
            pairs.append((name, arguments, str(message.get("content", ""))))
    return tuple(pairs)


def _instruction_tokens(text: str) -> tuple[str, ...]:
    """The user instruction's reference-tokenizer tokens, as the strings they stand for."""
    encoding = _reference_encoding()
    pieces: list[str] = []
    for token in encoding.encode_ordinary(text):
        piece = encoding.decode([token]).strip().lower()
        if piece:
            pieces.append(piece)
    return tuple(pieces)


def _tool_names(tools: tuple[_Any, ...]) -> tuple[str, ...]:
    return tuple(str(tool["name"]) for tool in tools)


def _lexical_overlap(instruction: str, tools: tuple[_Any, ...]) -> tuple[str, ...]:
    """N7's set: the instruction tokens that occur in any tool name, sorted."""
    names = tuple(name.lower() for name in _tool_names(tools))
    overlap = {
        piece for piece in _instruction_tokens(instruction) if any(piece in name for name in names)
    }
    return tuple(sorted(overlap))


def _rendered_block(tools: tuple[_Any, ...]) -> str:
    """The tool block as N4 and N5 read it: the schemas in slot order, canonically.

    Keys are sorted at every depth, so two blocks built by different insertion orders
    render the same string and neither hash nor token count moves with `PYTHONHASHSEED`.
    """
    return _json.dumps(list(tools), sort_keys=True, separators=(",", ":"))


def measure_pins(bundle: _Bundle) -> PinRecord:
    """Measure every ledger row a bundle can answer, and name the reason for the rest.

    Eleven rows are measurable from a bundle.  Only N10 and N13 need something no bundle
    carries -- a cfg and an episode's `meta` for the serving pin, and the trace for
    realised tokens -- and each of those gets a reason rather than a silent absence.

    This is a read.  Nothing on the bundle is written, so a caller may measure one bundle
    under two ledgers (P3).
    """
    tools = tuple(bundle.tools)
    observations = tuple(str(observation) for observation in bundle.reference_observations)
    rendered = _rendered_block(tools)

    required = {str(call[0]) for call in bundle.reference_calls}
    slots = tuple(bundle.prompt_slots)
    widths = tuple(sorted({len(observation.encode("utf-8")) for observation in observations}))
    counts = tuple(_count_tokens(observation) for observation in observations)

    seeded = _seeded_pairs(bundle.prompt)
    if seeded:
        # A control arm: N9's unit is the seeded pair, one total per pair, so `check_pins`
        # sums and nothing else has to.
        pairs = tuple(_pair_tokens(name, arguments, obs) for name, arguments, obs in seeded)
    else:
        pairs = tuple(
            _pair_tokens(str(name), arguments, observation)
            for (name, arguments), observation in zip(
                bundle.reference_calls, observations, strict=False
            )
        )

    values: dict[str, _Any] = {
        "N1": str(bundle.scenario_hash),
        "N2": tuple(
            sorted(
                (str(tool["name"]), index)
                for index, tool in enumerate(tools)
                if str(tool["name"]) in required
            )
        ),
        "N3": str(bundle.system_prompt),
        "N4": _hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
        "N5": _count_tokens(rendered),
        "N6": (
            str(bundle.template_id),
            tuple(_count_tokens(str(value)) for _name, value in slots),
        ),
        "N7": _lexical_overlap(_user_instruction(bundle.prompt), tools),
        "N8": (widths, (min(counts), max(counts)) if counts else (0, 0)),
        "N9": pairs,
        "N11": str(bundle.verifier.strictness),
        "N12": (str(bundle.engine_hash), str(bundle.generator_hash)),
    }
    unmeasured = {
        "N10": (
            "the serving pin is cfg, the arm spec and the serving-pin hash in every "
            "episode's `meta` (A14); a bundle carries none of the three, so the row is "
            "enforced when the adapter starts and not at generation"
        ),
        "N13": (
            "server-reported usage exists only once an episode has run; a bundle carries "
            "no trace, so the row is enforced at analysis against the pre-registered band "
            "(KC3)"
        ),
    }
    return PinRecord(arm_id=str(bundle.arm_id), values=values, unmeasured=unmeasured)


def _detail(arm_ids: tuple[str, ...], records: dict[str, PinRecord], row_id: str) -> str:
    """One row's measured value per arm, in arm-id order."""
    return ", ".join(f"{arm}={records[arm].values[row_id]!r}" for arm in arm_ids)


def _equal_across_arms(
    arm_ids: tuple[str, ...], records: dict[str, PinRecord], row_id: str
) -> str | None:
    """The shape most rows take: one measured value, held equal across every arm."""
    seen = {records[arm].values[row_id] for arm in arm_ids}
    if len(seen) <= 1:
        return None
    return f"not equal across arms: {_detail(arm_ids, records, row_id)}"


def _check_n2(arm_ids: tuple[str, ...], records: dict[str, PinRecord]) -> str | None:
    """N2 on the tools two arms share.

    Name *and* index, never a bare index set: d1 requires one tool and d8 requires eight,
    so a bare index set legitimately differs between levels and could not be compared.
    """
    slots: dict[str, dict[str, int]] = {}
    for arm in arm_ids:
        for name, index in records[arm].values["N2"]:
            slots.setdefault(name, {})[arm] = index
    moved = [
        f"{name}: " + ", ".join(f"{arm}={index}" for arm, index in sorted(by_arm.items()))
        for name, by_arm in sorted(slots.items())
        if len(set(by_arm.values())) > 1
    ]
    if not moved:
        return None
    return "a required tool moved slot between arms: " + "; ".join(moved)


def _check_n3(
    knob: str,
    arm_ids: tuple[str, ...],
    records: dict[str, PinRecord],
    parsed: dict[str, _ParsedArm],
) -> str | None:
    """N3, with the R control filler as the one permitted difference.

    The filler is appended "at the end of the system prompt", so a control's prompt is a
    plain arm's plus a suffix.  A difference anywhere else is not a filler, which is what
    tells the two apart without a new bundle field.
    """
    plain = tuple(arm for arm in arm_ids if parsed[arm].control is None)
    controls = tuple(arm for arm in arm_ids if parsed[arm].control is not None)
    if not plain:
        return _equal_across_arms(arm_ids, records, "N3")
    bases = {records[arm].values["N3"] for arm in plain}
    if len(bases) > 1:
        return f"the plain arms' system prompts differ: {_detail(plain, records, 'N3')}"
    base = bases.pop()
    offenders = []
    for arm in controls:
        prompt = records[arm].values["N3"]
        if prompt == base:
            continue
        if knob == _DISTRACTOR and prompt.startswith(base):
            # The R control filler, and the only difference N3 lets through.
            continue
        offenders.append(arm)
    if not offenders:
        return None
    return (
        "a control's system prompt differs from the plain arms' by something other than "
        f"the R control filler suffix: {_detail(tuple(offenders), records, 'N3')}"
    )


def _check_n5(arm_ids: tuple[str, ...], records: dict[str, PinRecord]) -> str | None:
    """N5: knob R's block must change, so its token count is described and not held equal.

    The difference is reported whenever there is one; the band it is reported against is
    the pre-registration's, and this row never refuses.
    """
    counts = {arm: records[arm].values["N5"] for arm in arm_ids}
    spread = max(counts.values()) - min(counts.values())
    if spread == 0:
        return None
    return (
        f"tool-block token count differs by {spread} across arms: "
        + ", ".join(f"{arm}={counts[arm]}" for arm in arm_ids)
    )


def _check_n8(arm_ids: tuple[str, ...], records: dict[str, PinRecord]) -> str | None:
    """N8, a per-arm property: `L_obs` exact and every observation's tokens in band.

    Not a cross-arm equality.  d1 and d8 carry different numbers of observations, so an
    equality here would refuse a clean contrast.
    """
    offenders = []
    for arm in arm_ids:
        widths, (low, high) = records[arm].values["N8"]
        if not widths:
            continue
        if tuple(widths) != (_L_OBS,):
            offenders.append(f"{arm}: observation widths {tuple(widths)}, expected ({_L_OBS},)")
        elif not (_BAND_LO <= low <= high <= _BAND_HI):
            offenders.append(
                f"{arm}: observation tokens [{low}, {high}] outside [{_BAND_LO}, {_BAND_HI}]"
            )
    if not offenders:
        return None
    return "; ".join(offenders)


def _check_n9(
    knob: str,
    arm_ids: tuple[str, ...],
    records: dict[str, PinRecord],
    parsed: dict[str, _ParsedArm],
) -> str | None:
    """N9: the aggregate over a control's seeded pairs against the pairs they stand in for.

    The control runs pairs 1..dL itself, so its seeded block stands in for the high arm's
    pairs dL+1..H, every one of them a chain pair -- which is why the single cheap stage-1
    call cancels out of the comparison.  The comparison is over sums and never
    per pair; the band is `_N9_BAND` tokens in both directions.
    """
    offenders = []
    for arm in arm_ids:
        reference = parsed[arm].control
        if reference is None:
            continue
        low = parsed[arm].level
        high_arm = _render_arm_id(knob, reference, None)
        if high_arm not in records:
            # Nothing to compare against.  N15 makes the constructor total, not the
            # contrast: a pre-registration that sweeps a control without its high arm is
            # a 4 error, and the row has no measurement here.
            continue
        seeded = records[arm].values["N9"]
        chain = records[high_arm].values["N9"]
        if len(seeded) != reference - low:
            offenders.append(
                f"{arm}: seeded {len(seeded)} pairs, expected H - dL = {reference - low}"
            )
            continue
        residual = sum(seeded) - sum(chain[low:])
        if abs(residual) > _N9_BAND:
            offenders.append(
                f"{arm}: seeded history is {residual:+d} tokens against the {high_arm} "
                f"pairs it stands in for, outside the +/-{_N9_BAND} band"
            )
    if not offenders:
        return None
    return "; ".join(offenders)


def check_pins(bundles_by_arm: _Mapping[str, _Bundle]) -> PinReport:
    """Run the ledger over the arms of one contrast.

    Every row is an equality *across* arms, so one arm satisfies all of them vacuously and
    two knobs in one call is a caller error rather than a pin violation.  Both raise
    `ValueError`: a refusal is a report a reader files, and neither of these is one.
    """
    parsed = {arm: _parse_arm_id(arm) for arm in bundles_by_arm}
    seen = {arm.knob for arm in parsed.values()}
    if len(seen) > 1:
        raise ValueError(
            "check_pins runs over the arms of one knob; "
            f"these arms carry {sorted(seen)}"
        )
    if len(bundles_by_arm) < 2:
        raise ValueError(
            "a contrast is two or more arms; every ledger row is an equality across arms "
            f"and {len(bundles_by_arm)} arm(s) satisfies all of them vacuously"
        )
    knob = seen.pop()
    arm_ids = tuple(sorted(bundles_by_arm))
    records = {arm: measure_pins(bundles_by_arm[arm]) for arm in arm_ids}

    violations: list[tuple[str, str]] = []
    reported: list[tuple[str, str]] = []
    for row in pin_ledger(knob):
        if knob not in row.applies_to or row.row_id in records[arm_ids[0]].unmeasured:
            continue
        if row.row_id == "N2":
            detail = _check_n2(arm_ids, records)
        elif row.row_id == "N3":
            detail = _check_n3(knob, arm_ids, records, parsed)
        elif row.row_id == "N5":
            detail = _check_n5(arm_ids, records)
        elif row.row_id == "N8":
            detail = _check_n8(arm_ids, records)
        elif row.row_id == "N9":
            detail = _check_n9(knob, arm_ids, records, parsed)
        else:
            detail = _equal_across_arms(arm_ids, records, row.row_id)
        if detail is None:
            continue
        if row.on_violation == _REPORT:
            reported.append((row.row_id, detail))
        else:
            violations.append((row.row_id, detail))

    return PinReport(
        knob=knob,
        refused=bool(violations),
        violations=tuple(violations),
        reported=tuple(reported),
        records=records,
    )
