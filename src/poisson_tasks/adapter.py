"""TG-M5's scripted path: the arm targets, the two scripted policies, the outcome map and the
pre-registration validator.

The invariants this file is built against are A1-A9 and A12 in the spec's 2.5, the two
coverage gaps 2.5 says the adapter inherits (N17's scripted `diff`, N18's revision
predicate) and knob R's level axis.  The frozen test file is `tests/test_tg_m5_scripted.py`;
where the spec's text could not be used as written, that file's module docstring is
authoritative and this file follows it.  Its twelve decisions are implemented as written
and are not restated here: the five public names, the TOML registration locked over its
bytes, the `<policy>_<arm>` target names, the cfg contract, `t` as the number of turns,
the outcome map's order, `meta`, what `to_episode` refuses, the module-global seam, the
validator's three clauses and `faulty`'s sealed file.  The model path (A10, A11, A13-A21)
is not here: it puts what needs `verifiers` in modules of its own and hands `to_episode` a
`Run` built from a trace.

Every entry point is a pure function of its arguments and the registration it was loaded
from: no clock, no RNG but a keyed hash of the Proofload seed, no model, no network, and
no module-level state that a call writes (A12).

Shapes the tests leave open, decided by this build
----------------------------------------------------
Each carries its escape hatch.  The tests pin none of them beyond what is said here.

* **`faulty`'s draws are keyed on the seed, the plant and the step, and on nothing
  else.**  The arm and the plant cell are not in the key, so two arms fed one seed draw
  the same numbers: a common-random-numbers design, under which a pure-depth plant shows a
  depth-1 arm and its control the same outcome at every seed, which is what "does not
  depend on history" looks like from a paired `diff`.  *Escape hatch:* add the arm id to
  `_draw`'s key to make arms independent; `test_f4`'s margins hold either way.
* **History is counted in N9's unit.**  A call's tokens are its tool name bare, its
  arguments as one compact JSON object and its observation as it stands, under the
  reference tokenizer: TG-M2's `_pair_tokens`, written again because it is private there.
  The seeded history is a bundle prompt's assistant `tool_calls` and `tool` messages, and
  never its user message, which is the task and not history: a plain arm's prompt is a
  string and holds none, so its first call sees no history at all.  *Escape hatch:* one
  helper, `_seeded_tokens`.
* **A botched call corrupts every argument that is not the record id.**  The engine
  rejects a wrong entry code or a wrong token and leaves the records where they were (E4),
  so the call is well formed, the format check does not fire, and the episode is a
  `wrong_state` and never a `malformed_call`.
* **The harness's signal is one of two labels.**  `api_error` or `wall_timeout`; a signal
  that is any other label, `passed` and the adapter's own two included, is refused, not
  only one outside the ten.  An import-time check ties all four labels this module names
  to TG-M3's `OUTCOMES`.
* **An uppercase revision is refused.**  N18's "40 hex characters" reads either way.  A
  Hugging Face commit hash is lowercase, and an uppercase spelling of one commit would be a
  second string for A13 to compare byte for byte.  *Escape hatch:* the character class of
  `_REVISION`.
* **The generator hash is checked after generation.**  A registration freezes a generator
  *version*; the hash is over `tasks.py`'s own source, so only a bundle can say what it is,
  and a cfg's `generator_hash` is compared with the bundle about to be run.
* **The scripted `fmt` is named `direct` and carries no markers**, so format-check clause 1
  never fires on this path.  A reply is the text `Done.`; nothing pins the wording.
* **At slack 0 the leaky plant cannot overshoot.**  An overshoot is `d + 2` turns and the
  budget is `d + 1`, so `to_episode`'s turn guard raises and Proofload stores an errored
  row.  The pilot's slack is 4; `validate_preregistration` allows 0 because N17 does.
* **Proofload is not a dependency, and this module is the only thing in the package that
  needs it.**  It is unpublished and there is no extra for it (`pyproject.toml` says why):
  it comes from a checkout installed into the same environment, `pip install -e
  ../proofload`.  The import below stays the one shape A1 permits, a
  top-level `from proofload import Episode`, and is wrapped so that importing this module
  without the extra raises a `ModuleNotFoundError` naming the extra rather than the bare
  "No module named 'proofload'".  Nothing on the package's import path reaches this module,
  so `import poisson_tasks` and everything under it but this file work without Proofload.
  *Escape hatch:* delete the `try`; A1 reads the `from` either way, since it walks the tree.
"""

