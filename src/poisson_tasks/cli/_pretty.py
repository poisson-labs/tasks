"""The pretty style: the same facts in the same order as the plain style, drawn with Rich, with
questionary for `init`'s two menus (rule L16, ruled 2026-10-13).

Colour has four meanings and no others: green, the command did what was asked (`ok`, `done`,
`passed`); yellow, it stopped short or cannot say (`stopped`, `refused`, `note:`); red, an
error or a failed check (`error:`, `not ready`); dim, secondary text.  A verdict word that is
neither good nor bad (`plan`) is bold with no colour, and a number is never coloured.  Only the
terminal's sixteen named colours, bold and dim are used, so the user's theme decides the shades.
A command printed for the user to copy is never hard-wrapped.  Questions and progress stay on
stderr, and a live display is removed when the work ends.  A table too wide for the terminal
moves a unit every cell repeats into its header, with nothing dropped (the look's item 27).

`poisson_tasks.cli.main` makes this renderer only when the switch allows it (stdout and stderr
both terminals, `NO_COLOR` unset or empty, `CI` unset, `TERM` not `dumb`, a UTF-8 stdout, and
neither `--json` nor `--plain`), so nothing here needs a fallback of its own.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import textwrap
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

from rich import box
from rich.console import Console, Group
from rich.live import Live
from rich.padding import Padding
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn
from rich.table import Table
from rich.text import Text

from poisson_tasks.cli import _format
from poisson_tasks.cli._plain import continued_command
from poisson_tasks.cli._result import Bullets, Command, Levels, Part, Result, Row

TONE = {"good": "bold green", "neutral": "bold", "warn": "bold yellow", "bad": "bold red"}
MARK = {"ok": ("✓", "green"), "bad": ("✗", "bold red"), "warn": ("!", "yellow"),
        "note": ("·", "dim"), "refused": ("!", "yellow")}
WIDTH = 104
"""The widest the pretty style draws, so a wide terminal does not stretch its lines."""


def make_console(stream: Any, *, stderr: bool = False) -> Console:
    console = Console(file=stream, stderr=stderr, color_system="standard", highlight=False,
                      emoji=False, legacy_windows=False)
    if console.width > WIDTH:
        console.width = WIDTH
    return console


class Pretty:
    pretty = True

    def __init__(self, prog: str, *, out: Console, err: Console) -> None:
        self.prog = prog
        self.stdout = out
        self.stderr = err
        self._session: Any = None
        self._output: Any = None

    # -- results --------------------------------------------------------------------------

    def show(self, result: Result) -> None:
        out = self.stdout
        # the verdict line is never hard-wrapped: the first line carries the whole sentence
        out.print(Text.assemble((result.verdict, TONE.get(result.tone, "bold")),
                                "  " + result.sentence), soft_wrap=True)
        marked = any(isinstance(row, Row) and row.status for row in result.rows)
        width = out.width

        def one_line(row: Any) -> bool:
            # a label longer than 12 heads its own line, unless its value is short enough to
            # sit beside it: `as one command  <prog> doctor --show-command prints it`
            if len(row.label) <= 12:
                return True
            if isinstance(row, Bullets) or "\n" in row.value:
                return False
            return len(row.label) + 4 + (3 if marked else 0) + len(row.value) <= width

        labels = [row.label for row in result.rows if isinstance(row, (Row, Bullets))
                  and one_line(row)]
        label_width = max((len(label) for label in labels), default=0)

        def emit(prefix: Text, value: str, indent: int, style: str = "") -> None:
            # wrapped at spaces, never inside a path, a URL or a quoted value; a word longer
            # than the line is left whole for the terminal to fold; the row's indent is kept
            room = max(10, width - indent)
            lines: list[str] = []
            for part in value.split("\n"):
                lines += textwrap.wrap(part, room, break_long_words=False,
                                       break_on_hyphens=False) or [""]
            first = Text.assemble(prefix, (lines[0], style))
            out.print(first, soft_wrap=True)
            for line in lines[1:]:
                out.print(Text.assemble(" " * indent, (line, style)), soft_wrap=True)

        for row in result.rows:
            if isinstance(row, (Row, Bullets)) and not one_line(row):
                out.print(Text("  " + row.label, style="bold"))
                if isinstance(row, Row):
                    emit(Text("    "), row.value, 4)
                else:
                    for item in row.items:
                        emit(Text.assemble("    ", ("•", "dim"), " "), item, 6)
            elif isinstance(row, Row):
                prefix = Text("  ")
                if marked:
                    mark, style = MARK.get(row.status or "ok", MARK["ok"])
                    prefix.append(mark, style=style)
                    prefix.append("  ")
                prefix.append(row.label.ljust(label_width), style="dim")
                prefix.append("  ")
                value = row.value.replace(", ", "\n") if row.label == "wrote" else row.value
                emit(prefix, value, len(prefix.plain), "bold" if row.status == "bad" else "")
            elif isinstance(row, Bullets):
                prefix = Text("  " + ("   " if marked else ""))
                prefix.append(row.label.ljust(label_width), style="dim")
                prefix.append("  ")
                indent = len(prefix.plain)
                for index, item in enumerate(row.items):
                    head = prefix if index == 0 else Text(" " * indent)
                    emit(Text.assemble(head, ("•", "dim"), " "), item, indent + 2)
            elif isinstance(row, Levels):
                out.print()
                out.print(Padding(levels_table(row.cells, width=out.width - 2), (0, 0, 0, 2)))
                out.print()
            elif isinstance(row, Command):
                out.print(Text("  " + row.label, style="dim"))
                out.print(Text("\n".join(continued_command(row.argv))), soft_wrap=True)
        for part in result.document:
            out.print()
            if part.kind == "document":
                out.print(Text(str(part.body).rstrip("\n")), soft_wrap=True)
                continue
            out.print(Text(part.title, style="bold"))
            self._part(part)
        if result.next and (result.document or len(result.rows) > 3):
            out.print()
        for command in result.next:
            out.print(Text.assemble(("next: ", "dim"), (command, "bold")), soft_wrap=True)

    @staticmethod
    def _items(items: Sequence[str]) -> Table:
        made = Table.grid(padding=(0, 1))
        made.add_column(width=1, style="dim")
        made.add_column(overflow="fold")
        for item in items:
            made.add_row("•", item)
        return made

    @staticmethod
    def _value(row: Row) -> Text:
        value = row.value
        if row.label == "wrote" and ", " in value:
            value = value.replace(", ", "\n")
        text = Text(value)
        if row.status == "bad":
            text.stylize("bold")
        return text

    def _part(self, part: Part) -> None:
        out = self.stdout
        if part.kind == "quote":
            out.print(Padding(Panel(Text(str(part.body)), box=box.ROUNDED, border_style="dim",
                                    padding=(0, 1)), (0, 0, 0, 2)))
        elif part.kind == "text":
            out.print(Padding(Text(str(part.body)), (0, 0, 0, 2)))
        elif part.kind == "code":
            out.print(Padding(Text(str(part.body), style="dim"), (0, 0, 0, 2)))
        elif part.kind == "lines":
            out.print(Padding(Text("\n".join(str(line) for line in part.body)), (0, 0, 0, 2)))
        elif part.kind == "tools":
            grid = Table.grid(padding=(0, 2))
            grid.add_column(width=1)
            grid.add_column(no_wrap=True)
            grid.add_column(style="dim", overflow="fold")
            for name, params, needed in part.body:
                grid.add_row(Text("●" if needed else " "),
                             Text(name, style="bold" if needed else "dim"), f"({params})")
            out.print(Padding(grid, (0, 0, 0, 2)))
            out.print(Text("  ● the reference solution calls it", style="dim"))
        elif part.kind == "steps":
            grid = Table.grid(padding=(0, 1))
            grid.add_column(no_wrap=True)
            grid.add_column(overflow="fold")
            for index, (name, arguments, returns) in enumerate(part.body, 1):
                grid.add_row(f"{index}.", Text.assemble((name, "bold"), f"({arguments})"))
                grid.add_row("", Text(f"→ {returns}", style="dim"))
            out.print(Padding(grid, (0, 0, 0, 2)))
        elif part.kind == "answers":
            grid = Table.grid(padding=(0, 3))
            grid.add_column(no_wrap=True)
            grid.add_column(no_wrap=True)
            grid.add_column(style="dim", overflow="fold")
            for what, outcome, extra in part.body:
                grid.add_row(what, Text(outcome, style="bold green" if outcome == "passed"
                                        else "bold"), extra or "")
            out.print(Padding(grid, (0, 0, 0, 2)))

    def help(self, parser: Any) -> None:
        """The same help argparse prints, from the same parser: the usage, the description,
        each group of flags with its help, then the examples and the exit codes."""
        import argparse

        out = self.stdout
        plain = argparse.HelpFormatter(parser.prog, width=out.width)
        usage = Text(parser.format_usage().rstrip())
        usage.stylize("dim", 0, len("usage:"))
        out.print(usage, soft_wrap=True)
        out.print()
        out.print(Text(" ".join(str(parser.description or "").split())))

        def block(title: str, rows: list[tuple[str, str]], strong: bool = True) -> None:
            out.print()
            out.print(Text(title, style="bold"))
            grid = Table.grid(padding=(0, 3))
            grid.add_column(no_wrap=True, style="bold" if strong else "")
            grid.add_column(overflow="fold")
            for left, right in rows:
                text = Text(right)
                at = right.rfind("(default")
                if at >= 0:
                    text.stylize("dim", at)
                grid.add_row(left, text)
            out.print(Padding(grid, (0, 0, 0, 2)))

        for group in parser._action_groups:
            rows: list[tuple[str, str]] = []
            for action in group._group_actions:
                if action.help is argparse.SUPPRESS:
                    continue
                if isinstance(action, argparse._SubParsersAction):
                    rows += [(choice.dest, choice.help or "") for choice in action._choices_actions]
                else:
                    rows.append((plain._format_action_invocation(action),
                                 " ".join(str(action.help or "").split())))
            if rows:
                block(f"{group.title}:", rows)
        for chunk in str(parser.epilog or "").strip().split("\n\n"):
            title, *lines = chunk.splitlines()
            rows = []
            for line in lines:
                left, _, right = line.strip().partition("  ")
                rows.append((left, right.strip()))
            block(title, rows, strong=title.startswith("examples"))

    def json(self, result: Result) -> None:
        sys.stdout.write(result.as_json())
        sys.stdout.flush()

    def raw(self, text: str) -> None:
        self.stdout.print(Text(text), soft_wrap=True)

    def error(self, message: str, next: Sequence[str] = ()) -> None:
        self.stderr.print(Text.assemble(("error:", "bold red"), " " + message), soft_wrap=True)
        for command in next:
            self.stderr.print(Text.assemble(("  next: ", "dim"), (command, "bold")),
                              soft_wrap=True)

    def note(self, message: str) -> None:
        self.stderr.print(Text.assemble(("note:", "yellow"), " " + message), soft_wrap=True)

    # -- the dialogue (all of it on stderr) --------------------------------------------------

    def _prompt_session(self) -> Any:
        if self._session is None:
            from prompt_toolkit import PromptSession
            from prompt_toolkit.output import create_output

            self._output = create_output(stdout=sys.stderr)
            self._session = PromptSession(output=self._output)
        return self._session

    def _line(self, tokens: list[tuple[str, str]]) -> str:
        """One typed line, on stderr.  Ctrl-C raises, so the caller prints the stop line."""
        try:
            answer: str = self._prompt_session().prompt(tokens, style=_style())
        except EOFError:
            raise KeyboardInterrupt from None
        return answer.strip()

    def intro(self, text: str) -> None:
        first, _, rest = text.partition(". ")
        self.stderr.print(Text.assemble((first + ("." if rest else ""), "bold"),
                                        (" " + rest if rest else "", "dim")))

    def gap(self) -> None:
        self.stderr.print()

    def say(self, text: str, status: str | None = None) -> None:
        if status in MARK:
            mark, style = MARK[status]
            self.stderr.print(Text.assemble((f"   {mark} ", style), text))
        else:
            self.stderr.print(Text("\n".join(f"   {line}" if line else ""
                                             for line in text.split("\n")), style="dim"))

    def confirm(self, question: str, default: bool, *, indent: str = "") -> bool:
        preface, _, ask = question.rpartition(". ")
        if preface:
            self.stderr.print(Text(indent + preface.replace("\n", " ") + "."))
        tokens = [("class:question", f"{indent}{ask} "),
                  ("class:instruction", "[Y/n] " if default else "[y/N] ")]
        while True:
            answer = self._line(tokens).lower()
            if not answer:
                return default
            if answer in ("y", "yes"):
                return True
            if answer in ("n", "no"):
                return False
            self.stderr.print(Text(f"{indent}Answer y or n.", style="yellow"))

    def choice(self, number: int | None, question: str, options: Sequence[tuple[str, str]],
               default: int) -> int:
        """A menu answered with the arrow keys; up to nine options each also take its number,
        as a single key.  questionary refuses a tenth single-key shortcut, so a longer menu (a
        run's episodes on setup's defaults, a card's sections, a tool file's tools) has none,
        and each option carries its number in its own words instead, as the plain look's do."""
        import questionary

        self.stderr.print()
        keyed = len(options) <= 9
        width = len(str(len(options)))
        choices = []
        for index, (label, note) in enumerate(options):
            title = label if keyed else f"{index + 1:>{width}}) {label}"
            choices.append(questionary.Choice(title, value=index,
                                              shortcut_key=str(index + 1) if keyed else False,
                                              description=note.replace("\n", " ") or None))
        self._prompt_session()
        answer: int = questionary.select(
            question, choices=choices, default=choices[default],
            qmark=f"{number}." if number is not None else "", pointer="❯", use_shortcuts=keyed,
            style=_question_style(),
            instruction=(f"(arrow keys or 1-{len(options)}, then Enter)" if keyed
                         else "(arrow keys, then Enter)"),
            output=self._output,
        ).unsafe_ask()
        return answer

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
        self.stderr.print()
        bracket = ([("class:instruction", f"[{shown if shown is not None else default}] ")]
                   if default is not None else [])
        head = f"{number}. {question}" if number is not None else f"   {question}"
        if hint:
            self.stderr.print(Text(head, style="bold"))
            self.stderr.print(Text("\n".join(f"   {line}" for line in hint.split("\n")),
                                   style="dim"))
            tokens = [("class:question", "   › ")] + bracket
        else:
            tokens = [("class:question", head + " ")] + bracket
        while True:
            answer = self._line(tokens) or (default or "")
            problem = validate(answer) if validate else None
            if problem is None:
                return answer
            self.stderr.print(Text(f"   {problem}", style="yellow"))
            tokens = [("class:question", "   › ")] + bracket

    @contextlib.contextmanager
    def status(self, text: str) -> Iterator[None]:
        with self.stderr.status(Text(text, style="dim"), spinner="dots", spinner_style="default"):
            yield

    def progress(self, *, total: int, arms: Sequence[tuple[str, int, int]],
                 folder: str) -> _Progress:
        return _Progress(self, total=total, arms=arms, folder=folder)


