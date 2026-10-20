"""What the command does in a fresh interpreter, frozen as tests.

The invariants are FD5.1's second half, FD5.8's question order, FD5.10, FD5.11, FD5.12, FD5.17's
fetch and FD5.21 of the front door's plan (spec §1.2 items 8 and 15, §3, §4.1, §4.7, §6.1, §8.1,
rules L4 and L16):
- **FD5.1** in a fresh interpreter, every verb's `--help`, the top-level help and `--version`
  import no `verifiers`, open no socket, and work without the tokenizer file;
- **FD5.21** with the tokenizer file absent, every command that needs it prints one `error:` line
  and a `next:` line, `<prog> doctor --fix`, exit 1, with no traceback; `init` still works, up to
  its fetch, and `doctor` says it is not ready, naming the file and the fix;
- **FD5.8** the tokenizer question comes first, and in a pseudo-terminal the questions' order and
  defaults are spec §6.1's; with the file fetched first, the cap's default is made from the plan's
  estimate;
- **FD5.17** `doctor --fix` fetches the tokenizer file and changes nothing else; a package folder
  the user cannot write is said, naming the file, with no traceback, by `doctor --fix` and by
  `init`;
- **FD5.10** a library call that raises `RuntimeError` gives one line naming a log file that holds
  the traceback, exit 3; `--debug` prints the traceback too;
- **FD5.11** a closed stdout pipe, and `PYTHONIOENCODING=ascii`, give no traceback;
- **FD5.12** `python -m poisson_tasks` gives the same stdout and exit code as the console script,
  over a corpus.

A copy of the package without its tokenizer file is put first on `PYTHONPATH` (FD2's way): the
copy's `poisson_tasks` is the one imported.  A fetch never leaves the machine: the child serves
this checkout's file in place of `tiktoken`'s download (`tests/fd5_child.py`).

Shapes decided here
-------------------

**1. The console script** is what pip writes for `poisson-tasks = "poisson_tasks.cli:main"`:
`sys.argv[0]` the script's path, then `sys.exit(main())`.  So `main()` with no prog names the
command as `python -m poisson_tasks` does.  Whether the `[project.scripts]` line lands with the
command or with the packaging module is a yes/no; this test writes the wrapper itself.

**2. An unexpected failure's log** is a file the `error:` line names by its path; where it is
kept is the build's.
"""

from __future__ import annotations

import os
import pty
import re
import select
import shutil
import stat
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from tests.fd5_support import (
    PROGS,
    VERBS,
    World,
    bare_package,
    base_env,
    config,
    error_lines,
    fresh,
    next_commands,
    package_copy,
    patch_everywhere,
    prog,
    runs,
    tokenizer_file,
    world,
    invoke,
)

__all__ = ["prog", "world", "bare_package"]

DASHED = PROGS[0]

HELPS = [["--help"], ["--version"], *[[verb, "--help"] for verb in VERBS]]


@pytest.mark.parametrize("argv", HELPS, ids=[" ".join(argv) for argv in HELPS])
def test_fd5_1_help_imports_no_verifiers_opens_no_socket_and_needs_no_tokenizer(
    argv: list[str], prog: str, world: World, bare_package: Path
) -> None:
    ran = fresh(argv, prog=prog, world=world, package_root=bare_package,
                job={"package_must_be": str(bare_package)})
    assert ran.code == 0, ran
    assert ran.out.strip(), ran
    assert ran.err == "", ran
    assert not [name for name in ran.record["modules"]
                if name == "verifiers" or name.startswith("verifiers.")], "verifiers imported"
    assert ran.record["events"] == [], ran.record["events"]


# ---------------------------------------------------------------------------
# FD5.21 no tokenizer
# ---------------------------------------------------------------------------


def write(world: World, flags: list[str]) -> None:
    made = config().config_from_init_args(flags)
    (world.work / "tasks.toml").write_text(config().dump_config(made), encoding="utf-8")