from __future__ import annotations

import asyncio as _asyncio
import hashlib as _hashlib
import json as _json
import re as _re
import tomllib as _tomllib
from collections.abc import Callable as _Callable
from collections.abc import Mapping as _Mapping
from dataclasses import asdict as _asdict
from dataclasses import dataclass as _dataclass
from pathlib import Path as _Path
from typing import Any as _Any

try:
    from proofload import Episode as _Episode
except ModuleNotFoundError as _exc:
    raise ModuleNotFoundError(
        "This module is the Proofload route, and Proofload is not a dependency of "
        "poisson-tasks: nothing else in the package needs it.  It is not publicly "
        "available yet, so there is no extra and no index to install it from -- install "
        "a checkout into this same environment: `pip install -e ../proofload`."
    ) from _exc

from poisson_tasks.engine import DomainState as _DomainState
from poisson_tasks.engine import apply as _apply
from poisson_tasks.engine import init_state as _init_state
from poisson_tasks.engine import replay as _replay
from poisson_tasks.knobs import ArmSpec as _ArmSpec
from poisson_tasks.knobs import arm_id as _arm_id
from poisson_tasks.tasks import OUTCOMES as _OUTCOMES
from poisson_tasks.tasks import FormatSpec as _FormatSpec
from poisson_tasks.tasks import TaskBundle as _TaskBundle
from poisson_tasks.tasks import Turn as _Turn
from poisson_tasks.tasks import generate as _generate
from poisson_tasks.tasks import scenario_for as _scenario_for
from poisson_tasks.tasks import verify as _verify
from poisson_tasks.tokenizer import count_tokens as _count_tokens

__all__ = [
    "ArmRegistry",
    "load_registry",
    "validate_preregistration",
    "Run",
    "to_episode",
]

# ---------------------------------------------------------------------------
# frozen literals
# ---------------------------------------------------------------------------

# 2.2's two knobs, the same strings TG-M2's arm ids render.
_DEPTH = "depth"
_DISTRACTOR = "distractor"
_KNOBS = (_DEPTH, _DISTRACTOR)

_STRICTNESSES = ("strict", "leaky")
_EVAL = "eval"  # G12: "v0 emits `eval` only"

_REFERENCE = "reference"
_FAULTY = "faulty"

# The labels this module assigns or accepts, in 2.3's spelling.  `verifier_error` and
# `replay_mismatch` are the adapter's own; `api_error` and `wall_timeout` are the only two
# a harness can signal.  `_check_labels` ties all four to the vocabulary at import.
_VERIFIER_ERROR = "verifier_error"
_REPLAY_MISMATCH = "replay_mismatch"
_INSTRUMENT_SIGNALS = ("api_error", "wall_timeout")

# A3, TG-ADR-06: a cfg key that names a level moves `config_hash` and breaks pairing.
_LEVEL_KEYS = ("level", "depth", "distractor", "knob", "arm", "arm_id", "max_turns")
# N10, N11, N12, N17: the sweep file declares these so that they enter `config_hash`.
_REQUIRED_CFG = ("slack", "horizon", "strictness", "generator_hash")

_REQUIRED_FIELDS = ("knob", "strictness", "split", "generator_version", "slack", "horizon", "arms")
_MODEL_PINS = ("vllm_version", "endpoint_type")
_REVISION = _re.compile(r"[0-9a-f]{40}")

# The four arm id formats 2.2 defines, read back.  `_arm_of` re-renders what these parse and
# demands the id it was given, so anything looser here is caught there.
_DEPTH_ID = _re.compile(r"depth:d([0-9]+)(?:\+h([0-9]+))?")
_DISTRACTOR_ID = _re.compile(r"distractor:r([0-9]+)(?:\+len\(r([0-9]+)\))?@k([0-9]+)")
_NAME_RUN = _re.compile(r"[^0-9A-Za-z]+")

_PLANT_KEYS = ("step_fail_rate", "history_fail_rate", "overshoot_rate")

_DIRECT = _FormatSpec(name="direct", markers=())
_REPLY = _Turn(content="Done.", calls=(), finish_reason="stop")

# `faulty`'s draw domain, the same shape as TG-M1's and TG-M3's separators, and left at
# the old spelling for the same reason: these bytes are hash input, not a name.
_DRAW_DOMAIN = b"task-generator/adapter/faulty-draw/1\n"

_Target = _Callable[[_Mapping[str, _Any], int], _Episode]
_Call = tuple[str, _Any]


