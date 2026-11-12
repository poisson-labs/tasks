"""In a narrow terminal nothing folds back to the left edge that could keep its indent, nothing is
split inside a value, and a long tool-file path is not repeated (#33).

Found in the hands-on check of 2026-10-21 and reproduced at 60 and 80 columns in both looks, across
the verbs and the guided session:
- a note, an error, a line of a verb's dialogue (`init`'s question notes) and every line the
  session writes wrapped back to column 0 in the pretty look (Rich and the terminal folded them),
  and the session wrapped nothing at all in either look;
- a JSON reply and a call's quoted argument in the reference solution were cut mid-string (Rich's
  fold in the pretty look; the terminal's fold in the plain one, where a call has no space to
  break at), and the task's own text was folded at column 0;
- an unnamed tool set was called by the whole path its settings give, on the settings line,
  `init`'s closing line and the session's summary, which a long path ran to two lines each;
- a command to copy, broken before its flags at 78 columns, was folded by any narrower terminal;
- `--help`'s examples and exit codes, which argparse prints as written, folded at column 0.

The rule both looks keep (the 0.1.0 changelog's): no path, URL, command or quoted value is ever
split by a line break, and a wrapped row keeps its indent.  A piece longer than any line is left
whole for the terminal to fold.  `--json` is never wrapped at all.
"""

from __future__ import annotations

import io
import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tests.fd5_support import World, base_env, invoke, prog, world
from tests.test_fd5_look import in_terminals, piped, pretty_env, rendered, stripped

__all__ = ["prog", "world"]

WIDTHS = (60, 80)
PROG = "poisson-tasks"
REPO = Path(__file__).resolve().parents[1]
PETSTORE = REPO / "tests" / "fixtures" / "o1" / "petstore-openapi-3.0.json"

QUOTED = re.compile(r'"(?:[^"\\]|\\.)*"')
CALL = ('addPet(id=167, name="jzmfuzwzf", category={"id": 71, "name": "nkvdd"}, photoUrls=[], '
        'tags=[{"id": 206, "name": "nqhqnbozg"}, {"id": 566, "name": "vbellrpyqze"}], '
        'status="available")')
REPLY = ('{"category":{"id":71,"name":"nkvdd"},"id":167,"name":"jzmfuzwzf","photoUrls":[],'
         '"status":"available","tags":[{"id":206,"name":"nqhqnbozg"},'
         '{"id":566,"name":"vbellrpyqze a name with spaces"}]}')
LONG_PATH = "/home/someone/Projects With Spaces/a rather long evaluation folder/tools.json"


def wrap() -> Any:
    from poisson_tasks.cli import _wrap

    return _wrap


def quoted_whole(text: str, shown: str) -> list[str]:
    """Each quoted value of `text` that is not whole on one line of `shown`."""
    lines = shown.splitlines()
    return [value for value in QUOTED.findall(text)
            if not any(value in line for line in lines)]


def cut_strings(shown: str) -> list[str]:
    """The lines of `shown` that hold an odd number of double quotes (an escaped one aside): a
    line that ends or starts inside a quoted string, cut in two by a line break."""
    return [line for line in shown.splitlines()
            if len(re.findall(r'(?<!\\)"', line)) % 2 == 1]


def too_wide(shown: str, width: int, whole: tuple[str, ...] = ()) -> list[str]:
    """The lines of `shown` wider than `width` that are not one of `whole` (a piece no line can
    hold) after their indent and the text before it."""
    return [line for line in shown.splitlines() if len(line) > width
            and not any(piece in line and len(piece) > width - 12 for piece in whole)]


# ---------------------------------------------------------------------------
# the rule
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("width", WIDTHS)
def test_the_rule_never_splits_a_quoted_value_a_path_a_command_or_an_assignment(
    width: int,
) -> None:
    text = (f"the tools at {LONG_PATH} were read; {PROG} run --config experiments/long-name.toml "
            "--spend-cap 2.00 resumes it, after export OPENAI_API_KEY=sk-placeholder is set, and "
            "the name 'gpt 5 nano with spaces' is the one the provider spells, see "
            "https://example.com/a/very/long/url/that/goes/on")
    lines = wrap().lines(text, width, indent=2, keep=(LONG_PATH,), prog=PROG)
    shown = "\n".join(lines)
    for piece in (LONG_PATH, f"{PROG} run --config experiments/long-name.toml --spend-cap 2.00",
                  "export OPENAI_API_KEY=sk-placeholder", "'gpt 5 nano with spaces'",
                  "https://example.com/a/very/long/url/that/goes/on"):
        assert any(piece in line for line in lines), (piece, shown)
    assert " ".join(line.strip() for line in lines) == text, shown
    assert all(line.startswith("  ") for line in lines[1:]), shown
    command = f"{PROG} run --config experiments/long-name.toml --spend-cap 2.00"
    assert too_wide(shown, width, (LONG_PATH, command)) == [], shown


