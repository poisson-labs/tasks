"""The guided session (spec §16): a bare `poisson-tasks` on a terminal.

Every action is one of the seven verbs' command lines, built from the folder's state by the
action table (`steps_for` and the `word_*` methods), parsed by the command's own parser and run
through `dispatch`, the function `main` runs a verb through; under each result the session prints
`same as  <the command>`.  The home screen reads the folder through
`poisson_tasks.folder.read_folder` and computes no number of its own.  Nothing here calls a
model: money is spent only by `run`, after its own question, and the session never passes
`--yes` to it.

The session runs inline on the normal screen, in the pretty look when the look's switch allows
it and in the plain look otherwise (numbered menus answered by typing, no escape sequence).
"""

from __future__ import annotations

import dataclasses
import difflib
import json
import os
import shlex
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from poisson_tasks.cli._banner import COBALT

WORDS = ("run", "again", "card", "more", "replies", "task", "verify", "runs", "settings", "setup",
         "flow", "export", "check", "home", "help", "quit")
"""The prompt's closed set of words (spec §16.3)."""
HELP = {
    "run": "start or finish a run; its plan and cost come before it spends",
    "again": "a second run of the same plan",
    "card": "the card of the newest run; card 2 for the second run listed",
    "more": "the whole card, by section",
    "replies": "the model's replies in a run, one episode at a time",
    "task": "look at one task; task 3 for the third, task d3 for the arm whose id ends d3",
    "verify": "check one task's own answers (built-in tasks only)",
    "runs": "every run in this folder",
    "settings": "what tasks.toml says, in words",
    "setup": "set up again; the old tasks.toml is kept as tasks.toml.bak",
    "flow": "add a flow to your tools (your own tools only)",
    "export": "hand the tasks to verifiers",
    "check": "is this environment ready (no network unless you say so)",
    "home": "this folder's status again",
    "help": "these words",
    "quit": "leave (Ctrl-D, or Ctrl-C twice, does the same)",
}
STEPS = (
    ("Set up", "what to test, and against which model", "free"),
    ("One task", "look at one task before anything runs", "free"),
    ("The run", "its plan and cost first; it asks before it spends", ""),
    ("The card", "what each level was worth to the model", "free"),
    ("What next", "your options from here", ""),
)
"""The run-through's five steps (spec §16.4): the name, one line on it, and whether it is free."""
PLAIN_PROMPT = "type a number or a word, then Enter (help, quit): "
WORD_OF_VERB = {"run": "run", "card": "card", "generate": "task", "init": "setup",
                "export": "export", "doctor": "check", "verify": "verify"}
"""The word that stands for a verb when a refusal's `next:` command becomes a step."""
PLATFORMS = {"darwin": "macOS", "linux": "Linux", "win32": "Windows"}


@dataclasses.dataclass
class Step:
    """One step of `next`: its sentence, its word, and the argv it runs (`None` for a view the
    session draws itself, picked by its word)."""

    label: str
    word: str
    argv: list[str] | None


class Leave(Exception):
    """The person is leaving at the prompt: `quit`, Ctrl-D or a second Ctrl-C."""


def _home_words(path: Path) -> str:
    """A folder as the person reads it: `~`-shortened when it is under the home folder."""
    try:
        return "~/" + str(path.resolve().relative_to(Path.home().resolve()))
    except ValueError:
        return str(path.resolve())


def _relative(path: Path) -> str:
    try:
        return os.path.relpath(path)
    except ValueError:
        return str(path)


def _lowest(levels: Sequence[tuple[str, float]]) -> str | None:
    """The arm whose strict pass@1 is lowest: where the model broke most."""
    return min(levels, key=lambda pair: pair[1])[0] if levels else None


def card_reading(folder: Any) -> tuple[Sequence[tuple[str, float]], str]:
    """The newest card's levels on the rate the card reads them on, and that rate's name.  On a
    depth plan of the built-in tasks it is leaky pass@1, as the card says: below the top level
    strict also asks the model to stop at the goal, which the top level cannot ask.  On anything
    else, and on your own tools (a write has no stage past its goal), it is strict pass@1."""
    levels = folder.levels
    built_in = folder.settings is None or folder.settings.own is None
    if (built_in and levels and all(arm.startswith("depth:") for arm, _ in levels)
            and len(folder.leaky_levels) == len(levels)):
        return folder.leaky_levels, "leaky pass@1"
    return levels, "strict pass@1"


# ---------------------------------------------------------------------------
# the action table's `next` (spec §16.3)
# ---------------------------------------------------------------------------