# ---------------------------------------------------------------------------
# the two public records
# ---------------------------------------------------------------------------


@_dataclass(frozen=True)
class Run:
    """What a harness hands the outcome map: the sampled turns, the tool messages in the
    order they were produced, how the run ended, the parser's format spec and, when the
    harness ended it, the instrument signal.

    A scripted policy builds one from its own turns; the model path builds one from a
    verifiers trace.  It is a plain record and validates nothing at construction: a
    structurally invalid trace has to reach `to_episode` to become a `verifier_error`, and
    a `Run` that refused it would turn an instrument failure into an exception at the
    caller.
    """

    turns: tuple[_Turn, ...]
    tool_messages: tuple[str, ...]
    ended_with_reply: bool
    turn_limit_hit: bool
    fmt: _FormatSpec
    instrument: str | None = None


@_dataclass(frozen=True)
class ArmRegistry:
    """A registration, built: its arms as TG-M2 `ArmSpec`s in file order, its slack and
    horizon, and the callables by registered name.

    Data, and not a singleton: two loads of one file are two registries.
    """

    arms: tuple[_ArmSpec, ...]
    slack: int
    horizon: int
    targets: dict[str, _Target]


# ---------------------------------------------------------------------------
# the outcome map, A4, A5, A8 and A9
# ---------------------------------------------------------------------------


@_dataclass(frozen=True)
class _Judgement:
    """The label an episode gets, with the two predicates and the clause `meta` records."""

    label: str
    strict_label: str
    leaky_pass: bool
    format_clause: int | None


def _judge(bundle: _TaskBundle, run: Run) -> _Judgement:
    """2.3's table in its own order, first match wins.

    An exception in the adapter's own verification -- the replay or the verdict -- is a
    `verifier_error`: G10's "no default-to-pass path", at the adapter's own sites.  Then a
    replay that does not equal the tool messages byte for byte; then the harness's signal,
    which outranks the verdict whatever state the trace shows and is never inferred; then
    `verify`'s label under the arm's strictness.  On an episode the adapter labelled itself,
    `leaky_pass` is False and the strict label is the label.
    """
    try:
        verdict = _verify(
            bundle, tuple(run.turns), run.ended_with_reply, run.turn_limit_hit, run.fmt
        )
        calls = [call for turn in run.turns for call in turn.calls]
        scenario = _scenario_for(bundle.seed, bundle.split)
        # A8, shape (b): a call the `null` harness answered itself (VN-7) never reached the
        # engine, so it is not replayed; `verify` still sees it, which is what makes the
        # episode `malformed_call`.  Everything else is replayed and compared byte for byte.
        kept = [
            (call, message)
            # `strict=False`: a count difference is a mismatch and not an exception, and
            # the `len` comparison below is what detects it (`test_a8_2`).
            for call, message in zip(calls, run.tool_messages, strict=False)
            if not _harness_answered(message)
        ]
        _final, observed = _replay(scenario, [call for call, _m in kept], bundle.seq_start)
        replays = len(calls) == len(run.tool_messages) and tuple(observed) == tuple(
            message for _c, message in kept
        )
    except Exception:
        return _Judgement(_VERIFIER_ERROR, _VERIFIER_ERROR, False, None)
    if not replays:
        return _Judgement(_REPLAY_MISMATCH, _REPLAY_MISMATCH, False, verdict.format_clause)
    if run.instrument is not None:
        return _Judgement(run.instrument, run.instrument, False, verdict.format_clause)
    return _Judgement(
        verdict.label, verdict.strict_label, verdict.leaky_pass, verdict.format_clause
    )


def _harness_answered(message: str) -> bool:
    """Whether a tool message is the `null` harness's own refusal (VN-7): its `error: ...`
    line, which carries no `seq` because the engine never saw the call.  An engine
    observation opens with its six-digit `seq`, so the two shapes cannot be confused."""
    return message.startswith("error: ")


