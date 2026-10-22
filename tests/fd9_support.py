"""Shared ground for the `tests/test_fd9_*.py` tests, the guided session: frozen with them.

**What is driven, and how.**  Two ways, each where it is the only faithful one.

- **In this process** (`in_session`): `cli.main([], prog=...)` with stdin, stdout and stderr swapped
  for streams the test owns, each saying it is a terminal (`isatty()` is true; there is no file
  descriptor).  The world's colour is off (`NO_COLOR=1`, `TERM=dumb`), so the session runs in the
  plain look (G4), whose prompt and menus are read a line at a time with `sys.stdin.readline()`, as
  `PlainUI` reads `init`'s questions.  Every call is made inside the network guard of
`tests/fd2_fakes.py`.  This is how
  the home screen's facts, the words, the actions and their files, the run-through, Ctrl-C at a
  question and leaving are pinned.
- **In a pseudo-terminal** (`Pty`): `python -m poisson_tasks` with stdin, stdout and stderr on one
  pseudo-terminal that is the process's controlling terminal, so Ctrl-C is the terminal's own
  signal or key, prompt_toolkit holds a real terminal, and the colour depth is the one the
  environment declares.  This is how the entry rule, the banner at each colour depth (each in a
  fresh process, since Rich keeps a style's escape codes from the first depth it rendered), Tab,
  Ctrl-C with text typed and during a run, and the prompt after a run are pinned.  The harness
  answers a cursor-position request, as a terminal does.

**How a test tells the session's prompt from a verb's question** (a shape the fakes hold the
build to): a line read while one of `PlainUI`'s `ask`, `choice` or `confirm` is on the stack is a
question, answered by the test's `answer` policy, which sees the question's kind, text, options and
default, and which module asked (`_init`, `_run`, `_doctor` and the rest, or `_session`).  Any other
line read is the session's own prompt, and gets the test's next word.  So the session's prompt, and
the run-through's prompts between steps, are not `PlainUI.ask`, `choice` or `confirm`.

**The session's five folder states** (`States`), made once per process, offline, against the
fixture model (built-in tasks) or a scripted model playing each task's reference calls (your own
tools), and copied into each test's own folder.  Every run folder in them holds a `run.lock` that
no process holds, as a run that ended may leave it, so every state is also a lock whose process is
gone:

| name | what is on disk |
|---|---|
| `A` | nothing |
| `B` | `tasks.toml` for depth at 1 and 3, one task each, against the fixture model under the published card's model name |
| `C1` | `B`'s run with its episode of depth 3 not ended well (its trace row not `ok`) and out of the ledger: stopped partway |
| `C2` | `C1`, with `run.lock` held by another process (`hold_lock`) |
| `D` | `B` run to the end, its card built |
| `D-nocard` | `B` run to the end, no card |
| `D-refused` | a run of `fixture-silent`, which answers in text, and its card, refused |
| `E` | the Petstore file on your own tools, the error-recovery recipe, one task a level, run and its card built |

**What every expectation is computed from**: the library (`folder.read_folder`, `config`, `runs`,
`own`, `cards`), the files on disk, the fixture's own count, and the banner files that were chosen
(`tests/fixtures/fd9/`); never the session under test.
"""

from __future__ import annotations

import dataclasses
import fcntl
import importlib
import io
import json
import os
import pty
import re
import select
import shlex
import shutil
import signal
import struct
import subprocess
import sys
import termios
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from tests.fd2_fakes import network_guard
from tests.fd3_support import KEY, KEY_VAR, stub_bin
from tests.fd5_support import (
    World,
    base_env,
    fixture_flags,
    joined_lines,
    next_commands,
    strip_prog,
    write_config,
)
from tests.fixtures.model_server import FixtureModel

REPO = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).with_name("fixtures") / "fd9"
PETSTORE = Path(__file__).with_name("fixtures") / "o1" / "petstore-openapi-3.0.json"
PROG = "poisson-tasks"
PUBLISHED_MODEL = "gpt-5-nano-2025-08-07"
"""The published card's model: a run under this name has a published card beside it (G17)."""

