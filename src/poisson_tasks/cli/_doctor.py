"""`doctor`: is this environment ready (spec §4.7 and §5.4).

One line per check, each with its own status word: Python, the package and where it was
imported from, the tokenizer file, the settings file, the key, the harness and the platform.
Exit 0 when ready, 4 when not, each failing line ending with what to run.  `--fix` fetches the
tokenizer file when it is missing, the one thing `doctor` changes; `--offline` opens no socket;
`--show-command` prints the `init --yes` command that writes the settings file.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import sys
from pathlib import Path
from typing import Any

from poisson_tasks import config, providers
from poisson_tasks.cli._common import (
    HARNESS_LINE,
    WINDOWS_LINE,
    Context,
    config_words,
    host_of,
    load_settings,
    settings_exist,
)
from poisson_tasks.cli._result import Command, Refusal, Result, Row

SCHEMA = "poisson-tasks.doctor/1"


def _version() -> str:
    try:
        return importlib.metadata.version("poisson-tasks")
    except importlib.metadata.PackageNotFoundError:
        return "unknown version"


def _digest(path: str) -> str:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]
    except OSError:
        return "unreadable"


def doctor(ctx: Context) -> Result:
    args = ctx.args
    ui = ctx.ui
    report = providers.environment_report()
    settings: Any = None
    settings_problem: str | None = None
    if settings_exist(ctx) or ctx.config_given:
        try:
            settings = load_settings(ctx)
        except Refusal as refused:
            if not settings_exist(ctx):
                raise
            settings_problem = refused.message
    if args.show_command:
        if settings is None:
            raise Refusal(settings_problem or
                          f"there is no settings file at {ctx.config_path}; "
                          f"{ctx.command('init', settings=False)} writes one")
        try:
            command = config.equivalent_init_command(settings, prog=ctx.prog)
        except config.ConfigError as refused:
            raise Refusal(str(refused)) from None
        return Result(
            schema=SCHEMA, verdict="ok",
            sentence=f"{ctx.config_path} is written by this command, with no questions:",
            rows=[Command("", command)], data={"command": command},
        )

    rows: list[Row] = []
    nexts: list[str] = []

    rows.append(Row("python", f"{report.python} ({report.python_version})", "ok"))
    rows.append(Row("package", f"poisson-tasks {_version()} at {report.package}", "ok"))
    if report.package_outside_environment:
        ui.note(f"the package at {report.package} is outside this environment ({sys.prefix}): "
                "an editable install, or another project's copy on the path")

    # the tokenizer, fetched under --fix
    tokenizer = report.tokenizer
    tokenizer_path = report.tokenizer_path
    fetched = False
    fix_problem: str | None = None
    if tokenizer != "present" and args.fix:
        if not args.yes and not sys.stdin.isatty():
            raise Refusal("doctor --fix asks before fetching the tokenizer file, and stdin is "
                          "not a terminal; pass --yes")
        wanted = args.yes or ui.confirm(
            "Tasks needs a 3.6 MB tokenizer file, fetched once into this environment from "
            "openaipublic.blob.core.windows.net. Fetch it now?", True)
        if wanted:
            try:
                with ui.status("fetching the tokenizer file"):
                    tokenizer_path = str(providers.fetch_tokenizer())
            except PermissionError as reason:
                fix_problem = (f"cannot write {reason.filename or tokenizer_path} (permission "
                               "denied); give this user write access to that folder, or install "
                               "the package where it can write")
            except (OSError, RuntimeError) as reason:
                fix_problem = f"the fetch failed: {reason}"
            else:
                tokenizer, fetched = "present", True
    if tokenizer == "present":
        text = (f"{'fetched' if fetched else 'present'} (o200k_base, sha256 "
                f"{_digest(tokenizer_path)}) at {tokenizer_path}")
        rows.append(Row("tokenizer", text, "ok"))
    else:
        fix = ctx.command("doctor", "--fix", settings=False)
        if fix_problem is not None:
            text = f"{'missing' if tokenizer == 'missing' else 'wrong digest'}: {fix_problem}"
        elif tokenizer == "missing":
            text = f"missing: the file is not at {tokenizer_path}; fetch it with {fix}"
        else:
            text = (f"the file at {tokenizer_path} is not the one the tokenizer needs; fetch it "
                    f"again with {fix}")
        rows.append(Row("tokenizer", text, "bad"))
        if fix_problem is None:
            nexts.append(fix)

    # the settings file
    if settings is not None:
        rows.append(Row("config", f"{ctx.config_path}: {config_words(settings)}, against "
                                  f"{settings.model.name}", "ok"))
    elif settings_problem is not None:
        rows.append(Row("config", settings_problem, "bad"))
    else:
        rows.append(Row("config", f"no settings file at {ctx.config_path} yet; "
                                  f"{ctx.command('init', settings=False)} writes one", "ok"))
        nexts.append(ctx.command("init"))

    # the key
    key_status = "ok"
    key_data: dict[str, Any] = {}
    if settings is not None:
        model = settings.model
        if not model.api_key_env:
            key_text = f"none needed for {host_of(model.base_url)}"
        elif not providers.key_is_set(model.api_key_env):
            found = providers.check_key(model)
            key_text, key_status = found.detail, "bad"
            key_data = {"status": found.status}
        elif args.offline:
            key_text = f"{model.api_key_env} is set (not checked: --offline)"
            key_data = {"status": "not checked"}
        else:
            try:
                found = providers.check_key(model)
            except config.ConfigError as refused:
                key_text, key_status = str(refused), "bad"
            else:
                key_text = found.detail
                key_data = {"status": found.status}
                if found.status in (providers.REFUSED, providers.MODEL_MISSING,
                                    providers.UNREACHABLE):
                    key_status = "bad"
        rows.append(Row("key", key_text, key_status))

    # the harness and the platform
    harness = HARNESS_LINE.replace("the first episode", "each run's first episode", 1)
    if report.uv:
        harness += "; uv is already at ~/.local/bin/uv"
    rows.append(Row("harness", harness, "ok"))
    if report.platform_supported:
        name = {"darwin": "macOS", "linux": "Linux"}.get(report.platform, report.platform)
        rows.append(Row("platform", f"{name} ({report.platform})", "ok"))
    else:
        rows.append(Row("platform", f"{report.platform}: {WINDOWS_LINE}", "bad"))

    failing = [row for row in rows if row.status == "bad"]
    ready = not failing
    target = ctx.config_path if settings is not None else "tasks"
    if ready:
        sentence = f"this environment is ready to run {target}"
        if settings is None:
            sentence += f"; there is no settings file at {ctx.config_path} yet"
    else:
        first = failing[0]
        sentence = f"this environment cannot run {target} yet: the {first.label} line says why"
    return Result(
        schema=SCHEMA, verdict="ok" if ready else "not ready", tone="good" if ready else "bad",
        sentence=sentence, rows=list(rows), next=nexts, exit=0 if ready else 4,
        data={
            "ready": ready,
            "checks": {row.label: {"status": row.status, "text": row.value} for row in rows},
            "key": key_data,
        },
    )
