"""Shared ground for FD5's tests, the command a user types: frozen with them.

**The command's name is not final.**  `PROGS` below is the one place it is written: the first is
the console script's name and `python -m poisson_tasks`'s, the second the shared command's form.
A rename is that one line.  Every test that drives the command runs once under each (FD5.6), and
every command the output names must start with the prog under test.

**How the command is driven.**  Most tests call `cli.main(argv, prog=PROG)` in this process
(`invoke`), with stdout, stderr and stdin swapped for streams the test owns: stdout and stderr are
not terminals, and stdin is one that fails the test if it is read, unless the test gives answers.
What a fresh interpreter must show (no `verifiers` imported by `--help`, no socket, no tokenizer,
`python -m`, a closed pipe, an ASCII-only stream, a pseudo-terminal, Ctrl-C) runs in a process of
its own through `tests/fd5_child.py`.

**Each test has its own world** (`world`): its own `HOME`, working folder and `TMPDIR`, colour off
(`NO_COLOR=1`, `TERM=dumb`) and a fixed width (`COLUMNS=100`), and no provider variable, no
variable whose name holds `API_KEY`, `TOKEN` or `SECRET`, and no proxy from the shell that started
the suite.  One thing is shared on purpose: `UV_CACHE_DIR` is the cache of the user running the
suite, so a run in a home of its own does not fetch the harness's packages again (FD3's child does
the same); the harness writes there, outside the test's world.

**How the command reads stdin** (a shape the fakes hold it to): `sys.stdin.isatty()` and
`sys.stdin.readline()`, as `input()` does.  A fake terminal has no file descriptor, so a build that
reads the terminal through `os.isatty(fileno)`, `termios` or `getpass` fails these tests.  Every in-process call is made inside FD2's network guard,
so nothing leaves the machine; runs go to the fixture model on loopback.

**The look is not ruled** (`evidence/cli-look-mockups/yes-nos.md`).  So these tests pin what is
said and when: the verdict word and the facts on a line, the order of lines, exit codes, which
stream, and what is written to disk.  They pin no colour, no spacing beyond the verdict line's two
spaces (FD5.5's own pattern), no symbol and no table layout.  An equivalent command may be printed
on one line or broken before its flags with a backslash; `printed_command` reads either.

**What every expectation is computed from**: the library's public functions, the plan, the files
on disk or the fixture's own count; never the command under test.
"""

from __future__ import annotations

import dataclasses
import http.client
import importlib
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import tomllib
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from tests.fd2_fakes import KEY_BODY, SENTINEL, network_guard
from tests.fd3_support import KEY, KEY_VAR, PRICE_FIELDS
from tests.helpers import INTERNAL
from tests.keymask_support import key_runs, masked_runs

REPO = Path(__file__).resolve().parents[1]
CHILD = Path(__file__).with_name("fd5_child.py")

# The command's names: the console script's (and `python -m poisson_tasks`'s) first, then the
# shared command's.  The one line a rename changes.
PROGS = ("poisson-tasks", "poisson tasks")

DISTRIBUTION = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["project"][
    "name"
]
"""The distribution's name, as `pyproject.toml` declares it: the first word of `--version`."""

VERBS = ("init", "generate", "run", "card", "verify", "export", "doctor")

TASK_OUTCOMES = (
    "verifier_error", "replay_mismatch", "api_error", "wall_timeout", "malformed_call",
    "turn_limit", "overshoot", "wrong_state", "collateral_mutation", "passed",
)
"""`tasks.OUTCOMES`, written out so this module imports nothing that needs the tokenizer."""

VERDICTS: dict[str, frozenset[str]] = {
    "init": frozenset({"ok"}),
    "generate": frozenset({"ok"}),
    "run": frozenset({"plan", "done", "stopped"}),
    "card": frozenset({"ok", "refused"}),
    "verify": frozenset({*TASK_OUTCOMES, "ok"}),
    "export": frozenset({"ok"}),
    "doctor": frozenset({"ok", "not ready"}),
}
"""FD5.5's table: the words a verb's first line may carry on success."""

