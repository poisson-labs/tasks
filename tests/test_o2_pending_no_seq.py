"""Pending a decision: an answer on a user's own tools carries no sequence number, and a run is
replayed in the order the harness sent the calls.

**Why it is open.**  The design says "every call advances a counter, so replay orders calls exactly
as the built-in export does".  The built-in export orders a run's calls by the `seq` each engine
line opens with.  An own-tools answer is the user's response object (or the format's error), and a
counter written into it would change the shape the user's schemas give it: an `outputSchema` with
`additionalProperties: false` would no longer hold.  verifiers' `null` harness makes a turn's calls
one at a time, in the order the assistant message lists them (`harnesses/null/program.py` at 0.3.1),
so the order the harness sent them is the order the server answered them.

**Recommended.**  The answer is the object alone; the counter is the simulator's own
(`State.calls`); the replay takes the sampled calls in the order they were made.  If it is declined,
the build puts the counter in the text (a line before the object, say) and orders the replay by it,
as the built-in export does.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tests.fd3_support import arm_dir as arm_dir_name
from tests.helpers import needs_uv
from tests.o1_support import fixture
from tests.o2_support import acme, calibration, config, generator, reference_model, runs


@needs_uv
def test_calls_made_in_one_turn_replay_in_the_order_the_harness_sent_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Retrofitted 2026-10-29 for 0.3.0: the own-tools generator label moved from "own-1" to "own-2" with the ruled change to the frozen generator (the faults spec's Q4)."""
    (tmp_path / "tools.json").write_bytes(fixture("acme-mcp-tools-list.json"))
    monkeypatch.setenv("O2_API_KEY", "EMPTY")
    from poisson_tasks.arms import arm_from_id

    with reference_model() as model:
        cfg = config()
        data = (tmp_path / "tools.json").read_bytes()
        spec = arm_from_id("spread:p4", generator_version="own-2")
        plan = cfg.Plan(
            preset="custom", arms=(spec,), seeds=(404,), attempts=1,
            model=cfg.ModelConfig(provider="openai-compatible", name="scripted", base_url=model.base_url,
                                  api_key_env="O2_API_KEY"),
            decoding={"temperature": 1.0, "top_p": 1.0, "reasoning_effort": "low", "max_tokens": 2048},
            max_model_calls=32,
            own={"file": str(tmp_path / "tools.json"), "format": "auto", "name": "tools", "read": [],
                 "write": [], "intents": {}, "flows": [], "file_digest": hashlib.sha256(data).hexdigest(),
                 "source_format": "mcp", "tools": 5},
        )
        bundle = generator().generate(acme("mcp", name="tools"), spec, plan.seeds[0])
        reads = [(n, json.dumps(a)) for n, a in bundle.reference_calls[:4]]
        last = [(n, json.dumps(a)) for n, a in bundle.reference_calls[4:]]
        model.script[bundle.request] = [reads, *[[call] for call in last]]
        folder = runs().find_run(plan, tmp_path / "runs")
        runs().run_plan(plan, folder, caps={"spend_usd": None, "tokens": 100000}, concurrency=1,
                        watchdog_seconds=300)
    (record,) = calibration().records_from_run(Path(folder.path) / arm_dir_name(spec), model="scripted")
    assert (record.label, record.strict, record.turns) == ("passed", True, 1 + len(last) + 1)
