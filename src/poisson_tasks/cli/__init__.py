"""The command a user types: `poisson-tasks` and its seven verbs, `init`, `generate`, `run`,
`card`, `verify`, `export` and `doctor`.

`main(argv, prog=...)` parses the command line, picks the style, runs the verb and prints its
result; every command named in any output is rendered from `prog`, never from a literal.
Problems go to stderr as one `error:` line and exit 1 (refused, nothing spent or written), 2
(the command line is wrong), 3 (stopped or failed after work started, or an unexpected failure,
whose traceback goes to a log file the line names), 4 (a check you asked for did not pass) or
130 (interrupted).  `--json` makes stdout one JSON document with the same exit code.

**Two renderings of one result** (rule L16, decided 2026-10-13): the plain style, text only, is
the contract; the pretty style, drawn with Rich, runs only when stdout and stderr are both
terminals, `NO_COLOR` is unset or empty, `CI` is unset, `TERM` is not `dumb`, stdout is UTF-8,
and neither `--json` nor `--plain` was given, and only when Rich can be imported.
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile
import time
import traceback
import warnings
from collections.abc import Sequence
from typing import Any

from poisson_tasks.cli import _parser
from poisson_tasks.cli._common import DEFAULT_SETTINGS, Context
from poisson_tasks.cli._result import Refusal, Result, Stopped, Usage

__all__ = ["main", "build_parser"]

DEFAULT_PROG = "poisson-tasks"


def build_parser(prog: str) -> Any:
    """The command's parser, every usage line and command it names starting with `prog`."""
    return _parser.build_parser(prog)


# ---------------------------------------------------------------------------
# the style
# ---------------------------------------------------------------------------


def _is_terminal(stream: Any) -> bool:
    try:
        return bool(stream.isatty())
    except (AttributeError, ValueError):
        return False


def _utf8(stream: Any) -> bool:
    encoding = str(getattr(stream, "encoding", None) or "").lower()
    return encoding.replace("-", "").replace("_", "") == "utf8"


def pretty_allowed(words: Sequence[str]) -> bool:
    """The switch: one of two states, decided before anything is printed."""
    if "--json" in words or "--plain" in words:
        return False
    if not (_is_terminal(sys.stdout) and _is_terminal(sys.stderr)):
        return False
    if os.environ.get("NO_COLOR") or "CI" in os.environ or os.environ.get("TERM") == "dumb":
        return False
    return _utf8(sys.stdout)


def _make_ui(prog: str, words: Sequence[str]) -> Any:
    if pretty_allowed(words):
        try:
            from poisson_tasks.cli import _pretty

            return _pretty.Pretty(prog, out=_pretty.make_console(sys.stdout),
                                  err=_pretty.make_console(sys.stderr, stderr=True))
        except ImportError:
            pass
    from poisson_tasks.cli import _plain

    return _plain.PlainUI(prog)


# ---------------------------------------------------------------------------
# library warnings become note: lines
# ---------------------------------------------------------------------------


class _NoteHandler(logging.Handler):
    """A warning from the library, or a Python warning, is one `note:` line on stderr."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = " ".join(record.getMessage().split())
            sys.stderr.write(f"note: {message}\n")
            sys.stderr.flush()
        except (OSError, ValueError):
            pass


def _format_warning(message: Any, category: Any, filename: str, lineno: int,
                    line: str | None = None) -> str:
    return str(message)


def quiet_logging() -> _NoteHandler:
    """Route every warning the libraries raise to `note:` lines, and nothing else to stderr."""
    root = logging.getLogger()
    for handler in list(root.handlers):
        if isinstance(handler, logging.StreamHandler) and handler.stream in (
            sys.stderr, sys.stdout, sys.__stderr__, sys.__stdout__
        ) and not isinstance(handler, _NoteHandler):
            root.removeHandler(handler)
    mine = _NoteHandler(level=logging.WARNING)
    if not any(isinstance(handler, _NoteHandler) for handler in root.handlers):
        root.addHandler(mine)
    if root.level == logging.NOTSET or root.level < logging.WARNING:
        root.setLevel(logging.WARNING)
    logging.captureWarnings(True)
    warnings.formatwarning = _format_warning
    return mine


def reclaim_logging() -> None:
    """Called after a library that may have added its own stream handler was imported."""
    quiet_logging()


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def _version_line() -> str:
    import importlib.metadata
    import platform

    def version_of(name: str) -> str:
        try:
            return importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            return "not installed"

    return (f"poisson-tasks {version_of('poisson-tasks')} (verifiers {version_of('verifiers')}, "
            f"Python {platform.python_version()})")


def _log_failure(prog: str, error: BaseException) -> str:
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    path = os.path.join(tempfile.gettempdir(), f"poisson-tasks-{stamp}-{os.getpid()}.log")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(f"{prog}: an unexpected failure at {stamp}\n\n")
        handle.write("".join(traceback.format_exception(type(error), error, error.__traceback__)))
    return path


def _quiet_broken_pipe() -> None:
    """Python's own advice for a closed stdout: point it at nowhere, so nothing is said at exit."""
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
    except (OSError, ValueError, AttributeError):
        pass


