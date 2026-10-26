"""What produced a run, the four rules the first provenance tests left unheld, frozen as tests
once they were ruled in (2026-10-26).

The invariants:
- a run segment with nothing owed writes no line to `produced_by.jsonl`;
- a torn last line (a process that died writing it) is dropped when the record is read, so the
  card reads the record as it was before it;
- the card's provenance block refuses a `produced_by` that lacks a key, names another schema, or
  names another seed list than the block's own, each beside the same block that is accepted;
- on your own tools the stale line reads the own-tools generator the run recorded, not the one the
  block was built under.

The built-in folders are copies of the `tests/fd4_support.py` scenarios; the last two invariants
build their blocks from a published card's stored provenance and from a small made-up own-tools
card, so this file pays for no own-tools run.  Expectations come from the folder, the shipped files
and the literals of `tests/pv_support.py`, never from the code under test.
"""

from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from tests.fd3_support import needs_uv
from tests.fd4_support import RunFolders, fd4_runs
from tests.pv_support import (
    BUILT_IN_GENERATOR,
    FIXTURE_HASHES,
    OWN_TOOLS_GENERATOR,
    RECORD,
    SCHEMA,
    SECTION_1,
    SHIPPED,
    VOCABULARY,
    bare,
    copy_run,
    engine_hash,
    other_hash,
    record_lines,
)

__all__ = ["fd4_runs"]

STALE = ("It is pinned to the generator it was made with, which is not the one this install has, "
         "so it is stale.")
MCP_FILE, MCP_SPEC = FIXTURE_HASHES["acme-mcp-tools-list.json"]


def calibration() -> Any:
    from poisson_tasks import calibration as module

    return module


@needs_uv
def test_pv_7_a_segment_with_nothing_owed_writes_no_line(
    fd4_runs: RunFolders, tmp_path: Path
) -> None:
    """A copy of the `strict` scenario, which owes nothing, run again."""
    from poisson_tasks import runs
    from tests.fd2_fakes import network_guard

    made = fd4_runs["strict"]
    copy = copy_run(made.folder, tmp_path / "runs" / made.folder.name)
    before = (copy / RECORD).read_bytes()
    assert len(record_lines(copy)) == 1
    with fd4_runs._environment(tmp_path) as patch:
        folder = runs.find_run(made.plan, tmp_path / "runs")
        assert (Path(folder.path), folder.status) == (copy, "complete")
        with network_guard(patch):
            result = runs.run_plan(made.plan, folder, caps={"spend_usd": 100.0, "tokens": None},
                                   concurrency=1)
    assert (result.episodes_run, result.episodes_owed) == (0, 0), result
    assert (copy / RECORD).read_bytes() == before


@needs_uv
def test_pv_8_a_torn_last_line_is_dropped_when_the_record_is_read(
    fd4_runs: RunFolders, tmp_path: Path
) -> None:
    provenance = importlib.import_module("poisson_tasks.provenance")
    copy = copy_run(fd4_runs["strict"].folder, tmp_path / "strict-torn")
    (line,) = record_lines(copy)
    expected = {**bare(line), "resumed_with": []}
    whole = json.dumps({**line, "segment": "resumed", "poisson_tasks_version": "0.2.1"})
    with (copy / RECORD).open("a", encoding="utf-8") as handle:
        handle.write(whole[: len(whole) // 2])
    assert provenance.read_run(copy) == expected
    assert dict(calibration().card_from_run(copy).artifact.provenance.produced_by) == expected


def shipped_block() -> dict[str, Any]:
    """A published card's stored provenance block, which carries no record."""
    path = sorted(SHIPPED.glob("*/artifact.json"))[0]
    block: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))["provenance"]
    assert "produced_by" not in block
    return block


def record_for(block: dict[str, Any], **changes: Any) -> dict[str, Any]:
    seeds = [int(seed) for seed in block["seed_list"]]
    record = {
        "schema": SCHEMA, "poisson_tasks_version": "0.2.0",
        "verifiers_version": str(block["verifiers_version"]), "generator_version": "1",
        "builtin_generator_hash": BUILT_IN_GENERATOR, "own_generator_hash": None,
        "engine_hash": engine_hash(), "vocabulary_hash": VOCABULARY, "tool_format": None,
        "tool_spec_hash": None, "tool_file_sha256": None, "plan_hash": other_hash("plan"),
        "preset": "card", "seeds": seeds,
        "seed_list_hash": hashlib.sha256(json.dumps(seeds).encode("utf-8")).hexdigest(),
        "resumed_with": [],
    }
    record.update(changes)
    return record


