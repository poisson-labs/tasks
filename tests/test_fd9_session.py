"""The guided session (spec §16, the plan's FD9), frozen as tests before it is built.

A bare `poisson-tasks` on a terminal opens a session that stays open: a load screen with the
ruled banner, then the run-through with no `tasks.toml`, else the home screen, which reads the
folder from disk and offers short steps.  Every action is one of the seven verbs' command lines,
run through the same parser and verb function as `main`, and shown with its `same as` command.
Nothing calls a model before a yes at `run`'s own question.  Off a terminal there is no session.

Each test names the invariant of spec §16.14 it pins, and the reason it is red before the build.
The ways of driving the session, the fixture states and what every expectation is computed from
are in `tests/fd9_support.py`.

Numbers in the status block are matched as the look already prints them (`cli._format`, FD5's,
not changed here): a rate with three decimals, dollars as `_format.dollars`.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from rich.cells import cell_len

from tests.fd3_support import KEY, KEY_VAR, harness_env, needs_uv
from tests.fd5_support import World, fresh, invoke, plan_of, tree, world, write_config
from tests.fd9_support import (
    BLOCKS,
    EOF,
    INTERRUPT,
    MARK,
    PETSTORE,
    PROG,
    SESSION_MODULES,
    STEP_COMMAND,
    STEP_ONE,
    WORDS,
    Asked,
    Keys,
    States,
    Through,
    banner_styles,
    banner_text,
    folder_module,
    hold_lock,
    home_blocks,
    in_session,
    kept_hashes,
    ledger_lines,
    pick,
    pretty_env,
    pty_session,
    run_folder,
    states,
    steps_of,
    stripped,
    styled,
    version,
)
from tests.test_fd5_run import over_estimate_design, under_the_cap

__all__ = ["harness_env", "states", "world"]

VERB_OF = {"run": "run", "again": "run", "card": "card", "task": "generate", "verify": "verify",
           "export": "export", "check": "doctor", "setup": "init", "flow": "init"}
"""The verb each action word runs (spec §16.2)."""

RUNTHROUGH_STEPS = ("Set up", "One task", "The run", "The card", "What next")
ONE_LINE = "Poisson Labs  tasks {}"
"""The banner's one line, ruled 2026-10-20 (P1): the ruled pick's own words."""
RAW = re.compile(r"^\s*(\||#|---)")
"""A line of raw Markdown: a table row, a heading or a rule (FD9.14)."""


def answering(*, start: str = "n", first: str | None = None,
              interrupt: str | None = None, flow: bool = False,
              menus: list[str] | None = None) -> Any:
    """A policy for the questions: `run`'s `Start?` gets `start`; every other yes/no gets no (no
    key check, no fetch: nothing leaves the machine unasked); `init`'s first menu gets the option
    matching `first` when given; with `interrupt`, every question that module asks gets Ctrl-C;
    the session's own menus get, in turn, the flow addPet.id into getPetById.petId (Petstore)
    with `flow`, then the numbers in `menus`, then Ctrl-C, which leaves a menu (spec §16.7);
    everything else is Enter."""
    seen = {"_init": 0, "_session": 0}
    flow_picks = [r"^addPet\b", r"^id\b", r"^getPetById\b", r"^petId\b"] if flow else []
    numbers = list(menus or ())

    def answer(asked: Asked) -> Any:
        if interrupt is not None and asked.module == interrupt:
            return INTERRUPT
        if asked.kind == "confirm":
            return start if asked.module == "_run" else "n"
        if asked.kind == "choice" and asked.module == "_init":
            seen["_init"] += 1
            if seen["_init"] == 1 and first is not None:
                return pick(first)
        if asked.module == "_session":
            if flow_picks:
                return pick(flow_picks.pop(0))
            if numbers:
                return numbers.pop(0)
            return INTERRUPT
        return None

    return answer


def flat(text: str) -> str:
    """`text` with its whitespace runs made one space: a terminal's wrapping undone."""
    return " ".join(text.split())


OPENING: dict[str, list[Any]] = {"A": [INTERRUPT]}
"""What reaches the home screen first: with no settings file the session opens on the
run-through, and a Ctrl-C at its first prompt ends it on the home screen (spec §16.4)."""


def here(states: States, name: str, world: World) -> Path:
    """State `name` copied into the test's working folder."""
    return states.copy(name, world.work)


def first_home(session: Any) -> list[str]:
    blocks = home_blocks(session.out)
    assert blocks, f"no home screen\n{session}"
    return blocks[0]


def keyed(monkeypatch: pytest.MonkeyPatch, states: States) -> None:
    """The OpenAI preset pointed at the fixture model, with a made-up key: what the run-through's
    defaults then set up runs against the fixture."""
    monkeypatch.setenv("OPENAI_BASE_URL", states.model.base_url)
    monkeypatch.setenv("OPENAI_API_KEY", KEY)


# ---------------------------------------------------------------------------
# FD9.1 entry
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("how", ["stdout piped", "stdin piped", "CI", "--json"])
def test_fd9_1_off_a_terminal_a_bare_command_exits_2_naming_the_session_and_the_first_step(
    how: str, states: States, world: World
) -> None:
    """G5.  Red before the build: the line names `--help`, not the session, and has no `next:`."""
    _off_a_terminal(how, "B", states, world)


@pytest.mark.parametrize("state", ["A", "D"])
def test_fd9_1_off_a_terminal_the_next_line_is_that_folders_first_step(
    state: str, states: States, world: World
) -> None:
    """G5, in two more states.  Red before the build: there is no `next:` line."""
    _off_a_terminal("stdout piped", state, states, world)


