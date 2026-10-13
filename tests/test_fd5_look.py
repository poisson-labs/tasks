"""The pretty style and what it may not change, frozen as tests before it is built.

Ruled 2026-10-13 (`evidence/cli-look-mockups/yes-nos.md`, every item yes): the pretty style is the
standard look, drawn with Rich, with questionary for `init`'s two menus; the plain style is the
contract every other FD5 test pins, and rule L16 is replaced.  Tasks' part only.
- **L16, the conformance test** (§11.4): each invocation of a corpus is run both ways.  Piped,
  the pretty build equals the plain build byte for byte.  In a pseudo-terminal, with escape
  sequences removed, the first line carries the same verdict word and sentence, and the exit
  code matches.  `--json` is identical.
- **Item 6, one switch, two states**: pretty runs only when stdout and stderr are both
  terminals, `NO_COLOR` is unset or empty, `CI` is unset, `TERM` is not `dumb`, stdout is UTF-8,
  and neither `--json` nor **`--plain` (item 7)** was given; otherwise plain runs, byte for byte.
  `NO_COLOR` turns off the whole pretty style, not only its colour.
- **Item 2**: plain wraps its own long lines at the terminal's width, with a hanging indent, when
  it is writing to a terminal, and never inside a question's bracketed default; piped output
  stays one line per fact.
- **Item 4**: `init`'s two menus are questionary's in the pretty style, and the file they write
  is the one `init --yes` writes.
- **L16's colours**: green for `ok`, `done` and `passed`; yellow for `stopped`, `refused` and
  `note:`; red for `error:` and `not ready`; a neutral verdict bold with no colour; a number
  never coloured; only the terminal's named colours.
- **L16**: a command printed for the user to copy is never hard-wrapped.
- **Item 27**: a table too wide for the terminal moves a unit every cell repeats into its header,
  with nothing dropped.
- **Item 24**: the equivalent `init --yes` command is printed broken before its flags with
  backslashes, in both styles, and still reads as one command.
- **Item 14**: in the plain style each `doctor` line carries a status word.
- **Item 12 and 13**: the plan's calls line is not a floor, and a dollar figure below $0.10 has
  two significant digits.
- **Item 20**: the pretty progress display shows how many passed, per level.

Shapes decided here
-------------------

**1. The renderers are private to the command**: `poisson_tasks.cli._pretty` (Rich) and
`poisson_tasks.cli._plain`; both print one `poisson_tasks.cli._result.Result`.  The tests of
colour and of the over-wide table draw into a recording console of a chosen width.

**2. A pseudo-terminal for each stream**: stdout and stderr each get a pseudo-terminal of their
own, 100 columns unless a test says otherwise, so what each stream carries is read apart.
"""

from __future__ import annotations

import fcntl
import importlib
import io
import os
import pty
import re
import select
import shlex
import struct
import subprocess
import sys
import termios
import time
from typing import Any

import pytest

from tests.fd2_fakes import SENTINEL
from tests.fd3_support import KEY, KEY_VAR, needs_uv, stub_bin
from tests.fd5_support import (
    PROGS,
    VERDICT_LINE,
    World,
    base_env,
    config,
    fixture_flags,
    invoke,
    joined_lines,
    next_commands,
    printed_command,
    prog,
    runs,
    strict_json,
    strip_prog,
    world,
    write_config,
)
from tests.fixtures.model_server import FixtureModel

__all__ = ["prog", "world"]

DASHED = PROGS[0]

ESCAPE = re.compile(
    r"\x1b(?:\[[0-9;?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\)|[@-Z\\-_])"
)
"""An escape sequence: CSI, OSC, or a two-character sequence."""


def stripped(text: str) -> str:
    """`text` without escape sequences and carriage returns."""
    return ESCAPE.sub("", text).replace("\r", "")