NEEDS_TOKENIZER = {
    "generate": ["generate", "--arm", "depth:d1", "--tasks-per-level", "1"],
    "generate-from-the-file": ["generate"],
    "run": ["run", "--yes"],
    "run-dry": ["run", "--dry-run", "--offline"],
    "verify": ["verify", "--arm", "depth:d1", "--task", "1", "--self-check"],
    "export": ["export", "--to", "verifiers"],
    "card": ["card"],
    "card-published": ["card", "--published"],
}


@pytest.mark.parametrize("name", list(NEEDS_TOKENIZER))
def test_fd5_21_a_command_that_needs_the_tokenizer_says_so_and_how_to_fix_it(
    name: str, prog: str, world: World, bare_package: Path
) -> None:
    write(world, ["--tasks-per-level", "1"])
    before = sorted(p.name for p in world.work.iterdir())
    ran = fresh(NEEDS_TOKENIZER[name], prog=prog, world=world, package_root=bare_package,
                job={"package_must_be": str(bare_package)})
    assert ran.code == 1, ran
    assert ran.out == "", ran
    assert len(error_lines(ran)) == 1 and ran.err_lines[0].startswith("error: "), ran
    assert next_commands(ran.err) == [f"{prog} doctor --fix"], ran
    assert "Traceback" not in ran.err
    assert sorted(p.name for p in world.work.iterdir()) == before


def test_fd5_21_init_still_writes_the_file_without_the_tokenizer(
    prog: str, world: World, bare_package: Path
) -> None:
    ran = fresh(["init", "--yes", "--no-fetch", "--no-check-key"], prog=prog, world=world,
                package_root=bare_package)
    assert ran.code == 0, ran
    assert (world.work / "tasks.toml").read_text(encoding="utf-8") == config().dump_config(
        config().config_from_init_args([]))
    assert "Traceback" not in ran.err


def test_fd5_21_doctor_is_not_ready_and_names_the_file_and_the_fix(
    prog: str, world: World, bare_package: Path
) -> None:
    ran = fresh(["doctor", "--offline"], prog=prog, world=world, package_root=bare_package)
    assert ran.code == 4, ran
    assert ran.out.startswith("not ready  "), ran
    path = os.path.join(os.path.realpath(bare_package / "poisson_tasks" / "data"),
                        "o200k_base.tiktoken")
    lines = [line for line in ran.out.splitlines() if path in line]
    assert lines and any(f"{prog} doctor --fix" in line for line in lines), ran


# ---------------------------------------------------------------------------
# fetching the tokenizer
# ---------------------------------------------------------------------------


def served() -> dict[str, Any]:
    return {"serve_tokenizer": str(tokenizer_file())}


def snapshot(*roots: Path) -> dict[str, int]:
    out = {}
    for root in roots:
        for path in root.rglob("*"):
            if path.is_file():
                out[str(path)] = path.stat().st_size
    return out


def test_fd5_17_doctor_fix_fetches_the_tokenizer_and_changes_nothing_else(
    prog: str, world: World, tmp_path: Path
) -> None:
    root = package_copy(tmp_path / "copy")
    target = root / "poisson_tasks" / "data" / "o200k_base.tiktoken"
    before = snapshot(world.work, world.home, root)
    ran = fresh(["doctor", "--fix", "--yes", "--offline"], prog=prog, world=world,
                package_root=root, job={**served(), "package_must_be": str(root)})
    assert ran.code == 0, ran
    assert ran.out.startswith("ok  "), ran
    assert target.read_bytes() == tokenizer_file().read_bytes()
    assert os.path.realpath(target) in ran.out or str(target) in ran.out, ran
    assert len(ran.record["fetched"]) == 1
    after = snapshot(world.work, world.home, root)
    assert {path for path in after if path not in before} == {str(target)}
    assert all(after[path] == size for path, size in before.items())


