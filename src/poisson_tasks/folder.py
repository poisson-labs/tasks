"""What a folder holds, read from disk alone: the facts the guided session's home screen shows
(spec §16.2).

`read_folder(config_path)` reads the settings file, the environment, whether the key's variable is
set, the tool file's counts on your own tools, every run folder under the settings' `runs` folder
and the newest card's levels.  It opens no socket and does not load the tokenizer.  `Folder` holds
facts only: no sentence and no command.
"""

from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path
from typing import Any

__all__ = ["Folder", "RunFacts", "ToolsFacts", "read_folder"]


@dataclasses.dataclass(frozen=True)
class RunFacts:
    """One run folder: its `name` and `path`; `kept` of `total` episodes, counted as a resume
    counts them; `spent_usd` from its ledger (`None` without a price); `card`, `"built"`,
    `"refused"` or `None`; `locked`, whether a process holds its `run.lock` now, and `holder`,
    the pid and start time that process wrote in it, when it did; `this_plan`, whether it holds
    the settings file's plan; and `silent_arms`, the arms of a refused card whose every attempt
    made no tool call (the card's records say so)."""

    name: str
    path: Path
    kept: int
    total: int
    spent_usd: float | None
    card: str | None
    locked: bool
    this_plan: bool
    holder: tuple[int, str] | None = None
    silent_arms: tuple[str, ...] = ()


@dataclasses.dataclass(frozen=True)
class ToolsFacts:
    """Your own tools, as the tool file reads with the effects you declared: the set's `name`,
    its `tools`, how many were `refused`, and how many `flows` are declared."""

    name: str
    tools: int
    refused: int
    flows: int


@dataclasses.dataclass(frozen=True)
class Folder:
    """The facts of one folder.  `settings` is the settings file's config, or `None` when there
    is none or the reader refuses it (`problem` then holds the reader's words); `environment` is
    `providers.environment_report()`; `runs` is newest first; `levels` is the newest card's
    (arm id, strict pass@1) per level, empty when no card is built, and `leaky_levels` the same
    card's (arm id, leaky pass@1), the rate the built-in card reads depth on."""

    config_path: Path
    settings: Any | None
    problem: str | None
    environment: Any
    key_variable: str | None
    key_set: bool
    tools: ToolsFacts | None
    runs: tuple[RunFacts, ...]
    levels: tuple[tuple[str, float], ...]
    leaky_levels: tuple[tuple[str, float], ...] = ()


def _lock_held(path: Path) -> bool:
    import fcntl

    if not path.is_file():
        return False
    try:
        handle = open(path, "rb")
    except OSError:
        return False
    with handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        except OSError:
            return False
        fcntl.flock(handle, fcntl.LOCK_UN)
    return False


