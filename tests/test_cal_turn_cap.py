"""An episode ends after 32 model calls: a default of the taskset, recorded on the card.

Model B's second card refused on its instrument-rate gate.  In `depth:d1+h8` and `depth:d2+h5`,
20 episodes each ran past 100 model calls (107 to 112) on tasks that need one or two.  They
ended only when the conversation filled the 16,384-token context, and the card counts a
context stop as an instrument failure.  No turn limit was set anywhere, so the run could not
end a model that does not stop in any other way.

Across all 14 arms, Qwen's ordinary episodes end within 17 model calls, and model A's longest
was 18.  Above that sit the loops: 24 or more calls, most past 100.  A cap anywhere from 24 to
50 changes 1 episode of the 900 in the three arms that loop.

So the taskset has a default of 32 model calls, four times the deepest task's minimum (8 at
`depth:d8`), pinned in the taskset's own env config beside the measured harness.  The
documented command and the calibration run then behave the same, and a flag overrides the
cap as it overrides the harness.  An episode that reaches it stops as `max_turns`, which the
verdict labels `turn_limit`: the model's own failure, not the instrument's.  The card prints
the cap, and a card from a run without one (model A's) prints nothing new and keeps its bytes.
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from poisson_tasks import calibration as cal
from tests.test_cal_qwen_prep import needs_uv

CAP = 32


def taskset() -> Any:
    import importlib

    return importlib.import_module("poisson_tasks.taskset")


def run_module() -> Any:
    import importlib

    return importlib.import_module("poisson_tasks.calibration_run")


# ---------------------------------------------------------------------------
# the default
# ---------------------------------------------------------------------------


def test_the_cap_is_four_times_the_deepest_tasks_minimum() -> None:
    deepest = max(cal._minimum_calls(cal._arm_id(spec)) for spec in cal.arm_specs())
    assert deepest == 8
    assert taskset().MAX_MODEL_CALLS == 4 * deepest == CAP


def test_the_taskset_env_pins_the_cap() -> None:
    config = taskset().PoissonTasksEnvConfig()
    assert config.agent.max_turns == CAP


# ---------------------------------------------------------------------------
# the card
# ---------------------------------------------------------------------------


def _provenance(**extra: Any) -> cal.Provenance:
    model = {"id": "m", "revision": "m", "endpoint_host": "h"}
    return cal.Provenance.for_run(models=[model], serving={"m": {"kind": "hosted",
                                  "endpoint_host": "h"}}, rate_read_date="2026-09-28", **extra)


def test_the_provenance_carries_the_cap_when_the_run_had_one() -> None:
    assert _provenance(max_model_calls=CAP).as_dict()["max_model_calls"] == CAP


def test_a_run_without_a_cap_serialises_as_before() -> None:
    """Model A's committed artifact has no such key, and must recompute byte for byte."""
    assert "max_model_calls" not in _provenance().as_dict()


def test_the_card_prints_the_cap() -> None:
    records = [
        cal.EpisodeRecord(task_id=f"t{seed}", arm_id="depth:d1", model="m", seed=seed,
                          attempt=attempt, strict=True, leaky=True, label="passed", turns=2,
                          sampled_calls=1, prompt_tokens=10, cached_input_tokens=0,
                          completion_tokens=5, reasoning_tokens=0)
        for seed in range(cal.S) for attempt in range(cal.N)
    ]
    cells = {("depth:d1", "m"): records}
    capped = cal.render_document(cal.build_artifact(
        cells, _provenance(max_model_calls=CAP), tally={key: {} for key in cells}))
    uncapped = cal.render_document(cal.build_artifact(
        cells, _provenance(), tally={key: {} for key in cells}))
    assert f"{CAP} model calls" in capped
    assert f"{CAP} model calls" not in uncapped


def test_model_b_cards_are_built_with_the_cap() -> None:
    """The driver's card records the cap the taskset imposed on the run."""
    assert run_module().CARD_MAX_MODEL_CALLS == taskset().MAX_MODEL_CALLS


