"""The plain style: text only, no escape sequence, standard library only.  The contract the
tests and the docs pin (rule L16, ruled 2026-10-13).

It falls back to ASCII when a stream cannot encode the glyphs (`·`, `–`, `×`).  Writing to a
terminal, it wraps its own long lines at the terminal's width with a hanging indent, never
inside a question's bracketed default and never a command printed for the user to copy; piped,
every fact stays on one line.  The dialogue is asked on stderr and read a line at a time from
stdin, as `input()` does, so `init > file` leaves the file holding only the result.
"""

from __future__ import annotations

import contextlib
import shlex
import shutil
import sys
import textwrap
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from typing import Any

from poisson_tasks.cli import _format
from poisson_tasks.cli._result import Bullets, Command, Levels, Part, Result, Row

_ASCII = str.maketrans({
    "·": "-", "–": "-", "—": "-", "−": "-", "×": "x", "…": "...", "→": "->", "’": "'",
    "‘": "'", "“": '"', "”": '"', "›": ">", "❯": ">", "✓": "ok", "✗": "x", "•": "-",
    "├": "[", "┤": "]", "─": "-", "●": "*",
})
STATUS_WORDS = {"ok": "ok", "bad": "not ok", "note": "note", "refused": "refused"}
"""`doctor`'s row words (G14): a check that passed, information, a tool not used, a check that
failed."""
COMMAND_WIDTH = 78
"""Where a command to copy is broken before a flag, in every style (the look's item 24)."""


def encodable(stream: Any) -> bool:
    """Whether `stream` can carry the glyphs the look uses."""
    try:
        "·–×…".encode(getattr(stream, "encoding", None) or "ascii")
    except (UnicodeEncodeError, LookupError):
        return False
    return True


def terminal_width(stream: Any) -> int | None:
    """The width to wrap at when `stream` is a terminal, else `None`: no wrapping in a pipe."""
    try:
        if not stream.isatty():
            return None
    except (AttributeError, ValueError):
        return None
    return max(20, shutil.get_terminal_size().columns)


def continued_command(
    argv: Sequence[str], indent: str = "    ", width: int = COMMAND_WIDTH
) -> list[str]:
    """A command as lines joined by backslashes, broken only before a flag."""
    words = [shlex.quote(word) if word else '""' for word in argv]
    lines: list[str] = []
    current = indent
    for index, word in enumerate(words):
        breakable = word.startswith("--") and index > 0
        if breakable and len(current) + len(word) > width:
            lines.append(current.rstrip() + " \\")
            current = indent + "  "
        current += word + " "
    lines.append(current.rstrip())
    return lines