VERDICT_LINE = re.compile(r"^([a-z][a-z_ ]*)  (\S.*)$")
"""FD5.5's pattern, with the word and the sentence as groups, and with `_` in the word: the plan's
pattern, `^[a-z][a-z ]*  \\S`, refuses five of the outcome labels spec §4.5 makes `verify`'s
verdict words (`wrong_state` and the rest).  The spec wins; this is reported as a plan defect."""

EXIT_CODES = frozenset({0, 1, 2, 3, 4, 130})

REPR = re.compile(
    r"Traceback \(most recent call last\)"
    r"|<[A-Za-z_][\w.]* object at 0x"
    r"|\b(?:Posix|Windows)?Path\('"
    r"|\b[A-Z]\w*(?:Error|Exception)\("
    r"|\('[^']*', "
    r"|\['[^']*'(?:, |\])"
    r"|\{'[^']*': "
    r"|\bdict_(?:keys|values|items)\("
    r"|\bmappingproxy\("
    r"|\bNone\b(?=[,)\]])"
)
"""A Python repr or a traceback, in text a user reads (L4)."""

MORE_INTERNAL = re.compile(r"\b(?:FD|PT|CAL)\d|\bK\d+\b|\bL1?\d\b(?! tokens)|\bP-\d\b")
"""The front door's own ids, which `helpers.INTERNAL` predates (L11)."""


# ---------------------------------------------------------------------------
# the modules under test, reached at call time so a missing one fails one test
# ---------------------------------------------------------------------------


def cli() -> Any:
    return importlib.import_module("poisson_tasks.cli")


def config() -> Any:
    return importlib.import_module("poisson_tasks.config")


def providers() -> Any:
    return importlib.import_module("poisson_tasks.providers")


def runs() -> Any:
    return importlib.import_module("poisson_tasks.runs")


def calibration() -> Any:
    return importlib.import_module("poisson_tasks.calibration")


def tasks() -> Any:
    return importlib.import_module("poisson_tasks.tasks")


def arms() -> Any:
    return importlib.import_module("poisson_tasks.arms")


def knobs() -> Any:
    return importlib.import_module("poisson_tasks.knobs")


def export() -> Any:
    return importlib.import_module("poisson_tasks.export")


def cards() -> Any:
    return importlib.import_module("poisson_tasks.cards")


def outcomes() -> Any:
    return importlib.import_module("poisson_tasks.outcomes")


# ---------------------------------------------------------------------------
# a world of the test's own
# ---------------------------------------------------------------------------

_SHELL_VARIABLES = (
    "OPENAI_BASE_URL", "CI",
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy",
    "PYTHONIOENCODING", "FORCE_COLOR", "CLICOLOR_FORCE",
)


_SECRET = re.compile(r"API_KEY|TOKEN|SECRET", re.IGNORECASE)
MADE_UP_KEYS = frozenset({KEY, SENTINEL})
"""The tests' own keys (FD3's and FD2's), the only values a key variable may hold in a test."""

SECRET_PARTS = {KEY: KEY.removeprefix("sk-"), SENTINEL: KEY_BODY}
"""Each made-up key's secret part: what follows its public prefix (`sk-`, `sk-proj-`), written
out.  The leak rule (`tests/keymask_support.py`, ruled 2026-10-12): a key's public prefix is
not secret; no text the command prints or writes holds twelve characters in a row of the secret
part (`key_runs`); a text that can carry the key, `run.log` and the lines that quote the first
error or `run.log`, holds no four in a row (`masked_runs`)."""


