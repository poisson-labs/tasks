"""The export config's arm: the readable id form, and the arms it refuses or notes, frozen as
tests.

The invariants are FD1.11 of the front door's plan and Taylor's first ruling of 2026-10-02 on it:
the arm validator refuses an unknown strictness (a misspelled `"leakey"` is silently scored as
strict today) and a level below 1, and accepts a level that is legitimate but on no published
card, such as depth 4, with a plain note that no published card covers it.

`ExportTasksetConfig.arm` stays a mapping.  An id string is turned into the six-field mapping
before the config is validated, so after validation `.arm` is the mapping, the frozen round-trip
tests and the export document's dict-form command are untouched, and both forms give the same
tasks.  Every config here is built the way `eval` builds it: its type found by the taskset id,
through the wheel's own loader.

Measured, and pinned as found
-----------------------------

**`--env.taskset.arm depth:d3` on `eval`'s command line reaches the validator.**  On the tree
FD1 started from, the wheel's parser hands the string to pydantic, which refuses it as "a valid
dictionary" (`dry_run` below, measured 2026-10-02 against verifiers 0.3.1).  With the id turned
into the mapping in the config's own before-validator, the same command resolves to the six-field
mapping.  So does a hand-written `eval` TOML whose `[env.taskset]` says `arm = "depth:d1+h8"`.

**The note is a Python `UserWarning`.**  The ruling asks for a plain note on an arm no published
card covers; through `eval` it reaches stderr as the warning line, measured.  It is pinned here
in-process: exactly one `UserWarning`, one line, naming the arm by its id, and none for an arm a
card covers.  How a command of Tasks' own prints it (a `note:` line) is FD5's.

A refusal's own words are read from pydantic's `msg` for the one error, which holds the
validator's text and not the input pydantic quotes beside it; they must be one line and name the
field refused (`strictness`, `level`).  Nothing else in them is pinned.

Read, and recorded for Taylor
-----------------------------

**"Any level below 1" is read per knob.**  Distractor level 0 is a published level (`r0`, and the
control `r0+len(r8)`), which `calibration.arm_specs()` and four frozen tests use, so it is
accepted; distractor level -1 is below 1 and refused.  Depth 0 and below are refused.

**FD0.4's message keeps its six-field example beside the new id one.**  The plan says the
message switches to the id form here, but FD0's frozen
`test_listing_a_taskset_with_no_arm_names_the_option_and_an_arm_it_accepts` reads a six-field
JSON object out of it.  So the id form is added, and pinned here as an example the option
accepts; the six-field one stays, pinned there.
"""

from __future__ import annotations

import dataclasses
import importlib
import json
import os
import re
import subprocess
import sys
import tempfile
import warnings
from pathlib import Path
from typing import Any

import pytest
import verifiers.v1 as vf

from poisson_tasks.arms import DEFAULT_GENERATOR_VERSION
from poisson_tasks.knobs import ArmSpec, arm_id

TASKSET_ID = "poisson-tasks"
SEEDS = [404, 55]
EVAL_MAIN = "import sys; from verifiers.v1.cli.eval.main import main; main(sys.argv[1:])"


def cal() -> Any:
    return importlib.import_module("poisson_tasks.calibration")


def loaders() -> Any:
    return importlib.import_module("verifiers.v1.utils.loaders")


def taskset_config(arm: Any, seeds: list[int] = SEEDS) -> Any:
    return loaders().taskset_config_type(TASKSET_ID)(id=TASKSET_ID, arm=arm, seeds=seeds)


def keys(config: Any) -> list[str]:
    return [task.key for task in loaders().load_taskset(config).load()]