def pretty_env(world: World, **extra: str) -> dict[str, str]:
    """A child's environment in which the pretty style may run: no `NO_COLOR`, no `CI`, a
    terminal type that is not `dumb`, a UTF-8 stdout, and the fixed width."""
    env = base_env(world)
    env.pop("NO_COLOR", None)
    env.pop("CI", None)
    env["TERM"] = "xterm-256color"
    env["PYTHONIOENCODING"] = "utf-8"
    env.update(extra)
    return env


def piped(argv: list[str], env: dict[str, str], world: World,
          stdin: bytes = b"") -> tuple[int, bytes, bytes]:
    done = subprocess.run([sys.executable, "-m", "poisson_tasks", *argv], cwd=world.work,
                          env=env, input=stdin, capture_output=True, timeout=600, check=False)
    return done.returncode, done.stdout, done.stderr


def in_terminals(
    argv: list[str], env: dict[str, str], world: World, *, columns: int = 100,
    presses: int = 0, stdout_tty: bool = True, stderr_tty: bool = True, timeout: float = 600,
) -> tuple[int, str, str]:
    """The command run with stdout and stderr each on a pseudo-terminal of `columns` columns
    (or piped, where a flag says so), and stdin on stdout's terminal, which gets Enter whenever
    the output has been quiet for a second and a half, at most `presses` times.  Each
    terminal's side is held open until everything is read.  Returns the exit code and what
    each stream carried, escapes included."""
    env = {**env, "COLUMNS": str(columns)}
    masters: dict[str, int] = {}
    slaves: dict[str, int] = {}
    pipes: dict[str, Any] = {}
    for name, tty in (("out", stdout_tty), ("err", stderr_tty)):
        if tty:
            master, slave = pty.openpty()
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 40, columns, 0, 0))
            masters[name], slaves[name] = master, slave
    stdin = slaves.get("out", subprocess.DEVNULL)
    process = subprocess.Popen(
        [sys.executable, "-m", "poisson_tasks", *argv], cwd=world.work, env=env,
        stdin=stdin,
        stdout=slaves.get("out", subprocess.PIPE), stderr=slaves.get("err", subprocess.PIPE),
        start_new_session=True,
    )
    for name in ("out", "err"):
        if name not in slaves:
            pipes[name] = getattr(process, "stdout" if name == "out" else "stderr")
    got: dict[str, bytes] = {"out": b"", "err": b""}
    readable = {**masters, **{name: pipe.fileno() for name, pipe in pipes.items()}}
    by_fd = {fd: name for name, fd in readable.items()}
    closed: set[int] = set()
    deadline = time.monotonic() + timeout
    quiet_since = time.monotonic()
    pressed = 0
    try:
        while time.monotonic() < deadline:
            open_fds = [fd for fd in by_fd if fd not in closed]
            ready, _, _ = select.select(open_fds, [], [], 0.25) if open_fds else ([], [], [])
            if ready:
                for fd in ready:
                    try:
                        chunk = os.read(fd, 65536)
                    except OSError:
                        chunk = b""
                    if not chunk:
                        closed.add(fd)
                        continue
                    got[by_fd[fd]] += chunk
                quiet_since = time.monotonic()
                continue
            if process.poll() is not None:
                break
            if "out" in masters and pressed < presses and time.monotonic() - quiet_since > 1.5:
                os.write(masters["out"], b"\r")
                pressed += 1
                quiet_since = time.monotonic()
        process.wait(30)
        for _ in range(50):
            open_fds = [fd for fd in by_fd if fd not in closed]
            ready, _, _ = select.select(open_fds, [], [], 0.2) if open_fds else ([], [], [])
            if not ready:
                break
            for fd in ready:
                try:
                    chunk = os.read(fd, 65536)
                except OSError:
                    chunk = b""
                if not chunk:
                    closed.add(fd)
                    continue
                got[by_fd[fd]] += chunk
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(10)
        for fd in (*slaves.values(), *masters.values()):
            os.close(fd)
        for pipe in pipes.values():
            pipe.close()
    return (process.returncode, got["out"].decode("utf-8", "replace"),
            got["err"].decode("utf-8", "replace"))


