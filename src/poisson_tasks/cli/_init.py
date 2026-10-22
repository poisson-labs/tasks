"""`init`: the guided setup.

Fetches the tokenizer file first if it is missing (with consent), asks the questions in plain
words, one at a time, each with its default in brackets, writes the settings file once and
atomically at the end, checks the key with a free request (with consent), and prints the same
setup as one command that asks nothing.  The dialogue goes to stderr and is read a line at a
time from stdin.  Every answer becomes one of the library's own flags, so the file is the one
`config.config_from_init_args` writes for them, and a flag the library refuses is refused in
its words, exit 2.

**Your own tools** (changed with the guided session): the first question asks
what to test, a model on the built-in tasks or on your own tools; your own tools then asks for
the file before any recipe, and the built-in recipes' menu has no own-tools entry.  Questions
are numbered as asked, 1 to n.
Choosing own tools asks for the tool file (or starts the MCP server `--mcp-command` names, with
consent, to list its tools into `tools.mcp.json` beside the settings file, the command itself
kept nowhere), reads it, says one summary line and each refusal, asks whether each tool of
unknown effect reads or writes, one question per tool in the file's order (`r`, `w`, or Enter to
leave it unknown and treated as write), then offers the recipes that apply to this set with
`tool-choice` as the default, and after them choosing the knob yourself, which offers every knob
the set reaches, the shipped ones first, each with the knob probe's status in words.  Under
`--yes`, `--own-file` or `--mcp-command` says it all; without `--recipe` the set's default is
taken, and when no recipe applies `init` refuses in one line and writes nothing.
"""

from __future__ import annotations

import datetime
import os
import sys
from pathlib import Path
from typing import Any

from poisson_tasks import arms, config, providers
from poisson_tasks.cli import _format
from poisson_tasks.cli._common import (
    Context,
    _arms_words,
    config_words,
    host_of,
    own_summary,
    tokenizer_present,
)
from poisson_tasks.cli._result import Refusal, Result, Row, Stopped, Usage

SCHEMA = "poisson-tasks.init/1"
TOKENIZER_QUESTION = (
    "Tasks needs a 3.6 MB tokenizer file, fetched once into this environment from "
    "openaipublic.blob.core.windows.net. Fetch it now?"
)
PUBLISHED_MODEL = "gpt-5-nano-2025-08-07"
PUBLISHED_PRICE_SHOWN = "0.05, 0.005, 0.40 — read 2026-09-25; check them"
PUBLISHED_NOTE = (
    "This one has a published card. It was measured on an earlier build of the generator, so a "
    "card from your run cannot be read beside it in this release; the next release measures it "
    "again on the current generator."
)
MEASURES = (
    ("first-look", "A first look at depth: tasks 1, 3 and 8 steps deep (recommended)", ""),
    ("card", "The published cards' design: both knobs at every level, with their control arms",
     "their sixty tasks and five attempts a level; 4,200 episodes, about $2.50 on gpt-5-nano"),
    ("custom", "Choose the knob and levels myself", ""),
)
OWN = "own"
OWN_LABEL = "Tasks on my own tools: an OpenAI tools file, an MCP tool list, or an OpenAPI spec"
CUSTOM_LABEL = "Choose the knob and levels myself"
FILE_QUESTION = ("Your tool file: an OpenAI tools file, an MCP tool list, or an OpenAPI "
                 "document, beside the settings file")
KNOBS = (
    ("depth", "depth: how many chained steps away the goal is", ""),
    ("distractor", "distractor (experimental): how many of the sixteen tools are irrelevant",
     "it does not make tasks harder for either calibrated model"),
)


def _measures() -> list[tuple[str, str, str]]:
    """Question 6's entries: the recipes offered on the built-in tasks in `arms.RECIPES`' order,
    then own tools, then choosing the knob yourself."""
    fixed = {name: (label, note) for name, label, note in MEASURES}
    out: list[tuple[str, str, str]] = []
    for name, recipe in arms.RECIPES.items():
        if not recipe.offered:
            continue
        if name in fixed:
            label, note = fixed[name]
        else:
            asks = recipe.asks
            label = f"{name}: {asks[0].upper()}{asks[1:]}"
            note = _arms_words([arms.arm_from_id(arm_id) for arm_id in recipe.arms])
        out.append((name, label, note))
    out.append((OWN, OWN_LABEL, ""))
    out.append(("custom", CUSTOM_LABEL, ""))
    return out


