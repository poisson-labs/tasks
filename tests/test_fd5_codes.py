"""Exit codes, the shape of what the command prints, and `--json`, over a corpus: frozen as tests.

The invariants are FD5.3, FD5.4, FD5.5, FD5.6 and FD5.9 of the front door's plan (spec §4.0,
§11.1 rules L3, L4, L9, L11 and L13, and §11.2):
- **FD5.3** each case of the corpus, an argv and a fixture state, exits with its code: 0 done, 1
  refused, 2 the command line is wrong, 4 a check that did not pass;
- **FD5.4** every stderr line is `error: …`, `note: …`, or a continuation or progress line
  indented two spaces; nothing holds a traceback, a Python repr or an internal id; and the
  `error:` line of a refusal the library makes is `error: ` and the library's own text for the
  same input, compared with the library, never with words;
- **FD5.5** the first stdout line of a success is a verdict line, `^[a-z][a-z ]*  \\S`, whose word
  is one of the verb's;
- **FD5.6** every `next:` command starts with the prog under test;
- **FD5.9** with `--json`, stdout is one strict JSON document whose first key is `schema`, then
  `verdict` and `sentence` (rule L9), equal to the text's verdict line, with the same exit code.

The mistakes round of spec §8.8 is in the corpus where it needs no model: a typo in an arm (as a
flag and in the file), an empty seed list (both ways) and no key.  A refused key, Ctrl-C and its
resume need the fixture model and are in `tests/test_fd5_run.py`.

Shapes decided here
-------------------

**1. A value given as a flag that the library refuses is a command line that is wrong: exit 2.**
The same value in the settings file is a refusal: exit 1 (spec §11.2's two rows; spec §4.1 says
it of init's flags).

**2. `--json` and a refusal.** When the text form prints nothing on stdout (an `error:` line
only), `--json` prints nothing on stdout either; errors stay on stderr in text (L9).  When the text
form prints a verdict line, `--json` prints one document.  For `run`, whose text prints the plan's
verdict line before the run's, the document's verdict is the last verdict line's.

**3. A refusal is one `error:` line**, with `next:` lines after it where there is a next step.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from tests.fd5_support import (
    Ran,
    World,
    arms,
    config,
    conformance,
    error_lines,
    invoke,
    json_keys,
    prog,
    providers,
    strict_json,
    verdict_lines,
    world,
)

__all__ = ["prog", "world"]

CONFIG_FLAGS = ["--tasks-per-level", "2"]
"""A first look against the OpenAI preset, two tasks per level: no network is needed to read or
plan it, and its key variable is unset in every test's world."""


def write(path: Path, flags: list[str] | None = None, edit: tuple[str, str] | None = None) -> Any:
    made = config().config_from_init_args(CONFIG_FLAGS if flags is None else flags)
    text = config().dump_config(made)
    if edit is not None:
        assert edit[0] in text, edit
        text = text.replace(edit[0], edit[1], 1)
    path.write_text(text, encoding="utf-8")
    return made


def nothing(world: World) -> None:
    pass


def a_config(world: World) -> None:
    write(world.work / "tasks.toml")


def a_custom_config(world: World) -> None:
    write(world.work / "tasks.toml",
          ["--recipe", "custom", "--knob", "depth", "--levels", "1,3", "--tasks-per-level", "2"])


def a_keyless_config(world: World) -> None:
    write(world.work / "tasks.toml", [*CONFIG_FLAGS, "--api-key-env", ""])


def a_typo_in_the_arm(world: World) -> None:
    write(world.work / "tasks.toml",
          ["--recipe", "custom", "--knob", "depth", "--levels", "1,3", "--tasks-per-level", "2"],
          edit=('knob = "depth"', 'knob = "dpeth"'))


def an_empty_seed_list(world: World) -> None:
    write(world.work / "tasks.toml", edit=("per_level = 2", "seeds = []"))


def per_level_zero(world: World) -> None:
    write(world.work / "tasks.toml", edit=("per_level = 2", "per_level = 0"))


@dataclasses.dataclass(frozen=True)
class Case:
    name: str
    argv: tuple[str, ...]
    code: int
    setup: Callable[[World], None] = nothing
    verb: str | None = None
    json: bool = True