def test_fd5_8_init_fetches_the_tokenizer_first_and_the_caps_default_is_from_the_estimate(
    prog: str, world: World, tmp_path: Path
) -> None:
    root = package_copy(tmp_path / "copy", cards=True)
    flags = ["--recipe", "card"]
    ran = fresh(["init", "--yes", "--no-check-key", *flags], prog=prog, world=world,
                package_root=root, job=served())
    assert ran.code == 0, ran
    fetched = root / "poisson_tasks" / "data" / "o200k_base.tiktoken"
    assert fetched.is_file()
    assert os.path.realpath(fetched) in ran.out or str(fetched) in ran.out, ran
    made = config().config_from_init_args(flags)
    estimate = runs().estimate(config().resolve_plan(made))
    expected = config().config_from_init_args(flags, expected_dollars=estimate.dollars_expected)
    assert expected.limits.spend_usd != config().config_from_init_args(flags).limits.spend_usd
    assert (world.work / "tasks.toml").read_text(encoding="utf-8") == config().dump_config(
        expected)


@pytest.mark.skipif(os.geteuid() == 0, reason="root can write any folder")
@pytest.mark.parametrize("verb", ["doctor", "init"])
def test_fd5_17_a_package_folder_the_user_cannot_write_is_said_naming_the_file(
    verb: str, prog: str, world: World, tmp_path: Path
) -> None:
    root = package_copy(tmp_path / "copy")
    data = root / "poisson_tasks" / "data"
    data.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        argv = (["doctor", "--fix", "--yes", "--offline"] if verb == "doctor"
                else ["init", "--yes", "--no-check-key"])
        ran = fresh(argv, prog=prog, world=world, package_root=root, job=served())
    finally:
        data.chmod(stat.S_IRWXU)
    path = os.path.join(os.path.realpath(data), "o200k_base.tiktoken")
    assert ran.code == (4 if verb == "doctor" else 0), ran
    assert path in ran.out + ran.err, ran
    assert "Traceback" not in ran.err and "Traceback" not in ran.out
    assert not (data / "o200k_base.tiktoken").exists()
    if verb == "init":
        assert (world.work / "tasks.toml").read_text(encoding="utf-8") == config().dump_config(
            config().config_from_init_args([]))


# ---------------------------------------------------------------------------
# FD5.8 the questions in a pseudo-terminal
# ---------------------------------------------------------------------------


def converse(argv: list[str], prog: str, world: World, root: Path,
             timeout: float = 300) -> tuple[int, str]:
    """Run the command on a pseudo-terminal and press Enter whenever its output has been quiet
    for a second and a half, as a person taking every default would, at most forty times.  The
    terminal's side is held open until everything is read (macOS throws a closed terminal's
    buffer away)."""
    import json

    from tests.fd5_support import CHILD

    work = world.tmp / "pty-job"
    work.mkdir()
    job = work / "job.json"
    job.write_text(json.dumps({"argv": argv, "prog": prog, "record": str(work / "record.json"),
                               **served()}), encoding="utf-8")
    master, slave = pty.openpty()
    env = base_env(world, {"PYTHONPATH": str(root)})
    process = subprocess.Popen([sys.executable, "-P", str(CHILD), str(job)], cwd=world.work,
                               env=env, stdin=slave, stdout=slave, stderr=slave,
                               start_new_session=True)
    transcript = b""
    deadline = time.monotonic() + timeout
    quiet_since = time.monotonic()
    presses = 0
    try:
        while time.monotonic() < deadline:
            ready, _, _ = select.select([master], [], [], 0.25)
            if ready:
                try:
                    chunk = os.read(master, 65536)
                except OSError:
                    chunk = b""
                transcript += chunk
                quiet_since = time.monotonic()
                continue
            if process.poll() is not None:
                break
            if time.monotonic() - quiet_since > 1.5 and presses < 40:
                os.write(master, b"\n")
                presses += 1
                quiet_since = time.monotonic()
        process.wait(30)
        while True:
            ready, _, _ = select.select([master], [], [], 0.2)
            if not ready:
                break
            try:
                chunk = os.read(master, 65536)
            except OSError:
                break
            if not chunk:
                break
            transcript += chunk
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(10)
        os.close(slave)
        os.close(master)
    return process.returncode, transcript.decode("utf-8", "replace").replace("\r", "")