def first_verdict(text: str) -> tuple[str, str] | None:
    for line in text.splitlines():
        if not line.strip():
            continue
        match = VERDICT_LINE.match(line.rstrip())
        return (match.group(1), match.group(2).rstrip()) if match else None
    return None


# ---------------------------------------------------------------------------
# the corpus: every verb, a refusal of each kind, help and the version
# ---------------------------------------------------------------------------


def settled(world: World) -> None:
    """A settings file for the OpenAI preset, two tasks per level, with no key set."""
    made = config().config_from_init_args(["--tasks-per-level", "2"])
    (world.work / "tasks.toml").write_text(config().dump_config(made), encoding="utf-8")


CORPUS: dict[str, list[str]] = {
    "help": ["--help"],
    "version": ["--version"],
    "init-help": ["init", "--help"],
    "init": ["init", "--yes", "--no-fetch", "--no-check-key", "--force"],
    "generate": ["generate", "--arm", "depth:d1", "--tasks-per-level", "1", "--force"],
    "generate-show": ["generate", "--arm", "depth:d3", "--show", "--task", "1"],
    "verify": ["verify", "--arm", "depth:d1", "--task", "1", "--self-check"],
    "export": ["export", "--to", "verifiers", "--force"],
    "run-dry": ["run", "--dry-run", "--offline"],
    "card-published": ["card", "--published"],
    "doctor": ["doctor", "--offline"],
    "doctor-command": ["doctor", "--show-command"],
    "a-usage-error": ["generate", "--arm", "dpeth:d1"],
    "a-refusal": ["doctor", "--offline", "--config", "missing.toml"],
    "a-check-not-passed": ["doctor", "--offline", "--config", "keyed.toml"],
}


def prepared(world: World) -> None:
    settled(world)
    keyed = config().config_from_init_args(["--api-key-env", "MY_PROVIDER_API_KEY"])
    (world.work / "keyed.toml").write_text(config().dump_config(keyed), encoding="utf-8")


@pytest.mark.parametrize("name", list(CORPUS))
def test_l16_piped_the_pretty_build_equals_the_plain_build_byte_for_byte(
    name: str, world: World
) -> None:
    prepared(world)
    argv = CORPUS[name]
    pretty = piped(argv, pretty_env(world), world)
    plain = piped([*argv, "--plain"], pretty_env(world), world)
    no_color = piped(argv, pretty_env(world, NO_COLOR="1"), world)
    assert pretty == plain == no_color, (pretty, plain, no_color)
    assert b"\x1b" not in pretty[1] + pretty[2]


@pytest.mark.parametrize("name", list(CORPUS))
def test_l16_in_a_terminal_the_first_line_and_the_exit_code_are_plains(
    name: str, world: World
) -> None:
    prepared(world)
    argv = CORPUS[name]
    code, out, err = piped([*argv, "--plain"], pretty_env(world), world)
    tty_code, tty_out, tty_err = in_terminals(argv, pretty_env(world), world)
    assert tty_code == code, (tty_out, tty_err, out.decode(), err.decode())
    shown = stripped(tty_out)
    if name in ("help", "version", "init-help"):
        # the help and the version carry no verdict: every word of plain's is on the terminal
        assert set(out.decode().split()) <= set(shown.split()), (out.decode(), shown)
        return
    if not out:
        assert not shown.strip(), shown
    else:
        assert first_verdict(shown) == first_verdict(out.decode()), (shown, out.decode())
    plain_errors = [line for line in err.decode().splitlines() if line.startswith("error: ")]
    shown_errors = [line for line in stripped(tty_err).splitlines()
                    if line.startswith("error: ")]
    assert [line.split(";")[0] for line in shown_errors] == [
        line.split(";")[0] for line in plain_errors], (tty_err, err.decode())


