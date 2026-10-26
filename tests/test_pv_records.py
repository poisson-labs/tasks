"""What produced a run, as the run records it and as its card and export say it, frozen as tests.

The invariants:
- a run writes `produced_by.jsonl` in its folder before its first request: one line per segment
  that dispatches episodes, `started` for the folder's first and `resumed` for each later one,
  each the object the docs describe with `at` (UTC, `Z`) and `segment` first after `schema`, its
  values those of the install and the plan that ran;
- `plan.json` is as 0.1.0 wrote it, so every folder is found and resumed as before;
- a resume of a folder started with another generator than this install's is refused by
  `runs.run_plan` in one line before any request, and the folder keeps its bytes;
- the card carries the run's record (`artifact.json`, `card --json`, a `made with` row right after
  the `run` row, a `What produced it` section in `card.md`), and `card --check` rebuilds it byte for
  byte; a run with no record reads as not recorded, and its card is a 0.1.0 card;
- the card is stale when the generator the run recorded is not this install's;
- `export --to verifiers` writes `produced_by.json` for the plan beside configs that do not change;
- on your own tools, a changed tool contract, or a file reformatted without changing it, is named
  when two runs are compared, and no figure is set beside another.

The built-in run folders are the scenarios of `tests/fd4_support.py`, copied before anything is
edited or written into them.  The own-tools folder is the `own_run` fixture of
`tests/test_o2_run.py`: one more run of its six episodes against the scripted model, on the acme
MCP tool list, paid once for this file.  Expectations come from the plan, the folder, the shipped
files and our own copy of the rule (`tests/pv_support.py`), never from the code under test.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from tests.fd2_fakes import network_guard
from tests.fd3_support import arm_dir, needs_uv
from tests.fd4_support import RunFolders, fd4_runs, partial_design, plan_from_folder
from tests.fd5_support import World, fixture_flags, invoke, world, write_config
from tests.pv_support import (
    AT,
    BUILT_IN_GENERATOR,
    FIXTURE_HASHES,
    OWN_TOOLS_GENERATOR,
    PROG,
    RECORD,
    SECTION_1,
    bare,
    card_md_section,
    copy_run,
    engine_hash,
    expected_record,
    fixture,
    invoke_json,
    other_hash,
    record_lines,
    rewrite_first_line,
    rows,
    sha256,
)
from tests.test_o2_run import OwnRun, own_run

__all__ = ["fd4_runs", "own_run", "world"]

MCP_FILE, MCP_SPEC = FIXTURE_HASHES["acme-mcp-tools-list.json"]
OWN_TOOLS = ("mcp", MCP_SPEC, MCP_FILE)

# The keys of a run's plan in `plan.json`, as 0.1.0 writes them; a plan on your own tools adds
# `own`.
PLAN_KEYS = {"preset", "arms", "seeds", "attempts", "model", "decoding", "max_model_calls"}

# The provenance keys of the `strict` scenario's card as 0.1.0 writes it.
PROVENANCE_KEYS_0_1_0 = {
    "S", "arms", "bootstrap_resamples", "bootstrap_seed", "budget", "decoding", "delta_star",
    "engine_hash", "generator_hash", "harness_id", "instrument_threshold", "k_values",
    "max_model_calls", "models", "n", "no_call_threshold", "package_version", "rate_read_date",
    "saturation_high", "saturation_low", "seed_list", "seed_list_hash", "serving",
    "verifiers_version", "vocabulary_hash",
}

STALE = ("It is pinned to the generator it was made with, which is not the one this install has, "
         "so it is stale.")
NOT_RECORDED = "not recorded: the run was made before poisson-tasks 0.2.0"


def calibration() -> Any:
    from poisson_tasks import calibration as module

    return module


def one_started_line(folder: Path) -> dict[str, Any]:
    lines = record_lines(folder)
    assert [line.get("segment") for line in lines] == ["started"], lines
    (line,) = lines
    assert list(line)[:3] == ["schema", "at", "segment"], list(line)
    assert set(line) == {*SECTION_1, "at", "segment"}, sorted(line)
    assert AT.match(str(line["at"])), line["at"]
    return line


def row_of(text: str, label: str) -> tuple[str, int, int]:
    found = [(value, start, end) for name, value, start, end in rows(text) if name == label]
    assert len(found) == 1, (label, text)
    return found[0]


def made_with(line: dict[str, Any], *, own: str | None = None) -> str:
    """The `made with` row the docs give, with the record's values."""
    parts = [f"poisson-tasks {line['poisson_tasks_version']}",
             f"generator {line['builtin_generator_hash'][:12]}"]
    if own is not None:
        parts += [f"own-tools generator {line['own_generator_hash'][:12]}",
                  f"tool spec {line['tool_spec_hash'][:12]} ({own})"]
    parts += [f"plan {line['plan_hash'][:12]} ({line['preset']})",
              f"{len(line['seeds'])} seeds, list {line['seed_list_hash'][:12]}"]
    return " · ".join(parts)