def _words(settings: list[tuple[str, str | None]]) -> list[str]:
    """The flags as typed, in order, for the library."""
    out: list[str] = []
    for flag, value in settings:
        out.append(flag)
        if value is not None:
            out.append(value)
    return out


def _given(settings: list[tuple[str, str | None]], flag: str) -> str | None:
    """The last value given for `flag`, with an alias read as the flag it stands for."""
    found = None
    for name, value in settings:
        if config.INIT_FLAG_ALIASES.get(name, name) == flag:
            found = value if value is not None else "true"
    return found


def _every(settings: list[tuple[str, str | None]], flag: str) -> list[str]:
    """Every value given for a repeatable flag, in order."""
    return [value for name, value in settings if name == flag and value is not None]


def _without(settings: list[tuple[str, str | None]], *flags: str) -> list[tuple[str, str | None]]:
    return [(name, value) for name, value in settings if name not in flags]


def _stopped(ctx: Context, fetched: bool) -> Stopped:
    tail = " (the tokenizer file was fetched, and stays)" if fetched else ""
    return Stopped(Result(
        schema=SCHEMA, verdict="stopped", tone="warn",
        sentence=f"setup interrupted; {ctx.config_path} was not written{tail}", exit=130,
    ))


def init(ctx: Context) -> Result:
    args = ctx.args
    ui = ctx.ui
    path = Path(ctx.config_path)
    settings: list[tuple[str, str | None]] = list(args.settings)
    if not args.yes and not sys.stdin.isatty():
        raise Refusal(
            "init asks questions and stdin is not a terminal; pass --yes and the answers as "
            f"flags ({ctx.command('init', '--help', settings=False)} lists them)"
        )
    if path.exists() and not args.force:
        raise Refusal(
            f"{ctx.config_path} is already there; edit it, or pass --force to write it again",
            [ctx.command("init", "--force")],
        )

    # the tokenizer file, first
    present = tokenizer_present()
    tokenizer = "present"
    fetched = False
    fetch_problem: str | None = None
    if not args.yes:
        ui.intro(f"Poisson Tasks setup. This writes {ctx.config_path} here and spends nothing. "
                 "Ctrl-C stops without writing.")
    own_setup: _OwnSetup | None = None
    try:
        if not present and args.fetch is not False:
            wanted = args.yes or args.fetch is True or ui.confirm(TOKENIZER_QUESTION, True)
            if wanted:
                try:
                    with ui.status("fetching the tokenizer file"):
                        where = providers.fetch_tokenizer()
                except (OSError, RuntimeError) as reason:
                    fetch_problem = _fetch_problem(reason)
                    tokenizer = "not fetched"
                else:
                    present, fetched, tokenizer = True, True, "fetched"
                    if not args.yes:
                        ui.say(f"fetched {where}", status="ok")
            else:
                tokenizer = "not fetched"
        elif not present:
            tokenizer = "not fetched"

        check: bool | None = args.check_key
        found: Any = None
        if not args.yes:
            settings, found, check, own_setup = _dialogue(ctx, settings, present)
        elif args.mcp_command is not None or _given(settings, "--own-file") is not None:
            # --yes on your own tools: the file (or the listed server) read and summarised,
            # the set's default recipe when none is given
            if args.mcp_command is not None:
                settings = _list_server(ctx, settings, consent=True)
            own_setup = _read_own(ctx, settings)
            _say_summary(ctx, own_setup)
            if _given(settings, "--recipe") is None:
                settings.append(("--recipe", _default_recipe(own_setup)))
    except KeyboardInterrupt:
        raise _stopped(ctx, fetched) from None

    flags = _words(settings)
    try:
        made = config.config_from_init_args(flags)
    except config.ConfigError as refused:
        raise Usage(str(refused)) from None
    if made.own is not None and present:
        # the recipe, or the knob and its levels, on this set: the library's refusal, exit 2
        try:
            config.resolve_plan(made, root=path.parent)
        except config.ConfigError as refused:
            raise Usage(str(refused)) from None
    estimate = None
    if made.model.price is not None and _given(settings, "--spend-cap") is None and present:
        estimate = _estimate(made, path.parent)
        if estimate is not None and estimate.dollars_expected is not None:
            made = config.config_from_init_args(flags, expected_dollars=estimate.dollars_expected)

    # the key
    if found is None:
        if made.model.api_key_env and check is not False:
            found = providers.check_key(made.model)
        elif made.model.api_key_env:
            found = providers.check_key(made.model) if not providers.key_is_set(
                made.model.api_key_env) else None

    # the file, once, atomically; a file it replaces is kept as `<name>.bak` (G10)
    text = config.dump_config(made)
    path.parent.mkdir(parents=True, exist_ok=True)
    kept: Path | None = None
    if path.exists():
        kept = path.with_name(path.name + ".bak")
        kept.write_bytes(path.read_bytes())
    temporary = path.with_name(path.name + ".part")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)

    command = config.equivalent_init_command(made, prog=ctx.prog)
    rows: list[Any] = []
    if tokenizer == "fetched":
        rows.append(Row("tokenizer", "fetched (o200k_base, into "
                                     f"{providers.environment_report().tokenizer_path})"))
    elif tokenizer == "present":
        rows.append(Row("tokenizer", "present"))
    elif fetch_problem is not None:
        rows.append(Row("tokenizer", f"{fetch_problem}; the file was still written, with no "
                                     "estimate"))
    else:
        rows.append(Row("tokenizer", "not fetched, so the plan's estimate cannot be shown; "
                                     f"{ctx.command('doctor', '--fix', settings=False)} "
                                     "fetches it"))
    rows.append(Row("key", _key_words(made, found, check)))
    data: dict[str, Any] = {}
    if own_setup is not None:
        rows.append(Row("your tools", _tools_row(own_setup)))
        data["tools"] = _tools_data(own_setup)
    if kept is not None:
        rows.append(Row("kept", f"the old {path.name} as {kept.name}"))
    rows.append(Row("as one command", f"{ctx.command('doctor', '--show-command')} prints it"))
    sentence = f"wrote {ctx.config_path}: {config_words(made)}, against {made.model.name}"
    return Result(
        schema=SCHEMA, verdict="ok", sentence=sentence, rows=rows,
        next=[ctx.command("run")],
        data={
            "wrote": str(path), "tokenizer": tokenizer,
            "key": {"variable": made.model.api_key_env,
                    "status": found.status if found is not None else
                    ("not checked" if made.model.api_key_env else "none needed")},
            "command": command,
            **data,
        },
    )