CORPUS = [
    Case("help", ("--help",), 0, json=False),
    Case("version", ("--version",), 0, json=False),
    Case("an unknown verb", ("nope",), 2, json=False),
    Case("an unknown flag", ("doctor", "--nope"), 2, verb="doctor", json=False),
    Case("init on a pipe", ("init",), 1, verb="init"),
    Case("init with yes", ("init", "--yes", "--no-fetch", "--no-check-key"), 0, verb="init"),
    Case("init over a file", ("init", "--yes", "--no-check-key"), 1, a_config, "init"),
    Case("init with a provider that is not one", ("init", "--yes", "--provider", "nope"), 2,
         verb="init"),
    Case("init with a recipe not offered", ("init", "--yes", "--no-check-key", "--recipe",
                                            "tool-choice"), 2, verb="init"),
    Case("generate from flags", ("generate", "--arm", "depth:d1", "--tasks-per-level", "2"), 0,
         verb="generate"),
    Case("generate from the file", ("generate",), 0, a_config, "generate"),
    Case("generate with a typo in an arm", ("generate", "--arm", "dpeth:d1"), 2,
         verb="generate"),
    Case("generate with no tasks", ("generate", "--arm", "depth:d1", "--tasks-per-level", "0"),
         2, verb="generate"),
    Case("generate with a typo in the file's arm", ("generate",), 1, a_typo_in_the_arm,
         "generate"),
    Case("generate with an empty seed list in the file", ("generate",), 1, an_empty_seed_list,
         "generate"),
    Case("run with no file", ("run", "--dry-run", "--offline"), 1, verb="run"),
    Case("run offline without a dry run", ("run", "--offline"), 2, a_config, "run"),
    Case("run a dry run", ("run", "--dry-run", "--offline"), 0, a_config, "run"),
    Case("run a dry run of a custom plan", ("run", "--dry-run", "--offline"), 0, a_custom_config,
         "run"),
    Case("run with a typo in the file's arm", ("run", "--dry-run", "--offline"), 1,
         a_typo_in_the_arm, "run"),
    Case("run with per_level 0", ("run", "--dry-run", "--offline"), 1, per_level_zero, "run"),
    Case("run with no key", ("run", "--yes"), 1, a_config, "run"),
    Case("verify a task's own answers", ("verify", "--arm", "depth:d1", "--task", "1",
                                         "--self-check"), 0, verb="verify"),
    Case("verify with a typo in the arm", ("verify", "--arm", "depht:d1", "--task", "1",
                                           "--self-check"), 2, verb="verify"),
    Case("export to a runner that is not offered", ("export", "--to", "prove"), 2, a_config,
         "export", json=False),
    Case("export", ("export", "--to", "verifiers"), 0, a_config, "export"),
    Case("export with no file", ("export", "--to", "verifiers"), 1, verb="export"),
    Case("card with no run", ("card",), 1, a_config, "card"),
    Case("card of the published cards", ("card", "--published"), 0, verb="card"),
    Case("card of a published card that is not one", ("card", "--published", "nope"), 2,
         verb="card", json=False),
    Case("doctor, ready", ("doctor", "--offline"), 0, a_keyless_config, "doctor"),
    Case("doctor, the key not set", ("doctor", "--offline"), 4, a_config, "doctor"),
    Case("doctor, the file refused", ("doctor", "--offline"), 4, a_typo_in_the_arm, "doctor"),
    Case("doctor, the init command", ("doctor", "--show-command"), 0, a_config, "doctor"),
]

IDS = [case.name.replace(" ", "-") for case in CORPUS]


def run_case(case: Case, prog: str, world: World, monkeypatch: pytest.MonkeyPatch,
             *, extra: tuple[str, ...] = (), where: str | None = None) -> Ran:
    if where is not None:
        folder = world.work / where
        folder.mkdir()
        monkeypatch.chdir(folder)
        case.setup(dataclasses.replace(world, work=folder))
    else:
        case.setup(world)
    return invoke([*case.argv, *extra], prog=prog, monkeypatch=monkeypatch)


