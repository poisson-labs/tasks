"""The first screen of an installed poisson-tasks: a bare `poisson-tasks` on a terminal, in both looks, and `--version`.

    python -I scripts/release/bare_first_screen.py --venv VENV --label LABEL --work WORK --expect-version VERSION [--shim PATH]

The full session is driven by drive.py (the wheel gate, step 6 of docs/releasing.md).  This one is the per-environment check
that runs in every install cell of step 11, with no tokenizer file, no key and a dead network: nothing it does needs one.

Per look (pretty: a pseudo-terminal, 100 columns; plain: the same with --plain), in a fresh empty folder and a temporary HOME:
  * `poisson-tasks` prints the load screen (`poisson labs`, `tasks`, the version), the five steps, the line that nothing
    calls a model until you say yes, and the prompt `Enter to start, or quit`;
  * `quit` ends the session: exit 0, `Left the session.`, and the folder is still empty (nothing was written);
And, once: `poisson-tasks --version` prints `poisson-tasks VERSION (verifiers 0.3.1, Python X.Y.Z)` and exits 0, and a bare
`poisson-tasks` off a terminal (stdin and stdout piped) exits 2 and starts no session.
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
ap.add_argument("--expect-version", required=True)
ap.add_argument("--shim", default="", help="the console script to run instead of VENV/bin/poisson-tasks (a pipx cell)")
args = ap.parse_args()

VENV, WORK, VERSION = Path(args.venv).resolve(), Path(args.work).resolve(), args.expect_version
BIN = args.shim or str(VENV / "bin" / "poisson-tasks")
DEAD = "http://127.0.0.1:1"
ESCAPE = re.compile(r"\x1b(?:\[[0-9;?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\)|[@-Z\\-_])")
results: list[dict[str, object]] = []


def say(text: str = "") -> None:
    print(text, flush=True)


def check(ok: bool, what: str) -> None:
    say(f"  {'ok  ' if ok else 'FAIL'} {what}")
    results.append({"check": what, "ok": bool(ok)})


def env_for(home: Path) -> dict[str, str]:
    base = {k: v for k, v in os.environ.items()
            if not any(w in k.upper() for w in ("API_KEY", "TOKEN", "SECRET"))
            and k not in ("OPENAI_BASE_URL", "PYTHONPATH", "CI", "NO_COLOR", "FORCE_COLOR", "VIRTUAL_ENV", "PYTHONHOME", "PYTHONSTARTUP")}
    base.update({"HTTP_PROXY": DEAD, "HTTPS_PROXY": DEAD, "ALL_PROXY": DEAD, "http_proxy": DEAD, "https_proxy": DEAD, "all_proxy": DEAD,
                 "NO_PROXY": "127.0.0.1,localhost", "UV_OFFLINE": "1", "UV_NO_MODIFY_PATH": "1", "HOME": str(home), "TMPDIR": str(home / "tmp"),
                 "TERM": "xterm-256color", "COLORTERM": "truecolor", "LANG": "en_US.UTF-8", "LC_ALL": "en_US.UTF-8", "PYTHONUNBUFFERED": "1",
                 "PATH": f"{VENV}/bin:/usr/bin:/bin:/usr/sbin:/sbin"})
    return base


def clean(raw: bytes) -> str:
    text = ESCAPE.sub("", raw.decode("utf-8", "replace")).replace("\r\n", "\n")
    return re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", "\n".join(line.split("\r")[-1] for line in text.split("\n")))


def on_terminal(argv: list[str], folder: Path, env: dict[str, str]) -> tuple[int | None, str, str]:
    """Run argv on a pseudo-terminal; wait for the prompt; type `quit`; wait for the exit.  Returns (exit, screen before quit, screen after)."""
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 50, 100, 0, 0))
    pid = os.fork()
    if pid == 0:
        os.setsid()
        for fd in (0, 1, 2):
            os.dup2(slave, fd)
        os.close(master)
        os.close(slave)
        os.chdir(folder)
        os.execvpe(argv[0], argv, env)
    os.close(slave)
    out, status, sent, before = b"", None, False, ""
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        ready, _, _ = select.select([master], [], [], 0.3)
        if ready:
            try:
                chunk = os.read(master, 65536)
            except OSError:
                chunk = b""
            if not chunk:
                break
            out += chunk
        elif not sent and "Enter to start, or quit" in clean(out):
            time.sleep(1.0)
            before = clean(out)
            os.write(master, b"quit\r")
            sent = True
        done, st = os.waitpid(pid, os.WNOHANG)
        if done:
            status = st
            break
    if status is None:
        # the pty hit end-of-file before the exit status was collected: give the child a moment to be reaped, then stop it
        for _ in range(100):
            done, st = os.waitpid(pid, os.WNOHANG)
            if done:
                status = st
                break
            time.sleep(0.1)
    if status is None:
        try:
            os.kill(pid, 9)
        except ProcessLookupError:
            pass
        _, st = os.waitpid(pid, 0)
        return None, before or clean(out), clean(out)
    # drain what is left
    while True:
        ready, _, _ = select.select([master], [], [], 0.2)
        if not ready:
            break
        try:
            chunk = os.read(master, 65536)
        except OSError:
            break
        if not chunk:
            break
        out += chunk
    return os.waitstatus_to_exitcode(status), before, clean(out)


if WORK.exists():
    shutil.rmtree(WORK)
WORK.mkdir(parents=True)
say(f"# {args.label}: the first screen of {BIN} (expecting {VERSION})")

home = WORK / "home-version"
(home / "tmp").mkdir(parents=True)
done = subprocess.run([BIN, "--version"], cwd=WORK, env=env_for(home), stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120)
say(f"\n$ poisson-tasks --version   [exit {done.returncode}]\n    {done.stdout.strip()}")
check(done.returncode == 0 and re.fullmatch(rf"poisson-tasks {re.escape(VERSION)} \(verifiers 0\.3\.1, Python \d+\.\d+\.\d+\)", done.stdout.strip()) is not None,
      f"--version prints `poisson-tasks {VERSION} (verifiers 0.3.1, Python X.Y.Z)` and exits 0")

folder = WORK / "project-piped"
folder.mkdir()
done = subprocess.run([BIN], cwd=folder, env=env_for(home), stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120)
say(f"\n$ poisson-tasks   (stdin and stdout piped)   [exit {done.returncode}]\n" + "\n".join("    " + l for l in (done.stdout + done.stderr).strip().splitlines()))
check(done.returncode == 2 and "Enter to start" not in done.stdout + done.stderr, "a bare poisson-tasks off a terminal exits 2 and starts no session")
check(not any(folder.iterdir()), "it wrote nothing")

for look in ("pretty", "plain"):
    home = WORK / f"home-{look}"
    (home / "tmp").mkdir(parents=True)
    folder = WORK / f"project-{look}"
    folder.mkdir()
    argv = [BIN] + (["--plain"] if look == "plain" else [])
    t0 = time.monotonic()
    code, before, after = on_terminal(argv, folder, env_for(home))
    say(f"\n$ {' '.join(['poisson-tasks'] + argv[1:])}   (on a terminal, then `quit`)   [exit {code}, {time.monotonic() - t0:.1f}s]")
    say("\n".join("    " + l.rstrip()[:118] for l in before.strip("\n").splitlines()[:22]))
    say("    ...")
    say("\n".join("    " + l.rstrip()[:118] for l in [l for l in after.splitlines() if l.strip()][-2:]))
    check("poisson labs" in before.lower() and VERSION in before, f"{look}: the load screen names Poisson Labs (the plain look capitalises it) and {VERSION}")
    check("Set up" in before and "What next" in before and "Nothing calls a model until you say yes" in before,
          f"{look}: the five steps are listed and the screen says nothing calls a model until you say yes")
    check("Enter to start, or quit" in before, f"{look}: the prompt is `Enter to start, or quit`")
    check(code == 0 and "Left the session." in after, f"{look}: `quit` leaves the session, exit 0, `Left the session.`")
    check(not any(folder.iterdir()), f"{look}: the folder is still empty (nothing was written)")

failed = [r["check"] for r in results if not r["ok"]]
(WORK / "results.json").write_text(json.dumps({"label": args.label, "version": VERSION, "checks": results}, indent=1))
say(f"\n# {args.label}: {len(results) - len(failed)} of {len(results)} checks held")
say("ALL CHECKS HELD" if not failed else f"{len(failed)} FAILED: " + "; ".join(failed))
sys.exit(1 if failed else 0)
