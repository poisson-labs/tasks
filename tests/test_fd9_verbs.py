"""What the guided session changes in the seven verbs, frozen as tests before it is built.  One
implementation: the session's actions are these verbs, so each change is the verb's own, printed
from a shell as in the session.

- **G9, the run lock**: `run` holds `<run folder>/run.lock` (an advisory `flock`) while it runs; a
  second `run` on a held folder refuses, exit 1, nothing spent; a lock whose process is gone is
  not held.
- **G10**: `init --force` keeps the replaced file as `tasks.toml.bak`, and says so.
- **G12, N2**: a card on your own tools names no comparison; `card --compare published` reads the
  written card, needs no `--force`, opens with `different`, writes `compare.md`, prints no card.
- **G13, N3**: `generate --show` with no `--arm` shows the first arm's first task and names the
  other arms; `verify` with nothing to judge names a complete command; an overwrite refusal's
  `next:` keeps every flag typed.  (The corpus test of complete next steps, following every
`next:` three hops,
  was cut by the cut rule: no mutant of the build fails it alone, since each new `next:` line is
  pinned exactly here.)
- **G14, N7**: no path, URL or command split by a newline in the pretty look; a wrapped row keeps
  its indent; `doctor`'s row words `ok`, `note`, `refused` and `not ok`; `init`'s questions
  numbered as asked; no "below" without the lines it promises.
- **G15**: `init`'s closing screen names `doctor --show-command` instead of the command, and
  `--json` keeps the command.
- **G17**: `card`'s result names its run (folder, dollars spent, kept of total) and says once how
  it stands beside the published card.

Each test says why it is red before the build.  The fixture states and how every expectation is
computed are in `tests/fd9_support.py`.
"""

from __future__ import annotations

import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from tests.fd3_support import KEY, KEY_VAR, harness_env, needs_uv
from tests.fd5_support import (
    World,
    base_env,
    error_lines,
    fixture_flags,
    invoke,
    next_commands,
    plan_of,
    printed_command,
    strict_json,
    strip_prog,
    world,
    write_config,
)
from tests.fd9_support import (
    PETSTORE,
    PROG,
    PUBLISHED_MODEL,
    Asked,
    Keys,
    States,
    hold_lock,
    kept_hashes,
    lock_is_held,
    pick,
    pretty_env,
    pty_session,
    run_folder,
    states,
)

__all__ = ["harness_env", "states", "world"]

QUIET = ["--yes", "--no-fetch", "--no-check-key"]


def here(states: States, name: str, world: World) -> Path:
    return states.copy(name, world.work)


# ---------------------------------------------------------------------------
# G9 the run lock
# ---------------------------------------------------------------------------