# ---------------------------------------------------------------------------
# FD5.3 exit codes, and FD5.4 to FD5.6 the shape of the output
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", CORPUS, ids=IDS)
def test_fd5_3_each_case_exits_with_its_code_and_prints_in_the_shared_look(
    case: Case, prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran = run_case(case, prog, world, monkeypatch)
    assert ran.code == case.code, ran
    problems = conformance(ran, case.verb)
    assert not problems, "\n".join(problems) + f"\n{ran}"
    if case.code in (1, 2) and not ran.out:
        assert len(error_lines(ran)) == 1, ran
        assert ran.err_lines[0].startswith("error: "), ran
    if case.code == 0 and case.verb is not None:
        assert ran.word in {word for word, _ in verdict_lines(ran.out, case.verb)}, ran


@pytest.mark.parametrize("case", [case for case in CORPUS if case.json and case.verb],
                         ids=[IDS[i] for i, case in enumerate(CORPUS) if case.json and case.verb])
def test_fd5_9_json_is_one_strict_document_with_the_texts_verdict_and_code(
    case: Case, prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    text = run_case(case, prog, world, monkeypatch, where="text")
    data = run_case(case, prog, world, monkeypatch, extra=("--json",), where="json")
    assert data.code == text.code == case.code, (text, data)
    problems = [problem for problem in conformance(data, None)
                if not problem.startswith("stdout")]
    assert not problems, problems
    if not text.out:
        assert data.out == "", data
        return
    document = strict_json(data.out)
    assert isinstance(document, dict)
    assert json_keys(data.out)[:3] == ["schema", "verdict", "sentence"], data.out[:200]
    assert isinstance(document["schema"], str) and document["schema"].strip()
    assert case.verb is not None
    found = verdict_lines(text.out, case.verb)
    assert found, text
    word, sentence = found[-1]
    assert (document["verdict"], document["sentence"]) == (word, sentence), (document, found)


# ---------------------------------------------------------------------------
# FD5.4 a library refusal is the library's own text
# ---------------------------------------------------------------------------


def init_flags(argv: tuple[str, ...]) -> list[str]:
    own = {"--yes", "--no-fetch", "--fetch", "--no-check-key", "--check-key", "--force"}
    return [word for word in argv[1:] if word not in own]


@pytest.mark.parametrize("argv", [
    ("init", "--yes", "--no-check-key", "--provider", "nope"),
    ("init", "--yes", "--no-check-key", "--recipe", "custom", "--knob", "depth", "--levels",
     "4"),
    ("init", "--yes", "--no-check-key", "--provider", "openai-compatible", "--model", "m"),
    ("init", "--yes", "--no-check-key", "--api-key-env", "OPENAI_KEY"),
    ("init", "--yes", "--no-check-key", "--tasks-per-level", "0"),
], ids=["a-provider", "a-level", "no-endpoint", "a-key-variable", "no-tasks"])
def test_fd5_4_inits_refusal_of_a_flag_is_the_librarys_text(
    argv: tuple[str, ...], prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(config().ConfigError) as refused:
        config().config_from_init_args(init_flags(argv))
    ran = invoke(list(argv), prog=prog, monkeypatch=monkeypatch)
    assert ran.code == 2, ran
    assert error_lines(ran) == [f"error: {refused.value}"], ran
    assert list(world.work.iterdir()) == []


@pytest.mark.parametrize("setup", [a_typo_in_the_arm, an_empty_seed_list, per_level_zero],
                         ids=["a-typo-in-an-arm", "an-empty-seed-list", "per-level-zero"])
@pytest.mark.parametrize("verb", ["run", "generate", "export"])
def test_fd5_4_a_refused_settings_file_is_the_readers_text(
    verb: str, setup: Callable[[World], None], prog: str, world: World,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup(world)
    with pytest.raises(config().ConfigError) as refused:
        config().load_config(Path("tasks.toml"))
    argv = {"run": ["run", "--dry-run", "--offline"], "generate": ["generate"],
            "export": ["export", "--to", "verifiers"]}[verb]
    before = sorted(path.name for path in world.work.iterdir())
    ran = invoke(argv, prog=prog, monkeypatch=monkeypatch)
    assert ran.code == 1, ran
    assert error_lines(ran) == [f"error: {refused.value}"], ran
    assert ran.out == ""
    assert sorted(path.name for path in world.work.iterdir()) == before


@pytest.mark.parametrize("arm", ["dpeth:d1", "depth:d03", "depth"])
def test_fd5_4_an_arm_flag_the_library_cannot_read_is_its_text(
    arm: str, prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(ValueError) as refused:
        arms().arm_from_id(arm)
    for argv in (["generate", "--arm", arm], ["verify", "--arm", arm, "--task", "1",
                                              "--self-check"]):
        ran = invoke(argv, prog=prog, monkeypatch=monkeypatch)
        assert ran.code == 2, ran
        assert error_lines(ran) == [f"error: {refused.value}"], ran


def test_fd5_4_a_key_that_is_not_set_is_the_key_checks_own_line(
    prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The mistakes round's "no key": the line is the library's, made with no network."""
    made = write(world.work / "tasks.toml")
    found = providers().check_key(made.model)
    assert found.status == providers().NOT_SET
    ran = invoke(["run", "--yes"], prog=prog, monkeypatch=monkeypatch)
    assert ran.code == 1, ran
    lines = error_lines(ran)
    assert len(lines) == 1 and lines[0].startswith(f"error: {found.detail}"), ran
    assert ran.events == (), ran.events
    assert sorted(path.name for path in world.work.iterdir()) == ["tasks.toml"]