def _fetch_problem(reason: BaseException) -> str:
    if isinstance(reason, PermissionError):
        return (f"the tokenizer file cannot be written at {reason.filename or ''} "
                "(permission denied)")
    return f"the tokenizer file could not be fetched ({reason})"


def _estimate(made: Any, root: Path | None = None) -> Any:
    try:
        plan = config.resolve_plan(made, root=root)
        from poisson_tasks import runs

        return runs.estimate(plan)
    except (config.ConfigError, OSError, ValueError):
        return None


def _key_words(made: Any, found: Any, check: bool | None) -> str:
    variable = made.model.api_key_env
    if not variable:
        return f"none needed for {host_of(made.model.base_url)}"
    if found is not None:
        detail: str = found.detail
        return detail
    if check is False:
        return f"{variable} is set (not checked)"
    return f"{variable} is set"


# ---------------------------------------------------------------------------
# the dialogue
# ---------------------------------------------------------------------------


def _dialogue(
    ctx: Context, settings: list[tuple[str, str | None]], present: bool
) -> tuple[list[tuple[str, str | None]], Any, bool | None, _OwnSetup | None]:
    """Ask the questions, each defaulting to the flag given, and return the flags the answers
    make, the key check made (or `None`), whether a check was declined, and the tool file read
    when own tools were chosen."""
    ui = ctx.ui
    answers: list[tuple[str, str | None]] = list(settings)
    own_setup: _OwnSetup | None = None
    asked = _Numbers()

    def set_flag(flag: str, value: str | None) -> None:
        answers.append((flag, value))

    # what to test: the built-in tasks or your own tools (G7)
    wants_own = _given(settings, "--own-file") is not None or ctx.args.mcp_command is not None
    kind = ui.choice(asked(), "What do you want to test?", KINDS, 1 if wants_own else 0)

    # the provider
    names = list(config.PRESET_NAMES)
    given = _given(settings, "--provider")
    default = names.index(given) if given in names else 0
    options = [(config.PRESETS[name].label, "") for name in names]
    provider = names[ui.choice(asked(), "Which provider serves the model?", options, default)]
    preset = config.PRESETS[provider]
    set_flag("--provider", provider)

    # 2. the model
    model_default = _given(settings, "--model") or preset.default_model
    hint = PUBLISHED_NOTE if provider == "openai" and model_default == PUBLISHED_MODEL else None
    model = ui.ask(asked(), "The model's name, as the provider spells it", model_default, hint=hint,
                   validate=lambda text: None if text.strip() else "A name is needed.")
    set_flag("--model", model)

    # 3. the endpoint
    endpoint = _given(settings, "--base-url") or preset.endpoint
    if provider == "openai" and _given(settings, "--base-url") is None and os.environ.get(
        "OPENAI_BASE_URL"
    ):
        endpoint = os.environ["OPENAI_BASE_URL"]
        ui.say(f"endpoint: {endpoint}, from OPENAI_BASE_URL in this shell")
    if preset.asks_endpoint:
        endpoint = ui.ask(asked(), "The endpoint", endpoint,
                          validate=lambda text: None if text.strip() else "A URL is needed.")
    if endpoint is not None:
        set_flag("--base-url", endpoint)

    # 4. the key's variable
    key_default = _given(settings, "--api-key-env")
    if key_default is None:
        key_default = preset.api_key_env
    variable = ui.ask(
        asked(), "Which environment variable holds your API key?",
        key_default if key_default is not None else None,
        hint="Tasks reads the key from it when it runs and never stores or prints it.\n"
             "Answer none for a model that needs no key.",
        shown=(key_default or "none") if key_default is not None else None,
    )
    variable = "" if variable.strip().lower() == "none" else variable.strip()
    set_flag("--api-key-env", variable)
    found: Any = None
    check: bool | None = ctx.args.check_key
    provisional = config.ModelConfig(provider=provider, name=model, base_url=endpoint or "",
                                     api_key_env=variable)
    if variable and providers.key_is_set(variable):
        if check is None:
            check = ui.confirm(f"{variable} is set. Check it with a free request to "
                               f"{host_of(endpoint or '')}?", True, indent="   ")
        if check:
            try:
                with ui.status("checking the key"):
                    found = providers.check_key(provisional)
            except config.ConfigError as refused:
                ui.say(str(refused), status="bad")
            else:
                ui.say(found.detail, status="ok" if found.status == providers.ACCEPTED
                       else "bad")
    elif variable:
        found = providers.check_key(provisional)
        ui.say(found.detail, status="bad")
    else:
        ui.say(f"no key: none is needed for {host_of(endpoint or '')}")

    # 5. the price
    if preset.asks_price:
        prefilled = provider == "openai" and model == PUBLISHED_MODEL
        price_given = _given(settings, "--price")
        price_default: str | None
        if _given(settings, "--no-price") is not None:
            price_default = None
        elif price_given is not None:
            price_default = price_given.replace(",", ", ")
        elif prefilled:
            price_default = "published"
        else:
            price_default = None
        answer = ui.ask(
            asked(), "Its price, in dollars per million tokens, from your provider's price page.",
            price_default,
            hint="It is used for the cost estimate and the spend cap. Input, cached input, output"
                 + ("" if price_default is not None else "; leave it blank for no price, and "
                    "the cap is then in tokens"),
            shown=PUBLISHED_PRICE_SHOWN if price_default == "published" else price_default,
            validate=_valid_price,
        )
        if answer == "published":
            pass
        elif not answer.strip():
            set_flag("--no-price", None)
        else:
            set_flag("--price", ",".join(part.strip() for part in answer.split(",")))
            read_on = _given(settings, "--price-read-on") or datetime.date.today().isoformat()
            set_flag("--price-read-on", read_on)
    elif _given(settings, "--price") is None:
        set_flag("--no-price", None)

    # what to measure: on your own tools, the file first, then its recipes
    if kind == 1:
        answers, own_setup = _own_dialogue(ctx, answers, asked)
        recipe = _given(answers, "--recipe") or ""
    else:
        measures = [entry for entry in _measures() if entry[0] != OWN]
        recipe_given = _given(settings, "--recipe")
        recipe_names = [name for name, _, _ in measures]
        default = recipe_names.index(recipe_given) if recipe_given in recipe_names else 0
        recipe = recipe_names[ui.choice(asked(), "What do you want to measure?",
                                        [(label, note) for _, label, note in measures],
                                        default)]
        set_flag("--recipe", recipe)
    if recipe == "custom" and own_setup is not None:
        pass  # asked in the own-tools dialogue
    elif recipe == "custom":
        knob_given = _given(settings, "--knob")
        knob_names = [name for name, _, _ in KNOBS]
        default = knob_names.index(knob_given) if knob_given in knob_names else 0
        knob = knob_names[ui.choice(asked(), "The knob",
                                    [(label, note) for _, label, note in KNOBS], default)]
        set_flag("--knob", knob)
        from poisson_tasks.knobs import levels

        candidates = levels(knob)
        levels_default = _given(settings, "--levels") or ",".join(str(x) for x in candidates)
        chosen = ui.ask(asked(), f"The levels, from {_format.words(candidates)}, comma-separated",
                        levels_default)
        set_flag("--levels", chosen.replace(" ", ""))
        controls_given = _given(settings, "--controls")
        wants = ui.confirm(
            "Add the control arms? They separate depth from prompt length (or distractors "
            "from block length), and are not difficulty levels.",
            controls_given is not None and _given(settings, "--no-controls") is None,
            indent="   ",
        )
        set_flag("--controls" if wants else "--no-controls", None)
        strictness = ui.ask(
            asked(), "Which strictness counts as passing on the progress line and in verify's "
                     "exit code?",
            _given(settings, "--strictness") or "strict",
            hint="Both are always measured and both are on the card. strict: stop exactly at "
                 "the goal and touch nothing else (what the published cards use); leaky: "
                 "reaching the goal is enough. Leaky tasks carry different task ids, so their "
                 "runs cannot sit beside the published cards.",
        )
        set_flag("--strictness", strictness.strip())
    elif recipe == "card":
        ui.say("The published design fixes sixty tasks per level and five attempts at each, "
               "so the next two questions are not asked.")

    # 7 and 8. the tasks and the attempts
    if recipe != "card":
        tasks = ui.ask(asked(), "How many tasks per level?", _given(settings, "--tasks-per-level")
                       or "10",
                       hint="Each task is a different record and a different chain; more tasks "
                            "give tighter numbers.",
                       validate=_whole)
        set_flag("--tasks-per-level", tasks.strip())
        attempts = ui.ask(asked(), "How many attempts at each task?",
                          _given(settings, "--attempts") or "1",
                          hint="More than one shows pass@k, the chance that one of k attempts "
                               "passes. The published cards use 5.",
                          validate=_whole)
        set_flag("--attempts", attempts.strip())

    # 9. the cap
    try:
        so_far = config.config_from_init_args(_words(answers))
    except config.ConfigError as refused:
        raise Usage(str(refused)) from None
    if so_far.model.price is not None:
        estimate = _estimate(so_far, Path(ctx.config_path).parent) if present else None
        expected = estimate.dollars_expected if estimate is not None else None
        cap_default = config.default_spend_cap(expected)
        if estimate is not None and expected is not None:
            hint = (f"This plan: {_format.count(estimate.episodes)} episodes, about "
                    f"{_format.about(expected)} at the published card's usage. The cap is what "
                    "holds.")
        else:
            hint = ("This plan's estimate cannot be shown without the tokenizer file. The cap "
                    "is what holds.")
        given_cap = _given(settings, "--spend-cap")
        answer = ui.ask(asked(), "Stop the run once it has spent",
                        given_cap or f"${cap_default:.2f}",
                        hint=hint, shown=given_cap or f"${cap_default:.2f}",
                        validate=_dollars)
        if given_cap is not None or answer.strip().lstrip("$") != f"{cap_default:.2f}":
            set_flag("--spend-cap", answer.strip().lstrip("$"))
    else:
        given_cap = _given(settings, "--token-cap")
        answer = ui.ask(asked(), "Stop the run once it has used this many tokens",
                        given_cap or "2000000", hint="There is no price, so the cap is in tokens.",
                        shown=given_cap or "2,000,000", validate=_whole)
        if given_cap is not None or answer.replace(",", "").strip() != "2000000":
            set_flag("--token-cap", answer.replace(",", "").strip())
    return answers, found, check, own_setup


