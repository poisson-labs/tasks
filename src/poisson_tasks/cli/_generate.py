"""`generate`: make the plan's tasks with no model and no network, and look at one (spec §4.2).

The tokenizer file is checked before anything that generates is imported.  The plan is the
settings file's, or the flags' (`--arm`, or `--knob` with `--levels`).  Every task is made, the
contrast is checked through the pin ledger seed by seed, and only then are the files written,
one per arm, each line the task in the wire form other runners read; `--print` sends the same
lines to stdout and `--show` prints one task in full and writes nothing.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from poisson_tasks import arms, config
from poisson_tasks.cli import _format
from poisson_tasks.cli._common import (
    Context,
    arm_folder,
    load_settings,
    need_tokenizer,
    plan_words,
    refuse_overwrite,
    resolve,
    settings_exist,
    shown,
)
from poisson_tasks.cli._result import Part, Refusal, Result, Row, Usage

SCHEMA = "poisson-tasks.generate/1"


def _plan_from_flags(ctx: Context) -> tuple[Any, Path]:
    """The flags' plan, and where its files go by default."""
    args = ctx.args
    flags: list[str] = []
    if args.knob is not None:
        flags += ["--recipe", "custom", "--knob", args.knob]
        if args.levels is not None:
            flags += ["--levels", args.levels]
        if args.controls is not None:
            flags.append("--controls" if args.controls else "--no-controls")
        if args.strictness is not None:
            flags += ["--strictness", args.strictness]
    if args.seeds is not None:
        flags += ["--seeds", args.seeds]
    elif args.tasks_per_level is not None:
        flags += ["--tasks-per-level", str(args.tasks_per_level)]
    if args.generator_version is not None:
        flags += ["--generator-version", args.generator_version]
    if args.arm:
        version = args.generator_version or arms.DEFAULT_GENERATOR_VERSION
        try:
            specs = tuple(
                arms.arm_from_id(arm_id, strictness=args.strictness or "strict",
                                 generator_version=version)
                for arm_id in args.arm
            )
        except ValueError as refused:
            raise Usage(str(refused)) from None
        try:
            made = config.config_from_init_args([flag for flag in flags])
        except config.ConfigError as refused:
            raise Usage(str(refused)) from None
        if made.tasks.seeds is not None:
            seeds = made.tasks.seeds
        else:
            from poisson_tasks import calibration

            seeds = calibration.seed_list()[: made.tasks.per_level or 10]
        plan = config.Plan(
            preset="custom", arms=specs, seeds=tuple(seeds), attempts=made.tasks.attempts,
            model=made.model, decoding=config.resolve_plan(made).decoding,
            max_model_calls=made.limits.max_model_calls,
        )
        return plan, Path("tasks")
    try:
        made = config.config_from_init_args(flags)
        plan = config.resolve_plan(made)
    except config.ConfigError as refused:
        raise Usage(str(refused)) from None
    return plan, Path("tasks")


def _plan(ctx: Context) -> tuple[Any, Path, int]:
    """The plan, where its files go, and the turn cap a run allows."""
    args = ctx.args
    if args.arm or args.knob is not None:
        if args.arm and args.knob is not None:
            raise Usage("--arm and --knob are two ways to name the arms; give one of them")
        plan, folder = _plan_from_flags(ctx)
        cap = config.INIT_FLAGS[[flag.flag for flag in config.INIT_FLAGS].index(
            "--max-model-calls")].default
        return plan, folder, int(cap)
    if not settings_exist(ctx) and not ctx.config_given:
        raise Refusal(
            f"there is no settings file at {ctx.config_path} and no --arm or --knob was given; "
            f"{ctx.command('init', settings=False)} writes one, or name the arms",
            [ctx.command("init")],
        )
    settings = load_settings(ctx)
    plan = resolve(settings)
    folder = Path(ctx.config_path).parent / settings.output.tasks
    return plan, folder, settings.limits.max_model_calls


def generate(ctx: Context) -> Result:
    need_tokenizer(ctx)
    args = ctx.args
    plan, folder, turn_cap = _plan(ctx)
    if args.show:
        return _show(ctx, plan, turn_cap)
    if args.out is not None:
        folder = Path(args.out)

    from poisson_tasks import knobs, tasks

    made: dict[Any, list[Any]] = {spec: [] for spec in plan.arms}
    sentences: list[str] = []
    for index, seed in enumerate(plan.seeds):
        bundles = {spec: tasks.generate(spec, seed) for spec in plan.arms}
        for spec, bundle in bundles.items():
            made[spec].append(bundle)
        for knob in dict.fromkeys(spec.knob for spec in plan.arms):
            group: dict[str, Any] = {knobs.arm_id(spec): bundle for spec, bundle in
                                     bundles.items() if spec.knob == knob}
            if len(group) < 2:
                if index == 0:
                    sentences.append(f"one arm, {next(iter(group))}: there is no contrast to "
                                     "check")
                continue
            report = knobs.check_pins(group)
            sentence = arms.describe_pins(report)
            if report.refused:
                raise Refusal(sentence)
            if index == 0:
                sentences.append(sentence)

    from poisson_tasks.export import task_from_bundle

    def line(bundle: Any) -> str:
        text: str = task_from_bundle(bundle).data.model_dump_json()
        return text

    if args.print:
        for spec in plan.arms:
            for bundle in made[spec]:
                sys.stdout.write(line(bundle) + "\n")
        sys.stdout.flush()
        return Result(schema=SCHEMA, verdict="ok", sentence="printed", silent=True)

    paths = [folder / f"{arm_folder(spec)}.jsonl" for spec in plan.arms]
    refuse_overwrite(paths, args.force, ctx, "generate")
    folder.mkdir(parents=True, exist_ok=True)
    wrote = []
    for spec, path in zip(plan.arms, paths, strict=True):
        path.write_text("".join(line(bundle) + "\n" for bundle in made[spec]), encoding="utf-8")
        wrote.append(f"{shown(path)} ({_format.plural(len(made[spec]), 'task')})")
    total = sum(len(bundles) for bundles in made.values())
    return Result(
        schema=SCHEMA, verdict="ok",
        sentence=f"generated {_format.plural(total, 'task')}: {plan_words(plan)}, no model and "
                 "no network",
        rows=[Row("pin ledger", " ".join(sentences)), Row("wrote", ", ".join(wrote))],
        next=[ctx.command("run")],
        data={"tasks": total, "files": [str(path) for path in paths], "pin_ledger": sentences},
    )


