"""`init`, the guided setup, frozen as tests.

The invariant is FD5.8 of the front door's plan (spec §4.1, §6.1, §6.2, §6.3 and §7.3), with what
the recipes' module (R0) carried to it.  The question order in a pseudo-terminal, the tokenizer
question coming first and `init` without the tokenizer are in `tests/test_fd5_fresh.py`.
- **FD5.8** under `--yes` init never reads stdin, and on stdin that is not a terminal without
  `--yes` it refuses before the first question; it refuses an existing file without `--force`
  and changes no byte of it; Ctrl-C at any question writes nothing; the equivalent command it
  prints writes the same file, byte for byte; no byte of a key is written or printed.
- **The file is the library's** (spec P-2): the bytes `dump_config(config_from_init_args(flags,
  expected_dollars=…))` give, the spend cap's default made from the plan's estimate when a price
  is set and no cap is given (spec §6.1, ruled 2026-10-02).
- **The key** (spec §4.1, §7.3): missing or refused at init's check is not a refusal: the file is
  written and the key's line is the library's.  `--no-check-key` opens no socket; under `--yes`
  the key is checked with one free request.
- **Recipes** (R0, spec Knobs §17.4): `--recipe` sets question 6 and `--measure` is its alias; a
  recipe not offered is refused in one line naming the recipe and the knobs it waits on (every
  recipe but `first-look` and `card` before the knob probe; `tool-choice` and
  `reading-and-filling` since it shipped faults, history and shape on 2026-10-14); `custom`
  offers depth and the distractor dial and no other knob.  Whether the command opens `custom` further is not this module's to decide: today's
  behaviour is pinned.
- **The questions** (spec §6.1): with the defaults taken, choosing the published design at
  question 6 asks two questions fewer than the first look, and choosing the knob and levels
  yourself asks four more.

Shapes decided here
-------------------

**1. The dialogue is read a line at a time from stdin and asked on stderr**, so `init > file` in a
terminal leaves the file holding only the result (spec §4.1: the dialogue goes to stderr).  A
question answered with Enter takes its default.  Answers to a menu are its numbers.

**2. Ctrl-C at a question ends the command with exit 130** and a `stopped` verdict line on
stdout, and leaves the folder as it was (spec §4.1's error list).
"""

from __future__ import annotations

import os
import shlex
from pathlib import Path
from typing import Any

import pytest

from tests.fd2_fakes import KEY_BODY, SENTINEL
from tests.fd5_support import (
    INTERRUPT,
    Answers,
    NoStdin,
    World,
    arms,
    config,
    error_lines,
    invoke,
    leaked,
    next_commands,
    printed_command,
    prog,
    providers,
    runs,
    strip_prog,
    tree,
    world,
)
from tests.fixtures.model_server import FixtureModel

__all__ = ["prog", "world"]

QUIET = ["--yes", "--no-fetch", "--no-check-key"]


def library_file(flags: list[str]) -> str:
    """The file the library writes for `init`'s flags, the default cap from the estimate."""
    made = config().config_from_init_args(flags)
    if made.model.price is not None and "--spend-cap" not in flags:
        estimate = runs().estimate(config().resolve_plan(made))
        made = config().config_from_init_args(flags, expected_dollars=estimate.dollars_expected)
    text: str = config().dump_config(made)
    return text


# ---------------------------------------------------------------------------
# stdin
# ---------------------------------------------------------------------------