# ---------------------------------------------------------------------------
# your own tools
# ---------------------------------------------------------------------------


class _OwnSetup:
    """The tool file as `init` read it: the reading, the set with the declared effects, the
    declared flows and the file's words."""

    def __init__(self, reading: Any, toolset: Any, flows: tuple[Any, ...], file: str) -> None:
        self.reading = reading
        self.toolset = toolset
        self.flows = flows
        self.file = file

    @property
    def unknown(self) -> list[str]:
        return [tool.name for tool in self.toolset.tools if tool.effect == "unknown"]


def _provisional_own(settings: list[tuple[str, str | None]]) -> Any:
    """The `[own]` table the flags given so far make, through the library, or a usage error."""
    try:
        made = config.config_from_init_args(_words(settings))
    except config.ConfigError as refused:
        raise Usage(str(refused)) from None
    return made.own


def _read_own(ctx: Context, settings: list[tuple[str, str | None]]) -> _OwnSetup:
    """Read the tool file the flags name, with the declared effects and flows; a file that
    cannot be read, or that the readers refuse as a whole, is a refusal in one line."""
    from poisson_tasks import own
    from poisson_tasks.own.generator import Flow, check_flows

    table = _provisional_own(settings)
    if table is None:
        raise Refusal("no tool file: pass --own-file PATH, or --mcp-command CMD to list a "
                      "server's tools")
    path = config.own_file_path(table, Path(ctx.config_path).parent)
    try:
        data = Path(path).read_bytes()
    except OSError as error:
        raise Refusal(f"the tool file {table.file} cannot be read ({error.strerror})") from None
    name = table.name if table.name is not None else Path(table.file).stem
    try:
        reading = own.read_tools(data, format=table.format, name=name)
        toolset = own.apply_effects(reading.toolset, read=table.read, write=table.write)
    except own.OwnToolsError as refused:
        lines = [str(refused)] + [each.line for each in getattr(refused, "refused", ()) or ()]
        raise Refusal(f"{table.file}: " + "; ".join(lines)) from None
    flows = tuple(Flow(*flow) for flow in table.flows)
    try:
        check_flows(toolset, flows)
    except ValueError as refused:
        raise Usage(f"--own-flow: {refused}") from None
    return _OwnSetup(reading, toolset, flows, table.file)


