"""Determinism and the own-tools generator's hash, frozen as tests.

The invariant is O2.1 of the knobs plan (spec §5.3, §2.2): same file bytes, arm and seed, the same
task, byte for byte, across processes; the own-tools generator's hash covers its module's bytes
and the shared modules it imports; no built-in task id moves, and the built-in generator hash and
`EXPECTED_GENERATOR_HASH` are byte-identical before and after O2; O2 edits neither `surface.py`
nor `knobs.py`.  The file's digest goes into every task id, and a user never types it.

Shapes decided here
-------------------

**1. `poisson_tasks.own.generator`** holds `GENERATOR_VERSION = "own-1"`, `generate(toolset, arm,
seed, *, intents=None, flows=())`, `generator_hash()`, `hash_of(sources)` (the hash as a pure
function of a mapping from module name to bytes) and `HASHED_MODULES`, the modules whose bytes
the hash covers.  An own-tools arm is a `knobs.ArmSpec` whose `generator_version` is `"own-1"`.

**2. What the hash covers**: every `poisson_tasks` module loaded by importing the generator, the
simulator and the verdict, `surface` and `knobs` among them (with them the package's own
`__init__` and O1's modules, which are loaded too); and none of `arms` (so a knob shipping moves no
own task id), `config`, `calibration`, `export`, `runs` or `cards`, which those imports must not
load.

**3. A task's id** moves with every field of the task and so with the file's digest, the arm, the
seed, the split and the generator's hash.  The task carries `file_digest`, `generator_hash`,
`arm_id`, `seed`, `split`, `set_name` and `source_format`.
"""

from __future__ import annotations

import dataclasses
import importlib
import json
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any

import pytest

from poisson_tasks import own
from tests.o1_support import fixture
from tests.o2_support import REPO, acme, acme_flows, arm, every_arm, generator

SOURCE = REPO / "src" / "poisson_tasks"
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def as_json(bundle: Any) -> str:
    return json.dumps(dataclasses.asdict(bundle), sort_keys=True, default=list)


def fresh(code: str, *, seed: str) -> str:
    done = subprocess.run([sys.executable, "-c", textwrap.dedent(code)], capture_output=True, text=True,
                          check=True, cwd=REPO, env={**os.environ, "PYTHONHASHSEED": seed})
    return done.stdout


def test_the_same_bytes_arm_and_seed_make_the_same_task_in_every_process() -> None:
    code = """
        import dataclasses, json
        from poisson_tasks import own
        from poisson_tasks.arms import arm_from_id
        from poisson_tasks.own import generator
        from tests.o2_support import acme, acme_flows, every_arm
        out = []
        for shape in ("mcp", "openai", "openapi-3.1"):
            toolset = acme(shape)
            flows = acme_flows("openai" if shape == "openai" else "mcp")
            for spec in every_arm(toolset, flows):
                for seed in (0, 404):
                    bundle = generator.generate(toolset, spec, seed, flows=flows)
                    out.append(json.dumps(dataclasses.asdict(bundle), sort_keys=True, default=list))
        print("\\n".join(out))
    """
    first = fresh(code, seed="0")
    second = fresh(code, seed="4242")
    assert first == second and first.count("\n") > 40
    here = []
    for shape in ("mcp", "openai", "openapi-3.1"):
        toolset = acme(shape)
        flows = acme_flows("openai" if shape == "openai" else "mcp")
        for spec in every_arm(toolset, flows):
            for seed in (0, 404):
                here.append(as_json(generator().generate(toolset, spec, seed, flows=flows)))
    assert first == "\n".join(here) + "\n"


def test_the_label_is_own_1_and_an_arm_at_another_version_is_refused() -> None:
    assert generator().GENERATOR_VERSION == "own-1"
    spec = dataclasses.replace(arm("faults", 1), generator_version="1")
    with pytest.raises(ValueError):
        generator().generate(acme(), spec, 7)


def test_the_hash_is_a_function_of_the_hashed_modules_bytes() -> None:
    gen = generator()
    names = tuple(gen.HASHED_MODULES)
    sources = {name: Path(importlib.import_module(name).__file__ or "").read_bytes() for name in names}
    found = gen.generator_hash()
    assert HEX64.match(found)
    assert gen.hash_of(sources) == found
    for name in names:
        moved = dict(sources)
        moved[name] = sources[name] + b"\n# one more line\n"
        assert gen.hash_of(moved) != found, name
    assert gen.hash_of(dict(reversed(list(sources.items())))) == found