@pytest.mark.parametrize("name", ["init", "generate", "verify", "export", "run-dry", "doctor",
                                  "a-check-not-passed"])
def test_l16_json_is_identical_in_a_terminal_and_piped(name: str, world: World) -> None:
    prepared(world)
    argv = [*CORPUS[name], "--json"]
    code, out, err = piped(argv, pretty_env(world), world)
    tty_code, tty_out, tty_err = in_terminals(argv, pretty_env(world), world)
    assert tty_code == code, (tty_out, tty_err)
    assert "\x1b" not in tty_out + tty_err
    assert strict_json(stripped(tty_out)) == strict_json(out.decode()), (tty_out, out)
    assert stripped(tty_out).replace("\n", "") == out.decode().replace("\n", "")


# ---------------------------------------------------------------------------
# item 6 and item 7: one switch, two states
# ---------------------------------------------------------------------------

CONDITIONS: dict[str, dict[str, Any]] = {
    "no-color": {"env": {"NO_COLOR": "1"}},
    "ci": {"env": {"CI": "true"}},
    "term-dumb": {"env": {"TERM": "dumb"}},
    "ascii-stdout": {"env": {"PYTHONIOENCODING": "ascii"}},
    "json": {"argv": ["--json"]},
    "plain-flag": {"argv": ["--plain"]},
    "stdout-piped": {"stdout_tty": False},
    "stderr-piped": {"stderr_tty": False},
}


@pytest.mark.parametrize("condition", list(CONDITIONS))
def test_item_6_each_condition_alone_gives_the_plain_style_byte_for_byte(
    condition: str, world: World
) -> None:
    """With one condition of the switch unmet, both streams are the plain build's on the same
    streams (`--plain`, which wraps on a terminal as item 2 says), byte for byte, with no escape
    sequence: `NO_COLOR` turns off the whole style, `--plain` forces it."""
    settled(world)
    case = CONDITIONS[condition]
    argv = ["run", "--dry-run", "--offline", *case.get("argv", [])]
    env = pretty_env(world, **case.get("env", {}))
    streams = {"stdout_tty": case.get("stdout_tty", True), "stderr_tty": case.get("stderr_tty", True)}
    code, out, err = in_terminals([*argv, "--plain"], env, world, **streams)
    tty_code, tty_out, tty_err = in_terminals(argv, env, world, **streams)
    assert tty_code == code == 0, (tty_out, tty_err)
    assert "\x1b" not in tty_out + tty_err, (tty_out, tty_err)
    assert tty_out == out, (tty_out, out)
    assert tty_err == err, (tty_err, err)
    piped_code, piped_out, _ = piped([*argv, "--plain"], env, world)
    assert piped_code == 0
    assert first_verdict(stripped(tty_out)) == first_verdict(piped_out.decode()), tty_out


def test_item_6_json_gives_plain_even_for_the_error_line_on_a_terminal(world: World) -> None:
    """`--json` turns off the whole pretty style, the `error:` line on stderr included: a refusal
    under `--json` on two terminals sends no escape sequence and equals `--plain`'s byte for
    byte (a success under `--json` prints nothing on stderr, so it could not tell)."""
    argv = ["generate", "--arm", "dpeth:d1", "--json"]
    code, out, err = in_terminals([*argv, "--plain"], pretty_env(world), world)
    tty_code, tty_out, tty_err = in_terminals(argv, pretty_env(world), world)
    assert tty_code == code == 2, (tty_out, tty_err)
    assert "\x1b" not in tty_out + tty_err, (tty_out, tty_err)
    assert tty_err.startswith("error: ") and tty_err == err and tty_out == out == ""