def notes(arm: Any) -> tuple[Any, list[str]]:
    """The config for `arm`, and the text of every `UserWarning` validating it raised."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        config = taskset_config(arm)
    return config, [str(w.message) for w in caught if issubclass(w.category, UserWarning)]


def mapping(knob: str, level: int, control: int | None = None, *,
            strictness: str = "strict") -> dict[str, Any]:
    return dataclasses.asdict(ArmSpec(knob=knob, level=level, control=control,
                                      strictness=strictness, split="eval",
                                      generator_version=DEFAULT_GENERATOR_VERSION))


# --------------------------------------------------------------------------
# FD1.11: the id form, in Python
# --------------------------------------------------------------------------


def test_fd1_11_each_card_arm_by_its_id_loads_the_tasks_of_its_mapping() -> None:
    specs = cal().arm_specs()
    assert len(specs) == 14
    for spec in specs:
        by_id = taskset_config(arm_id(spec))
        by_mapping = taskset_config(dataclasses.asdict(spec))
        assert by_id.arm == dataclasses.asdict(spec), arm_id(spec)
        assert by_id.task.arm_id == arm_id(spec) and by_id.task.strictness == "strict"
        assert keys(by_id) == keys(by_mapping) and len(keys(by_id)) == len(SEEDS)


def test_fd1_11_an_id_config_survives_the_wire_the_env_server_reads() -> None:
    """The config crosses one process boundary, the serve pool's (`test_w1`'s round trip):
    after validation it holds the mapping, so it is a fixed point there too."""
    pool = importlib.import_module("verifiers.v1.serve.pool")
    config = vf.resolve_env_config({"taskset": {"id": TASKSET_ID, "arm": "depth:d2+h5",
                                                "seeds": SEEDS}})
    data = dict(pool.env_config_data(config))
    assert data["taskset"]["arm"] == mapping("depth", 2, 5)
    again = vf.resolve_env_config(data)
    assert dict(pool.env_config_data(again)) == data


@pytest.mark.parametrize("text", ["depth:3", "depth:d3 ", "Depth:d3", "distractor:r4@k8",
                                  "depth:d1+h1", "d3"])
def test_fd1_11_an_id_that_does_not_parse_is_refused_when_the_config_is_validated(
    text: str,
) -> None:
    with pytest.raises(ValueError):
        taskset_config(text)
    taskset_config("depth:d3")


# --------------------------------------------------------------------------
# FD1.11: the id form, on eval's command line and in a hand-written TOML
# --------------------------------------------------------------------------


def dry_run(*args: str) -> tuple[int, str, dict[str, Any] | None]:
    """`eval <args> --dry-run`: the exit code, what it printed, and the resolved config."""
    with tempfile.TemporaryDirectory() as tmp:
        done = subprocess.run(
            [sys.executable, "-c", EVAL_MAIN, *args, "--dry-run", "-o", tmp],
            cwd=tmp, capture_output=True, text=True, timeout=300, env=dict(os.environ),
        )
        files = list(Path(tmp).glob("*/configs/resolved/eval.json"))
        resolved = json.loads(files[0].read_text(encoding="utf-8")) if files else None
        return done.returncode, done.stdout + done.stderr, resolved


def test_fd1_11_eval_takes_the_id_on_its_command_line() -> None:
    code, out, resolved = dry_run(TASKSET_ID, "--env.taskset.arm", "depth:d3",
                                  "--env.taskset.seeds", "404")
    assert code == 0 and resolved is not None, out[-3000:]
    assert resolved["env"]["taskset"]["arm"] == mapping("depth", 3)
    assert resolved["env"]["taskset"]["task"]["arm_id"] == "depth:d3"


def test_fd1_11_eval_refuses_a_malformed_id_on_its_command_line() -> None:
    code, out, resolved = dry_run(TASKSET_ID, "--env.taskset.arm", "depth:3",
                                  "--env.taskset.seeds", "404")
    assert code != 0 and resolved is None, out[-3000:]


def test_fd1_11_a_hand_written_eval_toml_takes_the_id(tmp_path: Path) -> None:
    toml = tmp_path / "eval.toml"
    toml.write_text(f'[env.taskset]\nid = "{TASKSET_ID}"\narm = "depth:d1+h8"\nseeds = [404, 55]\n',
                    encoding="utf-8")
    code, out, resolved = dry_run("@", str(toml))
    assert code == 0 and resolved is not None, out[-3000:]
    assert resolved["env"]["taskset"]["arm"] == mapping("depth", 1, 8)
    assert resolved["env"]["taskset"]["seeds"] == [404, 55]


# --------------------------------------------------------------------------
# FD1.11 and FD0.4: the no-arm message gives the id form
# --------------------------------------------------------------------------


def test_fd1_11_a_run_with_no_arm_names_an_id_the_option_takes() -> None:
    with pytest.raises(ValueError) as refused:
        list(loaders().load_taskset(taskset_config({}, [404])))
    message = str(refused.value)
    ids = [word.rstrip(".,;:") for word in
           re.findall(r"--env\.taskset\.arm ['\"]?((?:depth|distractor):[^\s'\"]+)", message)]
    assert ids, message
    for text in ids:
        assert len(keys(taskset_config(text, [404]))) == 1, text


# --------------------------------------------------------------------------
# ruling 1: what the arm validator refuses
# --------------------------------------------------------------------------


def own_message(refusal: pytest.ExceptionInfo[ValueError]) -> str:
    """The validator's own words: pydantic's `msg` for the one error, which carries the
    validator's text and not the input pydantic quotes beside it."""
    errors = refusal.value.errors() if hasattr(refusal.value, "errors") else []
    assert len(errors) == 1, errors
    message = str(errors[0]["msg"])
    assert "\n" not in message, message
    return message


