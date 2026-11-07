"""#30, what an exported run's display means: `export` says it, and so do the docs.

`poisson-tasks export --to verifiers` writes the eval configs and prints the `eval` command that
runs each.  `eval` is verifiers', and so is what it prints (0.3.1, which this package pins):

- beside every episode it prints `[success ]` when the episode ended without an error
  (`verifiers/v1/cli/dashboard/eval.py`, `"error" if t.has_error else "success"`), whatever it
  scored; the score is the `reward=` beside it, so an episode scored 0.00 is a `[success ]` too;
- its usage line adds up each episode's input tokens counted once (`trace.py`, `num_input_tokens`:
  "fed-in tokens, counted once; a lower bound"), while every model call sends the conversation
  again and is billed for it, so the dollars the line implies are less than the run spent.  The
  card and `run` price every call's own usage.

Tasks cannot change a library's display, so `export` now says what the display means, in a second
`note` row under the first and in `--json` (`notes`), and `docs/verifiers-export.md` and
`docs/commands.md` say it with the way to the real figure.

What each test holds:

- the note is printed, in both ways of calling the command's name, says `[success ]`, `reward=`
  and that the usage line counts a conversation once; the first note is as it was;
- `--json` carries both notes as a list;
- the two docs pages show the note in their `export` output block, and `docs/verifiers-export.md`
  explains the display and names the file the real spend is summed from;
- the installed verifiers still does what the note says (a guard: the note is true of 0.3.1, and
  fails the day the pin moves to a verifiers that does otherwise).
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from tests.fd5_support import (
    REPO,
    Ran,
    World,
    config,
    invoke,
    prog,
    strict_json,
    world,
)

__all__ = ["prog", "world"]

FIRST = "run that way, eval leaves out what run adds"
DISPLAY = (
    "eval marks [success ] on every episode that ended without an error, whatever it scored "
    "(reward= is the score), and its usage line counts each conversation once, so the dollars "
    "it implies are less than the run spent"
)


def _exported(world: World, prog: str, monkeypatch: pytest.MonkeyPatch, *extra: str) -> Ran:
    made = config().config_from_init_args(["--tasks-per-level", "2"])
    (world.work / "tasks.toml").write_text(config().dump_config(made), encoding="utf-8")
    ran = invoke(["export", "--to", "verifiers", *extra], prog=prog, monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    return ran


def test_fx30_1_export_says_what_the_evals_display_means(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Red before the change: one note, about what `eval` leaves out."""
    ran = _exported(world, prog, monkeypatch)
    notes = [line.strip() for line in ran.lines if line.strip().startswith("note")]
    assert len(notes) == 2, ran
    assert FIRST in notes[0]
    assert " ".join(notes[1].split()) == "note " + DISPLAY, notes[1]


def test_fx30_2_the_json_carries_both_notes(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Red before the change: the result has no `notes`."""
    ran = _exported(world, prog, monkeypatch, "--json")
    notes = strict_json(ran.out)["notes"]
    assert len(notes) == 2 and notes[0].startswith(FIRST) and notes[1] == DISPLAY, notes


def _output_block_after(text: str, command: str) -> str:
    """The `docs-check: output` block that follows the run block of `command`."""
    start = text.index(f"```bash\n{command}\n```")
    marker = text.index("<!-- docs-check: output -->", start)
    opening = text.index("```", marker)
    return text[opening: text.index("\n```", opening + 3)]


@pytest.mark.parametrize("page", ["docs/commands.md", "docs/verifiers-export.md"])
def test_fx30_3_the_docs_show_the_note_in_the_export_block(page: str) -> None:
    """Red before the change: the block shows the first note and the warning line only."""
    text = (Path(REPO) / page).read_text(encoding="utf-8")
    block = _output_block_after(text, "poisson-tasks export --to verifiers | head -n 5")
    assert FIRST in block and "  note  " + DISPLAY in block, block


def test_fx30_4_the_export_page_explains_the_display_and_where_the_real_spend_is() -> None:
    """Red before the change: the page tells a person reading `[success ]` and `reward=0.00` nothing
    about either."""
    text = " ".join((Path(REPO) / "docs/verifiers-export.md").read_text(encoding="utf-8").split())
    assert "`[success ]` is verifiers' word for an episode that ended without an error" in text
    assert "an episode that scored 0.00 is a `[success ]` too" in text
    assert "counts each conversation once" in text
    assert "`traces.jsonl`" in text and "`calls`" in text and "`usage`" in text
    assert "`poisson-tasks run`" in text


def test_fx30_5_the_installed_verifiers_does_what_the_note_says() -> None:
    """A guard, green by construction: the note describes verifiers 0.3.1's display, which this
    package pins.  If the pin moves to a verifiers that labels or counts otherwise, this fails
    and the note is read again."""
    from verifiers.v1 import trace
    from verifiers.v1.cli.dashboard import eval as dashboard

    assert '"error" if t.has_error else "success"' in inspect.getsource(dashboard)
    assert "counted once" in (trace.Trace.num_input_tokens.__doc__ or "") or "counted once" in (
        inspect.getsource(trace))
