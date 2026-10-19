"""What the verbs share: the context of one call, the settings file, the tokenizer check, the
words for a plan, the next command, and small helpers over paths."""

from __future__ import annotations

import dataclasses
import os
import platform
import shlex
import sys
import urllib.parse
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from poisson_tasks import arms, config, providers
from poisson_tasks.cli import _format
from poisson_tasks.cli._result import Refusal

DEFAULT_SETTINGS = "tasks.toml"
HARNESS_LINE = (
    "the first episode runs uv's installer (astral.sh inside a virtualenv) and fetches four "
    "packages and their dependencies from PyPI"
)
WINDOWS_LINE = (
    "runs need macOS or Linux (the harness uses a POSIX shell); generate, card, verify and "
    "export work here"
)


@dataclasses.dataclass
class Context:
    """One call of the command: the prog, the parsed arguments, the renderer and the settings
    file's path, as given or by default."""

    prog: str
    args: Any
    ui: Any
    config_path: str
    config_given: bool
    json: bool
    shown: list[Any] = dataclasses.field(default_factory=list)

    def show(self, result: Any) -> None:
        """Print an intermediate result (`run`'s plan): as text now, or remembered for the
        JSON document under `--json`."""
        if result.silent:
            return
        if self.json:
            self.shown[:] = [result]
        else:
            self.ui.show(result)

    def command(self, *words: str, settings: bool = True) -> str:
        """`<prog> <words>`, carrying `--config` as the user gave it when the command reads the
        settings file (rule L13; a next command finds the user's file)."""
        argv = [*shlex.split(self.prog), *words]
        if settings and self.config_given:
            argv += ["--config", self.config_path]
        return " ".join(shlex.quote(word) for word in argv)


# ---------------------------------------------------------------------------
# the platform and the tokenizer
# ---------------------------------------------------------------------------


def is_windows() -> bool:
    return sys.platform == "win32" or platform.system() == "Windows"


def tokenizer_present() -> bool:
    """Whether the tokenizer file is in this environment, read with no module that loads it."""
    return providers.environment_report().tokenizer == "present"


def need_tokenizer(ctx: Context) -> None:
    """Refuse, before anything that loads the tokenizer is imported, when the file is absent."""
    report = providers.environment_report()
    if report.tokenizer == "present":
        return
    what = "is not in this environment" if report.tokenizer == "missing" else (
        "in this environment is not the file the tokenizer needs")
    raise Refusal(
        f"the tokenizer file {what} ({report.tokenizer_path})",
        [ctx.command("doctor", "--fix", settings=False)],
    )


# ---------------------------------------------------------------------------
# the settings file and the plan
# ---------------------------------------------------------------------------


def settings_exist(ctx: Context) -> bool:
    return Path(ctx.config_path).is_file()


def load_settings(ctx: Context) -> Any:
    """The settings file's config, or a refusal in one line: the reader's own for a file it
    refuses, and one naming the file and `init` when there is none."""
    path = Path(ctx.config_path)
    if not path.is_file():
        raise Refusal(
            f"there is no settings file at {ctx.config_path}; "
            f"{ctx.command('init', settings=False)} writes one",
            [ctx.command("init")],
        )
    try:
        return config.load_config(path)
    except config.ConfigError as refused:
        raise Refusal(str(refused)) from None


def resolve(settings: Any, root: str | os.PathLike[str] | None = None) -> Any:
    """The settings file's plan; `root` is the settings file's folder, where a tool file named
    by `[own]` is read from."""
    try:
        return config.resolve_plan(settings, root=root)
    except config.ConfigError as refused:
        raise Refusal(str(refused)) from None


def settings_root(ctx: Context) -> Path:
    """The settings file's folder: where `[own] file`, the runs and the tasks are relative to."""
    return Path(ctx.config_path).parent


# ---------------------------------------------------------------------------
# words for a plan
# ---------------------------------------------------------------------------


def _knob_words(knob: str, levels: Sequence[int], controls: bool) -> str:
    note = " (experimental)" if knob == "distractor" else ""
    text = f"{knob}{note} at {_format.words(levels)}"
    if controls:
        text += ", with the control arms" if len(levels) > 2 else ", with the control arm"
    return text


def _arms_words(specs: Sequence[Any]) -> str:
    """The arms of a plan, by knob: `depth at 1, 3 and 8`, with the control arms named."""
    parts = []
    seen: list[str] = []
    for spec in specs:
        if spec.knob not in seen:
            seen.append(spec.knob)
    for knob in seen:
        own = [spec for spec in specs if spec.knob == knob]
        levels = [spec.level for spec in own if spec.control is None]
        parts.append(_knob_words(knob, levels, any(spec.control is not None for spec in own)))
    return _format.words(parts)