def _style() -> Any:
    from prompt_toolkit.styles import Style

    return Style([("question", "bold"), ("instruction", ""), ("", "")])


def _question_style() -> Any:
    import questionary

    # questionary's defaults colour the mark, the answer and the default option; none of those
    # colours means anything here, so each is set back to the terminal's own text colour.
    return questionary.Style([
        ("qmark", "fg:default bold"), ("question", "fg:default bold"),
        ("answer", "fg:default nobold"), ("pointer", "fg:default bold"),
        ("highlighted", "fg:default bold"), ("selected", "fg:default bg:default noreverse"),
        ("instruction", "fg:default"), ("text", "fg:default"), ("disabled", "fg:default"),
    ])


# ---------------------------------------------------------------------------
# the card's levels, and the over-wide table rule
# ---------------------------------------------------------------------------


BAR_WIDTH = 17


def _bar(estimate: float, low: float, high: float, width: int = BAR_WIDTH) -> Text:
    """The interval on a 0-to-1 track, so a wide interval looks wide."""
    def at(value: float) -> int:
        return round(value * (width - 1))

    point, start, end = at(estimate), at(low), at(high)
    text = Text()
    for index in range(width):
        if index == point:
            text.append("●", style="bold")
        elif index == start:
            text.append("├")
        elif index == end:
            text.append("┤")
        elif start < index < end:
            text.append("─")
        else:
            text.append("·", style="dim")
    return text


