"""The command's parser: seven verbs, help a stranger can act on, abbreviations refused.

Every verb's help gives a description, help on every argument and at least one example that
starts with the prog (rule L2).  Building the parser imports no module that needs the tokenizer
file or `verifiers`, so `--help` works in any environment.  `init`'s settings flags are the
library's own table (`config.INIT_FLAGS`), each recorded in the order it was typed and handed
to the library as typed, so a value the library refuses is refused in the library's words.
"""

from __future__ import annotations

import argparse
import re
from collections.abc import Sequence
from typing import Any

from poisson_tasks import cards, config
from poisson_tasks.cli._result import Usage

_UI: list[Any] = []
"""The renderer `main` chose, read by `print_help`; empty before `main` runs."""

VERBS = ("init", "generate", "run", "card", "verify", "export", "doctor")


def set_ui(ui: Any) -> None:
    _UI[:] = [ui]


class _Formatter(argparse.HelpFormatter):
    """argparse's own formatter, except that the examples and the exit codes are kept as
    written, one per line."""

    def _fill_text(self, text: str, width: int, indent: str) -> str:
        if text.lstrip().startswith(("examples:", "exit codes:")):
            return "\n".join(indent + line for line in text.splitlines())
        return super()._fill_text(text, width, indent)


class Parser(argparse.ArgumentParser):
    """A command-line mistake is one `error:` line, exit 2; the help is drawn by the renderer."""

    def error(self, message: str) -> Any:
        raise Usage(_plain_words(message))

    def print_help(self, file: Any = None) -> None:
        if _UI and _UI[0].pretty:
            _UI[0].help(self)
        else:
            super().print_help(file)


def _plain_words(message: str) -> str:
    """argparse's message in plain words: no quoted Python list of choices."""
    match = re.match(r"argument (\S+): invalid choice: '(.*)' \(choose from (.*)\)$", message)
    if match:
        where, given, choices = match.groups()
        names = [choice.strip().strip("'") for choice in choices.split(",")]
        what = "a command" if where == "command" else f"a value {where} takes"
        return f'"{given}" is not {what}; it is one of ' + _listed(names)
    return message


def _listed(names: Sequence[str]) -> str:
    if len(names) < 2:
        return "".join(names)
    return ", ".join(names[:-1]) + " or " + names[-1]


class _Setting(argparse.Action):
    """One of init's settings flags, recorded in the order typed as `(flag, value)`."""

    def __call__(self, parser: Any, namespace: Any, values: Any, option_string: Any = None) -> None:
        settings = getattr(namespace, "settings", None)
        if settings is None:
            settings = []
            namespace.settings = settings
        settings.append((option_string, None if self.nargs == 0 else values))


_SETTING_HELP: dict[str, str] = {
    "--provider": "the provider: openai, anthropic, ollama, vllm or openai-compatible",
    "--model": "the model's name, as the provider spells it",
    "--base-url": "the endpoint; required for openai-compatible, else the preset's",
    "--api-key-env": 'the variable that holds the key; "" for none',
    "--allow-plain-http-key": "send the key over plain http to another machine",
    "--price": "the price, dollars per million tokens: input, cached input, output",
    "--price-read-on": "the date the prices were read, as 2026-09-25",
    "--no-price": "no price: the cap is then in tokens",
    "--recipe": "what to measure: first-look, card or custom, or a recipe your tools reach",
    "--measure": "an alias of --recipe, kept for one release",
    "--knob": "with --recipe custom: depth or distractor",
    "--levels": "with --recipe custom: the levels, comma-separated",
    "--controls": "with --recipe custom: add the control arms",
    "--no-controls": "with --recipe custom: no control arms",
    "--strictness": "with --recipe custom: strict or leaky",
    "--tasks-per-level": "how many tasks per level",
    "--seeds": "the tasks' seeds, comma-separated, instead of --tasks-per-level",
    "--attempts": "how many attempts at each task",
    "--generator-version": "the label that enters every task id",
    "--temperature": "the decoding's temperature",
    "--top-p": 'the decoding\'s top-p, or "not sent"',
    "--reasoning-effort": 'the decoding\'s reasoning effort, or "not sent"',
    "--max-tokens": 'the decoding\'s token limit per reply, or "not sent"',
    "--spend-cap": "stop the run once it has spent this many dollars",
    "--token-cap": "stop the run once it has used this many tokens",
    "--max-model-calls": "the model calls allowed per episode",
    "--concurrency": "how many episodes run at once",
    "--runs-dir": "where runs are kept",
    "--tasks-dir": "where generate writes its files",
    "--own-file": "your own tools: the tool file, an OpenAI tools file, an MCP tool list or an "
                  "OpenAPI document, beside tasks.toml",
    "--own-format": "with --own-file: auto, openai, mcp or openapi",
    "--own-name": "with --own-file: the set's name, shown on the card",
    "--own-read": "with --own-file: a tool whose effect the file does not say is a read; "
                  "repeatable",
    "--own-write": "with --own-file: a tool whose effect the file does not say is a write; "
                   "repeatable",
    "--own-intent": "with --own-file: TOOL=TEXT, what a request says instead of the tool's "
                    "name; repeatable",
    "--own-flow": "with --own-file: FROM.FIELD:TO.PARAM, a value from one tool's output into "
                  "another's input, which depth and shape need; repeatable",
}
_OWN_METAVARS = {"--own-file": "PATH", "--own-format": "NAME", "--own-name": "NAME",
                 "--own-read": "TOOL", "--own-write": "TOOL", "--own-intent": "TOOL=TEXT",
                 "--own-flow": "FROM.FIELD:TO.PARAM"}


