"""C2.7: the provenance every version 2 card carries, and the refusal to build one without it.

The design's table, group by group: the package (its version; what produced the run, the command
and its arguments); the generator (its label and hash, the own-tools label and hash, the engine
and vocabulary hashes, the tokenizer and its file's sha256); the tasks (the seed list and its
hash, S = 60, n = 5, the arm list and its order, strictness, split, the 32-call cap,
concurrency); the own-tools arms (the fixture's sha256, the tool format, the tool-spec hash, the
plan hash); the model (the id asked for, every distinct `model` value the answers carried, the
first and last call in UTC); the serving (hosted: the endpoint's host and the API surface;
local: the stack, its version, the flags, the GPU, the weights' revision, the quantization, the
chat template's hash); the decoding (as sent, with each field not sent named as not sent); the
prices (input, cached input, output per million tokens, the date they were read, Claude's
prompt-length threshold); the run (phase 1's verdict, resumes, re-runs and void arms with their
causes, the spend recorded per arm); and the analysis (2,000 resamples, seed 20260922, the 0.15
resolution, floor 0.15, ceiling 0.85, the 0.02 instrument threshold, the rule's version
"0.5.0").  A version 2 card's artifact fails to build if any of these is missing.

Shapes decided here
-------------------
The block is `card_run.build_artifact(folder)["provenance"]`, a JSON mapping.  It keeps the
names the published blocks already use for what they already carry (`package_version`,
`generator_hash`, `engine_hash`, `vocabulary_hash`, `seed_list`, `seed_list_hash`, `S`, `n`,
`arms`, `max_model_calls`, `concurrency`, `models`, `serving` keyed by the model's id,
`decoding`, `rate_read_date`, `bootstrap_resamples`, `bootstrap_seed`, `delta_star`,
`instrument_threshold`), so the machinery that reads a block reads this one, and adds the rest
under the names in `HOSTED` and `LOCAL` below.  A path is a tuple of keys; `MODEL` stands for
the model's id.  `card_run.check_provenance(block)` returns nothing for a whole block and raises
a `ValueError` that names the missing field by its last key.

The rest of the artifact (the cells and what the card prints) is the reading's, not this file's.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

import pytest

from tests.c2_support import (
    ACME_SHA256,
    ARMS,
    BUILT_IN_HASH,
    DECODING,
    DESIGN,
    HAIKU,
    LUNA,
    OWN_HASH,
    PRICES,
    QWEN,
    QWEN_REVISION,
    card_run,
    clean_run,
    needs_uv,
    read,
)

MODEL = "<model>"
Path_ = tuple[Any, ...]

SHARED: tuple[Path_, ...] = (
    # the package
    ("card_version",),
    ("design",),
    ("role",),
    ("package_version",),
    ("produced_by", "command"),
    ("produced_by", "arguments"),
    # the generator
    ("generator_version",),
    ("generator_hash",),
    ("own_generator_version",),
    ("own_generator_hash",),
    ("engine_hash",),
    ("vocabulary_hash",),
    ("tokenizer", "encoding"),
    ("tokenizer", "sha256"),
    # the tasks
    ("seed_list",),
    ("seed_list_hash",),
    ("S",),
    ("n",),
    ("arms",),
    ("strictness",),
    ("split",),
    ("max_model_calls",),
    ("concurrency",),
    # the own-tools arms
    ("own_tools", "fixture_sha256"),
    ("own_tools", "tool_format"),
    ("own_tools", "tool_spec_hash"),
    ("own_tools", "plan_hash"),
    # the model
    ("models", 0, "id"),
    ("answer_models",),
    ("first_call",),
    ("last_call",),
    # the serving
    ("serving", MODEL, "kind"),
    # the decoding
    ("decoding", "temperature"),
    ("decoding", "top_p"),
    ("decoding", "reasoning_effort"),
    ("decoding", "max_tokens"),
    # the run
    ("run", "phase1"),
    ("run", "resumes"),
    ("run", "reruns"),
    ("run", "void_arms"),
    ("run", "spend_by_arm"),
    # the analysis
    ("bootstrap_resamples",),
    ("bootstrap_seed",),
    ("delta_star",),
    ("floor",),
    ("ceiling",),
    ("instrument_threshold",),
    ("rule_version",),
)
HOSTED: tuple[Path_, ...] = SHARED + (
    ("serving", MODEL, "endpoint_host"),
    ("serving", MODEL, "api_surface"),
    # the prices
    ("models", 0, "input_rate"),
    ("models", 0, "cached_input_rate"),
    ("models", 0, "output_rate"),
    ("rate_read_date",),
    ("prompt_length_threshold",),
)
LOCAL: tuple[Path_, ...] = SHARED + (
    ("serving", MODEL, "stack"),
    ("serving", MODEL, "stack_version"),
    ("serving", MODEL, "flags"),
    ("serving", MODEL, "gpu"),
    ("serving", MODEL, "revision"),
    ("serving", MODEL, "quantization"),
    ("serving", MODEL, "chat_template_sha256"),
)
HEX64 = re.compile(r"[0-9a-f]{64}")
UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|\+00:00)")


def at(block: Any, path: Path_, model: str) -> Any:
    node = block
    for part in path:
        key = model if part == MODEL else part
        if isinstance(key, int):
            assert isinstance(node, list) and len(node) > key, path
        else:
            assert isinstance(node, dict) and key in node, path
        node = node[key]
    return node


def dropped(block: Any, path: Path_, model: str) -> Any:
    copy = json.loads(json.dumps(block))
    node = copy
    for part in path[:-1]:
        node = node[model if part == MODEL else part]
    del node[path[-1]]
    return copy


def block_of(found: dict[str, Any]) -> dict[str, Any]:
    assert found["code"] == 0, found["out"] + found["err"]
    provenance = card_run().build_artifact(found["folder"])["provenance"]
    assert isinstance(provenance, dict)
    return provenance


def local_block(hosted: dict[str, Any]) -> dict[str, Any]:
    """A hosted run's block turned into the open model's: served locally, with no dollar price."""
    block = json.loads(json.dumps(hosted))
    block["models"] = [{"id": QWEN, "revision": QWEN_REVISION, "endpoint_host": "127.0.0.1:8000"}]
    block["serving"] = {
        QWEN: {
            "kind": "local",
            "stack": "vllm",
            "stack_version": "0.31.2",
            "flags": ["--revision", QWEN_REVISION],
            "gpu": "NVIDIA A100-SXM4-80GB",
            "revision": QWEN_REVISION,
            "quantization": "fp8",
            "chat_template_sha256": "ab" * 32,
        }
    }
    block["decoding"] = dict(DECODING[QWEN])
    block["answer_models"] = [QWEN]
    for name in ("prompt_length_threshold",):
        block.pop(name, None)
    return block


@pytest.fixture(scope="module")
def luna(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    return block_of(clean_run(LUNA, tmp_path_factory))


@pytest.fixture(scope="module")
def haiku(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    return block_of(clean_run(HAIKU, tmp_path_factory))


pytestmark = needs_uv


@pytest.mark.parametrize("model", [LUNA, HAIKU])
def test_a_hosted_runs_block_carries_every_field_of_the_table(
    model: str, tmp_path_factory: pytest.TempPathFactory
) -> None:
    block = block_of(clean_run(model, tmp_path_factory))
    for path in HOSTED:
        at(block, path, model)
    card_run().check_provenance(block)
    assert json.loads(json.dumps(block)) == block
    assert block["arms"] == list(clean_run(model, tmp_path_factory)["design"].arms)


def test_the_package_and_generator_groups_say_what_ran(luna: dict[str, Any]) -> None:
    import importlib.metadata

    assert (luna["card_version"], luna["design"], luna["role"]) == (2, DESIGN, "card")
    assert luna["package_version"] == importlib.metadata.version("poisson-tasks")
    assert isinstance(luna["produced_by"]["command"], str) and luna["produced_by"]["command"]
    arguments = luna["produced_by"]["arguments"]
    assert arguments["model"] == LUNA and arguments["cap"] == 5.0
    assert arguments["concurrency"] == 8
    assert (luna["generator_version"], luna["generator_hash"]) == ("4", BUILT_IN_HASH)
    assert (luna["own_generator_version"], luna["own_generator_hash"]) == ("own-4", OWN_HASH)
    assert HEX64.fullmatch(luna["engine_hash"]) and HEX64.fullmatch(luna["vocabulary_hash"])
    assert luna["tokenizer"]["encoding"] == "o200k_base"
    assert HEX64.fullmatch(luna["tokenizer"]["sha256"])


def test_the_tokenizer_digest_is_the_installed_files(luna: dict[str, Any]) -> None:
    import hashlib

    import poisson_tasks

    path = Path(poisson_tasks.__file__).resolve().parent / "data" / "o200k_base.tiktoken"
    assert luna["tokenizer"]["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()


def test_the_tasks_group_is_the_design_that_ran(
    luna: dict[str, Any], tmp_path_factory: pytest.TempPathFactory
) -> None:
    from poisson_tasks import calibration as cal

    design = clean_run(LUNA, tmp_path_factory)["design"]
    assert luna["seed_list"] == list(design.seeds)
    assert luna["seed_list_hash"] == cal._seed_list_digest(design.seeds)
    assert (luna["S"], luna["n"]) == (len(design.seeds), design.attempts)
    assert luna["arms"] == list(ARMS)
    assert (luna["strictness"], luna["split"]) == ("strict", "eval")
    assert (luna["max_model_calls"], luna["concurrency"]) == (32, 8)


def test_the_own_tools_group_names_the_fixture_and_its_contract(luna: dict[str, Any]) -> None:
    from poisson_tasks import provenance
    from tests.c2_fake import ACME_FILE

    own = luna["own_tools"]
    assert own["fixture_sha256"] == ACME_SHA256 and own["tool_format"] == "openai"
    assert own["tool_spec_hash"] == provenance.tool_spec_hash(ACME_FILE.read_bytes())
    assert HEX64.fullmatch(own["plan_hash"])


@pytest.mark.parametrize("model", [LUNA, HAIKU])
def test_the_model_group_is_the_id_asked_for_what_answered_and_when(
    model: str, tmp_path_factory: pytest.TempPathFactory
) -> None:
    block = block_of(clean_run(model, tmp_path_factory))
    assert block["models"][0]["id"] == model
    assert block["answer_models"] == [model]
    assert UTC.fullmatch(block["first_call"]) and UTC.fullmatch(block["last_call"])
    assert block["first_call"] <= block["last_call"]


def test_a_hosted_models_serving_is_its_host_and_its_api_surface(
    luna: dict[str, Any], haiku: dict[str, Any]
) -> None:
    assert luna["serving"][LUNA]["kind"] == haiku["serving"][HAIKU]["kind"] == "hosted"
    assert luna["serving"][LUNA]["api_surface"] == "OpenAI chat completions"
    assert haiku["serving"][HAIKU]["api_surface"] == "Anthropic OpenAI-compatible endpoint"
    # the runs here were sent to the fake, and the block says where they went
    assert luna["serving"][LUNA]["endpoint_host"].startswith("127.0.0.1:")
    assert luna["models"][0]["endpoint_host"] == luna["serving"][LUNA]["endpoint_host"]


def test_the_decoding_is_as_sent_with_each_unsent_field_named(
    luna: dict[str, Any], haiku: dict[str, Any]
) -> None:
    assert luna["decoding"] == DECODING[LUNA]
    assert haiku["decoding"] == DECODING[HAIKU]
    assert haiku["decoding"]["top_p"] == haiku["decoding"]["reasoning_effort"] == "not sent"


def test_the_prices_are_the_rates_their_read_date_and_claudes_threshold(
    luna: dict[str, Any], haiku: dict[str, Any]
) -> None:
    for model, block in ((LUNA, luna), (HAIKU, haiku)):
        entry = block["models"][0]
        assert (
            entry["input_rate"],
            entry["cached_input_rate"],
            entry["output_rate"],
            block["rate_read_date"],
        ) == PRICES[model]
    assert haiku["prompt_length_threshold"] == 100_000
    assert luna["prompt_length_threshold"] is None


def test_the_run_group_holds_phase_1_the_resumes_the_voids_and_each_arms_spend(
    luna: dict[str, Any], tmp_path_factory: pytest.TempPathFactory
) -> None:
    found = clean_run(LUNA, tmp_path_factory)
    run = luna["run"]
    assert run["phase1"]["passed"] is True and run["phase1"]["episodes"] == 168
    assert run["phase1"]["spent"] > 0
    assert run["resumes"] == [] and run["reruns"] == [] and run["void_arms"] == []
    assert list(run["spend_by_arm"]) == list(ARMS)
    assert all(dollars > 0 for dollars in run["spend_by_arm"].values())
    spent = read(found["folder"] / "status.json")["spent"]
    assert abs(run["phase1"]["spent"] + sum(run["spend_by_arm"].values()) - spent) < 1e-9


def test_the_analysis_group_is_the_registered_rule(luna: dict[str, Any]) -> None:
    assert (luna["bootstrap_resamples"], luna["bootstrap_seed"]) == (2000, 20260922)
    assert (luna["delta_star"], luna["floor"], luna["ceiling"]) == (0.15, 0.15, 0.85)
    assert luna["instrument_threshold"] == 0.02 and luna["rule_version"] == "0.5.0"


@pytest.mark.parametrize("path", HOSTED, ids=lambda path: ".".join(str(part) for part in path))
def test_a_hosted_block_missing_any_field_is_refused_naming_it(
    path: Path_, luna: dict[str, Any]
) -> None:
    with pytest.raises(ValueError) as refused:
        card_run().check_provenance(dropped(luna, path, LUNA))
    assert str(path[-1]) in str(refused.value), (path, str(refused.value))


def test_the_open_models_block_is_whole_with_its_serving_facts_and_no_price(
    luna: dict[str, Any],
) -> None:
    block = local_block(luna)
    for path in LOCAL:
        at(block, path, QWEN)
    card_run().check_provenance(block)


@pytest.mark.parametrize(
    "path",
    [path for path in LOCAL if path not in SHARED],
    ids=lambda path: ".".join(str(part) for part in path),
)
def test_a_local_block_missing_any_serving_fact_is_refused_naming_it(
    path: Path_, luna: dict[str, Any]
) -> None:
    with pytest.raises(ValueError) as refused:
        card_run().check_provenance(dropped(local_block(luna), path, QWEN))
    assert str(path[-1]) in str(refused.value), (path, str(refused.value))


def test_the_artifact_is_not_built_from_a_folder_whose_record_lacks_the_decoding(
    tmp_path: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """The artifact's own build goes through the check: a folder that cannot say how the model
    was called makes no artifact."""
    source = clean_run(LUNA, tmp_path_factory)["folder"]
    folder = tmp_path / "copy"
    shutil.copytree(source, folder)
    (folder / "artifact.json").unlink(missing_ok=True)
    record = read(folder / "record.json")
    del record["decoding"]
    (folder / "record.json").write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ValueError) as refused:
        card_run().build_artifact(folder)
    assert "decoding" in str(refused.value)
    assert not (folder / "artifact.json").exists()


def test_the_run_wrote_the_artifact_it_builds(tmp_path_factory: pytest.TempPathFactory) -> None:
    found = clean_run(LUNA, tmp_path_factory)
    written = read(found["folder"] / "artifact.json")
    assert written["provenance"] == block_of(found)
