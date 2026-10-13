"""`run`: show the plan and its cost, ask, then run the tasks against the model (spec §4.3, §8).

The order of events is spec §8.1's: the platform, the tokenizer file, the settings file and the
plan, the key's presence, the run folder, the free key check, the tasks and their contrast, the
plan on stdout, the question on stderr, then the run.  Nothing costs money before the run.  A
plan expected to cost more than its cap is refused before the question, with a cap that would
let it finish (the look's item 23); a dry run shows the plan and stops.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

from poisson_tasks import config, providers
from poisson_tasks.cli import _format
from poisson_tasks.cli._common import (
    HARNESS_LINE,
    WINDOWS_LINE,
    Context,
    arm_folder,
    is_windows,
    load_settings,
    model_words,
    need_tokenizer,
    plan_words,
    resolve,
    shown,
)
from poisson_tasks.cli._result import Refusal, Result, Row, Stopped, Usage

SCHEMA = "poisson-tasks.run/1"


def _caps(ctx: Context, settings: Any) -> dict[str, float | int | None]:
    args = ctx.args
    spend = args.spend_cap if args.spend_cap is not None else settings.limits.spend_usd
    tokens = args.token_cap if args.token_cap is not None else settings.limits.tokens
    return {"spend_usd": spend, "tokens": tokens}


def _cap_words(caps: dict[str, float | int | None]) -> str:
    parts = []
    if caps["spend_usd"] is not None:
        parts.append(f"{_format.dollars(float(caps['spend_usd']))}")
    if caps["tokens"] is not None:
        parts.append(f"{_format.count(int(caps['tokens']))} tokens")
    return " or ".join(parts)


def _suggested_cap(expected: float) -> str:
    return f"{config.default_spend_cap(expected):.2f}"


def _folder_words(ctx: Context, folder: Any) -> str:
    text = shown(folder.path)
    if folder.status == "new" and folder.previous is not None:
        changed = _format.words(folder.changed) if folder.changed else "the plan"
        text += f" (a new run: {changed} changed since {folder.previous})"
    elif folder.status == "new":
        text += " (a new run)"
    return text


def _kept_and_total(plan: Any, folder: Any) -> tuple[int, int]:
    """The episodes already kept in the folder, and the plan's total, read as the engine reads
    them: a kept episode is a whole `ok` row of an arm's traces."""
    total = len(plan.arms) * len(plan.seeds) * plan.attempts
    kept = 0
    for spec in plan.arms:
        path = Path(folder.path) / arm_folder(spec) / "traces.jsonl"
        if not path.is_file():
            continue
        for line in path.read_bytes().splitlines(keepends=True):
            if not line.endswith(b"\n"):
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and row.get("ok"):
                kept += 1
    return min(kept, total), total


def _spent(folder: Any, settings: Any) -> tuple[float | None, int]:
    from poisson_tasks import runs

    if not Path(folder.path).is_dir():
        return (0.0 if settings.model.price is not None else None), 0
    ledger = runs.SpendLedger(folder.path, price=settings.model.price)
    return ledger.total_dollars, ledger.total_tokens


