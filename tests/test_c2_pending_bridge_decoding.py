"""Pending a decision: how many completion tokens a call of the gpt-5-nano bridge may take, and
at what read date its price is recorded.

**The question.**  Ruled 2026-11-15: all three new cards allow 8,192 completion tokens per call,
and gpt-5-nano gets "a last run of the version 2 design" as a bridge record that counts toward
nothing.  The design says the bridge runs "through the same path as the generator-0 card", whose
calls were capped at 2,048, and gives the bridge two jobs: the replication check (its depth arms
paired by seed against the generator-0 card, to tell a generator change from a model change) and
measuring the five newer dials on the knob probe's own model, whose probe also ran at 2,048.
Neither ruling says which limit the bridge runs at.

**Proposed:** 2,048, the generator-0 card's and the probe's own limit.  At 8,192 the replication
check would compare runs that differ in the generator and in the limit at once, and the bridge's
statuses would not line up with the probe's on one decoding.  The bridge's price is recorded as
its published card declares it, read on 2026-09-25, the rates the probe's cap was counted in.
**A no** runs the bridge at 8,192 like the three cards, and its replication check then says the
limit differs too.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.c2_support import NANO, bodies, card_run, drive, needs_uv, registry_cache, small_design


def test_the_bridge_row_is_the_generator_0_cards_decoding_and_price() -> None:
    from poisson_tasks import calibration as cal

    row = card_run().MODELS[NANO]
    assert dict(row.decoding) == dict(cal.DECODING)
    assert dict(row.decoding)["max_tokens"] == 2048
    assert row.price.read_on == "2026-09-25"


@needs_uv
def test_every_request_of_a_bridge_run_carries_2048(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    found: dict[str, Any] = drive(
        tmp_path_factory.mktemp("c2-bridge-limit"),
        registry_cache(tmp_path_factory),
        model=NANO,
        design=small_design(tasks=1, attempts=1, arms=("depth:d1", "landed:l0")),
    )
    assert found["code"] == 0, found["out"] + found["err"]
    sent = bodies(found)
    assert sent and {body["max_completion_tokens"] for body in sent} == {2048}
