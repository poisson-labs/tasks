"""Pending a decision: a `next:` command carries the `--config` the user gave.

Rule L13: "A verb that has an obvious next step ends with `next: <exact command>`."
The design's examples are all for `tasks.toml` in the current folder.  A user who wrote their
settings elsewhere (`init --config experiments/a.toml`) and is told `next: poisson-tasks run` gets a
command that does not find their file.

**Recommended:** when `--config` was given, every `next:` command that reads the settings file
carries it, as given.

**If it is declined**, this file's commit is dropped: the `next:` lines are the design's examples
as written.
"""

from __future__ import annotations

import shlex

import pytest

from tests.fd5_support import World, config, invoke, next_commands, prog, world

__all__ = ["prog", "world"]


@pytest.mark.parametrize("argv", [
    ["init", "--yes", "--no-fetch", "--no-check-key", "--config", "exp/a.toml"],
    ["generate", "--config", "exp/a.toml"],
])
def test_fd5_l13_a_next_command_carries_the_config_given(
    argv: list[str], prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    (world.work / "exp").mkdir()
    if argv[0] != "init":
        made = config().config_from_init_args(["--tasks-per-level", "1"])
        (world.work / "exp" / "a.toml").write_text(config().dump_config(made), encoding="utf-8")
    ran = invoke(argv, prog=prog, monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    commands = next_commands(ran.out)
    assert commands, ran
    for command in commands:
        words = shlex.split(command)
        assert "--config" in words and words[words.index("--config") + 1] == "exp/a.toml", command
