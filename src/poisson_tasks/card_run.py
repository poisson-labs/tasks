"""The version 2 card's run: one model, 56 arms, through the run engine, under a cap.

0.5.0 measures each published model on one design, registered before any run: every level of every
built-in dial but the distractor, with every control arm a dial has (52 arms), and four arms on a
tool file for the two dials the built-in tasks cannot carry, on the cards' sixty tasks at five
attempts.  This module is that design and the run of it against a hosted model
(`python -m poisson_tasks.card_run`).  The open model's run is the Colab notebook's
(`calibration_run`'s `--design card-v2`), which takes its design, its gate, its record and its
provenance from here.  None of it is a command of the command-line tool.

The design
----------
* **Arms.**  `ARMS`, `calibration.arm_specs("card-v2")`'s 56 in the order they run: each dial's
  first level (`BASES`), each one's last (`TOPS`), the control arms (`CONTROLS`), the levels
  between (`MIDDLES`), then the four on the tool file (`OWN_ARMS`).  A stop then costs middle
  levels and own-tools arms before it costs either arm of a pair a dial is decided on.
* **Tasks.**  The cards' sixty seeds, five attempts at each: 300 episodes an arm, 16,800 a model,
  each capped at 32 model calls, through the `null` harness.
* **The tool file.**  `OWN_FIXTURE`, acme's five tools in OpenAI's shape, shipped in the package,
  with its three reads declared (`OWN_READS`), since that shape states no effects.
* **The generator.**  Built-in `"4"` and own tools `own-4`, at the two hashes frozen for 0.5.0.
  `check_generators` refuses any other before a key is read or a folder made.

The models
----------
`MODELS` holds a row for each hosted model: the settings file's preset that serves it, the
endpoint, the decoding as each request carries it (a field named `"not sent"` is left out), the
price the cap is counted in, the cap Taylor set, and the other `model` values the provider
documents for the id.  `role` is `"card"` for a published card's model and `"bridge"` for
gpt-5-nano's last run, a record of the same design that is no published card.

Phase 1
-------
Three seeds no card measures, one attempt, every arm, before anything else: 168 episodes.  It
stops the run when any episode carries an instrument label, when more than 0.02 of its model
calls were cut by the completion limit, when more than 0.10 of the base arms' episodes made no
tool call, or when an answer named a model that is neither the one asked for nor one of the row's
aliases (`phase1_gate`).  A stopped phase 1 says what it spent and is final for its folder.

The run
-------
Every episode goes through the run engine (`runs.run_plan`), the built-in arms as one plan and
the own-tools arms as another, since the second carries the tool file.  The cap is one, over the
folder: each plan is given what the others have left of it.  A cap that is reached stops the run
between episodes with every finished episode kept; the same call again with a larger cap goes on
with what is owed, and runs nothing twice.  A run that finished is not run again, so no failed
episode is quietly run twice; only a recorded re-run of a void arm reopens it (`rerun_void`).

What a folder holds
-------------------
`record.json`, written before the first model call: the design, both generators' labels and
hashes, the seeds, the arms, the model, the endpoint, the decoding, the tool file's digest and
one entry for each call of the driver.  `phase1.json`, phase 1's verdict.  `status.json`, how
the last call ended.  `records/episodes.jsonl`, one line an episode of the run proper, arm by
arm in the design's order, and `records/tallies.json`.  `artifact.json`, once phase 1 has
passed: the card's version and its provenance block (`provenance_block`), which is refused
(`check_provenance`) if any field the design asks every card to carry is missing.  The cells and
what a card prints are the card's reading, and are not built here.
"""

from __future__ import annotations

import argparse as _argparse
import dataclasses as _dc
import datetime as _datetime
import hashlib as _hashlib
import importlib.metadata as _metadata
import json as _json
import os as _os
import pathlib as _pathlib
import shutil as _shutil
import sys as _sys
import types as _types
import urllib.parse as _urlparse
from collections.abc import Callable as _Callable
from collections.abc import Iterable as _Iterable
from collections.abc import Mapping as _Mapping
from collections.abc import Sequence as _Sequence
from typing import Any as _Any

from poisson_tasks import calibration as _cal
from poisson_tasks import calibration_run as _run
from poisson_tasks import config as _config
from poisson_tasks import knob_probe as _probe
from poisson_tasks.export import MEASURED_HARNESS as _HARNESS
from poisson_tasks.knobs import ArmSpec as _ArmSpec
from poisson_tasks.knobs import arm_id as _arm_id
from poisson_tasks.taskset import MAX_MODEL_CALLS as _MAX_MODEL_CALLS

__all__ = [
    "DESIGN_NAME",
    "CARD_VERSION",
    "RULE_VERSION",
    "ARMS",
    "BASES",
    "TOPS",
    "CONTROLS",
    "MIDDLES",
    "OWN_ARMS",
    "PHASE1_SEEDS",
    "ATTEMPTS",
    "PHASE1_ATTEMPTS",
    "MAX_MODEL_CALLS",
    "Design",
    "DESIGN",
    "GENERATOR_VERSION",
    "OWN_GENERATOR_VERSION",
    "FROZEN_GENERATOR_HASH",
    "FROZEN_OWN_GENERATOR_HASH",
    "GeneratorMoved",
    "check_generators",
    "OWN_FIXTURE",
    "OWN_READS",
    "OWN_SET_NAME",
    "own_tools",
    "ModelRow",
    "MODELS",
    "CARD_DECODING",
    "QWEN_DECODING",
    "STOPS",
    "phase1_gate",
    "void_arms",
    "card_record",
    "check_record",
    "PROVENANCE_FIELDS",
    "provenance_block",
    "check_provenance",
    "build_artifact",
    "write_artifact",
    "file_run",
    "RerunRefused",
    "rerun_void",
    "run_card",
    "build_parser",
    "main",
]

# ---------------------------------------------------------------------------
# the design
# ---------------------------------------------------------------------------

DESIGN_NAME = _cal.CARD_V2
"""The design's name, as `calibration.arm_specs` and the notebook's `--design` take it."""
CARD_VERSION = 2
RULE_VERSION = "0.5.0"
"""The version of the rule a dial is read by on these records, registered before any run."""

_GROUPS = {
    name: tuple(_arm_id(spec) for spec in specs) for name, specs in _cal.card_v2_groups().items()
}
BASES: tuple[str, ...] = _GROUPS["bases"]
TOPS: tuple[str, ...] = _GROUPS["tops"]
CONTROLS: tuple[str, ...] = _GROUPS["controls"]
MIDDLES: tuple[str, ...] = _GROUPS["middles"]
OWN_ARMS: tuple[str, ...] = _GROUPS["own"]
ARMS: tuple[str, ...] = BASES + TOPS + CONTROLS + MIDDLES + OWN_ARMS
"""The 56 arms in the order they run."""
_SPECS: dict[str, _ArmSpec] = {
    _arm_id(spec): spec for specs in _cal.card_v2_groups().values() for spec in specs
}

PHASE1_SEEDS: tuple[int, ...] = tuple(_probe.PHASE1_SEEDS)
"""Phase 1's three seeds: the first three of the knob probe's derivation, on no card."""
ATTEMPTS = _cal.N
PHASE1_ATTEMPTS = 1
MAX_MODEL_CALLS = _MAX_MODEL_CALLS
"""Every episode ends after 32 model calls: the taskset's own turn limit."""


@_dc.dataclass(frozen=True)
class Design:
    """What a run runs.  `DESIGN` is the registered one; a smaller one is for tests."""

    arms: tuple[str, ...]
    phase1_seeds: tuple[int, ...]
    seeds: tuple[int, ...]
    attempts: int = ATTEMPTS
    phase1_attempts: int = PHASE1_ATTEMPTS

    @property
    def episodes_per_arm(self) -> int:
        return self.attempts * len(self.seeds)

    @property
    def phase1_episodes_per_arm(self) -> int:
        return self.phase1_attempts * len(self.phase1_seeds)

    @property
    def built_in(self) -> tuple[str, ...]:
        return tuple(arm for arm in self.arms if not _is_own(arm))

    @property
    def own(self) -> tuple[str, ...]:
        return tuple(arm for arm in self.arms if _is_own(arm))