SESSION_MODULES = ("poisson_tasks.cli._session", "poisson_tasks.cli._banner")
"""The session's modules: the two files the session's build touches."""

WORDS = ("run", "again", "card", "more", "replies", "task", "verify", "runs", "settings", "setup",
         "flow", "export", "check", "home", "help", "quit")
"""The prompt's closed set of words."""

STEP_ONE = {
    "A": "setup", "B": "run", "C1": "run", "C2": "home", "D": "card", "D-nocard": "card",
    "D-refused": "replies", "E": "card",
}
"""Step 1 of `next` for each fixture state, by the session's action table.  A refused card's step 1
is the replies view (decided 2026-10-20): the session never leads with a step that fails; `card` is
offered below it."""

STEP_COMMAND = {"setup": ["init"], "run": ["run"], "home": None, "card": ["card"]}
"""Step 1's verb, for the off-terminal `next:` (G5): `setup` is the run-through, whose command is
`init`; `home` is not a command, so that state's `next:` is not pinned here.  The flags are the
action table's (a card already built is read again with `--force`), so only the verb is pinned."""

MARK = "▁▃▆██▆▄▂▁▁▁▁"
"""The banner's mark, as `banner.txt` draws it."""
BLOCKS = set("▁▂▃▄▅▆▇█")

ESCAPE = re.compile(r"\x1b(?:\[[0-9;?<>=]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\)|[@-Z\\-_])")


def stripped(text: str) -> str:
    """`text` without escape sequences and carriage returns."""
    return ESCAPE.sub("", text).replace("\r", "")


def version() -> str:
    import importlib.metadata

    return importlib.metadata.version("poisson-tasks")


def banner_text() -> list[str]:
    """The chosen banner's two lines, with this install's version for the one it was drawn with."""
    lines = (FIXTURES / "banner.txt").read_text(encoding="utf-8").splitlines()
    return [line.replace("0.1.0", version()) for line in lines]


def cli() -> Any:
    return importlib.import_module("poisson_tasks.cli")


def folder_module() -> Any:
    return importlib.import_module("poisson_tasks.folder")


# ---------------------------------------------------------------------------
# a style per character, read from escape sequences
# ---------------------------------------------------------------------------


def styled(text: str) -> list[tuple[str, Any, bool, bool]]:
    """Each printed character of `text` with the foreground colour, bold and dim that apply to
    it, read from the SGR sequences; other escapes are skipped.  A colour is `("rgb", r, g, b)`,
    `("256", n)`, `("16", code)` or `None`."""
    out: list[tuple[str, Any, bool, bool]] = []
    fg: Any = None
    bold = dim = False
    at = 0
    sgr = re.compile(r"\x1b\[([0-9;]*)m")
    while at < len(text):
        match = ESCAPE.match(text, at)
        if match:
            found = sgr.fullmatch(match.group(0))
            if found:
                codes = [int(c) if c else 0 for c in found.group(1).split(";")]
                i = 0
                while i < len(codes):
                    code = codes[i]
                    if code == 0:
                        fg, bold, dim = None, False, False
                    elif code == 1:
                        bold = True
                    elif code == 2:
                        dim = True
                    elif code == 22:
                        bold = dim = False
                    elif code == 39:
                        fg = None
                    elif 30 <= code <= 37 or 90 <= code <= 97:
                        fg = ("16", code)
                    elif code == 38 and i + 1 < len(codes) and codes[i + 1] == 5:
                        fg = ("256", codes[i + 2])
                        i += 2
                    elif code == 38 and i + 1 < len(codes) and codes[i + 1] == 2:
                        fg = ("rgb", *codes[i + 2:i + 5])
                        i += 4
                    i += 1
            at = match.end()
            continue
        char = text[at]
        at += 1
        if char == "\r":
            continue
        out.append((char, fg, bold, dim))
    return out