def test_pv_9_the_block_refuses_a_record_it_cannot_carry() -> None:
    """Each refusal beside the same block and record, which is accepted."""
    block = shipped_block()
    assert block["seed_list_hash"] == record_for(block)["seed_list_hash"]
    accepted = calibration().Provenance(**block, produced_by=record_for(block))
    assert dict(accepted.produced_by) == record_for(block)
    assert accepted.as_dict()["produced_by"] == record_for(block)

    refused = [record_for(block, schema="poisson-tasks.produced-by/2"),
               record_for(block, seed_list_hash=other_hash("seed list"))]
    for key in SECTION_1:
        lacking = record_for(block)
        del lacking[key]
        refused.append(lacking)
    for record in refused:
        with pytest.raises(ValueError) as error:
            calibration().Provenance(**block, produced_by=record)
        message = str(error.value)
        assert message.strip() and "\n" not in message.strip(), message


def own_card(produced_by: dict[str, Any] | None, generator_hash: str) -> Any:
    """A small own-tools card, two tasks of one arm, under a block built with `generator_hash`."""
    cal = calibration()
    seeds = [7001, 7002]
    prov = cal.Provenance(
        package_version="0.2.0", engine_hash=engine_hash(), generator_hash=generator_hash,
        vocabulary_hash=VOCABULARY, verifiers_version="0.3.1", harness_id="null",
        models=[{"id": "model-a", "revision": "model-a", "endpoint_host": "h"}],
        decoding=dict(cal.DECODING), seed_list=seeds,
        seed_list_hash=hashlib.sha256(json.dumps(seeds).encode()).hexdigest(),
        S=len(seeds), n=1, k_values=[1], bootstrap_resamples=200, bootstrap_seed=20260922,
        delta_star=0.15, saturation_high=0.95, saturation_low=0.05, instrument_threshold=0.02,
        rate_read_date="2026-10-26", serving={"model-a": {"kind": "hosted", "endpoint_host": "h"}},
        budget=dict(cal.DEFAULT_BUDGET),
        tools={"kind": "own", "name": "acme-support", "tools": 5, "source_format": "mcp",
               "file_digest": MCP_FILE, "intents": [], "flows": 0, "generator": "own-1"},
        produced_by=produced_by)
    rows = [cal.EpisodeRecord(
        task_id=f"own-{seed}", arm_id="depth:d1", model="model-a", seed=seed, attempt=0,
        strict=True, leaky=True, label="passed", turns=3, sampled_calls=2, prompt_tokens=10,
        cached_input_tokens=0, completion_tokens=5, reasoning_tokens=0) for seed in seeds]
    return cal.build_artifact({("depth:d1", "model-a"): rows}, prov)


def test_pv_10_the_own_tools_stale_line_reads_the_generator_the_run_recorded() -> None:
    """The record decides both ways: a recorded own-tools generator other than this install's is
    stale under a block built with this install's, and this install's is not stale under a block
    built with another."""
    seeds = [7001, 7002]
    record = {
        "schema": SCHEMA, "poisson_tasks_version": "0.2.0", "verifiers_version": "0.3.1",
        "generator_version": "own-1", "builtin_generator_hash": BUILT_IN_GENERATOR,
        "own_generator_hash": OWN_TOOLS_GENERATOR, "engine_hash": engine_hash(),
        "vocabulary_hash": VOCABULARY, "tool_format": "mcp", "tool_spec_hash": MCP_SPEC,
        "tool_file_sha256": MCP_FILE, "plan_hash": other_hash("plan"), "preset": "first-look",
        "seeds": seeds,
        "seed_list_hash": hashlib.sha256(json.dumps(seeds).encode()).hexdigest(),
        "resumed_with": [],
    }
    moved = {**record, "own_generator_hash": other_hash("own-tools generator")}
    claims = calibration().card_claims
    assert STALE not in claims(own_card(record, OWN_TOOLS_GENERATOR)).not_claimed
    assert STALE in claims(own_card(moved, OWN_TOOLS_GENERATOR)).not_claimed
    assert STALE not in claims(own_card(record, other_hash("own-tools generator"))).not_claimed