def to_episode(
    arm: _ArmSpec,
    bundle: _TaskBundle,
    run: Run,
    *,
    slack: int,
    horizon: int,
    meta: _Mapping[str, _Any] | None = None,
) -> _Episode:
    """The one outcome path: a run of one bundle to a `proofload.Episode` (A9).

    `t` is the number of assistant turns, a reply included, and `horizon` is the knob's
    common `H` and never the arm's own `max_turns` (N17).  What would break A5 or A3 is
    refused with a `ValueError` naming it: an `arm` that is not the bundle's, an instrument
    signal outside the closed vocabulary, more turns than `max_turns(arm)`, and a `horizon`
    below it; the boundaries themselves are accepted.  `meta` carries what 2.5 lists that a
    scripted episode has, JSON-normalised so that the store takes it, and the caller's own
    keys, which never displace a required one.
    """
    rendered = _arm_id(arm)
    if bundle.arm_id != rendered:
        raise ValueError(f"arm {rendered!r} is not the bundle's arm, {bundle.arm_id!r}")
    if run.instrument is not None and run.instrument not in _INSTRUMENT_SIGNALS:
        raise ValueError(
            f"instrument signal {run.instrument!r} is outside the closed vocabulary; "
            f"a harness signals one of {_INSTRUMENT_SIGNALS}"
        )
    limit = arm.max_turns(slack)
    turns = len(run.turns)
    if turns > limit:
        raise ValueError(f"{rendered}: {turns} turns is over max_turns {limit} at slack {slack}")
    if horizon < limit:
        raise ValueError(
            f"{rendered}: horizon {horizon} is below max_turns {limit} at slack {slack}"
        )

    judged = _judge(bundle, run)
    pins: _Any = _json.loads(_json.dumps(_asdict(bundle.pins)))
    recorded: dict[str, _Any] = {
        "arm_id": rendered,
        "knob": arm.knob,
        "level": arm.level,
        "control": arm.control is not None,
        "task_id": bundle.task_id,
        "scenario_hash": bundle.scenario_hash,
        "pins": pins,
        "leaky_pass": judged.leaky_pass,
        "strict_label": judged.strict_label,
        "sampled_calls": sum(len(turn.calls) for turn in run.turns),
        "format_clause": judged.format_clause,
        "engine_hash": bundle.engine_hash,
        "generator_hash": bundle.generator_hash,
    }
    for key, value in (meta or {}).items():
        recorded.setdefault(key, value)
    return _Episode(outcome=judged.label, t=turns, horizon=horizon, meta=recorded)


# ---------------------------------------------------------------------------
# the pre-registration validator: N18, N15's pre-registration half, N17's number
# ---------------------------------------------------------------------------


def _is_int(value: _Any) -> bool:
    """An integer, and not a bool: `True` is an `int` to Python and a typo to a registration."""
    return isinstance(value, int) and not isinstance(value, bool)


def _arm_of(rendered: _Any, document: _Mapping[str, _Any]) -> _ArmSpec:
    """One listed arm id as a TG-M2 `ArmSpec`, or a `ValueError` naming it.

    TG-M2's constructor refuses `d3+h3` and `d8+h1` (N15); here the same refusal is reached
    from a registration file.  The canonical check re-renders the arm and demands the id it
    was given, so `d01`, `D1` and `@k8` are refused as ids `arm_id` would never produce.
    """
    if not isinstance(rendered, str):
        raise ValueError(f"arms must be arm id strings, got {rendered!r}")
    depth = _DEPTH_ID.fullmatch(rendered)
    distractor = _DISTRACTOR_ID.fullmatch(rendered)
    if depth is not None:
        knob, level, high = _DEPTH, depth.group(1), depth.group(2)
    elif distractor is not None:
        knob, level, high = _DISTRACTOR, distractor.group(1), distractor.group(2)
    else:
        raise ValueError(f"{rendered!r} is not an arm id 2.2 defines")
    try:
        arm = _ArmSpec(
            knob=knob,
            level=int(level),
            control=None if high is None else int(high),
            strictness=document["strictness"],
            split=document["split"],
            generator_version=document["generator_version"],
        )
    except ValueError as exc:
        raise ValueError(f"arm {rendered!r} is refused: {exc}") from exc
    if _arm_id(arm) != rendered:
        raise ValueError(f"arm {rendered!r} is not canonical: its one id is {_arm_id(arm)!r}")
    return arm


def _arms_of(document: _Mapping[str, _Any]) -> tuple[_ArmSpec, ...]:
    listed = document["arms"]
    if not isinstance(listed, (list, tuple)) or not listed:
        raise ValueError(f"arms must be a non-empty list of arm id strings, got {listed!r}")
    return tuple(_arm_of(item, document) for item in listed)