DESIGN = Design(arms=ARMS, phase1_seeds=PHASE1_SEEDS, seeds=tuple(_cal.seed_list()))


def _knob(arm: str) -> str:
    return arm.split(":", 1)[0]


def _is_own(arm: str) -> bool:
    return _knob(arm) in _cal._V2_OWN_DIALS


def _spec(arm: str) -> _ArmSpec:
    """The arm an id names, as a version 2 card generates it: a built-in arm at the built-in
    label, an arm on the tool file at the own-tools label."""
    if arm in _SPECS:
        return _SPECS[arm]
    spec = _run.spec_for(arm)
    return _dc.replace(spec, generator_version=_own_label()) if _is_own(arm) else spec


# ---------------------------------------------------------------------------
# the generator, frozen for 0.5.0
# ---------------------------------------------------------------------------

GENERATOR_VERSION = "4"
OWN_GENERATOR_VERSION = "own-4"
FROZEN_GENERATOR_HASH = _run.EXPECTED_GENERATOR_HASH
FROZEN_OWN_GENERATOR_HASH = _run.EXPECTED_OWN_GENERATOR_HASH
"""The built-in and the own-tools generators frozen from the merge of generator 4 until the last
paid run of 0.5.0.  Every version 2 card is measured on these two and on no other."""


class GeneratorMoved(RuntimeError):
    """The package's generators are not the frozen ones."""


def _own_label() -> str:
    from poisson_tasks.own import generator

    return str(generator.GENERATOR_VERSION)


def check_generators() -> tuple[str, str]:
    """Both frozen hashes, read off this install: the built-in generator's label and the hash a
    task it makes carries, and the own-tools generator's label and hash.  Refuses any other, in
    one line that shows what was found and what is frozen.  It is a check of the install, so a
    design with no arm on the tool file is held to both."""
    from poisson_tasks.arms import DEFAULT_GENERATOR_VERSION
    from poisson_tasks.own import generator
    from poisson_tasks.tasks import generate

    only = "a version 2 card is measured only on the frozen generators"
    if DEFAULT_GENERATOR_VERSION != GENERATOR_VERSION:
        raise GeneratorMoved(
            f'this package\'s built-in generator is labelled "{DEFAULT_GENERATOR_VERSION}", not '
            f'the frozen "{GENERATOR_VERSION}"; {only}'
        )
    if generator.GENERATOR_VERSION != OWN_GENERATOR_VERSION:
        raise GeneratorMoved(
            f'this package\'s own-tools generator is labelled "{generator.GENERATOR_VERSION}", '
            f'not the frozen "{OWN_GENERATOR_VERSION}"; {only}'
        )
    for arm in (BASES[0], "spread:p1"):
        found = generate(_SPECS[arm], DESIGN.seeds[0]).generator_hash
        if found != FROZEN_GENERATOR_HASH:
            raise GeneratorMoved(
                f"this package's built-in generator is {found}, not the frozen "
                f"{FROZEN_GENERATOR_HASH}; {only}"
            )
    found = generator.generator_hash()
    if found != FROZEN_OWN_GENERATOR_HASH:
        raise GeneratorMoved(
            f"this package's own-tools generator is {found}, not the frozen "
            f"{FROZEN_OWN_GENERATOR_HASH}; {only}"
        )
    return FROZEN_GENERATOR_HASH, FROZEN_OWN_GENERATOR_HASH


# ---------------------------------------------------------------------------
# the tool file the four own-tools arms run on
# ---------------------------------------------------------------------------

OWN_FIXTURE = (
    _pathlib.Path(__file__).resolve().parent / "data" / "fixtures" / "acme-openai-chat.json"
)
"""acme's five tools as an OpenAI Chat Completions tool list, shipped with the package so the
four arms can be run again from an install."""
OWN_READS: tuple[str, ...] = ("get_order", "search_orders", "list_channels")
"""The tools declared reads: the OpenAI shape states no effects."""
OWN_SET_NAME = "acme-openai-chat"
"""The set's name: the file's, as a settings file that names none takes it."""
_OWN_FORMAT = "auto"


def own_tools() -> dict[str, _Any]:
    """The tool file as a plan on it carries it (`config.Plan.own`): where it is, how it is read,
    the declared reads and nothing else declared, and what the reading found."""
    from poisson_tasks import own

    data = OWN_FIXTURE.read_bytes()
    reading = own.read_tools(data, format=_OWN_FORMAT, name=OWN_SET_NAME)
    toolset = own.apply_effects(reading.toolset, read=OWN_READS, write=())
    return {
        "file": str(OWN_FIXTURE),
        "format": _OWN_FORMAT,
        "name": toolset.name,
        "read": list(OWN_READS),
        "write": [],
        "intents": {},
        "flows": [],
        "file_digest": toolset.file_digest,
        "source_format": toolset.source_format,
        "tools": len(toolset.tools),
    }


# ---------------------------------------------------------------------------
# the models, and how each is called
# ---------------------------------------------------------------------------

_NOT_SENT = "not sent"
CARD_DECODING: _Mapping[str, _Any] = _types.MappingProxyType(
    {"temperature": 1.0, "top_p": 1.0, "reasoning_effort": "low", "max_tokens": 8192}
)
"""A version 2 card's decoding where the interface takes all of it: 8,192 completion tokens a
call, so that a model that reasons is not cut mid-call."""
_CLAUDE_DECODING: _Mapping[str, _Any] = _types.MappingProxyType(
    {"temperature": 1.0, "top_p": _NOT_SENT, "reasoning_effort": _NOT_SENT, "max_tokens": 8192}
)
"""A Claude model through Anthropic's OpenAI-compatible endpoint: a request that carries both
`temperature` and `top_p` is refused, and the endpoint ignores `reasoning_effort`, so neither is
sent and the model runs at its own default effort."""
QWEN_DECODING: _Mapping[str, _Any] = CARD_DECODING
"""The open model, served by vLLM: the whole decoding, thinking on at its default."""


@_dc.dataclass(frozen=True)
class ModelRow:
    """One hosted model of the run: whether it is a card's model or the bridge, the preset that
    serves it, the endpoint, the decoding, the price its cap is counted in, the cap, what the
    provider calls the interface, the other `model` values the provider's page documents for
    the id, and the prompt length above which the provider's price is another one."""

    role: str
    provider: str
    base_url: str
    decoding: _Mapping[str, _Any]
    price: _config.PriceConfig
    cap: float
    api_surface: str
    aliases: tuple[str, ...] = ()
    prompt_length_threshold: int | None = None


def _endpoint(provider: str) -> str:
    endpoint = _config.PRESETS[provider].endpoint
    assert endpoint is not None
    return endpoint


MODELS: _Mapping[str, ModelRow] = _types.MappingProxyType(
    {
        "gpt-6-luna": ModelRow(
            role="card",
            provider="openai",
            base_url=_endpoint("openai"),
            decoding=CARD_DECODING,
            price=_config.PUBLISHED_PRICES["gpt-6-luna"],
            cap=50.0,
            api_surface="OpenAI chat completions",
        ),
        "claude-haiku-5-5": ModelRow(
            role="card",
            provider="anthropic",
            base_url=_endpoint("anthropic"),
            decoding=_CLAUDE_DECODING,
            price=_config.PUBLISHED_PRICES["claude-haiku-5-5"],
            cap=65.0,
            api_surface="Anthropic OpenAI-compatible endpoint",
            prompt_length_threshold=100_000,
        ),
        "gpt-5-nano-2025-08-07": ModelRow(
            role="bridge",
            provider="openai",
            base_url=_endpoint("openai"),
            decoding=_types.MappingProxyType(dict(_cal.DECODING)),
            price=_config.PUBLISHED_PRICES["gpt-5-nano-2025-08-07"],
            cap=15.0,
            api_surface="OpenAI chat completions",
        ),
    }
)
"""The hosted models, each with the cap Taylor set on 2026-11-15.  gpt-5-nano's row is the bridge:
its last run before it retires, at the decoding and the price its generator-0 card and the knob
probe were run at, so that its depth arms can be read against that card's with only the
generator between them."""

CONCURRENCY = 16
"""Episodes in flight at once unless the call says otherwise; the run records what it ran at."""

# ---------------------------------------------------------------------------
# the rule's constants, registered before any run
# ---------------------------------------------------------------------------