def banner_styles(depth: str) -> list[tuple[str, Any, bool, bool]]:
    """The chosen banner at one colour depth, character by character (`banner-R-<depth>.ans`)."""
    text = (FIXTURES / f"banner-R-{depth}.ans").read_text(encoding="utf-8")
    want = version()
    out = []
    for char, fg, bold, dim in styled(text):
        out.append((char, fg, bold, dim))
    plain = "".join(char for char, *_ in out)
    if want != "0.1.0":
        at = plain.index("0.1.0")
        style = out[at][1:]
        out[at:at + 5] = [(char, *style) for char in want]
    return out


# ---------------------------------------------------------------------------
# in this process: the session in the plain look
# ---------------------------------------------------------------------------

INTERRUPT = "<Ctrl-C>"
"""A word or an answer: Ctrl-C at that read."""
EOF = "<Ctrl-D>"
"""A word: the end of input at that read (Ctrl-D)."""


@dataclasses.dataclass
class Asked:
    """A question a verb (or the session's own menu) asked through `PlainUI`."""

    kind: str
    """`ask`, `choice` or `confirm`."""
    question: str
    options: list[str]
    default: Any
    module: str
    """The module that asked: `_init`, `_run`, `_doctor`, ..., or `_session`."""


@dataclasses.dataclass
class Through:
    """A word: Enter at every prompt of the session's own until `run`'s question has been asked,
    which gets `start`; then the next word."""

    start: str = "n"


class _Log:
    """What the session wrote, in order, with each read marked."""

    def __init__(self) -> None:
        self.items: list[tuple[str, str]] = []

    def text(self, *streams: str) -> str:
        wanted = streams or ("out", "err")
        return "".join(text for kind, text in self.items if kind in wanted)

    def screens(self) -> list[str]:
        """The output between one read and the next, in order: the first is what was printed
        before the first read."""
        out = [""]
        for kind, text in self.items:
            if kind == "read":
                out.append("")
            else:
                out[-1] += text
        return out


class _Tty(io.TextIOBase):
    """A stream that says it is a UTF-8 terminal, and writes into the log."""

    def __init__(self, log: _Log, kind: str) -> None:
        self.log = log
        self.kind = kind

    encoding = "utf-8"
    errors = "strict"

    def isatty(self) -> bool:
        return True

    def writable(self) -> bool:
        return True

    def write(self, text: str) -> int:  # type: ignore[override]
        self.log.items.append((self.kind, text))
        return len(text)

    def flush(self) -> None:
        pass

    def fileno(self) -> int:
        raise io.UnsupportedOperation("no file descriptor")


_QUESTION_METHODS = ("ask", "choice", "confirm")


def _asked() -> Asked | None:
    frame = sys._getframe(2)
    method = None
    while frame is not None:
        name = frame.f_globals.get("__name__", "")
        if method is None and name == "poisson_tasks.cli._plain" and \
                frame.f_code.co_name in _QUESTION_METHODS:
            method = frame
        elif method is not None and name.startswith("poisson_tasks.cli.") and \
                name != "poisson_tasks.cli._plain":
            locals_ = method.f_locals
            options = [str(label) for label, _ in locals_.get("options") or ()]
            return Asked(kind=method.f_code.co_name, question=str(locals_.get("question", "")),
                         options=options, default=locals_.get("default"),
                         module=name.rsplit(".", 1)[-1])
        frame = frame.f_back  # type: ignore[assignment]
    if method is not None:
        locals_ = method.f_locals
        return Asked(kind=method.f_code.co_name, question=str(locals_.get("question", "")),
                     options=[str(label) for label, _ in locals_.get("options") or ()],
                     default=locals_.get("default"), module="")
    return None


class OutOfKeys(BaseException):
    """The session kept reading after its words ran out and twenty ends of input."""


class NoOption(BaseException):
    """A menu had no option the test looked for; not an `Exception`, so the command's own
    catch-all cannot turn it into exit 3."""