@pytest.mark.parametrize("width", WIDTHS)
@pytest.mark.parametrize("text", [CALL, f"-> {REPLY}"], ids=["call", "reply"])
def test_a_call_or_a_json_reply_breaks_only_between_its_members(width: int, text: str) -> None:
    lines = wrap().lines(text, width, first=5, indent=5)
    shown = "\n".join(lines)
    assert quoted_whole(text, shown) == [], shown
    assert cut_strings(shown) == [], shown
    assert all(len(line) <= width - (5 if index == 0 else 0)
               for index, line in enumerate(lines)), shown
    assert all(line.startswith("     ") for line in lines[1:]), shown
    assert not any(line.rstrip().endswith('":') for line in lines), "a key parted from its value"
    assert "".join(line.strip() for line in lines).replace(" ", "") == text.replace(" ", "")


def test_a_piece_no_line_can_hold_is_left_whole_on_a_line_of_its_own() -> None:
    """Beside its label it stays where it is (the label is `first`); after other words it starts
    a line of its own at the indent; either way the terminal folds it, and nothing else."""
    digest = "27ce0fc49091d238619aef4ac01c29c638b6226b02dfaacdee51a9b0f8671ed8"
    assert wrap().lines(f"{digest} of depth:d3", 60, first=11, indent=11) == [
        digest, "           of depth:d3"]
    assert wrap().lines(f"the task id is {digest} of depth:d3", 60, indent=2) == [
        "the task id is", f"  {digest}", "  of depth:d3"]


def test_text_that_fits_is_printed_as_written() -> None:
    text = "plan  30 episodes   against   the fixture: about $0.02"
    assert wrap().lines(text, 100) == [text]


words = st.one_of(
    st.from_regex(r"[a-z]{1,12}", fullmatch=True),
    st.from_regex(r'"[a-z ]{1,30}"', fullmatch=True),
    st.from_regex(r"/[a-z]{1,10}(/[a-z]{1,10}){1,5}", fullmatch=True),
)


@settings(max_examples=200, deadline=None)
@given(st.lists(words, min_size=1, max_size=40), st.sampled_from(WIDTHS),
       st.integers(min_value=0, max_value=12))
def test_property_every_word_comes_back_whole_in_order_at_its_indent(
    pieces: list[str], width: int, indent: int,
) -> None:
    text = " ".join(pieces)
    lines = wrap().lines(text, width, indent=indent)
    assert " ".join(line.strip() for line in lines) == text
    assert all(line.startswith(" " * indent) for line in lines[1:])
    for piece in pieces:
        if " " in piece:
            assert any(piece in line for line in lines), (piece, lines)
    for line in lines:
        if len(line) > width:
            # only a line that holds one piece too long for any line
            assert len(line.strip().split(" ")) >= 1 and any(
                len(piece) > width - indent - 1 for piece in pieces if piece in line), lines


# ---------------------------------------------------------------------------
# the pretty look, drawn into a console of the width
# ---------------------------------------------------------------------------


def pretty() -> Any:
    from poisson_tasks.cli import _pretty

    return _pretty


def plain_text(raw: str) -> str:
    from rich.text import Text

    return Text.from_ansi(raw).plain


@pytest.mark.parametrize("width", WIDTHS)
def test_a_note_keeps_its_indent_when_it_wraps_in_the_pretty_look(width: int) -> None:
    message = (f"the package at {LONG_PATH} is outside this environment, so {PROG} doctor "
               "--offline says which one runs; the name 'gpt 5 nano with spaces' is kept")

    def draw(console: Any) -> None:
        pretty().Pretty(PROG, out=console, err=console).note(message)

    shown = plain_text(rendered(width, draw))
    lines = shown.splitlines()
    assert lines[0].startswith("note: "), shown
    assert len(lines) > 1 and all(line.startswith("  ") for line in lines[1:]), shown
    assert "'gpt 5 nano with spaces'" in shown and f"{PROG} doctor --offline" in shown, shown
    assert too_wide(shown, width, (LONG_PATH,)) == [], shown


