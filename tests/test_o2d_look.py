"""The command's own-tools invocations under rule L16: each run both ways.

FD5's look conformance (`tests/test_fd5_look.py`) holds a corpus of invocations to the one switch
between the plain and the pretty style: piped, the pretty build equals the plain build byte for
byte; in a terminal, the first line and the exit code are the plain style's.  The invocations
O2 Session B2 adds to the command (own-tools spec §8) are held to the same rule here, through
that module's own machinery, so its frozen corpus stays as it is.
"""

from __future__ import annotations

import shlex
import sys

import pytest

from tests.fd5_support import World, world
from tests.o1_support import FAKE_MCP_SERVER, fixture
from tests.test_fd5_look import first_verdict, in_terminals, piped, pretty_env, stripped

FIXTURES = (world,)
"""FD5's world, used here by name."""

FLOWS = ["--own-flow", "search_orders.orders[].order_id:get_order.order_id",
         "--own-flow", "get_order.order_id:refund_order.order_id"]
QUIET = ["--yes", "--no-fetch", "--no-check-key"]


def prepared(world: World) -> None:
    """A settings file on the acme set with its two flows, two tasks a level, and the tool
    files the corpus names."""
    from poisson_tasks import config

    (world.work / "tools.json").write_bytes(fixture("acme-mcp-tools-list.json"))
    (world.work / "tools.openai.json").write_bytes(fixture("acme-openai-chat.json"))
    (world.work / "petstore.json").write_bytes(fixture("petstore-openapi-3.0.json"))
    made = config.config_from_init_args(["--tasks-per-level", "2", "--own-file", "tools.json",
                                         "--own-name", "acme-support", *FLOWS])
    (world.work / "tasks.toml").write_text(config.dump_config(made), encoding="utf-8")


def mcp_command(world: World) -> str:
    return shlex.join([sys.executable, str(FAKE_MCP_SERVER), str(world.tmp / "log"),
                       str(world.tmp / "marker")])


CORPUS: dict[str, list[str]] = {
    "init-own": ["init", *QUIET, "--force", "--own-file", "tools.json", *FLOWS],
    "init-own-openai": ["init", *QUIET, "--force", "--own-file", "tools.openai.json",
                        "--own-read", "get_order", "--own-flow", "get_order.id:refund_order.order_id"],
    "init-own-openapi": ["init", *QUIET, "--force", "--own-file", "petstore.json",
                         "--own-name", "petstore", "--recipe", "custom", "--knob", "faults"],
    "init-own-custom": ["init", *QUIET, "--force", "--own-file", "tools.json", *FLOWS,
                        "--recipe", "custom", "--knob", "faults", "--levels", "0,2"],
    "init-mcp-command": ["init", *QUIET, "--force", "--mcp-command", "@MCP@", "--recipe",
                         "error-recovery"],
    "doctor-own": ["doctor", "--offline"],
    "doctor-own-command": ["doctor", "--show-command"],
    "generate-own": ["generate", "--force"],
    "generate-own-show": ["generate", "--show", "--arm", "depth:d1", "--task", "1"],
    "export-own": ["export", "--to", "verifiers", "--force"],
    "run-own-dry": ["run", "--dry-run", "--offline"],
    "an-own-refusal": ["init", *QUIET, "--force", "--own-file", "missing.json"],
    "an-own-usage-error": ["init", *QUIET, "--force", "--own-file", "tools.json", "--own-flow",
                           "search_orders.orders:get_order"],
    "an-own-recipe-not-offered": ["init", *QUIET, "--force", "--own-file", "tools.json",
                                  "--recipe", "first-look"],
}


def argv_of(name: str, world: World) -> list[str]:
    return [mcp_command(world) if word == "@MCP@" else word for word in CORPUS[name]]


@pytest.mark.parametrize("name", list(CORPUS))
def test_l16_piped_the_pretty_build_equals_the_plain_build_byte_for_byte_on_own_tools(
    name: str, world: World
) -> None:
    prepared(world)
    argv = argv_of(name, world)
    pretty = piped(argv, pretty_env(world), world)
    plain = piped([*argv, "--plain"], pretty_env(world), world)
    no_color = piped(argv, pretty_env(world, NO_COLOR="1"), world)
    assert pretty == plain == no_color, (pretty, plain, no_color)
    assert b"\x1b" not in pretty[1] + pretty[2]
    assert not (world.tmp / "marker").exists()


@pytest.mark.parametrize("name", list(CORPUS))
def test_l16_in_a_terminal_the_first_line_and_the_exit_code_are_plains_on_own_tools(
    name: str, world: World
) -> None:
    prepared(world)
    argv = argv_of(name, world)
    code, out, err = piped([*argv, "--plain"], pretty_env(world), world)
    tty_code, tty_out, tty_err = in_terminals(argv, pretty_env(world), world)
    assert tty_code == code, (tty_out, tty_err, out.decode(), err.decode())
    shown = stripped(tty_out)
    if not out:
        assert not shown.strip(), shown
    else:
        assert first_verdict(shown) == first_verdict(out.decode()), (shown, out.decode())
    plain_errors = [line for line in err.decode().splitlines() if line.startswith("error: ")]
    shown_errors = [line for line in stripped(tty_err).splitlines()
                    if line.startswith("error: ")]
    assert [line.split(";")[0] for line in shown_errors] == [
        line.split(";")[0] for line in plain_errors], (tty_err, err.decode())