def _say_summary(ctx: Context, setup: _OwnSetup) -> None:
    """One summary line, then each refusal, and the sentence on depth and shape when no flow
    is declared."""
    from poisson_tasks.own.generator import UNAVAILABLE_WITHOUT_FLOWS

    ui = ctx.ui
    lines = own_summary(setup.reading, setup.toolset)
    refused = len(setup.reading.refused)
    ui.say(lines[0])
    for line in lines[1:1 + refused]:
        ui.say(line)
    for line in lines[1 + refused:]:
        ui.say(line)
    if not setup.flows:
        ui.say("depth and shape are not offered without a flow, a link you declare from one "
               "tool's output field into another tool's input (--own-flow "
               "get_order.id:refund_order.order_id, or [[own.flow]] in tasks.toml; the guided "
               f"session's flow step writes one; docs/own-tools.md explains them). "
               f"{UNAVAILABLE_WITHOUT_FLOWS}", status="warn")


def _list_server(
    ctx: Context, settings: list[tuple[str, str | None]], *, consent: bool
) -> list[tuple[str, str | None]]:
    """Start the MCP server `--mcp-command` names, once, to list its tools into
    `tools.mcp.json` beside the settings file, and point `--own-file` at that file; the
    command is kept nowhere (decided 2026-10-13)."""
    from poisson_tasks import own

    command = str(ctx.args.mcp_command)
    if not consent:
        raise Refusal(f"not started: {command} would be started only with your consent")
    try:
        with ctx.ui.status("listing the server's tools"):
            listed = own.list_mcp_tools(command, consent=True)
    except own.OwnToolsError as refused:
        raise Refusal(str(refused)) from None
    target = Path(ctx.config_path).parent / config.OWN_LIST_FILE
    if target.exists() and target.read_bytes() != listed and not ctx.args.force:
        raise Refusal(
            f"{target} is already there and holds another list; pass --force to write it again",
            [ctx.command("init", "--force")],
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".part")
    temporary.write_bytes(listed)
    temporary.replace(target)
    if not ctx.args.yes:
        ctx.ui.say(f"listed {len(json_tools(listed))} tools into {target.name}", status="ok")
    return [*_without(settings, "--own-file"), ("--own-file", config.OWN_LIST_FILE)]


