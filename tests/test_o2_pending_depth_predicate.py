"""Pending a yes/no: an own-tools card reads depth on strict pass@1, as every other knob.

**Why it is open.**  The built-in card reads depth on leaky pass@1 (ruling 13), because every depth
level offers the whole stage ladder and a model that overshoots the goal reached it.  Own tools have
no stage past the goal, so no overshoot; what leaky accepts there is collateral, a real side effect.

**Recommendation: yes.**  Every knob on own tools, depth included, is read against its first level on
strict pass@1.  A no reads depth on leaky, as the built-in card does.
"""

from __future__ import annotations

import hashlib
import json

from poisson_tasks import calibration as cal
from tests.o2_support import card, generator

MODEL = "gpt-5-nano-2025-08-07"


def test_depth_is_read_on_strict() -> None:
    seeds = list(range(500, 520))
    prov = cal.Provenance(
        package_version="0.0.1", engine_hash="e" * 64, generator_hash=generator().generator_hash(),
        vocabulary_hash="v" * 64, verifiers_version="0.3.1", harness_id="null",
        models=[{"id": MODEL, "revision": MODEL, "endpoint_host": "h"}], decoding=dict(cal.DECODING),
        seed_list=seeds, seed_list_hash=hashlib.sha256(json.dumps(seeds).encode()).hexdigest(),
        S=20, n=1, k_values=[1], bootstrap_resamples=200, bootstrap_seed=20260922, delta_star=0.15,
        saturation_high=0.95, saturation_low=0.05, instrument_threshold=1.0, rate_read_date="2026-10-13",
        serving={MODEL: {"kind": "hosted", "endpoint_host": "h"}}, budget=dict(cal.DEFAULT_BUDGET),
    )

    def record(arm: str, seed: int, strict: bool, leaky: bool) -> cal.EpisodeRecord:
        return cal.EpisodeRecord(task_id=f"{arm}-{seed}", arm_id=arm, model=MODEL, seed=seed, attempt=0,
                                 strict=strict, leaky=leaky,
                                 label="passed" if strict else ("collateral_mutation" if leaky else "wrong_state"),
                                 turns=3, sampled_calls=2, prompt_tokens=1, cached_input_tokens=0,
                                 completion_tokens=1, reasoning_tokens=0)

    cells = {
        ("depth:d1", MODEL): [record("depth:d1", s, i < 16, True) for i, s in enumerate(seeds)],
        ("depth:d3", MODEL): [record("depth:d3", s, i < 6, i < 14) for i, s in enumerate(seeds)],
    }
    (row,) = card().against_first(cells, prov)
    delta = cal.paired_delta(cells[("depth:d3", MODEL)], cells[("depth:d1", MODEL)],
                             resamples=200, seed=20260922, predicate="strict")
    assert (row.predicate, row.delta) == ("strict", delta.point)