def _default_words(flag: Any) -> str:
    if flag.flag in config.INIT_FLAG_ALIASES:
        return ""
    if flag.type == "switch":
        return ""
    if flag.flag == "--own-name":
        return " (default: the file's name)"
    if flag.flag.startswith("--own-"):
        return " (default: none)" if flag.default is None else f" (default: {flag.default})"
    if flag.default is None:
        if flag.flag in ("--model", "--base-url", "--api-key-env"):
            return " (default: the preset's; no default for openai-compatible)"
        if flag.flag == "--levels":
            return " (default: every level of the knob)"
        if flag.flag == "--spend-cap":
            return " (default: the larger of $1.00 and twice the estimate)"
        if flag.flag == "--token-cap":
            return " (default: 2,000,000 without a price)"
        if flag.flag == "--price":
            return " (default: the published price for gpt-5-nano-2025-08-07, else none)"
        return " (default: none)"
    return f" (default: {flag.default})"


def _add_setting_flags(parser: Parser) -> None:
    for flag in config.INIT_FLAGS:
        help_text = _SETTING_HELP.get(flag.flag, flag.key) + _default_words(flag)
        if flag.type == "switch":
            parser.add_argument(flag.flag, action=_Setting, nargs=0, help=help_text)
        else:
            metavar = {"integer": "N", "number": "X", "integers": "L,L,…", "prices": "I,C,O",
                       "date": "DATE", "choice": "NAME", "text": "TEXT"}.get(flag.type, "VALUE")
            if flag.flag == "--base-url":
                metavar = "URL"
            parser.add_argument(flag.flag, action=_Setting, metavar=metavar, help=help_text)
    for flag in config.OWN_INIT_FLAGS:
        help_text = _SETTING_HELP.get(flag.flag, flag.key) + _default_words(flag)
        parser.add_argument(flag.flag, action=_Setting, metavar=_OWN_METAVARS[flag.flag],
                            help=help_text)
    parser.add_argument("--mcp-command", metavar="CMD", default=None,
                        help="your own tools from an MCP server: the command that starts it over "
                             "stdio; it is started once, with your consent (--yes is consent), to "
                             "list its tools into tools.mcp.json beside tasks.toml, and stopped; "
                             "the command itself is kept nowhere (default: none)")


def _common(parser: Parser, *, top: bool) -> None:
    """The flags every verb takes, before or after the verb.  On a verb they are
    set only when given, so a value given before the verb survives."""
    default: Any = None if top else argparse.SUPPRESS
    parser.add_argument("--config", metavar="PATH", default=default,
                        help="the settings file to read, or to write (default: ./tasks.toml)")
    parser.add_argument("--json", action="store_true", default=False if top else argparse.SUPPRESS,
                        help="print the result as one JSON document on stdout (default: text)")
    parser.add_argument("--plain", action="store_true", default=False if top else argparse.SUPPRESS,
                        help="the plain style, text only, even on a terminal (default: pretty on "
                             "a terminal, plain in a pipe, under NO_COLOR or CI, or with --json)")
    parser.add_argument("--debug", action="store_true", default=False if top else argparse.SUPPRESS,
                        help="on an unexpected failure, print the traceback as well as writing it "
                             "to the log (default: the log only)")


