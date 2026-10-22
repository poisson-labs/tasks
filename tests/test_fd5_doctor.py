"""`doctor`, frozen as tests.

The invariant is `doctor`'s (decided 2026-10-04, which brings `fetch_tokenizer` here).  What needs a
copy of the package (the tokenizer missing, `--fix`, a site-packages the user cannot write) is in
`tests/test_fd5_fresh.py`.
- exit 0 when the environment is ready, verdict `ok`; exit 4 when it is not, verdict `not ready`,
  with the failing line naming what failed;
- `--offline` opens no socket; without it, the key is checked with one free request and its line
  is the library's;
- `--show-command` prints the `init --yes …` command that writes the settings file
  (`config.equivalent_init_command`), and refuses, with the library's text, a file no
  init command writes;
- the `package` line names the folder the package was imported from, and a `note:` line warns
  when that folder is outside the running environment (rule L4: a warning
  is `note:`);
- `fetch_tokenizer` returns the tokenizer file's path, and with the file in place fetches nothing.

Shapes decided here
-------------------

**1. A settings file `--config` names that is not there is refused**, exit 1.  What `doctor`
says with no settings file at all is `tests/test_fd5_pending_doctor_without_config.py`'s, pending
a decision.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from tests.fd2_fakes import SENTINEL
from tests.fd5_support import (
    World,
    config,
    error_lines,
    invoke,
    printed_command,
    prog,
    providers,
    strip_prog,
    world,
)
from tests.fixtures.model_server import FixtureModel

__all__ = ["prog", "world"]


def write(path: Path, flags: list[str], edit: tuple[str, str] | None = None) -> Any:
    text = config().dump_config(config().config_from_init_args(flags))
    if edit is not None:
        assert edit[0] in text
        text = text.replace(*edit)
    path.write_text(text, encoding="utf-8")
    return config().loads_config(text) if edit is None else None


def test_fd5_17_ready_is_exit_0_and_ok(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(world.work / "tasks.toml", ["--api-key-env", ""])
    ran = invoke(["doctor", "--offline"], prog=prog, monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    assert ran.word == "ok", ran


def test_fd5_17_a_key_not_set_is_not_ready_and_its_line_names_the_variable(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(world.work / "tasks.toml", ["--api-key-env", "MY_PROVIDER_API_KEY"])
    ran = invoke(["doctor", "--offline"], prog=prog, monkeypatch=monkeypatch)
    assert ran.code == 4, ran
    assert ran.word == "not ready", ran
    assert any("MY_PROVIDER_API_KEY" in line for line in ran.lines[1:]), ran
    monkeypatch.setenv("MY_PROVIDER_API_KEY", SENTINEL)
    ready = invoke(["doctor", "--offline"], prog=prog, monkeypatch=monkeypatch)
    assert ready.code == 0, ready


def test_fd5_17_a_refused_settings_file_is_not_ready_and_says_the_readers_text(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(world.work / "tasks.toml", ["--tasks-per-level", "2"],
          edit=("per_level = 2", "per_level = 61"))
    with pytest.raises(config().ConfigError) as refused:
        config().load_config(Path("tasks.toml"))
    ran = invoke(["doctor", "--offline"], prog=prog, monkeypatch=monkeypatch)
    assert ran.code == 4, ran
    assert ran.word == "not ready", ran
    assert str(refused.value) in ran.out + ran.err, ran


def test_fd5_17_offline_opens_no_socket_and_the_check_is_one_free_request(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    with FixtureModel() as fixture:
        made = write(world.work / "tasks.toml", ["--provider", "openai-compatible", "--model",
                                                 "fixture-reference", "--base-url",
                                                 fixture.base_url, "--api-key-env",
                                                 "FIXTURE_API_KEY", "--no-price"])
        monkeypatch.setenv("FIXTURE_API_KEY", SENTINEL)
        offline = invoke(["doctor", "--offline"], prog=prog, monkeypatch=monkeypatch)
        assert offline.code == 0, offline
        assert offline.events == () and fixture.requests == []
        checked = invoke(["doctor"], prog=prog, monkeypatch=monkeypatch)
        assert checked.code == 0, checked
        assert [seen.method for seen in fixture.requests] == ["GET"]
        found = providers().check_key(made.model)
    assert found.status == providers().ACCEPTED
    assert found.detail in checked.out, checked


def test_fd5_17_a_refused_key_is_not_ready_with_the_librarys_line(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    with FixtureModel() as fixture:
        made = write(world.work / "tasks.toml", ["--provider", "openai", "--model",
                                                 "fixture-401", "--base-url",
                                                 fixture.base_url, "--no-price"])
        monkeypatch.setenv("OPENAI_API_KEY", SENTINEL)
        ran = invoke(["doctor"], prog=prog, monkeypatch=monkeypatch)
        found = providers().check_key(made.model)
    assert ran.code == 4, ran
    assert ran.word == "not ready"
    assert found.status == providers().REFUSED
    assert found.detail in ran.out, ran


def test_fd5_17_show_command_prints_the_init_command_that_writes_the_file(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A file edited by hand still has its command: running it writes the file the reader reads
    from the edited one."""
    write(world.work / "tasks.toml", ["--tasks-per-level", "4"],
          edit=("concurrency = 8", "concurrency = 3        # edited by hand"))
    made = config().load_config(world.work / "tasks.toml")
    assert made.limits.concurrency == 3
    ran = invoke(["doctor", "--show-command"], prog=prog, monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    command = printed_command(ran.out, prog, "init")
    assert command is not None, ran
    assert command == config().equivalent_init_command(made, prog=prog), ran
    (world.work / "again").mkdir()
    monkeypatch.chdir(world.work / "again")
    again = invoke(strip_prog(command, prog) + ["--no-fetch", "--no-check-key"], prog=prog,
                   monkeypatch=monkeypatch)
    assert again.code == 0, again
    assert (world.work / "again" / "tasks.toml").read_text(encoding="utf-8") == \
        config().dump_config(made)


def test_fd5_17_show_command_refuses_a_file_no_init_command_writes(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(world.work / "tasks.toml", ["--tasks-per-level", "2"],
          edit=("spend_usd = 1.00", "tokens = 300_000"))
    made = config().load_config(world.work / "tasks.toml")
    with pytest.raises(config().ConfigError) as refused:
        config().equivalent_init_command(made, prog=prog)
    ran = invoke(["doctor", "--show-command"], prog=prog, monkeypatch=monkeypatch)
    assert ran.code == 1, ran
    assert error_lines(ran) == [f"error: {refused.value}"], ran


@pytest.mark.parametrize("outside", [True, False], ids=["outside", "inside"])
def test_fd5_17_the_package_line_names_its_folder_and_a_note_warns_when_it_is_outside(
    outside: bool, prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(world.work / "tasks.toml", ["--api-key-env", ""])
    package = Path(providers().environment_report().package)
    monkeypatch.setattr(sys, "prefix", str(world.tmp if outside else package.parent.parent))
    report = providers().environment_report()
    assert report.package_outside_environment is outside
    ran = invoke(["doctor", "--offline"], prog=prog, monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    assert any(report.package in line for line in ran.lines), ran
    notes = [line for line in ran.err_lines
             if line.startswith("note: ") and report.package in line]
    assert len(notes) == (1 if outside else 0), ran


def test_fd5_17_fetch_tokenizer_returns_the_files_path_and_fetches_nothing_when_it_is_there(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.fd2_fakes import network_guard
    from tests.fd5_support import tokenizer_file

    with network_guard(monkeypatch) as events:
        path = providers().fetch_tokenizer()
    assert Path(path) == tokenizer_file()
    assert events == []
