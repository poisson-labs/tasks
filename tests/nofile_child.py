"""Start a run one way in a process of its own whose limit on open files the test sets first:
`python tests/nofile_child.py JOB.json`, for `tests/test_nofile.py`.

The job names the way in (`entry`), the soft limit and the hard limit to set before anything is
imported (`hard` null keeps the one inherited), the fixture model's URL, the concurrency, the
episodes, where to run, and where to write what happened:

- `library`: `runs.find_run` then `runs.run_plan`, as a script would;
- `command`: `poisson-tasks run --yes` in the working folder, which holds `tasks.toml`;
- `probe`: the knob probe's driver, `knob_probe.run_probe`, with a `.env` file that is not there;
- `cell`: `calibration.run_cell`, the calibration runner's way in.

The result holds what each way returned or raised, the soft limit seen at each finished episode
(`library`), and the limits after.  SIGINT is set back to Python's handler first, as
`tests/fd3_child.py` does.
"""

from __future__ import annotations

import json
import os
import resource
import signal
import sys
from pathlib import Path
from typing import Any

NOFILE = resource.RLIMIT_NOFILE


def _set_limits(soft: int, hard: int | None) -> None:
    inherited = resource.getrlimit(NOFILE)[1]
    hard = inherited if hard is None else hard
    resource.setrlimit(NOFILE, (min(soft, hard), hard))


def _library(job: dict[str, Any], body: dict[str, Any]) -> None:
    from tests import fd3_support

    runs = fd3_support.runs()
    plan = fd3_support.make_plan(job["base_url"], seeds=tuple(range(1, job["episodes"] + 1)))
    folder = runs.find_run(plan, Path(job["where"]))
    seen: list[int] = []
    result = runs.run_plan(
        plan, folder, caps={"spend_usd": 100.0, "tokens": None},
        concurrency=job["concurrency"],
        events=lambda _: seen.append(resource.getrlimit(NOFILE)[0]),
    )
    body.update(verdict=result.verdict, stop=result.stop_reason, run=result.episodes_run,
                owed=result.episodes_owed, soft_during=sorted(set(seen)))


def _command(job: dict[str, Any], body: dict[str, Any]) -> None:
    from poisson_tasks import cli

    os.chdir(job["where"])
    body["code"] = cli.main(["run", "--yes"], prog="poisson-tasks")


def _probe(job: dict[str, Any], body: dict[str, Any]) -> None:
    from poisson_tasks import knob_probe

    body["code"] = knob_probe.run_probe(
        Path(job["where"]), cap=1.0, concurrency=job["concurrency"],
        env_file=Path(job["where"]).parent / "no-such.env", base_url=job["base_url"],
    )


def _cell(job: dict[str, Any], body: dict[str, Any]) -> None:
    import verifiers.v1 as vf

    from tests import fd3_support

    spec = fd3_support.arms_module().arm_from_id("depth:d1", strictness="strict")
    outcome = fd3_support.calibration().run_cell(
        spec, seeds=tuple(range(1, job["episodes"] + 1)), attempts=1,
        decoding=fd3_support.DECODING, output_dir=Path(job["where"]), model="fixture-reference",
        client=vf.EvalClientConfig(base_url=job["base_url"], api_key_var=fd3_support.KEY_VAR),
    )
    body.update(run=outcome.episodes_run, owed=outcome.episodes_owed,
                stop=None if outcome.stop is None else str(outcome.stop.reason))


ENTRIES = {"library": _library, "command": _command, "probe": _probe, "cell": _cell}


def main() -> int:
    signal.signal(signal.SIGINT, signal.default_int_handler)
    job = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    _set_limits(job["soft"], job["hard"])
    body: dict[str, Any] = {"limits_before": list(resource.getrlimit(NOFILE))}
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    try:
        ENTRIES[job["entry"]](job, body)
    except Exception as error:  # noqa: BLE001 - what the way in raised is the result
        body["raised"] = [kind.__name__ for kind in type(error).__mro__]
        body["message"] = str(error)
    body["limits_after"] = list(resource.getrlimit(NOFILE))
    Path(job["result"]).write_text(json.dumps(body), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
