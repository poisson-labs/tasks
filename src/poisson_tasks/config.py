"""The plan: `tasks.toml`, init's flags, the provider presets and the resolved plan.

A names-only skeleton.  Every name the frozen tests reach is declared with its signature, and
nothing is built: the tests in `tests/test_fd1_config.py` say what each one does.  Importing this
module imports no `verifiers` and none of `tasks`, `calibration` and `export`, which load the
tokenizer file at import.
"""

from __future__ import annotations

import dataclasses
import os
from collections.abc import Mapping, Sequence
from typing import Any

from poisson_tasks.knobs import ArmSpec

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


@dataclasses.dataclass(frozen=True)
class Preset:
    name: str
    label: str
    endpoint: str | None
    api_key_env: str | None
    default_model: str | None
    key_check_path: str
    asks_endpoint: bool
    asks_price: bool


PRESETS: dict[str, Preset] = {}
PRESET_NAMES: tuple[str, ...] = ()


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


@dataclasses.dataclass(frozen=True)
class InitFlag:
    flag: str
    key: str
    type: str
    default: Any


INIT_FLAGS: tuple[InitFlag, ...] = ()


@dataclasses.dataclass(frozen=True)
class Plan:
    preset: str
    arms: tuple[ArmSpec, ...]
    seeds: tuple[int, ...]
    attempts: int
    model: ModelConfig
    decoding: Mapping[str, Any]
    max_model_calls: int


def loads_config(text: str, *, source: str = "tasks.toml") -> ProjectConfig:
    raise NotImplementedError


def load_config(path: str | os.PathLike[str]) -> ProjectConfig:
    raise NotImplementedError


def dump_config(config: ProjectConfig) -> str:
    raise NotImplementedError


def default_spend_cap(expected_dollars: float | None) -> float:
    raise NotImplementedError


def config_from_init_args(
    argv: Sequence[str], *, expected_dollars: float | None = None
) -> ProjectConfig:
    raise NotImplementedError


def equivalent_init_command(config: ProjectConfig, *, prog: str) -> list[str]:
    raise NotImplementedError


def resolve_plan(config: ProjectConfig) -> Plan:
    raise NotImplementedError


def plan_hash(plan: Plan) -> str:
    raise NotImplementedError