def _off_a_terminal(how: str, state: str, states: States, world: World) -> None:
    work = here(states, state, world)
    env = pretty_env(world, **({"CI": "1"} if how == "CI" else {}))
    argv = ["--json"] if how == "--json" else []
    with pty_session(argv, env=env, cwd=work, stdout_tty=how != "stdout piped",
                     stdin_tty=how != "stdin piped") as session:
        code = session.wait()
        said = session.plain
        out = session.piped.get("out", b"").decode()
    assert code == 2, said
    assert MARK not in said
    lines = [line for line in said.splitlines() if line.strip()]
    errors = [i for i, line in enumerate(lines) if line.startswith("error: ")]
    assert len(errors) == 1, said
    text = lines[errors[0]]
    for line in lines[errors[0] + 1:]:
        if not line.startswith("  ") or line.strip().startswith("next:"):
            break
        text += " " + line.strip()
    for verb in ("init", "generate", "run", "card", "verify", "export", "doctor"):
        assert re.search(rf"\b{verb}\b", text), (verb, text)
    assert "session" in text, text
    nexts = [line.strip()[len("next:"):].strip() for line in lines if
             line.strip().startswith("next:")]
    assert len(nexts) == 1 and nexts[0].split()[:2] == [PROG, *STEP_COMMAND[STEP_ONE[state]]], said
    if how in ("stdout piped", "--json"):
        assert out == "", out


def test_fd9_1_a_verb_on_three_terminals_never_opens_the_session(
    states: States, world: World
) -> None:
    """Green before the build, by construction (no session exists): it holds the build to the
    entry rule's last line, that a verb is exactly as today."""
    work = here(states, "B", world)
    with pty_session(["doctor", "--offline"], env=pretty_env(world), cwd=work) as session:
        code = session.wait()
    assert code in (0, 4), session.plain
    assert MARK not in session.plain
    said = [line for line in session.plain.splitlines() if line.strip()
            and not line.startswith(("note:", "  "))]
    assert said and re.match(r"^(ok|not ready)  ", said[0]), session.plain


# ---------------------------------------------------------------------------
# FD9.2 isolation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("argv", [["--help"], ["--version"], ["run", "--help"],
                                  ["doctor", "--offline"]], ids=" ".join)
def test_fd9_2_a_verb_or_help_does_not_import_the_session(
    argv: list[str], world: World
) -> None:
    """Green before the build, by construction (the modules do not exist yet)."""
    ran = fresh(argv, prog=PROG, world=world)
    assert ran.code in (0, 4), ran
    imported = set(ran.record.get("modules", ()))
    assert imported, ran
    assert not imported & set(SESSION_MODULES), sorted(imported & set(SESSION_MODULES))