class _Progress:
    """One line rewritten in place on a terminal, and a new line at each tenth otherwise
    (spec §8.3)."""

    def __init__(self, ui: PlainUI, total: int) -> None:
        self.ui = ui
        self.total = max(1, total)
        self.started = time.monotonic()
        self.width = 0
        self.tenth = max(1, self.total // 10)
        self.tty = ui.err_width is not None

    def __enter__(self) -> _Progress:
        return self

    def advance(self, event: Mapping[str, Any]) -> None:
        done = int(event.get("episodes_done", 0))
        spend = event.get("spend")
        spent = f" · {_format.dollars(float(spend))} spent" if spend is not None else ""
        line = (f"  {done}/{self.total} episodes · {event.get('arm', '')}{spent} · "
                f"{_format.duration(time.monotonic() - self.started)}")
        line = self.ui.text(line, sys.stderr)
        if self.tty:
            sys.stderr.write("\r" + line.ljust(self.width))
            sys.stderr.flush()
            self.width = len(line)
        elif done % self.tenth == 0 or done == self.total:
            sys.stderr.write(line + "\n")
            sys.stderr.flush()

    def __exit__(self, *exc: object) -> None:
        if self.tty and self.width:
            sys.stderr.write("\r" + " " * (self.width + 2) + "\r")
            sys.stderr.flush()


class PlainUI:
    pretty = False

    def __init__(self, prog: str) -> None:
        self.prog = prog
        self.out_width = terminal_width(sys.stdout)
        self.err_width = terminal_width(sys.stderr)
        self._out_ascii = not encodable(sys.stdout)
        self._err_ascii = not encodable(sys.stderr)

    # -- writing --------------------------------------------------------------------------

    def text(self, text: str, stream: Any) -> str:
        """`text` as `stream` can carry it: the glyphs made ASCII where it cannot."""
        ascii_only = self._err_ascii if stream is sys.stderr else self._out_ascii
        if ascii_only:
            return text.translate(_ASCII).encode("ascii", "replace").decode("ascii")
        return text

    def _write(self, stream: Any, text: str, *, indent: str = "", wrap: bool = True) -> None:
        width = self.err_width if stream is sys.stderr else self.out_width
        text = self.text(text, stream)
        if wrap and width is not None and len(text) > width:
            lines = textwrap.wrap(text, width, subsequent_indent=indent,
                                  break_long_words=False, break_on_hyphens=False,
                                  drop_whitespace=True, replace_whitespace=False)
            text = "\n".join(lines) if lines else text
        stream.write(text + "\n")

    def out(self, text: str = "", *, indent: str = "", wrap: bool = True) -> None:
        self._write(sys.stdout, text, indent=indent, wrap=wrap)

    def err(self, text: str = "", *, indent: str = "", wrap: bool = True, end: str = "\n") -> None:
        if end == "\n":
            self._write(sys.stderr, text, indent=indent, wrap=wrap)
        else:
            sys.stderr.write(self.text(text, sys.stderr) + end)
        sys.stderr.flush()

    # -- results --------------------------------------------------------------------------

    def show(self, result: Result) -> None:
        self.out(f"{result.verdict}  {result.sentence}", indent=" " * (len(result.verdict) + 2))
        labels = [row.label for row in result.rows if isinstance(row, Row)]
        width = max((len(label) for label in labels), default=0)
        for row in result.rows:
            if isinstance(row, Row):
                if row.status is not None:
                    status = STATUS_WORDS.get(row.status, "not ok")
                    self.out(f"  {row.label:<{width}}  {status:<6}  {row.value}",
                             indent=" " * (width + 12))
                else:
                    self.out(f"  {row.label:<{width}}  {row.value}", indent=" " * (width + 4))
            elif isinstance(row, Levels):
                arm_width = max((len(str(cell["arm_id"])) for cell in row.cells), default=0)
                for cell in row.cells:
                    self.out(f"  {cell['arm_id']:<{arm_width}}  {level_line(cell)}",
                             indent=" " * (arm_width + 4))
            elif isinstance(row, Bullets):
                self.out(f"  {row.label}")
                for item in row.items:
                    self.out(f"    - {item}", indent="      ")
            elif isinstance(row, Command):
                self.out(f"  {row.label}")
                for line in continued_command(row.argv):
                    self.out(line, wrap=False)
        for part in result.document:
            self.out()
            if part.kind == "document":
                # a whole document, as written: never indented, never wrapped
                sys.stdout.write(self.text(str(part.body), sys.stdout))
                if not str(part.body).endswith("\n"):
                    sys.stdout.write("\n")
                continue
            self.out(part.title)
            self._part(part)
        for command in result.next:
            self.out(f"next: {command}", wrap=False)
        sys.stdout.flush()

    def _part(self, part: Part) -> None:
        if part.kind in ("quote", "text", "code"):
            for line in str(part.body).splitlines() or [""]:
                self.out(f"  {line}", indent="  ", wrap=part.kind != "quote")
        elif part.kind == "lines":
            for line in part.body:
                self.out(f"  {line}", indent="    ")
        elif part.kind == "tools":
            width = max((len(name) for name, _, _ in part.body), default=0)
            for name, params, needed in part.body:
                self.out(f"  {name:<{width}}  ({params})" + ("  needed" if needed else ""),
                         indent=" " * (width + 4))
        elif part.kind == "steps":
            for index, (name, arguments, returns) in enumerate(part.body, 1):
                self.out(f"  {index}. {name}({arguments})", indent="     ")
                self.out(f"     -> {returns}", indent="        ")
        elif part.kind == "answers":
            width = max((len(what) for what, _, _ in part.body), default=0)
            for what, outcome, extra in part.body:
                self.out(f"  {what:<{width}}  {outcome}" + (f"  {extra}" if extra else ""),
                         indent=" " * (width + 4))

    def json(self, result: Result) -> None:
        sys.stdout.write(self.text(result.as_json(), sys.stdout))
        sys.stdout.flush()

    def raw(self, text: str) -> None:
        """Text printed as it is: the version."""
        self.out(text, wrap=False)

    def help(self, parser: Any) -> None:
        parser.print_help(sys.stdout)

    def error(self, message: str, next: Sequence[str] = ()) -> None:
        self.err(f"error: {message}", indent="  ")
        for command in next:
            self.err(f"  next: {command}", wrap=False)

    def note(self, message: str) -> None:
        self.err(f"note: {message}", indent="  ")

    # -- the dialogue (all of it on stderr) --------------------------------------------------

    def intro(self, text: str) -> None:
        self.err(text)

    def gap(self) -> None:
        self.err()

    def say(self, text: str, status: str | None = None) -> None:
        """A line of the dialogue, indented: what was found or done."""
        head = {"ok": "ok: ", "bad": "not ok: ", "warn": "note: "}.get(status or "", "")
        for index, line in enumerate(text.split("\n")):
            self.err(f"   {head if index == 0 else ''}{line}" if line else "", indent="   ")

    def _read(self, prompt: str, *, width_free: str = "") -> str:
        """Print `prompt` and read one line.  The bracketed default is never broken: when the
        prompt would wrap, the text before it wraps and the brackets go whole on the last line,
        or on a line of their own."""
        width = self.err_width
        prompt = self.text(prompt, sys.stderr)
        if width is not None and len(prompt) > width:
            head, bracket = _split_bracket(prompt)
            indent = " " * (len(head) - len(head.lstrip()))
            lines = textwrap.wrap(head, width, subsequent_indent=indent,
                                  break_long_words=False, break_on_hyphens=False) or [head]
            if bracket:
                if len(lines[-1]) + 1 + len(bracket) <= width:
                    lines[-1] = lines[-1] + " " + bracket
                else:
                    lines.append(indent + bracket)
            prompt = "\n".join(lines) + " "
        sys.stderr.write(prompt)
        sys.stderr.flush()
        line = sys.stdin.readline()
        if not line:
            sys.stderr.write("\n")
            sys.stderr.flush()
            raise KeyboardInterrupt
        return line.strip()

    def confirm(self, question: str, default: bool, *, indent: str = "") -> bool:
        mark = "[Y/n]" if default else "[y/N]"
        while True:
            answer = self._read(f"{indent}{question} {mark} ").lower()
            if not answer:
                return default
            if answer in ("y", "yes"):
                return True
            if answer in ("n", "no"):
                return False
            self.err(f"{indent}Answer y or n.")

    def choice(self, number: int, question: str, options: Sequence[tuple[str, str]],
               default: int) -> int:
        """A numbered menu; returns the index chosen."""
        self.err()
        self.err(f"{number}. {question}", indent="   ")
        for index, (label, note) in enumerate(options, 1):
            self.err(f"   {index}) {label}", indent="      ")
            for line in note.split("\n") if note else []:
                self.err(f"      {line}", indent="      ")
        while True:
            answer = self._read(f"   [{default + 1}] ")
            if not answer:
                return default
            if answer.isdigit() and 1 <= int(answer) <= len(options):
                return int(answer) - 1
            self.err(f"   Type a number from 1 to {len(options)}.")

    def ask(
        self,
        number: int | None,
        question: str,
        default: str | None,
        *,
        hint: str | None = None,
        shown: str | None = None,
        validate: Callable[[str], str | None] | None = None,
    ) -> str:
        """Ask for a line.  `shown` is the bracketed default when it differs from the value; a
        hint goes above the answer line (the look's item 10)."""
        bracket = f"[{shown if shown is not None else default}] " if default is not None else ""
        self.err()
        head = f"{number}. {question}" if number is not None else f"   {question}"
        if hint:
            self.err(head, indent="   ")
            for line in hint.split("\n"):
                self.err(f"   {line}", indent="   ")
            prompt = f"   {bracket}"
        else:
            prompt = f"{head} {bracket}"
        while True:
            answer = self._read(prompt) or (default or "")
            problem = validate(answer) if validate else None
            if problem is None:
                return answer
            self.err(f"   {problem}", indent="   ")
            prompt = f"   {bracket}"

    @contextlib.contextmanager
    def status(self, text: str) -> Iterator[None]:
        """Work in progress: nothing is drawn in the plain style."""
        yield

    def progress(self, *, total: int, arms: Sequence[tuple[str, int, int]],
                 folder: str) -> _Progress:
        return _Progress(self, total)


def _split_bracket(prompt: str) -> tuple[str, str]:
    """The prompt's text and its trailing bracketed default, `[...]`, when it ends in one."""
    stripped = prompt.rstrip()
    if stripped.endswith("]") and "[" in stripped:
        at = stripped.rfind("[")
        if "\n" not in stripped[at:]:
            return stripped[:at].rstrip(), stripped[at:]
    return stripped, ""


def level_line(cell: Mapping[str, Any]) -> str:
    """One level of a card, in the plain style."""
    planned = int(cell["tasks_planned"])
    attempts = int(cell.get("attempts") or 1)
    if cell["state"] == "not run":
        return f"not run (0 of {planned} tasks)"
    tasks = int(cell["tasks"])
    low, high = cell["interval"]
    text = (f"strict pass@1 {_format.rate(cell['pass_at_1'])} {_format.interval(low, high)} · "
            f"leaky {_format.rate(cell['leaky_at_1'])} · "
            f"overshoot {_format.rate(cell['overshoot'])} · ")
    if cell["state"] == "incomplete":
        text += f"{tasks} of {planned} tasks × {_format.plural(attempts, 'attempt')}, incomplete"
    else:
        text += f"{_format.plural(tasks, 'task')} × {_format.plural(attempts, 'attempt')}"
    return text
