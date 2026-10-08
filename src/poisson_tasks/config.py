"""The plan: `tasks.toml`, init's flags, the provider presets and the resolved plan.

One settings file says what to run, against which model, and when to stop.  This module reads
it, writes it, builds it from `init`'s flags, and resolves it to the plan a run carries out: the
arms, the seeds, the attempts, the model and the decoding.  `tests/test_fd1_config.py` says what
each name does.

**One validation.**  A file and a set of flags are both turned into the same document and read
by the same reader, so a value refused in the file is refused as a flag, under the same key.  A
refusal is a `ConfigError`: one line, naming the setting (and, for a file, the line it is written
on), with `.key` its dotted path and `.suggestion` the nearest known key or choice.

**Pure.**  Importing this module imports no `verifiers` and none of `tasks`, `calibration` and
`export`, which load the tokenizer file at import; reading, writing and resolving open no socket
and write no file.  So a settings file can be read and checked in an environment with no
tokenizer.  Resolving a plan needs the published design (`calibration`), and so the tokenizer:
`resolve_plan` checks for the file first and raises `TokenizerMissing` before importing anything.

**The design's literals.**  Because `calibration` cannot be imported here, this module carries its
own copy of the declared decoding, of model A's name and rates, and of the design's sixty tasks
and five attempts.  The tests hold each equal to the published card's.
"""

from __future__ import annotations

import dataclasses
import datetime
import hashlib
import importlib
import json
import math
import os
import re
import shlex
import tomllib
import types
import urllib.parse
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from poisson_tasks.arms import _CONTROL_PAIRS, DEFAULT_GENERATOR_VERSION, RECIPES, arm_from_id
from poisson_tasks.knobs import ArmSpec, arm_id, levels
from poisson_tasks.tokenizer import _ENCODING_PATH

__all__ = [
    "ProjectConfig",
    "ModelConfig",
    "PriceConfig",
    "MeasureConfig",
    "TasksConfig",
    "DecodingConfig",
    "LimitsConfig",
    "OutputConfig",
    "ConfigError",
    "TokenizerMissing",
    "load_config",
    "loads_config",
    "dump_config",
    "InitFlag",
    "INIT_FLAGS",
    "config_from_init_args",
    "default_spend_cap",
    "Plan",
    "resolve_plan",
    "plan_hash",
    "equivalent_init_command",
    "Preset",
    "PRESETS",
    "PRESET_NAMES",
    "SCHEMA_VERSION",
]

SCHEMA_VERSION = 1

_NOT_SENT = "not sent"
# `[measure] preset` takes each recipe offered, then `custom`; a recipe whose knobs have not
# shipped is refused by name.
_PRESETS = (*(name for name, recipe in RECIPES.items() if recipe.offered), "custom")
_KNOBS = tuple(_CONTROL_PAIRS)
_STRICTNESSES = ("strict", "leaky")
_FIRST_LOOK_LEVELS = (1, 3, 8)
_SEED_SPACE = 2**32

# The published cards' design, and model A's declared rates: `calibration.S`, `calibration.N`,
# `calibration.DECODING`, `calibration.MODEL_A`, and the rates and the date they were read in
# model A's `artifact.json`.
_CARD_TASKS = 60
_CARD_ATTEMPTS = 5
_CARD_DECODING: dict[str, Any] = {
    "temperature": 1.0,
    "top_p": 1.0,
    "reasoning_effort": "low",
    "max_tokens": 2048,
}
_PUBLISHED_MODEL = "gpt-5-nano-2025-08-07"
_PUBLISHED_PRICE = {
    "input": 0.05,
    "cached_input": 0.005,
    "output": 0.40,
    "read_on": "2026-09-25",
}

_DEFAULT_TOKEN_CAP = 2_000_000
_DEFAULT_SPEND_FLOOR = 1.0


class ConfigError(ValueError):
    """A config refused: `.key` is the dotted path, `.line` the line where one is known, and
    `.suggestion` the nearest known key or choice within two edits."""

    def __init__(
        self,
        message: str,
        *,
        key: str | None = None,
        line: int | None = None,
        suggestion: str | None = None,
    ) -> None:
        super().__init__(message)
        self.key = key
        self.line = line
        self.suggestion = suggestion


class TokenizerMissing(FileNotFoundError):
    """The tokenizer file is not in this environment, so no plan can be resolved."""


# ---------------------------------------------------------------------------
# the provider presets
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Preset:
    """One provider preset.  `None` means the setting has no default and must be given.
    `key_check_path` is appended to the endpoint, with `{model}` for the model's name.
    `asks_endpoint` and `asks_price` say whether `init` asks that question for this preset."""

    name: str
    label: str
    endpoint: str | None
    api_key_env: str | None
    default_model: str | None
    key_check_path: str
    asks_endpoint: bool
    asks_price: bool


_PRESET_ROWS = (
    Preset(
        name="openai",
        label="OpenAI",
        endpoint="https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY",
        default_model=_PUBLISHED_MODEL,
        key_check_path="/models/{model}",
        asks_endpoint=False,
        asks_price=True,
    ),
    Preset(
        name="anthropic",
        label="Anthropic",
        endpoint="https://api.anthropic.com/v1/",
        api_key_env="ANTHROPIC_API_KEY",
        default_model=None,
        key_check_path="/models/{model}",
        asks_endpoint=False,
        asks_price=True,
    ),
    Preset(
        name="ollama",
        label="A model on this machine, through Ollama",
        endpoint="http://127.0.0.1:11434/v1",
        api_key_env="",
        default_model="qwen3:8b",
        key_check_path="/models",
        asks_endpoint=False,
        asks_price=False,
    ),
    Preset(
        name="vllm",
        label="A model on this machine or your network, through vLLM",
        endpoint="http://127.0.0.1:8000/v1",
        api_key_env="",
        default_model=None,
        key_check_path="/models",
        asks_endpoint=True,
        asks_price=False,
    ),
    Preset(
        name="openai-compatible",
        label="Another OpenAI-compatible endpoint (a URL)",
        endpoint=None,
        api_key_env=None,
        default_model=None,
        key_check_path="/models",
        asks_endpoint=True,
        asks_price=True,
    ),
)

PRESETS: Mapping[str, Preset] = types.MappingProxyType({row.name: row for row in _PRESET_ROWS})
PRESET_NAMES: tuple[str, ...] = tuple(PRESETS)


# ---------------------------------------------------------------------------
# the config: its attributes are the file's keys
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class PriceConfig:
    input: float
    cached_input: float
    output: float
    read_on: str