# ---------------------------------------------------------------------------
# FD9.3 the first screen
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("state", ["A", "B"])
def test_fd9_3_the_first_screen_is_the_run_through_without_settings_else_the_home_screen(
    state: str, states: States, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Red before the build: no session opens."""
    here(states, state, world)
    session = in_session(Keys(["quit"], answer=answering()), monkeypatch)
    first = stripped(session.log.screens()[0])
    assert session.keys.prompts >= 1, session
    homes = [line for line in first.splitlines() if re.match(r"^(folder|next)\s*", line)]
    if state == "A":
        assert not homes, first
        for name in RUNTHROUGH_STEPS:
            assert name in first, (name, first)
    else:
        assert len(homes) >= 2 and "Step 1 of 5" not in first, first


# ---------------------------------------------------------------------------
# FD9.4 no model call before the yes
# ---------------------------------------------------------------------------


def test_fd9_4_the_run_through_to_start_and_every_word_but_run_and_again_calls_no_model(
    states: States, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The run-through's setup with every default (the OpenAI preset at the fixture model; its
    key check declined), then one task, then the run's plan, answered no; then every home word but
    `run` and `again`, `check` taken offline.  One request in all: the free key check `run` names
    before its plan (a GET).  No completion, nothing off the machine.  Red before the build: no
    session opens, so `Start?` is never asked."""
    here(states, "A", world)
    shutil.copy(PETSTORE, world.work / "petstore.json")
    keyed(monkeypatch, states)
    before = len(states.model.requests)
    words = [w for w in WORDS if w not in ("run", "again", "quit")]
    session = in_session(Keys([Through("n"), *words, "quit"], answer=answering()), monkeypatch)
    assert session.keys.started, session
    assert session.code == 0, session
    sent = [seen.method for seen in states.model.requests[before:]]
    assert sent == ["GET"], f"only the run's own free key check, before its plan: {sent}"
    ports = {address[1] for address in session.connections if isinstance(address, tuple)}
    assert ports <= {states.model.port}, ports


@needs_uv
def test_the_run_through_takes_its_five_steps_in_order_and_ends_on_the_home_screen_with_a_card(
    harness_env: Path, states: States, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spec §16.4, binding: set up, one task, the run (yes), the card, then what next: the home
    screen of a finished run with its card, whose step 1 is `card`; and no line of it is raw
    Markdown (FD9.14).  Red before the build: no session opens."""
    here(states, "A", world)
    keyed(monkeypatch, states)
    session = in_session(Keys([Through("y"), "quit"], answer=answering()), monkeypatch)
    assert session.keys.started, session
    assert [argv[1] for argv in session.same_as()][:4] == ["init", "generate", "run", "card"], (
        session.same_as())
    heads = re.findall(r"^Step (\d) of 5", stripped(session.text), re.MULTILINE)
    assert heads == ["1", "2", "3", "4", "5"], heads
    assert (run_folder(world.work) / "card" / "artifact.json").is_file()
    blocks = home_blocks(session.out)
    assert blocks and steps_of(blocks[-1])[0] == "card", session
    raw = [line for line in stripped(session.text).splitlines() if RAW.match(line)]
    assert not raw, raw


# ---------------------------------------------------------------------------
# FD9.5 and FD9.6 one implementation, and the same-as command
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("state,word,config,prog", [
    ("D-nocard", "card", None, "poisson-tasks"), ("B", "task", None, "poisson-tasks"),
    ("D", "export", None, "poisson-tasks"), ("B", "setup", None, "poisson-tasks"),
    ("D-refused", "card", None, "poisson-tasks"), ("D-nocard", "card", "sub/tasks.toml",
                                                  "poisson-tasks"),
    ("D-nocard", "card", None, "poisson tasks")])
def test_fd9_5_6_an_actions_files_are_its_same_as_commands_and_so_is_its_exit(
    state: str, word: str, config: str | None, prog: str, states: States, world: World,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """In the session and from a shell in a copy of the folder, the same files, byte for byte, and
    the same verdict; the command exits with the verb's code for that result (a refused card, 1).
    With `--config`, the session reads that settings file and its commands carry it.  Red before
    the build: there is no session, so no `same as` line."""
    if config is None:
        work = here(states, state, world)
        copy = states.copy(state, world.tmp / "copy")
    else:
        states.copy(state, world.work / "sub")
        states.copy(state, world.tmp / "copy" / "sub")
        work, copy = world.work, world.tmp / "copy"
    argv0 = ["--config", config] if config else []
    session = in_session(Keys([word, "quit"], answer=answering()), monkeypatch, prog=prog,
                         argv=argv0)
    commands = session.same_as()
    assert commands, session
    argv = commands[0]
    assert " ".join(argv).startswith(prog + " "), argv
    command = argv[len(prog.split()):]
    assert command[0] == VERB_OF[word], command
    if config:
        assert command[command.index("--config") + 1] == config, command
    monkeypatch.chdir(copy)
    shell = invoke(command, prog=prog, monkeypatch=monkeypatch,
                   stdin=Keys([], answer=answering()), check=False)
    monkeypatch.chdir(work)
    assert tree(work) == tree(copy), (session, shell)
    assert shell.code == (1 if state == "D-refused" else 0), shell
    assert shell.first and flat(shell.first) in flat(stripped(session.text)), (shell, session)


@needs_uv
def test_fd9_5_a_run_in_the_session_keeps_the_episodes_its_same_as_command_keeps(
    harness_env: Path, states: States, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Red before the build: no session, so no run and no `same as` line."""
    work = here(states, "B", world)
    copy = states.copy("B", world.tmp / "copy")
    session = in_session(Keys(["run", "quit"], answer=answering(start="y")), monkeypatch)
    commands = session.same_as()
    assert commands and commands[0][1] == "run", session
    monkeypatch.chdir(copy)
    shell = invoke(commands[0][1:], prog=PROG, monkeypatch=monkeypatch,
                   stdin=Keys([], answer=answering(start="y")), check=False)
    monkeypatch.chdir(work)
    assert shell.code == 0, shell
    mine, theirs = run_folder(work), run_folder(copy)
    assert kept_hashes(mine) == kept_hashes(theirs) and kept_hashes(mine)
    assert len(ledger_lines(mine)) == len(ledger_lines(theirs))


# ---------------------------------------------------------------------------
# FD9.7 the home screen's facts
# ---------------------------------------------------------------------------

CARD_WORDS = {"built": "card built", "refused": "card refused"}


@pytest.mark.parametrize("state", ["A", "B", "C1", "C2", "D", "D-nocard", "D-refused", "E"])
def test_fd9_7_the_status_block_says_what_read_folder_reads_and_step_1_is_the_states(
    state: str, states: States, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Red before the build: there is no `folder` module and no session."""
    from poisson_tasks.cli import _format

    work = here(states, state, world)
    if state == "C2":
        holder = hold_lock(run_folder(work))
        holder.__enter__()
    try:
        facts = folder_module().read_folder(work / "tasks.toml")
        session = in_session(Keys([*OPENING.get(state, []), "quit"], answer=answering()),
                             monkeypatch)
    finally:
        if state == "C2":
            holder.__exit__(None, None, None)
    block = first_home(session)
    status = "\n".join(line for line in block if not re.match(r"^next\s*$", line))
    assert steps_of(block)[0] == STEP_ONE[state], block
    rows = {match.group(1) for line in block if (match := re.match(r"^(\w[\w ]*?)\s{2,}", line))}
    assert "folder" in rows and "ready" in rows, block
    if facts.settings is None:
        assert "settings" in rows and facts.runs == ()
    else:
        assert facts.settings.model.name in status
        assert facts.key_variable in status
        assert ("not set" in status) is (not facts.key_set), status
    for run in facts.runs[:5]:
        line = next((line for line in block if run.name in line), None)
        assert line is not None, (run.name, block)
        at = block.index(line)
        said = " ".join(block[at:at + 3])
        assert f"{run.kept} of {run.total}" in said, (run, said)
        if run.spent_usd is not None:
            assert _format.dollars(run.spent_usd) in said, (run, said)
        if run.locked:
            assert "running in another window" in said, said
        elif run.card is not None:
            assert CARD_WORDS[run.card] in said, said
        elif run.kept < run.total:
            assert "stopped partway" in said, said
    for arm, rate in facts.levels:
        assert arm.split(":")[-1] in status and _format.rate(rate) in status, (arm, status)
    if facts.tools is not None:
        assert "your tools" in rows, block
        assert facts.tools.name in status and str(facts.tools.tools) in status, status
        assert str(facts.tools.refused) in status, status


@pytest.mark.parametrize("state", ["C1", "C2", "D", "D-refused", "E"])
def test_fd9_7_read_folder_reads_the_folder_from_disk_alone(
    state: str, states: States, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each run's kept of total as `runs` counts them for a resume, its dollars from the ledger,
    its card, its lock; the newest card's levels; the tools' counts; with no socket, and none of
    the modules that load the tokenizer when imported (`tasks`, `calibration`, `runs`) imported,
    in a fresh process.  Red before the build: there is no `folder` module."""
    import json

    from poisson_tasks import config, runs
    from tests.fd2_fakes import network_guard
    from tests.fd5_support import recording_opens

    work = here(states, state, world)
    settings = config.load_config(work / "tasks.toml")
    plan = config.resolve_plan(settings, root=work)
    folder = run_folder(work) if (work / "runs").exists() else None
    with recording_opens() as opened, network_guard(monkeypatch) as events:
        if state == "C2":
            assert folder is not None
            with hold_lock(folder):
                facts = folder_module().read_folder(work / "tasks.toml")
        else:
            facts = folder_module().read_folder(work / "tasks.toml")
    assert not [e for e in events if e[0] == "connect"], events
    assert opened
    loaded = subprocess.run(
        [sys.executable, "-c", "import sys; from poisson_tasks.folder import read_folder; "
         f"read_folder({str(work / 'tasks.toml')!r}); "
         "print(sorted(m for m in ('poisson_tasks.tasks', 'poisson_tasks.calibration', "
         "'poisson_tasks.runs') if m in sys.modules))"],
        capture_output=True, text=True, check=True, cwd=work)
    assert loaded.stdout.strip() == "[]", loaded
    assert facts.key_variable == settings.model.api_key_env
    assert facts.key_set is bool(os.environ.get(settings.model.api_key_env))
    if folder is None:
        assert facts.runs == ()
        return
    (run,) = facts.runs
    assert run.name == folder.name
    assert (run.kept, run.total) == (runs._kept(plan, folder), runs._total(plan))
    assert run.spent_usd == pytest.approx(
        runs.SpendLedger(folder, price=settings.model.price).total_dollars)
    assert run.locked is (state == "C2")
    card = folder / "card"
    expected = ("built" if (card / "artifact.json").is_file() else
                "refused" if (card / "episodes.jsonl").is_file() else None)
    assert run.card == expected
    if expected == "built":
        cells = json.loads((card / "artifact.json").read_text(encoding="utf-8"))["cells"]
        assert sorted(facts.levels) == sorted((str(c["arm_id"]), float(c["pass_at_1"]))
                                              for c in cells)
    else:
        assert facts.levels == ()
    if state == "E":
        from poisson_tasks import own

        reading = own.read_tools((work / "petstore.json").read_bytes(), name="petstore")
        assert (facts.tools.tools, facts.tools.refused, facts.tools.flows) == (
            len(reading.toolset.tools), len(reading.refused), 0)
    else:
        assert facts.tools is None


# ---------------------------------------------------------------------------
# FD9.8 no step the verb refuses
# ---------------------------------------------------------------------------


@needs_uv
@pytest.mark.parametrize("state", ["A", "B", "C1", "C2", "D", "D-nocard", "D-refused", "E"])
def test_fd9_8_every_offered_step_runs_as_a_command_without_a_refusal(
    state: str, harness_env: Path, states: States, world: World,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each step of `next`, picked by its number in a session on a copy of the state, then its
    `same as` command run from a shell in another copy (a run answered yes): no exit 1 or 2.  A
    step with no command (`home`, `replies`) is a view.  In state D with a refused card, step 1 is
    `card`, which shows the refusal and exits 1: that step is the pending question
    `test_fd9_pending_refused_card_step.py`.  Red before the build: there is no session."""
    keyed(monkeypatch, states)
    work = here(states, state, world)
    held = hold_lock(run_folder(work)) if state == "C2" else None
    if held is not None:
        held.__enter__()
    try:
        shown = in_session(Keys([*OPENING.get(state, []), "quit"], answer=answering()),
                           monkeypatch_for(work, monkeypatch))
    finally:
        if held is not None:
            held.__exit__(None, None, None)
    steps = steps_of(first_home(shown))
    assert steps, shown
    for number, word in enumerate(steps, 1):
        if word in ("home", "replies", "more", "runs", "settings", "help"):
            continue
        if state == "D-refused" and word == "card":
            continue
        mine = states.copy(state, world.tmp / f"{number}-session")
        theirs = states.copy(state, world.tmp / f"{number}-shell")
        locks = [hold_lock(run_folder(path)) for path in (mine, theirs)] if state == "C2" else []
        for lock in locks:
            lock.__enter__()
        try:
            monkeypatch.chdir(mine)
            start = [""] if (state, word) == ("A", "setup") else []  # the run-through's first
            session = in_session(Keys([*OPENING.get(state, []), str(number), *start, "quit"],
                                      answer=answering(flow=word == "flow")), monkeypatch)
            commands = session.same_as()
            assert commands, (word, session)
            monkeypatch.chdir(theirs)
            shell = invoke(commands[0][1:], prog=PROG, monkeypatch=monkeypatch,
                           stdin=Keys([], answer=answering(start="y")), check=False)
        finally:
            for lock in locks:
                lock.__exit__(None, None, None)
        assert shell.code not in (1, 2), (word, shell)


def monkeypatch_for(work: Path, monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    monkeypatch.chdir(work)
    return monkeypatch


# ---------------------------------------------------------------------------
# FD9.9 the prompt
# ---------------------------------------------------------------------------


def test_fd9_9_after_an_action_next_is_the_new_states_and_the_status_block_is_not_repeated(
    states: States, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spec §16.3: after an action, its result, then `next` for the state it left, then the
    prompt; the status block only on opening, after `home` and after a run.  Building the card
    (step 1 of a finished run with none) leaves the state of a card built, whose step 2 is not
    `task`.  Red before the build: there is no session."""
    here(states, "D-nocard", world)
    session = in_session(Keys(["", "quit"], answer=answering()), monkeypatch)
    after = stripped(session.log.screens()[1]).splitlines()
    assert not [line for line in after if re.match(r"^folder\s", line)], after
    at = max(i for i, line in enumerate(after) if line.strip() == "next")
    steps = steps_of(after[at:])
    assert steps[0] == "card" and steps[1:] != ["task", "again"], steps


def test_fd9_9_enter_picks_step_1_and_a_number_picks_that_step(
    states: States, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Red before the build: there is no session."""
    here(states, "D", world)
    session = in_session(Keys(["", "2", "quit"], answer=answering()), monkeypatch)
    steps = steps_of(first_home(session))
    commands = session.same_as()
    assert len(commands) == 2, session
    assert commands[0][1] == VERB_OF[steps[0]] and commands[1][1] == VERB_OF[steps[1]], (
        steps, commands)


@pytest.mark.parametrize("word", [w for w in WORDS if w != "quit"])
def test_fd9_9_each_word_of_the_closed_set_runs_its_action(
    word: str, states: States, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A verb's word shows its verb's `same as` command; a view's word shows what it reads.  Red
    before the build: there is no session."""
    state = "E" if word in ("flow", "replies") else "D"
    work = here(states, state, world)
    folder = run_folder(work)
    session = in_session(Keys([word, "quit"], answer=answering(flow=word == "flow")),
                         monkeypatch)
    after = stripped("".join(session.log.screens()[1:]))
    if word in VERB_OF:
        commands = session.same_as()
        assert commands and commands[0][1] == VERB_OF[word], session
        extra = {"again": "--again", "check": "--offline", "flow": "--own-flow",
                 "task": "--show"}.get(word)
        assert extra is None or extra in commands[0], commands
        return
    if word == "more":
        heads = [line[3:] for line in (folder / "card" / "card.md").read_text(
            encoding="utf-8").splitlines() if line.startswith("## ")]
        assert heads and all(head in after for head in heads), after
    elif word == "replies":
        from tests.fd5_support import TASK_OUTCOMES

        assert any(arm.name.replace("-", ":", 1) in after for arm in folder.iterdir()
                   if (arm / "traces.jsonl").is_file()), after
        assert any(re.search(rf"\b{label}\b", after) for label in TASK_OUTCOMES), after
    elif word == "runs":
        assert folder.name in after, after
    elif word == "settings":
        from poisson_tasks import config

        settings = config.load_config(work / "tasks.toml")
        assert settings.model.name in after and str(settings.limits.concurrency) in after, after
    elif word == "home":
        assert len(home_blocks(session.out)) == 2, session
    elif word == "help":
        assert all(re.search(rf"\b{w}\b", after) for w in WORDS), after
    else:  # pragma: no cover - every word is named above
        raise AssertionError(word)


def test_fd9_9_an_unknown_word_says_so_in_one_line_and_changes_nothing(
    states: States, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Red before the build: there is no session."""
    work = here(states, "D", world)
    before = tree(work)
    session = in_session(Keys(["crad", "quit"], answer=answering()), monkeypatch)
    screen = stripped(session.log.screens()[1]).splitlines()[:-1]  # the last is the prompt
    said = [line for line in screen if line.strip()]
    assert len(said) == 1 and "crad" in said[0] and "card" in said[0], said
    assert tree(work) == before


def test_fd9_9_tab_completes_a_unique_prefix(states: States, world: World) -> None:
    """In the pretty look, `he` and Tab is `help`.  Red before the build: there is no session."""
    work = here(states, "D", world)
    with pty_session([], env=pretty_env(world), cwd=work) as session:
        session.quiet(1.5)
        mark = len(session.plain)
        session.send("he\t")
        session.type("")
        after = session.plain[mark:]
        assert all(re.search(rf"\b{w}\b", after) for w in WORDS), after
        session.type("quit", settle=0)
        assert session.wait() == 0


# ---------------------------------------------------------------------------
# FD9.10 leaving
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("how", ["quit", "Ctrl-D", "Ctrl-C twice"])
def test_fd9_10_leaving_at_the_prompt_exits_0_and_changes_nothing(
    how: str, states: States, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """G8.  Red before the build: a bare command exits 2."""
    work = here(states, "D", world)
    before = tree(work)
    words = {"quit": ["quit"], "Ctrl-D": [EOF], "Ctrl-C twice": [INTERRUPT, INTERRUPT]}[how]
    session = in_session(Keys(words, answer=answering()), monkeypatch)
    assert session.code == 0, session
    assert home_blocks(session.out), session
    assert session.keys.ends <= 1 and not session.keys.words, session
    assert tree(work) == before


def test_fd9_10_ctrl_c_with_text_typed_clears_the_line_only(
    states: States, world: World
) -> None:
    """`car`, Ctrl-C, then `d` and Enter: the word read is `d`, not `card`.  Then `car` and Ctrl-C
    twice: the first clears the line, the second is a first Ctrl-C on an empty line, so the session
    is still open; a third leaves it.  Red before the build: no session."""
    work = here(states, "D", world)
    with pty_session([], env=pretty_env(world), cwd=work) as session:
        session.quiet(1.5)
        session.send("car")
        session.ctrl_c()
        mark = len(session.plain)
        session.type("d")
        after = session.plain[mark:]
        assert '"d"' in after and not re.search(r"^ok  card", after, re.MULTILINE), after
        session.send("car")
        session.ctrl_c()
        session.ctrl_c()
        assert session.process.poll() is None, session.plain
        session.ctrl_c(settle=0)
        assert session.wait() == 0, session.plain


# ---------------------------------------------------------------------------
# FD9.11 Ctrl-C at a question
# ---------------------------------------------------------------------------


def test_fd9_11_ctrl_c_at_an_init_question_writes_no_settings_and_the_session_stays(
    states: States, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Red before the build: there is no session."""
    here(states, "A", world)
    session = in_session(Keys(["", "home", "quit"], answer=answering(interrupt="_init")),
                         monkeypatch)
    assert any(asked.module == "_init" for asked in session.keys.asked), session
    assert not (world.work / "tasks.toml").exists()
    assert session.code == 0 and home_blocks(session.out), session


@pytest.mark.parametrize("word", ["runs", "replies", "more"])
def test_fd9_11_ctrl_c_in_a_view_goes_back_to_the_prompt(
    word: str, states: States, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spec §16.7: Ctrl-C in a view's menu (the session's own) goes back to the prompt, which then
    reads a word.  Red before the build: there is no session."""
    here(states, "E", world)
    session = in_session(Keys([word, "home", "quit"], answer=answering()), monkeypatch)
    assert any(a.module == "_session" for a in session.keys.asked), session
    assert session.code == 0 and len(home_blocks(session.out)) == 2, session


def test_fd9_11_ctrl_c_at_start_spends_nothing_makes_no_folder_and_the_session_stays(
    states: States, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Red before the build: there is no session."""
    work = here(states, "B", world)
    monkeypatch.setenv(KEY_VAR, KEY)
    posts = len(states.model.posts())
    session = in_session(Keys(["run", "home", "quit"], answer=answering(start=INTERRUPT)),
                         monkeypatch)
    assert session.keys.started, session
    assert not (work / "runs").exists()
    assert len(states.model.posts()) == posts
    assert session.code == 0 and len(home_blocks(session.out)) >= 2, session


# ---------------------------------------------------------------------------
# FD9.12 and FD9.13 Ctrl-C during a run, and the prompt after a run
# ---------------------------------------------------------------------------


@needs_uv
def test_fd9_12_ctrl_c_during_a_run_stops_it_as_run_does_and_step_1_resumes_it(
    harness_env: Path, states: States, world: World
) -> None:
    """The run's own first interrupt: the folder keeps what ended, the session is at its prompt,
    the home screen says stopped partway with step 1 the resume, and taking it finishes the run
    with no episode run twice.  The prompt reads after the interrupt and after the run ends
    (FD9.13).  Red before the build: there is no session."""
    write_config(world.work / "tasks.toml",
                 states.flags(model="fixture-slow", tasks_per_level=3))
    plan = plan_of(world.work / "tasks.toml")
    total = len(plan.arms) * len(plan.seeds)
    with pty_session([], env=pretty_env(world), cwd=world.work) as session:
        session.quiet(1.5)
        session.type("run", settle=0)
        session.expect(r"Start\?", timeout=120)
        session.type("y", settle=0)
        deadline = __import__("time").monotonic() + 180
        while not (world.work / "runs").exists() or not ledger_lines(run_folder(world.work)):
            assert __import__("time").monotonic() < deadline, session.plain
            session._pump(0.3)
        session.ctrl_c(settle=0)
        session.expect(r"^stopped\s", timeout=60)
        session.quiet(1.5)
        folder = run_folder(world.work)
        kept = kept_hashes(folder)
        assert 1 <= len(kept) < total and len(set(kept)) == len(kept)
        assert len(ledger_lines(folder)) == len(kept)
        mark = len(session.plain)
        session.type("home")
        block = home_blocks(session.plain[mark:])
        assert block and "stopped partway" in "\n".join(block[0]), session.plain[mark:]
        assert steps_of(block[0])[0] == "run"
        session.type("", settle=0)
        session.expect(r"Start\?", timeout=120, since=mark)
        session.type("y", settle=0)
        session.expect(r"^done\s", timeout=300, since=mark)
        session.quiet(1.5)
        mark = len(session.plain)
        session.type("help")
        assert all(re.search(rf"\b{w}\b", session.plain[mark:]) for w in WORDS)
        session.type("quit", settle=0)
        assert session.wait() == 0
    kept = kept_hashes(folder)
    assert len(kept) == total and len(set(kept)) == total


@needs_uv
def test_fd9_13_the_prompt_reads_a_word_after_a_run_stopped_by_its_cap(
    harness_env: Path, states: States, world: World
) -> None:
    """Red before the build: there is no session."""
    flags, cap = over_estimate_design(states.model.base_url)
    write_config(world.work / "tasks.toml", flags)
    under_the_cap(plan_of(world.work / "tasks.toml"), cap)
    with pty_session([], env=pretty_env(world), cwd=world.work) as session:
        session.quiet(1.5)
        session.type("run", settle=0)
        session.expect(r"Start\?", timeout=120)
        session.type("y", settle=0)
        session.expect(r"^stopped\s", timeout=300)
        session.quiet(1.5)
        mark = len(session.plain)
        session.type("help")
        assert all(re.search(rf"\b{w}\b", session.plain[mark:]) for w in WORDS), session.plain
        session.type("quit", settle=0)
        assert session.wait() == 0


# ---------------------------------------------------------------------------
# FD9.14 no raw Markdown
# ---------------------------------------------------------------------------


def test_fd9_14_the_card_view_and_more_print_no_raw_markdown(
    states: States, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every section of `more`, picked by number from its menu.  Red before the build: there is
    no session."""
    work = here(states, "D-nocard", world)
    session = in_session(Keys(["card", "quit"], answer=answering()), monkeypatch)
    folder = run_folder(work)
    heads = [line for line in (folder / "card" / "card.md").read_text(
        encoding="utf-8").splitlines() if line.startswith("## ")]
    menus = [str(number) for number in range(1, len(heads) + 1)]
    more = in_session(Keys([*["more"] * len(heads), "quit"], answer=answering(menus=menus)),
                      monkeypatch)
    text = stripped(session.text + more.text)
    assert len(heads) > 1 and all(head[3:] in text for head in heads), text
    raw = [line for line in text.splitlines() if RAW.match(line)]
    assert not raw, raw


# ---------------------------------------------------------------------------
# FD9.16 the copy, from the session
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("state,word", [("B", "setup"), ("E", "flow")])
def test_fd9_16_setup_and_flow_keep_the_file_they_replace(
    state: str, word: str, states: States, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """G10; `flow` takes the flow addPet.id into getPetById.petId from its menus (G21).  Red
    before the build: there is no session."""
    work = here(states, state, world)
    old = (work / "tasks.toml").read_bytes()
    session = in_session(Keys([word, "quit"], answer=answering(flow=word == "flow")),
                         monkeypatch)
    assert (work / "tasks.toml.bak").read_bytes() == old, session
    assert any(re.match(r"^\s*kept\s.*tasks\.toml\.bak", line)
               for line in stripped(session.text).splitlines()), session
    if word == "flow":
        from poisson_tasks import config

        flows = config.load_config(work / "tasks.toml").own.flows
        assert [tuple(f) for f in flows] == [("addPet", "id", "getPetById", "petId")], flows


# ---------------------------------------------------------------------------
# FD9.20 the first question
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("where", ["init", "run-through"])
@pytest.mark.parametrize("kind", ["built-in", "own"])
def test_fd9_20_the_first_question_is_built_in_tasks_or_your_own_tools(
    where: str, kind: str, states: States, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """G7: one menu of two, built-in tasks or your own tools, in `init` and in the run-through,
    which are one dialogue; your own tools asks for the file before any recipe, and the built-in
    recipes' menu has no own-tools entry.  Red before the build: the first question is the
    provider, of five."""
    shutil.copy(PETSTORE, world.work / "petstore.json")
    keyed(monkeypatch, states)
    first = r"built-in" if kind == "built-in" else r"own tools"
    keys = Keys([Through("n"), "quit"] if where == "run-through" else [],
                answer=answering(first=first), free=["petstore.json"])
    if where == "init":
        invoke(["init"], prog=PROG, monkeypatch=monkeypatch, stdin=keys, check=False)
    else:
        in_session(keys, monkeypatch)
    asked = [a for a in keys.asked if a.module == "_init"]
    assert asked and asked[0].kind == "choice" and len(asked[0].options) == 2, asked[:1]
    assert re.search("built-in", asked[0].options[0], re.I), asked[0].options
    assert re.search("own tools", asked[0].options[1], re.I), asked[0].options
    from poisson_tasks import config

    made = config.load_config(world.work / "tasks.toml")
    presets = [config.PRESETS[name].label for name in config.PRESET_NAMES]
    menus = [i for i, a in enumerate(asked) if a.kind == "choice" and i > 0
             and a.options != presets]
    if kind == "own":
        assert made.own is not None and made.own.file == "petstore.json"
        file_at = next(i for i, a in enumerate(asked) if a.kind == "ask" and a.default is None)
        recipe_at = menus[0]
        assert file_at < recipe_at, [(a.kind, a.question) for a in asked]
    else:
        assert made.own is None
        assert not any(re.search("own tools", label, re.I)
                       for a in asked[1:] for label in a.options), asked


# ---------------------------------------------------------------------------
# FD9.21 the plain session
# ---------------------------------------------------------------------------


NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


@pytest.mark.parametrize("how", ["--plain", "NO_COLOR", "TERM=dumb"])
def test_fd9_21_the_plain_session_writes_no_escape_and_carries_the_pretty_ones_facts(
    how: str, states: States, world: World
) -> None:
    """G4.  Red before the build: there is no session."""
    work = here(states, "D", world)
    homes = {}
    for look in ("pretty", "plain"):
        extra = {"NO_COLOR": "1"} if (look, how) == ("plain", "NO_COLOR") else (
            {"TERM": "dumb"} if (look, how) == ("plain", "TERM=dumb") else {})
        argv = ["--plain"] if (look, how) == ("plain", "--plain") else []
        with pty_session(argv, env=pretty_env(world, **extra), cwd=work) as session:
            session.quiet(1.5)
            session.type("quit", settle=0)
            assert session.wait() == 0, session.plain
            if look == "plain":
                assert "\x1b" not in session.text, repr(session.text[:400])
            blocks = home_blocks(session.plain)
            assert blocks, session.plain
            homes[look] = sorted(NUMBER.findall("\n".join(blocks[0])))
    assert homes["plain"] == homes["pretty"], homes


# ---------------------------------------------------------------------------
# FD9.22 the banner
# ---------------------------------------------------------------------------

DEPTHS = {
    "truecolor": {"COLORTERM": "truecolor", "TERM": "xterm-256color"},
    "256": {"COLORTERM": None, "TERM": "xterm-256color"},
    "16": {"COLORTERM": None, "TERM": "xterm"},
    "monochrome": {"NO_COLOR": "1", "COLORTERM": None, "TERM": "xterm-256color"},
}


def _banner_lines(text: str) -> list[list[tuple[str, Any, bool, bool]]]:
    lines: list[list[tuple[str, Any, bool, bool]]] = [[]]
    for item in styled(text):
        if item[0] == "\n":
            lines.append([])
        else:
            lines[-1].append(item)
    while lines and not "".join(c for c, *_ in lines[0]).strip():
        lines.pop(0)
    return [[(c, *rest) for c, *rest in line] for line in lines]


def _trimmed(line: list[tuple[str, Any, bool, bool]]) -> list[tuple[str, Any, bool, bool]]:
    while line and line[-1][0] == " ":
        line = line[:-1]
    return [(c, None, False, False) if c == " " else (c, *rest) for c, *rest in line]


@pytest.mark.parametrize("depth", list(DEPTHS))
def test_fd9_22_the_banner_at_each_colour_depth_is_the_ruled_one(
    depth: str, states: States, world: World
) -> None:
    """B1 to B3: the mark flat cobalt (#3B5BDB, then Rich's step-down), the name in the terminal's
    foreground, bold, the version dim; under `NO_COLOR` the same text with no escape sequence.
    Each depth in a process of its own.  Red before the build: there is no session."""
    work = here(states, "B", world)
    with pty_session([], env=pretty_env(world, **DEPTHS[depth]), cwd=work,
                     columns=80) as session:
        session.quiet(1.5)
        session.type("quit", settle=0)
        session.wait()
    got = _banner_lines(session.text)[:2]
    want = _banner_lines(_ans_text(depth))[:2]
    assert [_trimmed(line) for line in got] == [_trimmed(line) for line in want], (
        got, want)
    if depth == "monochrome":
        head = session.text.split("\n", 2)
        assert "\x1b" not in head[0] + head[1], repr(head[:2])


def _ans_text(depth: str) -> str:
    """The `.ans` file's text with this install's version."""
    from tests.fd9_support import FIXTURES

    text = (FIXTURES / f"banner-R-{depth}.ans").read_text(encoding="utf-8")
    if version() == "0.1.0":
        return text
    out = []
    for char, fg, bold, dim in banner_styles(depth):
        codes = [str(c) for c in (1 if bold else None, 2 if dim else None) if c]
        if fg is not None:
            codes += {"rgb": lambda f: ["38", "2", *map(str, f[1:])],
                      "256": lambda f: ["38", "5", str(f[1])],
                      "16": lambda f: [str(f[1])]}[fg[0]](fg)
        out.append(f"\x1b[{';'.join(codes)}m{char}\x1b[0m" if codes else char)
    return "".join(out)


@pytest.mark.parametrize("columns", [40, 60, 120])
def test_fd9_22_the_banner_is_its_two_lines_at_every_width_from_40_and_never_wraps(
    columns: int, states: States, world: World
) -> None:
    """The ruled banner is its own narrow form, 26 cells wide.  Red before the build."""
    work = here(states, "B", world)
    with pty_session([], env=pretty_env(world), cwd=work, columns=columns) as session:
        session.quiet(1.5)
        session.type("quit", settle=0)
        session.wait()
    lines = [line.rstrip() for line in session.plain.lstrip("\n").splitlines()]
    assert lines[:2] == banner_text(), lines[:3]
    assert max(cell_len(line) for line in banner_text()) <= min(columns, 40)


@pytest.mark.parametrize("how", ["--plain", "TERM=dumb"])
def test_fd9_22_with_plain_or_a_dumb_terminal_the_banner_is_one_line_with_no_art(
    how: str, states: States, world: World
) -> None:
    """B3, and the one line's words as ruled on 2026-10-20 (P1, no): `Poisson Labs  tasks
    <version>`, the ruled banner's own words.  Red before the build: there is no session."""
    work = here(states, "B", world)
    extra = {"TERM": "dumb"} if how == "TERM=dumb" else {}
    argv = ["--plain"] if how == "--plain" else []
    with pty_session(argv, env=pretty_env(world, **extra), cwd=work) as session:
        session.quiet(1.5)
        session.type("quit", settle=0)
        assert session.wait() == 0
    lines = [line for line in session.plain.splitlines() if line.strip()]
    assert lines[0].strip() == ONE_LINE.format(version()), lines[:2]
    assert not set(session.plain) & BLOCKS, session.plain


def test_fd9_22_the_banner_shows_once_and_first(states: States, world: World) -> None:
    """Once, first, in a session that stays on the normal screen (G3: no alternate screen).  Red
    before the build: there is no session."""
    work = here(states, "B", world)
    with pty_session([], env=pretty_env(world), cwd=work) as session:
        session.quiet(1.5)
        for word in ("home", "help", "home"):
            session.type(word)
        session.type("quit", settle=0)
        assert session.wait() == 0
    assert session.plain.count(MARK) == 1, session.plain
    assert session.plain.lstrip().startswith(MARK), session.plain[:200]
    assert "\x1b[?1049h" not in session.text, "G3: no alternate screen"