@dataclasses.dataclass(frozen=True)
class World:
    home: Path
    work: Path
    tmp: Path


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> World:
    """The test's own `HOME`, working folder and `TMPDIR`, colour off and a fixed width."""
    cache = uv_cache()
    made = World(home=tmp_path / "home", work=tmp_path / "work", tmp=tmp_path / "tmp")
    for folder in (made.home, made.work, made.tmp):
        folder.mkdir()
    monkeypatch.setenv("HOME", str(made.home))
    monkeypatch.setenv("TMPDIR", str(made.tmp))
    monkeypatch.setattr(tempfile, "tempdir", None)
    monkeypatch.chdir(made.work)
    for name in [*_SHELL_VARIABLES, *(n for n in os.environ if _SECRET.search(n))]:
        if os.environ.get(name) not in MADE_UP_KEYS:
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv("TERM", "dumb")
    monkeypatch.setenv("COLUMNS", "100")
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    if cache is not None and "UV_CACHE_DIR" not in os.environ:
        monkeypatch.setenv("UV_CACHE_DIR", cache)
    return made


_UV_CACHE: list[str | None] = []


def uv_cache() -> str | None:
    """uv's cache folder for the user running the suite, so a run with a home of its own does
    not fetch the harness's packages again (FD3's child does the same)."""
    if not _UV_CACHE:
        uv = shutil.which("uv")
        found = None
        if uv is not None:
            done = subprocess.run([uv, "cache", "dir"], capture_output=True, text=True,
                                  check=False)
            found = done.stdout.strip() if done.returncode == 0 and done.stdout.strip() else None
        _UV_CACHE.append(found)
    return _UV_CACHE[0]


@pytest.fixture(params=PROGS, ids=["dashed", "spaced"])
def prog(request: pytest.FixtureRequest) -> str:
    """The prog under test: every test that drives the command runs under each (FD5.6)."""
    value: str = request.param
    return value


# ---------------------------------------------------------------------------
# stdin: none, answers, or a terminal's answers
# ---------------------------------------------------------------------------


class NoStdin(io.TextIOBase):
    """A stdin that is not a terminal and fails the test if anything reads it."""

    reads = 0

    def isatty(self) -> bool:
        return False

    def readable(self) -> bool:
        return True

    def read(self, size: int | None = -1) -> str:
        raise AssertionError("the command read stdin")

    def readline(self, size: int | None = -1) -> str:  # type: ignore[override]
        raise AssertionError("the command read stdin")

    def fileno(self) -> int:
        raise io.UnsupportedOperation("no file descriptor")


INTERRUPT = object()
"""In `Answers`, Ctrl-C at that question."""


class Answers(io.TextIOBase):
    """A terminal's stdin that answers each line read with the next of `answers` (an empty
    string is Enter; `INTERRUPT` is Ctrl-C), and Enter once they run out.  `reads` counts the
    lines read: the questions asked."""

    def __init__(self, answers: Sequence[Any] = (), *, tty: bool = True) -> None:
        self.answers = list(answers)
        self.reads = 0
        self.tty = tty

    def isatty(self) -> bool:
        return self.tty

    def readable(self) -> bool:
        return True

    def readline(self, size: int | None = -1) -> str:  # type: ignore[override]
        self.reads += 1
        answer = self.answers.pop(0) if self.answers else ""
        if answer is INTERRUPT:
            raise KeyboardInterrupt
        return str(answer) + "\n"

    def read(self, size: int | None = -1) -> str:
        return self.readline()

    def fileno(self) -> int:
        raise io.UnsupportedOperation("no file descriptor")


# ---------------------------------------------------------------------------
# one call of the command, in this process
# ---------------------------------------------------------------------------


class _Out(io.TextIOWrapper):
    def isatty(self) -> bool:
        return False