def json_tools(listed: bytes) -> list[Any]:
    import json

    tools = json.loads(listed).get("tools")
    return list(tools) if isinstance(tools, list) else []


def _default_recipe(setup: _OwnSetup) -> str:
    """The set's default recipe, or a refusal in one line naming what is missing (decided
    2026-10-13, narrowed at 23:26 that day)."""
    from poisson_tasks.own import recipes

    found = recipes.default_recipe(setup.toolset, flows=setup.flows)
    if found is not None:
        return str(found)
    raise Refusal(_no_recipe_words(setup))


def _no_recipe_words(setup: _OwnSetup) -> str:
    from poisson_tasks.own import recipes

    shipped = list(arms.SHIPPED_KNOBS)
    reached = recipes.offered_knobs(setup.toolset, flows=setup.flows)
    missing = []
    if not setup.flows:
        missing.append("a flow ([[own.flow]], --own-flow) for depth")
    if shipped:
        missing.append(f"a level of {_format.words(shipped, 'or')}, the knobs that shipped, "
                       "which this set does not reach")
    else:
        missing.append("a knob that shipped from the knob probe, of which there is none yet")
    knobs = (f"; the knobs this set reaches are {_format.words(reached)}, which --recipe custom "
             "--knob takes") if reached else ""
    return (f"no recipe applies to {setup.toolset.name} ({setup.file}): it needs "
            f"{_format.words(missing)}{knobs}")