@dataclasses.dataclass(frozen=True)
class ModelConfig:
    provider: str
    name: str
    base_url: str
    api_key_env: str
    allow_plain_http_key: bool = False
    price: PriceConfig | None = None


@dataclasses.dataclass(frozen=True)
class MeasureConfig:
    preset: str
    knob: str | None = None
    levels: tuple[int, ...] | None = None
    controls: bool | None = None
    strictness: str | None = None


@dataclasses.dataclass(frozen=True)
class TasksConfig:
    per_level: int | None
    seeds: tuple[int, ...] | None
    attempts: int
    generator_version: str | None = None


@dataclasses.dataclass(frozen=True)
class DecodingConfig:
    temperature: float
    top_p: float | str
    reasoning_effort: str
    max_tokens: int | str


@dataclasses.dataclass(frozen=True)
class LimitsConfig:
    spend_usd: float | None
    tokens: int | None
    max_model_calls: int
    concurrency: int


@dataclasses.dataclass(frozen=True)
class OutputConfig:
    runs: str
    tasks: str


@dataclasses.dataclass(frozen=True)
class ProjectConfig:
    version: int
    model: ModelConfig
    measure: MeasureConfig
    tasks: TasksConfig
    decoding: DecodingConfig
    limits: LimitsConfig
    output: OutputConfig


# The file's tables and the keys each may hold, in the order the file is written in.
_KEYS: dict[str, tuple[str, ...]] = {
    "": ("version", "model", "measure", "tasks", "decoding", "limits", "output"),
    "model": ("provider", "name", "base_url", "api_key_env", "allow_plain_http_key", "price"),
    "model.price": ("input", "cached_input", "output", "read_on"),
    "measure": ("preset", "knob", "levels", "controls", "strictness"),
    "tasks": ("per_level", "seeds", "attempts", "generator_version"),
    "decoding": ("temperature", "top_p", "reasoning_effort", "max_tokens"),
    "limits": ("spend_usd", "tokens", "max_model_calls", "concurrency"),
    "output": ("runs", "tasks"),
}


# ---------------------------------------------------------------------------
# words for a message
# ---------------------------------------------------------------------------


def _show(value: Any) -> str:
    """A value as the file would write it, for a message: never a Python repr."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_show(item) for item in value) + "]"
    if isinstance(value, Mapping):
        return "a table"
    return str(value)


def _listed(items: Sequence[Any], last: str = "and") -> str:
    words = [str(item) for item in items]
    if len(words) < 2:
        return "".join(words)
    return ", ".join(words[:-1]) + f" {last} " + words[-1]


def _not_shipped(knobs: Sequence[str]) -> str:
    """The knobs a recipe waits on, said as not shipped: it is offered once any one ships."""
    if len(knobs) == 1:
        return f"{knobs[0]} has not shipped"
    if len(knobs) == 2:
        return f"neither {knobs[0]} nor {knobs[1]} has shipped"
    return f"none of {_listed(knobs)} has shipped"


def _edits(a: str, b: str) -> int:
    """The edit distance between two words: insertions, deletions and substitutions."""
    row = list(range(len(b) + 1))
    for i, left in enumerate(a, start=1):
        previous, row[0] = row[0], i
        for j, right in enumerate(b, start=1):
            previous, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, previous + (left != right))
    return row[-1]


def _nearest(word: str, known: Sequence[str]) -> str | None:
    """The known word nearest to `word`, when it is within two edits; the first of equals."""
    best: tuple[int, str] | None = None
    for candidate in known:
        distance = _edits(word, candidate)
        if distance <= 2 and (best is None or distance < best[0]):
            best = (distance, candidate)
    return None if best is None else best[1]


def _whole(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


# ---------------------------------------------------------------------------
# where each key is written in a file
# ---------------------------------------------------------------------------

_KEY_PART = r"""(?:[A-Za-z0-9_-]+|"[^"]*"|'[^']*')"""
_DOTTED_KEY = rf"{_KEY_PART}(?:\s*\.\s*{_KEY_PART})*"
_HEADER = re.compile(rf"^\s*\[\s*({_DOTTED_KEY})\s*\]\s*(?:#.*)?$")
_ASSIGNMENT = re.compile(rf"^\s*({_DOTTED_KEY})\s*=")


def _key_lines(text: str) -> dict[str, int]:
    """The 1-based line each table header and each key is written on, by dotted path.

    `tomllib` gives a line only for a file that is not TOML, so a refused key's line is found in
    the text.  It reads table headers and `key = value` lines, which is how this file is written;
    a key set some other way (inside an inline table) takes the line of the table around it.
    """
    lines: dict[str, int] = {}
    table: list[str] = []
    for number, line in enumerate(text.splitlines(), start=1):
        header = _HEADER.match(line)
        assignment = None if header else _ASSIGNMENT.match(line)
        if header:
            table = [part.strip("\"'") for part in re.findall(_KEY_PART, header.group(1))]
            parts = table
        elif assignment:
            parts = table + [
                part.strip("\"'") for part in re.findall(_KEY_PART, assignment.group(1))
            ]
        else:
            continue
        for end in range(len(table) + 1 if assignment else 1, len(parts) + 1):
            lines.setdefault(".".join(parts[:end]), number)
    return lines


def _name_in_file(key: str) -> str:
    """A key as a reader of the file knows it: `[tasks] per_level`, `[measure]`, `version`."""
    table, _, last = key.rpartition(".")
    if key in _KEYS:
        return f"[{key}]"
    return f"[{table}] {last}" if table else last


# ---------------------------------------------------------------------------
# the one reader, of a file's document and of the document init's flags make
# ---------------------------------------------------------------------------

_MISSING: Any = object()