def test_item_6_with_every_condition_met_the_pretty_style_runs(world: World) -> None:
    settled(world)
    code, out, err = in_terminals(["run", "--dry-run", "--offline"], pretty_env(world), world)
    assert code == 0, (out, err)
    assert "\x1b[" in out, "no escape sequence: the pretty style did not run"
    verdict = first_verdict(stripped(out))
    assert verdict is not None and verdict[0] == "plan", stripped(out)


# ---------------------------------------------------------------------------
# item 2: plain wraps on a terminal, not in a pipe
# ---------------------------------------------------------------------------


def test_item_2_plain_wraps_long_lines_on_a_terminal_with_a_hanging_indent(
    world: World
) -> None:
    """The plain style (`NO_COLOR` set) on a 60-column terminal: no line of the plan is longer
    than the terminal, a wrapped line's continuation is indented past its label, and piped the
    same plan is one line per fact; `init`'s tokenizer question, asked on a 60-column terminal,
    keeps its bracketed default whole."""
    settled(world)
    env = pretty_env(world, NO_COLOR="1")
    code, out, err = in_terminals(["run", "--dry-run", "--offline"], env, world, columns=60)
    assert code == 0, (out, err)
    lines = stripped(out).splitlines()
    assert lines and lines[0].startswith("plan  "), lines
    assert all(len(line) <= 60 for line in lines), [line for line in lines if len(line) > 60]
    assert any(line.startswith("    ") for line in lines[1:]), "no continuation line"
    _, piped_out, _ = piped(["run", "--dry-run", "--offline"], env, world)
    facts = piped_out.decode().splitlines()
    assert any(len(line) > 60 for line in facts), "the piped plan has no long line to wrap"
    assert len(lines) > len(facts)
    assert [line for line in facts if line.startswith("next:")] == [
        line for line in lines if line.startswith("next:")]
    (world.work / "tasks.toml").unlink()
    code, out, err = in_terminals(["init", "--no-check-key"], env, world, columns=60,
                                  presses=30)
    assert code == 0, (out, err)
    defaults = re.findall(r"\[([^\[\]\n]*)\]", stripped(out) + stripped(err))
    assert any("0.05" in default and "0.40" in default for default in defaults), defaults
    # the newline after an answer is the terminal's echo, which lives on stdin's terminal (here
    # stdout's), so on stderr alone a prompt and the line after it share a line: split them
    questions = re.sub(r"\] (?= *\S)", "] \n", stripped(err))
    assert all(len(line) <= 60 for line in questions.splitlines()), questions


# ---------------------------------------------------------------------------
# item 4: questionary draws init's menus
# ---------------------------------------------------------------------------


def test_item_4_inits_menus_are_questionarys_and_write_the_yes_file(world: World) -> None:
    code, out, err = in_terminals(["init", "--no-check-key"], pretty_env(world), world,
                                  presses=30)
    assert code == 0, (out, err)
    assert "❯" in out + err, "questionary's pointer was not drawn"
    assert "\x1b[" in out + err
    written = (world.work / "tasks.toml").read_text(encoding="utf-8")
    (world.work / "tasks.toml").unlink()
    yes = piped(["init", "--yes", "--no-fetch", "--no-check-key"], pretty_env(world), world)
    assert yes[0] == 0, yes
    assert written == (world.work / "tasks.toml").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# the renderers: colour, commands, the over-wide table
# ---------------------------------------------------------------------------


def pretty_module() -> Any:
    return importlib.import_module("poisson_tasks.cli._pretty")


def result_module() -> Any:
    return importlib.import_module("poisson_tasks.cli._result")


def rendered(width: int, draw: Any) -> str:
    """What `draw(console)` prints on a terminal of `width` columns, escapes included."""
    from rich.console import Console

    held = io.StringIO()
    console = Console(file=held, width=width, force_terminal=True, color_system="standard",
                      highlight=False, emoji=False, legacy_windows=False)
    draw(console)
    return held.getvalue()