def pick(pattern: str) -> Callable[[Asked], str]:
    """An answer to a menu: the number of the first option matching `pattern`."""
    def answer(asked: Asked) -> str:
        for index, label in enumerate(asked.options, 1):
            if re.search(pattern, label, re.IGNORECASE):
                return str(index)
        raise NoOption(f"no option of {asked.question!r} matches {pattern!r}: {asked.options}")

    return answer


class Keys(io.TextIOBase):
    """A terminal's stdin for the session: the session's prompts get `words` in order (`Through`
    covers the run-through); a question gets `answer(asked)` (None, or no policy, is Enter).
    Each answer is echoed into the log, as a terminal echoes what is typed, then the read is
    marked; every question is kept in `asked`."""

    def __init__(self, words: Sequence[Any] = (), *,
                 answer: Callable[[Asked], Any] | None = None,
                 free: Sequence[str] = ()) -> None:
        self.words = list(words)
        self.answer = answer
        self.free = list(free)
        self.asked: list[Asked] = []
        self.prompts = 0
        self.ends = 0
        self.started = False
        self.log: _Log | None = None
        self._through: Through | None = None

    def isatty(self) -> bool:
        return True

    def readable(self) -> bool:
        return True

    def fileno(self) -> int:
        raise io.UnsupportedOperation("no file descriptor")

    def read(self, size: int | None = -1) -> str:
        return self.readline()

    def readline(self, size: int | None = -1) -> str:  # type: ignore[override]
        asked = _asked()
        reply = self._reply(asked)
        if self.log is not None:
            echo = {INTERRUPT: "^C\n", EOF: "\n"}.get(reply, f"{reply}\n")
            self.log.items.append(("out", echo))
            self.log.items.append(("read", "question" if asked else "prompt"))
        if reply == INTERRUPT:
            raise KeyboardInterrupt
        if reply == EOF:
            self.ends += 1
            if self.ends > 20:
                raise OutOfKeys
            return ""
        return str(reply) + "\n"

    def _reply(self, asked: Asked | None) -> Any:
        """The answer to this read, as a terminal would echo it."""
        reply: Any
        if asked is not None:
            self.asked.append(asked)
            reply = None
            if self._through is not None and asked.kind == "confirm" and asked.module == "_run":
                reply, self._through, self.started = self._through.start, None, True
            elif self.answer is not None:
                reply = self.answer(asked)
                if callable(reply):
                    reply = reply(asked)
            if reply is None and asked.kind == "ask" and asked.default is None and self.free:
                reply = self.free.pop(0)
            if asked.kind == "confirm" and asked.module == "_run":
                self.started = True
            reply = "" if reply is None else reply
        else:
            self.prompts += 1
            if self._through is not None:
                reply = ""
            elif self.words:
                reply = self.words.pop(0)
                if isinstance(reply, Through):
                    self._through = reply
                    reply = ""
            else:
                reply = EOF
        return reply


@dataclasses.dataclass
class Session:
    """What one session in this process did."""

    code: int
    log: _Log
    keys: Keys
    events: tuple[tuple[str, Any], ...]

    @property
    def out(self) -> str:
        return self.log.text("out")

    @property
    def err(self) -> str:
        return self.log.text("err")

    @property
    def text(self) -> str:
        return self.log.text()

    @property
    def connections(self) -> list[Any]:
        return [address for kind, address in self.events if kind == "connect"]

    def same_as(self) -> list[list[str]]:
        """Every `same as` command the session printed, as argv, in order."""
        found = []
        for line in joined_lines(self.text):
            match = re.match(r"^\s*same as\s+(.+?)\s*$", line)
            if match:
                found.append(shlex.split(match.group(1)))
        return found

    def __str__(self) -> str:
        return f"the session exited {self.code}\n--- transcript\n{self.text}"