@needs_uv
def test_fd9_15_g9_a_run_on_a_folder_another_process_holds_is_refused_with_nothing_spent(
    harness_env: Path, states: States, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Refused before its first request: no key check and no call.  Red before the build:
    nothing locks a folder, so the run resumes and spends."""
    work = here(states, "C1", world)
    folder = run_folder(work)
    ledger = (folder / "spend.jsonl").read_bytes()
    requests = len(states.model.requests)
    with hold_lock(folder):
        ran = invoke(["run", "--yes"], prog=PROG, monkeypatch=monkeypatch)
    assert ran.code == 1, ran
    (line,) = error_lines(ran)
    assert folder.name in line, line
    assert len(states.model.requests) == requests, "a request was sent, a key check or a call"
    assert (folder / "spend.jsonl").read_bytes() == ledger


@needs_uv
def test_fd9_15_g9_a_run_holds_its_folders_lock_until_it_ends(
    harness_env: Path, states: States, world: World
) -> None:
    """Red before the build: no lock is ever held."""
    write_config(world.work / "tasks.toml", states.flags(model="fixture-slow"))
    env = base_env(world, {"PATH": __import__("os").environ["PATH"], KEY_VAR: KEY})
    process = subprocess.Popen([sys.executable, "-m", "poisson_tasks", "run", "--yes"],
                               cwd=world.work, env=env, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
    held = False
    try:
        deadline = time.monotonic() + 180
        while process.poll() is None and time.monotonic() < deadline:
            runs = world.work / "runs"
            if runs.exists() and any(runs.iterdir()) and lock_is_held(run_folder(world.work)):
                held = True
                break
            time.sleep(0.2)
        assert process.wait(300) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(10)
    assert held, "the run never held its folder's lock"
    assert not lock_is_held(run_folder(world.work))


@needs_uv
def test_fd9_15_g9_a_lock_whose_process_is_gone_does_not_stop_a_run(
    harness_env: Path, states: States, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Green before the build, by construction (nothing reads a lock): it holds the build to a
    lock that never goes stale."""
    work = here(states, "C1", world)
    folder = run_folder(work)
    with hold_lock(folder):
        pass
    ran = invoke(["run", "--yes"], prog=PROG, monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    assert len(kept_hashes(folder)) == 2


# ---------------------------------------------------------------------------
# G10 the copy
# ---------------------------------------------------------------------------


def test_fd9_16_g10_init_force_keeps_the_replaced_file_and_says_so(
    states: States, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Red before the build: there is no `tasks.toml.bak`."""
    work = here(states, "B", world)
    old = (work / "tasks.toml").read_bytes()
    ran = invoke(["init", "--force", *QUIET, "--tasks-per-level", "2"], prog=PROG,
                 monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    assert (work / "tasks.toml.bak").read_bytes() == old
    assert (work / "tasks.toml").read_bytes() != old
    assert any(re.match(r"^\s+kept\s.*tasks\.toml\.bak", line) for line in ran.lines), ran


# ---------------------------------------------------------------------------
# G12 the comparison
# ---------------------------------------------------------------------------


@needs_uv
def test_fd9_17_g12_a_card_on_your_own_tools_names_no_comparison(
    states: States, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Red before the build: it ends with `next: ... card --compare published`."""
    here(states, "E", world)
    ran = invoke(["card", "--force"], prog=PROG, monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    assert not [c for c in next_commands(ran.out) if "--compare" in c], ran


@needs_uv
def test_fd9_17_g12_card_compare_published_reads_the_written_card(
    states: States, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exit 0 with no `--force`, `different` first, `compare.md` written, neither card printed.
    Red before the build: the written card is refused as an overwrite."""
    work = here(states, "E", world)
    folder = run_folder(work)
    card = (folder / "card" / "card.md").read_text(encoding="utf-8")
    written = {name: (folder / "card" / name).read_bytes()
               for name in ("artifact.json", "card.md", "episodes.jsonl")}
    ran = invoke(["card", "--compare", "published"], prog=PROG, monkeypatch=monkeypatch)
    assert ran.code == 0 and ran.word == "different", ran
    assert (folder / "card" / "compare.md").is_file()
    assert {name: (folder / "card" / name).read_bytes() for name in written} == written
    lines = {line.strip() for line in card.splitlines() if len(line.strip()) > 20}
    assert not [line for line in ran.lines if line.strip() in lines], ran
    assert not [line for line in ran.lines if re.match(r"^\s*(\||#|---)", line)], ran


@needs_uv
def test_fd9_17_g12_card_compare_published_on_the_built_in_tasks_says_different(
    states: States, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Decided yes 2026-10-20: G12's one-line verdict covers the
    built-in tasks: exit 0, `different`, and `compare.md` holding the earlier-build sentence.
    Folded in from its pending file unchanged.  Red before the build: it is refused, exit 1."""
    folder = run_folder(states.copy("D", world.work))
    ran = invoke(["card", "--compare", "published"], prog=PROG, monkeypatch=monkeypatch)
    assert ran.code == 0 and ran.word == "different", ran
    compare = folder / "card" / "compare.md"
    assert compare.is_file() and compare.read_text(encoding="utf-8").strip()


# ---------------------------------------------------------------------------
# G13 every next step complete
# ---------------------------------------------------------------------------

def test_fd9_18_g13_generate_show_without_an_arm_shows_the_first_arms_first_task(
    states: States, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Red before the build: a plan of two arms is a usage error, exit 2."""
    work = here(states, "B", world)
    plan = plan_of(work / "tasks.toml")
    from poisson_tasks.knobs import arm_id

    arms = [arm_id(spec) for spec in plan.arms]
    ran = invoke(["generate", "--show"], prog=PROG, monkeypatch=monkeypatch)
    named = invoke(["generate", "--show", "--arm", arms[0], "--task", "1"], prog=PROG,
                   monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    assert ran.first == named.first, (ran.first, named.first)
    rows = ran.lines[1:ran.lines.index("") if "" in ran.lines else None]
    assert any(all(arm in row for arm in arms[1:]) for row in rows), rows


@needs_uv
@pytest.mark.parametrize("state", ["B", "E", "E without a run"])
def test_fd9_18_g13_verify_with_nothing_to_judge_names_a_complete_command(
    state: str, states: States, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """On the built-in tasks, `verify --self-check --arm <first arm> --task 1`, which passes; on
    your own tools, `card` when a run exists, else `generate --show`.  Red before the build: no
    `next:` line."""
    work = here(states, "E" if state.startswith("E") else state, world)
    if state == "E without a run":
        shutil.rmtree(work / "runs")
    if state == "B":
        from poisson_tasks.knobs import arm_id

        first = arm_id(plan_of(work / "tasks.toml").arms[0])
        ran = invoke(["verify"], prog=PROG, monkeypatch=monkeypatch, check=False)
        want = f"{PROG} verify --self-check --arm {first} --task 1"
    else:
        ran = invoke(["verify", "--self-check", "--arm", "faults:f0", "--task", "1"], prog=PROG,
                     monkeypatch=monkeypatch, check=False)
        want = f"{PROG} card" if state == "E" else f"{PROG} generate --show"
    assert ran.code in (1, 2), ran
    assert next_commands(ran.err) == [want], ran
    if state == "B":
        again = invoke(strip_prog(shlex.split(want), PROG), prog=PROG, monkeypatch=monkeypatch)
        assert again.code == 0, again


@needs_uv
def test_fd9_18_g13_an_overwrite_refusals_next_keeps_every_flag_typed(
    states: States, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Red before the build: the `next:` is `card --force`, without `--print`."""
    here(states, "D", world)
    ran = invoke(["card", "--print"], prog=PROG, monkeypatch=monkeypatch)
    assert ran.code == 1, ran
    assert next_commands(ran.err) == [f"{PROG} card --print --force"], ran


# ---------------------------------------------------------------------------
# G14 the output list
# ---------------------------------------------------------------------------


def _whole_tokens(text: str) -> set[str]:
    """Paths, URLs and the commands named in `text` (one fact per line, as piped): each word
    holding a `/`, and each `next:` command."""
    found = {word.strip(",;()") for line in text.splitlines() for word in line.split()
             if "/" in word and len(word.strip(",;()")) > 12}
    found |= set(next_commands(text))
    return found


CASES = {
    "doctor on your own tools": ("E", ["doctor", "--offline"]),
    "a card": ("D", ["card", "--force"]),
}


@needs_uv
@pytest.mark.parametrize("columns", [60, 80, 100])
@pytest.mark.parametrize("case", list(CASES))
def test_fd9_19_a_g14_no_path_url_or_command_is_split_by_a_newline(
    case: str, columns: int, states: States, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each path, URL and command the piped output names is in the pretty output whole, with no
    newline inside it: on one line, or, longer than the line, left whole for the terminal to fold
    (a pseudo-terminal's stream holds no newline the terminal adds).  Red before the build: Rich
    folds a long path inside its cell."""
    state, argv = CASES[case]
    work = here(states, state, world)
    piped = invoke(argv, prog=PROG, monkeypatch=monkeypatch, check=False)
    here(states, state, world)
    with pty_session(argv, env=pretty_env(world), cwd=work, columns=columns) as session:
        session.wait()
    text = session.plain
    tokens = _whole_tokens(piped.out + piped.err)
    assert tokens, piped
    split = [token for token in tokens if token not in text]
    assert not split, (split, text)


def _rows(lines: list[str], labels: set[str]) -> list[tuple[int, list[str]]]:
    """Each row whose label is one of `labels`, as (the column its value starts at, its
    continuation lines)."""
    out = []
    for index, line in enumerate(lines):
        match = re.match(r"^(\s+)(?:\S\s{2})?(\S+(?: \S+)?)(\s{2,})(\S)", line)
        if not match or match.group(2) not in labels:
            continue
        start = match.start(4)
        following = []
        for later in lines[index + 1:]:
            head = re.match(r"^(\s+)(?:\S\s{2})?(\S+(?: \S+)?)\s{2,}", later)
            if not later.strip() or (head and head.group(2) in labels) or not later.startswith(" "):
                break
            following.append(later)
        out.append((start, following))
    return out


@needs_uv
@pytest.mark.parametrize("case", ["doctor on your own tools", "a card"])
def test_fd9_19_b_g14_a_wrapped_rows_lines_keep_its_indent(
    case: str, states: States, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """At 60 columns in the pretty look, every continuation line of a wrapped row starts where
    the row's value starts.  The labels are the piped output's."""
    state, argv = CASES[case]
    work = here(states, state, world)
    piped = invoke(argv, prog=PROG, monkeypatch=monkeypatch, check=False)
    labels = {match.group(1) for line in piped.lines
              if (match := re.match(r"^  (\S+(?: \S+)?)\s{2,}\S", line))}
    with pty_session(argv, env=pretty_env(world), cwd=work, columns=60) as session:
        session.wait()
    rows = _rows(session.plain.splitlines(), labels)
    assert any(following for _, following in rows), session.plain
    for start, following in rows:
        for line in following:
            assert len(line) - len(line.lstrip()) == start, (start, line, session.plain)


@needs_uv
def test_fd9_19_c_g14_doctor_words_each_row_by_what_it_is(
    states: States, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """In the pipe, on your own tools: `refused` on each refused tool, `note` on each knob's
    probe line and on the flows line, `ok` on the checks that passed, and no other word than
    `ok`, `note`, `refused` and `not ok`.  Red before the build: every one of those rows says
    `ok`."""
    from poisson_tasks import own
    from poisson_tasks.own import recipes

    work = here(states, "E", world)
    reading = own.read_tools(PETSTORE.read_bytes(), name="petstore")
    knobs = set(recipes.offered_knobs(reading.toolset, flows=()))
    ran = invoke(["doctor", "--offline"], prog=PROG, monkeypatch=monkeypatch)
    rows = [match.groups() for line in ran.lines
            if (match := re.match(r"^  (\S+)\s+(ok|note|refused|not ok)\s{2,}\S", line))]
    labels = [label for label, _ in rows]
    assert len(rows) == len(ran.lines) - 1, ran
    words = dict(rows)
    assert labels.count("refused") == len(reading.refused) > 0
    assert all(word == "refused" for label, word in rows if label == "refused"), rows
    assert knobs and all(words[knob] == "note" for knob in knobs), rows
    assert words["flows"] == "note", rows
    for label in ("python", "package", "tokenizer", "config", "platform"):
        assert words[label] == "ok", rows
    assert work


def test_fd9_19_d_g15_inits_closing_screen_points_at_doctor_show_command(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No `init --yes` command block; one row naming `doctor --show-command`; `--json` still holds
    the command.  Red before the build: the closing screen prints the command."""
    from poisson_tasks import config

    flags = [*QUIET, "--tasks-per-level", "2"]
    ran = invoke(["init", *flags], prog=PROG, monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    assert printed_command(ran.out, PROG, "init") is None, ran
    assert any(f"{PROG} doctor --show-command" in line for line in ran.lines), ran
    data = invoke(["init", "--force", *flags, "--json"], prog=PROG, monkeypatch=monkeypatch)
    made = config.load_config(world.work / "tasks.toml")
    assert strict_json(data.out)["command"] == config.equivalent_init_command(made, prog=PROG)


def _numbering_policy(path: str) -> Any:
    from poisson_tasks import config

    order = {"choices": 0}
    provider = {"vllm": "vllm", "openai-compatible": "openai-compatible"}.get(path)

    def answer(asked: Asked) -> Any:
        if asked.kind == "confirm":
            return "n"
        if asked.kind != "choice":
            return None
        order["choices"] += 1
        if order["choices"] == 1:
            return pick("own tools" if path == "own tools" else "built-in")
        if order["choices"] == 2 and provider is not None:
            return pick(re.escape(config.PRESETS[provider].label))
        if path == "custom knob" and len(asked.options) > 2 and order["choices"] == 3:
            return str(len(asked.options))
        return None

    return answer


@pytest.mark.parametrize("path", ["built-in", "own tools", "custom knob", "vllm",
                                  "openai-compatible"])
def test_fd9_19_e_g14_inits_questions_are_numbered_as_asked(
    path: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """1 to n, with no gap and no number twice, on each path.  Red before the build: the built-in
    path skips question 3 and own tools asks question 6 twice."""
    shutil.copy(PETSTORE, world.work / "petstore.json")
    keys = Keys([], answer=_numbering_policy(path),
                free=["petstore.json", "http://127.0.0.1:9/v1"])
    ran = invoke(["init"], prog=PROG, monkeypatch=monkeypatch, stdin=keys, check=False)
    assert ran.code == 0, ran
    numbers = [int(m.group(1)) for line in ran.err_lines
               if (m := re.match(r"^\s*(\d+)\. \S", line))]
    assert numbers == list(range(1, len(numbers) + 1)) and len(numbers) >= 5, (numbers, ran)


def test_fd9_19_f_g14_below_is_followed_by_the_lines_it_names(
    states: States, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """In `init`'s closing screen and its summary on your own tools, and in `doctor`: a line that
    says what follows "below" is followed by a line for each refused tool.  Red before the build:
    the closing row says "below" and nothing follows it."""
    from poisson_tasks import own

    shutil.copy(PETSTORE, world.work / "petstore.json")
    refused = [line.line.split(":")[0].split()[0]
               for line in own.read_tools(PETSTORE.read_bytes(), name="petstore").refused]
    assert refused
    flags = fixture_flags("http://127.0.0.1:9/v1", recipe="error-recovery",
                          extra=["--own-file", "petstore.json"])
    made = invoke(["init", *QUIET, *flags], prog=PROG, monkeypatch=monkeypatch)
    doctor = invoke(["doctor", "--offline"], prog=PROG, monkeypatch=monkeypatch)
    for text in (made.out, made.err, doctor.out):
        lines = text.splitlines()
        for index, line in enumerate(lines):
            if re.search(r"\bbelow\b", line):
                after = "\n".join(lines[index + 1:index + 2 + len(refused)])
                assert all(name in after for name in refused), (line, after)
    closing = next(line for line in made.lines if re.match(r"^\s+your tools\s", line))
    assert all(name in closing for name in refused) or "below" not in closing, closing


# ---------------------------------------------------------------------------
# G17 the card's two rows
# ---------------------------------------------------------------------------


@needs_uv
def test_fd9_g17_the_cards_result_names_its_run_what_it_spent_and_kept_of_total(
    states: States, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Red before the build: there is no `run` row."""
    from poisson_tasks import config, runs
    from poisson_tasks.cli import _format

    work = here(states, "D-nocard", world)
    folder = run_folder(work)
    settings = config.load_config(work / "tasks.toml")
    plan = config.resolve_plan(settings, root=work)
    spent = runs.SpendLedger(folder, price=settings.model.price).total_dollars
    ran = invoke(["card"], prog=PROG, monkeypatch=monkeypatch)
    row = next((line for line in ran.lines if re.match(r"^  run\s{2,}", line)), None)
    assert row is not None, ran
    assert folder.name in row and _format.dollars(spent) in row, row
    assert f"{runs._kept(plan, folder)} of {runs._total(plan)}" in row, row


BESIDE = re.compile(r"^  beside the published cards?\s{2,}(\S.*)$")


@needs_uv
def test_fd9_g17_the_card_says_once_how_it_stands_beside_the_published_card(
    harness_env: Path, states: States, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """On the built-in tasks under a model a published card measured, one row; on your own tools,
    one row that says something else; under another model, none.  Red before the build: there is
    no such row."""
    said: dict[str, list[str]] = {}
    other = world.tmp / "other"
    other.mkdir()
    write_config(other / "tasks.toml", states.flags(model="fixture-reference"))
    for name in ("D-nocard", "E", "other"):
        work = states.copy(name, world.tmp / name) if name != "other" else other
        monkeypatch.chdir(work)
        if name == "other":
            assert invoke(["run", "--yes"], prog=PROG, monkeypatch=monkeypatch).code == 0
        ran = invoke(["card", "--force"], prog=PROG, monkeypatch=monkeypatch)
        assert ran.code == 0, ran
        said[name] = [m.group(1) for line in ran.lines if (m := BESIDE.match(line))]
    assert len(said["D-nocard"]) == 1 and len(said["E"]) == 1, said
    assert said["D-nocard"] != said["E"], said
    assert said["other"] == [], said
    assert PUBLISHED_MODEL