FLOOR = 0.15
CEILING = 0.85
PHASE1_LENGTH_STOPS = 0.02
"""Phase 1 stops when more than this share of its model calls ended at the completion limit;
an arm of the run above it is void."""
PHASE1_NO_CALL = _cal.NO_CALL_THRESHOLD
VOID_INSTRUMENT = _cal.INSTRUMENT_THRESHOLD
STOPS = ("instrument", "length_stops", "no_call", "answer_model")
"""What can stop phase 1, in the order a verdict names them."""

# ---------------------------------------------------------------------------
# small things
# ---------------------------------------------------------------------------


def _now() -> str:
    return _datetime.datetime.now(_datetime.UTC).isoformat(timespec="seconds")


def _say(message: str) -> None:
    print(message, flush=True)


def _refuse(sentence: str) -> int:
    print(f"error: {sentence}", file=_sys.stderr, flush=True)
    return 1


def _read_json(path: _pathlib.Path) -> _Any:
    return _json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _write_json(path: _pathlib.Path, value: _Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(f".{path.name}.{_os.getpid()}.part")
    # keys in the order they were given: a decoding reads in the order its fields are declared
    partial.write_text(_json.dumps(value, indent=2) + "\n", encoding="utf-8")
    _os.replace(partial, path)


def _host(base_url: str) -> str:
    """An endpoint's host, with its port where the URL names one."""
    return _urlparse.urlsplit(base_url).netloc


def _by_arm(records: _Iterable[_cal.EpisodeRecord]) -> dict[str, list[_cal.EpisodeRecord]]:
    out: dict[str, list[_cal.EpisodeRecord]] = {}
    for row in records:
        out.setdefault(row.arm_id, []).append(row)
    return out


def _distinct(names: _Iterable[str]) -> list[str]:
    return list(dict.fromkeys(names))


# ---------------------------------------------------------------------------
# phase 1's gate, and the arms a run leaves void
# ---------------------------------------------------------------------------


def _no_call_share(rows: _Sequence[_cal.EpisodeRecord]) -> float | None:
    kept = _cal.scored(rows)
    if not kept:
        return None
    return sum(1 for row in kept if _cal._made_no_call(row)) / len(kept)


def _length_stop_share(rows: _Sequence[_cal.EpisodeRecord]) -> float:
    calls = sum(row.turns for row in rows)
    return sum(row.length_stops or 0 for row in rows) / calls if calls else 0.0


def phase1_gate(
    records: _Mapping[str, _Sequence[_cal.EpisodeRecord]],
    tallies: _Mapping[str, _Mapping[str, int]],
    *,
    design: Design,
    model: str,
    aliases: _Sequence[str] = (),
) -> dict[str, _Any]:
    """Phase 1's verdict on its recorded episodes, as `phase1.json` holds it.

    It stops the run on any of four things, named in `stops` in this order: an episode with an
    instrument label, or an instrument tally that is not empty (`instrument`); more than
    `PHASE1_LENGTH_STOPS` of all its model calls ended at the completion limit
    (`length_stops`); more than `PHASE1_NO_CALL` of the scored episodes of the base arms, the
    built-in dials' first levels, made no tool call (`no_call`); and an answer whose `model` is
    neither the id asked for nor one of `aliases` (`answer_model`).  A top arm that never calls a
    tool is the dial's effect and stops nothing."""
    rows = [row for arm in design.arms for row in records.get(arm, ())]
    labelled = sum(1 for row in rows if row.label in _cal.INSTRUMENT_LABELS)
    tallied = sum(sum(tallies.get(arm, {}).values()) for arm in design.arms)
    failures = max(labelled, tallied)
    length_share = _length_stop_share(rows)
    bases = [row for arm in design.arms if arm in BASES for row in records.get(arm, ())]
    no_call = _no_call_share(bases) or 0.0
    answered = _distinct(name for row in rows for name in (row.answer_models or ()))
    strangers = [name for name in answered if name != model and name not in aliases]
    reasons: dict[str, str] = {}
    if failures:
        reasons["instrument"] = (
            f"{failures} episode(s) failed for instrument reasons: the plumbing is not clean"
        )
    if length_share > PHASE1_LENGTH_STOPS:
        reasons["length_stops"] = (
            f"{length_share:.3f} of the model calls were cut by the completion limit, above "
            f"{PHASE1_LENGTH_STOPS}"
        )
    if no_call > PHASE1_NO_CALL:
        reasons["no_call"] = (
            f"{no_call:.3f} of the base arms' episodes made no tool call, above {PHASE1_NO_CALL}"
        )
    if strangers:
        reasons["answer_model"] = (
            f"an answer named {', '.join(strangers)}, which is not {model} and not an alias "
            "its provider documents"
        )
    stops = [name for name in STOPS if name in reasons]
    return {
        "passed": not stops,
        "stops": stops,
        "reasons": [reasons[name] for name in stops],
        "episodes": len(rows),
        "model_calls": sum(row.turns for row in rows),
        "length_stops": sum(row.length_stops or 0 for row in rows),
        "length_stop_share": length_share,
        "no_call_share": no_call,
        "base_episodes": len(bases),
        "instrument_failures": failures,
        "answer_models": answered,
    }


def _base_of(arm: str) -> str:
    """The arm a no-call share is read against: the dial's first level."""
    knob = _knob(arm)
    return next((base for base in (*BASES, *OWN_ARMS) if _knob(base) == knob), arm)


def _complete(rows: _Sequence[_cal.EpisodeRecord], design: Design) -> bool:
    counts: dict[int, int] = {}
    for row in rows:
        counts[row.seed] = counts.get(row.seed, 0) + 1
    return all(counts.get(seed, 0) >= design.attempts for seed in design.seeds)


def void_arms(
    records: _Mapping[str, _Sequence[_cal.EpisodeRecord]],
    tallies: _Mapping[str, _Mapping[str, int]],
    *,
    design: Design,
) -> list[dict[str, _Any]]:
    """The complete arms of a run that are void, each with its causes, as the pre-registration
    has them: an instrument rate above 0.02 (`instrument`); more than 0.02 of the arm's model
    calls cut by the completion limit, an instrument cause too (`length_stops`); and a no-call
    share above 0.10 when the dial's base arm's is above it as well (`no_call`), since on a top
    arm alone it is the dial's effect and is scored as failures."""
    shares = {arm: _no_call_share(records.get(arm, ())) for arm in design.arms}
    out: list[dict[str, _Any]] = []
    for arm in design.arms:
        rows = list(records.get(arm, ()))
        if not _complete(rows, design):
            continue
        causes: list[dict[str, _Any]] = []
        rate = _cal.instrument_rate(rows, tallies.get(arm, {}))
        if rate > VOID_INSTRUMENT:
            causes.append({"cause": "instrument", "share": rate, "above": VOID_INSTRUMENT})
        length = _length_stop_share(rows)
        if length > PHASE1_LENGTH_STOPS:
            causes.append({"cause": "length_stops", "share": length,
                           "above": PHASE1_LENGTH_STOPS})
        share, base = shares[arm], shares.get(_base_of(arm))
        if (share is not None and share > PHASE1_NO_CALL
                and base is not None and base > PHASE1_NO_CALL):
            causes.append({"cause": "no_call", "share": share, "above": PHASE1_NO_CALL,
                           "base_arm": _base_of(arm), "base_share": base})
        if causes:
            out.append({"arm": arm, "causes": causes})
    return out


# ---------------------------------------------------------------------------
# the record, written before the first model call
# ---------------------------------------------------------------------------


def _plan(
    design: Design,
    arms: _Sequence[str],
    seeds: _Sequence[int],
    attempts: int,
    *,
    model: str,
    row: ModelRow,
    base_url: str,
    key_var: str,
    own: _Mapping[str, _Any] | None,
) -> _Any:
    """A phase's arms as the run engine's plan: the built-in arms as one plan, the arms on the
    tool file as another, which carries the file."""
    return _config.Plan(
        preset=DESIGN_NAME,
        arms=tuple(_spec(arm) for arm in arms),
        seeds=tuple(seeds),
        attempts=attempts,
        model=_config.ModelConfig(
            provider=row.provider,
            name=model,
            base_url=base_url,
            api_key_env=key_var,
            price=row.price,
        ),
        decoding=_types.MappingProxyType(dict(row.decoding)),
        max_model_calls=MAX_MODEL_CALLS,
        own=None if own is None else _types.MappingProxyType(dict(own)),
    )


def own_tools_record(
    design: Design, *, model: str, base_url: str, decoding: _Mapping[str, _Any]
) -> dict[str, _Any]:
    """What a run's record says of the tool file: its digest, the format it was read as, its
    name, the reads declared, the digest of its tool specifications, and the hash of the plan
    the design's own-tools arms run as (the arms, the seeds, the attempts, the model, the
    endpoint, the decoding, the turn cap and the file)."""
    from poisson_tasks import provenance

    own = own_tools()
    plan = _config.Plan(
        preset=DESIGN_NAME,
        arms=tuple(_spec(arm) for arm in design.own),
        seeds=tuple(design.seeds),
        attempts=design.attempts,
        model=_config.ModelConfig(provider="", name=model, base_url=base_url, api_key_env=""),
        decoding=_types.MappingProxyType(dict(decoding)),
        max_model_calls=MAX_MODEL_CALLS,
        own=_types.MappingProxyType(own),
    )
    return {
        "fixture": OWN_FIXTURE.name,
        "fixture_sha256": str(own["file_digest"]),
        "tool_format": str(own["source_format"]),
        "tool_spec_hash": provenance.tool_spec_hash(OWN_FIXTURE.read_bytes()),
        "plan_hash": _config.plan_hash(plan),
        "name": str(own["name"]),
        "read": list(own["read"]),
        "write": list(own["write"]),
        "tools": int(own["tools"]),
    }


def _tokenizer() -> dict[str, str]:
    path = _pathlib.Path(__file__).resolve().parent / "data" / "o200k_base.tiktoken"
    return {"encoding": "o200k_base", "sha256": _hashlib.sha256(path.read_bytes()).hexdigest()}


def card_record(
    design: Design,
    *,
    model: str,
    role: str,
    base_url: str,
    decoding: _Mapping[str, _Any],
    command: str,
    extra: _Mapping[str, _Any],
) -> dict[str, _Any]:
    """A run's record, written into its folder before the first model call: the design, both
    frozen generators, the seeds and their hashes, the arms in the order they run, the model,
    the endpoint, the decoding as each request carries it, the tool file, and what the driver
    adds (`extra`: a hosted model's price and how it is served, a served model's pin)."""
    from poisson_tasks.engine import EngineSpec, engine_hash

    return {
        "card_version": CARD_VERSION,
        "design": DESIGN_NAME,
        "role": role,
        "command": command,
        "generator_version": GENERATOR_VERSION,
        "frozen_generator_hash": FROZEN_GENERATOR_HASH,
        "own_generator_version": OWN_GENERATOR_VERSION,
        "own_generator_hash": FROZEN_OWN_GENERATOR_HASH,
        "engine_hash": engine_hash(EngineSpec.load()),
        "vocabulary_hash": _cal._vocabulary_hash(),
        "tokenizer": _tokenizer(),
        "strictness": "strict",
        "split": _cal.SPLIT,
        "seeds": list(design.seeds),
        "seed_list_hash": _cal._seed_list_digest(design.seeds),
        "phase1_seeds": list(design.phase1_seeds),
        "phase1_seed_list_hash": _cal._seed_list_digest(design.phase1_seeds),
        "arms": list(design.arms),
        "own_arms": list(design.own),
        "attempts": design.attempts,
        "phase1_attempts": design.phase1_attempts,
        "episodes_per_arm": design.episodes_per_arm,
        "model": model,
        "base_url": base_url,
        "decoding": dict(decoding),
        "max_model_calls": MAX_MODEL_CALLS,
        "harness": _HARNESS,
        "own_tools": own_tools_record(design, model=model, base_url=base_url, decoding=decoding),
        "package_version": _metadata.version("poisson-tasks"),
        "verifiers_version": _metadata.version("verifiers"),
        **dict(extra),
    }


_SETTLED = (
    "card_version",
    "design",
    "role",
    "generator_version",
    "frozen_generator_hash",
    "own_generator_version",
    "own_generator_hash",
    "split",
    "seeds",
    "phase1_seeds",
    "arms",
    "attempts",
    "phase1_attempts",
    "model",
    "base_url",
    "decoding",
    "max_model_calls",
    "harness",
    "own_tools",
)
"""What a folder's record settles: a call on other settings is refused, and takes a new folder."""


def check_record(
    path: _pathlib.Path, record: _Mapping[str, _Any], invocation: _Mapping[str, _Any]
) -> dict[str, _Any]:
    """Write the record before the first episode, or check a folder's own against it: a call on
    other settings is refused.  Each call of the driver is added to its `invocations`."""
    held = _read_json(path)
    if held is None:
        written = {**record, "written": _now(), "invocations": [dict(invocation)]}
        _write_json(path, written)
        return written
    differ = [name for name in _SETTLED if held.get(name) != record.get(name)]
    if differ:
        raise ValueError(
            f"{path.parent} holds a run with other settings ("
            + ", ".join(differ)
            + "); use a new folder"
        )
    held["invocations"] = [*held.get("invocations", []), dict(invocation)]
    _write_json(path, held)
    return dict(held)


def _close_invocation(path: _pathlib.Path, **facts: _Any) -> None:
    """What the driver's latest call did, added to its entry in the record."""
    held = _read_json(path)
    if isinstance(held, dict) and held.get("invocations"):
        held["invocations"][-1].update(facts)
        _write_json(path, held)


# ---------------------------------------------------------------------------
# the provenance every version 2 card carries
# ---------------------------------------------------------------------------

_SHARED_FIELDS: tuple[tuple[_Any, ...], ...] = (
    ("card_version",),
    ("design",),
    ("role",),
    ("package_version",),
    ("produced_by", "command"),
    ("produced_by", "arguments"),
    ("generator_version",),
    ("generator_hash",),
    ("own_generator_version",),
    ("own_generator_hash",),
    ("engine_hash",),
    ("vocabulary_hash",),
    ("tokenizer", "encoding"),
    ("tokenizer", "sha256"),
    ("seed_list",),
    ("seed_list_hash",),
    ("S",),
    ("n",),
    ("arms",),
    ("strictness",),
    ("split",),
    ("max_model_calls",),
    ("concurrency",),
    ("own_tools", "fixture_sha256"),
    ("own_tools", "tool_format"),
    ("own_tools", "tool_spec_hash"),
    ("own_tools", "plan_hash"),
    ("models", 0, "id"),
    ("answer_models",),
    ("first_call",),
    ("last_call",),
    ("serving", "<model>", "kind"),
    ("decoding", "temperature"),
    ("decoding", "top_p"),
    ("decoding", "reasoning_effort"),
    ("decoding", "max_tokens"),
    ("run", "phase1"),
    ("run", "resumes"),
    ("run", "reruns"),
    ("run", "void_arms"),
    ("run", "spend_by_arm"),
    ("bootstrap_resamples",),
    ("bootstrap_seed",),
    ("delta_star",),
    ("floor",),
    ("ceiling",),
    ("instrument_threshold",),
    ("rule_version",),
)
_HOSTED_FIELDS: tuple[tuple[_Any, ...], ...] = (
    ("serving", "<model>", "endpoint_host"),
    ("serving", "<model>", "api_surface"),
    ("models", 0, "input_rate"),
    ("models", 0, "cached_input_rate"),
    ("models", 0, "output_rate"),
    ("rate_read_date",),
    ("prompt_length_threshold",),
)
_LOCAL_FIELDS: tuple[tuple[_Any, ...], ...] = (
    ("serving", "<model>", "stack"),
    ("serving", "<model>", "stack_version"),
    ("serving", "<model>", "flags"),
    ("serving", "<model>", "gpu"),
    ("serving", "<model>", "revision"),
    ("serving", "<model>", "quantization"),
    ("serving", "<model>", "chat_template_sha256"),
)
PROVENANCE_FIELDS: dict[str, tuple[str, ...]] = {
    kind: tuple(".".join(str(part) for part in path) for path in (*_SHARED_FIELDS, *fields))
    for kind, fields in (("hosted", _HOSTED_FIELDS), ("local", _LOCAL_FIELDS))
}
"""Every field a version 2 card's provenance block must carry, as dotted paths, for a hosted
model and for one served locally; `<model>` stands for the model's id."""


def _missing(block: _Any, path: _Sequence[_Any], model: str | None) -> bool:
    node = block
    for part in path:
        key = model if part == "<model>" else part
        if isinstance(key, int):
            if not isinstance(node, list) or len(node) <= key:
                return True
        elif key is None or not isinstance(node, _Mapping) or key not in node:
            return True
        node = node[key]
    return False


def check_provenance(block: _Mapping[str, _Any]) -> None:
    """Refuse (`ValueError`) a provenance block that lacks any field every version 2 card
    carries, naming the first one missing; return nothing for a whole block.  A hosted model's
    block holds where it was called and at what price; a locally served model's holds its
    serving stack and no price."""
    serving = block.get("serving")
    model = next(iter(serving), None) if isinstance(serving, _Mapping) and serving else None
    entry = serving.get(model) if isinstance(serving, _Mapping) and model is not None else None
    kind = entry.get("kind") if isinstance(entry, _Mapping) else None
    fields = _SHARED_FIELDS + (_LOCAL_FIELDS if kind == "local" else _HOSTED_FIELDS)
    for path in fields:
        if _missing(block, path, model):
            where = ".".join(str(model if part == "<model>" else part) for part in path)
            raise ValueError(
                f"a version 2 card's provenance must carry `{path[-1]}` ({where}), and this "
                "block does not: no artifact is built from it"
            )


def provenance_block(
    record: _Mapping[str, _Any],
    *,
    phase1: _Mapping[str, _Any],
    run: _Mapping[str, _Any],
    answer_models: _Sequence[str],
    first_call: str | None,
    last_call: str | None,
) -> dict[str, _Any]:
    """The provenance block of a run, from its record, phase 1's verdict and what the run did.
    A field the record does not hold is left out, and `check_provenance` then refuses the
    block by that field's name."""
    invocations = list(record.get("invocations") or [])
    latest = dict(invocations[-1]) if invocations else {}
    arguments = {
        key: value for key, value in latest.items()
        if key in ("model", "cap", "concurrency", "design", "step", "wall_clock_hours")
    }
    concurrencies = sorted(
        {int(entry["concurrency"]) for entry in invocations if entry.get("concurrency")}
    )
    model = record.get("model")
    block: dict[str, _Any] = {
        "card_version": record.get("card_version"),
        "design": record.get("design"),
        "role": record.get("role"),
        "package_version": record.get("package_version"),
        "verifiers_version": record.get("verifiers_version"),
        "harness": record.get("harness"),
        "produced_by": {"command": record.get("command"), "arguments": arguments},
        "generator_version": record.get("generator_version"),
        "generator_hash": record.get("frozen_generator_hash"),
        "own_generator_version": record.get("own_generator_version"),
        "own_generator_hash": record.get("own_generator_hash"),
        "engine_hash": record.get("engine_hash"),
        "vocabulary_hash": record.get("vocabulary_hash"),
        "tokenizer": record.get("tokenizer"),
        "seed_list": record.get("seeds"),
        "seed_list_hash": record.get("seed_list_hash"),
        "S": len(record.get("seeds") or ()),
        "n": record.get("attempts"),
        "phase1_seed_list": record.get("phase1_seeds"),
        "arms": record.get("arms"),
        "strictness": record.get("strictness"),
        "split": record.get("split"),
        "max_model_calls": record.get("max_model_calls"),
        "concurrency": concurrencies[-1] if concurrencies else record.get("concurrency"),
        "concurrencies": concurrencies,
        "own_tools": record.get("own_tools"),
        "models": [dict(record.get("model_entry") or {})],
        "answer_models": list(answer_models),
        "first_call": first_call,
        "last_call": last_call,
        "serving": {str(model): dict(record.get("serving") or {})},
        "decoding": record.get("decoding"),
        "rate_read_date": record.get("rate_read_date"),
        "run": dict(run, phase1=dict(phase1)),
        "bootstrap_resamples": _cal.BOOTSTRAP_RESAMPLES,
        "bootstrap_seed": _cal.BOOTSTRAP_SEED,
        "delta_star": _cal.DELTA_STAR,
        "floor": FLOOR,
        "ceiling": CEILING,
        "instrument_threshold": _cal.INSTRUMENT_THRESHOLD,
        "no_call_threshold": _cal.NO_CALL_THRESHOLD,
        "length_stop_threshold": PHASE1_LENGTH_STOPS,
        "rule_version": RULE_VERSION,
    }
    if "prompt_length_threshold" in record:
        block["prompt_length_threshold"] = record["prompt_length_threshold"]
    # a field the record lacks is left out, so the check names it
    return {
        key: value for key, value in block.items()
        if value is not None or key == "prompt_length_threshold"
    }


_PHASE1_KEPT = (
    "passed", "episodes", "spent", "stops", "reasons", "length_stop_share", "no_call_share",
    "answer_models", "instrument_failures", "seconds_per_episode", "projected_hours",
)


def call_times(roots: _Iterable[_pathlib.Path]) -> tuple[str | None, str | None]:
    """When the first and the last recorded model calls of a run came back (UTC), from every
    arm's `calibration.ANSWERS_FILE` under `roots`."""
    first: list[str] = []
    last: list[str] = []
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.glob(f"*/{_cal.ANSWERS_FILE}")):
            for row in _cal.read_answers(path.parent).values():
                if row.get("first_call"):
                    first.append(str(row["first_call"]))
                if row.get("last_call"):
                    last.append(str(row["last_call"]))
    return (min(first) if first else None, max(last) if last else None)


