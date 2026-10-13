"""`card`: what each level was worth, from a run (spec §4.4 and §9).

From a run folder (by default the settings file's newest run) it builds the card through the
library and writes `card/`: the records, the artifact, the document and the instrument tallies,
so `card --check` recomputes it as it recomputes a published one.  The verdict comes first and
the card's own statement of what it means and what it does not claim is printed, never typed
here.  `--published` recomputes the cards shipped with the package, named by their model;
`--compare published` puts a run's card beside them, or says in one line why it cannot be;
`--page` writes the one page for every published card.
"""

from __future__ import annotations

import json
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from poisson_tasks import cards
from poisson_tasks.cli import _format
from poisson_tasks.cli._common import (
    Context,
    load_settings,
    need_tokenizer,
    refuse_overwrite,
    resolve,
    shown,
)
from poisson_tasks.cli._result import Bullets, Levels, Part, Refusal, Result, Row, Usage

SCHEMA = "poisson-tasks.card/1"


def _published_names() -> list[str]:
    return [card.name for card in cards.published()]


def card(ctx: Context) -> Result:
    args = ctx.args
    chosen = [name for name, given in (("--published", args.published is not None),
                                       ("--check", args.check is not None),
                                       ("--page", args.page)) if given]
    if len(chosen) > 1:
        raise Usage(f"{_format.words(chosen)} are different jobs; give one of them")
    if args.published is not None and args.published:
        names = _published_names()
        if args.published not in names:
            listed = _format.words(names, "or") if names else "none in this install"
            raise Usage(f'"{args.published}" is not a published card; the names are {listed}')
    need_tokenizer(ctx)
    if args.published is not None:
        return _published(ctx)
    if args.check is not None:
        return _check(ctx, Path(args.check))
    if args.page:
        return _page(ctx)
    return _run_card(ctx)


# ---------------------------------------------------------------------------
# a run's card
# ---------------------------------------------------------------------------


def _folder(ctx: Context) -> Path:
    args = ctx.args
    if args.run is not None:
        return Path(args.run)
    settings = load_settings(ctx)
    plan = resolve(settings)
    from poisson_tasks import runs

    runs_dir = Path(ctx.config_path).parent / settings.output.runs
    found = runs.find_run(plan, runs_dir)
    if found.status == "new":
        raise Refusal(
            f"no run of {ctx.config_path}'s plan in {shown(runs_dir)} yet; "
            f"{ctx.command('run', settings=False)} makes one",
            [ctx.command("run")],
        )
    return Path(found.path)


def _plan_words_of(folder: Path) -> tuple[str, str]:
    """The plan's words and its model's name, from the folder's own `plan.json`."""
    from poisson_tasks.cli._common import plan_words
    from poisson_tasks.config import ModelConfig, Plan
    from poisson_tasks.knobs import ArmSpec

    try:
        held = json.loads((folder / "plan.json").read_text(encoding="utf-8"))["plan"]
        model = held["model"]
        plan = Plan(
            preset=str(held.get("preset", "custom")),
            arms=tuple(ArmSpec(**arm) for arm in held["arms"]),
            seeds=tuple(int(seed) for seed in held["seeds"]), attempts=int(held["attempts"]),
            model=ModelConfig(provider=model["provider"], name=model["name"],
                              base_url=model["base_url"], api_key_env=model["api_key_env"]),
            decoding=dict(held.get("decoding", {})),
            max_model_calls=int(held.get("max_model_calls", 32)),
        )
    except (OSError, ValueError, KeyError, TypeError):
        return folder.name, ""
    return plan_words(plan), str(plan.model.name)