# ---------------------------------------------------------------------------
# the run records it
# ---------------------------------------------------------------------------


@needs_uv
def test_pv_5_a_built_in_run_records_what_produced_it(fd4_runs: RunFolders) -> None:
    made = fd4_runs["strict"]
    line = one_started_line(made.folder)
    expected = expected_record(made.plan)
    assert expected["tool_format"] is None and expected["own_generator_hash"] is None
    assert bare(line) == expected


@needs_uv
def test_pv_5_an_own_tools_run_records_what_produced_it(own_run: OwnRun) -> None:
    line = one_started_line(own_run.folder)
    assert sha256(Path(own_run.plan.own["file"]).read_bytes()) == MCP_FILE
    expected = expected_record(own_run.plan, tools=OWN_TOOLS)
    assert (expected["generator_version"], expected["own_generator_hash"]) == (
        "own-1", OWN_TOOLS_GENERATOR)
    assert bare(line) == expected


@needs_uv
def test_pv_6_plan_json_is_as_0_1_0_wrote_it(fd4_runs: RunFolders, own_run: OwnRun) -> None:
    from poisson_tasks import config

    for name in ("strict", "failed_once_resumed"):
        made = fd4_runs[name]
        held = json.loads((made.folder / "plan.json").read_text(encoding="utf-8"))
        assert set(held) == {"plan", "plan_hash"}, name
        assert set(held["plan"]) == PLAN_KEYS, name
        assert held["plan_hash"] == config.plan_hash(plan_from_folder(made.folder)), name
        assert held["plan_hash"] == config.plan_hash(made.plan), name
    held = json.loads((own_run.folder / "plan.json").read_text(encoding="utf-8"))
    assert set(held) == {"plan", "plan_hash"}
    assert set(held["plan"]) == PLAN_KEYS | {"own"}
    assert set(held["plan"]["own"]) == set(own_run.plan.own)
    assert held["plan_hash"] == config.plan_hash(own_run.plan)


@needs_uv
def test_pv_7_a_resume_appends_a_resumed_line_and_the_card_names_no_other_version(
    fd4_runs: RunFolders,
) -> None:
    """The `failed_once` folder as it was before its resume, and after it."""
    before = fd4_runs["failed_once"]
    after = fd4_runs["failed_once_resumed"]
    first = one_started_line(before.folder)
    lines = record_lines(after.folder)
    assert [line["segment"] for line in lines] == ["started", "resumed"]
    assert lines[0] == first
    assert AT.match(str(lines[1]["at"]))
    assert bare(lines[1]) == bare(lines[0]) == expected_record(after.plan)
    card = calibration().card_from_run(after.folder)
    assert dict(card.artifact.provenance.produced_by) == {**bare(lines[0]), "resumed_with": []}


def snapshot(folder: Path) -> dict[str, bytes]:
    """The files a refused resume must leave as they were."""
    paths = [folder / RECORD, folder / "spend.jsonl", folder / "plan.json",
             *sorted(folder.rglob("traces.jsonl"))]
    return {str(path.relative_to(folder)): path.read_bytes() for path in paths}


@needs_uv
def test_pv_7_a_resume_of_a_run_started_with_another_generator_is_refused_before_any_request(
    fd4_runs: RunFolders, tmp_path: Path
) -> None:
    """Two copies of the `partial` scenario, which owes tasks, resumed under the cap it was run
    with: the copy whose `started` line names another built-in generator is refused in one line,
    with nothing written and no connection made; the untouched copy is not refused."""
    from poisson_tasks import runs

    made = fd4_runs["partial"]
    _, cap = partial_design()
    caps = {"spend_usd": cap, "tokens": None}
    moved = other_hash("generator")
    for where, edit in ((tmp_path / "control", False), (tmp_path / "moved", True)):
        copy = copy_run(made.folder, where / "runs" / made.folder.name)
        if edit:
            started = rewrite_first_line(copy, builtin_generator_hash=moved)
            before = snapshot(copy)
        with fd4_runs._environment(where) as patch:
            folder = runs.find_run(made.plan, where / "runs")
            assert (Path(folder.path), folder.status) == (copy, "resume")
            with network_guard(patch) as events:
                if not edit:
                    result = runs.run_plan(made.plan, folder, caps=caps, concurrency=1)
                    assert result.episodes_run == 0, result
                    continue
                with pytest.raises(ValueError) as refused:
                    runs.run_plan(made.plan, folder, caps=caps, concurrency=1)
        message = str(refused.value)
        assert message.strip() and "\n" not in message.strip(), message
        assert copy.name in message, message
        assert f"{moved[:12]} there, {BUILT_IN_GENERATOR[:12]} here" in message, message
        assert f"poisson-tasks {started['poisson_tasks_version']}" in message, message
        assert not [event for event in events if event[0] == "connect"], events
        assert snapshot(copy) == before