def _ledger(folder: _pathlib.Path) -> list[dict[str, _Any]]:
    path = folder / "spend.jsonl"
    out: list[dict[str, _Any]] = []
    if not path.exists():
        return out
    for line in path.read_bytes().splitlines(keepends=True):
        if not line.endswith(b"\n"):
            break
        try:
            row = _json.loads(line)
        except ValueError:
            break
        if isinstance(row, dict):
            out.append(row)
    return out


def _spent(folder: _pathlib.Path) -> float:
    return float(sum(float(line.get("dollars") or 0.0) for line in _ledger(folder)))


_PHASE1_DIRS = ("phase1", "phase1-own")
_CARD_DIRS = ("card", "card-own")
"""Where a hosted run's two plans run, in each phase: the built-in arms, then the arms on the
tool file."""


def build_artifact(folder: _pathlib.Path) -> dict[str, _Any]:
    """A hosted run's artifact, from its folder: the card's version, whether every arm is
    complete, and the provenance block, checked (`check_provenance`).  A folder whose record
    lacks a field the block must carry, or whose phase 1 has not passed, builds none
    (`ValueError`).  It writes nothing: `write_artifact` does."""
    folder = _pathlib.Path(folder)
    record = _read_json(folder / "record.json")
    phase1 = _read_json(folder / "phase1.json")
    if not isinstance(record, dict):
        raise ValueError(f"{folder} holds no run (no record.json)")
    if not (isinstance(phase1, dict) and phase1.get("passed")):
        raise ValueError(f"phase 1 has not passed in {folder}: there is no card to build")
    design = Design(
        arms=tuple(record.get("arms") or ()),
        phase1_seeds=tuple(record.get("phase1_seeds") or ()),
        seeds=tuple(record.get("seeds") or ()),
        attempts=int(record.get("attempts") or 0),
        phase1_attempts=int(record.get("phase1_attempts") or 0),
    )
    records_path = folder / "records" / _cal.RECORDS_FILE
    rows = _cal.read_records(records_path) if records_path.exists() else []
    by_arm = _by_arm(rows)
    tallies = _read_json(folder / "records" / "tallies.json") or {}
    spend: dict[str, float] = {arm: 0.0 for arm in design.arms}
    for sub in _CARD_DIRS:
        for line in _ledger(folder / sub):
            arm = str(line.get("arm"))
            spend[arm] = spend.get(arm, 0.0) + float(line.get("dollars") or 0.0)
    invocations = list(record.get("invocations") or [])
    first_call, last_call = call_times(folder / sub for sub in (*_PHASE1_DIRS, *_CARD_DIRS))
    block = provenance_block(
        record,
        phase1={key: phase1[key] for key in _PHASE1_KEPT if key in phase1},
        run={
            "resumes": [dict(entry) for entry in invocations[1:] if entry.get("episodes_run")],
            "reruns": list(_read_json(folder / "reruns.json") or []),
            "void_arms": void_arms(by_arm, tallies, design=design),
            "spend_by_arm": spend,
        },
        answer_models=_distinct(
            [*phase1.get("answer_models", []),
             *(name for row in rows for name in (row.answer_models or ()))]
        ),
        first_call=first_call,
        last_call=last_call,
    )
    check_provenance(block)
    complete = [arm for arm in design.arms if _complete(by_arm.get(arm, ()), design)]
    return {
        "card_version": CARD_VERSION,
        "design": record.get("design"),
        "role": record.get("role"),
        "model": record.get("model"),
        "complete": len(complete) == len(design.arms),
        "arms_complete": complete,
        "records": len(rows),
        "provenance": block,
    }