def _check_model(index: int, value: _Any) -> None:
    """N18: `<HF id>@<revision>`, one `@`, a non-empty id and a full commit hash."""
    if not isinstance(value, str) or value.count("@") != 1 or value.startswith("@"):
        raise ValueError(
            f"models[{index}]['model'] must be '<HF id>@<revision>' with exactly one '@' "
            f"and a non-empty id, got {value!r}"
        )
    revision = value.split("@")[1]
    if _REVISION.fullmatch(revision) is None:
        raise ValueError(
            f"models[{index}]: revision {revision!r} is not 40 lowercase hex characters, so "
            "it is a branch, a tag or nothing, and not a commit (N18)"
        )


def _check_models(models: _Any) -> None:
    if not isinstance(models, (list, tuple)) or not all(isinstance(m, _Mapping) for m in models):
        raise ValueError(f"models must be a list of tables, got {models!r}")
    for index, entry in enumerate(models):
        _check_model(index, entry.get("model"))
    for key in _MODEL_PINS:
        seen: list[str] = []
        for index, entry in enumerate(models):
            value = entry.get(key)
            if not isinstance(value, str) or not value:
                raise ValueError(
                    f"models[{index}] has no {key!r}: two models cannot be shown to agree "
                    "on a value one of them omits (N18)"
                )
            seen.append(value)
        if len(set(seen)) > 1:
            raise ValueError(f"models disagree on {key!r}: {seen} (N18: one for every model)")


def validate_preregistration(document: _Mapping[str, _Any]) -> None:
    """Refuse a registration that cannot be built, and name what is wrong.

    Reads its document and never writes it.  Fields nobody here reads are tolerated at the
    top level and in a model table, because the model path adds the serve command, the
    decoding dict and the GPU type to the same file.  Refused, each with a `ValueError`
    that names the key or the value:

    * a missing field, an unknown knob, a strictness that is not `strict` or `leaky`, a
      split other than `eval` (G12), a `slack` that is not a non-negative integer;
    * an arm that is not a canonical id of the registration's knob, or is listed twice;
    * no control arm at all (N15's pre-registration half: a sweep of a knob without its
      control arm is a pre-registration error);
    * a `horizon` that is not `max(max_turns)` over the arms at that slack (N17);
    * a model that is not `<HF id>@<40 hex characters>`, models that omit or disagree on
      `vllm_version` or `endpoint_type` (N18: the predicate TG-M2 declared and could not
      hold, since no model string reaches a bundle).
    """
    if not isinstance(document, _Mapping):
        raise ValueError(f"a registration is a table of keys, got {type(document).__name__}")
    for key in _REQUIRED_FIELDS:
        if key not in document:
            raise ValueError(f"the registration has no {key!r}")
    knob = document["knob"]
    if knob not in _KNOBS:
        raise ValueError(f"knob must be one of {_KNOBS}, got {knob!r}")
    strictness, split = document["strictness"], document["split"]
    if strictness not in _STRICTNESSES:
        raise ValueError(f"strictness must be one of {_STRICTNESSES}, got {strictness!r}")
    if split != _EVAL:
        raise ValueError(f"split must be {_EVAL!r}, v0 emits eval only (G12), got {split!r}")
    version = document["generator_version"]
    if not isinstance(version, str) or not version:
        raise ValueError(f"generator_version must be a non-empty string, got {version!r}")
    slack, horizon = document["slack"], document["horizon"]
    if not _is_int(slack) or slack < 0:
        raise ValueError(f"slack must be a non-negative integer, got {slack!r}")
    if not _is_int(horizon):
        raise ValueError(f"horizon must be an integer, got {horizon!r}")

    arms = _arms_of(document)
    listed: set[str] = set()
    for arm in arms:
        rendered = _arm_id(arm)
        if arm.knob != knob:
            raise ValueError(
                f"arm {rendered!r} is a {arm.knob} arm, and the registration's knob is {knob!r}"
            )
        if rendered in listed:
            raise ValueError(f"arm {rendered!r} is listed more than once")
        listed.add(rendered)
    if not any(arm.control is not None for arm in arms):
        raise ValueError(
            f"the {knob} registration has no control arm: a sweep of a knob without its "
            "control arm is a pre-registration error (N15)"
        )
    largest = max(arm.max_turns(slack) for arm in arms)
    if horizon != largest:
        raise ValueError(
            f"horizon is {horizon}, but N17 makes it the largest max_turns over the arms, "
            f"{largest} at slack {slack}"
        )
    if "models" in document:
        _check_models(document["models"])


# ---------------------------------------------------------------------------
# the sealed calibration file, and the registry
# ---------------------------------------------------------------------------