def plan_words(plan: Any) -> str:
    """`depth at 1, 3 and 8, 10 tasks each` for a resolved plan, with the attempts when more
    than one and the strictness when leaky."""
    text = _arms_words(plan.arms)
    text += f", {_format.plural(len(plan.seeds), 'task')} each"
    if plan.attempts != 1:
        text += f", {_format.plural(plan.attempts, 'attempt')} each"
    if any(spec.strictness == "leaky" for spec in plan.arms):
        text += ", leaky"
    return text


def own_words(settings: Any) -> str:
    """`your tools (acme-support)`, or `your tools (tools.json)` when the set is unnamed, from
    the settings file alone."""
    own = settings.own
    name = own.name if own.name is not None else own.file
    return f"your tools ({name})"


def config_words(settings: Any) -> str:
    """The same words from the settings file alone, with no tokenizer: the recipe's arms, or the
    custom knob and levels, the tasks and the attempts; on the user's own tools the recipe or the
    knob by name, since which arms the set reaches needs the tool file."""
    measure = settings.measure
    if settings.own is not None:
        if measure.preset == "custom":
            levels = list(measure.levels or ())
            text = f"{measure.knob or 'depth'} at " + (
                _format.words(levels) if levels else "every level your tools reach")
        else:
            text = f"the {measure.preset} recipe"
        text += f" on {own_words(settings)}"
    elif measure.preset == "custom":
        knob = measure.knob or "depth"
        levels = list(measure.levels or ())
        text = _knob_words(knob, levels, bool(measure.controls))
    else:
        recipe = arms.RECIPES[measure.preset]
        specs = [arms.arm_from_id(arm_id) for arm_id in recipe.arms]
        text = _arms_words(specs)
        if measure.preset == "card":
            text = "the published cards' design: " + text
    tasks = settings.tasks
    if tasks.seeds is not None:
        text += f", {_format.plural(len(tasks.seeds), 'chosen task')} each"
    elif tasks.per_level is not None:
        text += f", {_format.plural(tasks.per_level, 'task')} each"
    if tasks.attempts != 1:
        text += f", {_format.plural(tasks.attempts, 'attempt')} each"
    if measure.preset == "custom" and measure.strictness == "leaky":
        text += ", leaky"
    return text


def own_summary(reading: Any, toolset: Any) -> list[str]:
    """The lines of `own.summary` for a tool file read as `reading`, counted on `toolset`: the
    same tools with the effects you declared applied (`[own] read` and `write`, `--own-read`,
    `--own-write`, and the answers to `init`'s question about each tool), not the file's alone.
    `init` and `doctor` print these, and the set a run's plan makes counts the same."""
    from poisson_tasks import own

    return str(own.summary(dataclasses.replace(reading, toolset=toolset))).splitlines()


def own_plan_words(plan: Any) -> str:
    """`acme-support, 5 tools from tools.json; ...` for a resolved plan on the user's own tools."""
    own = plan.own
    return (f"{own['name']}, {_format.plural(int(own['tools']), 'tool')} from "
            f"{shown(str(own['file']))}; the responses are simulated from your schemas, and your "
            "backend is never called")


def model_words(model: Any) -> str:
    return f"{model.name} at {host_of(model.base_url)}"


def host_of(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    return parts.netloc or url


# ---------------------------------------------------------------------------
# files
# ---------------------------------------------------------------------------


def arm_folder(spec: Any) -> str:
    """An arm's folder-safe name (`depth:d1` to `depth-d1`), as a run folder names an arm's; the
    arm is a spec or its id."""
    from poisson_tasks.knobs import arm_id

    name = spec if isinstance(spec, str) else arm_id(spec)
    return str(name).replace("/", "-").replace(":", "-").replace("@", "-")


def shown(path: str | os.PathLike[str]) -> str:
    """A path as the user reads it: relative to the current folder when it is under it."""
    target = Path(path)
    try:
        return str(target.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(target)


def refuse_overwrite(paths: Sequence[Path], force: bool, ctx: Context, *argv: str) -> None:
    """Rule L12: a verb that writes files refuses to overwrite one without `--force`."""
    if force:
        return
    for path in paths:
        if path.exists():
            raise Refusal(
                f"{shown(path)} is already there; pass --force to write it again",
                [ctx.command(*argv, "--force")],
            )
