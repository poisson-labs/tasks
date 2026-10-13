"""Run the command once in a fresh interpreter, for FD5's tests: `python -P tests/fd5_child.py JOB`.

The job is JSON: `argv` and `prog`, passed to `poisson_tasks.cli.main`; `record`, the file this
writes when it ends; and, when the test sets them:
- `serve_tokenizer`: a path whose bytes `tiktoken.load.read_file` returns in place of the network,
  so a fetch of the tokenizer file is made without leaving the machine; each URL asked for is
  recorded;
- `watchdog_seconds`: the run's start-up watchdog, forced on every `runs.run_plan` call;
- `package_must_be`: a folder the imported `poisson_tasks` must come from (a copy on the path).

Before anything is imported it installs an audit hook that records every socket event and refuses
any connection or name lookup that is not on this machine.  The record holds those events, every
module imported by the end, the URLs fetched, and how the command ended.  SIGINT is Python's
default here: a process started from a background job inherits it ignored, and these tests send
it.  Stdout, stderr and stdin are the process's own: the test reads them as a user would.
"""

from __future__ import annotations

import ipaddress
import json
import signal
import socket
import sys
from pathlib import Path
from typing import Any

EVENTS: list[list[Any]] = []
FETCHED: list[str] = []


def _loopback(host: Any) -> bool:
    if isinstance(host, bytes):
        host = host.decode()
    if not isinstance(host, str):
        return False
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.split("%")[0]).is_loopback
    except ValueError:
        return False


def _hook(event: str, args: tuple[Any, ...]) -> None:
    if not event.startswith("socket."):
        return
    if event == "socket.getaddrinfo":
        host = args[0].decode() if isinstance(args[0], bytes) else args[0]
        EVENTS.append(["getaddrinfo", str(host)])
        if not _loopback(host):
            raise socket.gaierror(socket.EAI_NONAME, f"{host}: the test allows no network")
    elif event == "socket.connect":
        address = args[1]
        EVENTS.append(["connect", list(address) if isinstance(address, tuple) else str(address)])
        if not (isinstance(address, tuple) and _loopback(address[0])):
            raise ConnectionRefusedError(f"{address}: the test allows no network")
    else:
        EVENTS.append([event, None])


def main() -> int:
    signal.signal(signal.SIGINT, signal.default_int_handler)
    job = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    sys.addaudithook(_hook)
    outcome: dict[str, Any] = {"ended": "returned"}
    code: Any = None
    try:
        if job.get("serve_tokenizer"):
            import tiktoken.load

            served = Path(job["serve_tokenizer"]).read_bytes()

            def read_file(blobpath: str) -> bytes:
                FETCHED.append(blobpath)
                return served

            tiktoken.load.read_file = read_file
        if job.get("watchdog_seconds") is not None:
            from poisson_tasks import runs

            original = runs.run_plan
            limit = float(job["watchdog_seconds"])

            def run_plan(*args: Any, **kwargs: Any) -> Any:
                return original(*args, **{**kwargs, "watchdog_seconds": limit})

            runs.run_plan = run_plan
        import poisson_tasks

        if job.get("package_must_be"):
            where = Path(poisson_tasks.__file__ or "").resolve().parent.parent
            if where != Path(job["package_must_be"]).resolve():
                raise SystemExit(f"poisson_tasks came from {where}, not the copy")
        from poisson_tasks.cli import main as command

        code = command(list(job["argv"]), prog=job["prog"])
    except SystemExit as stop:
        outcome = {"ended": "system exit"}
        code = stop.code
    except KeyboardInterrupt:
        outcome = {"ended": "keyboard interrupt"}
        code = 130
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        record = {
            **outcome,
            "events": EVENTS,
            "fetched": FETCHED,
            "modules": sorted(name for name in sys.modules if name is not None),
        }
        Path(job["record"]).write_text(json.dumps(record), encoding="utf-8")
    if code is None:
        return 0
    if isinstance(code, int):
        return code
    print(code, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