@_dataclass(frozen=True)
class _Plant:
    """One sealed cell's planted parameters, each a rate in [0, 1] that defaults to 0."""

    step_fail_rate: float = 0.0
    history_fail_rate: float = 0.0
    overshoot_rate: float = 0.0


def _is_rate(value: _Any) -> bool:
    """A number in [0, 1].  A bool is a typo, and a NaN fails the comparison."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 1


def _cells_of(location: _Path) -> dict[str, _Plant]:
    """The sealed file's `[cells.<name>]` tables, refused at load and by name.

    A mistyped parameter would otherwise be a plant that silently does nothing, and a
    calibration would be scored against a plant that never fired.
    """
    try:
        document = _tomllib.loads(location.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, _tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"the sealed file {location} is not valid TOML: {exc}") from exc
    cells = document.get("cells")
    if not isinstance(cells, dict) or not cells:
        raise ValueError(
            f"the sealed file {location} needs a non-empty [cells] table, got {cells!r}"
        )
    plants: dict[str, _Plant] = {}
    for name, params in cells.items():
        if not isinstance(params, dict):
            raise ValueError(f"cell {name!r} of the sealed file is not a table, got {params!r}")
        rates: dict[str, float] = {}
        for key, value in params.items():
            if key not in _PLANT_KEYS:
                raise ValueError(f"cell {name!r} names {key!r}, which is not one of {_PLANT_KEYS}")
            if not _is_rate(value):
                raise ValueError(f"cell {name!r}: {key} must be a number in [0, 1], got {value!r}")
            rates[key] = float(value)
        plants[name] = _Plant(**rates)
    return plants


def _target_name(policy: str, rendered: str) -> str:
    """The module attribute a target is registered under: the policy, then the arm id with
    every run of non-alphanumeric characters made one underscore, because `--target
    module:attr` refuses an attribute with a colon in it."""
    return f"{policy}_{_NAME_RUN.sub('_', rendered)}"


def load_registry(
    path: str | _Path, *, sha256: str, sealed: str | _Path | None = None
) -> ArmRegistry:
    """A registration file, checked, validated and built (A7, A12).

    The lock is over the file's raw bytes: they are hashed once, the whole digest is
    compared with `sha256` before anything else is read, and the same bytes are parsed, so
    an edit that leaves the parsed document identical -- a comment, a newline, two keys
    swapped -- still refuses.  A mismatch is a `RuntimeError` naming both hashes, one of
    the four types `proofload sweep` turns into "cannot resolve --target", so a stale
    registry fails at import and before any episode.  There is no cache: every load checks
    again.

    A registry module is `REGISTRY = load_registry(...)` then
    `globals().update(REGISTRY.targets)`.  `faulty` targets exist only when `sealed` names
    a calibration file.
    """
    location = _Path(path)
    raw = location.read_bytes()
    actual = _hashlib.sha256(raw).hexdigest()
    if actual != sha256:
        raise RuntimeError(
            f"the registration {location} hashes to {actual}, but this registry was "
            f"compiled against {sha256}: the file was edited after it was frozen, or the "
            "registry is stale"
        )
    try:
        document = _tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, _tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"the registration {location} is not valid TOML: {exc}") from exc
    validate_preregistration(document)
    arms = _arms_of(document)
    slack, horizon = document["slack"], document["horizon"]
    cells = {} if sealed is None else _cells_of(_Path(sealed))
    policies = (_REFERENCE,) if sealed is None else (_REFERENCE, _FAULTY)

    targets: dict[str, _Target] = {}
    for arm in arms:
        for policy in policies:
            name = _target_name(policy, _arm_id(arm))
            if name in targets:
                raise ValueError(f"two targets would be registered as {name!r}")
            targets[name] = _scripted_target(policy, arm, slack, horizon, cells)
    return ArmRegistry(arms=arms, slack=slack, horizon=horizon, targets=targets)


# ---------------------------------------------------------------------------
# a target: what it accepts, and refuses
# ---------------------------------------------------------------------------


def _refuse_running_loop() -> None:
    """A12: a call from inside a running event loop is refused.  Nothing is started or
    left behind, so a refused call poisons nothing."""
    try:
        _asyncio.get_running_loop()
    except RuntimeError:
        return
    raise RuntimeError(
        "an arm target cannot be called from inside a running event loop: it would nest "
        "one loop in another (A12)"
    )


def _integral(value: _Any) -> int | None:
    """An int, or a float that is one: `inspect` prints a stored config with every number a
    float, and A6 runs that config back through the target."""
    if _is_int(value):
        return int(value)
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _check_cfg(cfg: _Mapping[str, _Any], arm: _ArmSpec, slack: int, horizon: int) -> None:
    """The cfg contract (decision 4), by name.

    "The adapter refuses to start" has no start hook in Proofload to live in, so a rollout
    that raises is the only refusal it can store.  A key that names a level is refused,
    because it moves `config_hash`; the four pins must be there and equal the
    registration's; every other key -- `model`, `serving_pin`, `temperature`,
    `plant_cell` -- is tolerated and inert, since A21 runs the scripted `reference` target
    on the model's real sweep file.  `generator_hash` is compared after generation.
    """
    for key in _LEVEL_KEYS:
        if key in cfg:
            raise ValueError(
                f"cfg carries {key!r}: what a contrast varies lives in the target and "
                "never in cfg, because a cfg key moves config_hash and breaks pairing (A3)"
            )
    for key in _REQUIRED_CFG:
        if key not in cfg:
            raise ValueError(
                f"cfg has no {key!r}, which a sweep file declares so that it enters config_hash"
            )
    for key, frozen in (("slack", slack), ("horizon", horizon)):
        if _integral(cfg[key]) != frozen:
            raise ValueError(f"cfg[{key!r}] is {cfg[key]!r}, but the registration froze {frozen}")
    if cfg["strictness"] != arm.strictness:
        raise ValueError(
            f"cfg['strictness'] is {cfg['strictness']!r}, but the arm is {arm.strictness!r}"
        )


def _check_generator_hash(cfg: _Mapping[str, _Any], bundle: _TaskBundle) -> None:
    if cfg["generator_hash"] != bundle.generator_hash:
        raise ValueError(
            f"cfg['generator_hash'] is {cfg['generator_hash']!r}, but this generator's is "
            f"{bundle.generator_hash!r}"
        )


def _plant_of(cfg: _Mapping[str, _Any], cells: _Mapping[str, _Plant]) -> _Plant:
    """Never silently "no plant": a typo in a cell's name would score a planted cell clean."""
    cell = cfg.get("plant_cell")
    if not isinstance(cell, str) or cell not in cells:
        raise ValueError(
            f"cfg['plant_cell'] is {cell!r}, which the sealed file does not name: {sorted(cells)}"
        )
    return cells[cell]


