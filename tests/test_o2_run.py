"""A plan on a user's own tools run end to end on a fake endpoint, frozen as tests.

The invariants are O2.6 (the export's tool server replays to the verdict's observations on a fake
endpoint) and O2.7 (the card on own tools), on the path a user's `run` takes: `config.resolve_plan`
on a settings file with `[own]`, `runs.find_run`, `runs.run_plan` through verifiers' `null`
harness and the launched own-tools tool server, `calibration.records_from_run` and
`calibration.card_from_run`.  The model is the scripted endpoint of `tests/o2_support.py`, which
plays each task's reference calls; nothing leaves the machine and no key is real.

Shapes decided here
-------------------

**1. The plan.**  `resolve_plan(config, root=folder)` reads the tool file `[own] file` names
relative to `root` (the settings file's folder; the working folder when `root` is not given), and
the plan's `own` carries what the taskset needs (shape 4 of `tests/test_o2_server.py`).

**2. The run folder** is `runs/<preset>-<model>/` as for any plan; its `plan.json` carries the
plan's `own`, and `card_from_run` reads the card from the folder alone.

**3. The replay.**  On every own-tools arm, each sampled call that reached the server is replayed
through the simulator and its answer must equal its tool message byte for byte, or the episode is
`replay_mismatch` and scores nothing.
"""

from __future__ import annotations

import dataclasses
import io
import json
import os
import shutil
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tests.fd3_support import arm_dir as arm_dir_name
from tests.helpers import needs_uv
from tests.o1_support import fixture
from tests.o2_support import calibration, config, generator, reference_model, runs
from tests.o2_support import card as own_card

MODEL = "gpt-5-nano-2025-08-07"

FLOWS = ["search_orders.orders[].order_id:get_order.order_id", "get_order.order_id:refund_order.order_id"]


def plan_for(work: Path, base_url: str, *extra: str) -> Any:
    flags = ["--provider", "openai-compatible", "--model", "scripted", "--base-url", base_url,
             "--api-key-env", "O2_API_KEY", "--no-price", "--token-cap", "1000000",
             "--recipe", "first-look", "--tasks-per-level", "2", "--concurrency", "1",
             "--own-file", "tools.json", "--own-name", "acme-support",
             *[word for flow in FLOWS for word in ("--own-flow", flow)], *extra]
    made = config().config_from_init_args(flags)
    return config().resolve_plan(made, root=work)


def own_bundles(plan: Any) -> list[Any]:
    from poisson_tasks import own

    data = Path(plan.own["file"]).read_bytes()
    toolset = own.read_tools(data, name=plan.own["name"]).toolset
    flows = tuple(generator().Flow(f["from"], f["field"], f["to"], f["param"]) for f in plan.own["flows"])
    return [generator().generate(toolset, spec, seed, flows=flows, intents=plan.own["intents"])
            for spec in plan.arms for seed in plan.seeds]


def planted(arm_dir: Path, line_index: int, index: int) -> None:
    """The `index`-th tool message of the `line_index`-th episode, its last character changed."""
    path = arm_dir / "traces.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    row = json.loads(lines[line_index])
    seen = 0
    for trace in row["traces"]:
        for node in trace["nodes"]:
            message = node.get("message") or {}
            if message.get("role") == "tool":
                if seen == index:
                    text = message["content"]
                    message["content"] = text[:-1] + ("0" if text[-1] != "0" else "1")
                seen += 1
    assert seen > index
    lines[line_index] = json.dumps(row)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@dataclasses.dataclass(frozen=True)
class OwnRun:
    plan: Any
    folder: Path
    bundles: tuple[Any, ...]


@pytest.fixture(scope="module")
def own_run(tmp_path_factory: pytest.TempPathFactory) -> Iterator[OwnRun]:
    """One run of `first-look` on the acme set with its two flows, two tasks a level, under the
    published card's model name (the endpoint is the scripted one), so the card can be read beside
    the published card of that model."""
    if shutil.which("uv") is None:
        pytest.skip("the `null` harness launches its program through uv")
    work = tmp_path_factory.mktemp("own-run")
    (work / "tools.json").write_bytes(fixture("acme-mcp-tools-list.json"))
    saved = os.environ.get("O2_API_KEY")
    os.environ["O2_API_KEY"] = "EMPTY"
    try:
        with reference_model() as model:
            plan = plan_for(work, model.base_url, "--model", MODEL)
            bundles = own_bundles(plan)
            for bundle in bundles:
                model.register(bundle)
            folder = runs().find_run(plan, work / "runs")
            assert (folder.status, folder.name) == ("new", f"first-look-{MODEL}")
            result = runs().run_plan(plan, folder, caps={"spend_usd": None, "tokens": 1_000_000},
                                     concurrency=1, watchdog_seconds=300)
            assert (result.verdict, result.episodes_run) == ("done", len(bundles))
        yield OwnRun(plan=plan, folder=Path(folder.path), bundles=tuple(bundles))
    finally:
        if saved is None:
            os.environ.pop("O2_API_KEY", None)
        else:
            os.environ["O2_API_KEY"] = saved