def run(ctx: Context) -> Result:
    args = ctx.args
    ui = ctx.ui
    if is_windows():
        raise Refusal(WINDOWS_LINE)
    need_tokenizer(ctx)
    if args.offline and not args.dry_run:
        raise Usage("--offline skips the key check, and is taken only with --dry-run; a run "
                    "that would send something checks the key first")
    settings = load_settings(ctx)
    plan = resolve(settings)
    caps = _caps(ctx, settings)
    if caps["spend_usd"] is None and caps["tokens"] is None:
        raise Refusal("the plan has no cap: set spend_usd or tokens under [limits], or pass "
                      "--spend-cap or --token-cap")
    model = settings.model

    # the key's presence, with no network
    if model.api_key_env and not args.offline and not providers.key_is_set(model.api_key_env):
        found = providers.check_key(model)
        raise Refusal(f"{found.detail}; nothing was spent")

    from poisson_tasks import runs

    try:
        folder = runs.find_run(plan, Path(ctx.config_path).parent / settings.output.runs,
                               again=args.again, name=args.run)
    except ValueError as refused:
        raise Refusal(str(refused)) from None

    spent_dollars, spent_tokens = _spent(folder, settings)
    if folder.status == "complete":
        kept, total = _kept_and_total(plan, folder)
        return _done(ctx, plan, folder, kept, total, 0, spent_dollars, spent_tokens)

    # the free key check (spec §8.1 step 4)
    key_words = "not checked (--offline)"
    if args.offline:
        key_words = ("not checked (--offline)" if model.api_key_env
                     else f"none needed for {model_words(model)}")
    else:
        try:
            check = providers.check_key(model)
        except config.ConfigError as refused:
            raise Refusal(str(refused)) from None
        if check.status in (providers.REFUSED, providers.MODEL_MISSING, providers.UNREACHABLE):
            raise Refusal(f"{check.detail}; nothing was spent")
        if check.status == providers.NOT_CHECKABLE:
            key_words = f"{providers.NOT_CHECKABLE} ({check.detail})"
        elif model.api_key_env:
            key_words = check.status
        else:
            key_words = f"none needed; {check.detail}"

    # the tasks and their contrast (spec §8.1 step 5)
    from poisson_tasks import arms, knobs, tasks

    for seed in plan.seeds:
        bundles = {spec: tasks.generate(spec, seed) for spec in plan.arms}
        for knob in dict.fromkeys(spec.knob for spec in plan.arms):
            group: dict[str, Any] = {knobs.arm_id(spec): bundle for spec, bundle in
                                     bundles.items() if spec.knob == knob}
            if len(group) < 2:
                continue
            report = knobs.check_pins(group)
            if report.refused:
                raise Refusal(arms.describe_pins(report))

    # the plan (spec §8.2)
    kept, total = _kept_and_total(plan, folder)
    left = total - kept
    estimate = None
    try:
        estimate = runs.estimate(plan)
    except (OSError, ValueError) as reason:
        ui.note(f"no estimate: {reason}; the cap is what holds")
    share = left / total if total else 0.0
    expected_dollars = (estimate.dollars_expected * share
                        if estimate is not None and estimate.dollars_expected is not None
                        else None)
    expected_tokens = estimate.tokens_expected * share if estimate is not None else None
    cap_words = _cap_words(caps)
    about = ""
    if expected_dollars is not None:
        about = f"about {_format.about(expected_dollars)}"
    elif expected_tokens is not None:
        about = f"about {_format.count(expected_tokens)} tokens"
    if folder.status == "resume":
        sentence = (f"{_format.count(left)} of {_format.count(total)} episodes left against "
                    f"{model.name}: {about + ' more, ' if about else ''}and the run stops at "
                    f"{cap_words}")
    else:
        sentence = (f"{_format.count(total)} episodes against {model.name}: "
                    f"{about + ', ' if about else ''}and the run stops at {cap_words}")
    rows: list[Any] = [Row("tasks", plan_words(plan) + " · " + (
        "leaky" if any(spec.strictness == "leaky" for spec in plan.arms) else "strict"))]
    if folder.status == "resume":
        spent_words = (f"{_format.dollars(spent_dollars)} spent" if spent_dollars is not None
                       else f"{_format.count(spent_tokens)} tokens used")
        rows.append(Row("resume", f"{_format.count(kept)} of {_format.count(total)} episodes "
                                  f"kept, {spent_words}"))
    key_part = (f"key in {model.api_key_env}: {key_words}" if model.api_key_env
                else key_words)
    rows.append(Row("model", f"{model_words(model)} · {key_part}"))
    if estimate is not None:
        rows.append(Row("calls", f"{_format.count(estimate.calls_min * share)} if every task is "
                                 f"solved the shortest way · about "
                                 f"{_format.count(estimate.calls_expected * share)} expected · "
                                 f"at most {_format.count(estimate.calls_at_cap * share)} "
                                 f"({plan.max_model_calls} per episode)"))
        if expected_dollars is not None:
            rows.append(Row("cost", f"about {_format.about(expected_dollars)} expected · the "
                                    f"run stops at {cap_words}"))
        else:
            rows.append(Row("cost", f"no price, so no dollar figure: about "
                                    f"{_format.count(expected_tokens or 0)} tokens expected · "
                                    f"the run stops at {cap_words}"))
        if estimate.same_model:
            rows.append(Row("estimate", f"from the published {estimate.source} card for this "
                                        "model"))
        else:
            rows.append(Row("estimate", f"from the published {estimate.source} card; your "
                                        "model's usage will differ, and the cap is what holds"))
    else:
        rows.append(Row("cost", f"no estimate for this install; the run stops at {cap_words}"))
    rows.append(Row("harness", HARNESS_LINE))
    rows.append(Row("folder", _folder_words(ctx, folder)))
    plan_result = Result(
        schema=SCHEMA, verdict="plan", tone="neutral", sentence=sentence, rows=rows,
        data={"episodes": total, "left": left, "model": model.name, "folder": folder.name,
              "estimate": None if estimate is None else {
                  "dollars": expected_dollars, "tokens": expected_tokens,
                  "source": estimate.source, "same_model": estimate.same_model},
              "cap": {"spend_usd": caps["spend_usd"], "tokens": caps["tokens"]}},
    )
    ctx.show(plan_result)

    # the cap against the estimate, before the question (the look's item 23)
    over: str | None = None
    if caps["spend_usd"] is not None and expected_dollars is not None:
        if (spent_dollars or 0.0) + expected_dollars > float(caps["spend_usd"]):
            over = (f"this plan is expected to cost about "
                    f"{_format.about((spent_dollars or 0.0) + expected_dollars)} and the cap is "
                    f"{_format.dollars(float(caps['spend_usd']))}, so it would stop partway; "
                    "nothing was spent")
            suggestion = ctx.command("run", "--spend-cap", _suggested_cap(
                (spent_dollars or 0.0) + expected_dollars))
    elif caps["tokens"] is not None and expected_tokens is not None and caps["spend_usd"] is None:
        if spent_tokens + expected_tokens > int(caps["tokens"]):
            needed = int(math.ceil(2 * (spent_tokens + expected_tokens)))
            over = (f"this plan is expected to use about "
                    f"{_format.count(spent_tokens + expected_tokens)} tokens and the cap is "
                    f"{_format.count(int(caps['tokens']))} tokens, so it would stop partway; "
                    "nothing was spent")
            suggestion = ctx.command("run", "--token-cap", str(needed))
    if args.dry_run:
        if over is not None:
            ui.note(over)
        return plan_result
    if over is not None:
        raise Refusal(over, [suggestion])

    # the question (spec §8.1 step 7)
    if not args.yes:
        if not sys.stdin.isatty():
            raise Refusal("stdin is not a terminal; pass --yes to start")
        try:
            wanted = ui.confirm("Start?", False)
        except KeyboardInterrupt:
            raise Stopped(Result(schema=SCHEMA, verdict="stopped", tone="warn",
                                 sentence="not started; nothing was spent", exit=130)) from None
        if not wanted:
            raise Stopped(Result(schema=SCHEMA, verdict="stopped", tone="warn",
                                 sentence="not started; nothing was spent", exit=1))

    # the run (spec §8.3)
    path = Path(folder.path)
    path.mkdir(parents=True, exist_ok=True)
    if model.provider in ("ollama", "vllm") and not (path / "serving.json").exists():
        facts = providers.server_facts(model)
        (path / "serving.json").write_text(json.dumps(facts, indent=2, sort_keys=True) + "\n",
                                           encoding="utf-8")
    from poisson_tasks.cli import reclaim_logging

    reclaim_logging()
    arm_counts = []
    per_arm = len(plan.seeds) * plan.attempts
    for spec in plan.arms:
        kept_here = 0
        traces = path / arm_folder(spec) / "traces.jsonl"
        if traces.is_file():
            kept_here = sum(1 for line in traces.read_bytes().splitlines(keepends=True)
                            if line.endswith(b"\n") and b'"ok": true' in line)
        arm_counts.append((knobs.arm_id(spec), per_arm, min(kept_here, per_arm)))
    concurrency = args.concurrency if args.concurrency is not None else settings.limits.concurrency
    try:
        with ui.progress(total=total, arms=arm_counts, folder=str(path)) as progress:
            result = runs.run_plan(plan, folder, caps=caps, concurrency=concurrency,
                                   events=progress.advance)
    except KeyboardInterrupt:
        kept_now, _ = _kept_and_total(plan, folder)
        spent_now, _ = _spent(folder, settings)
        raise Stopped(Result(
            schema=SCHEMA, verdict="stopped", tone="warn",
            sentence=f"interrupted: {_format.count(kept_now)} of {_format.count(total)} episodes "
                     f"kept{_spent_words(spent_now)}; nothing was lost",
            next=[_resume_command(ctx, folder)], exit=130,
        )) from None
    return _ended(ctx, plan, folder, result, total)