def steps_for(folder: Any) -> list[Step]:
    """The steps for a folder's state (spec §16.3's table), at most five.  A step is offered
    only when its verb accepts this folder: `verify` never on your own tools, `again` only after
    a finished run, `flow` and `replies` on your own tools, `run` not on Windows."""
    from poisson_tasks.cli._common import is_windows

    check = Step("Check this environment", "check", ["doctor", "--offline"])
    if folder.settings is None:
        return [Step("Set up this folder", "setup", None), check]
    own = folder.settings.own is not None
    env = folder.environment
    ready = env.tokenizer == "present" and env.platform_supported
    task = Step("Look at one task", "task", ["generate", "--show"])
    setup = Step("Measure another recipe on your tools" if own else "Change what to measure",
                 "setup", ["init", "--force"])
    export = Step("Hand the tasks to verifiers" + (" (as the poisson-tasks-own taskset)" if own
                                                   else ""), "export", ["export", "--force"])
    again = Step("Run the same plan again (a second run)", "again", ["run", "--again"])
    mine = [run for run in folder.runs if run.this_plan]
    newest = mine[0] if mine else None
    out: list[Step] = []
    if not ready:
        what = ("the tokenizer file is missing; it offers the fetch" if env.tokenizer != "present"
                else "runs need macOS or Linux")
        out.append(Step(f"Check this environment: {what}", "check", ["doctor", "--fix"]))

    def card_of(run: Any, *, named: bool = False) -> list[str]:
        argv = ["card"]
        if named:
            argv.append(_relative(run.path))
        if run.card == "built":
            argv.append("--force")
        return argv

    if newest is None:
        out += [Step("Run it; the plan and its cost come before it spends", "run", ["run"]),
                task, setup, export]
    elif newest.locked:
        out += [Step("Look again", "home", None), task, check]
    elif newest.kept < newest.total:
        out += [Step(f"Finish the stopped run: {newest.kept} of {newest.total} episodes kept "
                     "so far", "run", ["run"]),
                Step("A card from what ran so far (it marks the levels that are partial)",
                     "card", card_of(newest))]
        finished = [run for run in mine if run.kept >= run.total and run.card == "built"]
        if finished:
            number = list(folder.runs).index(finished[0]) + 1
            out.append(Step("Read the card of the finished run", f"card {number}",
                            card_of(finished[0], named=True)))
        out.append(task)
    elif newest.card is None:
        out += [Step("Build the card (free)", "card", ["card"]), task, again]
    elif newest.card == "refused":
        silent = newest.silent_arms[0] if newest.silent_arms else None
        out += [Step("Read the replies the card was refused for", "replies", None),
                Step("Why the card was refused", "card", ["card"]),
                Step("Look at the task it answered in text", "task",
                     ["generate", "--show", "--arm", silent]) if silent else task]
    elif own:
        worst = _lowest(folder.levels)
        flows = folder.tools.flows if folder.tools is not None else 0
        out += [Step("Read the card", "card", card_of(newest)),
                Step(f"Read the replies at {worst}, where it broke most" if worst
                     else "Read the replies", "replies", None),
                Step("Add a flow, so depth and shape can run on your tools" if not flows
                     else f"Add another flow to your tools ({flows} declared)", "flow", None),
                setup, export]
    else:
        out += [Step("Read the card", "card", card_of(newest)),
                Step("Hand these tasks to verifiers", "export", ["export", "--force"]),
                again, setup]
    if is_windows():
        out = [step for step in out if step.word not in ("run", "again")]
    return out[:5]


def first_step_command(prog: str, args: Any) -> str | None:
    """Step 1 of the folder's `next`, as a command, for the off-terminal error (G5); `None`
    for a step that is a view."""
    from poisson_tasks.folder import read_folder

    config_path = args.config or "tasks.toml"
    step = steps_for(read_folder(config_path))[0]
    argv = step.argv if step.argv is not None else (["init"] if step.word == "setup" else None)
    if argv is None:
        return None
    words = [*shlex.split(prog), *argv]
    if args.config is not None:
        words += ["--config", args.config]
    return " ".join(shlex.quote(word) for word in words)


def run_session(prog: str, args: Any, words: list[str]) -> int:
    return Session(prog, args, words).run()


# ---------------------------------------------------------------------------
# the session
# ---------------------------------------------------------------------------