def main(argv: Sequence[str] | None = None, *, prog: str | None = None) -> int:
    """Run the command on `argv` (the process's own arguments by default) and return its exit
    code; `prog` is the command's name as the user typed it."""
    prog = prog or DEFAULT_PROG
    words = list(sys.argv[1:] if argv is None else argv)
    ui = _make_ui(prog, words)
    _parser.set_ui(ui)
    parser = build_parser(prog)
    try:
        args = parser.parse_args(words)
    except Usage as wrong:
        ui.error(wrong.message)
        return 2
    if args.version:
        ui.raw(_version_line())
        return 0
    if args.verb is None:
        return _bare(prog, args, words, ui)
    ctx = Context(
        prog=prog, args=args, ui=ui,
        config_path=args.config or DEFAULT_SETTINGS, config_given=args.config is not None,
        json=bool(args.json), typed=_typed(words),
    )
    return dispatch(ctx)


def _typed(words: Sequence[str]) -> list[str]:
    """The words as typed, without `--config` and its value, which `ctx.command` adds back."""
    out: list[str] = []
    skip = False
    for word in words:
        if skip:
            skip = False
            continue
        if word == "--config":
            skip = True
            continue
        if word.startswith("--config="):
            continue
        out.append(word)
    return out


def session_allowed(words: Sequence[str]) -> bool:
    """The session runs when stdin, stdout and stderr are all terminals, `CI` is unset and
    `--json` is not given."""
    if "--json" in words or "CI" in os.environ:
        return False
    return all(_is_terminal(stream) for stream in (sys.stdin, sys.stdout, sys.stderr))


def _bare(prog: str, args: Any, words: Sequence[str], ui: Any) -> int:
    from poisson_tasks.cli import _session

    if session_allowed(words):
        return _session.run_session(prog, args, list(words))
    step = _session.first_step_command(prog, args)
    ui.error(f"a command is needed: one of {', '.join(_parser.VERBS)}; on a terminal, {prog} "
             "with no command opens a guided session", [step] if step else [])
    return 2


def dispatch(ctx: Context) -> int:
    """Run one verb on `ctx` and show its outcome: a result, a stop, a refusal, a usage error or
    an unexpected failure; return the exit code.  `main` and the session both call it."""
    ui = ctx.ui
    args = ctx.args
    prog = ctx.prog
    handler = quiet_logging()
    try:
        try:
            result = _VERBS[args.verb](ctx)
        except Stopped as stop:
            result = stop.result
        ctx.show(result)
        if ctx.json and not result.silent:
            ui.json(result)
        ctx.outcome = result
        return int(result.exit)
    except Usage as wrong:
        ui.error(wrong.message)
        return 2
    except Refusal as refused:
        if ctx.json and ctx.shown:
            ui.json(ctx.shown[0])
        ui.error(refused.message, refused.next)
        ctx.refused = refused
        return 1
    except KeyboardInterrupt:
        try:
            result = Result(schema=f"poisson-tasks.{args.verb}/1", verdict="stopped",
                            tone="warn", sentence="interrupted; nothing was written", exit=130)
            ctx.show(result)
            if ctx.json:
                ui.json(result)
        except (OSError, ValueError):
            pass
        return 130
    except BrokenPipeError:
        _quiet_broken_pipe()
        return 0
    except Exception as error:  # noqa: BLE001 - the one place a failure becomes one line
        if isinstance(error, OSError) and error.errno == 32:
            _quiet_broken_pipe()
            return 0
        path = _log_failure(prog, error)
        ui.error(f"an unexpected failure inside {prog} ({type(error).__name__}); the details "
                 f"are in {path}")
        if args.debug:
            sys.stderr.write("".join(traceback.format_exception(type(error), error,
                                                                error.__traceback__)))
            sys.stderr.flush()
        return 3
    finally:
        logging.getLogger().removeHandler(handler)
        try:
            sys.stdout.flush()
        except (OSError, ValueError):
            _quiet_broken_pipe()


class _Verbs:
    """Each verb's function, imported when it is first run."""

    def __getitem__(self, name: str) -> Any:
        from poisson_tasks.cli import _card, _doctor, _export, _generate, _init, _run, _verify

        return {
            "init": _init.init, "generate": _generate.generate, "run": _run.run,
            "card": _card.card, "verify": _verify.verify, "export": _export.export,
            "doctor": _doctor.doctor,
        }[name]


_VERBS = _Verbs()