def test_fd5_8_under_yes_init_never_reads_stdin(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    for stdin in (NoStdin(), _TerminalThatMustNotBeRead()):
        ran = invoke(["init", "--yes", "--no-check-key"], prog=prog, monkeypatch=monkeypatch,
                     stdin=stdin)
        assert ran.code == 0, ran
        (world.work / "tasks.toml").unlink()


class _TerminalThatMustNotBeRead(NoStdin):
    def isatty(self) -> bool:
        return True


def test_fd5_8_on_a_pipe_without_yes_init_refuses_before_the_first_question(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran = invoke(["init"], prog=prog, monkeypatch=monkeypatch, stdin=NoStdin())
    assert ran.code == 1, ran
    assert tree(world.work) == {}
    lines = error_lines(ran)
    assert len(lines) == 1 and f"{prog} init --help" in lines[0], ran
    assert ran.err_lines[0] == lines[0], "the refusal is the first thing said"


# ---------------------------------------------------------------------------
# an existing file
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("where", ["tasks.toml", "sub/other.toml"])
def test_fd5_8_an_existing_file_is_refused_unchanged_and_replaced_with_force(
    where: str, prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = world.work / where
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"# mine\nversion = 1\n")
    given = [] if where == "tasks.toml" else ["--config", where]
    ran = invoke(["init", *QUIET, *given], prog=prog, monkeypatch=monkeypatch)
    assert ran.code == 1, ran
    assert path.read_bytes() == b"# mine\nversion = 1\n"
    assert sorted(p.name for p in path.parent.iterdir()) == [path.name]
    assert len(error_lines(ran)) == 1 and where in error_lines(ran)[0], ran
    commands = [shlex.split(command) for command in next_commands(ran.err + ran.out)]
    words = shlex.split(prog)
    assert any(command[: len(words) + 1] == [*words, "init"] and "--force" in command
               for command in commands), ran
    replaced = invoke(["init", *QUIET, *given, "--force"], prog=prog, monkeypatch=monkeypatch)
    assert replaced.code == 0, replaced
    assert path.read_text(encoding="utf-8") == library_file([])


# ---------------------------------------------------------------------------
# Ctrl-C at any question
# ---------------------------------------------------------------------------


def _entries() -> dict[str, str]:
    """Question 6's entries, numbered from 1: the offered recipes in `arms.RECIPES`' order, then
    choosing the knob yourself.  Retrofitted 2026-10-14 (O2 Session A's yes/no 32): the first-look,
    card and custom answers were "1", "2" and "3", the three entries of the menu before own tools
    took the place after the recipes and the knob probe shipped faults, history and shape.
    Retrofitted 2026-10-20 by ruling G7 (FD9 Session A): your own tools is the first question's
    second answer, so it left this menu and custom is the entry after the recipes."""
    offered = [name for name, recipe in arms().RECIPES.items() if recipe.offered]
    return {"first-look": str(offered.index("first-look") + 1),
            "card": str(offered.index("card") + 1), "custom": str(len(offered) + 1)}


@pytest.mark.parametrize("measure", list(_entries().values()), ids=list(_entries()))
def test_fd5_8_ctrl_c_at_any_question_writes_nothing(
    measure: str, prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Enter at every question but the measure menu, which takes `measure`; Ctrl-C at the k-th,
    for every k until the dialogue ends.  Retrofitted by ruling G7 (FD9 Session A): the first
    question, built-in tasks or your own tools, is answered first, with Enter."""
    asked = None
    for k in range(40):
        answers: list[Any] = ["", "", "", "", "", measure, "", "", "", "", "", "", "", ""]
        answers = answers[:k] + [INTERRUPT]
        stdin = Answers(answers)
        ran = invoke(["init", "--no-check-key"], prog=prog, monkeypatch=monkeypatch, stdin=stdin)
        if stdin.reads <= k:
            assert ran.code == 0, ran
            asked = stdin.reads
            break
        assert ran.code == 130, ran
        assert tree(world.work) == {}, f"Ctrl-C at question {k + 1} left {tree(world.work)}"
        assert ran.word == "stopped", ran
    assert asked is not None and asked >= 7, asked
    assert (world.work / "tasks.toml").is_file()


def test_fd5_8_the_published_design_asks_two_fewer_questions_and_custom_four_more(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spec §6.1: question 6's second answer skips the tasks and the attempts; its third asks
    the knob, the levels, the control arms and the strictness.  Retrofitted by ruling G7 (FD9
    Session A): the first question is answered first, with Enter."""
    counts = {}
    for measure in _entries().values():
        stdin = Answers(["", "", "", "", "", measure])
        ran = invoke(["init", "--no-check-key"], prog=prog, monkeypatch=monkeypatch,
                     stdin=stdin)
        assert ran.code == 0, ran
        made = config().load_config(world.work / "tasks.toml")
        counts[made.measure.preset] = stdin.reads
        (world.work / "tasks.toml").unlink()
    assert set(counts) == {"first-look", "card", "custom"}, counts
    assert counts["card"] == counts["first-look"] - 2, counts
    assert counts["custom"] == counts["first-look"] + 4, counts


BRANCHES = {
    # provider's answer, the answers after it, init's flags for the same file; retrofitted by
    # ruling G7 (FD9 Session A): the first question, answered with Enter, comes before them
    "ollama": (["", "3"], ["--provider", "ollama"]),
    "vllm": (["", "4", "served-model"], ["--provider", "vllm", "--model", "served-model"]),
    "a-model-with-no-published-price": (["", "1", "gpt-other"], ["--model", "gpt-other"]),
}


@pytest.mark.parametrize("branch", list(BRANCHES))
def test_fd5_8_each_providers_questions_are_spec_6_1s(
    branch: str, prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ruled 2026-10-02: the endpoint is asked only for vLLM and another endpoint; no price is
    asked for Ollama and vLLM; a blank price moves the cap to tokens.  So, against OpenAI's eight
    questions with Enter at each: Ollama asks one fewer (no price), vLLM as many (the endpoint,
    and no price), and a model with no published price writes a file with no price and the
    token cap's default."""
    default = Answers([])
    assert invoke(["init", "--no-check-key"], prog=prog, monkeypatch=monkeypatch,
                  stdin=default).code == 0
    (world.work / "tasks.toml").unlink()
    answers, flags = BRANCHES[branch]
    stdin = Answers(answers)
    ran = invoke(["init", "--no-check-key"], prog=prog, monkeypatch=monkeypatch, stdin=stdin)
    assert ran.code == 0, ran
    assert (world.work / "tasks.toml").read_text(encoding="utf-8") == library_file(flags)
    expected = {"ollama": default.reads - 1, "vllm": default.reads,
                "a-model-with-no-published-price": default.reads}[branch]
    assert stdin.reads == expected, (stdin.reads, default.reads)


def test_fd5_8_enter_through_every_question_writes_the_first_run_of_spec_6_1(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pressing Enter at every question gives the defaults of `init --yes`: one file."""
    ran = invoke(["init", "--no-check-key"], prog=prog, monkeypatch=monkeypatch,
                 stdin=Answers([]))
    assert ran.code == 0, ran
    assert (world.work / "tasks.toml").read_text(encoding="utf-8") == library_file([])


# ---------------------------------------------------------------------------
# the equivalent command, and the file
# ---------------------------------------------------------------------------

SETUPS = {
    "defaults": [],
    "card": ["--recipe", "card"],
    "a-measure-alias": ["--measure", "card"],
    "ollama": ["--provider", "ollama"],
    "vllm": ["--provider", "vllm", "--model", "my-model", "--base-url",
             "http://127.0.0.1:8000/v1"],
    "anthropic": ["--provider", "anthropic", "--model", "claude-test",
                  "--price", "1,0.1,5", "--price-read-on", "2026-10-01"],
    "another-endpoint": ["--provider", "openai-compatible", "--model", "m", "--base-url",
                         "https://gateway.example/v1", "--api-key-env", "GATEWAY_API_KEY",
                         "--no-price"],
    "custom": ["--recipe", "custom", "--knob", "distractor", "--levels", "0,2,8,14",
               "--controls", "--strictness", "leaky", "--tasks-per-level", "3",
               "--attempts", "2"],
    "seeds-and-limits": ["--seeds", "404,55,2121", "--spend-cap", "2.5",
                         "--max-model-calls", "20", "--concurrency", "3", "--runs-dir", "out",
                         "--tasks-dir", "made"],
    "not-sent-and-version": ["--top-p", "not sent", "--max-tokens", "not sent",
                             "--reasoning-effort", "not sent", "--generator-version", "0",
                             "--temperature", "0.7"],
    "tokens-only": ["--no-price", "--token-cap", "500000"],
}


@pytest.mark.parametrize("flags", list(SETUPS.values()), ids=list(SETUPS))
def test_fd5_8_the_file_is_the_librarys_and_the_equivalent_command_writes_it_again(
    flags: list[str], prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran = invoke(["init", *QUIET, *flags], prog=prog, monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    first = (world.work / "tasks.toml").read_bytes()
    library = [word for word in flags]
    if "--measure" in library:
        library[library.index("--measure")] = "--recipe"
    assert first.decode("utf-8") == library_file(library)
    command = printed_command(ran.out, prog, "init")
    assert command is not None, ran
    assert command == config().equivalent_init_command(
        config().load_config(world.work / "tasks.toml"), prog=prog)
    elsewhere = world.work / "again"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    monkeypatch.setenv("OPENAI_BASE_URL", "https://proxy.example/v1")
    again = invoke(strip_prog(command, prog) + ["--no-fetch", "--no-check-key"], prog=prog,
                   monkeypatch=monkeypatch)
    assert again.code == 0, again
    assert (elsewhere / "tasks.toml").read_bytes() == first


def test_fd5_8_the_next_step_is_the_run(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran = invoke(["init", *QUIET], prog=prog, monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    assert next_commands(ran.out)[-1:] == [f"{prog} run"], ran


# ---------------------------------------------------------------------------
# the key
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("model", ["gpt-5-nano-2025-08-07", "fixture-401"],
                         ids=["accepted", "refused"])
def test_fd5_8_no_byte_of_the_key_is_written_or_printed(
    model: str, prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The fixture's refusal quotes the key back whole and masked; the key's line is the
    library's own, and no four characters of the key in a row are anywhere init wrote."""
    with FixtureModel() as fixture:
        monkeypatch.setenv("OPENAI_BASE_URL", fixture.base_url)
        monkeypatch.setenv("OPENAI_API_KEY", SENTINEL)
        ran = invoke(["init", "--yes", "--no-fetch", "--model", model], prog=prog,
                     monkeypatch=monkeypatch)
        assert ran.code == 0, ran
        made = config().load_config(world.work / "tasks.toml")
        found = providers().check_key(made.model)
        assert not fixture.posts()
    assert found.status == (providers().ACCEPTED if model != "fixture-401"
                            else providers().REFUSED)
    assert found.detail in ran.out, ran
    written = "".join((path.read_bytes().decode("utf-8", "replace"))
                      for root in (world.work, world.home, world.tmp)
                      for path in root.rglob("*") if path.is_file())
    assert leaked(ran.out + ran.err + written, KEY_BODY) == []


def test_fd5_8_a_key_that_is_not_set_is_no_refusal(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran = invoke(["init", "--yes", "--no-fetch"], prog=prog, monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    assert (world.work / "tasks.toml").read_text(encoding="utf-8") == library_file([])
    assert ran.events == ()
    found = providers().check_key(config().load_config(world.work / "tasks.toml").model)
    assert found.status == providers().NOT_SET
    assert found.detail in ran.out, ran


def test_fd5_8_no_check_key_opens_no_socket_and_yes_checks_once(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    with FixtureModel() as fixture:
        monkeypatch.setenv("OPENAI_BASE_URL", fixture.base_url)
        monkeypatch.setenv("OPENAI_API_KEY", SENTINEL)
        quiet = invoke(["init", "--yes", "--no-fetch", "--no-check-key"], prog=prog,
                       monkeypatch=monkeypatch)
        assert quiet.code == 0, quiet
        assert quiet.events == () and fixture.requests == []
        checked = invoke(["init", "--yes", "--no-fetch", "--force"], prog=prog,
                         monkeypatch=monkeypatch)
        assert checked.code == 0, checked
        assert [seen.method for seen in fixture.requests] == ["GET"]


def test_fd5_8_the_dialogue_asks_before_the_key_check_and_takes_no(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the key set, question 4 asks whether to check it (spec §6.1); answered no, nothing
    is sent."""
    with FixtureModel() as fixture:
        monkeypatch.setenv("OPENAI_BASE_URL", fixture.base_url)
        monkeypatch.setenv("OPENAI_API_KEY", SENTINEL)
        unset = Answers([])
        monkeypatch.delenv("OPENAI_API_KEY")
        invoke(["init"], prog=prog, monkeypatch=monkeypatch, stdin=unset)
        (world.work / "tasks.toml").unlink()
        monkeypatch.setenv("OPENAI_API_KEY", SENTINEL)
        answers = ["", "", "", "", "n"]  # G7: the first question first (FD9 Session A)
        stdin = Answers(answers)
        ran = invoke(["init"], prog=prog, monkeypatch=monkeypatch, stdin=stdin)
        assert ran.code == 0, ran
        assert stdin.reads == unset.reads + 1
        assert fixture.requests == []


# ---------------------------------------------------------------------------
# recipes (R0)
# ---------------------------------------------------------------------------


def not_offered() -> list[str]:
    return [name for name, recipe in arms().RECIPES.items() if not recipe.offered]


def test_fd5_8_a_recipe_not_offered_is_refused_in_one_line_naming_what_it_waits_on(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    for recipe in not_offered():
        with pytest.raises(config().ConfigError) as refused:
            config().config_from_init_args(["--recipe", recipe])
        for flag in ("--recipe", "--measure"):
            ran = invoke(["init", *QUIET, flag, recipe], prog=prog, monkeypatch=monkeypatch)
            assert ran.code == 2, ran
            assert error_lines(ran) == [f"error: {refused.value}"], ran
            for knob in arms().RECIPES[recipe].waiting:
                assert knob in error_lines(ran)[0], (recipe, knob)
            assert tree(world.work) == {}


@pytest.mark.parametrize("knob", ["depth", "distractor", "similarity", "faults", "history",
                                  "block", "arguments", "shape", "spread"])
def test_fd5_8_custom_offers_depth_and_the_distractor_dial_and_no_other_knob(
    knob: str, prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran = invoke(["init", *QUIET, "--recipe", "custom", "--knob", knob], prog=prog,
                 monkeypatch=monkeypatch)
    if knob in ("depth", "distractor"):
        assert ran.code == 0, ran
        assert config().load_config(world.work / "tasks.toml").measure.knob == knob
    else:
        assert ran.code == 2, ran
        assert len(error_lines(ran)) == 1 and knob in error_lines(ran)[0], ran
        assert tree(world.work) == {}


def test_fd5_8_init_writes_where_config_says(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    os.makedirs(world.work / "sub")
    ran = invoke(["init", *QUIET, "--config", "sub/mine.toml"], prog=prog,
                 monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    assert sorted(str(p.relative_to(world.work)) for p in world.work.rglob("*")) == [
        "sub", str(Path("sub/mine.toml"))]
    assert (world.work / "sub" / "mine.toml").read_text(encoding="utf-8") == library_file([])