class Session:
    def __init__(self, prog: str, args: Any, words: list[str]) -> None:
        from poisson_tasks import cli

        self.prog = prog
        self.config_path = args.config or "tasks.toml"
        self.config_given = args.config is not None
        self.debug = bool(args.debug)
        self.ui = cli._make_ui(prog, words)
        self.pretty = bool(getattr(self.ui, "pretty", False))
        if self.pretty:
            self.mode = "colour"
        elif "--plain" in words or os.environ.get("TERM") == "dumb":
            self.mode = "line"
        else:
            self.mode = "mono"
        self.steps: list[Step] = []
        self._prompt: Any = None
        self._pressed = False
        self._console: Any = None

    # -- writing ------------------------------------------------------------------------

    @property
    def console(self) -> Any:
        """The session's own console, at the colour depth the terminal declares (B2: the
        chrome's cobalt steps down as the banner's does)."""
        if self._console is None:
            from rich.console import Console

            from poisson_tasks.cli._pretty import WIDTH

            self._console = Console(file=sys.stdout, highlight=False, emoji=False,
                                    legacy_windows=False)
            if self._console.width > WIDTH:
                self._console.width = WIDTH
        return self._console

    def write(self, text: str = "", style: str | None = None) -> None:
        """One line of the session's own: `style` is Rich's, used in the pretty look only."""
        if self.pretty:
            from rich.text import Text

            self.console.print(Text(text, style=style or ""), soft_wrap=True)
        else:
            sys.stdout.write(text + "\n")
            sys.stdout.flush()

    def row(self, label: str, value: str, width: int, style: str | None = None) -> None:
        """A `label  value` line of the status block, the label dim in the pretty look."""
        if self.pretty:
            from rich.text import Text

            self.console.print(Text.assemble((label.ljust(width), "dim"), "  ",
                                             (value, style or "")), soft_wrap=True)
        else:
            self.write(f"{label.ljust(width)}  {value}")

    def heading(self, text: str) -> None:
        self.write()
        if self.pretty:
            from rich.text import Text

            head, _, rest = text.partition(" · ")
            self.console.print(Text.assemble((head, f"bold {COBALT}"), (" · " + rest, "bold")),
                               soft_wrap=True)
        else:
            self.write(text)
        self.write()

    def width(self) -> int:
        return shutil.get_terminal_size().columns

    def height(self) -> int:
        return shutil.get_terminal_size().lines

    # -- reading ------------------------------------------------------------------------

    def read(self, hint: str = PLAIN_PROMPT, *, above: bool = False) -> str:
        """One line at the session's own prompt.  Ctrl-C is `KeyboardInterrupt`, Ctrl-D is
        `EOFError`.  This is never a verb's question: those go through the renderer's `ask`,
        `choice` and `confirm`.  In the pretty look the hint is the prompt's placeholder, which
        goes at the first key, or with `above` a dim line above the prompt."""
        if not self.pretty:
            sys.stdout.write(hint)
            sys.stdout.flush()
            line = sys.stdin.readline()
            if not line:
                raise EOFError
            return line.strip()
        if self._prompt is None:
            from prompt_toolkit import PromptSession
            from prompt_toolkit.completion import WordCompleter
            from prompt_toolkit.key_binding import KeyBindings
            from prompt_toolkit.styles import Style

            keys = KeyBindings()

            @keys.add("c-c")
            def _(event: Any) -> None:
                buffer = event.app.current_buffer
                if buffer.text:
                    buffer.reset()
                else:
                    event.app.exit(exception=KeyboardInterrupt())

            self._prompt = PromptSession(
                completer=WordCompleter(list(WORDS)), complete_while_typing=False,
                key_bindings=keys,
                style=Style([("mark", f"bold {COBALT}"), ("placeholder", "fg:ansibrightblack")]),
            )
        if above:
            self.write(hint.rstrip(": "), "dim")
            placeholder = ""
        else:
            placeholder = hint if hint != PLAIN_PROMPT else (
                "a step's number, a word, help or quit" if self.width() >= 50
                else "a number or a word")
        answer: str = self._prompt.prompt([("class:mark", "› ")],
                                          placeholder=[("class:placeholder", placeholder)])
        return answer.strip()

    # -- the loop -----------------------------------------------------------------------

    def run(self) -> int:
        from poisson_tasks import cli
        from poisson_tasks.cli import _banner

        try:
            _banner.show(mode=self.mode, width=self.width())
            if not Path(self.config_path).is_file():
                self.run_through()
            else:
                self.home()
            while True:
                try:
                    text = self.read()
                except KeyboardInterrupt:
                    if self._pressed:
                        raise Leave from None
                    self._pressed = True
                    self.write("  Press Ctrl-C again to leave, or type a word.", "dim")
                    continue
                except EOFError:
                    raise Leave from None
                self._pressed = False
                try:
                    self.take(text)
                except KeyboardInterrupt:
                    # a Ctrl-C in one of the session's own views: back to the prompt
                    self.write()
        except Leave:
            kept = [name for name in (Path(self.config_path).name,
                                      folder_runs_name(self.config_path))
                    if (Path(self.config_path).parent / name).exists()]
            files = f": {' and '.join(kept)}" if kept else ""
            self.write(f"Left the session. Your files are as they were{files}. "
                       f"Open it again with {self.prog}.")
            return 0
        except Exception as error:  # noqa: BLE001 - the session's own failure, in one line
            path = cli._log_failure(self.prog, error)
            self.ui.error(f"an unexpected failure inside {self.prog} ({type(error).__name__}); "
                          f"the details are in {path}")
            if self.debug:
                import traceback

                sys.stderr.write("".join(traceback.format_exception(type(error), error,
                                                                    error.__traceback__)))
                sys.stderr.flush()
            return 3

    def take(self, text: str) -> None:
        """One line typed at the prompt: Enter is step 1, a number its step, a word its
        action, anything else one line and the prompt again."""
        if not text:
            self.pick(1)
            return
        if text.isdigit():
            self.pick(int(text))
            return
        head, _, rest = text.partition(" ")
        if head not in WORDS:
            close = difflib.get_close_matches(head, WORDS, n=1)
            hint = f"; did you mean {close[0]}?" if close else ";"
            self.write(f'  "{text}" is not a word here{hint} help lists them all', "yellow")
            return
        getattr(self, "word_" + head)(rest.strip())

    def pick(self, number: int) -> None:
        if not self.steps or not 1 <= number <= len(self.steps):
            self.write(f"  there is no step {number} here; help lists the words", "yellow")
            return
        step = self.steps[number - 1]
        if step.argv is None:
            getattr(self, "word_" + step.word)("")
        else:
            self.act(step.argv)

    # -- acting -------------------------------------------------------------------------

    def command(self, argv: Sequence[str]) -> str:
        words = [*shlex.split(self.prog), *argv]
        if self.config_given:
            words += ["--config", self.config_path]
        return " ".join(shlex.quote(word) for word in words)

    def act(self, argv: list[str], *, then: bool = True, extra: Sequence[Step] = ()) -> int:
        """Run one verb's argv as `main` would, show its outcome, then `same as` and, with
        `then`, the steps for the new state (a refusal's `next:` commands first)."""
        from poisson_tasks.cli import _parser, build_parser, dispatch
        from poisson_tasks.cli._common import Context
        from poisson_tasks.cli._result import Usage

        words = [*argv, *(["--config", self.config_path] if self.config_given else [])]
        _parser.set_ui(self.ui)
        try:
            args = build_parser(self.prog).parse_args(words)
        except Usage as wrong:
            self.ui.error(wrong.message)
            return 2
        ctx = Context(prog=self.prog, args=args, ui=self.ui, config_path=self.config_path,
                      config_given=self.config_given, json=False, typed=list(argv))
        code = dispatch(ctx)
        self.write()
        self.write(f"same as  {self.command(argv)}", "dim")
        if then:
            offered = list(extra)
            if ctx.refused is not None:
                offered += self._steps_of_next(ctx.refused.next)
            self.show_next(extra=offered)
        return code

    def _steps_of_next(self, commands: Sequence[str]) -> list[Step]:
        """A refusal's `next:` commands as steps, when they map back to the action table (they
        are complete commands, by N3); one that does not is left as the printed text."""
        prog = shlex.split(self.prog)
        steps = []
        for command in commands:
            try:
                words = shlex.split(command)
            except ValueError:
                continue
            if words[:len(prog)] != prog or len(words) == len(prog):
                continue
            argv = []
            skip = False
            for word in words[len(prog):]:
                if skip:
                    skip = False
                elif word == "--config":
                    skip = True
                elif not word.startswith("--config="):
                    argv.append(word)
            if argv and argv[0] in WORD_OF_VERB:
                steps.append(Step(" ".join(argv), WORD_OF_VERB[argv[0]], argv))
        return steps

    # -- the home screen ----------------------------------------------------------------

    def folder(self) -> Any:
        from poisson_tasks.folder import read_folder

        return read_folder(self.config_path)

    def home(self) -> None:
        """The status block, then `next` for the state (spec §16.3): printed when the session
        opens, after `home`, and after a run."""
        from poisson_tasks.cli import _format
        from poisson_tasks.cli._common import config_words

        folder = self.folder()
        root = Path(self.config_path).parent
        rows: list[tuple[str, str, str | None]] = [("folder", _home_words(root), None)]
        if folder.settings is None:
            rows.append(("settings", folder.problem or
                         f"none yet: setup writes {Path(self.config_path).name} here", None))
        else:
            settings = folder.settings
            rows.append(("settings", f"{config_words(settings)}, against {settings.model.name}",
                         None))
            cap = (_format.dollars(float(settings.limits.spend_usd))
                   if settings.limits.spend_usd is not None else
                   f"{settings.limits.tokens:,} tokens" if settings.limits.tokens is not None
                   else "no cap")
            key = (f"key in {folder.key_variable} ({'set' if folder.key_set else 'not set'})"
                   if folder.key_variable else "no key needed")
            rows.append(("", f"cap {cap} · {key}", "dim"))
        if folder.tools is not None:
            tools = folder.tools
            flows = (f"{tools.flows} flow{'s' if tools.flows != 1 else ''} declared"
                     if tools.flows else
                     "no flows declared, so depth and shape are not offered (add one: flow)")
            rows.append(("your tools", f"{tools.name}: {tools.tools} tools, {tools.refused} "
                         f"refused · {flows}", "yellow" if not tools.flows else None))
        env = folder.environment
        platform = PLATFORMS.get(env.platform, env.platform)
        if env.tokenizer == "present" and env.platform_supported:
            rows.append(("ready", f"python {env.python_version} · {platform} · tokenizer present",
                         None))
        else:
            missing = ("the tokenizer file is missing; check offers the fetch"
                       if env.tokenizer != "present" else
                       f"{platform}: runs need macOS or Linux; generate, card and export work")
            rows.append(("ready", f"python {env.python_version} · {platform} · not yet: "
                         f"{missing}", "yellow"))
        if folder.settings is not None:
            if not folder.runs:
                rows.append(("runs", "none yet", None))
            for index, run in enumerate(folder.runs[:5]):
                spent = f" · {_format.dollars(run.spent_usd)}" if run.spent_usd is not None else ""
                style = None
                if run.locked:
                    holder = (f" (pid {run.holder[0]}, since {run.holder[1]})"
                              if run.holder is not None else "")
                    state, style = f"running in another window{holder}", COBALT
                elif run.kept < run.total:
                    state, style = "stopped partway", "yellow"
                elif run.card == "built":
                    state = "card built"
                elif run.card == "refused":
                    state, style = "card refused", "yellow"
                else:
                    state = "finished, no card yet"
                rows.append(("runs" if index == 0 else "",
                             f"{run.name}   {run.kept} of {run.total}{spent} · {state}", style))
            if len(folder.runs) > 5:
                rows.append(("", f"and {len(folder.runs) - 5} more (runs lists them all)", "dim"))
        if folder.levels:
            read, measure = card_reading(folder)
            levels = " · ".join(f"{arm} {_format.rate(rate)}" for arm, rate in read)
            rows.append(("latest card", f"{levels}  {measure}", None))
        width = max(len(label) for label, _, _ in rows)
        for label, value, style in rows:
            self.row(label, value, width, style)
        self.write()
        self.show_next(folder)

    def show_next(self, folder: Any = None, extra: Sequence[Step] = ()) -> None:
        folder = folder if folder is not None else self.folder()
        self.steps = [*extra, *steps_for(folder)]
        self.write("next", "bold")
        width = max(len(step.label) for step in self.steps)
        for index, step in enumerate(self.steps, 1):
            if self.pretty:
                from rich.text import Text

                self.console.print(Text.assemble("  ", (str(index), f"bold {COBALT}"), "  ",
                                                 step.label.ljust(width), "  ",
                                                 (step.word, "dim")), soft_wrap=True)
            else:
                self.write(f"  {index}  {step.label.ljust(width)}  {step.word}")
        self.write()

    # -- the run-through (spec §16.4) ---------------------------------------------------

    def run_through(self) -> None:
        where = _home_words(Path(self.config_path).parent)
        self.write(f"There is no {Path(self.config_path).name} in {where}, so this starts with "
                   "setup.")
        self.write()
        width = max(len(name) for name, _, _ in STEPS)
        room = max(len(note) for _, note, _ in STEPS)
        for index, (name, note, free) in enumerate(STEPS, 1):
            if self.pretty:
                from rich.text import Text

                self.console.print(Text.assemble("  ", (str(index), f"bold {COBALT}"), "  ",
                                                 name.ljust(width), "  ", note.ljust(room), "  ",
                                                 (free, "dim")), soft_wrap=True)
            else:
                self.write(f"  {index}  {name.ljust(width)}  {note.ljust(room)}  {free}".rstrip())
        self.write()
        self.write("Nothing calls a model until you say yes to the run's cost. Ctrl-C stops the "
                   "step you are in and leaves the folder as it was; you can leave at any prompt "
                   "with quit.")
        self.write()
        if not self._between("Enter to start, or quit: ", starts=("1", "y", "yes")):
            return
        from poisson_tasks.cli._common import tokenizer_present

        self.heading(f"Step 1 of 5 · {STEPS[0][0]}")
        if not tokenizer_present():
            self.act(["doctor", "--fix"], then=False)
        if self.act(["init"], then=False) != 0:
            self.write()
            self.home()
            return
        self.heading(f"Step 2 of 5 · {STEPS[1][0]}")
        self.act(["generate", "--show"], then=False)
        self.write()
        if not self._between("Enter for step 3, the run, or quit: "):
            return
        self.heading(f"Step 3 of 5 · {STEPS[2][0]}")
        code = self.act(["run"], then=False)
        if code != 0:
            self.write()
            if code in (3, 130):
                self.write("The run did not finish. From here you can finish it, or build a card "
                           "from what ran so far.")
                self.write()
            self.home()
            return
        self.heading(f"Step 4 of 5 · {STEPS[3][0]}")
        self.act(["card"], then=False)
        self.heading(f"Step 5 of 5 · {STEPS[4][0]}")
        folder = self.folder()
        if folder.levels:
            from poisson_tasks.cli import _format
            from poisson_tasks.cli._common import config_words

            read, measure = card_reading(folder)
            low = min(read, key=lambda pair: pair[1])
            high = max(read, key=lambda pair: pair[1])
            model = folder.settings.model.name if folder.settings is not None else "the model"
            plan = config_words(folder.settings) if folder.settings is not None else "the plan"
            span = (f"{_format.rate(low[1])} at every level" if low[1] == high[1] else
                    f"from {_format.rate(low[1])} at {low[0]} to {_format.rate(high[1])} at "
                    f"{high[0]}")
            self.write(f"You have a card for {model} on {plan}: {measure} {span}. From here:")
            self.write()
        self.home()

    def _between(self, hint: str, starts: Sequence[str] = ()) -> bool:
        """A prompt between the run-through's steps: Enter, or one of `starts`, goes on; `quit`
        leaves; Ctrl-C ends the run-through on the home screen; any other word ends it and is
        taken there.  The hint is a line of its own above the prompt, so it stays while typing."""
        try:
            text = self.read(hint, above=True)
        except KeyboardInterrupt:
            self.write()
            self.home()
            return False
        except EOFError:
            raise Leave from None
        if text == "quit":
            raise Leave
        if text and text.lower() not in starts:
            self.home()
            self.take(text)
            return False
        return True

    # -- the words ----------------------------------------------------------------------

    def _newest(self, folder: Any, number: str = "") -> Any:
        """The run a word names: `card 2` is the second run listed, else the plan's newest."""
        runs = list(folder.runs)
        if number.isdigit() and 1 <= int(number) <= len(runs):
            return runs[int(number) - 1]
        mine = [run for run in runs if run.this_plan]
        return mine[0] if mine else (runs[0] if runs else None)

    def word_run(self, rest: str) -> None:
        self.act(["run"])

    def word_again(self, rest: str) -> None:
        self.act(["run", "--again"])

    def word_card(self, rest: str) -> None:
        folder = self.folder()
        run = self._newest(folder, rest)
        if run is None:
            self.act(["card"])
            return
        argv = ["card"]
        if rest:
            argv.append(_relative(run.path))
        if run.card == "built":
            argv.append("--force")
        self.act(argv)

    def word_task(self, rest: str) -> None:
        argv = ["generate", "--show"]
        if rest.isdigit():
            argv += ["--task", rest]
        elif rest:
            arm = self._arm_ending(rest)
            if arm is None:
                self.write(f'  no arm of the plan ends "{rest}"; task 3 is the third task of the '
                           "first arm", "yellow")
                return
            argv += ["--arm", arm]
        self.act(argv)

    def _arms(self) -> list[str]:
        from poisson_tasks import config
        from poisson_tasks.knobs import arm_id

        settings = config.load_config(self.config_path)
        plan = config.resolve_plan(settings, root=Path(self.config_path).parent)
        return [str(arm_id(spec)) for spec in plan.arms]

    def _arm_ending(self, end: str) -> str | None:
        return next((arm for arm in self._arms() if arm.endswith(end)), None)

    def word_verify(self, rest: str) -> None:
        folder = self.folder()
        if folder.settings is None:
            self.write("  there is no tasks.toml here yet; setup writes one", "yellow")
            return
        if folder.settings.own is not None:
            self.write("  verify judges the built-in tasks only; on your own tools a run's card "
                       "judges every episode", "yellow")
            return
        self.act(["verify", "--self-check", "--arm", self._arms()[0], "--task", "1"])

    def word_export(self, rest: str) -> None:
        self.act(["export", "--force"])

    def word_check(self, rest: str) -> None:
        self.act(["doctor", "--offline"],
                 extra=[Step("Check the key with a free request", "check", ["doctor"])])

    def word_setup(self, rest: str) -> None:
        if not Path(self.config_path).is_file():
            self.run_through()
            return
        self.act(["init", "--force"])

    def word_flow(self, rest: str) -> None:
        """Four menus over your tools, then `init --force` with the file's own settings plus
        `--own-flow` (G21), so there is no second writer of `tasks.toml`."""
        from poisson_tasks import config, own

        folder = self.folder()
        settings = folder.settings
        if settings is None or settings.own is None:
            self.write("  flow belongs to your own tools; setup chooses them", "yellow")
            return
        table = settings.own
        path = config.own_file_path(table, Path(self.config_path).parent)
        name = table.name if table.name is not None else Path(table.file).stem
        toolset = own.read_tools(Path(path).read_bytes(), format=table.format, name=name).toolset
        self.write("A flow carries a value from one tool's output into another tool's input, so "
                   "a task can chain them.")
        outputs = [tool for tool in toolset.tools
                   if (tool.output_schema or {}).get("properties")]
        inputs = [tool for tool in toolset.tools
                  if (tool.input_schema or {}).get("properties")]
        if not outputs or not inputs:
            self.write("  no tool of this set returns a field another tool takes", "yellow")
            return
        source = outputs[self.ui.choice(1, "Which tool's output?",
                                        [(tool.name, "") for tool in outputs], 0)]
        fields = list((source.output_schema or {}).get("properties", {}))
        field = fields[self.ui.choice(2, "Which field of its output?",
                                      [(f, "") for f in fields], 0)]
        target = inputs[self.ui.choice(3, "Into which tool?",
                                       [(tool.name, "") for tool in inputs], 0)]
        params = list((target.input_schema or {}).get("properties", {}))
        param = params[self.ui.choice(4, "Which of its inputs?", [(p, "") for p in params], 0)]
        command = config.equivalent_init_command(settings, prog=self.prog)
        flags = command[len(shlex.split(self.prog)) + 1:]
        self.act(["init", "--force", *flags, "--own-flow",
                  f"{source.name}.{field}:{target.name}.{param}"])

    # -- the card's sections --------------------------------------------------------------

    def word_more(self, rest: str) -> None:
        folder = self.folder()
        run = self._newest(folder, rest)
        built = [run for run in folder.runs if run.card == "built"]
        if run is None or run.card != "built":
            run = built[0] if built else None
        if run is None:
            self.write("  there is no card yet; card builds one", "yellow")
            return
        text = (run.path / "card" / "card.md").read_text(encoding="utf-8")
        sections: list[tuple[str, list[str]]] = []
        for line in text.splitlines():
            if line.startswith("## "):
                sections.append((line[3:].strip(), []))
            elif sections:
                sections[-1][1].append(line)
        if not sections:
            self.write("  the card has no sections", "yellow")
            return
        chosen = self.ui.choice(None, f"card.md, {len(sections)} sections",
                                [(title, "") for title, _ in sections], 0)
        title, body = sections[chosen]
        self.draw(title, "\n".join(body).strip("\n"))

    def draw(self, title: str, body: str) -> None:
        """One section of the card, drawn from its Markdown: headings, paragraphs and tables as
        tables; through the pager when it is longer than the screen, in the pretty look."""
        from rich.console import Console
        from rich.markdown import Markdown
        from rich.text import Text

        if not self.pretty:
            console = Console(file=sys.stdout, color_system=None, highlight=False, emoji=False,
                              width=self.width(), force_terminal=False)
            console.print(title)
            console.print(Markdown(body))
            return
        console = self.console
        with console.capture() as captured:
            console.print(Text(title, style="bold"))
            console.print(Markdown(body))
        drawn = captured.get()
        pager = shutil.which("less")
        if pager is not None and drawn.count("\n") + 2 > self.height():
            import subprocess

            subprocess.run([pager, "-R"], input=drawn.encode("utf-8"), check=False)
            return
        sys.stdout.write(drawn)
        sys.stdout.flush()

    # -- the replies (G19) ----------------------------------------------------------------

    def word_replies(self, rest: str) -> None:
        """One arm's episodes with their outcomes and the model's last reply, then one episode's
        turns: each call with its arguments and the simulated answer, and the last reply."""
        from poisson_tasks.cli._common import arm_folder

        folder = self.folder()
        run = self._newest(folder, rest)
        if run is None:
            self.write("  there is no run yet; run makes one", "yellow")
            return
        plan = json.loads((run.path / "plan.json").read_text(encoding="utf-8"))["plan"]
        from poisson_tasks.knobs import ArmSpec, arm_id

        ids = [str(arm_id(ArmSpec(**arm))) for arm in plan["arms"]]
        arm = None
        if run.card == "built":
            arm = _lowest(self._levels_of(run))
        elif run.silent_arms:
            arm = run.silent_arms[0]
        if arm not in ids:
            arm = ids[0]
        episodes = self._episodes(run.path / arm_folder(arm), plan["model"]["name"])
        self.write(f"{arm}, {len(episodes)} episode{'s' if len(episodes) != 1 else ''} of "
                   f"{run.name}")
        if plan.get("own"):
            self.write("  The tool responses are simulated from your tools' schemas, so a reply "
                       "can look wrong while the episode passes: it is scored on the calls.", "dim")
        if not episodes:
            self.write("  no episode of this arm ended; run finishes it", "yellow")
            return
        options = []
        for index, (label, calls, reply, _) in enumerate(episodes, 1):
            said = f'  "{reply}"' if reply else ""
            options.append((f"{index:>2}  {label:<14} {calls:>3} calls{said}", ""))
        chosen = self.ui.choice(None, "Which episode?", options, 0)
        self._open_episode(*episodes[chosen])

    @staticmethod
    def _levels_of(run: Any) -> list[tuple[str, float]]:
        try:
            cells = json.loads((run.path / "card" / "artifact.json").read_text(
                encoding="utf-8"))["cells"]
            return [(str(cell["arm_id"]), float(cell["pass_at_1"])) for cell in cells]
        except (OSError, ValueError, KeyError, TypeError):
            return []

    @staticmethod
    def _episodes(arm_dir: Path, model: str) -> list[tuple[str, int, str, str]]:
        """Each kept episode of an arm: its outcome label and call count (the card's own
        records), the model's last reply shortened, and the traces row it was read from."""
        from poisson_tasks import calibration, transcripts

        traces = arm_dir / "traces.jsonl"
        if not traces.is_file():
            return []
        rows = [line.decode("utf-8") for line in traces.read_bytes().splitlines(keepends=True)
                if line.endswith(b"\n")]
        kept = [row for row in rows if json.loads(row).get("ok")]
        records = calibration.records_from_run(arm_dir, model=model)
        out = []
        for index, row in enumerate(kept):
            record = records[index] if index < len(records) else None
            reply = ""
            try:
                transcript = transcripts.read_transcript(row)
                if transcript.ended_with_reply and transcript.turns:
                    reply = " ".join(transcript.turns[-1].content.split())
            except ValueError:
                transcript = None
            if len(reply) > 40:
                reply = reply[:39] + "…"
            label = record.label if record is not None else "not scored"
            calls = record.sampled_calls if record is not None else 0
            out.append((label, calls, reply, row))
        return out

    def _open_episode(self, label: str, calls: int, reply: str, row: str) -> None:
        from poisson_tasks import transcripts

        try:
            transcript = transcripts.read_transcript(row)
        except ValueError as refused:
            self.write(f"  {refused}", "yellow")
            return
        answers = _answers(row)
        self.write()
        number = 0
        for turn in transcript.turns:
            for name, arguments in turn.calls:
                number += 1
                key = f"{name}:{json.dumps(arguments, sort_keys=True, default=str)}"
                answer = answers.get(key)
                self.write(f"  {number}. {name}({json.dumps(arguments, default=str)})")
                if answer:
                    self.write(f"     → {' '.join(str(answer.pop(0)).split())}", "dim")
            if turn.content and not turn.calls:
                self.write(f"  reply  {' '.join(turn.content.split())}")
        self.write(f"  outcome  {label} · {calls} tool call{'s' if calls != 1 else ''}", "bold")
        self.write()

    # -- the other views ------------------------------------------------------------------

    def word_runs(self, rest: str) -> None:
        from poisson_tasks.cli import _format

        folder = self.folder()
        if not folder.runs:
            self.write("  no runs yet; run makes one", "yellow")
            return
        options = []
        for run in folder.runs:
            spent = f" · {_format.dollars(run.spent_usd)}" if run.spent_usd is not None else ""
            state = ("running in another window" if run.locked else
                     "stopped partway" if run.kept < run.total else
                     "card built" if run.card == "built" else
                     "card refused" if run.card == "refused" else "no card yet")
            options.append((f"{run.name}  {run.kept} of {run.total}{spent} · {state}", ""))
        self.write(f"runs in {_home_words(Path(self.config_path).parent)}")
        chosen = self.ui.choice(None, "Which run?", options, 0)
        run = folder.runs[chosen]
        if run.kept < run.total and not run.locked:
            what = self.ui.choice(None, f"{run.name} stopped partway",
                                  [("Finish it", ""), ("A card from what ran so far", "")], 0)
            if what == 0:
                self.act(["run", "--run", _relative(run.path)])
                return
        self.word_card(str(chosen + 1))

    def word_settings(self, rest: str) -> None:
        """What `tasks.toml` says, in words, the settings `init` never asks about included."""
        from poisson_tasks.cli import _format
        from poisson_tasks.cli._common import config_words, host_of

        folder = self.folder()
        settings = folder.settings
        if settings is None:
            self.write(f"  {folder.problem}" if folder.problem else
                       "  there is no tasks.toml here yet; setup writes one", "yellow")
            return
        model = settings.model
        rows = [("model", f"{model.name} at {host_of(model.base_url)}, key in "
                          f"{model.api_key_env or 'none'}")]
        if model.price is not None:
            rows.append(("price", f"${model.price.input} input, ${model.price.cached_input} "
                                  f"cached input, ${model.price.output} output per million "
                                  f"tokens, read {model.price.read_on}"))
        rows.append(("measure", config_words(settings)))
        decoding = settings.decoding
        limits = settings.limits
        rows.append(("decoding", f"temperature {decoding.temperature}, top_p {decoding.top_p}, "
                                 f"reasoning effort {decoding.reasoning_effort}, at most "
                                 f"{decoding.max_tokens} tokens a reply, {limits.max_model_calls} "
                                 "model calls an episode"))
        cap = (f"stops at {_format.dollars(float(limits.spend_usd))}"
               if limits.spend_usd is not None else
               f"stops at {limits.tokens:,} tokens" if limits.tokens is not None else "no cap")
        rows.append(("run", f"{cap} · {limits.concurrency} episodes at a time · into "
                            f"{settings.output.runs}/"))
        self.write(f"settings  {self.config_path}")
        width = max(len(label) for label, _ in rows)
        for label, value in rows:
            self.row(f"  {label}", value, width + 2)
        self.write()
        self.write(f"  Edit {Path(self.config_path).name} to change any of these, or setup to "
                   "answer the questions again.", "dim")
        self.write()

    def word_home(self, rest: str) -> None:
        self.home()

    def word_help(self, rest: str) -> None:
        self.write("Words you can type (or a step's number; Enter takes step 1):")
        for word in WORDS:
            if self.pretty:
                from rich.text import Text

                self.console.print(Text.assemble("  ", (f"{word:<9}", "bold"), " ", HELP[word]),
                                   soft_wrap=True)
            else:
                self.write(f"  {word:<9} {HELP[word]}")
        self.write()

    def word_quit(self, rest: str) -> None:
        raise Leave