def write_artifact(folder: _pathlib.Path) -> dict[str, _Any]:
    """`artifact.json` in a hosted run's folder: `build_artifact`'s, or nothing when it refuses."""
    artifact = build_artifact(folder)
    _write_json(_pathlib.Path(folder) / "artifact.json", artifact)
    return artifact


# ---------------------------------------------------------------------------
# filing a finished run under a `calibration/` folder
# ---------------------------------------------------------------------------

FILED = ("artifact.json", _cal.RECORDS_FILE, "tallies.json")
"""The three files a committed card has."""


def card_folder_name(model: str) -> str:
    """The folder a model's card is filed in: a hosted model's id; a served model's short name
    and the first eight characters of its revision, as the generator-0 cards' folders are."""
    from poisson_tasks import cards

    name, _, revision = model.partition("@")
    if revision:
        return f"{cards._short(name)}-{revision[:8]}"
    return model.replace("/", "-")


def file_card(
    into: _pathlib.Path, *, model: str, role: str, artifact: _pathlib.Path,
    records: _pathlib.Path, tallies: _pathlib.Path,
) -> _pathlib.Path:
    """The three files of a finished run under `into`, a `calibration/` folder:
    `into/<model>/` for a card's model and `into/bridge/<model>/` for the bridge, which no
    listing of published cards reads.  A file already there with other bytes is not
    overwritten (`ValueError`)."""
    base = _pathlib.Path(into) / "bridge" if role == "bridge" else _pathlib.Path(into)
    where = base / card_folder_name(model)
    sources = dict(zip(FILED, (artifact, records, tallies), strict=True))
    for name, source in sources.items():
        target = where / name
        if target.exists() and target.read_bytes() != source.read_bytes():
            raise ValueError(f"{target} exists and differs; it is not overwritten")
    where.mkdir(parents=True, exist_ok=True)
    for name, source in sources.items():
        _shutil.copyfile(source, where / name)
    return where