class _Reader:
    """Reads a document (the nested tables of a `tasks.toml`) into a `ProjectConfig`, or refuses.

    `name` turns a key into what its author calls it (the file's `[tasks] per_level`, or the
    flag `--tasks-per-level`), `source` is the file's name or `None` for flags, and `lines` is
    where each key is written.
    """

    def __init__(
        self,
        document: Mapping[str, Any],
        *,
        name: Callable[[str], str],
        source: str | None = None,
        lines: Mapping[str, int] | None = None,
    ) -> None:
        self.document = document
        self.name = name
        self.source = source
        self.lines = lines or {}

    # -- refusing ----------------------------------------------------------

    def line_of(self, key: str) -> int | None:
        """The line `key` is written on, or the line of the nearest table around it."""
        while key:
            if key in self.lines:
                return self.lines[key]
            key = key.rpartition(".")[0]
        return None

    def refusal(self, key: str, problem: str, *, suggestion: str | None = None) -> ConfigError:
        line = self.line_of(key)
        where = ""
        if self.source is not None:
            where = f"{self.source}: " if line is None else f"{self.source} line {line}: "
        return ConfigError(where + problem, key=key, line=line, suggestion=suggestion)

    # -- reaching into the document ------------------------------------------

    def get(self, key: str) -> Any:
        value: Any = self.document
        for part in key.split("."):
            if not isinstance(value, Mapping) or part not in value:
                return _MISSING
            value = value[part]
        return value

    def need(self, key: str) -> Any:
        value = self.get(key)
        if value is _MISSING:
            raise self.refusal(key, f"{self.name(key)} is not set, and it has to be")
        return value

    def table(self, key: str, *, required: bool = True) -> bool:
        """Whether the table `key` is there; refused when it is something other than a table."""
        value = self.get(key)
        if value is _MISSING:
            if required:
                raise self.refusal(key, f"{self.name(key)} is missing, and it has to be there")
            return False
        if not isinstance(value, Mapping):
            raise self.refusal(
                key, f"{key.rpartition('.')[2]} is {_show(value)}; it must be a table, [{key}]"
            )
        return True

    # -- one value of each kind ----------------------------------------------

    def whole(self, key: str, value: Any, *, low: int, high: int | None = None) -> int:
        allowed = f"{low} or more" if high is None else f"from {low} to {high}"
        if not _whole(value):
            raise self.refusal(
                key, f"{self.name(key)} is {_show(value)}; it must be a whole number, {allowed}"
            )
        if value < low or (high is not None and value > high):
            raise self.refusal(key, f"{self.name(key)} is {value}; it must be {allowed}")
        return int(value)

    def number(
        self,
        key: str,
        value: Any,
        *,
        above: float | None = None,
        low: float = 0.0,
        high: float | None = None,
    ) -> float:
        if above is not None:
            allowed = f"above {above:g}" + ("" if high is None else f" and at most {high:g}")
        else:
            allowed = f"{low:g} or more"
        if not _number(value):
            raise self.refusal(
                key, f"{self.name(key)} is {_show(value)}; it must be a number, {allowed}"
            )
        too_low = value <= above if above is not None else value < low
        if too_low or (high is not None and value > high):
            raise self.refusal(key, f"{self.name(key)} is {_show(value)}; it must be {allowed}")
        return float(value)

    def text(self, key: str, value: Any, what: str) -> str:
        if not isinstance(value, str) or not value:
            raise self.refusal(key, f"{self.name(key)} is {_show(value)}; it must be {what}")
        return value

    def switch(self, key: str, value: Any) -> bool:
        if not isinstance(value, bool):
            raise self.refusal(key, f"{self.name(key)} is {_show(value)}; it must be true or false")
        return value

    def choice(self, key: str, value: Any, choices: Sequence[str], what: str) -> str:
        if isinstance(value, str) and value in choices:
            return value
        offered = _listed(choices, "or")
        if not isinstance(value, str):
            raise self.refusal(
                key, f"{self.name(key)} is {_show(value)}; it must be one of {offered}"
            )
        near = _nearest(value, choices)
        hint = f'; did you mean "{near}"?' if near is not None else f"; it is one of {offered}"
        raise self.refusal(
            key, f"{self.name(key)}: {_show(value)} is not {what}{hint}", suggestion=near
        )

    def whole_list(self, key: str, value: Any, what: str) -> tuple[int, ...]:
        """A non-empty list of whole numbers with none repeated."""
        if not isinstance(value, list) or not all(_whole(item) for item in value):
            raise self.refusal(
                key, f"{self.name(key)} is {_show(value)}; it must be a list of whole numbers"
            )
        if not value:
            raise self.refusal(key, f"{self.name(key)} is empty; it must hold at least one {what}")
        repeated = sorted({item for item in value if value.count(item) > 1})
        if repeated:
            raise self.refusal(
                key,
                f"{self.name(key)} holds {_listed(repeated)} more than once; "
                f"each {what} is given once",
            )
        return tuple(value)

    # -- unknown keys and tables ---------------------------------------------

    def refuse_unknown(self, table: str = "") -> None:
        """Refuse the first key or table, in the order written, that the file does not have."""
        here = self.document if not table else self.get(table)
        for key, value in here.items():
            path = f"{table}.{key}" if table else key
            if key not in _KEYS[table]:
                near = _nearest(key, _KEYS[table])
                suggestion = None if near is None else (f"{table}.{near}" if table else near)
                if isinstance(value, Mapping):
                    problem = f"[{path}] is not a table of this file"
                    hint = "" if suggestion is None else f"; did you mean [{suggestion}]?"
                else:
                    problem = (f"[{table}] " if table else "") + f'"{key}" is not a setting'
                    hint = "" if near is None else f'; did you mean "{near}"?'
                raise self.refusal(path, problem + hint, suggestion=suggestion)
            if path in _KEYS and isinstance(value, Mapping):
                self.refuse_unknown(path)

    # -- the tables ----------------------------------------------------------

    def config(self) -> ProjectConfig:
        self.refuse_unknown()
        version = self.version()
        model = self.model()
        measure = self.measure()
        tasks = self.tasks(measure)
        decoding = self.decoding()
        limits = self.limits(model)
        output = self.output()
        return ProjectConfig(
            version=version,
            model=model,
            measure=measure,
            tasks=tasks,
            decoding=decoding,
            limits=limits,
            output=output,
        )

    def version(self) -> int:
        key = "version"
        version = self.whole(key, self.need(key), low=1)
        if version > SCHEMA_VERSION:
            raise self.refusal(
                key,
                f"{self.name(key)} is {version}, which a newer Poisson Tasks wrote; this one "
                f"({_package_version()}) reads version {SCHEMA_VERSION}",
            )
        return version

    def model(self) -> ModelConfig:
        self.table("model")
        provider = self.choice(
            "model.provider", self.need("model.provider"), PRESET_NAMES, "a provider"
        )
        name = self.text(
            "model.name", self.need("model.name"), "the model's name, as the provider spells it"
        )
        key = "model.base_url"
        base_url = self.text(key, self.need(key), "the endpoint's URL")
        parts = urllib.parse.urlsplit(base_url)
        if parts.scheme not in ("http", "https") or not parts.netloc:
            raise self.refusal(
                key,
                f"{self.name(key)} is {_show(base_url)}; it must be a URL starting with "
                "https:// or http://",
            )
        key = "model.api_key_env"
        api_key_env = self.need(key)
        if not isinstance(api_key_env, str):
            raise self.refusal(
                key,
                f"{self.name(key)} is {_show(api_key_env)}; it must be the name of the "
                'environment variable that holds the key, or "" for no key',
            )
        if api_key_env and not (
            re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", api_key_env)
            and "API_KEY" in api_key_env.upper()
        ):
            raise self.refusal(
                key,
                f"{self.name(key)} is {_show(api_key_env)}; the variable's name must contain "
                'API_KEY, so that the key is kept from the program under test, or be "" for no '
                "key",
            )
        key = "model.allow_plain_http_key"
        allow = False if self.get(key) is _MISSING else self.switch(key, self.get(key))
        price = None
        if self.table("model.price", required=False):
            figures = {
                field: self.number(f"model.price.{field}", self.need(f"model.price.{field}"))
                for field in ("input", "cached_input", "output")
            }
            price = PriceConfig(read_on=self.read_on(), **figures)
        return ModelConfig(
            provider=provider,
            name=name,
            base_url=base_url,
            api_key_env=api_key_env,
            allow_plain_http_key=allow,
            price=price,
        )

    def read_on(self) -> str:
        key = "model.price.read_on"
        value = self.need(key)
        if type(value) is datetime.date:
            return value.isoformat()
        if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value, re.ASCII):
            try:
                datetime.date.fromisoformat(value)
            except ValueError:
                pass
            else:
                return value
        raise self.refusal(
            key,
            f"{self.name(key)} is {_show(value)}; it must be the date the prices were read, "
            'as "2026-09-25"',
        )

    def measure(self) -> MeasureConfig:
        self.table("measure")
        key = "measure.preset"
        value = self.need(key)
        recipe = RECIPES.get(value) if isinstance(value, str) else None
        if recipe is not None and not recipe.offered:
            raise self.refusal(
                key,
                f"{self.name(key)}: {_show(value)} is a recipe not offered yet, because "
                f"{_not_shipped(recipe.waiting)}",
            )
        preset = self.choice(key, value, _PRESETS, "a recipe")
        custom_keys = ("knob", "levels", "controls", "strictness")
        if preset != "custom":
            for field in custom_keys:
                key = f"measure.{field}"
                if self.get(key) is not _MISSING:
                    raise self.refusal(
                        key,
                        f"{self.name(key)} is read only when {self.name('measure.preset')} is "
                        f'"custom"; with "{preset}" it would change nothing, so it is refused',
                    )
            return MeasureConfig(preset=preset)

        given = {field: self.get(f"measure.{field}") for field in custom_keys}
        knob = "depth"
        if given["knob"] is not _MISSING:
            knob = self.choice("measure.knob", given["knob"], _KNOBS, "a knob")
        candidates = levels(knob)
        chosen = candidates
        if given["levels"] is not _MISSING:
            key = "measure.levels"
            chosen = self.whole_list(key, given["levels"], "level")
            for level in chosen:
                if level not in candidates:
                    raise self.refusal(
                        key,
                        f"{self.name(key)}: level {level} is not a {knob} level; the levels "
                        f"are {_listed(candidates)}",
                    )
        controls = False
        if given["controls"] is not _MISSING:
            key = "measure.controls"
            controls = self.switch(key, given["controls"])
            pairs = _CONTROL_PAIRS[knob]
            if controls and not any(low in chosen and high in chosen for low, high in pairs):
                both = _listed([f"{low} and {high}" for low, high in pairs], "or")
                raise self.refusal(
                    key,
                    f"{self.name(key)} is true, and no control arm fits these levels: a {knob} "
                    f"control arm needs both of its levels chosen, {both}",
                )
        strictness = "strict"
        if given["strictness"] is not _MISSING:
            strictness = self.choice(
                "measure.strictness", given["strictness"], _STRICTNESSES, "a strictness"
            )
        return MeasureConfig(
            preset=preset, knob=knob, levels=chosen, controls=controls, strictness=strictness
        )

    def tasks(self, measure: MeasureConfig) -> TasksConfig:
        card = measure.preset == "card"
        there = self.table("tasks", required=not card)
        given = {
            field: self.get(f"tasks.{field}") if there else _MISSING for field in _KEYS["tasks"]
        }
        version = None
        if given["generator_version"] is not _MISSING:
            version = self.text(
                "tasks.generator_version", given["generator_version"], "a generator version"
            )
        if card:
            return self.card_tasks(given, version)

        per_level: int | None = None
        seeds: tuple[int, ...] | None = None
        if given["seeds"] is not _MISSING:
            key = "tasks.seeds"
            if given["per_level"] is not _MISSING:
                raise self.refusal(
                    key,
                    f"{self.name(key)} and {self.name('tasks.per_level')} are both set; a plan "
                    "takes its tasks from one of them",
                )
            seeds = self.whole_list(key, given["seeds"], "seed")
            outside = [seed for seed in seeds if not 0 <= seed < _SEED_SPACE]
            if outside:
                raise self.refusal(
                    key,
                    f"{self.name(key)} holds {outside[0]}; a seed is a whole number from 0 to "
                    f"{_SEED_SPACE - 1}",
                )
        else:
            key = "tasks.per_level"
            per_level = self.whole(key, self.need(key), low=1, high=_CARD_TASKS)
        attempts = self.whole("tasks.attempts", self.need("tasks.attempts"), low=1)
        return TasksConfig(
            per_level=per_level, seeds=seeds, attempts=attempts, generator_version=version
        )

    def card_tasks(self, given: Mapping[str, Any], version: str | None) -> TasksConfig:
        """The card preset's `[tasks]`: absent, or exactly the published design."""
        design = (
            f"the published cards' design is {_CARD_TASKS} tasks per level and {_CARD_ATTEMPTS} "
            "attempts, and a plan that says anything else is not that design"
        )
        if given["seeds"] is not _MISSING:
            key = "tasks.seeds"
            raise self.refusal(key, f"{self.name(key)} is set; {design}")
        for field, fixed in (("per_level", _CARD_TASKS), ("attempts", _CARD_ATTEMPTS)):
            key = f"tasks.{field}"
            if given[field] is not _MISSING and (self.whole(key, given[field], low=1) != fixed):
                raise self.refusal(key, f"{self.name(key)} is {given[field]}; {design}")
        if version is not None and version != DEFAULT_GENERATOR_VERSION:
            key = "tasks.generator_version"
            raise self.refusal(
                key,
                f"{self.name(key)} is {_show(version)}; the published cards were measured at "
                f'"{DEFAULT_GENERATOR_VERSION}", and tasks at another version carry other ids',
            )
        return TasksConfig(
            per_level=_CARD_TASKS, seeds=None, attempts=_CARD_ATTEMPTS, generator_version=version
        )

    def decoding(self) -> DecodingConfig:
        self.table("decoding")
        key = "decoding.temperature"
        value = self.need(key)
        if value == _NOT_SENT:
            raise self.refusal(
                key,
                f'{self.name(key)} is "{_NOT_SENT}"; the temperature is always sent, because '
                "repeated attempts at a task need a decoding that is not deterministic",
            )
        temperature = self.number(key, value, above=0)
        key = "decoding.top_p"
        value = self.need(key)
        top_p: float | str = _NOT_SENT
        if value != _NOT_SENT:
            top_p = self.number(key, value, above=0, high=1)
        effort = self.text(
            "decoding.reasoning_effort",
            self.need("decoding.reasoning_effort"),
            f'a reasoning effort the provider takes, or "{_NOT_SENT}"',
        )
        key = "decoding.max_tokens"
        value = self.need(key)
        max_tokens: int | str = _NOT_SENT
        if value != _NOT_SENT:
            max_tokens = self.whole(key, value, low=1)
        return DecodingConfig(
            temperature=temperature, top_p=top_p, reasoning_effort=effort, max_tokens=max_tokens
        )

    def limits(self, model: ModelConfig) -> LimitsConfig:
        self.table("limits")
        spend: float | None = None
        tokens: int | None = None
        if self.get("limits.spend_usd") is not _MISSING:
            spend = self.number("limits.spend_usd", self.get("limits.spend_usd"), above=0)
        if self.get("limits.tokens") is not _MISSING:
            tokens = self.whole("limits.tokens", self.get("limits.tokens"), low=1)
        calls = self.whole("limits.max_model_calls", self.need("limits.max_model_calls"), low=1)
        concurrency = self.whole("limits.concurrency", self.need("limits.concurrency"), low=1)
        spend_name, tokens_name = self.name("limits.spend_usd"), self.name("limits.tokens")
        if spend is None and tokens is None:
            raise self.refusal(
                "limits",
                f"neither {spend_name} nor {tokens_name} is set, so nothing would stop the run; "
                "set one of them",
            )
        if spend is not None and model.price is None:
            raise self.refusal(
                "limits.spend_usd",
                f"{spend_name} is set and the model has no price, so dollars cannot be counted; "
                f"give the price, or cap the run with {tokens_name}",
            )
        return LimitsConfig(
            spend_usd=spend, tokens=tokens, max_model_calls=calls, concurrency=concurrency
        )

    def output(self) -> OutputConfig:
        self.table("output")
        return OutputConfig(
            runs=self.text("output.runs", self.need("output.runs"), "a folder's name"),
            tasks=self.text("output.tasks", self.need("output.tasks"), "a folder's name"),
        )