# ---------------------------------------------------------------------------
# the card carries it
# ---------------------------------------------------------------------------


@needs_uv
def test_pv_8_the_built_in_card_carries_the_record(
    fd4_runs: RunFolders, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = copy_run(fd4_runs["strict"].folder, world.tmp / "strict-run")
    line = one_started_line(folder)
    expected = {**bare(line), "resumed_with": []}
    ran = invoke(["card", str(folder)], prog=PROG, monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    _, run_start, run_end = row_of(ran.out, "run")
    value, start, _ = row_of(ran.out, "made with")
    assert start == run_end + 1 and start > run_start, ran
    assert value == made_with(line)
    stored = json.loads((folder / "card" / "artifact.json").read_text(encoding="utf-8"))
    assert stored["provenance"]["produced_by"] == expected

    text = (folder / "card" / "card.md").read_text(encoding="utf-8")
    assert text.index("## What produced it") < text.index("## What this card means")
    section = card_md_section(text, "What produced it")
    for wanted in (
        "Recorded by the run before its first request.",
        f"- poisson-tasks {line['poisson_tasks_version']}, verifiers {line['verifiers_version']}",
        f"- built-in generator `{BUILT_IN_GENERATOR}` (generator version \"1\")",
        "- tools: the built-in tools, made by the generator above",
        f"- domain `{engine_hash()}`, vocabulary `{line['vocabulary_hash']}`",
        f"- plan `{line['plan_hash']}` (preset custom), 2 seeds, seed list "
        f"`{line['seed_list_hash']}`",
    ):
        assert wanted in section, (wanted, section)

    ran, document = invoke_json(["card", str(folder), "--force"], monkeypatch)
    assert ran.code == 0, ran
    assert document["produced_by"] == expected
    written = (folder / "card" / "artifact.json").read_bytes()
    checked = invoke(["card", "--check", str(folder / "card")], prog=PROG, monkeypatch=monkeypatch)
    assert checked.code == 0 and checked.word == "ok", checked
    assert (folder / "card" / "artifact.json").read_bytes() == written


@needs_uv
def test_pv_8_the_own_tools_card_carries_the_record(
    own_run: OwnRun, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = copy_run(own_run.folder, world.tmp / "own-run")
    line = one_started_line(folder)
    expected = {**bare(line), "resumed_with": []}
    ran = invoke(["card", str(folder)], prog=PROG, monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    value, _, _ = row_of(ran.out, "made with")
    assert value == made_with(line, own="an MCP tool list")
    stored = json.loads((folder / "card" / "artifact.json").read_text(encoding="utf-8"))
    assert stored["provenance"]["produced_by"] == expected
    section = card_md_section((folder / "card" / "card.md").read_text(encoding="utf-8"),
                              "What produced it")
    for wanted in (
        f"- own-tools generator `{OWN_TOOLS_GENERATOR}` (generator version \"own-1\")",
        f"- tool spec `{MCP_SPEC}`: the canonical JSON of your tool file, an MCP tool list; the "
        f"file's own bytes hash to `{MCP_FILE}`",
    ):
        assert wanted in section, (wanted, section)
    ran, document = invoke_json(["card", str(folder), "--force"], monkeypatch)
    assert ran.code == 0, ran
    assert document["produced_by"] == expected


@needs_uv
def test_pv_9_a_run_made_before_0_2_0_reads_as_not_recorded(
    fd4_runs: RunFolders, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = copy_run(fd4_runs["strict"].folder, world.tmp / "strict-before")
    (folder / RECORD).unlink()
    ran = invoke(["card", str(folder)], prog=PROG, monkeypatch=monkeypatch)
    assert ran.code == 0, ran
    assert row_of(ran.out, "made with")[0] == NOT_RECORDED
    stored = json.loads((folder / "card" / "artifact.json").read_text(encoding="utf-8"))
    assert set(stored["provenance"]) == PROVENANCE_KEYS_0_1_0
    section = card_md_section((folder / "card" / "card.md").read_text(encoding="utf-8"),
                              "What produced it")
    assert "Not recorded: the run was made before poisson-tasks 0.2.0." in section, section
    ran, document = invoke_json(["card", str(folder), "--force"], monkeypatch)
    assert ran.code == 0, ran
    assert "produced_by" in document and document["produced_by"] is None


@needs_uv
def test_pv_10_the_stale_line_reads_the_generator_the_run_recorded(
    fd4_runs: RunFolders, tmp_path: Path
) -> None:
    untouched = copy_run(fd4_runs["strict"].folder, tmp_path / "strict-run")
    moved = copy_run(fd4_runs["strict"].folder, tmp_path / "strict-moved")
    rewrite_first_line(moved, builtin_generator_hash=other_hash("generator"))
    assert STALE not in calibration().card_from_run(untouched).claims.not_claimed
    claims = calibration().card_from_run(moved).claims
    assert STALE in claims.not_claimed and "stale" in claims.flags


# ---------------------------------------------------------------------------
# the export says it
# ---------------------------------------------------------------------------


@needs_uv
def test_pv_11_the_export_writes_what_produced_it_and_its_configs_do_not_change(
    fd4_runs: RunFolders, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The `strict` scenario's level and seeds, as a settings file."""
    from poisson_tasks import config, runs
    from poisson_tasks.knobs import arm_id

    strict = fd4_runs["strict"].plan
    seeds = ",".join(str(seed) for seed in strict.seeds)
    write_config(world.work / "tasks.toml", fixture_flags("http://127.0.0.1:9/v1", seeds=seeds))
    plan = config.resolve_plan(config.load_config(world.work / "tasks.toml"))
    assert [arm_id(spec) for spec in plan.arms] == [arm_id(spec) for spec in strict.arms]
    assert list(plan.seeds) == list(strict.seeds)
    expected = expected_record(plan)

    ran, document = invoke_json(["export", "--to", "verifiers"], monkeypatch)
    assert ran.code == 0, ran
    folder = world.work / "export"
    configs = {f"eval-{arm_dir(spec)}.json": spec for spec in plan.arms}
    assert sorted(path.name for path in folder.iterdir()) == sorted([*configs, "produced_by.json"])
    written = (folder / "produced_by.json").read_bytes()
    assert json.loads(written) == expected
    assert document["produced_by"] == expected
    for name, spec in configs.items():
        held = json.loads((folder / name).read_text(encoding="utf-8"))
        made = json.loads(json.dumps(runs.verifiers_config(plan, spec)))
        assert held == {**made, "output_dir": held["output_dir"]}, name

    again = invoke(["export", "--to", "verifiers", "--force"], prog=PROG, monkeypatch=monkeypatch)
    assert again.code == 0, again
    assert (folder / "produced_by.json").read_bytes() == written


# ---------------------------------------------------------------------------
# on your own tools, compare names the contract
# ---------------------------------------------------------------------------


@needs_uv
def test_pv_14_own_tools_a_changed_contract_or_a_rewritten_file_is_named(
    own_run: OwnRun, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Copies of the own-tools run, compared with a copy whose record names another contract,
    and with one whose record names only another file digest."""
    other_file, other_spec = FIXTURE_HASHES["acme-openai-chat.json"]
    rewritten = sha256(fixture("acme-mcp-tools-list.json") + b"\n")
    cases = (
        ("own-other-contract", {"tool_spec_hash": other_spec, "tool_file_sha256": other_file},
         "{a} and {b} were made on different tool contracts (tool spec "
         f"{MCP_SPEC[:12]} and {other_spec[:12]}), so their tasks differ and a shift between them "
         "is not the model's alone",
         ["tool_spec_hash", "tool_file_sha256"]),
        ("own-rewritten-file", {"tool_file_sha256": rewritten},
         "{a} and {b} share one tool contract (tool spec "
         f"{MCP_SPEC[:12]}), but the file was reformatted, and tasks are drawn from the file's "
         "bytes, so their tasks differ",
         ["tool_file_sha256"]),
    )
    for name, edit, sentence, keys in cases:
        a = copy_run(own_run.folder, world.tmp / name / "own-run")
        b = copy_run(own_run.folder, world.tmp / name / name)
        rewrite_first_line(b, **edit)
        ran, document = invoke_json(["card", str(a), "--compare", str(b)], monkeypatch)
        assert ran.code == 0, ran
        assert document["verdict"] == "different", document
        assert document["sentence"] == sentence.format(a=a.name, b=b.name)
        assert document["changed"] == keys
        text = (a / "card" / "compare.md").read_text(encoding="utf-8")
        assert document["sentence"] in text
        assert "# Cards side by side" not in text
        assert not (b / "card").exists()
        shutil.rmtree(world.tmp / name)
