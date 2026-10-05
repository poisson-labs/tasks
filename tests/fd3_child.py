"""Run one plan in a process of its own, for FD3's tests: `python tests/fd3_child.py JOB.json`.

The job names the plan (`fd3_support.plan_spec`), the runs folder, the caps, the concurrency,
the watchdog's limit when the test sets one, and where to write the result.  The child finds the
run folder with `runs.find_run` and runs it with `runs.run_plan`, as `poisson-tasks run` will,
then writes the `RunResult` as JSON.  A `KeyboardInterrupt` out of `run_plan` is written as
`{"keyboard_interrupt": true}` and the child exits 130.

With `"audit_writes"` set, every path this process opens for writing, creates, renames to or
removes is appended to that file, through an audit hook installed before anything is imported
(an operation named relative to a directory's descriptor is inside a directory already recorded,
and is skipped).

SIGINT is set back to Python's default first: a process started from a background job inherits
it ignored, and these tests send it.
"""

from __future__ import annotations

import dataclasses
import json
import os
import signal
import sys
import threading
from pathlib import Path
from typing import Any


def _audit(path: str) -> None:
    flags = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC
    local = threading.local()

    def hook(event: str, args: tuple[Any, ...]) -> None:
        if getattr(local, "busy", False):
            return
        target: Any = None
        if event == "open":
            mode, flag = args[1], args[2]
            if (isinstance(mode, str) and any(c in mode for c in "wax+")) or (
                    isinstance(flag, int) and flag & flags):
                target = args[0]
        elif event in ("os.mkdir", "os.remove", "os.rmdir", "os.truncate", "os.symlink"):
            # A path relative to a directory's descriptor (`shutil.rmtree` removes that way)
            # names something inside a directory whose own creation was recorded; skipped.
            if args[-1] is None or event in ("os.truncate", "os.symlink"):
                target = args[0]
        elif event in ("os.rename", "os.link"):
            if args[-1] is None:
                target = args[1]
        if isinstance(target, (str, bytes)):
            local.busy = True
            try:
                with open(path, "a", encoding="utf-8") as record:
                    record.write(os.path.abspath(os.fsdecode(target)) + "\n")
            finally:
                local.busy = False

    sys.addaudithook(hook)


def main() -> int:
    signal.signal(signal.SIGINT, signal.default_int_handler)
    job = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    if job.get("audit_writes"):
        _audit(job["audit_writes"])
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from tests import fd3_support

    runs = fd3_support.runs()
    plan = fd3_support.plan_from_spec(job["plan"])
    folder = runs.find_run(plan, Path(job["runs_dir"]), again=bool(job.get("again", False)))
    extra = {}
    if job.get("watchdog_seconds") is not None:
        extra["watchdog_seconds"] = float(job["watchdog_seconds"])
    result_path = Path(job["result_path"])
    try:
        result = runs.run_plan(
            plan, folder, caps=job["caps"], concurrency=int(job["concurrency"]), **extra
        )
    except KeyboardInterrupt:
        result_path.write_text(json.dumps({"keyboard_interrupt": True}), encoding="utf-8")
        return 130
    body = dataclasses.asdict(result)
    body["folder"] = str(folder.path)
    result_path.write_text(json.dumps(body, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
