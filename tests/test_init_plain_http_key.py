"""`init` on a key that would go over plain http to another machine: a refusal, not a crash.

A setup that names a key variable and a plain-`http` endpoint that is not loopback is refused by
the library before any connection (`providers.refuse_plain_http_key`).  `init` reached that
refusal through the key check, and let it escape as an unexpected failure, exit 3, whenever the
check ran: with the key set and checked, and with the key unset, which is checked even under
`--no-check-key` to say so.  It is now a refusal like `init`'s others: exit 1, one `error:` line
first on stderr, and a `next:` line that is the command as typed plus `--allow-plain-http-key`
(rule N3); nothing is written and no socket is opened.

Every refusal is pinned against a control that differs in the one thing under test (a loopback
endpoint, an `https` one, or the option the `next:` line adds), never by the words of its
message.  With the key set and checked on an `https` endpoint the command would send the check,
so that case has no control here: `tests/test_fd5_init.py` sends it to the fixture model.
"""

from __future__ import annotations

import dataclasses
import shlex
import sys
from typing import Any

import pytest

from tests.fd2_fakes import FAKE_DOMAIN, SENTINEL
from tests.fd5_support import (
    Answers,
    Ran,
    World,
    config,
    conformance,
    error_lines,
    invoke,
    next_commands,
    prog,
    tree,
    world,
)

__all__ = ["prog", "world"]

PLAIN = f"http://{FAKE_DOMAIN}/v1"
LOOPBACK = "http://127.0.0.1:9/v1"
HTTPS = f"https://{FAKE_DOMAIN}/v1"
KEY_VAR = "OPENAI_API_KEY"


def refused_as_typed(ran: Ran, typed: list[str], world: World) -> list[str]:
    """`ran` is the refusal: exit 1, one `error:` line and the first on stderr, nothing written,
    no socket; its one `next:` command, which is returned, is `typed` plus the option."""
    assert ran.code == 1, ran
    lines = error_lines(ran)
    assert len(lines) == 1, ran
    assert ran.err_lines[0] == lines[0], "the refusal is the first thing said"
    assert ran.out == "", ran
    assert tree(world.work) == {}, ran
    assert ran.events == (), ran
    commands = next_commands(ran.err)
    assert len(commands) == 1, ran
    command = shlex.split(commands[0])
    assert command == [*shlex.split(ran.prog), *typed, "--allow-plain-http-key"], ran
    return command


def written_model(world: World) -> Any:
    return config().load_config(world.work / "tasks.toml").model


@pytest.mark.parametrize("check", [["--no-check-key"], []], ids=["no-check-key", "default"])
def test_an_unset_key_on_plain_http_is_refused_and_the_next_command_writes_the_file(
    check: list[str], prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    typed = ["init", "--yes", "--no-fetch", *check, "--base-url", PLAIN]
    ran = invoke(typed, prog=prog, monkeypatch=monkeypatch)
    command = refused_as_typed(ran, typed, world)
    again = invoke(command[len(shlex.split(prog)):], prog=prog, monkeypatch=monkeypatch)
    assert again.code == 0, again
    model = written_model(world)
    assert model.allow_plain_http_key is True
    assert model.base_url == PLAIN


def test_a_set_key_on_plain_http_is_refused_before_the_check_opens_a_socket(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(KEY_VAR, SENTINEL)
    typed = ["init", "--yes", "--no-fetch", "--base-url", PLAIN]
    refused_as_typed(invoke(typed, prog=prog, monkeypatch=monkeypatch), typed, world)


@pytest.mark.parametrize("url", [LOOPBACK, HTTPS], ids=["loopback", "https"])
@pytest.mark.parametrize("check", [["--no-check-key"], []], ids=["no-check-key", "default"])
def test_an_unset_key_on_loopback_or_https_is_written_as_before(
    url: str, check: list[str], prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran = invoke(["init", "--yes", "--no-fetch", *check, "--base-url", url], prog=prog,
                 monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    assert error_lines(ran) == [], ran
    assert ran.events == (), ran
    assert written_model(world).base_url == url


class EchoingAnswers(Answers):
    """`Answers` on a terminal that echoes each Enter to stderr, as a real one does, so what is
    said after the last question starts a line of its own."""

    def readline(self, size: int | None = -1) -> str:  # type: ignore[override]
        line = super().readline(size)
        sys.stderr.write("\n")
        return line


def test_the_dialogue_refuses_an_unset_key_on_plain_http_after_its_questions(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Enter through every question: the command then refuses as the one with no questions
    does, its `error:` and `next:` lines the last on stderr.  `invoke`'s shared checks read no
    stderr after a dialogue, and so are made here, on those two lines."""
    typed = ["init", "--no-fetch", "--base-url", PLAIN]
    stdin = EchoingAnswers([])
    ran = invoke(typed, prog=prog, monkeypatch=monkeypatch, stdin=stdin, check=False)
    assert stdin.reads > 0
    assert ran.code == 1, ran
    assert ran.out == "", ran
    lines = error_lines(ran)
    assert len(lines) == 1 and ran.err_lines[-2] == lines[0], ran
    assert conformance(dataclasses.replace(ran, err="\n".join(ran.err_lines[-2:])), "init") == []
    assert tree(world.work) == {}, ran
    assert ran.events == (), ran
    commands = next_commands(ran.err_lines[-1])
    assert [shlex.split(command) for command in commands] == [
        [*shlex.split(prog), *typed, "--allow-plain-http-key"]], ran