def _levels_table(cells: Sequence[Mapping[str, Any]], *, units_in_cells: bool) -> Table:
    table = Table(box=box.SIMPLE_HEAD, pad_edge=False, header_style="dim", border_style="dim",
                  show_edge=False)
    table.add_column("level", no_wrap=True)
    table.add_column("strict pass@1", justify="right", no_wrap=True)
    table.add_column("95% interval", no_wrap=True)
    table.add_column("0 " + "·" * (BAR_WIDTH - 4) + " 1", no_wrap=True)
    table.add_column("leaky", justify="right", no_wrap=True)
    table.add_column("overshoot", justify="right", no_wrap=True)
    table.add_column("tasks" if units_in_cells else "tasks × attempts", no_wrap=True)
    for cell in cells:
        planned = int(cell["tasks_planned"])
        attempts = int(cell.get("attempts") or 1)
        if cell["state"] == "not run":
            times = f"0 of {planned}" + (" tasks" if units_in_cells else "")
            table.add_row(str(cell["arm_id"]), "", "", "", "", "",
                          Text(f"{times}\nnot run", style="yellow"))
            continue
        tasks = int(cell["tasks"])
        if units_in_cells:
            times = (f"{tasks} of {planned} tasks" if cell["state"] == "incomplete"
                     else _format.plural(tasks, "task"))
            times += f" × {_format.plural(attempts, 'attempt')}"
        else:
            times = (f"{tasks} of {planned}" if cell["state"] == "incomplete" else str(tasks))
            times += f" × {attempts}"
        times_cell: Any = times
        if cell["state"] == "incomplete":
            times_cell = Text(f"{times}\nincomplete", style="yellow")
        low, high = cell["interval"]
        table.add_row(
            str(cell["arm_id"]), Text(_format.rate(cell["pass_at_1"]), style="bold"),
            _format.interval(low, high), _bar(cell["pass_at_1"], low, high),
            _format.rate(cell["leaky_at_1"]), _format.rate(cell["overshoot"]), times_cell,
        )
    return table