# ---------------------------------------------------------------------------
# --show
# ---------------------------------------------------------------------------


def task_name(arm_id: str, place: int | None, seed: int) -> str:
    """How a task is named everywhere: by its arm and its place, and its seed (ruled
    2026-10-03); by the arm and the seed alone for a seed the user chose."""
    if place is None:
        return f"{arm_id} seed {seed}"
    return f"{arm_id} task {place} (seed {seed})"


def pick_task(plan: Any, spec: Any, place: int | None, seed: int | None) -> tuple[Any, str]:
    """The bundle `--task N` or `--seed S` names in the plan, and its name."""
    from poisson_tasks import knobs, tasks

    arm_id = knobs.arm_id(spec)
    if seed is not None:
        return tasks.generate(spec, seed), task_name(arm_id, None, seed)
    place = 1 if place is None else place
    if place < 1 or place > len(plan.seeds):
        raise Refusal(
            f"--task {place} is out of range: the plan has "
            f"{_format.plural(len(plan.seeds), 'task')} per level, counted from 1"
        )
    chosen = plan.seeds[place - 1]
    return tasks.generate(spec, chosen), task_name(arm_id, place, chosen)


def wrong_answers(bundle: Any) -> list[tuple[str, str, str, bool]]:
    """Each wrong answer the task ships with: its name, the label it earns, the sentence for
    it, and whether that is the outcome it is named for."""
    from poisson_tasks import outcomes, tasks

    fmt = tasks.FormatSpec(name="direct", markers=())
    out = []
    for name, calls in bundle.negative_controls.items():
        limit = name == "turn_limit"
        turns = tuple(tasks.Turn(content="", calls=(call,), finish_reason="tool_calls")
                      for call in calls)
        if not limit:
            turns += (tasks.Turn(content="Done.", calls=(), finish_reason="stop"),)
        verdict = tasks.verify(bundle, turns, not limit, limit, fmt)
        expected = name.split("_clause")[0]
        out.append((name, verdict.label, outcomes.describe(verdict), verdict.label == expected))
    return out


def reference_verdict(bundle: Any) -> Any:
    from poisson_tasks import tasks

    fmt = tasks.FormatSpec(name="direct", markers=())
    turns = tuple(tasks.Turn(content="", calls=(call,), finish_reason="tool_calls")
                  for call in bundle.reference_calls)
    turns += (tasks.Turn(content="Done.", calls=(), finish_reason="stop"),)
    return tasks.verify(bundle, turns, True, False, fmt)


def _show(ctx: Context, plan: Any, turn_cap: int) -> Result:
    args = ctx.args
    if len(plan.arms) != 1:
        raise Usage(f"--show prints one task, and the plan has {len(plan.arms)} arms; name one "
                    "with --arm")
    spec = plan.arms[0]
    bundle, name = pick_task(plan, spec, args.task, args.seed)
    calls = len(bundle.reference_calls)
    header = (f"needs {_format.plural(calls, 'tool call')} and a reply ({calls + 1} model "
              f"calls); a run allows {turn_cap} model calls")
    prompt = bundle.prompt if isinstance(bundle.prompt, str) else json.dumps(
        list(bundle.prompt), indent=2, ensure_ascii=False)
    needed = {call_name for call_name, _ in bundle.reference_calls}
    tools = []
    for tool in bundle.tools:
        function = tool.get("function", tool) if isinstance(tool, dict) else {}
        tool_name = str(function.get("name", ""))
        params = ", ".join((function.get("parameters") or {}).get("properties", {}).keys())
        tools.append((tool_name, params, tool_name in needed))
    steps = []
    for (call_name, arguments), observation in zip(
        bundle.reference_calls, bundle.reference_observations, strict=False
    ):
        shown_args = ", ".join(f"{key}={json.dumps(value, ensure_ascii=False)}"
                               for key, value in dict(arguments).items())
        steps.append((call_name, shown_args, observation))
    answers = [(name_, label, sentence) for name_, label, sentence, _ in wrong_answers(bundle)]
    return Result(
        schema=SCHEMA, verdict="ok", sentence=f"{name}: {header}",
        rows=[Row("task id", bundle.task_id)],
        document=[
            Part("what the model is shown", "quote", f"{bundle.system_prompt}\n\n{prompt}"),
            Part("the tools it may call", "tools", tools),
            Part("the reference solution", "steps", steps),
            Part("the wrong answers it ships with, and their verdicts", "answers", answers),
        ],
        data={"task": name, "task_id": bundle.task_id, "seed": bundle.seed,
              "arm": bundle.arm_id, "reference_calls": calls},
    )