@pytest.mark.parametrize("strictness", ["leakey", "loose", "Strict", "STRICT", ""])
def test_ruling_1_an_unknown_strictness_is_refused(strictness: str) -> None:
    with pytest.raises(ValueError) as refusal:
        taskset_config(mapping("depth", 3, strictness=strictness))
    assert "strictness" in own_message(refusal)


@pytest.mark.parametrize("strictness", ["strict", "leaky"])
def test_ruling_1_the_two_strictnesses_are_the_control(strictness: str) -> None:
    """Whether a leaky arm also carries the note is a separate question
    (`tests/test_fd1_export_arm_note_wider.py`), so only the acceptance is pinned here."""
    config, _ = notes(mapping("depth", 3, strictness=strictness))
    assert config.arm["strictness"] == strictness
    assert len(keys(config)) == len(SEEDS)


@pytest.mark.parametrize("arm", [
    mapping("depth", 0), mapping("depth", -2), "depth:d0", mapping("distractor", -1),
    mapping("depth", 0, 8),
])
def test_ruling_1_a_level_below_1_is_refused(arm: Any) -> None:
    with pytest.raises(ValueError) as refusal:
        taskset_config(arm)
    assert "level" in own_message(refusal)


@pytest.mark.parametrize("arm", [
    mapping("depth", 1), "depth:d1", mapping("distractor", 0), "distractor:r0@k16",
    mapping("distractor", 0, 8), mapping("depth", 1, 8),
])
def test_ruling_1_the_lowest_published_levels_are_the_control(arm: Any) -> None:
    """Distractor level 0 is published, so `below 1` stops at depth's lowest and distractor's."""
    config, said = notes(arm)
    assert config.arm["level"] in (0, 1) and said == []


@pytest.mark.parametrize(("arm", "named"), [
    (mapping("depth", 4), "depth:d4"),
    ("depth:d4", "depth:d4"),
    (mapping("depth", 6), "depth:d6"),
    (mapping("distractor", 3), "distractor:r3@k16"),
    (mapping("depth", 1, 5), "depth:d1+h5"),
    (mapping("distractor", 0, 14), "distractor:r0+len(r14)@k16"),
    (mapping("depth", 4, strictness="leaky"), "depth:d4"),
])
def test_ruling_1_an_arm_no_card_covers_is_taken_with_one_plain_note(arm: Any, named: str) -> None:
    config, said = notes(arm)
    assert arm_id(ArmSpec(**config.arm)) == named
    assert len(said) == 1, said
    assert named in said[0] and "\n" not in said[0], said[0]
    assert len(keys(config)) == len(SEEDS)


def test_ruling_1_every_arm_a_card_covers_is_taken_with_no_note() -> None:
    for spec in cal().arm_specs():
        for arm in (dataclasses.asdict(spec), arm_id(spec)):
            config, said = notes(arm)
            assert said == [], (arm, said)
            assert config.arm == dataclasses.asdict(spec)