def test_the_hash_covers_every_module_the_generator_imports_and_none_that_moves_no_task() -> None:
    code = """
        import sys
        import poisson_tasks.own.generator, poisson_tasks.own.simulator, poisson_tasks.own.verdict
        print("\\n".join(sorted(name for name in sys.modules
                                if name.split(".")[0] == "poisson_tasks"
                                and getattr(sys.modules[name], "__file__", None))))
    """
    loaded = set(fresh(code, seed="0").split())
    hashed = set(generator().HASHED_MODULES)
    assert loaded <= hashed, sorted(loaded - hashed)
    assert {"poisson_tasks.surface", "poisson_tasks.knobs", "poisson_tasks.own.generator",
            "poisson_tasks.own.simulator", "poisson_tasks.own.verdict"} <= hashed
    for name in ("poisson_tasks.arms", "poisson_tasks.config", "poisson_tasks.calibration",
                 "poisson_tasks.export", "poisson_tasks.runs", "poisson_tasks.cards"):
        assert name not in loaded and name not in hashed, name


def test_every_task_carries_the_hash_its_digest_and_its_arm() -> None:
    toolset = acme()
    gen = generator()
    found = gen.generator_hash()
    bundle = gen.generate(toolset, arm("faults", 1), 7)
    assert bundle.generator_hash == found
    assert HEX64.match(bundle.task_id)
    assert bundle.file_digest == toolset.file_digest
    assert (bundle.arm_id, bundle.seed, bundle.split) == ("faults:f1", 7, "eval")
    assert (bundle.set_name, bundle.source_format) == ("acme-support", "mcp")


def test_the_task_id_moves_with_the_file_digest_the_arm_the_seed_and_the_split() -> None:
    gen = generator()
    data = fixture("acme-mcp-tools-list.json")
    toolset = own.read_tools(data, name="acme").toolset
    respaced = own.read_tools(data + b"\n", name="acme").toolset
    assert respaced.tools == toolset.tools and respaced.file_digest != toolset.file_digest
    base = gen.generate(toolset, arm("faults", 1), 7)
    assert gen.generate(toolset, arm("faults", 1), 7).task_id == base.task_id
    others = {
        "digest": gen.generate(respaced, arm("faults", 1), 7),
        "level": gen.generate(toolset, arm("faults", 2), 7),
        "knob": gen.generate(toolset, arm("similarity", 1), 7),
        "seed": gen.generate(toolset, arm("faults", 1), 8),
        "split": gen.generate(toolset, arm("faults", 1, split="train"), 7),
        "strictness": gen.generate(toolset, arm("faults", 1, strictness="leaky"), 7),
    }
    for what, other in others.items():
        assert other.task_id != base.task_id, what
    assert others["digest"].file_digest == respaced.file_digest


def test_the_built_in_generator_is_untouched_by_the_own_tools_generator() -> None:
    """The frozen built-in hash, `EXPECTED_GENERATOR_HASH` and built-in tasks (a similarity arm,
    whose numbers come from `surface`'s keyed draw the own generator shares, and a distractor arm)
    made after own tasks in this process are those a fresh interpreter makes with no own task, and
    the own hash is another."""
    from poisson_tasks import calibration_run
    from poisson_tasks.arms import arm_from_id
    from poisson_tasks.tasks import generate
    from tests.test_frozen_generator import FROZEN_GENERATOR_HASH

    built_in = ("similarity:s2", "distractor:r0@k16")
    untouched = fresh(f"""
        from poisson_tasks.arms import arm_from_id
        from poisson_tasks.tasks import generate
        for each in {built_in!r}:
            print(repr(generate(arm_from_id(each), 404)))
    """, seed="0").splitlines()
    for spec in every_arm(acme(), acme_flows()):
        generator().generate(acme(), spec, 404, flows=acme_flows())
    after = [generate(arm_from_id(each), 404) for each in built_in]
    assert [repr(task) for task in after] == untouched
    assert after[0].generator_hash == FROZEN_GENERATOR_HASH == calibration_run.EXPECTED_GENERATOR_HASH
    assert generator().generator_hash() != FROZEN_GENERATOR_HASH