def _cells(artifact: Any, verdict: Any) -> list[dict[str, Any]]:
    prov = artifact.provenance
    held: list[dict[str, Any]] = []
    for cell in artifact.cells:
        low, high = cell["pass_at_1_interval"]
        held.append({
            "arm_id": str(cell["arm_id"]),
            "state": "incomplete" if cell["incomplete"] else "complete",
            "pass_at_1": float(cell["pass_at_1"]), "interval": (float(low), float(high)),
            "leaky_at_1": float(cell["leaky_at_1"]), "overshoot": float(cell["overshoot_share"]),
            "tasks": int(cell["S_observed"]), "tasks_planned": int(cell["S_declared"]),
            "attempts": int(cell["n_declared"]),
        })
    for arm in verdict.not_run:
        held.append({"arm_id": arm, "state": "not run", "pass_at_1": None, "interval": None,
                     "leaky_at_1": None, "overshoot": None, "tasks": 0,
                     "tasks_planned": int(prov.S), "attempts": int(prov.n)})
    order = {arm: index for index, arm in enumerate(prov.arms or ())}
    held.sort(key=lambda cell: order.get(cell["arm_id"], len(order)))
    return held


def _what_ran(document: str) -> list[str]:
    lines = document.splitlines()
    out: list[str] = []
    inside = False
    for line in lines:
        if line.startswith("## "):
            inside = line.startswith("## What ran")
            continue
        if inside and line.strip():
            out.append(line.lstrip("- ").strip())
    return out


def _gate_words(records: Any, tally: Any, arm: str, gate: str, prov: Any) -> str:
    from poisson_tasks import calibration

    rows = [record for record in records if record.arm_id == arm]
    if gate == "no_call":
        scored = calibration.scored(rows)
        silent = sum(1 for record in scored if record.sampled_calls == 0)
        return (f"{arm} is not published: {silent} of {len(scored)} scored attempts made no "
                f"tool call (more than {_format.rate(prov.no_call_threshold)}), so it would "
                "measure whether the model starts, not the level")
    rate = calibration.instrument_rate(rows, tally.get(arm) or None)
    return (f"{arm} is not published: {_format.rate(rate)} of its attempts failed for "
            f"instrument reasons (more than {_format.rate(prov.instrument_threshold)}), so the "
            "run, not the model, is what it would measure")