def _spent_words(dollars: float | None) -> str:
    return f", {_format.dollars(dollars)} spent" if dollars is not None else ""


def _resume_command(ctx: Context, folder: Any) -> str:
    """`run` again, naming the folder when the user named one or asked for another."""
    if ctx.args.again or ctx.args.run is not None:
        return ctx.command("run", "--run", folder.name)
    return ctx.command("run")


def _done(ctx: Context, plan: Any, folder: Any, kept: int, total: int, owed: int,
          dollars: float | None, tokens: int) -> Result:
    spent = _spent_words(dollars) if dollars is not None else f", {_format.count(tokens)} tokens"
    if owed:
        owed_words = _format.plural(owed, "failed and is owed again",
                                    "failed and are owed again")
        sentence = (f"{_format.count(kept)} of {_format.count(total)} episodes kept; "
                    f"{owed_words}{spent}")
        nexts = [_resume_command(ctx, folder), ctx.command("card")]
    else:
        sentence = f"{_format.count(kept)} of {_format.count(total)} episodes{spent}"
        nexts = [ctx.command("card")]
    return Result(
        schema=SCHEMA, verdict="done", sentence=sentence,
        rows=[Row("folder", shown(folder.path))], next=nexts,
        data={"folder": folder.name, "episodes_kept": kept, "episodes_total": total,
              "episodes_owed": owed, "spend": dollars, "tokens": tokens},
    )