@pytest.mark.parametrize("width", WIDTHS)
def test_a_questions_note_keeps_its_indent_in_the_pretty_look(
    width: int, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`init`'s third question and its note on the published card (the hands-on check's F6)."""
    hint = ("This one has a published card. It was measured on an earlier build of the "
            "generator, so a card from your run cannot be read beside it in this release; a "
            "later release measures it again on the current generator.")
    held = io.StringIO()
    from rich.console import Console

    console = Console(file=held, width=width, force_terminal=True, color_system="standard")
    ui = pretty().Pretty(PROG, out=console, err=console)
    monkeypatch.setattr(ui, "_line", lambda tokens: "")
    answer = ui.ask(3, "The model's name, as the provider spells it", "gpt-5-nano-2025-08-07",
                    hint=hint)
    assert answer == "gpt-5-nano-2025-08-07"
    lines = [line for line in plain_text(held.getvalue()).splitlines() if line.strip()]
    assert lines[0].startswith("3. The model's name"), lines
    assert all(line.startswith("   ") for line in lines[1:]), lines
    assert all(len(line) <= width for line in lines), lines


@pytest.mark.parametrize("width", WIDTHS)
def test_the_dialogues_lines_keep_their_indent_in_the_pretty_look(width: int) -> None:
    text = ("OPENAI_API_KEY is not set; set it in this shell (export OPENAI_API_KEY=…) and run "
            "again before the run asks for its cost")

    def draw(console: Any) -> None:
        ui = pretty().Pretty(PROG, out=console, err=console)
        ui.say(text, "bad")
        ui.say(text + "\n" + text)

    lines = [line for line in plain_text(rendered(width, draw)).splitlines() if line.strip()]
    assert lines[0].startswith("   ✗ "), lines
    assert all(line.startswith("   ") for line in lines), lines
    assert sum("(export OPENAI_API_KEY=…)" in line for line in lines) == 3, lines
    assert all(len(line) <= width for line in lines), lines


def solution_result() -> Any:
    from poisson_tasks.cli._result import Part, Result

    return Result(schema="poisson-tasks.test/1", verdict="ok", tone="good", sentence="one task",
                  document=[
                      Part(title="what the model is shown", kind="quote",
                           body='Advance record "able-sheet-shopping-question" of the purchase '
                                "ledger, and reply in plain text once the request is satisfied."),
                      Part(title="the tools it may call", kind="tools",
                           body=[("addPet", "id, name, category, photoUrls, tags, status", True)]),
                      Part(title="the reference solution", kind="steps",
                           body=[(CALL.split("(")[0], CALL.split("(", 1)[1][:-1], REPLY)]),
                      Part(title="the wrong answers", kind="answers",
                           body=[("wrong_state", "wrong_state",
                                  "The model stopped with the record in a state that is not the "
                                  "goal.")]),
                  ])


@pytest.mark.parametrize("width", WIDTHS)
def test_a_task_in_the_pretty_look_splits_no_value_and_folds_nothing(width: int) -> None:
    def draw(console: Any) -> None:
        pretty().Pretty(PROG, out=console, err=console).show(solution_result())

    shown = plain_text(rendered(width, draw))
    assert quoted_whole(CALL + REPLY + '"able-sheet-shopping-question"', shown) == [], shown
    assert cut_strings(shown) == [], shown
    assert all(len(line) <= width for line in shown.splitlines()), shown
    body = shown.split("\nthe reference solution", 1)[1].split("\nthe wrong answers")[0]
    assert all(line.startswith("  ") for line in body.splitlines() if line.strip()), body


# ---------------------------------------------------------------------------
# the plain look, on a terminal of the width
# ---------------------------------------------------------------------------


class _Terminal(io.StringIO):
    def isatty(self) -> bool:
        return True


def plain_on_a_terminal(width: int, monkeypatch: pytest.MonkeyPatch, draw: Any) -> str:
    from poisson_tasks.cli import _plain

    monkeypatch.setenv("COLUMNS", str(width))
    out = _Terminal()
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", out)
    draw(_plain.PlainUI(PROG))
    return out.getvalue()


@pytest.mark.parametrize("width", WIDTHS)
def test_a_task_in_the_plain_look_splits_no_value_and_keeps_its_indent(
    width: int, monkeypatch: pytest.MonkeyPatch,
) -> None:
    shown = plain_on_a_terminal(width, monkeypatch, lambda ui: ui.show(solution_result()))
    assert quoted_whole(CALL + REPLY + '"able-sheet-shopping-question"', shown) == [], shown
    assert cut_strings(shown) == [], shown
    assert all(len(line) <= width for line in shown.splitlines()), shown
    body = shown.split("\nthe reference solution", 1)[1].split("\nthe wrong answers")[0]
    assert all(line.startswith("  ") for line in body.splitlines() if line.strip()), body


@pytest.mark.parametrize("width", WIDTHS)
def test_a_note_and_an_error_keep_their_indent_in_the_plain_look(
    width: int, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """The path is under the working folder, whose name has spaces: a path that starts with the
    folder the command runs in is kept whole, its spaces and all."""
    here = tmp_path / "Projects With Spaces" / "a rather long evaluation folder"
    here.mkdir(parents=True)
    monkeypatch.chdir(here)
    path = f"{here}/tools.json"
    message = (f"the tools at {path} were read\nand {PROG} run --spend-cap 2.00 resumes it; "
               "the name 'gpt 5 nano with spaces' is kept")

    def draw(ui: Any) -> None:
        ui.note(message)
        ui.error(message)

    lines = plain_on_a_terminal(width, monkeypatch, draw).splitlines()
    assert lines[0].startswith("note: ") and any(line.startswith("error: ") for line in lines)
    assert all(line.startswith(("note: ", "error: ", "  ")) for line in lines), lines
    assert sum(f"{PROG} run --spend-cap 2.00" in line for line in lines) == 2, lines
    assert sum(path in line for line in lines) == 2, lines


@pytest.mark.parametrize("width", WIDTHS)
def test_plain_help_wraps_its_examples_at_their_column(
    width: int, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from poisson_tasks.cli import _parser

    parser = _parser.build_parser(PROG)
    shown = plain_on_a_terminal(width, monkeypatch, lambda ui: ui.help(parser))
    assert all(len(line) <= width for line in shown.splitlines()), [
        line for line in shown.splitlines() if len(line) > width]


@pytest.mark.parametrize("width", WIDTHS)
def test_a_command_to_copy_fits_the_terminal_and_is_unchanged_at_78(width: int) -> None:
    from poisson_tasks.cli._plain import COMMAND_WIDTH, command_width, continued_command

    argv = (f"{PROG} init --yes --provider openai --model gpt-5-nano-2025-08-07 --base-url "
            "https://api.openai.com/v1 --api-key-env OPENAI_API_KEY --price 0.05,0.005,0.4 "
            "--price-read-on 2026-09-25 --recipe first-look --tasks-per-level 10").split()
    lines = continued_command(argv, width=command_width(width))
    assert all(len(line) <= width for line in lines), lines
    assert " ".join(line.strip().rstrip("\\").strip() for line in lines) == " ".join(argv)
    assert command_width(None) == COMMAND_WIDTH == command_width(200)
    assert continued_command(argv) == continued_command(argv, width=command_width(None))


# ---------------------------------------------------------------------------
# end to end, on a pseudo-terminal, both looks
# ---------------------------------------------------------------------------


def look_env(world: World, look: str) -> dict[str, str]:
    return pretty_env(world) if look == "pretty" else pretty_env(world, NO_COLOR="1")


@pytest.mark.parametrize("width", WIDTHS)
@pytest.mark.parametrize("look", ["plain", "pretty"])
def test_generate_show_in_a_narrow_terminal_splits_no_quoted_value(
    look: str, width: int, world: World,
) -> None:
    argv = ["generate", "--arm", "depth:d3", "--show", "--task", "1"]
    code, out, err = in_terminals(argv, look_env(world, look), world, columns=width)
    assert code == 0, (out, err)
    _, whole, _ = piped(argv, base_env(world), world)
    shown = stripped(out)
    assert quoted_whole(whole.decode(), shown) == [], shown
    assert cut_strings(shown) == [], shown
    digest = re.search(r"\b[0-9a-f]{64}\b", whole.decode())
    parts = shown.split("\n\n", 1)[1]
    assert too_wide(parts, width, (digest.group(0),) if digest else ()) == [], parts


@pytest.mark.parametrize("width", WIDTHS)
@pytest.mark.parametrize("look", ["plain", "pretty"])
def test_a_json_reply_on_your_own_tools_is_split_only_between_members(
    look: str, width: int, world: World, monkeypatch: pytest.MonkeyPatch,
) -> None:
    deep = world.work / "tool files kept somewhere deep"
    deep.mkdir()
    tools = deep / PETSTORE.name
    tools.write_bytes(PETSTORE.read_bytes())
    made = invoke(["init", "--yes", "--no-check-key", "--own-file", str(tools),
                   "--recipe", "error-recovery"], prog=PROG, monkeypatch=monkeypatch)
    assert made.code == 0, made
    assert str(tools) not in made.out, "the path is repeated on init's closing line"
    assert f"your tools ({tools.name})" in made.out, made
    argv = ["generate", "--arm", "faults:f0", "--show", "--task", "1"]
    code, out, err = in_terminals(argv, look_env(world, look), world, columns=width)
    assert code == 0, (out, err)
    _, whole, _ = piped(argv, base_env(world), world)
    shown = stripped(out)
    assert quoted_whole(whole.decode(), shown) == [], shown
    assert cut_strings(shown) == [], shown
    solution = shown.split("\nthe reference solution\n", 1)[1].split("\n\n")[0]
    assert all(len(line) <= width for line in solution.splitlines()), solution
    assert all(line.startswith("  ") for line in solution.splitlines() if line.strip()), solution


@pytest.mark.parametrize("width", WIDTHS)
@pytest.mark.parametrize("look", ["plain", "pretty"])
def test_json_is_never_wrapped(look: str, width: int, world: World,
                               monkeypatch: pytest.MonkeyPatch) -> None:
    assert invoke(["init", "--yes", "--no-check-key"], prog=PROG,
                  monkeypatch=monkeypatch).code == 0
    argv = ["run", "--dry-run", "--offline", "--json"]
    code, out, _ = in_terminals(argv, look_env(world, look), world, columns=width)
    _, whole, _ = piped(argv, base_env(world), world)
    assert code == 0
    assert stripped(out).splitlines() == whole.decode().splitlines()
    assert any(len(line) > width for line in whole.decode().splitlines()), "nothing to wrap"
    json.loads(whole)


# ---------------------------------------------------------------------------
# the guided session
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("width", WIDTHS)
def test_the_session_wraps_its_rows_at_their_column_and_names_the_tool_file_once(
    width: int, world: World, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.fd9_support import Keys, in_session

    folder = world.work / "Projects With Spaces" / "a rather long evaluation folder"
    folder.mkdir(parents=True)
    tools = folder / PETSTORE.name
    tools.write_bytes(PETSTORE.read_bytes())
    monkeypatch.chdir(folder)
    assert invoke(["init", "--yes", "--no-check-key", "--own-file", str(tools), "--recipe",
                   "error-recovery"], prog=PROG, monkeypatch=monkeypatch).code == 0
    monkeypatch.setenv("COLUMNS", str(width))
    session = in_session(Keys(["quit"]), monkeypatch)
    shown = session.out
    assert str(tools) not in shown, shown
    home = shown.split("\nnext\n", 1)[0].splitlines()
    rows = [line for line in home if re.match(r"^(folder|settings|your tools|ready|runs)\b",
                                              line)]
    assert [row.split()[0] for row in rows][:2] == ["folder", "settings"], home
    column = len(re.match(r"^\S+(?: \S+)?\s+", rows[1]).group(0))
    after = home[home.index(rows[1]) + 1:]
    for line in after:
        if line and not re.match(r"^(your tools|ready|runs|latest card)\b", line):
            assert line.startswith(" " * column), (line, home)
    where = str(Path.cwd().resolve())
    assert too_wide("\n".join(home[1:]), width, (where, "~" + where)) == [], home
    steps = shown.split("\nnext\n", 1)[1].split("\n\n")[0].splitlines()
    assert all(re.match(r"^  \d+  \S", line) or line.startswith("     ") for line in steps), steps
    assert all(len(line) <= width for line in steps), steps
