"""#34, reading a card: "Read the card" opens the card that is there; it does not build it again.

The guided session's step "Read the card", the word `card` and the `runs` view each ran
`card --force` on a run whose card was built, which rebuilds the card from the run's records and
writes its four files again.  Reading wrote to the run folder, and a card made by another build
of the package was replaced by this one's.  The step is now a view, like `more` and `replies`:
the session draws the card's own `card/card.md` and runs no verb, so it prints no `same as`
command and writes nothing.

A built card is read as it stands only when it is the card of the run as the run stands.  A card
built from part of a run (the run was stopped, a card was made from what ran, the run was then
finished) is not that run's card any more, and for it the step is the build, as it always was.
A run's card is the current one when its `episodes.jsonl` holds as many records as the run has
kept episodes (`RunFacts.card_current`).

What each test holds:

- the session reads a built card: the card is on the screen, no verb ran, and no file of the run
  folder was written or touched (contents and modification times of every file);
- Enter at the home screen, `card 1` and the word `card` all read it;
- a card that is not the run's current one is built again, as before: the control for the rule
  above;
- a run with no card is built by `card`, as before: a control;
- reading opens no socket and calls no model;
- the facts: `RunFacts.card_current` is true for a card of the run as it stands and false once
  the run has an episode the card has not, and the first step of a built card is a view while
  the first step of a stale one is the build;
- off a terminal, the folder's first step is still the `card` verb: a view has no command, and
  the bare command's `next:` line is held by `test_fd9_session` to name one.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.fd5_support import World, world
from tests.fd9_support import (
    Keys,
    Session,
    States,
    folder_module,
    in_session,
    run_folder,
    states,
)
from tests.test_fd9_session import answering, flat, here

__all__ = ["states", "world"]

CARD_TEXT = "What each difficulty level is worth"
"""The first heading of every card's own document."""


def _snapshot(folder: Path) -> dict[str, tuple[bytes, int]]:
    """Every file under `folder`: its bytes and its modification time in nanoseconds."""
    return {
        str(path.relative_to(folder)): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in sorted(folder.rglob("*")) if path.is_file()
    }


def _state_d(states: States, world: World) -> tuple[Path, Path]:
    work = here(states, "D", world)
    return work, run_folder(work)


def _make_stale(folder: Path) -> None:
    """The card of a run that has gone on since: one record fewer than the run has kept."""
    path = folder / "card" / "episodes.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    assert len(lines) >= 2, lines
    path.write_text("".join(lines[:-1]), encoding="utf-8")


def _read_in_the_session(words: list[str], states: States, work: Path,
                         monkeypatch: pytest.MonkeyPatch, *, menus: list[str] | None = None
                         ) -> Session:
    monkeypatch.chdir(work)
    return in_session(Keys(words, answer=answering(menus=menus)), monkeypatch)


@pytest.mark.parametrize("words", [["card", "quit"], ["card 1", "quit"], ["", "quit"]],
                         ids=["the word card", "card 1", "Enter, step 1"])