def _natural_width(table: Table, width: int) -> int:
    """How wide the table draws when nothing in it is wrapped or cut."""
    with open(os.devnull, "w") as sink:
        measured = Console(width=max(width, 20), file=sink, color_system=None)
        return int(table.__rich_measure__(measured, measured.options).maximum)


def levels_table(cells: Sequence[Mapping[str, Any]], *, width: int) -> Any:
    """The card's levels for a terminal `width` columns wide.  When the table with its units in
    every cell (`10 tasks × 1 attempt`) would be wider than the terminal, the units move into the
    header (`tasks × attempts`) and the figures stay (the look's item 27); when even that is
    wider, the levels are printed as the plain style prints them, one wrapped line each, so
    nothing is cut."""
    table = _levels_table(cells, units_in_cells=True)
    if _natural_width(table, width) <= width:
        return table
    table = _levels_table(cells, units_in_cells=False)
    if _natural_width(table, width) <= width:
        return table
    from poisson_tasks.cli._plain import level_line

    grid = Table.grid(padding=(0, 2))
    grid.add_column(no_wrap=True, style="bold")
    grid.add_column(overflow="fold")
    for cell in cells:
        grid.add_row(str(cell["arm_id"]), level_line(cell))
    return grid


# ---------------------------------------------------------------------------
# progress: one bar per level, the passes counted, removed when the run ends
# ---------------------------------------------------------------------------