@dataclasses.dataclass(frozen=True)
class Ran:
    """What one call of the command did: its exit code, stdout and stderr, and the socket
    events it raised."""

    argv: tuple[str, ...]
    prog: str
    code: int
    out: str
    err: str
    events: tuple[tuple[str, Any], ...] = ()

    @property
    def lines(self) -> list[str]:
        return self.out.splitlines()

    @property
    def err_lines(self) -> list[str]:
        return self.err.splitlines()

    @property
    def first(self) -> str:
        return self.lines[0] if self.lines else ""

    @property
    def word(self) -> str | None:
        match = VERDICT_LINE.match(self.first)
        return match.group(1) if match else None

    @property
    def connections(self) -> list[Any]:
        return [address for kind, address in self.events if kind == "connect"]

    def __str__(self) -> str:
        return (f"argv {list(self.argv)} under {self.prog!r} exited {self.code}\n"
                f"--- stdout\n{self.out}--- stderr\n{self.err}")


def _code(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    return 1


def invoke(
    argv: Sequence[str],
    *,
    prog: str,
    monkeypatch: pytest.MonkeyPatch,
    stdin: io.TextIOBase | None = None,
    check: bool = True,
) -> Ran:
    """`cli.main(argv, prog=prog)` in this process, inside the network guard, with stdout and
    stderr captured as UTF-8 streams that are not terminals.

    Unless `check` is false, every call is held to the shared look (`conformance`) and searched
    for the tests' made-up keys (the leak rule, `SECRET_PARTS`), so every test that drives the
    command checks FD5.4 to FD5.6:
    except that a dialogue's questions go to stderr (stdin given as a terminal's answers), `--debug`
    prints a traceback, `--print` and `--json` make stdout data, and help and the version are not
    verdict lines."""
    main = cli().main
    out_bytes, err_bytes = io.BytesIO(), io.BytesIO()
    out = _Out(out_bytes, encoding="utf-8", newline="\n", write_through=True)
    err = _Out(err_bytes, encoding="utf-8", newline="\n", write_through=True)
    saved = sys.stdin, sys.stdout, sys.stderr
    sys.stdin = stdin if stdin is not None else NoStdin()
    sys.stdout, sys.stderr = out, err
    try:
        with network_guard(monkeypatch) as events:
            try:
                code = _code(main(list(argv), prog=prog))
            except SystemExit as stop:
                code = _code(stop.code)
    finally:
        out.flush()
        err.flush()
        sys.stdin, sys.stdout, sys.stderr = saved
    ran = Ran(
        argv=tuple(argv), prog=prog, code=code,
        out=out_bytes.getvalue().decode("utf-8"), err=err_bytes.getvalue().decode("utf-8"),
        events=tuple(events),
    )
    if check:
        held_to(ran, asked=isinstance(stdin, Answers))
    return ran


def held_to(ran: Ran, *, asked: bool = False) -> None:
    """The checks `invoke` makes of every call (see there)."""
    verb = next((word for word in ran.argv if word in VERBS), None)
    if {"--help", "-h", "--version"} & set(ran.argv):
        verb = None
    data = "--print" in ran.argv or "--json" in ran.argv
    problems = conformance(dataclasses.replace(ran, out="" if data else ran.out,
                                               err="" if asked else ran.err),
                           None if data else verb)
    if "--debug" in ran.argv:
        problems = [p for p in problems if not p.startswith("stderr")]
    assert not problems, "\n".join(problems) + f"\n{ran}"
    for text in (ran.out, ran.err):
        for secret in SECRET_PARTS.values():
            assert key_runs(text, secret) == [], f"a key leaked\n{ran}"


# ---------------------------------------------------------------------------
# reading what the command printed
# ---------------------------------------------------------------------------


def joined_lines(text: str) -> list[str]:
    """The text's lines, with a line that ends in a backslash joined to the next: an equivalent
    command may be printed broken before its flags (the look's yes/no 24)."""
    out: list[str] = []
    pending = ""
    for line in text.splitlines():
        if line.rstrip().endswith("\\"):
            pending += line.rstrip()[:-1].rstrip() + " "
            continue
        out.append(pending + (line.strip() if pending else line))
        pending = ""
    if pending:
        out.append(pending.rstrip())
    return out


def next_commands(text: str) -> list[str]:
    """Every command a `next:` line names, at the start of a line or indented."""
    found = []
    for line in joined_lines(text):
        match = re.match(r"^\s*next:\s+(.+?)\s*$", line)
        if match:
            found.append(match.group(1))
    return found


def printed_command(text: str, prog: str, verb: str) -> list[str] | None:
    """The argv of the first command printed in `text` that starts with `<prog> <verb>`, read
    as a shell reads it; a `next:` line is not one."""
    head = f"{prog} {verb}"
    for line in joined_lines(text):
        stripped = line.strip()
        if stripped.startswith("next:") or stripped.startswith("usage:"):
            continue
        at = stripped.find(head + " ")
        if at < 0 and stripped.endswith(head):
            at = stripped.find(head)
        if at >= 0:
            return shlex.split(stripped[at:])
    return None


def strip_prog(argv: Sequence[str], prog: str) -> list[str]:
    """An argv a command line names, without the prog's own words."""
    words = shlex.split(prog)
    assert list(argv[: len(words)]) == words, (argv, prog)
    return list(argv[len(words):])


def verdict_lines(out: str, verb: str) -> list[tuple[str, str]]:
    """Each line at the start of a line that is a verdict line with one of `verb`'s words, as
    (word, sentence).  For `card` and `generate`, whose summary may be followed by a document or
    a task after one empty line, only the lines before the first empty line are read."""
    found = []
    for line in out.splitlines():
        if not line.strip():
            if verb in ("card", "generate"):
                break
            continue
        match = VERDICT_LINE.match(line)
        if match and match.group(1) in VERDICTS[verb]:
            found.append((match.group(1), match.group(2)))
    return found


def stderr_conforms(err: str) -> list[str]:
    """The stderr lines that are none of: `error: …`, `note: …`, or a continuation or progress
    line indented two spaces (FD5.4)."""
    bad = []
    for line in err.splitlines():
        if not line:
            continue
        if line.startswith(("error: ", "note: ", "  ")):
            continue
        bad.append(line)
    return bad


def conformance(ran: Ran, verb: str | None) -> list[str]:
    """Every way `ran` breaks the shared look's checkable rules (FD5.4 to FD5.6), as reasons."""
    problems: list[str] = []
    for line in stderr_conforms(ran.err):
        problems.append(f"stderr line of no allowed kind: {line!r}")
    for text, where in ((ran.out, "stdout"), (ran.err, "stderr")):
        for line in text.splitlines():
            if REPR.search(line):
                problems.append(f"{where} holds a repr or a traceback: {line!r}")
            if INTERNAL.search(line) or MORE_INTERNAL.search(line):
                problems.append(f"{where} holds an internal id: {line!r}")
    for command in next_commands(ran.out + "\n" + ran.err):
        if not (command == ran.prog or command.startswith(ran.prog + " ")):
            problems.append(f"a next: command does not start with {ran.prog!r}: {command!r}")
    if ran.code not in EXIT_CODES:
        problems.append(f"exit code {ran.code} is not in the table")
    if ran.out and not VERDICT_LINE.match(ran.first) and verb is not None:
        problems.append(f"stdout's first line is not a verdict line: {ran.first!r}")
    if ran.code == 0 and verb is not None and ran.word not in VERDICTS[verb]:
        problems.append(f"{verb}'s success opens with {ran.word!r}, not one of its words")
    if ran.code in (1, 2) and not any(
        line.startswith("error: ") for line in ran.err_lines
    ) and not ran.out:
        problems.append("a refusal with nothing on stdout and no error: line")
    return problems


def assert_clean(
    ran: Any, verb: str | None, *folders: Path, quoted: Sequence[str] = ()
) -> None:
    """`ran` keeps the shared look's checkable rules (FD5.4 to FD5.6), and the leak rule holds
    (`SECRET_PARTS`): its output and every file under `folders` hold no twelve characters in a
    row of either made-up key's secret part; every `run.log` under `folders`, and the lines of
    the output `quoted` names (the first error, or `run.log`'s tail), hold no four."""
    problems = conformance(ran, verb) if isinstance(ran, Ran) else [
        f"stderr line of no allowed kind: {line!r}" for line in stderr_conforms(ran.err)]
    assert not problems, "\n".join(problems) + f"\n{ran}"
    texts = [ran.out, ran.err]
    carriers = list(quoted)
    for folder in folders:
        for path in Path(folder).rglob("*"):
            if path.is_file():
                text = path.read_bytes().decode("utf-8", "replace")
                texts.append(text)
                if path.name == "run.log":
                    carriers.append(text)
    for secret in SECRET_PARTS.values():
        for text in texts:
            assert key_runs(text, secret) == [], "a key leaked"
        for text in carriers:
            assert masked_runs(text, secret) == [], "a key leaked where a provider can put it"


def error_lines(ran: Any) -> list[str]:
    return [line for line in ran.err_lines if line.startswith("error: ")]


def strict_json(text: str) -> Any:
    """One strict JSON document: `NaN`, `Infinity` and `-Infinity` refused."""
    def refuse(constant: str) -> Any:
        raise ValueError(f"{constant} is not strict JSON")

    return json.loads(text, parse_constant=refuse)


def json_keys(text: str) -> list[str]:
    """The top-level keys of a JSON object, in the order written."""
    pairs: list[str] = []

    def hook(items: list[tuple[str, Any]]) -> dict[str, Any]:
        nonlocal pairs
        pairs = [key for key, _ in items]
        return dict(items)

    json.loads(text, object_pairs_hook=hook)
    return pairs


def leaked(text: str, key: str) -> list[str]:
    """Every four characters in a row of `key` that `text` holds."""
    return sorted({key[i:i + 4] for i in range(len(key) - 3) if key[i:i + 4] in text})


def tree(root: Path) -> dict[str, bytes | None]:
    """Every file under `root` with its bytes, and every folder, as `None`."""
    out: dict[str, bytes | None] = {}
    if not root.exists():
        return out
    for path in sorted(root.rglob("*")):
        out[str(path.relative_to(root))] = path.read_bytes() if path.is_file() else None
    return out


# ---------------------------------------------------------------------------
# settings files, made by the library
# ---------------------------------------------------------------------------

FIXTURE_PRICE = (
    f"{PRICE_FIELDS['input']},{PRICE_FIELDS['cached_input']},{PRICE_FIELDS['output']}"
)


def fixture_flags(
    base_url: str,
    *,
    model: str = "fixture-reference",
    recipe: str = "custom",
    levels: str = "1",
    tasks_per_level: int | None = 1,
    seeds: str | None = None,
    attempts: int = 1,
    priced: bool = True,
    spend_cap: float | None = 100.0,
    token_cap: int | None = None,
    concurrency: int = 4,
    provider: str = "openai",
    key_var: str = KEY_VAR,
    extra: Sequence[str] = (),
) -> list[str]:
    """`init`'s flags for a plan against the fixture model: depth at the given levels by
    default, one task, one attempt, the fixture's prices, a cap no test reaches.  The provider is
    the OpenAI preset at the fixture's URL by default, whose free key check asks for the model by
    name, which the fixture answers for every name but `fixture-401`."""
    flags = ["--provider", provider, "--model", model, "--base-url", base_url,
             "--api-key-env", key_var, "--recipe", recipe]
    if recipe == "custom":
        flags += ["--knob", "depth", "--levels", levels]
    if seeds is not None:
        flags += ["--seeds", seeds]
    elif tasks_per_level is not None:
        flags += ["--tasks-per-level", str(tasks_per_level)]
    flags += ["--attempts", str(attempts), "--concurrency", str(concurrency)]
    if priced:
        flags += ["--price", FIXTURE_PRICE, "--price-read-on", str(PRICE_FIELDS["read_on"])]
        if spend_cap is not None:
            flags += ["--spend-cap", str(spend_cap)]
    else:
        flags += ["--no-price"]
    if token_cap is not None:
        flags += ["--token-cap", str(token_cap)]
    return flags + list(extra)


def write_config(path: Path, flags: Sequence[str]) -> Any:
    """`tasks.toml` at `path` as `config` writes it for these flags; returns the config."""
    made = config().config_from_init_args(list(flags))
    path.write_text(config().dump_config(made), encoding="utf-8")
    return made


def plan_of(path: Path) -> Any:
    return config().resolve_plan(config().load_config(path))


# ---------------------------------------------------------------------------
# patching a library name wherever a module bound it
# ---------------------------------------------------------------------------


def patch_everywhere(
    monkeypatch: pytest.MonkeyPatch, module: str, name: str, value: Any
) -> None:
    """Replace `module.name` with `value`, and every binding of the same object that a loaded
    `poisson_tasks` module made with `from module import name`, so the command meets `value`
    however it imported the name."""
    source = importlib.import_module(module)
    original = getattr(source, name)
    monkeypatch.setattr(source, name, value)
    for loaded_name, loaded in list(sys.modules.items()):
        if not loaded_name.startswith("poisson_tasks") or loaded is None or loaded is source:
            continue
        for attribute, bound in list(vars(loaded).items()):
            if bound is original:
                monkeypatch.setattr(loaded, attribute, value)


# ---------------------------------------------------------------------------
# every file opened, while a test asks
# ---------------------------------------------------------------------------

_OPENS: list[list[str]] = []


def _open_hook(event: str, args: tuple[Any, ...]) -> None:
    if _OPENS and event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
        _OPENS[-1].append(os.path.abspath(os.fsdecode(args[0])))


sys.addaudithook(_open_hook)


@contextmanager
def recording_opens() -> Iterator[list[str]]:
    """Every path opened, for reading or writing, while active."""
    paths: list[str] = []
    _OPENS.append(paths)
    try:
        yield paths
    finally:
        _OPENS.remove(paths)


# ---------------------------------------------------------------------------
# a provider whose key check cannot tell
# ---------------------------------------------------------------------------


class NotCheckable:
    """A front for the fixture model that answers every GET with 503, so the free key check
    can say nothing about the key, and passes every POST on to the fixture."""

    def __init__(self, upstream_port: int) -> None:
        self.gets = 0
        front = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, format: str, *args: Any) -> None:
                pass

            def do_GET(self) -> None:
                front.gets += 1
                body = b'{"error": {"message": "unavailable"}}'
                self.send_response(503)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self) -> None:
                length = int(self.headers.get("content-length") or 0)
                body = self.rfile.read(length)
                upstream = http.client.HTTPConnection("127.0.0.1", upstream_port, timeout=60)
                headers = {k: v for k, v in self.headers.items() if k.lower() != "host"}
                upstream.request("POST", self.path, body=body, headers=headers)
                answer = upstream.getresponse()
                data = answer.read()
                self.send_response(answer.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                upstream.close()

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, args=(0.05,),
                                        daemon=True)
        self._thread.start()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}/v1"

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(10)