def defaults(transcript: str) -> list[str]:
    """Each default in brackets, in the order the questions showed them, from any line."""
    return re.findall(r"\[([^\[\]\n]*)\]", transcript)


def test_fd5_8_in_a_terminal_the_questions_come_in_spec_6_1s_order_with_its_defaults(
    prog: str, world: World, tmp_path: Path
) -> None:
    root = package_copy(tmp_path / "copy", cards=True)
    code, transcript = converse(["init"], prog, world, root)
    assert code == 0, transcript
    found = defaults(transcript)
    expected: list[Callable[[str], bool]] = [
        lambda d: d.lower() == "y/n",
        lambda d: d == "1",  # G7 (FD9 Session A): built-in tasks or your own tools
        lambda d: d == "1",
        lambda d: d == "gpt-5-nano-2025-08-07",
        lambda d: d == "OPENAI_API_KEY",
        lambda d: "0.05" in d and "0.005" in d and "0.40" in d,
        lambda d: d == "1",
        lambda d: d == "10",
        lambda d: d == "1",
        lambda d: "1.00" in d,
    ]
    assert len(found) == len(expected), found
    for index, (default, check) in enumerate(zip(found, expected, strict=True)):
        assert check(default), (index, default, found)
    assert (world.work / "tasks.toml").is_file()


# ---------------------------------------------------------------------------
# FD5.10 an unexpected failure
# ---------------------------------------------------------------------------

FAILING = {
    "init": (["init", "--yes", "--no-check-key", "--force"], "poisson_tasks.config",
             "config_from_init_args"),
    "generate": (["generate", "--arm", "depth:d1", "--tasks-per-level", "1"],
                 "poisson_tasks.tasks", "generate"),
    "run": (["run", "--dry-run", "--offline"], "poisson_tasks.runs", "find_run"),
    "card": (["card", "--published"], "poisson_tasks.cards", "recompute"),
    "verify": (["verify", "--arm", "depth:d1", "--task", "1", "--self-check"],
               "poisson_tasks.tasks", "verify"),
    "export": (["export", "--to", "verifiers"], "poisson_tasks.runs", "verifiers_config"),
    "doctor": (["doctor", "--offline"], "poisson_tasks.providers", "environment_report"),
}

SENTINEL_TEXT = "an-unexpected-failure-for-the-test"


def logs_named(line: str) -> list[Path]:
    return [Path(word.rstrip(".;,)")) for word in line.split()
            if os.path.isabs(word.rstrip(".;,)")) and Path(word.rstrip(".;,)")).is_file()]