def styles_of(text: str, word: str) -> list[Any]:
    """The styles Rich applied over every occurrence of `word`, read back from the escapes."""
    from rich.text import Text

    parsed = Text.from_ansi(text)
    plain = parsed.plain
    found = []
    at = plain.find(word)
    while at >= 0:
        styles = [span.style for span in parsed.spans if span.start <= at and span.end >= at + len(word)]
        found.append(styles)
        at = plain.find(word, at + 1)
    return found


NAMED = {1: "red", 2: "green", 3: "yellow", 4: "blue", 5: "magenta", 6: "cyan",
         9: "red", 10: "green", 11: "yellow", 12: "blue", 13: "magenta", 14: "cyan"}
"""The terminal's named colours by their number, as escapes name them."""


def colour_names(styles: list[Any]) -> set[str]:
    from rich.style import Style

    names = set()
    for style in styles:
        made = Style.parse(style) if isinstance(style, str) else style
        if made.color is not None:
            names.add(NAMED.get(made.color.number, made.color.name)
                      if made.color.number is not None else made.color.name)
        if made.bold:
            names.add("bold")
        if made.dim:
            names.add("dim")
    return names


@pytest.mark.parametrize("word,tone,colour", [
    ("ok", "good", "green"), ("done", "good", "green"), ("passed", "good", "green"),
    ("stopped", "warn", "yellow"), ("refused", "warn", "yellow"),
    ("not ready", "bad", "red"), ("plan", "neutral", None), ("different", "neutral", None),
])
def test_l16_colour_has_four_meanings(word: str, tone: str, colour: str | None) -> None:
    lib = result_module()
    result = lib.Result(schema="poisson-tasks.test/1", verdict=word, tone=tone,
                        sentence="4,200 episodes, $0.021 spent",
                        rows=[lib.Row("cost", "about $0.02 expected")])
    text = rendered(100, lambda console: pretty_module().Pretty(
        DASHED, out=console, err=console).show(result))
    found = styles_of(text, word)
    assert found, text
    names = colour_names(found[0])
    if colour is None:
        assert "bold" in names and not names & {"green", "yellow", "red", "blue", "cyan"}, names
    else:
        assert colour in names, (names, text)
    for number in ("4,200", "$0.021", "$0.02"):
        for styles in styles_of(text, number):
            assert not colour_names(styles) & {"green", "yellow", "red", "blue", "cyan"}, number


def test_l16_error_is_red_and_note_is_yellow_on_stderr() -> None:
    def draw(console: Any) -> None:
        ui = pretty_module().Pretty(DASHED, out=console, err=console)
        ui.error("the file is not there", [f"{DASHED} init"])
        ui.note("the estimate is from another model")

    text = rendered(100, draw)
    assert "red" in colour_names(styles_of(text, "error:")[0])
    assert "yellow" in colour_names(styles_of(text, "note:")[0])
    for styles in styles_of(text, "the file is not there"):
        assert not colour_names(styles) & {"green", "yellow", "red"}


def test_l16_a_command_to_copy_is_never_hard_wrapped() -> None:
    lib = result_module()
    command = (f"{DASHED} run --config experiments/a-very-long-name.toml --spend-cap 2.00 "
               "--concurrency 3 --again")
    result = lib.Result(schema="poisson-tasks.test/1", verdict="ok", tone="good",
                        sentence="wrote the file", next=[command])
    text = rendered(40, lambda console: pretty_module().Pretty(
        DASHED, out=console, err=console).show(result))
    from rich.text import Text

    plain = Text.from_ansi(text).plain
    assert command in plain.replace("\n", ""), plain
    lines = [line for line in plain.splitlines() if "next:" in line]
    assert len(lines) == 1 and command in lines[0], plain