def _package_version() -> str:
    from importlib import metadata

    try:
        return "version " + metadata.version("poisson-tasks")
    except metadata.PackageNotFoundError:
        return "this version"


# ---------------------------------------------------------------------------
# reading and writing the file
# ---------------------------------------------------------------------------


def loads_config(text: str, *, source: str = "tasks.toml") -> ProjectConfig:
    """The config a `tasks.toml`'s text holds, or a `ConfigError` in one line."""
    try:
        document = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        said = str(error)
        at = re.search(r" \(at line (\d+), column \d+\)$", said)
        line = int(at.group(1)) if at else max(len(text.splitlines()), 1)
        problem = re.sub(r" \(at [^()]*\)$", "", said)
        raise ConfigError(f"{source} line {line}: this is not TOML: {problem}", line=line) from None
    return _Reader(document, name=_name_in_file, source=source, lines=_key_lines(text)).config()


def load_config(path: str | os.PathLike[str]) -> ProjectConfig:
    """The config the file at `path` holds."""
    source = os.fspath(path)
    with open(source, "rb") as file:
        raw = file.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise ConfigError(f"{source}: this is not a text file in UTF-8") from None
    return loads_config(text, source=source)


def _toml_text(value: str) -> str:
    """A TOML basic string."""
    out = ['"']
    for char in value:
        if char in ('"', "\\"):
            out.append("\\" + char)
        elif char < " " or char == "\x7f":
            out.append(f"\\u{ord(char):04x}")
        else:
            out.append(char)
    out.append('"')
    return "".join(out)