def file_run(folder: _pathlib.Path, into: _pathlib.Path) -> _pathlib.Path:
    """File a finished hosted run's card files under `into` (`file_card`), and return the folder
    written.  A run that is not finished, whose phase 1 stopped it or which a cap left with
    episodes owed, is refused (`ValueError`) and nothing is written."""
    folder = _pathlib.Path(folder)
    record = _read_json(folder / "record.json")
    status = _read_json(folder / "status.json")
    if not isinstance(record, dict):
        raise ValueError(f"{folder} holds no run (no record.json)")
    if not (isinstance(status, dict) and status.get("phase") == "card"
            and status.get("verdict") == "done" and status.get("stop") is None):
        raise ValueError(f"the run in {folder} has not finished; only a finished run is filed")
    for name in ("artifact.json", f"records/{_cal.RECORDS_FILE}", "records/tallies.json"):
        if not (folder / name).is_file():
            raise ValueError(f"the run in {folder} has no {name}; it is not filed")
    return file_card(
        into, model=str(record["model"]), role=str(record["role"]),
        artifact=folder / "artifact.json",
        records=folder / "records" / _cal.RECORDS_FILE,
        tallies=folder / "records" / "tallies.json",
    )


# ---------------------------------------------------------------------------
# the hosted driver
# ---------------------------------------------------------------------------


def _arm_rows(
    run_dir: _pathlib.Path, model: str
) -> tuple[list[_cal.EpisodeRecord], dict[str, int]]:
    if not (run_dir / _cal.TRACES_FILE).exists():
        return [], {}
    return (
        _cal.records_from_run(run_dir, model=model, card_version=CARD_VERSION),
        _cal.read_tally(run_dir),
    )


def _collect(
    folder: _pathlib.Path, subs: _Sequence[str], design: Design, model: str
) -> tuple[dict[str, list[_cal.EpisodeRecord]], dict[str, dict[str, int]]]:
    """Every arm's records and tally, from where its plan ran: `subs` is the built-in arms'
    folder and the own-tools arms'."""
    records: dict[str, list[_cal.EpisodeRecord]] = {}
    tallies: dict[str, dict[str, int]] = {}
    for arm in design.arms:
        sub = subs[1] if _is_own(arm) else subs[0]
        records[arm], tallies[arm] = _arm_rows(folder / sub / _run._arm_dir(arm), model)
    return records, tallies


def _progress(phase: str, before: float) -> _Callable[[_Mapping[str, _Any]], None]:
    seen: dict[str, _Any] = {"arm": None}

    def report(event: _Mapping[str, _Any]) -> None:
        done = int(event["episodes_done"])
        if event["arm"] != seen["arm"] or done % 300 == 0 or done == event["episodes_total"]:
            seen["arm"] = event["arm"]
            spend = event.get("spend")
            _say(
                f"[{phase}] {event['arm']}: {done} of {event['episodes_total']} episodes"
                + ("" if spend is None else f", ${before + float(spend):.4f} spent in this folder")
            )

    return report


@_dc.dataclass
class _Phase:
    """How a phase's two plans ended: the first stop, what they ran and what they still owe."""

    stop: str | None = None
    first_error: str | None = None
    run: int = 0
    owed: int = 0


def _run_phase(
    folder: _pathlib.Path,
    subs: _Sequence[str],
    design: Design,
    seeds: _Sequence[int],
    attempts: int,
    *,
    phase: str,
    cap: float,
    concurrency: int,
    plan_for: _Callable[[_Sequence[str], _Sequence[int], int, bool], _Any],
) -> _Phase:
    """A phase through the run engine: the built-in arms' plan, then the own-tools arms', each
    in its own folder, under what the cap leaves once every other folder's spend is counted.
    A plan a stop left unfinished ends the phase, and the plan after it is owed whole."""
    from poisson_tasks import runs as _runs

    out = _Phase()
    spent_dirs = (*_PHASE1_DIRS, *_CARD_DIRS)
    for sub, arms, own in ((subs[0], design.built_in, False), (subs[1], design.own, True)):
        if not arms:
            continue
        plan = plan_for(arms, seeds, attempts, own)
        if out.stop is not None:
            out.owed += _runs._total(plan) - _runs._kept(plan, folder / sub)
            continue
        elsewhere = sum(_spent(folder / other) for other in spent_dirs if other != sub)
        result = _runs.run_plan(
            plan,
            _runs.RunFolder(path=folder / sub, name=sub, status="new"),
            caps={"spend_usd": max(0.0, cap - elsewhere), "tokens": None},
            concurrency=concurrency,
            events=_progress(phase, elsewhere),
        )
        out.run += int(result.episodes_run)
        out.owed += int(result.episodes_owed)
        if result.stop_reason is not None:
            out.stop, out.first_error = result.stop_reason, result.first_error
    return out


_RESUMABLE = ("spend_cap", "token_cap", "provider_exhausted", "interrupted", "watchdog")
"""The stops a run goes on from when it is called again: a cap, the provider out of credit, an
interrupt, a start that hung.  A streak of failed episodes is none of them: it is phase 1's
first stop, or an arm the run leaves void."""