def levels() -> list[dict[str, Any]]:
    return [
        {"arm_id": "depth:d1", "state": "complete", "pass_at_1": 0.6, "interval": (0.3, 0.9),
         "leaky_at_1": 1.0, "overshoot": 0.4, "tasks": 10, "tasks_planned": 10, "attempts": 1},
        {"arm_id": "depth:d3", "state": "incomplete", "pass_at_1": 0.3, "interval": (0.0, 0.6),
         "leaky_at_1": 0.7, "overshoot": 0.1, "tasks": 4, "tasks_planned": 10, "attempts": 1},
        {"arm_id": "depth:d8", "state": "not run", "pass_at_1": None, "interval": None,
         "leaky_at_1": None, "overshoot": None, "tasks": 0, "tasks_planned": 10, "attempts": 1},
    ]


def test_item_27_a_table_too_wide_for_the_terminal_moves_its_units_into_the_header() -> None:
    """At 120 columns the tasks column's cells carry their units (`10 tasks × 1 attempt`); at
    100 the units move into the header and every figure stays; at 60, where even that is too
    wide, the levels are printed one line each with every figure, nothing cut."""
    from rich.text import Text

    def draw(width: int) -> str:
        return Text.from_ansi(rendered(width, lambda console: console.print(
            pretty_module().levels_table(levels(), width=width)))).plain

    figures = ("depth:d1", "depth:d3", "depth:d8", "0.600", "0.300", "0.900", "0.400", "1.000",
               "not run", "incomplete", "4 of 10")
    wide = draw(120)
    assert "10 tasks × 1 attempt" in wide, wide
    narrow = draw(100)
    assert "10 tasks × 1 attempt" not in narrow, narrow
    header = narrow.splitlines()[0] + narrow.splitlines()[1]
    assert "tasks" in header and "attempt" in header, narrow
    assert "10 × 1" in narrow, narrow
    for figure in figures:
        assert figure in narrow, (figure, narrow)
    assert all(len(line) <= 100 for line in narrow.splitlines()), narrow
    narrowest = draw(60)
    assert "…" not in narrowest, narrowest
    for figure in (*figures, "10 tasks × 1 attempt"):
        assert figure in narrowest, (figure, narrowest)
    assert all(len(line) <= 60 for line in narrowest.splitlines()), narrowest


# ---------------------------------------------------------------------------
# item 24, item 14, items 12 and 13: the plain style's own words
# ---------------------------------------------------------------------------