@pytest.mark.parametrize("verb", list(FAILING))
@pytest.mark.parametrize("debug", [False, True], ids=["plain", "debug"])
def test_fd5_10_an_unexpected_failure_is_one_line_naming_a_log_and_exit_3(
    verb: str, debug: bool, prog: str, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    write(world, ["--tasks-per-level", "1"])
    argv, module, name = FAILING[verb]

    def fails(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError(SENTINEL_TEXT)

    import importlib

    importlib.import_module("poisson_tasks.cli")
    importlib.import_module(module)
    patch_everywhere(monkeypatch, module, name, fails)
    ran = invoke([*argv, *(["--debug"] if debug else [])], prog=prog, monkeypatch=monkeypatch)
    assert ran.code == 3, ran
    lines = error_lines(ran)
    assert len(lines) == 1, ran
    assert "RuntimeError" in lines[0], ran
    logs = logs_named(lines[0])
    assert len(logs) == 1, lines
    held = logs[0].read_text(encoding="utf-8")
    assert "Traceback" in held and SENTINEL_TEXT in held
    if debug:
        assert "Traceback" in ran.err and SENTINEL_TEXT in ran.err
    else:
        assert "Traceback" not in ran.err and SENTINEL_TEXT not in ran.err + ran.out


# ---------------------------------------------------------------------------
# FD5.11 pipes and encodings
# ---------------------------------------------------------------------------

PIPED = [["--help"], ["doctor", "--offline"],
         ["generate", "--arm", "depth:d1", "--tasks-per-level", "60", "--print"]]


def python_m(argv: list[str], world: World, **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
    env = base_env(world, kwargs.pop("env", None))
    return subprocess.run([sys.executable, "-m", "poisson_tasks", *argv], cwd=world.work,
                          env=env, capture_output=True, timeout=600, check=False,
                          stdin=subprocess.DEVNULL, **kwargs)


@pytest.mark.parametrize("argv", PIPED, ids=[" ".join(argv[:2]) for argv in PIPED])
def test_fd5_11_a_closed_stdout_pipe_gives_no_traceback(argv: list[str], world: World) -> None:
    env = base_env(world)
    process = subprocess.Popen([sys.executable, "-m", "poisson_tasks", *argv], cwd=world.work,
                               env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
    assert process.stdout is not None and process.stderr is not None
    process.stdout.close()
    err = process.stderr.read().decode("utf-8", "replace")
    process.wait(600)
    assert "Traceback" not in err and "Exception ignored" not in err, err
    assert process.returncode in (0, 1, 3, -13, 141), (process.returncode, err)


ASCII = [["run", "--dry-run", "--offline"], ["card", "--published"], ["doctor", "--offline"],
         ["generate", "--arm", "depth:d3", "--show", "--task", "1"]]


@pytest.mark.parametrize("argv", ASCII, ids=[" ".join(argv[:2]) for argv in ASCII])
def test_fd5_11_an_ascii_only_stdout_gives_no_traceback_and_the_same_verdict(
    argv: list[str], world: World
) -> None:
    write(world, ["--tasks-per-level", "2"])
    utf8 = python_m(argv, world, env={"PYTHONIOENCODING": "utf-8"})
    ascii_ = python_m(argv, world, env={"PYTHONIOENCODING": "ascii"})
    assert ascii_.returncode == utf8.returncode, ascii_.stderr.decode()
    assert utf8.stdout.strip(), utf8.stderr.decode()
    assert b"Traceback" not in ascii_.stderr
    assert all(byte < 128 for byte in ascii_.stdout)
    assert ascii_.stdout.decode().split("  ", 1)[0] == utf8.stdout.decode().split("  ", 1)[0]
    assert len(ascii_.stdout.splitlines()) == len(utf8.stdout.splitlines())


# ---------------------------------------------------------------------------
# FD5.12 python -m is the console script
# ---------------------------------------------------------------------------

CORPUS = [["--help"], ["--version"], ["nope"], ["doctor", "--offline"],
          ["doctor", "--show-command"], ["init"],
          ["generate", "--arm", "depth:d1", "--tasks-per-level", "2", "--print"],
          ["verify", "--arm", "depth:d2", "--task", "4", "--self-check"],
          ["run", "--dry-run", "--offline"], ["card", "--published", "nope"]]


def console_script(world: World) -> Path:
    """The script pip writes for `poisson-tasks = "poisson_tasks.cli:main"`."""
    folder = world.tmp / "bin"
    folder.mkdir(exist_ok=True)
    script = folder / DASHED
    script.write_text(
        f"#!{sys.executable}\n"
        "import re\nimport sys\nfrom poisson_tasks.cli import main\n"
        "if __name__ == '__main__':\n"
        "    sys.argv[0] = re.sub(r'(-script\\.pyw|\\.exe)?$', '', sys.argv[0])\n"
        "    sys.exit(main())\n", encoding="utf-8")
    script.chmod(0o755)
    return script


@pytest.mark.parametrize("argv", CORPUS, ids=[" ".join(argv[:2]) for argv in CORPUS])
def test_fd5_12_python_m_gives_the_console_scripts_stdout_and_exit_code(
    argv: list[str], world: World
) -> None:
    write(world, ["--tasks-per-level", "2"])
    script = console_script(world)
    env = base_env(world)
    one = subprocess.run([sys.executable, "-m", "poisson_tasks", *argv], cwd=world.work,
                         env=env, capture_output=True, timeout=600, check=False,
                         stdin=subprocess.DEVNULL)
    two = subprocess.run([sys.executable, str(script), *argv], cwd=world.work, env=env,
                         capture_output=True, timeout=600, check=False,
                         stdin=subprocess.DEVNULL)
    assert one.returncode == two.returncode, (one, two)
    assert one.stdout == two.stdout
    assert one.stderr == two.stderr
    shutil.rmtree(world.tmp / "bin")


def test_fd5_18_a_published_card_that_no_longer_rebuilds_is_a_check_not_passed(
    prog: str, world: World, tmp_path: Path
) -> None:
    """`card --published` recomputes each published card byte for byte (spec §4.4): one byte
    changed in one card's `artifact.json` makes that check fail, exit 4 (spec §11.2: a check you
    asked for did not pass); the other card, named alone, still passes."""
    from tests.fd5_support import cards

    root = package_copy(tmp_path / "copy", cards=True, tokenizer=True)
    found = cards().published(root.parent / "calibration")
    assert len(found) >= 2
    changed = found[0].folder / "artifact.json"
    blob = bytearray(changed.read_bytes())
    at = next(i for i, byte in enumerate(blob) if chr(byte).isdigit() and i > 200)
    blob[at] = ord("7") if chr(blob[at]) != "7" else ord("3")
    changed.write_bytes(bytes(blob))
    every = fresh(["card", "--published"], prog=prog, world=world, package_root=root)
    assert every.code == 4, every
    assert "Traceback" not in every.err
    alone = fresh(["card", "--published", found[1].name], prog=prog, world=world,
                  package_root=root)
    assert alone.code == 0, alone
    broken = fresh(["card", "--published", found[0].name], prog=prog, world=world,
                   package_root=root)
    assert broken.code == 4, broken


def test_fd5_19_an_install_without_the_cards_shows_the_plan_and_says_why_no_estimate(
    prog: str, world: World, tmp_path: Path
) -> None:
    """Ruled yes 2026-10-05 (FD3 Session A's yes/no 5): until the cards ship in the package, an
    install without them refuses the estimate in one line that says so; the plan is still
    shown."""
    root = package_copy(tmp_path / "copy", tokenizer=True)
    write(world, ["--tasks-per-level", "1"])
    ran = fresh(["run", "--dry-run", "--offline"], prog=prog, world=world, package_root=root)
    assert ran.code == 0, ran
    assert ran.out.startswith("plan  "), ran
    notes = [line for line in ran.err_lines if line.startswith("note: ")]
    assert len(notes) == 1, ran
    assert "Traceback" not in ran.err


def test_fd5_18_card_help_lists_the_published_cards_without_the_tokenizer(
    prog: str, world: World, tmp_path: Path
) -> None:
    """FD5.1 and FD5.18 together: in an install with the published cards and no tokenizer file,
    `card --help` lists every card's name, importing no `verifiers`."""
    from tests.fd5_support import cards

    root = package_copy(tmp_path / "copy", cards=True)
    names = [card.name for card in cards().published(root.parent / "calibration")]
    ran = fresh(["card", "--help"], prog=prog, world=world, package_root=root)
    assert ran.code == 0, ran
    for name in names:
        assert name in ran.out, (name, ran)
    assert not [m for m in ran.record["modules"] if m == "verifiers" or m.startswith("verifiers.")]