# ---------------------------------------------------------------------------
# a fresh interpreter
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Fresh:
    """What a command run in a fresh interpreter did."""

    code: int
    out: str
    err: str
    record: dict[str, Any]

    @property
    def lines(self) -> list[str]:
        return self.out.splitlines()

    @property
    def err_lines(self) -> list[str]:
        return self.err.splitlines()

    def __str__(self) -> str:
        return f"exited {self.code}\n--- stdout\n{self.out}--- stderr\n{self.err}"


def base_env(world: World, extra: Mapping[str, str] | None = None) -> dict[str, str]:
    """A child's environment: this one's, less the shell's provider variables and proxies, with
    the world's home and temporary folder, colour off and a fixed width."""
    env = {name: value for name, value in os.environ.items()
           if name not in _SHELL_VARIABLES and name != "PYTHONPATH"
           and (not _SECRET.search(name) or value in MADE_UP_KEYS)}
    cache = uv_cache()
    if cache is not None and "UV_CACHE_DIR" not in env:
        env["UV_CACHE_DIR"] = cache
    env.update({
        "HOME": str(world.home), "TMPDIR": str(world.tmp), "NO_COLOR": "1", "TERM": "dumb",
        "COLUMNS": "100", "NO_PROXY": "127.0.0.1,localhost", "PYTHONUNBUFFERED": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    env.update(extra or {})
    return env


def fresh(
    argv: Sequence[str],
    *,
    prog: str,
    world: World,
    package_root: Path | None = None,
    job: Mapping[str, Any] | None = None,
    env: Mapping[str, str] | None = None,
    stdin: bytes | None = None,
    timeout: float = 600,
) -> Fresh:
    """`cli.main(argv, prog=prog)` in a fresh interpreter, through `tests/fd5_child.py`, with
    `package_root` first on the path when given (a copy of the package), the network refused off
    the machine, and a record of the socket events and the modules it imported."""
    work = Path(tempfile.mkdtemp(prefix="child-", dir=world.tmp))
    record_path = work / "record.json"
    body = {"argv": list(argv), "prog": prog, "record": str(record_path), **(job or {})}
    job_path = work / "job.json"
    job_path.write_text(json.dumps(body), encoding="utf-8")
    extra = dict(env or {})
    if package_root is not None:
        extra["PYTHONPATH"] = str(package_root)
    done = subprocess.run(
        [sys.executable, "-P", str(CHILD), str(job_path)], cwd=world.work,
        env=base_env(world, extra), input=stdin if stdin is not None else b"",
        capture_output=True, timeout=timeout, check=False,
    )
    record = json.loads(record_path.read_text(encoding="utf-8")) if record_path.exists() else {}
    shutil.rmtree(work, ignore_errors=True)
    return Fresh(code=done.returncode, out=done.stdout.decode("utf-8", "replace"),
                 err=done.stderr.decode("utf-8", "replace"), record=record)


@pytest.fixture(scope="session")
def bare_package(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A copy of this package with no tokenizer file and no published cards, made once: the
    folder to put first on `PYTHONPATH`.  Tests that change the copy make their own."""
    return package_copy(tmp_path_factory.mktemp("bare-package"))


def package_copy(root: Path, *, cards: bool = False, tokenizer: bool = False) -> Path:
    """A copy of this package at `root/src/poisson_tasks`, without its tokenizer file unless
    `tokenizer`; returns `root/src`, the folder to put first on `PYTHONPATH`.  With `cards`, the
    published cards' folders are copied to `root/calibration`, where a checkout keeps them beside
    `src/`, which is where the estimate and `cards.published()` read them until they ship inside
    the package (FD3 Session A's yes/no 5)."""
    source = Path(importlib.import_module("poisson_tasks").__file__ or "").resolve().parent
    shutil.copytree(source, root / "src" / "poisson_tasks",
                    ignore=shutil.ignore_patterns("__pycache__", "*.tiktoken", "*.part"))
    if tokenizer:
        shutil.copy2(tokenizer_file(), root / "src" / "poisson_tasks" / "data" / tokenizer_file().name)
    if cards:
        for artifact in sorted((REPO / "calibration").glob("*/artifact.json")):
            shutil.copytree(artifact.parent, root / "calibration" / artifact.parent.name)
    return root / "src"


def tokenizer_file() -> Path:
    """This checkout's tokenizer file, which a child serves in place of the network."""
    path = Path(importlib.import_module("poisson_tasks.fetch_encoding").ENCODING_PATH)
    assert path.is_file(), "the suite needs the tokenizer file in this checkout"
    return path


__all__ = [
    "KEY", "KEY_VAR", "PROGS", "world", "prog", "bare_package",
]