def test_item_24_the_equivalent_command_is_printed_broken_before_its_flags(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran = invoke(["init", "--yes", "--no-fetch", "--no-check-key"], prog=prog,
                 monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    lines = ran.out.splitlines()
    starts = [i for i, line in enumerate(lines) if f"{prog} init " in line and "next:" not in line]
    assert starts, ran
    at = starts[0]
    continued = []
    while lines[at].rstrip().endswith("\\"):
        continued.append(lines[at])
        at += 1
    continued.append(lines[at])
    assert len(continued) >= 3, continued
    assert all(line.rstrip().endswith("\\") for line in continued[:-1])
    assert all(line.lstrip().startswith("--") for line in continued[1:]), continued
    command = printed_command(ran.out, prog, "init")
    assert command == config().equivalent_init_command(
        config().load_config(world.work / "tasks.toml"), prog=prog)
    assert all(len(line) <= 100 for line in continued), continued


def test_item_14_each_doctor_line_carries_a_status_word(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    made = config().config_from_init_args(["--api-key-env", "MY_PROVIDER_API_KEY"])
    (world.work / "tasks.toml").write_text(config().dump_config(made), encoding="utf-8")
    ran = invoke(["doctor", "--offline"], prog=prog, monkeypatch=monkeypatch)
    assert ran.code == 4 and ran.word == "not ready", ran
    detail = [line for line in ran.lines[1:] if line.startswith("  ") and line.strip()]
    assert len(detail) >= 5, ran
    words = {}
    for line in detail:
        parts = line.split()
        assert len(parts) >= 3, line
        words[parts[0]] = parts[1] if parts[1] != "not" else " ".join(parts[1:3])
    assert set(words.values()) <= {"ok", "not ok"}, words
    assert words["key"] == "not ok" and words["tokenizer"] == "ok", words
    monkeypatch.setenv("MY_PROVIDER_API_KEY", SENTINEL)
    ready = invoke(["doctor", "--offline"], prog=prog, monkeypatch=monkeypatch)
    assert ready.code == 0, ready
    assert all(line.split()[1] == "ok" for line in ready.lines[1:]
               if line.startswith("  ") and line.strip()), ready


def test_item_12_the_calls_line_is_not_a_floor(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    settled(world)
    plan = config().resolve_plan(config().load_config(world.work / "tasks.toml"))
    estimate = runs().estimate(plan)
    ran = invoke(["run", "--dry-run", "--offline"], prog=prog, monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    calls = [line for line in ran.lines if line.strip().startswith("calls")]
    assert len(calls) == 1, ran
    line = calls[0]
    assert f"{estimate.calls_min:,} if every task is solved the shortest way" in line, line
    assert f"about {round(estimate.calls_expected):,} expected" in line, line
    assert f"at most {estimate.calls_at_cap:,}" in line, line
    assert "at least" not in line


@pytest.mark.parametrize("value,shown", [
    (1.0, "$1.00"), (2.5, "$2.50"), (0.1, "$0.10"), (0.0995, "$0.10"), (0.0149, "$0.015"),
    (0.00456, "$0.0046"), (0.021, "$0.021"), (0.0052, "$0.0052"), (0.0, "$0.00"),
])
def test_item_13_dollars_below_ten_cents_have_two_significant_digits(
    value: float, shown: str
) -> None:
    fmt = importlib.import_module("poisson_tasks.cli._format")
    assert fmt.dollars(value) == shown


# ---------------------------------------------------------------------------
# item 20: the pretty progress shows how many passed, per level
# ---------------------------------------------------------------------------


@needs_uv
def test_item_20_the_pretty_progress_shows_how_many_passed_per_level(
    world: World, tmp_path_factory: pytest.TempPathFactory
) -> None:
    stubs = stub_bin(tmp_path_factory.mktemp("quiet-pip"))
    with FixtureModel() as fixture:
        write_config(world.work / "tasks.toml",
                     fixture_flags(fixture.base_url, levels="1,3", tasks_per_level=2))
        env = pretty_env(world, PATH=f"{stubs}{os.pathsep}{os.environ['PATH']}")
        env[KEY_VAR] = KEY
        code, out, err = in_terminals(["run", "--yes"], env, world)
    assert code == 0, (out, err)
    shown = stripped(err)
    assert re.search(r"depth:d1\b.*\b2 passed", shown), shown
    assert re.search(r"depth:d3\b.*\b2 passed", shown), shown
    final = stripped(out)
    verdict = first_verdict(final)
    assert verdict is not None and verdict[0] == "plan", final
    assert "done  " in final


# ---------------------------------------------------------------------------
# the plain contract, read once more: a next command under each prog
# ---------------------------------------------------------------------------


def test_l16_every_next_command_starts_with_the_prog_in_both_styles(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The plain build's `next:` lines (every other test's) and the pretty build's (read through
    a recording console) name the same commands, each starting with the prog."""
    ran = invoke(["init", "--yes", "--no-fetch", "--no-check-key"], prog=prog,
                 monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    commands = next_commands(ran.out)
    assert commands and all(strip_prog(shlex.split(c), prog)[0] == "run" for c in commands)
    lib = result_module()
    result = lib.Result(schema="poisson-tasks.init/1", verdict="ok", tone="good",
                        sentence="wrote tasks.toml", next=commands)
    from rich.text import Text

    text = Text.from_ansi(rendered(100, lambda console: pretty_module().Pretty(
        prog, out=console, err=console).show(result))).plain
    assert next_commands(text) == commands, text
    assert joined_lines(text)[-1].startswith("next: ")