def folder_runs_name(config_path: str) -> str:
    """The runs folder's name from the settings file, read for the leaving line alone."""
    try:
        import tomllib

        with open(config_path, "rb") as handle:
            return str(tomllib.load(handle).get("output", {}).get("runs", "runs")) + "/"
    except (OSError, ValueError, TypeError):
        return "runs/"


def _answers(row: str) -> dict[str, list[Any]]:
    """Each sampled call's answer from a traces row, keyed by the call's name and arguments,
    in the order the calls were made; a call the harness refused has none."""
    try:
        import verifiers.v1 as vf
        from pydantic import TypeAdapter

        trace = TypeAdapter(vf.Trace).validate_python(json.loads(row)["traces"][0])
    except (ValueError, KeyError, IndexError, TypeError, ImportError):
        return {}
    open_calls: list[tuple[str, str]] = []
    found: dict[int, Any] = {}
    for node in trace.nodes:
        message = node.message
        if node.sampled and isinstance(message, vf.AssistantMessage):
            for call in message.tool_calls or []:
                try:
                    arguments: Any = json.loads(call.arguments or "{}")
                except ValueError:
                    arguments = call.arguments
                key = f"{call.name}:{json.dumps(arguments, sort_keys=True, default=str)}"
                open_calls.append((call.id, key))
        elif isinstance(message, vf.ToolMessage):
            for index, (call_id, _) in enumerate(open_calls):
                if call_id == message.tool_call_id and index not in found:
                    found[index] = message.content
                    break
    out: dict[str, list[Any]] = {}
    for index, (_, key) in enumerate(open_calls):
        if index in found:
            out.setdefault(key, []).append(found[index])
    return out