def _run_card(ctx: Context) -> Result:
    args = ctx.args
    folder = _folder(ctx)
    from poisson_tasks import calibration

    serving = None
    saved = folder / "serving.json"
    if saved.is_file():
        try:
            serving = json.loads(saved.read_text(encoding="utf-8"))
        except ValueError:
            serving = None
    try:
        made = calibration.card_from_run(folder, serving=serving)
    except ValueError as refused:
        raise Refusal(str(refused)) from None
    out = folder / "card"
    if args.compare is not None:
        if args.compare != "published":
            raise Usage(f'--compare takes "published", not "{args.compare}"')
        if made.artifact is None:
            raise Refusal(f"the card of {shown(folder)} is refused, so it cannot be compared")
        mapping = {folder.name: made.artifact}
        for published in cards.published():
            mapping[published.name] = cards.recompute(published).artifact
        try:
            side_by_side = calibration.render_side_by_side(mapping)
        except ValueError as refused:
            raise Refusal(str(refused)) from None
    else:
        side_by_side = None
    verdict = made.verdict
    plan_text, model_name = _plan_words_of(folder)
    model_name = model_name or verdict.model

    if verdict.word == "refused":
        out.mkdir(parents=True, exist_ok=True)
        records_path = calibration.write_records(made.records, out / "episodes.jsonl")
        prov_like = _provenance_like(folder)
        reasons = [_gate_words(made.records, made.tally, arm, gate, prov_like)
                   for arm, gate in verdict.refused]
        return Result(
            schema=SCHEMA, verdict="refused", tone="warn", sentence="; ".join(reasons),
            rows=[Row("wrote", shown(records_path))], exit=1,
            data={"folder": str(folder), "refused": [list(pair) for pair in verdict.refused],
                  "wrote": [str(records_path)]},
        )

    assert made.artifact is not None and made.document is not None and made.claims is not None
    paths = [out / "episodes.jsonl", out / "artifact.json", out / "card.md",
             out / cards.TALLIES_FILE]
    refuse_overwrite(paths, args.force, ctx, "card", *([str(folder)] if args.run else []))
    out.mkdir(parents=True, exist_ok=True)
    calibration.write_records(made.records, paths[0])
    calibration.write_artifact(made.artifact, paths[1])
    paths[2].write_text(made.document, encoding="utf-8")
    paths[3].write_text(json.dumps({arm: dict(counts) for arm, counts in made.tally.items()},
                                   indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if side_by_side is not None:
        (out / "compare.md").write_text(side_by_side, encoding="utf-8")

    cells = _cells(made.artifact, verdict)
    if verdict.partial:
        parts = []
        for cell in cells:
            if cell["state"] == "incomplete":
                parts.append(f"{cell['arm_id']} has {cell['tasks']} of {cell['tasks_planned']} "
                             "tasks, and it is marked incomplete")
            elif cell["state"] == "not run":
                parts.append(f"{cell['arm_id']} did not run")
        sentence = f"partial card for {model_name}: {plan_text}; " + "; ".join(parts)
    else:
        sentence = f"card for {model_name}: {plan_text}"
    rows: list[Any] = [Levels(cells)]
    note = _depth_note(made.document, cells)
    if note is not None:
        rows.append(Row("about depth", note))
    rows += [Row("what it means", made.claims.meaning),
             Bullets("what it does not claim", list(made.claims.not_claimed))]
    ran = _what_ran(made.document)
    if ran:
        rows.append(Bullets("what ran", ran))
    rows.append(Row("wrote", ", ".join(shown(path) for path in paths)))
    document = []
    if args.print:
        document.append(Part("", "document", made.document))
    if side_by_side is not None:
        document.append(Part("beside the published cards", "text", side_by_side))
    return Result(
        schema=SCHEMA, verdict="ok", sentence=sentence, rows=rows, document=document,
        next=[ctx.command("card", *([str(folder)] if args.run else []), "--compare",
                          "published")] if side_by_side is None else [],
        data={"folder": str(folder), "model": model_name, "partial": verdict.partial,
              "owed": verdict.owed, "levels": cells, "meaning": made.claims.meaning,
              "not_claimed": list(made.claims.not_claimed), "wrote": [str(p) for p in paths]},
    )


def _depth_note(document: str, cells: list[dict[str, Any]]) -> str | None:
    """The published cards' own note on depth, from the card's document, when the card's depth
    arms include the ladder's top level (the look's item 19): at the top level strict cannot
    fail by overshooting, so depth is read on leaky."""
    from poisson_tasks.knobs import levels

    top = max(levels("depth"))
    if not any(str(cell["arm_id"]) == f"depth:d{top}" for cell in cells):
        return None
    for line in document.splitlines():
        if "no stage lies above the goal" in line:
            return line.strip().lstrip("- ").strip()
    return None


def _provenance_like(folder: Path) -> Any:
    """The thresholds a refused card was judged by: the library's, as every card's are."""
    from poisson_tasks import calibration

    class _Thresholds:
        no_call_threshold = float(calibration.NO_CALL_THRESHOLD)
        instrument_threshold = 0.02

    return _Thresholds()


# ---------------------------------------------------------------------------
# --published, --check, --page
# ---------------------------------------------------------------------------


def _published(ctx: Context) -> Result:
    wanted = ctx.args.published
    found = [card for card in cards.published() if not wanted or card.name == wanted]
    if not found:
        raise Refusal("this install ships no published card")
    rows = []
    failed = []
    data = {}
    for card in found:
        try:
            made = cards.recompute(card)
        except ValueError as refused:
            rows.append(Row(card.name, f"cannot be rebuilt: {refused}"))
            failed.append(card.name)
            data[card.name] = {"identical": False, "records": 0}
            continue
        current = "current for this install" if made.current else (
            "not current: this install's generator differs from the card's")
        if made.identical:
            rows.append(Row(card.name, f"rebuilds byte for byte from "
                                       f"{_format.plural(made.records, 'record')} · {current}"))
        else:
            rows.append(Row(card.name, f"no longer rebuilds byte for byte from its "
                                       f"{_format.plural(made.records, 'record')} · {current}"))
            failed.append(card.name)
        data[card.name] = {"identical": made.identical, "current": made.current,
                           "records": made.records}
    names = _format.words([card.name for card in found])
    if failed:
        return Result(
            schema=SCHEMA, verdict="failed", tone="bad",
            sentence=f"the published card for {_format.words(failed)} no longer rebuilds from "
                     "its records", rows=rows, exit=4, data={"cards": data},
        )
    which = "every published card" if not wanted and len(found) > 1 else (
        f"the published card for {names}")
    return Result(schema=SCHEMA, verdict="ok",
                  sentence=f"{which} rebuilds from its records byte for byte",
                  rows=rows, data={"cards": data})


def _check(ctx: Context, path: Path) -> Result:
    if path.is_file() and path.suffix == ".zip":
        with tempfile.TemporaryDirectory(prefix="poisson-tasks-card-") as scratch:
            with zipfile.ZipFile(path) as bundle:
                bundle.extractall(scratch)
            folders = [Path(name).parent for name in Path(scratch).rglob("artifact.json")]
            if not folders:
                raise Refusal(f"{path} holds no artifact.json, so there is no card to check")
            return _check_folder(ctx, folders[0], shown(path))
    if not (path / "artifact.json").is_file():
        raise Refusal(f"{shown(path)} is not a card folder: it holds no artifact.json")
    return _check_folder(ctx, path, shown(path))


def _check_folder(ctx: Context, folder: Path, name: str) -> Result:
    try:
        made = cards.recompute(cards.PublishedCard(name=name, folder=folder))
    except (OSError, ValueError) as refused:
        raise Refusal(f"{name} cannot be recomputed: {refused}") from None
    if made.identical:
        return Result(
            schema=SCHEMA, verdict="ok",
            sentence=f"{name} rebuilds from its {_format.plural(made.records, 'record')} byte "
                     "for byte",
            data={"identical": True, "records": made.records, "current": made.current},
        )
    return Result(
        schema=SCHEMA, verdict="failed", tone="bad",
        sentence=f"{name} no longer rebuilds from its {_format.plural(made.records, 'record')}: "
                 "the artifact differs from what the records give", exit=4,
        data={"identical": False, "records": made.records, "current": made.current},
    )


def _page(ctx: Context) -> Result:
    args = ctx.args
    from poisson_tasks import calibration

    artifacts = [cards.recompute(card).artifact for card in cards.published()]
    included: list[str] = [card.name for card in cards.published()]
    if args.run is not None:
        folder = Path(args.run)
        try:
            made = calibration.card_from_run(folder)
        except ValueError as refused:
            raise Refusal(str(refused)) from None
        if made.artifact is not None and all(
            calibration.comparable(made.artifact, other).field is None for other in artifacts
        ) and not any(calibration.comparable(made.artifact, other).same_model
                      for other in artifacts):
            artifacts.append(made.artifact)
            included.append(folder.name)
        else:
            ctx.ui.note(f"the run's card at {shown(folder)} was not measured the published "
                        "cards' way, so the page holds the published cards alone")
    target = Path(args.out) if args.out is not None else Path("calibration.md")
    refuse_overwrite([target], args.force, ctx, "card", "--page")
    target.write_text(calibration.render_combined_document(artifacts), encoding="utf-8")
    return Result(
        schema=SCHEMA, verdict="ok",
        sentence=f"wrote the page for {_format.words(included)}",
        rows=[Row("wrote", shown(target))], data={"wrote": str(target), "cards": included},
    )