def _toml(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return _toml_text(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_toml(item) for item in value) + "]"
    return repr(value)


def _dollars(value: float) -> str:
    """Dollars to the cent where that is exact (`1.00`), and in full otherwise."""
    cents = f"{value:.2f}"
    return cents if float(cents) == value else repr(value)


def _line(setting: str, comment: str = "") -> str:
    return f"{setting:<35} # {comment}" if comment else setting


def dump_config(config: ProjectConfig) -> str:
    """The `tasks.toml` that holds `config`: the same bytes in every process."""
    model, measure, tasks = config.model, config.measure, config.tasks
    decoding, limits, output = config.decoding, config.limits, config.output
    custom = measure.preset == "custom"
    hint = "" if custom else "# "
    custom_values = (
        (measure.knob, measure.levels, measure.controls, measure.strictness)
        if custom
        else ("depth", _FIRST_LOOK_LEVELS, False, "strict")
    )
    knob, chosen, controls, strictness = custom_values

    out = [
        "# Poisson Tasks: what to run, against which model, and when to stop.",
        "# Edit it freely.  It never holds a key, only the name of the variable that does.",
        f"version = {config.version}",
        "",
        "[model]",
        _line(f"provider = {_toml(model.provider)}", " | ".join(PRESET_NAMES)),
        _line(f"name = {_toml(model.name)}", "the model id the endpoint expects"),
        f"base_url = {_toml(model.base_url)}",
        _line(
            f"api_key_env = {_toml(model.api_key_env)}",
            'the NAME of the variable that holds the key; "" for none.',
        ),
        _line(
            "", "Its name must contain API_KEY, which keeps the key from the program under test."
        ),
        _line(
            ("" if model.allow_plain_http_key else "# ")
            + f"allow_plain_http_key = {_toml(model.allow_plain_http_key)}",
            "send the key over plain http to another machine",
        ),
        "",
    ]
    if model.price is not None:
        out += [
            _line("[model.price]", "dollars per million tokens, from your provider's price page"),
            f"input = {_toml(model.price.input)}",
            f"cached_input = {_toml(model.price.cached_input)}",
            f"output = {_toml(model.price.output)}",
            _line(f"read_on = {_toml(model.price.read_on)}", "when you read them"),
            "",
        ]
    else:
        out += [
            "# No price is set, so the run is capped in tokens.  To cap it in dollars, add the",
            "# model's price, in dollars per million tokens, and spend_usd under [limits]:",
            "# [model.price]",
            "# input = 0.05",
            "# cached_input = 0.005",
            "# output = 0.40",
            '# read_on = "2026-09-25"',
            "",
        ]
    out += [
        "[measure]",
        _line(f"preset = {_toml(measure.preset)}", " | ".join(_PRESETS)),
    ]
    if not custom:
        out.append('# With preset = "custom":')
    out += [
        _line(f"{hint}knob = {_toml(knob)}", "depth | distractor (experimental)"),
        f"{hint}levels = {_toml(chosen)}",
        f"{hint}controls = {_toml(controls)}",
        _line(f"{hint}strictness = {_toml(strictness)}", " | ".join(_STRICTNESSES)),
        "",
        "[tasks]",
    ]
    if tasks.seeds is None:
        out += [
            _line(
                f"per_level = {_toml(tasks.per_level)}",
                f"1 to {_CARD_TASKS}, from the published cards' seed list; or:",
            ),
            "# seeds = [404, 55, 2121]",
        ]
    else:
        out += [
            _line(
                f"seeds = {_toml(tasks.seeds)}",
                "one task per seed, at each level; or:",
            ),
            "# per_level = 10",
        ]
    out.append(f"attempts = {_toml(tasks.attempts)}")
    if tasks.generator_version is None:
        out.append(
            _line(
                f"# generator_version = {_toml(DEFAULT_GENERATOR_VERSION)}",
                "leave unset: another version moves every task id",
            )
        )
    else:
        out.append(f"generator_version = {_toml(tasks.generator_version)}")
    out += [
        "",
        _line("[decoding]", f'sent with every model call; "{_NOT_SENT}" leaves a field out'),
        f"temperature = {_toml(decoding.temperature)}",
        f"top_p = {_toml(decoding.top_p)}",
        f"reasoning_effort = {_toml(decoding.reasoning_effort)}",
        f"max_tokens = {_toml(decoding.max_tokens)}",
        "",
        "[limits]",
    ]
    if limits.spend_usd is not None:
        out.append(
            _line(
                f"spend_usd = {_dollars(limits.spend_usd)}",
                "the run stops once it has spent this",
            )
        )
    if limits.tokens is not None:
        out.append(_line(f"tokens = {limits.tokens:_}", "the run stops once it has used this many"))
    else:
        out.append(f"# tokens = {_DEFAULT_TOKEN_CAP:_}")
    out += [
        _line(f"max_model_calls = {_toml(limits.max_model_calls)}", "per episode"),
        f"concurrency = {_toml(limits.concurrency)}",
        "",
        "[output]",
        _line(f"runs = {_toml(output.runs)}", "run folders go here, beside this file"),
        f"tasks = {_toml(output.tasks)}",
    ]
    return "\n".join(line.rstrip() for line in out) + "\n"


# ---------------------------------------------------------------------------
# init's flags
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class InitFlag:
    """One of init's flags that sets a key of the file: the flag, the key (or the table it sets
    whole), the kind of value it takes, and its default (`None` where the default depends on the
    provider, on another flag, or on the run's estimate)."""

    flag: str
    key: str
    type: str
    default: Any


INIT_FLAGS: tuple[InitFlag, ...] = (
    InitFlag("--provider", "model.provider", "choice", "openai"),
    InitFlag("--model", "model.name", "text", None),
    InitFlag("--base-url", "model.base_url", "text", None),
    InitFlag("--api-key-env", "model.api_key_env", "text", None),
    InitFlag("--allow-plain-http-key", "model.allow_plain_http_key", "switch", False),
    InitFlag("--price", "model.price", "prices", None),
    InitFlag("--price-read-on", "model.price.read_on", "date", None),
    InitFlag("--no-price", "model.price", "switch", False),
    InitFlag("--recipe", "measure.preset", "choice", "first-look"),
    InitFlag("--measure", "measure.preset", "choice", "first-look"),
    InitFlag("--knob", "measure.knob", "choice", "depth"),
    InitFlag("--levels", "measure.levels", "integers", None),
    InitFlag("--controls", "measure.controls", "switch", False),
    InitFlag("--no-controls", "measure.controls", "switch", False),
    InitFlag("--strictness", "measure.strictness", "choice", "strict"),
    InitFlag("--tasks-per-level", "tasks.per_level", "integer", 10),
    InitFlag("--seeds", "tasks.seeds", "integers", None),
    InitFlag("--attempts", "tasks.attempts", "integer", 1),
    InitFlag("--generator-version", "tasks.generator_version", "text", None),
    InitFlag("--temperature", "decoding.temperature", "number", _CARD_DECODING["temperature"]),
    InitFlag("--top-p", "decoding.top_p", "number", _CARD_DECODING["top_p"]),
    InitFlag(
        "--reasoning-effort",
        "decoding.reasoning_effort",
        "text",
        _CARD_DECODING["reasoning_effort"],
    ),
    InitFlag("--max-tokens", "decoding.max_tokens", "integer", _CARD_DECODING["max_tokens"]),
    InitFlag("--spend-cap", "limits.spend_usd", "number", None),
    InitFlag("--token-cap", "limits.tokens", "integer", None),
    InitFlag("--max-model-calls", "limits.max_model_calls", "integer", 32),
    InitFlag("--concurrency", "limits.concurrency", "integer", 8),
    InitFlag("--runs-dir", "output.runs", "text", "runs"),
    InitFlag("--tasks-dir", "output.tasks", "text", "tasks"),
)

_FLAGS = {flag.flag: flag for flag in INIT_FLAGS}
# Init's flags that set no key of the file; they are init's own to act on.
_FLAGS_OF_INIT_ALONE = ("--yes", "--fetch", "--no-fetch", "--check-key", "--no-check-key")
_SWITCHED_OFF = ("--no-controls",)
# A flag kept under an older name for one release: the older name sets what the newer one does,
# and given both, the last one given counts, as with any flag given twice.
_ALIASES = {"--measure": "--recipe"}


def _name_as_flag(key: str) -> str:
    """The flag that sets `key`, or the table around it."""
    while key:
        for flag in INIT_FLAGS:
            if flag.key == key:
                return flag.flag
        key = key.rpartition(".")[0]
    return "the cap"


def _flag_value(flag: InitFlag, text: str) -> Any:
    """A flag's text as the value the file would hold.  Text that is not of the flag's kind is
    left as text, and the reader refuses it under the flag's key."""
    if flag.type == "integer" and re.fullmatch(r"[+-]?[0-9]+", text):
        return int(text)
    if flag.type == "number":
        try:
            return float(text)
        except ValueError:
            return text
    if flag.type == "integers":
        parts = [part.strip() for part in text.split(",")] if text.strip() else []
        if all(re.fullmatch(r"[+-]?[0-9]+", part) for part in parts):
            return [int(part) for part in parts]
    return text


def _given_flags(argv: Sequence[str]) -> dict[str, Any]:
    """Each flag in `argv` with its value; a flag given twice keeps its last value."""
    given: dict[str, Any] = {}
    words = list(argv)
    index = 0
    while index < len(words):
        word = words[index]
        index += 1
        name, equals, attached = word.partition("=")
        if name in _FLAGS_OF_INIT_ALONE and not equals:
            continue
        flag = _FLAGS.get(_ALIASES.get(name, name))
        if flag is None:
            near = _nearest(name, tuple(_FLAGS)) if name.startswith("--") else None
            hint = "" if near is None else f"; did you mean {near}?"
            raise ConfigError(f"{word} is not one of init's settings{hint}", suggestion=near)
        if flag.type == "switch":
            if equals:
                raise ConfigError(f"{name} takes no value", key=flag.key)
            if name in ("--controls", "--no-controls"):
                given.pop("--controls", None)
                given.pop("--no-controls", None)
            given[name] = name not in _SWITCHED_OFF
            continue
        if equals:
            text = attached
        elif index < len(words):
            text = words[index]
            index += 1
        else:
            raise ConfigError(f"{name} needs a value", key=flag.key)
        given[flag.flag] = text if flag.type == "prices" else _flag_value(flag, text)
    return given


def default_spend_cap(expected_dollars: float | None) -> float:
    """Init's default spend cap, in dollars: the larger of $1.00 and twice the run's estimate,
    rounded up to a whole dollar.  With no estimate it is $1.00."""
    if expected_dollars is None:
        return _DEFAULT_SPEND_FLOOR
    if not _number(expected_dollars) or expected_dollars < 0:
        raise ValueError(f"an estimate is dollars, zero or more; got {expected_dollars!r}")
    return max(_DEFAULT_SPEND_FLOOR, float(math.ceil(2 * expected_dollars)))


def _price_from_flags(
    given: Mapping[str, Any], preset: Preset, model: str, fail: Callable[..., ConfigError]
) -> dict[str, Any] | None:
    figures, read_on = given.get("--price"), given.get("--price-read-on")
    if given.get("--no-price"):
        if figures is not None or read_on is not None:
            raise fail("model.price", "--no-price is given beside a price; give one or the other")
        return None
    if figures is None:
        prefilled = preset.name == "openai" and model == _PUBLISHED_MODEL
        if not prefilled:
            if read_on is not None:
                raise fail("model.price", "--price-read-on is given with no --price")
            return None
        price = dict(_PUBLISHED_PRICE)
    else:
        parts = [part.strip() for part in figures.split(",")]
        try:
            numbers = [float(part) for part in parts]
        except ValueError:
            numbers = []
        if len(numbers) != 3:
            raise fail(
                "model.price",
                f"--price is {_show(figures)}; it takes three numbers, the dollars per million "
                "tokens of input, cached input and output, as 0.05,0.005,0.40",
            )
        if read_on is None:
            raise fail(
                "model.price.read_on",
                "--price needs --price-read-on, the date the prices were read, as 2026-09-25",
            )
        price = dict(zip(("input", "cached_input", "output"), numbers, strict=True))
    if read_on is not None:
        price["read_on"] = read_on
    return price


def config_from_init_args(
    argv: Sequence[str], *, expected_dollars: float | None = None
) -> ProjectConfig:
    """The config `init` writes for these flags, with every other setting at its default.

    `expected_dollars` is the run's estimate, which `init` computes and this module cannot (it
    needs the tokenizer); the default spend cap is made from it.  A flag refused is refused under
    the key it sets, exactly as the file would be.
    """
    given = _given_flags(argv)
    reader = _Reader({}, name=_name_as_flag)
    fail = reader.refusal

    provider = reader.choice(
        "model.provider", given.get("--provider", "openai"), PRESET_NAMES, "a provider"
    )
    preset = PRESETS[provider]
    model: dict[str, Any] = {"provider": provider}

    name = given.get("--model", preset.default_model)
    if name is None:
        raise fail(
            "model.name", f"--model is not given, and the {provider} preset has no default model"
        )
    endpoint = preset.endpoint
    if provider == "openai":
        endpoint = os.environ.get("OPENAI_BASE_URL") or endpoint
    base_url = given.get("--base-url", endpoint)
    if base_url is None:
        raise fail(
            "model.base_url",
            f"--base-url is not given, and the {provider} preset has no default endpoint",
        )
    api_key_env = given.get("--api-key-env", preset.api_key_env)
    if api_key_env is None:
        raise fail(
            "model.api_key_env",
            f"--api-key-env is not given, and the {provider} preset has no default: name the "
            'variable that holds the key, or pass --api-key-env "" for no key',
        )
    model.update(name=name, base_url=base_url, api_key_env=api_key_env)
    if given.get("--allow-plain-http-key"):
        model["allow_plain_http_key"] = True
    price = _price_from_flags(given, preset, name, fail)
    if price is not None:
        model["price"] = price

    measure: dict[str, Any] = {"preset": given.get("--recipe", "first-look")}
    custom = {
        "knob": given.get("--knob", _MISSING),
        "levels": given.get("--levels", _MISSING),
        "controls": given.get("--controls", given.get("--no-controls", _MISSING)),
        "strictness": given.get("--strictness", _MISSING),
    }
    if measure["preset"] == "custom":
        if custom["knob"] is _MISSING:
            custom["knob"] = "depth"
        if custom["levels"] is _MISSING and custom["knob"] in _KNOBS:
            custom["levels"] = list(levels(custom["knob"]))
        if custom["controls"] is _MISSING:
            custom["controls"] = False
        if custom["strictness"] is _MISSING:
            custom["strictness"] = "strict"
    measure.update({field: value for field, value in custom.items() if value is not _MISSING})

    # A recipe sets the tasks per level and the attempts; the flags still override them.
    tasks: dict[str, Any] = {}
    recipe = RECIPES.get(measure["preset"]) if isinstance(measure["preset"], str) else None
    per_level = _FLAGS["--tasks-per-level"].default if recipe is None else recipe.tasks_per_level
    attempts = _FLAGS["--attempts"].default if recipe is None else recipe.attempts
    if "--seeds" in given:
        tasks["seeds"] = given["--seeds"]
    if "--tasks-per-level" in given:
        tasks["per_level"] = given["--tasks-per-level"]
    elif "seeds" not in tasks:
        tasks["per_level"] = per_level
    tasks["attempts"] = given.get("--attempts", attempts)
    if "--generator-version" in given:
        tasks["generator_version"] = given["--generator-version"]

    limits: dict[str, Any] = {}
    if "--spend-cap" in given:
        limits["spend_usd"] = given["--spend-cap"]
    elif price is not None:
        limits["spend_usd"] = default_spend_cap(expected_dollars)
    if "--token-cap" in given:
        limits["tokens"] = given["--token-cap"]
    elif price is None:
        limits["tokens"] = _DEFAULT_TOKEN_CAP

    def of(table: str) -> dict[str, Any]:
        prefix = table + "."
        return {
            flag.key.removeprefix(prefix): given.get(flag.flag, flag.default)
            for flag in INIT_FLAGS
            if flag.key.startswith(prefix) and (flag.flag in given or flag.default is not None)
        }

    document = {
        "version": SCHEMA_VERSION,
        "model": model,
        "measure": measure,
        "tasks": tasks,
        "decoding": of("decoding"),
        "limits": {**limits, **{k: v for k, v in of("limits").items() if k not in limits}},
        "output": of("output"),
    }
    return _Reader(document, name=_name_as_flag).config()


def equivalent_init_command(config: ProjectConfig, *, prog: str) -> list[str]:
    """The argv of the `init --yes ...` command that writes `config`'s file, byte for byte.

    Every setting is spelled out, the endpoint included, so the command writes the same file
    whatever `OPENAI_BASE_URL` says where it runs, and whatever the run's estimate is there.
    """
    model, measure, tasks = config.model, config.measure, config.tasks
    decoding, limits, output = config.decoding, config.limits, config.output

    def joined(values: Sequence[Any]) -> str:
        return ",".join(str(value) for value in values)

    command = [*shlex.split(prog), "init", "--yes"]
    command += ["--provider", model.provider, "--model", model.name]
    command += ["--base-url", model.base_url, "--api-key-env", model.api_key_env]
    if model.allow_plain_http_key:
        command.append("--allow-plain-http-key")
    if model.price is None:
        command.append("--no-price")
    else:
        price = model.price
        command += [
            "--price",
            joined([repr(price.input), repr(price.cached_input), repr(price.output)]),
        ]
        command += ["--price-read-on", price.read_on]
        if limits.spend_usd is None:
            raise ConfigError(
                "no init command writes this file: it gives the model a price and no "
                "spend_usd under [limits], and init always writes a dollar cap beside a price",
                key="limits.spend_usd",
            )
    command += ["--recipe", measure.preset]
    if measure.preset == "custom":
        command += ["--knob", str(measure.knob), "--levels", joined(measure.levels or ())]
        command.append("--controls" if measure.controls else "--no-controls")
        command += ["--strictness", str(measure.strictness)]
    if tasks.seeds is not None:
        command += ["--seeds", joined(tasks.seeds)]
    else:
        command += ["--tasks-per-level", str(tasks.per_level)]
    command += ["--attempts", str(tasks.attempts)]
    if tasks.generator_version is not None:
        command += ["--generator-version", tasks.generator_version]
    command += ["--temperature", repr(decoding.temperature)]
    command += [
        "--top-p",
        decoding.top_p if isinstance(decoding.top_p, str) else repr(decoding.top_p),
    ]
    command += ["--reasoning-effort", decoding.reasoning_effort]
    command += ["--max-tokens", str(decoding.max_tokens)]
    if limits.spend_usd is not None:
        command += ["--spend-cap", repr(limits.spend_usd)]
    if limits.tokens is not None:
        command += ["--token-cap", str(limits.tokens)]
    command += ["--max-model-calls", str(limits.max_model_calls)]
    command += ["--concurrency", str(limits.concurrency)]
    command += ["--runs-dir", output.runs, "--tasks-dir", output.tasks]
    return command


# ---------------------------------------------------------------------------
# the plan
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Plan:
    """What a config runs: the arms in the published cards' own order (a recipe's in its own),
    the seeds in the order they run, the attempts at each task, the model, the decoding and the
    turn cap.  It carries no cap on spending, no concurrency and no folder: none of them changes
    what runs."""

    preset: str
    arms: tuple[ArmSpec, ...]
    seeds: tuple[int, ...]
    attempts: int
    model: ModelConfig
    decoding: Mapping[str, Any]
    max_model_calls: int


def resolve_plan(config: ProjectConfig) -> Plan:
    """The plan `config` asks for.

    The published design is `calibration`'s, which loads the tokenizer file when it is imported;
    so the file is looked for first, and `TokenizerMissing` is raised before anything is imported.
    """
    if not _ENCODING_PATH.exists():
        raise TokenizerMissing(
            "the tokenizer file is not in this environment, and tasks cannot be made without "
            "it: fetch it once with `python -m poisson_tasks.fetch_encoding`"
        )
    calibration = importlib.import_module("poisson_tasks.calibration")
    measure, tasks = config.measure, config.tasks
    version = tasks.generator_version or DEFAULT_GENERATOR_VERSION
    card_arms: tuple[ArmSpec, ...] = calibration.arm_specs()

    if measure.preset == "card":
        arms = card_arms
    elif measure.preset in RECIPES:
        arms = tuple(
            arm_from_id(arm, generator_version=version) for arm in RECIPES[measure.preset].arms
        )
    else:
        knob = measure.knob or "depth"
        chosen = set(levels(knob) if measure.levels is None else measure.levels)
        arms = tuple(
            arm_from_id(
                arm_id(spec), strictness=measure.strictness or "strict", generator_version=version
            )
            for spec in card_arms
            if spec.knob == knob
            and spec.level in chosen
            and (spec.control is None or (bool(measure.controls) and spec.control in chosen))
        )

    if tasks.seeds is not None:
        seeds = tasks.seeds
    else:
        published: tuple[int, ...] = calibration.seed_list()
        seeds = published[: tasks.per_level]
    return Plan(
        preset=measure.preset,
        arms=arms,
        seeds=seeds,
        attempts=tasks.attempts,
        model=config.model,
        decoding=types.MappingProxyType(dataclasses.asdict(config.decoding)),
        max_model_calls=config.limits.max_model_calls,
    )


def plan_hash(plan: Plan) -> str:
    """The plan's identity, as lowercase hex: the same in every process.

    It moves with what runs (the arms, the seeds and their order, the attempts, the model's name,
    the endpoint, the decoding and the turn cap) and with nothing else: not the caps, the
    concurrency, the prices or the folders, and not which preset or key variable was named.
    """
    identity = {
        "plan": 1,
        "arms": [dataclasses.asdict(spec) for spec in plan.arms],
        "seeds": list(plan.seeds),
        "attempts": plan.attempts,
        "model": plan.model.name,
        "base_url": plan.model.base_url,
        "decoding": dict(plan.decoding),
        "max_model_calls": plan.max_model_calls,
    }
    canonical = json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()