def test_the_card_the_driver_writes_records_the_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`finalize`, the driver's last step, on one arm's records as a run leaves them (read
    here without a run): the artifact it writes carries the taskset's cap in its provenance,
    and the card prints it."""
    run = run_module()
    served = run.QWEN3_8B.served_name

    def arm_rows(_run_dir: Path, arm: str, _served: str) -> tuple[Any, ...]:
        rows = [
            cal.EpisodeRecord(task_id=f"t{seed}", arm_id=arm, model=served, seed=seed,
                              attempt=attempt, strict=True, leaky=True, label="passed",
                              turns=2, sampled_calls=1, prompt_tokens=10,
                              cached_input_tokens=0, completion_tokens=5, reasoning_tokens=0)
            for seed in range(cal.S) for attempt in range(cal.N)
        ]
        return rows, {}, {"episodes": len(rows), "max_prompt_tokens": 10, "context_stops": 0}

    monkeypatch.setattr(run, "_arm_rows", arm_rows)
    result = run.finalize(
        tmp_path, tmp_path / "card",
        serving={"stack_version": "0.29.0+cu129", "gpu": "NVIDIA L4", "date": "2026-09-28"},
        arms=["depth:d1"], wall_clock_hours=1.0, served=served,
    )
    assert result["cal24"] == "published", result
    stored = json.loads((tmp_path / "card" / "artifact.json").read_text())
    assert stored["provenance"]["max_model_calls"] == taskset().MAX_MODEL_CALLS == CAP
    assert f"{CAP} model calls" in (tmp_path / "card" / "card.md").read_text()


# ---------------------------------------------------------------------------
# a model that never stops, end to end
# ---------------------------------------------------------------------------


GIVE_UP = 64
"""The stand-in stops calling tools here, so a run with no cap ends (and the test fails)
instead of looping until the budget."""


class _Loop(BaseHTTPRequestHandler):
    """An OpenAI-compatible chat endpoint that answers every request with one more tool
    call, up to `GIVE_UP` calls."""

    calls = 0

    def do_POST(self) -> None:  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).calls += 1
        tool = body["tools"][0]["function"]["name"]
        message: dict[str, Any] = {
            "role": "assistant", "content": None,
            "tool_calls": [{"id": f"call_{type(self).calls}", "type": "function",
                            "function": {"name": tool, "arguments": "{}"}}],
        }
        finish = "tool_calls"
        if type(self).calls >= GIVE_UP:
            message, finish = {"role": "assistant", "content": "Done."}, "stop"
        reply = {
            "id": f"chatcmpl-{type(self).calls}", "object": "chat.completion", "created": 0,
            "model": body["model"],
            "choices": [{"index": 0, "finish_reason": finish, "message": message}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 5, "total_tokens": 105},
        }
        data = json.dumps(reply).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args: Any) -> None:
        return


@pytest.fixture
def looping_endpoint() -> Iterator[str]:
    _Loop.calls = 0
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Loop)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}/v1"
    server.shutdown()
    server.server_close()


@needs_uv
def test_a_model_that_never_stops_ends_at_the_cap_as_its_own_failure(
    looping_endpoint: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import verifiers.v1 as vf

    run = run_module()
    monkeypatch.setenv("LOOP_KEY", "EMPTY")
    spec = run.spec_for("depth:d1")
    client = vf.EvalClientConfig(base_url=looping_endpoint, api_key_var="LOOP_KEY")
    with run.design(run.Design(seeds=(404,), n=1, k_values=(1,))):
        outcome = cal.run_arm(spec, output_dir=tmp_path, model="loop", client=client)
    records = cal.records_from_run(outcome.run_dir, model="loop")
    assert len(records) == 1, records
    record = records[0]
    assert record.label not in cal.INSTRUMENT_LABELS, record
    assert record.turns == CAP, record
    assert _Loop.calls == CAP
    stops = [trace.get("stop_condition")
             for line in (outcome.run_dir / cal.TRACES_FILE).read_text().splitlines()
             for trace in json.loads(line).get("traces") or []]
    assert stops == ["max_turns"], stops
    assert os.environ.get("LOOP_KEY") == "EMPTY"
