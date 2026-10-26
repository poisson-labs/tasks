"""`export`: write the configs another runner reads.

One target: `--to verifiers`, one eval config per arm, each the one `run` uses for that arm,
written as JSON (TOML cannot carry a plain arm's missing control arm), and the command that
runs it, with verifiers' `eval` by absolute path.  Beside them, `produced_by.json`: what produces
the plan's tasks (`provenance.produced_by`), with no time in it, so two exports of one plan write
the same bytes.  The configs carry nothing of it, since they are what `run` sends.  It reads no
key and opens no socket: a config that would send a key over plain http to another machine is
refused before anything is written.
"""

from __future__ import annotations

import json
import sysconfig
from pathlib import Path

from poisson_tasks import config, providers
from poisson_tasks.cli import _format
from poisson_tasks.cli._common import (
    Context,
    arm_folder,
    load_settings,
    need_tokenizer,
    plan_words,
    refuse_overwrite,
    resolve,
    settings_root,
    shown,
)
from poisson_tasks.cli._result import Part, Refusal, Result, Row, Usage

SCHEMA = "poisson-tasks.export/1"
LEAVES_OUT = (
    "run that way, eval leaves out what run adds (the plan, the instrument tally, the "
    "out-of-credit stop, the failure-streak stop and the watchdog), and it exits 0 when every "
    "episode errored"
)
SPENDS = ("Each of these runs calls the model and spends money with no cap; {run} is the way "
          "with a cap.")
"""The warning printed right above the commands (pass two's N6), in plain English."""


def _eval_path() -> Path:
    scripts = Path(sysconfig.get_path("scripts"))
    program = scripts / "eval"
    if program.is_file():
        return program
    raise Refusal(
        f"verifiers' eval is not beside this Python ({program} is not there); install verifiers "
        "in this environment and run again"
    )


RUNNERS = ("verifiers",)


def export(ctx: Context) -> Result:
    args = ctx.args
    if args.to not in RUNNERS:
        raise Usage(f'"{args.to}" is not a runner export writes for; it is one of '
                    f"{_format.words(RUNNERS, 'or')}")
    need_tokenizer(ctx)
    settings = load_settings(ctx)
    try:
        providers.refuse_plain_http_key(settings.model)
    except config.ConfigError as refused:
        raise Refusal(str(refused)) from None
    plan = resolve(settings, settings_root(ctx))
    folder = Path(args.out) if args.out is not None else Path(ctx.config_path).parent / "export"
    from poisson_tasks import provenance, runs

    paths = [folder / f"eval-{arm_folder(spec)}.json" for spec in plan.arms]
    record_path = folder / "produced_by.json"
    refuse_overwrite([*paths, record_path], args.force, ctx, "export", "--to", "verifiers")
    program = _eval_path()
    try:
        record = provenance.produced_by(plan)
    except ValueError as refused:
        raise Refusal(str(refused)) from None
    folder.mkdir(parents=True, exist_ok=True)
    commands = []
    for spec, path in zip(plan.arms, paths, strict=True):
        mapping = runs.verifiers_config(plan, spec)
        mapping["output_dir"] = str(folder)
        path.write_text(json.dumps(mapping, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
        commands.append(f"{program} @ {shown(path)}")
    record_path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n",
                           encoding="utf-8")
    return Result(
        schema=SCHEMA, verdict="ok",
        sentence=f"wrote {_format.plural(len(paths), 'verifiers config')}, one per arm: "
                 f"{plan_words(plan)}",
        rows=[Row("note", LEAVES_OUT)],
        document=[Part(SPENDS.format(run=ctx.command('run')), "lines", commands)],
        data={"files": [str(path) for path in paths], "commands": commands,
              "produced_by": record},
    )