def _scripted_target(
    policy: str, arm: _ArmSpec, slack: int, horizon: int, cells: _Mapping[str, _Plant]
) -> _Target:
    """One arm's callable under one policy: `(cfg, seed) -> proofload.Episode`.

    Refusals come first and cheapest -- a running loop, then the cfg, then the plant cell --
    and only then a bundle is generated, so a refused call costs no generation except for
    the one check that needs the bundle, the generator hash.
    """

    def target(cfg: _Mapping[str, _Any], seed: int) -> _Episode:
        _refuse_running_loop()
        _check_cfg(cfg, arm, slack, horizon)
        plant = _plant_of(cfg, cells) if policy == _FAULTY else None
        # The Proofload seed is the task seed itself, with no remapping (G12).
        bundle = _generate(arm, seed)
        _check_generator_hash(cfg, bundle)
        run = _reference_run(bundle) if plant is None else _faulty_run(bundle, seed, plant)
        # Decision 9: the map is looked up in this module at call time, and not captured
        # here, so that a test, and the model path, can replace the one outcome path.
        return to_episode(arm, bundle, run, slack=slack, horizon=horizon, meta={"policy": policy})

    return target


# ---------------------------------------------------------------------------
# the two scripted policies
# ---------------------------------------------------------------------------


def _take(
    state: _DomainState, call: _Call, turns: list[_Turn], messages: list[str]
) -> tuple[_DomainState, str]:
    """One sampled call, made on the live engine, and the observation it got back."""
    state, observation = _apply(state, call)
    turns.append(_Turn(content="", calls=(call,), finish_reason="tool_calls"))
    messages.append(observation)
    return state, observation


def _finished(turns: list[_Turn], messages: list[str]) -> Run:
    return Run(
        turns=(*turns, _REPLY),
        tool_messages=tuple(messages),
        ended_with_reply=True,
        turn_limit_hit=False,
        fmt=_DIRECT,
    )


def _live_state(bundle: _TaskBundle) -> _DomainState:
    """A control's observations are numbered from its own `seq_start` (A8)."""
    return _init_state(_scenario_for(bundle.seed, bundle.split), bundle.seq_start)