def test_fx34_10_reading_a_built_card_shows_it_and_writes_nothing(
    words: list[str], states: States, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Red before the change: a verb runs (`same as  poisson-tasks card --force`) and the four
    files of the card are written again."""
    work, folder = _state_d(states, world)
    assert folder_module().read_folder(work / "tasks.toml").runs[0].card == "built"
    before = _snapshot(folder)
    session = _read_in_the_session(words, states, work, monkeypatch)
    assert session.code == 0, session
    assert not session.same_as(), f"a verb ran\n{session}"
    assert CARD_TEXT in flat(session.out), session
    assert "What it does not claim" in flat(session.out), session
    assert _snapshot(folder) == before, "reading the card wrote to the run folder"


def test_fx34_11_reading_a_built_card_opens_no_socket_and_calls_no_model(
    states: States, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The view reads a file.  Red before the change only through test 10's own check; this one
    holds the cost: nothing left the machine and the fixture model saw no request."""
    work, _ = _state_d(states, world)
    seen = len(states.model.requests)
    session = _read_in_the_session(["card", "quit"], states, work, monkeypatch)
    assert session.connections == [], session
    assert len(states.model.requests) == seen


def test_fx34_12_a_card_the_run_has_moved_on_from_is_built_again(
    states: States, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control for the rule that a built card is read only when it is the run's current one:
    green before the change and after.  One record of the card is gone, as if the run had kept
    an episode since; the word `card` then builds it again, with `--force`, and the card is whole
    once more."""
    work, folder = _state_d(states, world)
    whole = (folder / "card" / "episodes.jsonl").read_bytes()
    _make_stale(folder)
    assert (folder / "card" / "episodes.jsonl").read_bytes() != whole
    session = _read_in_the_session(["card", "quit"], states, work, monkeypatch)
    commands = session.same_as()
    assert commands and commands[0][1] == "card" and "--force" in commands[0], session
    assert (folder / "card" / "episodes.jsonl").read_bytes() == whole


def test_fx34_13_a_run_with_no_card_has_it_built_by_the_word_card(
    states: States, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A control: green before the change and after.  Nothing to read, so `card` is the build,
    with no `--force`."""
    work = here(states, "D-nocard", world)
    assert not (run_folder(work) / "card" / "artifact.json").exists()
    session = _read_in_the_session(["card", "quit"], states, work, monkeypatch)
    commands = session.same_as()
    assert commands and commands[0][1] == "card" and "--force" not in commands[0], session
    assert (run_folder(work) / "card" / "artifact.json").is_file()


def test_fx34_14_card_current_is_true_for_the_runs_card_and_false_once_the_run_has_gone_on(
    states: States, world: World
) -> None:
    """The fact the view depends on, read from disk alone.  Red before the change: `RunFacts` has
    no such field."""
    work, folder = _state_d(states, world)
    (run,) = folder_module().read_folder(work / "tasks.toml").runs
    assert run.card == "built" and run.card_current is True
    _make_stale(folder)
    (run,) = folder_module().read_folder(work / "tasks.toml").runs
    assert run.card == "built" and run.card_current is False


def test_fx34_15_step_one_of_a_built_card_is_a_view_and_of_a_stale_one_the_build(
    states: States, world: World
) -> None:
    """The home screen's first step.  Red before the change: it is `card --force` for both."""
    from poisson_tasks.cli._session import steps_for

    work, folder = _state_d(states, world)
    first = steps_for(folder_module().read_folder(work / "tasks.toml"))[0]
    assert (first.label, first.word, first.argv) == ("Read the card", "card", None)
    _make_stale(folder)
    first = steps_for(folder_module().read_folder(work / "tasks.toml"))[0]
    assert first.word == "card" and first.argv is not None and "--force" in first.argv
    assert first.label != "Read the card", first


def test_fx34_16_the_bare_command_off_a_terminal_still_names_the_card_verb_as_the_next_step(
    states: States, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A control: green before the change.  A view has no command, and the bare command's
    `next:` line must still be one the folder's first step gives (`test_fd9_session`)."""
    from poisson_tasks.cli._session import first_step_command

    work, _ = _state_d(states, world)
    monkeypatch.chdir(work)

    class Args:
        config = None

    command = first_step_command("poisson-tasks", Args())
    assert command is not None and command.split()[:2] == ["poisson-tasks", "card"], command


def test_fx34_17_the_run_view_reads_a_built_card_too(
    states: States, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`runs` ends by handing the run picked to the word `card`, which builds a card again
    before the change and reads it after.  Red before the change."""
    work, folder = _state_d(states, world)
    before = _snapshot(folder)
    session = _read_in_the_session(["runs", "quit"], states, work, monkeypatch, menus=["1"])
    assert CARD_TEXT in flat(session.out), session
    assert not session.same_as(), f"a verb ran\n{session}"
    assert _snapshot(folder) == before


def test_fx34_18_the_card_read_is_the_card_on_disk(
    states: States, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What is drawn is the file, so a card another build wrote is shown as that build wrote it:
    a sentence added to the file's last section appears on the screen, and the file is as it was
    left.  Red before the change: the card is built again and the sentence is gone."""
    work, folder = _state_d(states, world)
    path = folder / "card" / "card.md"
    marked = path.read_text(encoding="utf-8") + "\nA sentence only the file on disk has.\n"
    path.write_text(marked, encoding="utf-8")
    session = _read_in_the_session(["card", "quit"], states, work, monkeypatch)
    assert "A sentence only the file on disk has." in flat(session.out), session
    assert path.read_text(encoding="utf-8") == marked