def _ended(ctx: Context, plan: Any, folder: Any, result: Any, total: int) -> Result:
    kept = result.episodes_kept + result.episodes_run - result.episodes_owed
    kept = min(max(kept, 0), total)
    spent = result.spend
    tokens = result.tokens
    if result.verdict == "done":
        return _done(ctx, plan, folder, kept, total, result.episodes_owed, spent, tokens)
    reason = result.stop_reason
    data = {"folder": folder.name, "stop": reason, "episodes_kept": kept,
            "episodes_total": total, "episodes_owed": result.episodes_owed, "spend": spent,
            "tokens": tokens}
    rows: list[Any] = [Row("folder", shown(folder.path))]
    document = []
    nexts = []
    exit_code = 3
    if reason in ("spend_cap", "token_cap"):
        if reason == "spend_cap":
            cap = _format.dollars(float(ctx.args.spend_cap)) if ctx.args.spend_cap is not None \
                else "the cap"
            raised = config.default_spend_cap(2 * (spent or 0.0) + 0.0)
            if spent is not None:
                raised = max(1.0, float(math.ceil(2 * spent + 1e-9)))
            nexts.append(ctx.command("run", "--spend-cap", f"{raised:.2f}"))
            sentence = (f"the spend cap: {_format.count(kept)} of {_format.count(total)} "
                        f"episodes, {_format.dollars(spent or 0.0)} spent of {cap}; the rest "
                        "are owed")
        else:
            raised_tokens = int(math.ceil(2 * tokens)) if tokens else 2_000_000
            nexts.append(ctx.command("run", "--token-cap", str(raised_tokens)))
            sentence = (f"the token cap: {_format.count(kept)} of {_format.count(total)} "
                        f"episodes, {_format.count(tokens)} tokens used; the rest are owed")
    elif reason == "provider_exhausted":
        sentence = (f"the provider says the account is out of credit after "
                    f"{_format.count(kept)} episodes{_spent_words(spent)}")
    elif reason == "failure_streak":
        first = result.first_error or "no error was recorded"
        sentence = (f"the first {_format.count(result.episodes_run)} episodes all failed before "
                    f"the model answered: {first}; nothing was scored")
    elif reason == "watchdog":
        sentence = ("nothing happened: no model call and no finished episode before the "
                    "start-up watchdog fired; the last lines of run.log follow")
        tail = [line for line in (result.log_tail or "").splitlines() if line.strip()]
        document = [Part_lines("the last lines of run.log", tail)]
        nexts.append(_resume_command(ctx, folder))
    elif reason == "interrupted":
        sentence = (f"interrupted: {_format.count(kept)} of {_format.count(total)} episodes "
                    f"kept{_spent_words(spent)}; nothing was lost")
        nexts.append(_resume_command(ctx, folder))
        exit_code = 130
    else:
        sentence = (f"the run stopped ({reason}): {_format.count(kept)} of "
                    f"{_format.count(total)} episodes kept{_spent_words(spent)}")
        nexts.append(_resume_command(ctx, folder))
    return Result(schema=SCHEMA, verdict="stopped", tone="warn", sentence=sentence, rows=rows,
                  document=document, next=nexts, exit=exit_code, data=data)


def Part_lines(title: str, lines: list[str]) -> Any:
    from poisson_tasks.cli._result import Part

    return Part(title, "lines", lines)
