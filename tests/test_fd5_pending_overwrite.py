"""Pending a decision: `generate`, `export` and `card` refuse to overwrite without `--force`.

Rule L12: "A verb that writes files says what it wrote, and refuses to overwrite
without `--force`."  The design gives `init` its `--force`, and lists no `--force`
for `generate`, `card` and `export`, which also write files.  The design does not agree with itself.

**Recommended, so that L12 holds:** each of the three, run again over its own files, refuses (exit
1, one line naming a file, nothing changed), and with `--force` writes them again.  A `card` is
derived from its run folder and cheap to make again, so `--force` costs a user little; a task file
or a config someone edited is not lost by accident.

**If it is declined**, this file's commit is dropped: the three overwrite their own files without
asking.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest

from tests.fd3_support import needs_uv
from tests.fd4_support import fd4_runs
from tests.fd5_support import World, config, error_lines, invoke, prog, tree, world

__all__ = ["prog", "world", "fd4_runs"]


def write(world: World) -> None:
    made = config().config_from_init_args(["--tasks-per-level", "1"])
    (world.work / "tasks.toml").write_text(config().dump_config(made), encoding="utf-8")


def again(argv: list[str], folder: Path, prog: str, monkeypatch: pytest.MonkeyPatch) -> None:
    first = invoke(argv, prog=prog, monkeypatch=monkeypatch)
    assert first.code == 0, first
    made = tree(folder)
    (sorted(p for p in folder.rglob("*") if p.is_file())[0]).write_text("edited\n")
    edited = tree(folder)
    refused = invoke(argv, prog=prog, monkeypatch=monkeypatch)
    assert refused.code == 1, refused
    assert len(error_lines(refused)) == 1, refused
    assert tree(folder) == edited
    forced = invoke([*argv, "--force"], prog=prog, monkeypatch=monkeypatch)
    assert forced.code == 0, forced
    assert tree(folder) == made


def test_fd5_l12_generate_refuses_to_overwrite_without_force(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(world)
    again(["generate"], world.work / "tasks", prog, monkeypatch)


def test_fd5_l12_export_refuses_to_overwrite_without_force(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(world)
    again(["export", "--to", "verifiers"], world.work / "export", prog, monkeypatch)


@needs_uv
def test_fd5_l12_card_refuses_to_overwrite_without_force(
    fd4_runs: Any, prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = world.work / "run"
    shutil.copytree(fd4_runs["first_look"].folder, folder)
    again(["card", str(folder)], folder / "card", prog, monkeypatch)