def _reference_run(bundle: _TaskBundle) -> Run:
    """`reference` executes the reference calls: one per turn, then a reply."""
    state = _live_state(bundle)
    turns: list[_Turn] = []
    messages: list[str] = []
    for call in bundle.reference_calls:
        state, _observation = _take(state, call, turns, messages)
    return _finished(turns, messages)


def _draw(seed: int, kind: str, step: int) -> float:
    """A uniform number in [0, 1), a keyed hash of the Proofload seed: the same in every
    process and under every `PYTHONHASHSEED`.  53 bits, so that 1.0 is unreachable and a
    rate of 1 fires every time."""
    material = _DRAW_DOMAIN + f"{seed}\x1f{kind}\x1f{step}".encode("ascii")
    return (int.from_bytes(_hashlib.sha256(material).digest()[:8], "big") >> 11) / (1 << 53)


def _pair_tokens(name: str, arguments: _Any, observation: str) -> int:
    """N9's unit under the reference tokenizer: the name bare, the arguments as one
    compact JSON object, the observation as it stands."""
    if not isinstance(arguments, str):
        arguments = _json.dumps(arguments, separators=(",", ":"))
    return _count_tokens(name) + _count_tokens(arguments) + _count_tokens(observation)


def _seeded_tokens(bundle: _TaskBundle) -> int:
    """The history a bundle's prompt already holds: a `Messages` prompt's assistant tool
    calls and tool messages, in the chat shape TG-M3 seeds.  A string prompt is the task
    alone and holds none."""
    if isinstance(bundle.prompt, str):
        return 0
    total = 0
    for message in bundle.prompt:
        if message.get("role") == "assistant":
            for call in message.get("tool_calls") or ():
                function = call["function"]
                total += _count_tokens(function["name"]) + _count_tokens(function["arguments"])
        elif message.get("role") == "tool":
            total += _count_tokens(message["content"])
    return total


def _botch(call: _Call, record: str) -> _Call:
    """The call made wrongly: every argument but the record id is corrupted, so the engine
    rejects it (E4) and the record does not move."""
    name, arguments = call
    wrong = {key: value if value == record else "x" + value for key, value in arguments.items()}
    return name, wrong


def _faulty_run(bundle: _TaskBundle, seed: int, plant: _Plant) -> Run:
    """The three plants of 2.5's `faulty`, on the reference chain.

    **Depth** fails each required call independently at `step_fail_rate`.  **History**
    fails a required call with probability `min(1, history_fail_rate * history tokens)`,
    the tokens being the seeded prompt's plus the policy's own calls and observations so
    far.  A failed call is made wrongly, the engine rejects it, and the policy replies: a
    failure at the first call is two turns and one sampled call, with the target below its
    goal.  **Leaky** makes one further stage call past the goal, with probability
    `overshoot_rate`, when the block holds a tool that can, which is TG-M3's own rule for
    an `overshoot` control.
    """
    record = bundle.goal[1]
    state = _live_state(bundle)
    turns: list[_Turn] = []
    messages: list[str] = []
    history = _seeded_tokens(bundle)
    for step, call in enumerate(bundle.reference_calls):
        by_depth = _draw(seed, "step", step) < plant.step_fail_rate
        by_history = _draw(seed, "history", step) < min(1.0, plant.history_fail_rate * history)
        if by_depth or by_history:
            _take(state, _botch(call, record), turns, messages)
            return _finished(turns, messages)
        state, observation = _take(state, call, turns, messages)
        history += _pair_tokens(call[0], call[1], observation)
    overshoot = bundle.negative_controls.get("overshoot")
    if overshoot is not None and _draw(seed, "overshoot", 0) < plant.overshoot_rate:
        for call in overshoot[len(bundle.reference_calls) :]:
            state, _observation = _take(state, call, turns, messages)
    return _finished(turns, messages)


# ---------------------------------------------------------------------------
# an import-time check, which no test can reach
# ---------------------------------------------------------------------------


def _check_labels() -> None:
    """Every label this module names is in 2.3's closed vocabulary.  A vocabulary that
    dropped one would otherwise store an unlisted label under `outcome`, which is what
    A4's closed set exists to prevent."""
    for label in (_VERIFIER_ERROR, _REPLAY_MISMATCH, *_INSTRUMENT_SIGNALS):
        if label not in _OUTCOMES:
            raise ValueError(f"{label!r} is not in the outcome vocabulary {_OUTCOMES}")


_check_labels()
