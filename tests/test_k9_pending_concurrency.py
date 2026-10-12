"""Pending a yes/no: gpt-5-nano runs 128 episodes at once, and Qwen's 128 is what is recorded.

**The question.**  The spec says only "concurrency recorded".  Both published cards ran through the
calibration runner, whose limit is the eval config's `max_concurrent` (128, the wheel's default);
neither card recorded it.

**Proposed: 128 for gpt-5-nano** (the driver's default; `--concurrency` lowers it if the account's
rate limit answers 429s, which would show as instrument failures), and Qwen's run records the
runner's own limit, 128.  Each run of the driver adds its concurrency to the probe's record.
**A no** names another number; it changes how many model calls can be in flight when the cap
stops the run, and time, which decides nothing.
"""

from __future__ import annotations

from pathlib import Path


def test_gpt_5_nano_runs_128_at_once_by_default() -> None:
    from poisson_tasks import knob_probe as probe

    assert probe.CONCURRENCY == 128
    args = probe.build_parser().parse_args(["run", "--folder", "f", "--cap", "4"])
    assert args.concurrency == 128


def test_qwens_run_records_the_runners_own_limit(tmp_path: Path) -> None:
    from poisson_tasks import calibration_run as run

    ctx = run.Context(
        local=tmp_path, durable=tmp_path, port=1, mirror_interval=1.0, design="knob-probe"
    )
    assert run._concurrency(ctx, "similarity:s0") == 128