def _tools_row(setup: _OwnSetup) -> str:
    lines = own_summary(setup.reading, setup.toolset)
    first = lines[0]
    names = [each.line.split(":", 1)[0] for each in setup.reading.refused]
    if names:
        first = first.replace(" (one line each below)", f" ({', '.join(names)})")
    return (f"{setup.toolset.name}: {first}; {lines[1 + len(setup.reading.refused)]}; the "
            "responses are simulated from your schemas, and your backend is never called")


def _tools_data(setup: _OwnSetup) -> dict[str, Any]:
    toolset = setup.toolset
    return {
        "name": toolset.name, "file": setup.file, "tools": len(toolset.tools),
        "source_format": toolset.source_format, "file_digest": toolset.file_digest,
        "refused": [each.line for each in setup.reading.refused],
        "unknown": setup.unknown, "flows": len(setup.flows),
    }


def _own_dialogue(
    ctx: Context, answers: list[tuple[str, str | None]], asked: _Numbers
) -> tuple[list[tuple[str, str | None]], _OwnSetup]:
    """Own tools chosen at question 6: the file, its summary, the unknowns, the recipes that
    apply to this set and, after them, the knob menu of every knob the set reaches."""
    from poisson_tasks.own import card as own_card
    from poisson_tasks.own import recipes
    from poisson_tasks.own.generator import knob_levels

    ui = ctx.ui
    if ctx.args.mcp_command is not None:
        command = str(ctx.args.mcp_command)
        wanted = ui.confirm(
            f"Start {command} to list its tools? It is stopped once the list is read, and no "
            "tool of it is called.", True, indent="   ")
        answers = _list_server(ctx, answers, consent=wanted)
    else:
        given = _given(answers, "--own-file")
        root = Path(ctx.config_path).parent

        def readable(text: str) -> str | None:
            if not text.strip():
                return "A path is needed."
            if not (root / text.strip()).is_file():
                return f"There is no file at {text.strip()}."
            return None

        file = ui.ask(asked(), FILE_QUESTION, given, validate=readable)
        answers = [*_without(answers, "--own-file"), ("--own-file", file.strip())]
    setup = _read_own(ctx, answers)
    _say_summary(ctx, setup)

    # the tools of unknown effect, one question each, in the file's order
    declared = set(_every(answers, "--own-read")) | set(_every(answers, "--own-write"))
    for tool in setup.unknown:
        if tool in declared:
            continue
        answer = ui.ask(
            asked(), f"{tool}: does it read, or write? r, w, or Enter to leave it unknown "
                  "(treated as write)", None,
            validate=lambda text: None if text.strip().lower() in ("", "r", "w", "read", "write")
            else "r, w, or Enter.",
        ).strip().lower()
        if answer in ("r", "read"):
            answers.append(("--own-read", tool))
        elif answer in ("w", "write"):
            answers.append(("--own-write", tool))
    if any(flag in ("--own-read", "--own-write") for flag, _ in answers):
        setup = _read_own(ctx, answers)

    # the recipes that apply to this set, then choosing the knob yourself
    table = recipes.recipes_for(setup.toolset, flows=setup.flows)
    offered = [(name, recipe) for name, recipe in table.items() if recipe.offered]
    options: list[tuple[str, str]] = []
    names: list[str] = []
    for name, recipe in offered:
        asks = recipe.asks
        used = [arms.arm_from_id(arm, generator_version="own-1") for arm in recipe.arms]
        options.append((f"{name}: {asks[0].upper()}{asks[1:]}", _arms_words(used)))
        names.append(name)
    options.append((CUSTOM_LABEL, "every knob this set reaches"))
    names.append("custom")
    if not offered:
        ui.say(_no_recipe_words(setup), status="warn")
    recipe_given = _given(answers, "--recipe")
    default_name = recipes.default_recipe(setup.toolset, flows=setup.flows) or "custom"
    default = names.index(recipe_given) if recipe_given in names else names.index(default_name)
    chosen = names[ui.choice(asked(), f"What do you want to measure on {own_words_of(setup)}?",
                             options, default)]
    answers.append(("--recipe", chosen))
    if chosen != "custom":
        return answers, setup

    # the knob menu: every knob the set reaches, the shipped ones first, with the probe's status
    reached = recipes.offered_knobs(setup.toolset, flows=setup.flows)
    shipped = recipes.shipped_knobs(setup.toolset, flows=setup.flows)
    ordered = [*shipped, *(knob for knob in reached if knob not in shipped)]
    statuses = own_card.probe_statuses(ordered)
    knob_options = []
    for knob in ordered:
        if knob in statuses:
            said = "; ".join(f"{status} on {model}" for model, status in statuses[knob].items())
            note = f"the knob probe on the built-in tasks: {said}"
        else:
            note = "measured on the published cards, not by the knob probe"
        if knob in shipped:
            note += "; shipped"
        knob_options.append((knob, note))
    knob_given = _given(answers, "--knob")
    knob_default = ordered.index(knob_given) if knob_given in ordered else 0
    knob = ordered[ui.choice(asked(), "The knob", knob_options, knob_default)]
    answers.append(("--knob", knob))
    candidates = knob_levels(setup.toolset, knob, flows=setup.flows)
    levels_default = _given(answers, "--levels") or ",".join(str(x) for x in candidates)
    chosen_levels = ui.ask(asked(),
                           f"The levels, from {_format.words(candidates)}, comma-separated",
                           levels_default)
    answers.append(("--levels", chosen_levels.replace(" ", "")))
    strictness = ui.ask(
        asked(), "Which strictness counts as passing on the progress line and in verify's exit "
                 "code?",
        _given(answers, "--strictness") or "strict",
        hint="Both are always measured and both are on the card. strict: stop exactly at the "
             "goal and touch nothing else; leaky: reaching the goal is enough.",
    )
    answers.append(("--strictness", strictness.strip()))
    return answers, setup


class _Numbers:
    """The questions' numbers, as asked: 1 to n, no gap, none twice."""

    def __init__(self) -> None:
        self.n = 0

    def __call__(self) -> int:
        self.n += 1
        return self.n


KINDS = [
    ("A model on the built-in tasks",
     "Tasks with a known right answer, at a difficulty you choose; export hands them to "
     "verifiers."),
    ("A model on your own tools",
     "Your tools file or MCP server; responses are simulated from your schemas."),
]


def own_words_of(setup: _OwnSetup) -> str:
    return f"your tools ({setup.toolset.name})"


def _valid_price(text: str) -> str | None:
    if text in ("", "published"):
        return None
    parts = [part.strip() for part in text.split(",")]
    try:
        numbers = [float(part) for part in parts]
    except ValueError:
        numbers = []
    if len(numbers) != 3 or any(number < 0 for number in numbers):
        return "Three numbers, as 0.05, 0.005, 0.40; or leave it blank for no price."
    return None


def _whole(text: str) -> str | None:
    if text.replace(",", "").strip().isdigit():
        return None
    return "A whole number."


def _dollars(text: str) -> str | None:
    try:
        float(text.strip().lstrip("$"))
    except ValueError:
        return "An amount in dollars, as 1.00."
    return None