def run_card(
    folder: _pathlib.Path,
    *,
    model: str,
    cap: float,
    concurrency: int = CONCURRENCY,
    env_file: _pathlib.Path = _pathlib.Path(".env"),
    key_var: str | None = None,
    base_url: str | None = None,
    design: Design = DESIGN,
    row: ModelRow | None = None,
) -> int:
    """The version 2 design on a hosted model into `folder`: phase 1, then every arm.

    `model` is a row of `MODELS` (`row` replaces it); `cap` is the folder's spend cap in
    dollars; the key is read from `env_file`'s `key_var` line (the preset's own variable when
    not named) and never printed; `base_url` is the row's endpoint unless given.  Run again on
    the same folder it goes on with what is owed, under the cap given then: phase 1 is not
    repeated, a finished run is not run again, and a folder phase 1 stopped stays stopped.

    Returns 0 when every arm is complete, 2 when phase 1 stopped the run, 4 when a stop left
    episodes owed, and 1, with one `error:` line, when it refused before anything was spent."""
    from poisson_tasks import _open_files
    from poisson_tasks import providers as _providers

    chosen = MODELS.get(model) if row is None else row
    if chosen is None:
        return _refuse(
            f"{model} is not a model of the version 2 design; they are {', '.join(MODELS)}"
        )
    if cap <= 0:
        return _refuse(f"the cap is ${cap}; give a cap above zero, in dollars")
    try:
        # before the key is read or anything is written; the run engine makes the room
        _open_files.check(
            min(max(1, concurrency), max(design.episodes_per_arm, design.phase1_episodes_per_arm))
        )
    except _open_files.OpenFilesRefused as error:
        return _refuse(str(error))
    try:
        generator, own_generator = check_generators()
    except GeneratorMoved as error:
        return _refuse(str(error))
    url = chosen.base_url if base_url is None else base_url
    variable = key_var or _config.PRESETS[chosen.provider].api_key_env or _probe.KEY_VAR
    try:
        key = _probe.load_key(env_file, variable)
    except _probe.KeyMissing as error:
        return _refuse(f"{error}; the run reads the key from there")
    _os.environ[variable] = key
    del key
    check = _providers.check_key(
        _config.ModelConfig(
            provider=chosen.provider, name=model, base_url=url, api_key_env=variable
        )
    )
    if check.status not in (_providers.ACCEPTED, _providers.NOT_CHECKABLE):
        return _refuse(
            f"{check.detail} (the key was read from {_pathlib.Path(env_file).resolve()})"
        )
    folder = _pathlib.Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    record_path = folder / "record.json"
    price = chosen.price
    try:
        check_record(
            record_path,
            card_record(
                design,
                model=model,
                role=chosen.role,
                base_url=url,
                decoding=chosen.decoding,
                command="python -m poisson_tasks.card_run run",
                extra={
                    "model_entry": {
                        "id": model,
                        "endpoint_host": _host(url),
                        "input_rate": price.input,
                        "cached_input_rate": price.cached_input,
                        "output_rate": price.output,
                    },
                    "serving": {
                        "kind": "hosted",
                        "endpoint_host": _host(url),
                        "api_surface": chosen.api_surface,
                        "provider": chosen.provider,
                    },
                    "rate_read_date": price.read_on,
                    "prompt_length_threshold": chosen.prompt_length_threshold,
                    "aliases": list(chosen.aliases),
                    "registered_endpoint": url == chosen.base_url,
                    "registered_cap": chosen.cap,
                },
            ),
            {"when": _now(), "model": model, "cap": cap, "concurrency": concurrency,
             "design": DESIGN_NAME},
        )
    except ValueError as error:
        return _refuse(str(error))
    _say(f"generator {generator} (frozen), own tools {own_generator} (frozen)")
    _say(
        f"{model} ({chosen.role}): {len(design.arms)} arms x {len(design.seeds)} tasks x "
        f"{design.attempts} attempts = {len(design.arms) * design.episodes_per_arm} episodes, "
        f"after phase 1's {len(design.arms) * design.phase1_episodes_per_arm}; cap ${cap:.2f} "
        f"(registered ${chosen.cap:.2f}), {concurrency} at once"
    )

    def plan_for(arms: _Sequence[str], seeds: _Sequence[int], attempts: int, own: bool) -> _Any:
        return _plan(
            design, arms, seeds, attempts, model=model, row=chosen, base_url=url,
            key_var=variable, own=own_tools() if own else None,
        )

    def stopped(phase: str, ended: _Phase, spent: float, ran: int) -> int:
        _write_json(
            folder / "status.json",
            {"phase": phase, "verdict": "stopped", "stop": ended.stop, "owed": ended.owed,
             "spent": spent, "cap": cap},
        )
        _close_invocation(record_path, episodes_run=ran, exit=4, stop=ended.stop)
        return 4

    def spent_now() -> float:
        return sum(_spent(folder / sub) for sub in (*_PHASE1_DIRS, *_CARD_DIRS))

    ran = 0
    phase1_path = folder / "phase1.json"
    phase1 = _read_json(phase1_path)
    if isinstance(phase1, dict) and not phase1.get("passed"):
        _say(
            "STOP: phase 1 stopped the run in this folder, so nothing more runs here "
            f"(${float(phase1.get('spent') or 0.0):.4f} spent): "
            + "; ".join(phase1.get("reasons", []))
        )
        _close_invocation(record_path, episodes_run=0, exit=2)
        return 2
    with _cal.answers_recorded():
        if not isinstance(phase1, dict):
            ended = _run_phase(
                folder, _PHASE1_DIRS, design, design.phase1_seeds, design.phase1_attempts,
                phase="phase 1", cap=cap, concurrency=concurrency, plan_for=plan_for,
            )
            ran += ended.run
            spent = sum(_spent(folder / sub) for sub in _PHASE1_DIRS)
            if ended.stop in _RESUMABLE:
                _say(
                    f"STOP: phase 1 stopped ({ended.stop}) with {ended.owed} episodes owed; "
                    f"${spent:.4f} spent. Run the same command again to resume."
                )
                if ended.first_error:
                    _say(f"first error: {ended.first_error}")
                return stopped("phase1", ended, spent, ran)
            records, tallies = _collect(folder, _PHASE1_DIRS, design, model)
            phase1 = {
                **phase1_gate(
                    records, tallies, design=design, model=model, aliases=chosen.aliases
                ),
                "spent": spent,
                "tallies": tallies,
            }
            if ended.stop is not None:
                # the run engine gave up on a streak of failed episodes: phase 1's first stop
                phase1["engine_stop"] = ended.stop
                if "instrument" not in phase1["stops"]:
                    phase1["stops"] = ["instrument", *phase1["stops"]]
                    phase1["reasons"] = [
                        f"the run engine stopped phase 1 ({ended.stop})", *phase1["reasons"]
                    ]
                phase1["passed"] = False
                if ended.first_error:
                    phase1["first_error"] = ended.first_error
            _write_json(phase1_path, phase1)
            if not phase1["passed"]:
                _say(f"STOP: phase 1 stopped the run; ${spent:.4f} spent")
                for reason in phase1["reasons"]:
                    _say(f"  {reason}")
                if phase1.get("first_error"):
                    _say(f"first error: {phase1['first_error']}")
                _write_json(
                    folder / "status.json",
                    {"phase": "phase1", "verdict": "stopped", "stop": "phase1",
                     "owed": len(design.arms) * design.episodes_per_arm, "spent": spent,
                     "cap": cap},
                )
                _close_invocation(record_path, episodes_run=ran, exit=2)
                return 2
        _say(
            f"phase 1 passed: {phase1['episodes']} episodes, ${float(phase1['spent']):.4f}"
        )

        status = _read_json(folder / "status.json")
        if (isinstance(status, dict) and status.get("phase") == "card"
                and status.get("verdict") == "done"):
            # A finished run is not run again: that would re-run the episodes that failed for
            # instrument reasons.  Only a recorded re-run of a void arm reopens it.
            _say("the run finished in this folder; nothing to run, its files are written again")
            ended = _Phase(owed=int(status.get("owed") or 0))
        else:
            ended = _run_phase(
                folder, _CARD_DIRS, design, design.seeds, design.attempts,
                phase="card", cap=cap, concurrency=concurrency, plan_for=plan_for,
            )
            ran += ended.run
    spent = spent_now()
    records, tallies = _collect(folder, _CARD_DIRS, design, model)
    _cal.write_records(
        [row for arm in design.arms for row in records[arm]],
        folder / "records" / _cal.RECORDS_FILE,
    )
    _write_json(folder / "records" / "tallies.json", tallies)
    verdict = "done" if ended.stop is None else "stopped"
    _write_json(
        folder / "status.json",
        {"phase": "card", "verdict": verdict, "stop": ended.stop, "owed": ended.owed,
         "spent": spent, "cap": cap},
    )
    _close_invocation(
        record_path, episodes_run=ran, exit=0 if ended.stop is None else 4, stop=ended.stop
    )
    artifact = write_artifact(folder)
    failed = sum(
        1 for rows in records.values() for row in rows if row.label in _cal.INSTRUMENT_LABELS
    )
    if failed:
        _say(
            f"{failed} episode(s) failed for instrument reasons; each counts in its arm's "
            "instrument rate"
        )
    void = [entry["arm"] for entry in artifact["provenance"]["run"]["void_arms"]]
    if void:
        _say(
            f"void: {', '.join(void)}; an arm void for an instrument cause may be run once "
            "more (rerun-void)"
        )
    _say(
        f"spent ${spent:.4f} of the ${cap:.2f} cap; {len(artifact['arms_complete'])} of "
        f"{len(design.arms)} arms complete; records in {folder / 'records' / _cal.RECORDS_FILE}"
    )
    if ended.stop is not None:
        _say(
            f"STOPPED ({ended.stop}): {ended.owed} episodes owed. Every finished episode is "
            "kept; run the same command again, with a larger cap if the cap stopped it, to go on."
        )
        if ended.first_error:
            _say(f"first error: {ended.first_error}")
        return 4
    return 0