def in_session(keys: Keys, monkeypatch: pytest.MonkeyPatch, *, prog: str = PROG,
               argv: Sequence[str] = ()) -> Session:
    """A bare command (`argv` holds only `--config`, `--plain` or `--debug`) with all three
    streams on terminals, in this process, inside the network guard."""
    log = _Log()
    keys.log = log
    saved = sys.stdin, sys.stdout, sys.stderr
    sys.stdin, sys.stdout, sys.stderr = keys, _Tty(log, "out"), _Tty(log, "err")
    code: Any = None
    escaped: str | None = None
    try:
        with network_guard(monkeypatch) as events:
            try:
                code = cli().main(list(argv), prog=prog)
            except SystemExit as stop:
                code = stop.code
            except KeyboardInterrupt:
                escaped = "a Ctrl-C escaped the session"
            except (OutOfKeys, NoOption) as stopped:
                escaped = f"{type(stopped).__name__}: {stopped}"
    finally:
        sys.stdin, sys.stdout, sys.stderr = saved
    if escaped is not None:
        # a failure of the test, never pytest's own interrupt
        raise AssertionError(f"{escaped}\n--- transcript\n{log.text()}")
    return Session(code=int(code or 0), log=log, keys=keys, events=tuple(events))


def home_blocks(text: str) -> list[list[str]]:
    """Each home screen in `text`: the status block's lines (from `folder` to the line before
    `next`) and the `next` lines, as one list of lines, in order."""
    lines = stripped(text).splitlines()
    out: list[list[str]] = []
    for index, line in enumerate(lines):
        if re.match(r"^folder\s", line):
            block = []
            for later in lines[index:]:
                block.append(later)
                if re.match(r"^\s*$", later) and any(re.match(r"^\s*1\s", b) for b in block):
                    break
            out.append(block)
    return out


def steps_of(block: Sequence[str]) -> list[str]:
    """The words of a home screen's numbered `next` steps, in order: the last word on each step's
    line (or on the line its sentence wraps to), with any parentheses taken off."""
    words: list[str] = []
    seen_next = False
    current = ""
    for line in block:
        if re.match(r"^next\s*$", line.strip()):
            seen_next = True
            continue
        if not seen_next:
            continue
        match = re.match(r"^\s*(\d+)\s{2,}(.*)$", line)
        if match:
            if current:
                words.append(current)
            current = match.group(2)
        elif line.strip() and current:
            current += " " + line.strip()
        elif not line.strip() and current:
            break
    if current:
        words.append(current)
    found = []
    for step in words:
        last = step.split()[-1].strip("()")
        if last.isdigit() and len(step.split()) > 1:
            last = " ".join(step.split()[-2:]).strip("()")
        found.append(last)
    return found


# ---------------------------------------------------------------------------
# in a pseudo-terminal
# ---------------------------------------------------------------------------


def pretty_env(world: World, **extra: str) -> dict[str, str]:
    """A child's environment in which the pretty look may run, at a colour depth Rich reads from
    `COLORTERM` and `TERM`: truecolor by default."""
    env = base_env(world, {"PATH": os.environ.get("PATH", "")})
    env.pop("NO_COLOR", None)
    env.pop("CI", None)
    env["TERM"] = "xterm-256color"
    env["COLORTERM"] = "truecolor"
    env["PYTHONIOENCODING"] = "utf-8"
    for name, value in extra.items():
        if value is None:
            env.pop(name, None)
        else:
            env[name] = value
    return env


