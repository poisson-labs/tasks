"""The smoke for an installed version, in both looks: `poisson-tasks doctor` and `poisson-tasks generate --arm depth:d3 --show ...`
(step 11 of docs/releasing.md, through run_cells_pypi.py).

    python -I scripts/release/smoke_cell.py --venv VENV --label LABEL --work WORK --tokenizer FILE --expect-version VERSION

Same method and helpers as matrix_cell.py: a clean environment, proxies at a dead loopback port, uv offline, a temporary HOME and
project folder, no key of any kind in the environment, every command run twice, piped (the plain look) and on a pseudo-terminal (the
pretty look).  The tokenizer file is placed by hand, as in the matrix cells.

`--show` takes no value (the docs write `--show --task 7`), so `generate --arm depth:d3 --show 7` is an argparse error; both forms are
run, the documented form asserted, the other recorded.
Prints a transcript; writes WORK/results.json; exit 0 only when every check held.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import pty
import re
import select
import shutil
import struct
import subprocess
import sys
import termios
import time
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--venv", required=True)
ap.add_argument("--label", required=True)
ap.add_argument("--work", required=True)
ap.add_argument("--tokenizer", required=True)
ap.add_argument("--expect-version", required=True)
args = ap.parse_args()

VENV, WORK = Path(args.venv).resolve(), Path(args.work).resolve()
TOKENIZER = Path(args.tokenizer)
DEAD = "http://127.0.0.1:1"
UV = shutil.which("uv") or ""
UV_CACHE = subprocess.run(["uv", "cache", "dir"], capture_output=True, text=True, check=True).stdout.strip()
ESCAPE = re.compile(r"\x1b(?:\[[0-9;?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\)|[@-Z\\-_])")
results: list[dict[str, object]] = []


def say(text: str = "") -> None:
    print(text, flush=True)


def check(ok: bool, what: str) -> None:
    say(f"  {'ok  ' if ok else 'FAIL'} {what}")
    results.append({"check": what, "ok": bool(ok)})


def env_for(home: Path, *, pretty: bool) -> dict[str, str]:
    base = {k: v for k, v in os.environ.items()
            if not any(w in k.upper() for w in ("API_KEY", "TOKEN", "SECRET"))
            and k not in ("OPENAI_BASE_URL", "PYTHONPATH", "CI", "NO_COLOR", "FORCE_COLOR", "VIRTUAL_ENV", "PYTHONHOME", "PYTHONSTARTUP")}
    base.update({
        "HTTP_PROXY": DEAD, "HTTPS_PROXY": DEAD, "ALL_PROXY": DEAD, "http_proxy": DEAD, "https_proxy": DEAD, "all_proxy": DEAD,
        "NO_PROXY": "127.0.0.1,localhost", "UV_OFFLINE": "1", "UV_NO_MODIFY_PATH": "1", "UV_CACHE_DIR": UV_CACHE,
        "UV_PYTHON_PREFERENCE": "only-system", "UV_PYTHON_DOWNLOADS": "never", "PYTHONUNBUFFERED": "1", "COLUMNS": "100",
        "HOME": str(home), "TMPDIR": str(home / "tmp"), "PATH": f"{VENV}/bin:{home}/.local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
    })
    if pretty:
        base.update({"TERM": "xterm-256color", "PYTHONIOENCODING": "utf-8"})
    else:
        base.update({"NO_COLOR": "1", "TERM": "dumb"})
    return base


def piped(home: Path, cwd: Path, argv: list[str]) -> tuple[int, str, str]:
    done = subprocess.run([str(VENV / "bin/poisson-tasks"), *argv], cwd=cwd, env=env_for(home, pretty=False),
                          input=b"", capture_output=True, timeout=900)
    return done.returncode, done.stdout.decode("utf-8", "replace"), done.stderr.decode("utf-8", "replace")


def on_terminal(home: Path, cwd: Path, argv: list[str]) -> tuple[int, str, str]:
    masters, slaves = {}, {}
    for name in ("out", "err"):
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 100, 0, 0))
        masters[name], slaves[name] = master, slave
    proc = subprocess.Popen([str(VENV / "bin/poisson-tasks"), *argv], cwd=cwd, env=env_for(home, pretty=True),
                            stdin=subprocess.DEVNULL, stdout=slaves["out"], stderr=slaves["err"], start_new_session=True)
    got = {"out": b"", "err": b""}
    by_fd = {fd: n for n, fd in masters.items()}
    closed: set[int] = set()
    deadline = time.monotonic() + 900
    while time.monotonic() < deadline:
        fds = [fd for fd in by_fd if fd not in closed]
        ready, _, _ = select.select(fds, [], [], 0.25) if fds else ([], [], [])
        for fd in ready:
            try:
                chunk = os.read(fd, 65536)
            except OSError:
                chunk = b""
            if not chunk:
                closed.add(fd)
            else:
                got[by_fd[fd]] += chunk
        if not ready and proc.poll() is not None:
            break
    proc.wait(30)
    for _ in range(10):
        fds = [fd for fd in by_fd if fd not in closed]
        ready, _, _ = select.select(fds, [], [], 0.2) if fds else ([], [], [])
        if not ready:
            break
        for fd in ready:
            try:
                chunk = os.read(fd, 65536)
            except OSError:
                chunk = b""
            got[by_fd[fd]] += chunk
            if not chunk:
                closed.add(fd)
    for fd in (*slaves.values(), *masters.values()):
        os.close(fd)
    return proc.returncode, got["out"].decode("utf-8", "replace"), got["err"].decode("utf-8", "replace")


def stripped(text: str) -> str:
    return ESCAPE.sub("", text).replace("\r", "")


def first(text: str) -> str:
    return next((l.rstrip() for l in text.splitlines() if l.strip()), "")


def both(home: Path, cwd: Path, argv: list[str], *, expect: int | None) -> tuple[int, str, str, int, str, str]:
    """Run once piped and once on a terminal; return both results."""
    name = " ".join(argv)
    code, out, err = piped(home, cwd, argv)
    tcode, tout, terr = on_terminal(home, cwd, argv)
    say(f"\n$ poisson-tasks {name}")
    say("\n".join("    " + l for l in (out or err).rstrip().splitlines()[:14]))
    say(f"    plain: exit {code}   pretty: exit {tcode}")
    if expect is not None:
        check(code == expect, f"{name} (plain) exits {expect}: {first(out or err)[:90]!r}")
    else:
        say(f"    (recorded, not asserted: plain exit {code}, first line {first(out or err)[:100]!r})")
    check(tcode == code, f"{name} (pretty) exits the same ({tcode})")
    pf = first(stripped(tout)) or first(stripped(terr))
    pl = first(out) or first(err)
    check(pf == pl, f"{name}: the same first line in both looks")
    check("\x1b[" in tout or "\x1b[" in terr, f"{name}: the pretty look drew (escape codes on the terminal)")
    return code, out, err, tcode, tout, terr


say(f"# smoke {args.label}: {VENV}")
if WORK.exists():
    shutil.rmtree(WORK)
home = WORK / "home"
(home / ".local/bin").mkdir(parents=True)
(home / "tmp").mkdir()
for name in ("uv", "uvx"):
    src = Path(UV).parent / name
    if src.exists():
        (home / ".local/bin" / name).symlink_to(src)
work = WORK / "project"
work.mkdir()

probe = subprocess.run([str(VENV / "bin/python"), "-I", "-c", "import poisson_tasks;print(poisson_tasks.__file__)"],
                       cwd="/", capture_output=True, text=True, env={"PATH": "/usr/bin:/bin"})
pkg = Path(probe.stdout.strip())
check(probe.returncode == 0 and str(VENV) in str(pkg), f"poisson_tasks is imported from the environment: {pkg}")
shutil.copy2(TOKENIZER, pkg.parent / "data" / TOKENIZER.name)
say(f"\n## the tokenizer file placed by hand (sha256 {__import__('hashlib').sha256(TOKENIZER.read_bytes()).hexdigest()[:12]}), no key in the environment, network dead")

code, out, err, *_ = both(home, work, ["doctor"], expect=0)
check(first(out).startswith("ok  this environment is ready") and "tokenizer  ok" in out
      and f"poisson-tasks {args.expect_version}" in out,
      f"doctor says ready and names tokenizer ok and poisson-tasks {args.expect_version}")
code, out, err, *_ = both(home, work, ["generate", "--arm", "depth:d3", "--show", "--task", "7"], expect=0)
check(first(out).startswith("ok  depth:d3 task 7 (seed ") and "what the model is shown" in out,
      "generate --arm depth:d3 --show --task 7 prints task 7 as a model sees it")
code, out, err, *_ = both(home, work, ["generate", "--arm", "depth:d3", "--show", "7"], expect=None)
check(code == 2 and first(out or err) == "error: unrecognized arguments: 7",
      "the form --show 7 is an argparse error, exit 2 (recorded: --show takes no value)")

failed = [r["check"] for r in results if not r["ok"]]
(WORK / "results.json").write_text(json.dumps({"label": args.label, "checks": results}, indent=1))
say(f"\n# {args.label}: {len(results) - len(failed)} of {len(results)} checks held")
say("ALL CHECKS HELD" if not failed else f"{len(failed)} FAILED: " + "; ".join(failed))
sys.exit(1 if failed else 0)