def _holder(path: Path) -> tuple[int, str] | None:
    """The pid and start time a run wrote in its lock file, when the file holds them."""
    try:
        held = json.loads(path.read_text(encoding="utf-8"))
        return int(held["pid"]), str(held["since"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _silent_arms(records: Path) -> tuple[str, ...]:
    """The arms whose every record in a refused card's `episodes.jsonl` made no tool call."""
    calls: dict[str, list[int]] = {}
    for line in _whole_lines(records):
        try:
            row = json.loads(line)
            calls.setdefault(str(row["arm_id"]), []).append(int(row["sampled_calls"]))
        except (ValueError, KeyError, TypeError):
            continue
    return tuple(arm for arm, made in calls.items() if made and not any(made))


def _whole_lines(path: Path) -> list[bytes]:
    try:
        raw = path.read_bytes()
    except OSError:
        return []
    return [line for line in raw.splitlines(keepends=True) if line.endswith(b"\n")]


def _kept(folder: Path, arms: list[Any], per_arm: int) -> int:
    from poisson_tasks.knobs import ArmSpec, arm_id

    kept = 0
    for arm in arms:
        name = str(arm_id(ArmSpec(**arm))).replace("/", "-").replace(":", "-").replace("@", "-")
        count = 0
        for line in _whole_lines(folder / name / "traces.jsonl"):
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and row.get("ok"):
                count += 1
        kept += min(count, per_arm)
    return kept


def _spent(folder: Path, priced: bool) -> float | None:
    if not priced:
        return None
    total = 0.0
    for line in _whole_lines(folder / "spend.jsonl"):
        try:
            row = json.loads(line)
        except ValueError:
            break
        if isinstance(row, dict):
            total += float(row.get("dollars") or 0.0)
    return total


def _tools(settings: Any, root: Path) -> ToolsFacts | None:
    from poisson_tasks import config, own

    table = settings.own
    path = Path(config.own_file_path(table, root))
    name = table.name if table.name is not None else Path(table.file).stem
    try:
        reading = own.read_tools(path.read_bytes(), format=table.format, name=name)
        toolset = own.apply_effects(reading.toolset, read=table.read, write=table.write)
    except (OSError, own.OwnToolsError):
        return ToolsFacts(name=name, tools=0, refused=0, flows=len(table.flows))
    return ToolsFacts(name=toolset.name, tools=len(toolset.tools), refused=len(reading.refused),
                      flows=len(table.flows))


def _identity(settings: Any) -> dict[str, Any]:
    """What tells the settings file's plan from another's, read from the settings alone: the
    preset, the model and its endpoint, the tasks and attempts, the custom knob's levels, and
    on your own tools the tool file.  Resolving the plan would import the module that loads the
    tokenizer, which this reader never does."""
    measure = settings.measure
    tasks = settings.tasks
    held: dict[str, Any] = {
        "preset": measure.preset, "name": settings.model.name,
        "base_url": settings.model.base_url, "attempts": int(tasks.attempts),
        "seeds": list(tasks.seeds) if tasks.seeds is not None else None,
        "per_level": tasks.per_level,
    }
    if measure.preset == "custom" and measure.levels is not None:
        held["levels"] = {(measure.knob or "depth", int(level)) for level in measure.levels}
    if settings.own is not None:
        own = settings.own
        held["own_file"] = Path(own.file).name
        held["own_name"] = own.name if own.name is not None else Path(own.file).stem
    return held


def _same_plan(wanted: dict[str, Any], plan: dict[str, Any]) -> bool:
    """Whether a run folder's `plan.json` holds the settings file's plan, by `_identity`."""
    model = plan.get("model") or {}
    if (plan.get("preset"), model.get("name"), model.get("base_url"), int(plan["attempts"])) != (
            wanted["preset"], wanted["name"], wanted["base_url"], wanted["attempts"]):
        return False
    seeds = list(plan["seeds"])
    if wanted["seeds"] is not None:
        if seeds != wanted["seeds"]:
            return False
    elif wanted["per_level"] is not None and len(seeds) != wanted["per_level"]:
        return False
    if "levels" in wanted:
        plain = {(arm.get("knob"), int(arm.get("level", -1))) for arm in plan["arms"]
                 if arm.get("control") is None}
        if plain != wanted["levels"]:
            return False
    if "own_file" in wanted:
        own = plan.get("own") or {}
        if Path(str(own.get("file", ""))).name != wanted["own_file"] or (
                own.get("name") != wanted["own_name"]):
            return False
    return True


def read_folder(config_path: str | os.PathLike[str]) -> Folder:
    """The facts of the folder whose settings file is `config_path`, from disk alone."""
    from poisson_tasks import config, providers

    path = Path(config_path)
    root = path.parent
    settings: Any = None
    problem: str | None = None
    if path.is_file():
        try:
            settings = config.load_config(path)
        except config.ConfigError as refused:
            problem = str(refused)
    environment = providers.environment_report()
    variable: str | None = settings.model.api_key_env if settings is not None else None
    key_set = bool(variable) and providers.key_is_set(variable or "")
    tools = _tools(settings, root) if settings is not None and settings.own is not None else None
    wanted = _identity(settings) if settings is not None else None
    found: list[tuple[tuple[int, str], RunFacts]] = []
    runs_dir = root / (settings.output.runs if settings is not None else "runs")
    if settings is not None and runs_dir.is_dir():
        for child in sorted(runs_dir.iterdir()):
            plan_file = child / "plan.json"
            if not child.is_dir() or not plan_file.is_file():
                continue
            try:
                held = json.loads(plan_file.read_text(encoding="utf-8"))
                plan = held["plan"]
                per_arm = len(plan["seeds"]) * int(plan["attempts"])
                total = len(plan["arms"]) * per_arm
                kept = _kept(child, list(plan["arms"]), per_arm)
                priced = plan["model"].get("price") is not None
            except (OSError, ValueError, KeyError, TypeError):
                continue
            card_dir = child / "card"
            card = ("built" if (card_dir / "artifact.json").is_file() else
                    "refused" if (card_dir / "episodes.jsonl").is_file() else None)
            facts = RunFacts(
                name=child.name, path=child, kept=kept, total=total,
                spent_usd=_spent(child, priced), card=card,
                locked=_lock_held(child / "run.lock"),
                this_plan=wanted is not None and _same_plan(wanted, plan),
                holder=_holder(child / "run.lock"),
                silent_arms=_silent_arms(card_dir / "episodes.jsonl") if card == "refused" else (),
            )
            found.append(((plan_file.stat().st_mtime_ns, child.name), facts))
    ordered = tuple(facts for _, facts in sorted(found, key=lambda item: item[0], reverse=True))
    levels: tuple[tuple[str, float], ...] = ()
    leaky: tuple[tuple[str, float], ...] = ()
    for facts in ordered:
        if facts.card == "built":
            try:
                cells = json.loads((facts.path / "card" / "artifact.json").read_text(
                    encoding="utf-8"))["cells"]
                levels = tuple((str(cell["arm_id"]), float(cell["pass_at_1"])) for cell in cells)
                leaky = tuple((str(cell["arm_id"]), float(cell["leaky_at_1"])) for cell in cells
                              if cell.get("leaky_at_1") is not None)
            except (OSError, ValueError, KeyError, TypeError):
                levels = leaky = ()
            break
    return Folder(config_path=path, settings=settings, problem=problem, environment=environment,
                  key_variable=variable, key_set=key_set, tools=tools, runs=ordered,
                  levels=levels, leaky_levels=leaky)