@needs_uv
def test_a_plan_on_own_tools_runs_end_to_end_and_its_replay_holds_each_tool_message(own_run: OwnRun) -> None:
    import verifiers.v1 as vf
    from verifiers.v1.cli.output import read_episodes

    cal = calibration()
    plan, folder = own_run.plan, own_run.folder
    assert [spec.generator_version for spec in plan.arms] == ["own-1"] * len(plan.arms)
    held = json.loads((folder / "plan.json").read_text(encoding="utf-8"))
    assert held["plan"]["own"]["file_digest"] == plan.own["file_digest"]
    by_id = {bundle.task_id: bundle for bundle in own_run.bundles}
    for spec in plan.arms:
        arm_dir = folder / arm_dir_name(spec)
        records = cal.records_from_run(arm_dir, model=MODEL)
        assert [(r.label, r.strict, r.leaky) for r in records] == [("passed", True, True)] * len(plan.seeds)
        episodes = read_episodes(arm_dir, vf.Trace)
        original = (arm_dir / "traces.jsonl").read_bytes()
        try:
            for line_index, episode in enumerate(episodes):
                bundle = by_id[str(episode.task.data.task_id)]
                sent = [str(n.message.content) for n in episode.traces[0].nodes
                        if isinstance(n.message, vf.ToolMessage)]
                assert sent == list(bundle.reference_observations)
                for index in range(len(sent)):
                    planted(arm_dir, line_index, index)
                    changed = cal.records_from_run(arm_dir, model=MODEL)
                    assert (changed[line_index].label, changed[line_index].strict) == ("replay_mismatch", False)
                    (arm_dir / "traces.jsonl").write_bytes(original)
        finally:
            (arm_dir / "traces.jsonl").write_bytes(original)


@needs_uv
def test_the_runs_card_is_an_own_tools_card(own_run: OwnRun) -> None:
    cal = calibration()
    plan = own_run.plan
    card = cal.card_from_run(own_run.folder)
    assert card.verdict.word == "ok" and not card.verdict.partial
    tools = card.artifact.provenance.as_dict()["tools"]
    assert (tools["kind"], tools["name"], tools["tools"], tools["source_format"], tools["file_digest"]) == (
        "own", "acme-support", 5, "mcp", plan.own["file_digest"])
    assert card.artifact.provenance.generator_hash == generator().generator_hash()
    lines = [line for line in card.document.splitlines() if line.strip()]
    assert lines[1] == (
        "Measured on your tools (acme-support, 5 tools from an MCP tool list), with responses "
        "simulated from your schemas. Your backend was never called.")
    assert "own_word_match" in card.claims.flags
    cells: dict[tuple[str, str], list[Any]] = {}
    for record in card.records:
        cells.setdefault((record.arm_id, record.model), []).append(record)
    said = own_card().bite(own_card().against_first(cells, card.artifact.provenance))
    assert said and all(line in card.document for line in said.values())


@needs_uv
def test_card_compare_published_shows_an_own_card_beside_the_published_one(
    own_run: OwnRun, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spec §9: `card --compare published` prints the card and the published card of the same model
    side by side and pools nothing (the command is FD5's, `cli.main`)."""
    import importlib

    from poisson_tasks import cards

    card = calibration().card_from_run(own_run.folder)
    (published,) = [c for c in cards.published() if c.name == "gpt-5-nano"]
    expected = own_card().beside_published(card.artifact, cards.recompute(published).artifact)
    out, err = io.StringIO(), io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", err)
    code = importlib.import_module("poisson_tasks.cli").main(
        ["card", str(own_run.folder), "--compare", "published"], prog="poisson-tasks")
    assert code == 0, err.getvalue()
    assert expected in out.getvalue()


@needs_uv
def test_a_run_of_the_same_plan_in_its_folder_owes_nothing_and_a_changed_file_is_another_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "tools.json").write_bytes(fixture("acme-mcp-tools-list.json"))
    monkeypatch.setenv("O2_API_KEY", "EMPTY")
    with reference_model() as model:
        plan = plan_for(tmp_path, model.base_url, "--tasks-per-level", "1")
        for bundle in own_bundles(plan):
            model.register(bundle)
        folder = runs().find_run(plan, tmp_path / "runs")
        runs().run_plan(plan, folder, caps={"spend_usd": None, "tokens": 1_000_000}, concurrency=1,
                        watchdog_seconds=300)
        again = runs().find_run(plan, tmp_path / "runs")
        assert (again.path, again.status) == (folder.path, "complete")
        (tmp_path / "tools.json").write_bytes(fixture("acme-mcp-tools-list.json") + b"\n")
        moved = plan_for(tmp_path, model.base_url, "--tasks-per-level", "1")
        assert config().plan_hash(moved) != config().plan_hash(plan)
        other = runs().find_run(moved, tmp_path / "runs")
        assert other.path != folder.path and other.status == "new"
