"""`export`, frozen as tests.

The invariant is `export`'s (decided 2026-10-04):
- the config file `export --to verifiers` writes for an arm, loaded through verifiers' own config
  reader (the one `eval @ FILE` uses), equals `runs.verifiers_config(plan, arm)` loaded the same
  way, the run's identity aside (`output_dir`, `run.name` and `run.dir`), and carries the arm as its
  six-field mapping;
- the command it prints for each file runs verifiers' `eval` by an absolute path to a file that
  exists in this environment, then `@` and the file;
- a config that would send a key over plain http to a host that is not loopback is refused with
  the `ConfigError` `providers.check_key` raises for it, before anything is written.

Shapes decided here
-------------------

**1. A file per arm**, `eval-<the arm's folder-safe id>` with one suffix for every file, in
`--out DIR`, else `export/` beside the settings file.

**The file's format is left open here, and that is a defect of the design.**  It says TOML.  TOML
has no null, an arm with no control arm has `control = None`, and the export's arm validator refuses
a mapping with `control` missing (the frozen `test_fd1_*` tests pin that refusal, decided
2026-10-03).  So no TOML file can carry a first look's arm as its six-field mapping, and `eval @`
refuses one that leaves `control` out (measured, `evidence/front-door-fd5-a/`).  These tests take
`.json`, which `eval @` reads the same way and which carries `null`, or `.toml` for a plan whose
every arm it can carry; `tests/test_fd5_pending_export_json.py` pins JSON, pending a decision.

**2. The printed command** is `<eval's absolute path> @ <the file>`, one line per file.
"""

from __future__ import annotations

import dataclasses
import json
import sys
import sysconfig
import tomllib
from pathlib import Path
from typing import Any

import pytest

from tests.fd3_support import KEY, KEY_VAR, arm_dir
from tests.fd5_support import (
    World,
    config,
    error_lines,
    invoke,
    providers,
    prog,
    runs,
    world,
)

__all__ = ["prog", "world"]


def through_verifiers(path: Path) -> dict[str, Any]:
    """The config file read the way `eval @ FILE` reads it (the `test_fd3_*` tests' own
    reader)."""
    from pydantic_config import cli  # type: ignore[import-untyped]
    from verifiers.v1.cli.resolve import narrow_config
    from verifiers.v1.configs.cli.eval import EvalConfig

    argv = ["@", str(path)]
    saved = sys.argv
    sys.argv = ["eval", *argv]
    try:
        loaded = cli(narrow_config(EvalConfig, argv))
    finally:
        sys.argv = saved
    value = json.loads(loaded.model_dump_json())
    assert isinstance(value, dict)
    value.pop("output_dir", None)
    value.pop("run", None)
    return value


def suffix_of(folder: Path) -> str:
    """The one suffix every file in `folder` has: `.json` or `.toml`."""
    suffixes = {path.suffix for path in folder.iterdir()}
    assert len(suffixes) == 1 and suffixes <= {".json", ".toml"}, suffixes
    return suffixes.pop()


def read(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    value = json.loads(text) if path.suffix == ".json" else tomllib.loads(text)
    assert isinstance(value, dict)
    return value


def as_config_file(mapping: dict[str, Any], path: Path) -> Path:
    """A mapping written as a JSON config file, which `eval @` reads too."""
    path.write_text(json.dumps(mapping), encoding="utf-8")
    return path


PLANS = {
    "first-look": ["--tasks-per-level", "3"],
    "custom-leaky-not-sent": ["--recipe", "custom", "--knob", "depth", "--levels", "1,2,5",
                              "--controls", "--strictness", "leaky", "--tasks-per-level", "2",
                              "--attempts", "2", "--top-p", "not sent", "--max-model-calls",
                              "20", "--generator-version", "0"],
    "a-users-server": ["--provider", "vllm", "--model", "served", "--api-key-env",
                       "VLLM_API_KEY", "--seeds", "404,55"],
}


@pytest.mark.parametrize("name", list(PLANS))
def test_fd5_16_each_file_is_the_runs_config_through_verifiers_reader(
    name: str, prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    made = config().config_from_init_args(PLANS[name])
    (world.work / "tasks.toml").write_text(config().dump_config(made), encoding="utf-8")
    plan = config().resolve_plan(made)
    ran = invoke(["export", "--to", "verifiers"], prog=prog, monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    folder = world.work / "export"
    suffix = suffix_of(folder)
    assert sorted(p.name for p in folder.iterdir()) == sorted(
        f"eval-{arm_dir(spec)}{suffix}" for spec in plan.arms)
    for spec in plan.arms:
        path = folder / f"eval-{arm_dir(spec)}{suffix}"
        written = read(path)
        assert written["env"]["taskset"]["arm"] == dataclasses.asdict(spec)
        expected = as_config_file(runs().verifiers_config(plan, spec),
                                world.tmp / f"{arm_dir(spec)}.json")
        assert through_verifiers(path) == through_verifiers(expected), spec


def test_fd5_16_the_printed_command_runs_eval_by_its_absolute_path(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    made = config().config_from_init_args(["--tasks-per-level", "1"])
    (world.work / "tasks.toml").write_text(config().dump_config(made), encoding="utf-8")
    plan = config().resolve_plan(made)
    ran = invoke(["export", "--to", "verifiers", "--out", "elsewhere"], prog=prog,
                 monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    scripts = Path(sysconfig.get_path("scripts")).resolve()
    suffix = suffix_of(world.work / "elsewhere")
    for spec in plan.arms:
        path = Path("elsewhere") / f"eval-{arm_dir(spec)}{suffix}"
        assert (world.work / path).is_file()
        found = []
        for line in ran.lines:
            words = line.split()
            if "@" in words and words.index("@") >= 1:
                at = words.index("@")
                program, target = Path(words[at - 1]), words[at + 1] if at + 1 < len(words) \
                    else ""
                if Path(target) in (path, world.work / path):
                    found.append(program)
        assert found, f"no command for {path}:\n{ran.out}"
        program = found[0]
        assert program.is_absolute() and program.name == "eval" and program.is_file(), program
        assert program.resolve().parent == scripts or program.parent == Path(
            sysconfig.get_path("scripts")), program


def test_fd5_16_a_key_over_plain_http_to_another_machine_is_refused_before_anything_is_written(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(KEY_VAR, KEY)
    flags = ["--provider", "openai-compatible", "--model", "m", "--base-url",
             "http://tasks-fake.test:9/v1", "--api-key-env", KEY_VAR, "--no-price",
             "--tasks-per-level", "1"]
    made = config().config_from_init_args(flags)
    (world.work / "tasks.toml").write_text(config().dump_config(made), encoding="utf-8")
    with pytest.raises(config().ConfigError) as refused:
        providers().check_key(made.model)
    ran = invoke(["export", "--to", "verifiers"], prog=prog, monkeypatch=monkeypatch)
    assert ran.code == 1, ran
    assert error_lines(ran) == [f"error: {refused.value}"], ran
    assert sorted(p.name for p in world.work.iterdir()) == ["tasks.toml"]
    assert ran.connections == []
    allowed = config().config_from_init_args([*flags, "--allow-plain-http-key"])
    (world.work / "tasks.toml").write_text(config().dump_config(allowed), encoding="utf-8")
    taken = invoke(["export", "--to", "verifiers"], prog=prog, monkeypatch=monkeypatch)
    assert taken.code == 0, taken