# ---------------------------------------------------------------------------
# the one re-run a void arm may have
# ---------------------------------------------------------------------------


class RerunRefused(ValueError):
    """A re-run the pre-registration does not allow."""


_RERUN_CAUSES = ("instrument", "length_stops")
"""The causes a void arm may be run again once for: the instrument's, as the pre-registration
has it (our side, the key, the provider, the server), and calls cut by the completion limit,
which it names an instrument cause."""


def start_rerun(
    arm: str,
    void: _Sequence[_Mapping[str, _Any]],
    *,
    cause: str,
    reruns: _Sequence[_Mapping[str, _Any]],
    folders: _Sequence[tuple[_pathlib.Path, _pathlib.Path]],
) -> dict[str, _Any]:
    """Set a void arm aside for its one re-run, and return the entry that records it.

    Allowed only for an arm `void_arms` names void for an instrument cause, only once, and only
    with what failed written down.  Each of `folders` is a pair: where the arm's run folder is,
    and where it is kept instead, so the void attempt and the re-run are both kept; the next
    call of the run then runs the arm again from nothing.  Anything else is a new
    pre-registration."""
    if not cause.strip():
        raise RerunRefused(
            "a re-run records its cause: say what failed (the server, the key or the provider)"
        )
    if any(str(entry.get("arm")) == arm for entry in reruns):
        raise RerunRefused(f"{arm} has had its one re-run; another is a new pre-registration")
    found = next((entry for entry in void if entry.get("arm") == arm), None)
    if found is None:
        raise RerunRefused(
            f"{arm} is not void (an arm is void once it is complete and over a threshold); "
            "there is nothing to run again"
        )
    causes = [str(entry["cause"]) for entry in found["causes"]]
    if not any(name in _RERUN_CAUSES for name in causes):
        raise RerunRefused(
            f"{arm} is void by {', '.join(causes)}, which is no instrument cause; a re-run for "
            "any other cause is a new pre-registration"
        )
    for source, target in folders:
        if source.exists():
            if target.exists():
                raise RerunRefused(f"{target} already exists; it is not overwritten")
            target.parent.mkdir(parents=True, exist_ok=True)
            _shutil.move(str(source), str(target))
    return {
        "arm": arm,
        "cause": cause.strip(),
        "void_by": list(found["causes"]),
        "kept_at": [str(target) for _, target in folders],
        "when": _now(),
    }


def rerun_void(folder: _pathlib.Path, arm: str, cause: str) -> int:
    """Set a void arm of a hosted run aside for its one re-run; `run` then runs it again."""
    folder = _pathlib.Path(folder)
    record = _read_json(folder / "record.json")
    if not isinstance(record, dict):
        return _refuse(f"{folder} holds no run (no record.json)")
    if arm not in record.get("arms", []):
        return _refuse(f"{arm} is not one of this run's arms")
    try:
        artifact = build_artifact(folder)
    except ValueError as error:
        return _refuse(str(error))
    reruns = list(_read_json(folder / "reruns.json") or [])
    sub = _CARD_DIRS[1] if _is_own(arm) else _CARD_DIRS[0]
    name = _run._arm_dir(arm)
    try:
        entry = start_rerun(
            arm,
            artifact["provenance"]["run"]["void_arms"],
            cause=cause,
            reruns=reruns,
            folders=[(folder / sub / name, folder / "void" / f"{name}-1")],
        )
    except RerunRefused as error:
        return _refuse(str(error))
    _write_json(folder / "reruns.json", [*reruns, entry])
    status = _read_json(folder / "status.json") or {}
    _write_json(folder / "status.json", {**status, "verdict": "rerun"})
    _say(f"{arm} is set aside in {entry['kept_at'][0]}; run the same run command to re-run it")
    return 0


# ---------------------------------------------------------------------------
# the command line (a module, not a command of the tool)
# ---------------------------------------------------------------------------


def build_parser() -> _argparse.ArgumentParser:
    parser = _argparse.ArgumentParser(
        prog="python -m poisson_tasks.card_run",
        description="The version 2 card's run on a hosted model: phase 1 and the 56 arms under a "
        "spend cap, a void arm's one re-run, and filing a finished run (see the module "
        "docstring).",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("run", help="phase 1, then every arm; run again, it goes on")
    p.add_argument("--model", required=True, choices=tuple(MODELS),
                   help="the model, a row of the design's table")
    p.add_argument("--folder", type=_pathlib.Path, required=True,
                   help="the run's folder: its record, both phases, the records, the artifact")
    p.add_argument("--cap", type=float, required=True,
                   help="the folder's spend cap, in dollars; a larger one on a later call "
                        "resumes a run the cap stopped")
    p.add_argument("--concurrency", type=int, default=CONCURRENCY,
                   help=f"episodes in flight at once (default: {CONCURRENCY})")
    p.add_argument("--env-file", type=_pathlib.Path, default=_pathlib.Path(".env"),
                   help="the file the key is read from (default: .env)")
    p.add_argument("--key-var", default=None,
                   help="the variable whose line in that file holds the key (default: the "
                        "provider's own, OPENAI_API_KEY or ANTHROPIC_API_KEY)")
    p.add_argument("--base-url", default=None, help=_argparse.SUPPRESS)
    p = sub.add_parser("rerun-void", help="set a void arm aside for its one re-run")
    p.add_argument("--folder", type=_pathlib.Path, required=True)
    p.add_argument("--arm", required=True)
    p.add_argument("--cause", required=True,
                   help="what failed: the server, the key or the provider")
    p = sub.add_parser("artifact", help="write a run folder's artifact.json again; runs nothing")
    p.add_argument("--folder", type=_pathlib.Path, required=True)
    p = sub.add_parser("file", help="copy a finished run's card files under a calibration folder")
    p.add_argument("--folder", type=_pathlib.Path, required=True)
    p.add_argument("--into", type=_pathlib.Path, required=True,
                   help="the calibration folder; a bridge record goes under its bridge/")
    return parser


def main(argv: _Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(list(_sys.argv[1:] if argv is None else argv))
    if args.command == "run":
        return run_card(
            args.folder,
            model=args.model,
            cap=args.cap,
            concurrency=args.concurrency,
            env_file=args.env_file,
            key_var=args.key_var,
            base_url=args.base_url,
        )
    if args.command == "rerun-void":
        return rerun_void(args.folder, args.arm, args.cause)
    try:
        if args.command == "artifact":
            artifact = write_artifact(args.folder)
            _say(f"{args.folder / 'artifact.json'}: {len(artifact['arms_complete'])} arms complete")
            return 0
        if args.command == "file":
            _say(str(file_run(args.folder, args.into)))
            return 0
    except ValueError as error:
        return _refuse(str(error))
    raise AssertionError(args.command)


if __name__ == "__main__":
    _sys.exit(main())