class Pty:
    """`python -m poisson_tasks <argv>` on a pseudo-terminal of `columns` columns that is its
    controlling terminal; stdin, stdout or stderr is a pipe instead where a flag says so."""

    def __init__(self, argv: Sequence[str], *, env: dict[str, str], cwd: Path,
                 columns: int = 100, stdin_tty: bool = True, stdout_tty: bool = True,
                 stderr_tty: bool = True) -> None:
        env = {**env, "COLUMNS": str(columns), "LINES": "40"}
        env.pop("COLUMNS", None) if stdout_tty else None
        self.master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 40, columns, 0, 0))
        controlling = 0 if stdin_tty else (1 if stdout_tty else 2)

        def own_terminal() -> None:
            try:
                fcntl.ioctl(controlling, termios.TIOCSCTTY, 0)
            except OSError:
                pass

        self.process = subprocess.Popen(
            [sys.executable, "-m", "poisson_tasks", *argv], cwd=cwd, env=env,
            stdin=slave if stdin_tty else subprocess.PIPE,
            stdout=slave if stdout_tty else subprocess.PIPE,
            stderr=slave if stderr_tty else subprocess.PIPE,
            start_new_session=True, preexec_fn=own_terminal,
        )
        os.close(slave)
        self.raw = b""
        self.pipes = {name: pipe for name, pipe in (("out", self.process.stdout),
                                                    ("err", self.process.stderr)) if pipe}
        self.piped = {name: b"" for name in self.pipes}
        self.closed = False

    def _pump(self, wait: float) -> bool:
        fds = [] if self.closed else [self.master]
        fds += [pipe.fileno() for pipe in self.pipes.values() if not pipe.closed]
        if not fds:
            time.sleep(wait)
            return False
        ready, _, _ = select.select(fds, [], [], wait)
        got = False
        for fd in ready:
            try:
                chunk = os.read(fd, 65536)
            except OSError:
                chunk = b""
            if fd == self.master:
                if not chunk:
                    self.closed = True
                    continue
                self.raw += chunk
                for _ in range(chunk.count(b"\x1b[6n")):
                    os.write(self.master, b"\x1b[1;1R")
                got = True
            else:
                name = next(n for n, p in self.pipes.items() if p.fileno() == fd)
                if not chunk:
                    self.pipes[name].close()
                    continue
                self.piped[name] += chunk
                got = True
        return got

    @property
    def text(self) -> str:
        return self.raw.decode("utf-8", "replace")

    @property
    def plain(self) -> str:
        return stripped(self.text)

    def quiet(self, seconds: float = 1.0, timeout: float = 120) -> None:
        """Wait until nothing has been written for `seconds`."""
        deadline = time.monotonic() + timeout
        last = time.monotonic()
        while time.monotonic() < deadline:
            if self._pump(0.1):
                last = time.monotonic()
            elif time.monotonic() - last >= seconds or self.process.poll() is not None:
                return
        raise AssertionError(f"still writing after {timeout} s\n{self.plain}")

    def expect(self, pattern: str, timeout: float = 120, since: int = 0) -> re.Match[str]:
        """Wait until the stripped transcript, from character `since`, matches `pattern`."""
        deadline = time.monotonic() + timeout
        while True:
            found = re.search(pattern, self.plain[since:], re.MULTILINE)
            if found:
                return found
            if time.monotonic() > deadline or (self.process.poll() is not None
                                               and not self._pump(0.2)):
                raise AssertionError(f"{pattern!r} never came\n{self.plain}")
            self._pump(0.1)

    def send(self, text: str, settle: float = 1.0) -> None:
        if self.process.poll() is not None:
            raise AssertionError(f"the command had already ended, exit {self.process.returncode}, "
                                 f"before {text!r} was typed\n{self.plain}")
        os.write(self.master, text.encode("utf-8"))
        if settle:
            self.quiet(settle)

    def type(self, word: str, settle: float = 1.0) -> None:
        """A word and Enter."""
        self.send(word + "\r", settle)

    def ctrl_c(self, settle: float = 1.0) -> None:
        self.send("\x03", settle)

    def wait(self, timeout: float = 120) -> int:
        deadline = time.monotonic() + timeout
        while self.process.poll() is None and time.monotonic() < deadline:
            self._pump(0.1)
        if self.process.poll() is None:
            self.kill()
            raise AssertionError(f"the session did not end\n{self.plain}")
        for _ in range(20):
            if not self._pump(0.05):
                break
        return int(self.process.returncode)

    def kill(self) -> None:
        if self.process.poll() is None:
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except OSError:
                pass
            self.process.wait(10)

    def close(self) -> None:
        self.kill()
        try:
            os.close(self.master)
        except OSError:
            pass
        for pipe in self.pipes.values():
            pipe.close()


@contextmanager
def pty_session(argv: Sequence[str], *, env: dict[str, str], cwd: Path,
                **kwargs: Any) -> Iterator[Pty]:
    made = Pty(argv, env=env, cwd=cwd, **kwargs)
    try:
        yield made
    finally:
        made.close()


