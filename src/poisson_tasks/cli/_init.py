"""`init`: the guided setup (spec §4.1, §6 and §7.3).

Fetches the tokenizer file first if it is missing (with consent), asks the questions in plain
words, one at a time, each with its default in brackets, writes the settings file once and
atomically at the end, checks the key with a free request (with consent), and prints the same
setup as one command that asks nothing.  The dialogue goes to stderr and is read a line at a
time from stdin.  Every answer becomes one of the library's own flags, so the file is the one
`config.config_from_init_args` writes for them, and a flag the library refuses is refused in
its words, exit 2.
"""

from __future__ import annotations

import datetime
import os
import sys
from pathlib import Path
from typing import Any

from poisson_tasks import config, providers
from poisson_tasks.cli import _format
from poisson_tasks.cli._common import (
    Context,
    config_words,
    host_of,
    tokenizer_present,
)
from poisson_tasks.cli._result import Command, Refusal, Result, Row, Stopped, Usage

SCHEMA = "poisson-tasks.init/1"
TOKENIZER_QUESTION = (
    "Tasks needs a 3.6 MB tokenizer file, fetched once into this environment from "
    "openaipublic.blob.core.windows.net. Fetch it now?"
)
PUBLISHED_MODEL = "gpt-5-nano-2025-08-07"
PUBLISHED_PRICE_SHOWN = "0.05, 0.005, 0.40 — read 2026-09-25; check them"
PUBLISHED_NOTE = (
    "This one has a published card. A first look runs ten of its tasks per level, so you can "
    "read your levels against it; only the published design is comparable in the card's sense."
)
MEASURES = (
    ("first-look", "A first look at depth: tasks 1, 3 and 8 steps deep (recommended)", ""),
    ("card", "The published cards' design: both knobs at every level, with their control arms",
     "comparable with the published cards; 4,200 episodes, about $2.50 on gpt-5-nano"),
    ("custom", "Choose the knob and levels myself", ""),
)
KNOBS = (
    ("depth", "depth: how many chained steps away the goal is", ""),
    ("distractor", "distractor (experimental): how many of the sixteen tools are irrelevant",
     "it does not make tasks harder for either calibrated model"),
)


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
            settings, found, check = _dialogue(ctx, settings, present)
    except KeyboardInterrupt:
        raise _stopped(ctx, fetched) from None

    flags = _words(settings)
    try:
        made = config.config_from_init_args(flags)
    except config.ConfigError as refused:
        raise Usage(str(refused)) from None
    estimate = None
    if made.model.price is not None and _given(settings, "--spend-cap") is None and present:
        estimate = _estimate(made)
        if estimate is not None and estimate.dollars_expected is not None:
            made = config.config_from_init_args(flags, expected_dollars=estimate.dollars_expected)

    # the key
    if found is None:
        if made.model.api_key_env and check is not False:
            found = providers.check_key(made.model)
        elif made.model.api_key_env:
            found = providers.check_key(made.model) if not providers.key_is_set(
                made.model.api_key_env) else None

    # the file, once, atomically
    text = config.dump_config(made)
    path.parent.mkdir(parents=True, exist_ok=True)
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
    rows.append(Command("the same setup, without questions:", command))
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
        },
    )


def _fetch_problem(reason: BaseException) -> str:
    if isinstance(reason, PermissionError):
        return (f"the tokenizer file cannot be written at {reason.filename or ''} "
                "(permission denied)")
    return f"the tokenizer file could not be fetched ({reason})"


def _estimate(made: Any) -> Any:
    try:
        plan = config.resolve_plan(made)
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
# the dialogue (spec §6.1)
# ---------------------------------------------------------------------------


def _dialogue(
    ctx: Context, settings: list[tuple[str, str | None]], present: bool
) -> tuple[list[tuple[str, str | None]], Any, bool | None]:
    """Ask the questions, each defaulting to the flag given, and return the flags the answers
    make, the key check made (or `None`) and whether a check was declined."""
    ui = ctx.ui
    answers: list[tuple[str, str | None]] = list(settings)

    def set_flag(flag: str, value: str | None) -> None:
        answers.append((flag, value))

    # 1. the provider
    names = list(config.PRESET_NAMES)
    given = _given(settings, "--provider")
    default = names.index(given) if given in names else 0
    options = [(config.PRESETS[name].label, "") for name in names]
    provider = names[ui.choice(1, "Which model do you want to test?", options, default)]
    preset = config.PRESETS[provider]
    set_flag("--provider", provider)

    # 2. the model
    model_default = _given(settings, "--model") or preset.default_model
    hint = PUBLISHED_NOTE if provider == "openai" and model_default == PUBLISHED_MODEL else None
    model = ui.ask(2, "The model's name, as the provider spells it", model_default, hint=hint,
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
        endpoint = ui.ask(3, "The endpoint", endpoint,
                          validate=lambda text: None if text.strip() else "A URL is needed.")
    if endpoint is not None:
        set_flag("--base-url", endpoint)

    # 4. the key's variable
    key_default = _given(settings, "--api-key-env")
    if key_default is None:
        key_default = preset.api_key_env
    variable = ui.ask(
        4, "Which environment variable holds your API key?",
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
            5, "Its price, in dollars per million tokens, from your provider's price page.",
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

    # 6. what to measure
    recipe_given = _given(settings, "--recipe")
    recipe_names = [name for name, _, _ in MEASURES]
    default = recipe_names.index(recipe_given) if recipe_given in recipe_names else 0
    recipe = recipe_names[ui.choice(6, "What do you want to measure?",
                                    [(label, note) for _, label, note in MEASURES], default)]
    set_flag("--recipe", recipe)
    if recipe == "custom":
        knob_given = _given(settings, "--knob")
        knob_names = [name for name, _, _ in KNOBS]
        default = knob_names.index(knob_given) if knob_given in knob_names else 0
        knob = knob_names[ui.choice(None, "The knob", [(label, note) for _, label, note in KNOBS],
                                    default)]
        set_flag("--knob", knob)
        from poisson_tasks.knobs import levels

        candidates = levels(knob)
        levels_default = _given(settings, "--levels") or ",".join(str(x) for x in candidates)
        chosen = ui.ask(None, f"The levels, from {_format.words(candidates)}, comma-separated",
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
            None, "Which strictness counts as passing on the progress line and in verify's "
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
        tasks = ui.ask(7, "How many tasks per level?", _given(settings, "--tasks-per-level")
                       or "10",
                       hint="Each task is a different record and a different chain; more tasks "
                            "give tighter numbers.",
                       validate=_whole)
        set_flag("--tasks-per-level", tasks.strip())
        attempts = ui.ask(8, "How many attempts at each task?",
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
        estimate = _estimate(so_far) if present else None
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
        answer = ui.ask(9, "Stop the run once it has spent", given_cap or f"${cap_default:.2f}",
                        hint=hint, shown=given_cap or f"${cap_default:.2f}",
                        validate=_dollars)
        if given_cap is not None or answer.strip().lstrip("$") != f"{cap_default:.2f}":
            set_flag("--spend-cap", answer.strip().lstrip("$"))
    else:
        given_cap = _given(settings, "--token-cap")
        answer = ui.ask(9, "Stop the run once it has used this many tokens",
                        given_cap or "2000000", hint="There is no price, so the cap is in tokens.",
                        shown=given_cap or "2,000,000", validate=_whole)
        if given_cap is not None or answer.replace(",", "").strip() != "2000000":
            set_flag("--token-cap", answer.replace(",", "").strip())
    return answers, found, check


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