class _Progress:
    """One bar per arm and one summary line, drawn on stderr and removed when the run ends, so
    what stays on screen is the plan and then the verdict.  Each arm's passes are counted from
    its `traces.jsonl` as lines are appended (the look's item 20)."""

    def __init__(self, ui: Pretty, *, total: int, arms: Sequence[tuple[str, int, int]],
                 folder: str) -> None:
        self.ui = ui
        self.total = max(1, total)
        self.folder = Path(folder)
        self.started = time.monotonic()
        self.bars = Progress(
            TextColumn("  {task.description}"),
            BarColumn(bar_width=30, style="dim", complete_style="default",
                      finished_style="default"),
            TextColumn("{task.completed:>3.0f}/{task.total:.0f}"),
            TextColumn("{task.fields[passed]}", style="dim"),
            console=ui.stderr,
        )
        self.tasks: dict[str, Any] = {}
        self.offsets: dict[str, int] = {}
        self.passed: dict[str, int] = {}
        self.done: dict[str, int] = {}
        for arm, count, kept in arms:
            self.done[arm] = kept
            self.passed[arm] = 0
            self.tasks[arm] = self.bars.add_task(arm, total=count, completed=kept, passed="")
        self.summary = Text()
        self.live = Live(Group(self.bars, self.summary), console=ui.stderr, transient=True,
                         refresh_per_second=12)

    def __enter__(self) -> _Progress:
        for arm in self.tasks:
            self._count(arm)
        self._summarise(0)
        self.live.start()
        return self

    def _count(self, arm: str) -> None:
        """The passes recorded in the arm's traces since the last look."""
        name = arm.replace("/", "-").replace(":", "-").replace("@", "-")
        path = self.folder / name / "traces.jsonl"
        try:
            size = path.stat().st_size
        except OSError:
            return
        offset = self.offsets.get(arm, 0)
        if size < offset:
            offset, self.passed[arm] = 0, 0
        with path.open("rb") as handle:
            handle.seek(offset)
            chunk = handle.read()
        lines = chunk.split(b"\n")
        whole = lines[:-1]
        self.offsets[arm] = offset + sum(len(line) + 1 for line in whole)
        for line in whole:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if not isinstance(row, dict) or not row.get("ok"):
                continue
            traces = row.get("traces") or []
            if not traces:
                continue
            reward = (traces[0].get("rewards") or {}).get("strict")
            score = reward.get("score") if isinstance(reward, dict) else reward
            if score == 1:
                self.passed[arm] += 1

    def _summarise(self, done: int, spend: float | None = None) -> None:
        spent = f" · {_format.dollars(spend)} spent" if spend is not None else ""
        self.summary.plain = (f"  {done}/{self.total} episodes{spent} · "
                              f"{_format.duration(time.monotonic() - self.started)}")
        self.summary.stylize("dim")

    def advance(self, event: Mapping[str, Any]) -> None:
        arm = str(event.get("arm", ""))
        if arm in self.tasks:
            self.done[arm] += 1
            self._count(arm)
            passed = self.passed[arm]
            self.bars.update(self.tasks[arm], completed=self.done[arm],
                             passed=f"{passed} passed" if passed else "")
        spend = event.get("spend")
        self._summarise(int(event.get("episodes_done", 0)),
                        float(spend) if spend is not None else None)

    def __exit__(self, *exc: object) -> None:
        self.live.stop()