# ---------------------------------------------------------------------------
# the run lock, held by another process
# ---------------------------------------------------------------------------

_HOLDER = (
    "import fcntl, os, sys\n"
    "handle = open(sys.argv[1], 'a+')\n"
    "fcntl.flock(handle, fcntl.LOCK_EX)\n"
    "print('held', flush=True)\n"
    "sys.stdin.read()\n"
)


@contextmanager
def hold_lock(folder: Path) -> Iterator[int]:
    """`<folder>/run.lock` held, as an advisory `flock`, by another process until the block ends;
    yields its pid.  The holder writes nothing in the file."""
    process = subprocess.Popen([sys.executable, "-c", _HOLDER, str(folder / "run.lock")],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    try:
        assert process.stdout is not None
        assert process.stdout.readline().strip() == b"held"
        yield process.pid
    finally:
        if process.stdin is not None:
            process.stdin.close()
        process.wait(10)


def lock_is_held(folder: Path) -> bool:
    """Whether another process holds `<folder>/run.lock` now."""
    path = folder / "run.lock"
    if not path.exists():
        return False
    with open(path, "a+") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(handle, fcntl.LOCK_UN)
    return False


# ---------------------------------------------------------------------------
# the five folder states, made once per process
# ---------------------------------------------------------------------------


@contextmanager
def harness(where: Path) -> Iterator[pytest.MonkeyPatch]:
    """This process's environment for a run: the do-nothing `pip` first on `PATH`, the fixture's
    key in `KEY_VAR`, no proxy, colour off."""
    with pytest.MonkeyPatch.context() as patch:
        stubs = stub_bin(where / "stub-bin")
        patch.setenv("PATH", f"{stubs}{os.pathsep}{os.environ.get('PATH', '')}")
        patch.setenv(KEY_VAR, KEY)
        for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy",
                     "all_proxy", "CI", "OPENAI_BASE_URL"):
            patch.delenv(name, raising=False)
        patch.setenv("NO_PROXY", "127.0.0.1,localhost")
        patch.setenv("NO_COLOR", "1")
        patch.setenv("TERM", "dumb")
        yield patch


def _quiet_main(argv: Sequence[str], cwd: Path) -> int:
    """`cli.main(argv)` in `cwd`, its output thrown away."""
    saved = sys.stdin, sys.stdout, sys.stderr, os.getcwd()
    sink = io.StringIO()
    sys.stdout = sys.stderr = sink
    sys.stdin = io.StringIO("")
    os.chdir(cwd)
    try:
        return int(cli().main(list(argv), prog=PROG) or 0)
    finally:
        sys.stdin, sys.stdout, sys.stderr = saved[:3]
        os.chdir(saved[3])


def drop_one(folder: Path, arm: str = "depth-d3") -> None:
    """Make the last kept episode of `arm` one that did not end well (its trace row kept, not
    `ok`) and take its line out of the ledger, as a run stopped partway, with that episode owed
    again, would have left them."""
    traces = folder / arm / "traces.jsonl"
    lines = traces.read_bytes().splitlines(keepends=True)
    row = json.loads(lines[-1])
    row["ok"] = False
    traces.write_bytes(b"".join(lines[:-1]) + json.dumps(row).encode("utf-8") + b"\n")
    ledger = folder / "spend.jsonl"
    rows = ledger.read_text(encoding="utf-8").splitlines(keepends=True)
    name = arm.replace("-", ":", 1)
    last = max(i for i, row in enumerate(rows) if json.loads(row).get("arm") == name)
    ledger.write_text("".join(rows[:last] + rows[last + 1:]), encoding="utf-8")