def _published_names() -> list[str]:
    try:
        return [card.name for card in cards.published()]
    except (OSError, ValueError):
        return []


def build_parser(prog: str) -> argparse.ArgumentParser:
    """The command's parser, every usage line and command it names starting with `prog`."""
    common: dict[str, Any] = {"formatter_class": _Formatter, "allow_abbrev": False}
    parser = Parser(
        prog=prog, **common,
        description="Tool-use tasks with a known right answer, generated on your machine, and a "
                    "card that says what each level of difficulty was worth to the model you ran.",
        epilog=(
            "examples:\n"
            f"  {prog}             on a terminal, with no command: a guided session\n"
            f"  {prog} init        answer a few questions; writes tasks.toml and spends nothing\n"
            f"  {prog} run         show the plan and its cost, ask, then run\n"
            f"  {prog} card        what each level was worth to the model\n"
            f"  {prog} run --help  one command's flags, defaults and examples\n"
            "\n"
            "exit codes:\n"
            "  0    done: the result is printed, whatever it says\n"
            "  1    refused: nothing was spent or written\n"
            "  2    the command line is wrong\n"
            "  3    stopped or failed after work started; what was kept is printed\n"
            "  4    a check you asked for did not pass\n"
            "  130  interrupted\n"
        ),
    )
    parser.add_argument("--version", action="store_true",
                        help="print the version of this package, verifiers and Python, and exit")
    _common(parser, top=True)
    sub = parser.add_subparsers(dest="verb", metavar="command", title="commands")
    sub.required = False

    def verb(name: str, summary: str, description: str, examples: Sequence[str]) -> Parser:
        made: Parser = sub.add_parser(
            name, help=summary, description=description, **common,
            epilog="examples:\n" + "\n".join(f"  {prog} {example}" for example in examples),
        )
        _common(made, top=False)
        return made

    p = verb(
        "init", "ask what to test and write tasks.toml; spends nothing",
        "A guided setup. It asks what to test (a model on the built-in tasks, or on your own "
        "tools), which model, which environment variable holds its key (it records the "
        "variable's name, never the key), what to measure and when to stop, then writes "
        "tasks.toml; doctor --show-command prints the same setup as one command. It fetches "
        "the tokenizer file first if it is missing. It spends nothing.",
        ["init", "init --yes --provider openai --spend-cap 1.00", "init --force",
         "init --yes --recipe custom --knob depth --levels 1,3 --no-check-key",
         "init --own-file tools.json --own-flow get_order.order_id:refund_order.order_id",
         "init --yes --mcp-command 'python my_server.py'"],
    )
    p.add_argument("--yes", action="store_true",
                   help="no questions: every answer from a flag or its default (default: ask)")
    p.add_argument("--force", action="store_true",
                   help="replace an existing settings file (default: refuse)")
    p.add_argument("--fetch", dest="fetch", action="store_true", default=None,
                   help="fetch the tokenizer file if it is missing (default: ask, then fetch)")
    p.add_argument("--no-fetch", dest="fetch", action="store_false",
                   help="do not fetch the tokenizer file; the file is still written, with no "
                        "estimate")
    p.add_argument("--check-key", dest="check_key", action="store_true", default=None,
                   help="check the key with one free request (default: ask, then check)")
    p.add_argument("--no-check-key", dest="check_key", action="store_false",
                   help="make no network call")
    _add_setting_flags(p)
    p.set_defaults(settings=[])

    p = verb(
        "generate", "make the plan's tasks with no model and no network, or show one",
        "Generates the plan's tasks with no model and no network, checks the contrast through "
        "the pin ledger, and writes them as files, one per level, in the form other runners "
        "read. With --show it prints one task the way a model would see it, with its reference "
        "solution and the verdict on every wrong answer it ships with.",
        ["generate", "generate --arm depth:d3 --show --task 7",
         "generate --knob depth --levels 1,3 --tasks-per-level 5 --print"],
    )
    p.add_argument("--arm", metavar="ID", action="append", default=None,
                   help="an arm to generate, as depth:d3; repeatable (default: the settings "
                        "file's plan)")
    p.add_argument("--knob", metavar="NAME", default=None,
                   help="instead of --arm: the knob, depth or distractor; on your own tools, "
                        "any knob the set reaches (default: none)")
    p.add_argument("--levels", metavar="L,L,…", default=None,
                   help="with --knob: the levels, comma-separated (default: every level)")
    p.add_argument("--controls", dest="controls", action="store_true", default=None,
                   help="with --knob: add the control arms (default: no)")
    p.add_argument("--no-controls", dest="controls", action="store_false",
                   help="with --knob: no control arms")
    p.add_argument("--tasks-per-level", metavar="N", type=int, default=None,
                   help="how many tasks per level, the published seeds' first N (default: 10, or "
                        "the settings file's)")
    p.add_argument("--seeds", metavar="S,S,…", default=None,
                   help="the tasks' seeds, comma-separated, instead of --tasks-per-level")
    p.add_argument("--strictness", metavar="NAME", default=None,
                   help="strict or leaky (default: strict, or the settings file's)")
    p.add_argument("--generator-version", metavar="V", default=None,
                   help="the label that enters every task id (default: the package's)")
    p.add_argument("--out", metavar="DIR", default=None,
                   help="where the files go (default: the settings file's tasks folder, or "
                        "./tasks/)")
    p.add_argument("--print", action="store_true",
                   help="write the tasks to stdout as JSON Lines instead of files")
    p.add_argument("--show", action="store_true",
                   help="print one task in full, with one arm; writes nothing")
    p.add_argument("--task", metavar="N", type=int, default=None,
                   help="with --show: the task's place in the plan, counting from 1 (default: 1)")
    p.add_argument("--seed", metavar="S", type=int, default=None,
                   help="with --show: a seed you chose, instead of --task")
    p.add_argument("--force", action="store_true",
                   help="write over files already there (default: refuse)")

    p = verb(
        "run", "show the plan and its cost, ask, then run the tasks against the model",
        "Reads the settings file, generates the tasks, checks the key with a free request, "
        "prints the plan with the expected calls and cost and the cap, asks, then runs every "
        "episode, stopping at the cap and resuming an interrupted run when started again.",
        ["run", "run --yes", "run --dry-run --offline", "run --spend-cap 2.00",
         "run --again"],
    )
    p.add_argument("--yes", action="store_true", help="start without asking (default: ask)")
    p.add_argument("--dry-run", action="store_true",
                   help="print the plan and exit 0; the free key check still runs unless "
                        "--offline")
    p.add_argument("--offline", action="store_true",
                   help="skip the key check; only with --dry-run")
    p.add_argument("--spend-cap", metavar="USD", type=float, default=None,
                   help="stop at this many dollars, for this run (default: the settings file's)")
    p.add_argument("--token-cap", metavar="N", type=int, default=None,
                   help="stop at this many tokens, for this run (default: the settings file's)")
    p.add_argument("--again", action="store_true",
                   help="start a second run of the same plan instead of resuming or reporting "
                        "it complete")
    p.add_argument("--run", metavar="NAME", default=None,
                   help="resume or report the run folder of that name (default: the plan's own)")
    p.add_argument("--concurrency", metavar="N", type=int, default=None,
                   help="how many episodes run at once (default: the settings file's)")

    names = _published_names()
    listed = _listed(names) if names else "none in this install"
    p = verb(
        "card", "what each level was worth, from a run",
        "Builds the card from a run folder: the per-episode records, the machine-readable "
        "artifact and the document, and prints the verdict, a line per level, and the card's "
        "plain statement of what it means and what it does not claim.",
        ["card", "card runs/first-look-my-model", "card --published",
         "card --published " + (names[0] if names else "gpt-5-nano"), "card --print",
         "card runs/first-look-my-model --compare runs/first-look-my-model-2"],
    )
    p.add_argument("run", metavar="RUN", nargs="?", default=None,
                   help="a run folder (default: the settings file's newest run)")
    p.add_argument("--print", action="store_true",
                   help="print the whole card document after the summary")
    p.add_argument("--published", metavar="NAME", nargs="?", const="", default=None,
                   help=f"recompute a card shipped with the package from its records, by the "
                        f"model's short name ({listed}), or every one (default: the run's card)")
    p.add_argument("--page", action="store_true",
                   help="write the one page for every published card, plus this run's card "
                        "when it was measured the same way")
    p.add_argument("--out", metavar="FILE", default=None,
                   help="with --page: where to write it (default: calibration.md)")
    p.add_argument("--compare", metavar="WHAT", default=None,
                   help="put this run's card beside the published ones (--compare published) "
                        "or beside another run's (--compare OTHER_RUN)")
    p.add_argument("--check", metavar="PATH", default=None,
                   help="recompute a card folder, or a calibration bundle .zip, from its records "
                        "and compare it with its artifact; exit 4 on any difference")
    p.add_argument("--force", action="store_true",
                   help="write over a card already there (default: refuse)")

    p = verb(
        "verify", "judge an answer with the task's own verifier, with no model",
        "Runs the verifier a task was generated with. With --self-check, the reference solution "
        "passes and each wrong answer the task ships with earns the outcome it is named for. "
        "With --transcript, your own agent's attempt at the task is judged: OpenAI chat "
        "messages, one row of a verifiers traces.jsonl, or this tool's own turns. Exit 0 when the "
        "verdict is passed, 4 otherwise.",
        ["verify --arm depth:d3 --task 7 --self-check",
         "verify --arm depth:d3 --task 7 --transcript attempt.json",
         "verify --tasks tasks/depth-d3.jsonl --task 2 --self-check"],
    )
    p.add_argument("--arm", metavar="ID", default=None,
                   help="the task's arm, as depth:d3 (default: none; or --tasks)")
    p.add_argument("--task", metavar="N", type=int, default=None,
                   help="the task's place in the plan, counting from 1: the settings file's "
                        "seeds, or the published sixty (default: 1)")
    p.add_argument("--seed", metavar="S", type=int, default=None,
                   help="a seed you chose, instead of --task")
    p.add_argument("--tasks", metavar="FILE", default=None,
                   help="a file generate wrote; --task N counts in it (default: none)")
    p.add_argument("--self-check", action="store_true",
                   help="check the task's own answers: the reference solution and each wrong one")
    p.add_argument("--transcript", metavar="FILE", default=None,
                   help="your agent's attempt, in one of the three forms (default: none)")
    p.add_argument("--hit-turn-limit", action="store_true",
                   help="the attempt was cut off by a turn limit, when the form cannot say")

    p = verb(
        "export", "write the configs another runner reads",
        "Writes the plan's tasks as configs another runner reads: with --to verifiers, one "
        "eval config per level, each the one run uses for that level, and prints the command "
        "that runs it. Run that way, eval leaves out what run adds: the plan, the spend cap, "
        "the instrument tally, the out-of-credit stop, the failure-streak stop and the "
        "watchdog, and it exits 0 when every episode errored.",
        ["export --to verifiers", "export --to verifiers --out configs/"],
    )
    p.add_argument("--to", metavar="RUNNER", default="verifiers",
                   help="the runner (default: verifiers, the one runner there is)")
    p.add_argument("--out", metavar="DIR", default=None,
                   help="where the configs go (default: export/ beside the settings file)")
    p.add_argument("--force", action="store_true",
                   help="write over files already there (default: refuse)")

    p = verb(
        "doctor", "say whether this environment is ready, and what to do if not",
        "Says whether this environment can run the settings file, line by line: Python, the "
        "package, the tokenizer file, the settings, the key, the harness and the platform. "
        "Exit 0 when ready, 4 when not, each failing line ending with what to run. Free.",
        ["doctor", "doctor --fix", "doctor --offline", "doctor --show-command"],
    )
    p.add_argument("--fix", action="store_true",
                   help="fetch the tokenizer file when it is missing, the one thing doctor "
                        "changes (default: report only)")
    p.add_argument("--yes", action="store_true",
                   help="with --fix: fetch without asking")
    p.add_argument("--offline", action="store_true",
                   help="skip the key check, so no socket is opened")
    p.add_argument("--show-command", action="store_true",
                   help="print the init --yes command that writes this settings file")
    return parser
