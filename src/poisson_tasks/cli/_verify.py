"""`verify`: judge an answer with the task's own verifier, with no model (spec §4.5).

`--self-check` checks the task's own answers: the reference solution passes under both
strictnesses and each wrong answer the task ships with earns the outcome it is named for.
`--transcript FILE` judges an agent's attempt, in one of three forms.  A task is named by its
arm and its place in the plan (the settings file's seeds, or the published sixty), or by a seed
the user chose, or counted in a file `generate` wrote.  The verdict word is the outcome label,
its sentence the library's; exit 0 when the verdict is `passed`, 4 otherwise.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from poisson_tasks.cli import _format
from poisson_tasks.cli._common import (
    Context,
    load_settings,
    need_tokenizer,
    resolve,
    settings_exist,
)
from poisson_tasks.cli._generate import reference_verdict, task_name, wrong_answers
from poisson_tasks.cli._result import Refusal, Result, Row, Usage

SCHEMA = "poisson-tasks.verify/1"


def _bundle(ctx: Context) -> tuple[Any, str]:
    """The task to judge, and its name."""
    args = ctx.args
    from poisson_tasks import arms, calibration, tasks

    if args.tasks is not None:
        if args.arm is not None or args.seed is not None:
            raise Usage("--tasks counts tasks in a file; --arm and --seed name one without a "
                        "file; give one or the other")
        path = Path(args.tasks)
        if not path.is_file():
            raise Refusal(f"there is no file at {args.tasks}")
        from poisson_tasks.export import ExportTaskData, bundle_from_data

        rows = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        try:
            bundles = [bundle_from_data(ExportTaskData.model_validate(json.loads(row)))
                       for row in rows]
        except ValueError as refused:
            first = str(refused).splitlines()[0]
            raise Refusal(f"{args.tasks} is not a file generate wrote ({first})") from None
        if not bundles:
            raise Refusal(f"{args.tasks} holds no task")
        place = 1 if args.task is None else args.task
        if place < 1 or place > len(bundles):
            raise Refusal(f"--task {place} is out of range: {args.tasks} holds "
                          f"{_format.plural(len(bundles), 'task')}, counted from 1")
        bundle = bundles[place - 1]
        return bundle, task_name(bundle.arm_id, place, bundle.seed)
    if args.arm is None:
        raise Usage("name the task: --arm ID with --task N or --seed S, or --tasks FILE")
    strictness = "strict"
    version = arms.DEFAULT_GENERATOR_VERSION
    seeds: tuple[int, ...] | None = None
    if settings_exist(ctx) or ctx.config_given:
        settings = load_settings(ctx)
        plan = resolve(settings)
        seeds = plan.seeds
        strictness = settings.measure.strictness or "strict"
        if settings.tasks.generator_version is not None:
            version = settings.tasks.generator_version
    try:
        spec = arms.arm_from_id(args.arm, strictness=strictness, generator_version=version)
    except ValueError as refused:
        raise Usage(str(refused)) from None
    from poisson_tasks import knobs

    arm_id = knobs.arm_id(spec)
    if args.seed is not None:
        if args.task is not None:
            raise Usage("--task counts in the plan and --seed names a seed you chose; give one")
        return tasks.generate(spec, args.seed), task_name(arm_id, None, args.seed)
    if seeds is None:
        seeds = calibration.seed_list()
    place = 1 if args.task is None else args.task
    if place < 1 or place > len(seeds):
        raise Refusal(f"--task {place} is out of range: the plan has "
                      f"{_format.plural(len(seeds), 'task')} per level, counted from 1")
    seed = seeds[place - 1]
    return tasks.generate(spec, seed), task_name(arm_id, place, seed)


def verify(ctx: Context) -> Result:
    args = ctx.args
    if not args.self_check and args.transcript is None:
        raise Usage("say what to judge: --self-check, or --transcript FILE")
    if args.self_check and args.transcript is not None:
        raise Usage("--self-check judges the task's own answers and --transcript an attempt; "
                    "give one")
    need_tokenizer(ctx)
    bundle, name = _bundle(ctx)
    if args.self_check:
        return _self_check(ctx, bundle, name)
    return _transcript(ctx, bundle, name)


def _self_check(ctx: Context, bundle: Any, name: str) -> Result:
    from poisson_tasks import outcomes

    reference = reference_verdict(bundle)
    holds = reference.strict_label == "passed" and reference.leaky_pass
    answers = wrong_answers(bundle)
    calls = _format.plural(len(bundle.reference_calls), "tool call")
    rows: list[Any] = [Row("reference solution", (
        f"passed under both strictnesses ({calls})"
        if holds else f"{reference.strict_label} under strict"
        + (", passed" if reference.leaky_pass else ", not passed") + " under leaky"))]
    for answer_name, label, sentence, as_named in answers:
        rows.append(Row(answer_name, f"{label}" + ("" if as_named else
                                                   f", not {answer_name.split('_clause')[0]}")
                        + f" · {sentence}"))
    every = holds and all(as_named for _, _, _, as_named in answers)
    sentence = (f"{name}: the reference solution passes and each of the "
                f"{_format.plural(len(answers), 'wrong answer')} earns its outcome"
                if every else
                f"{name}: the self-check does not hold: " + "; ".join(
                    ([] if holds else [f"the reference solution is {reference.strict_label}"])
                    + [f"{answer_name} was judged {label}" for answer_name, label, _, as_named
                       in answers if not as_named]))
    return Result(
        schema=SCHEMA, verdict="ok" if every else "failed", tone="good" if every else "bad",
        sentence=sentence, rows=rows, exit=0 if every else 4,
        data={"task": name, "task_id": bundle.task_id, "holds": every,
              "reference": reference.strict_label,
              "wrong_answers": {answer_name: label for answer_name, label, _, _ in answers},
              "meaning": {answer_name: outcomes.describe(label) for answer_name, label, _, _
                          in answers}},
    )


def _transcript(ctx: Context, bundle: Any, name: str) -> Result:
    args = ctx.args
    from poisson_tasks import outcomes, transcripts

    path = Path(args.transcript)
    if not path.is_file():
        raise Refusal(f"there is no transcript at {args.transcript}")
    try:
        transcript = transcripts.read_transcript(path.read_text(encoding="utf-8"))
    except ValueError as refused:
        raise Refusal(str(refused)) from None
    limit = True if args.hit_turn_limit else None
    verdict = transcripts.verdict_of(bundle, transcript, turn_limit_hit=limit)
    calls = sum(len(turn.calls) for turn in transcript.turns)
    detail = (f"strict  {verdict.strict_label} · leaky  "
              f"{'passed' if verdict.leaky_pass else 'not passed'} · tool calls {calls} · "
              f"records changed {len(verdict.mutations)}")
    passed = verdict.label == "passed"
    return Result(
        schema=SCHEMA, verdict=verdict.label, tone="good" if passed else "warn",
        sentence=f"{name}: {outcomes.describe(verdict)}",
        rows=[Row("verdict", detail), Row("transcript", f"{args.transcript}, read as "
                                                        f"{_form_words(transcript.form)}")],
        exit=0 if passed else 4,
        data={"task": name, "task_id": bundle.task_id, "label": verdict.label,
              "strict": verdict.strict_label, "leaky": verdict.leaky_pass,
              "tool_calls": calls, "records_changed": len(verdict.mutations),
              "form": transcript.form},
    )


def _form_words(form: str) -> str:
    return {"openai": "OpenAI chat messages", "traces": "a verifiers traces.jsonl row",
            "turns": "this tool's own turns"}.get(form, form)