class States:
    """The fixture states, made the first time a test asks for one, then copied."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.made: dict[str, Path] = {}
        self.model = FixtureModel()
        self.model.start()
        from tests.o2_support import reference_model

        self._reference = reference_model()
        self.reference = self._reference.__enter__()

    def close(self) -> None:
        self.model.close()
        self._reference.__exit__(None, None, None)

    def flags(self, model: str = PUBLISHED_MODEL, **kwargs: Any) -> list[str]:
        return fixture_flags(self.model.base_url, model=model, levels="1,3", concurrency=1,
                             **kwargs)

    def path(self, name: str) -> Path:
        if name not in self.made:
            target = self.root / name
            target.mkdir(parents=True)
            with harness(self.root):
                getattr(self, "_" + name.replace("-", "_"))(target)
            for lock in target.glob("runs/*/plan.json"):
                (lock.parent / "run.lock").touch()  # a lock file no process holds
            self.made[name] = target
        return self.made[name]

    def copy(self, name: str, into: Path) -> Path:
        """State `name`'s files copied into the folder `into` (made if missing)."""
        source = self.path("C1" if name == "C2" else name)
        into.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, into, dirs_exist_ok=True, symlinks=True)
        return into

    def _A(self, target: Path) -> None:
        pass

    def _B(self, target: Path) -> None:
        write_config(target / "tasks.toml", self.flags())

    def _D_nocard(self, target: Path) -> None:
        shutil.copytree(self.path("B"), target, dirs_exist_ok=True)
        assert _quiet_main(["run", "--yes"], target) == 0

    def _D(self, target: Path) -> None:
        shutil.copytree(self.path("D-nocard"), target, dirs_exist_ok=True)
        assert _quiet_main(["card"], target) == 0

    def _C1(self, target: Path) -> None:
        shutil.copytree(self.path("D-nocard"), target, dirs_exist_ok=True)
        (folder,) = (target / "runs").iterdir()
        drop_one(folder)

    def _D_refused(self, target: Path) -> None:
        write_config(target / "tasks.toml", self.flags(model="fixture-silent"))
        assert _quiet_main(["run", "--yes"], target) == 0
        assert _quiet_main(["card"], target) == 1

    def _E(self, target: Path) -> None:
        from poisson_tasks import config, runs

        shutil.copy(PETSTORE, target / "petstore.json")
        flags = fixture_flags(self.reference.base_url, model=PUBLISHED_MODEL,
                              recipe="error-recovery", tasks_per_level=1, concurrency=1,
                              extra=["--own-file", "petstore.json"])
        write_config(target / "tasks.toml", flags)
        plan = config.resolve_plan(config.load_config(target / "tasks.toml"), root=target)
        for spec in plan.arms:
            for bundle in runs.own_bundles(plan, spec, plan.seeds):
                self.reference.register(bundle)
        assert _quiet_main(["run", "--yes"], target) == 0
        assert _quiet_main(["card"], target) == 0


_STATES: list[States] = []


@pytest.fixture(scope="session")
def states(tmp_path_factory: pytest.TempPathFactory) -> Iterator[States]:
    """The fixture states, made once per process."""
    if not _STATES:
        _STATES.append(States(tmp_path_factory.mktemp("fd9-states")))
    yield _STATES[0]


def run_folder(work: Path) -> Path:
    """The one run folder under `work/runs`."""
    (folder,) = sorted(p for p in (work / "runs").iterdir() if p.is_dir())
    return folder


def ledger_lines(folder: Path) -> list[dict[str, Any]]:
    path = folder / "spend.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def kept_hashes(folder: Path) -> list[str]:
    """The task hash of every kept episode in a run folder, across its arms, sorted."""
    out = []
    for traces in sorted(folder.glob("*/traces.jsonl")):
        for line in traces.read_bytes().splitlines(keepends=True):
            if not line.endswith(b"\n"):
                continue
            row = json.loads(line)
            if row.get("ok"):
                out.append(str(row["task"]["hash"]))
    return sorted(out)


def as_command(argv: Sequence[str], prog: str) -> list[str]:
    """A printed command's argv without the prog's own words."""
    return strip_prog(list(argv), prog)


__all__ = [
    "EOF", "INTERRUPT", "Keys", "Through", "pick", "in_session", "states", "Pty", "pty_session",
    "hold_lock", "next_commands",
]
