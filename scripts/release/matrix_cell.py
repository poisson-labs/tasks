"""One cell of the install matrix: an installed release, driven offline (step 11 of docs/releasing.md, through
run_cells_pypi.py).

    python -I scripts/release/matrix_cell.py --venv VENV --label LABEL --work WORK --fixtures REPO --tokenizer FILE \\
        --expect-version VERSION

A clean environment, proxies at a dead loopback port, uv offline, a temporary HOME and project folder, every command
run twice, piped (the plain look) and on a pseudo-terminal (the pretty look). No model is called: nothing here reaches
a model, and the dead proxies would refuse it. The tokenizer file is placed by hand, as `fetch_encoding` would leave it,
because the network is off.  Every command is run, the own-tools path from the docs against the repo's own-tools
fixture files, and `--help` and a bare `doctor` before the tokenizer file is in place (what a first-time user sees).
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
ap.add_argument("--fixtures", required=True, help="a checkout holding tests/fixtures/o1/")
ap.add_argument("--tokenizer", required=True)
ap.add_argument("--expect-version", required=True)
ap.add_argument("--shim", default="", help="a console script outside the venv (pipx's bin folder)")
args = ap.parse_args()

VENV, WORK = Path(args.venv).resolve(), Path(args.work).resolve()
FIX = Path(args.fixtures).resolve() / "tests/fixtures/o1"
TOKENIZER = Path(args.tokenizer)
DEAD = "http://127.0.0.1:1"
UV = shutil.which("uv") or ""
UV_CACHE = subprocess.run(["uv", "cache", "dir"], capture_output=True, text=True, check=True).stdout.strip()
ESCAPE = re.compile(r"\x1b(?:\[[0-9;?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\)|[@-Z\\-_])")
results: list[dict[str, object]] = []
KEY_SET = False


def say(text: str = "") -> None:
    print(text, flush=True)


def check(ok: bool, what: str) -> None:
    say(f"  {'ok  ' if ok else 'FAIL'} {what}")
    results.append({"check": what, "ok": bool(ok)})


def env_for(home: Path, *, pretty: bool) -> dict[str, str]:
    base = {k: v for k, v in os.environ.items()
            if not any(w in k.upper() for w in ("API_KEY", "TOKEN", "SECRET"))
            and k not in ("OPENAI_BASE_URL", "PYTHONPATH", "CI", "NO_COLOR", "FORCE_COLOR", "VIRTUAL_ENV",
                          "PYTHONHOME", "PYTHONSTARTUP")}
    base.update({
        "HTTP_PROXY": DEAD, "HTTPS_PROXY": DEAD, "ALL_PROXY": DEAD, "http_proxy": DEAD, "https_proxy": DEAD,
        "all_proxy": DEAD, "NO_PROXY": "127.0.0.1,localhost", "UV_OFFLINE": "1", "UV_NO_MODIFY_PATH": "1",
        "UV_CACHE_DIR": UV_CACHE, "UV_PYTHON_PREFERENCE": "only-system", "UV_PYTHON_DOWNLOADS": "never",
        "PYTHONUNBUFFERED": "1", "COLUMNS": "100", "HOME": str(home), "TMPDIR": str(home / "tmp"),
        "PATH": f"{VENV}/bin:{home}/.local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
    })
    if KEY_SET:
        base["OPENAI_API_KEY"] = "sk-made-up-for-the-wheel-check"
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


def both(home: Path, cwd: Path, argv: list[str], *, expect: int | None = 0, show: bool = False,
         drew: bool = True) -> tuple[int, str, str]:
    """Run once piped and once on a terminal; return the piped (code, stdout, stderr)."""
    name = " ".join(argv)
    code, out, err = piped(home, cwd, argv)
    tcode, tout, terr = on_terminal(home, cwd, argv)
    say(f"\n$ poisson-tasks {name}")
    if show:
        say("\n".join("    " + l for l in (out or err).rstrip().splitlines()[:40]))
    else:
        say(f"    plain  : exit {code}: {first(out or err)[:110]!r}")
    if expect is not None:
        check(code == expect, f"{name} (plain) exits {expect}: {first(out or err)[:90]!r}")
    else:
        say(f"    (exit {code} recorded, not asserted)")
    check(tcode == code, f"{name} (pretty) exits the same ({tcode})")
    pf = first(stripped(tout)) or first(stripped(terr))
    pl = first(out) or first(err)
    check(pf == pl, f"{name}: the same first line in both looks")
    if drew and (out.strip() or err.strip()) and argv[0] not in ("--version",):
        check("\x1b[" in tout or "\x1b[" in terr, f"{name}: the pretty look drew (escape codes on the terminal)")
    return code, out, err


# ---- the cell ---------------------------------------------------------------------------------
say(f"# cell {args.label}: {VENV}")
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

say("\n## identity: what is installed, and where it is imported from")
probe = subprocess.run(
    [str(VENV / "bin/python"), "-I", "-c",
     "import sys, importlib.metadata as m, json, poisson_tasks, poisson_tasks_own;"
     "d={'python':sys.version.split()[0],'file':poisson_tasks.__file__,'own':poisson_tasks_own.__file__,"
     "'path':[p for p in sys.path if p],'version':m.version('poisson-tasks')};"
     "d.update({n:m.version(n) for n in ('verifiers','tiktoken','rich','questionary','pyyaml')});"
     "print(json.dumps(d))"],
    cwd="/", capture_output=True, text=True, env={"PATH": "/usr/bin:/bin"})
if probe.returncode != 0:
    say(probe.stderr[-1500:])
check(probe.returncode == 0, "python -I imports poisson_tasks and poisson_tasks_own")
info = json.loads(probe.stdout) if probe.returncode == 0 else {}
say("  " + json.dumps({k: v for k, v in info.items() if k != "path"}))
pkg = Path(info.get("file", "/nonexistent"))
check("site-packages" in str(pkg) and str(VENV) in str(pkg), f"poisson_tasks is imported from the environment's site-packages: {pkg}")
REPOS = str(Path(args.fixtures).resolve().parent) + "/"   # the folder that holds the checkout and its worktrees
check(not any(p.startswith(REPOS) for p in info.get("path", [])) and not str(pkg).startswith(REPOS),
      f"no checkout under {REPOS} is on sys.path (entries: {len(info.get('path', []))})")
check(info.get("version") == args.expect_version, f"installed version is {args.expect_version} (got {info.get('version')})")
check((pkg.parent / "py.typed").is_file() and (Path(info.get("own", "/x")).parent / "py.typed").is_file(),
      "both packages carry py.typed once installed")
check(len(list((pkg.parent / "cards").glob("*/artifact.json"))) == 2, "the installed package holds both published cards")
check((pkg.parent / "knob_status.json").is_file(), "knob_status.json is installed")
check(not any((pkg.parent / "data").glob("*.tiktoken")), "no tokenizer file arrives with the install (it is fetched after)")
if args.shim:
    shim = Path(args.shim)
    r = subprocess.run([str(shim), "--version"], capture_output=True, text=True, env={"PATH": "/usr/bin:/bin", "HOME": str(home)})
    check(r.returncode == 0 and r.stdout.startswith(f"poisson-tasks {args.expect_version}"), f"the pipx shim {shim} runs --version: {r.stdout.strip()!r}")

say("\n## a first-time user, before the tokenizer file is in place (nothing fetched: the network is off)")
code, out, err = both(home, work, ["--help"], drew=False)
check("init" in out and "generate" in out and "run" in out and "card" in out and "verify" in out and "export" in out and "doctor" in out,
      "--help lists the seven verbs")
code, out, err = both(home, work, ["--version"])
check(out.startswith(f"poisson-tasks {args.expect_version} ("), f"--version starts 'poisson-tasks {args.expect_version} (': {out.strip()!r}")
code, out, err = both(home, work, ["doctor"], expect=None, show=True)
bare_doctor = (code, first(out or err))

say("\n## the tokenizer file placed by hand, as fetch_encoding would leave it")
shutil.copy2(TOKENIZER, pkg.parent / "data" / TOKENIZER.name)
code, out, err = both(home, work, ["doctor", "--offline"], expect=None, show=True)
check("package" in out and str(VENV) in out, "doctor names the package inside the environment")

say("\n## the built-in tasks, offline at $0")
KEY_SET = True
both(home, work, ["init", "--yes", "--no-check-key", "--no-fetch", "--force"], show=True)
check((work / "tasks.toml").is_file(), "init --yes wrote tasks.toml")
code, out, _ = both(home, work, ["doctor", "--offline"], show=True)
check(first(out).startswith("ok  this environment is ready"), "doctor says ready once there is a settings file")
both(home, work, ["generate", "--force"], show=True)
check((work / "tasks/depth-d1.jsonl").is_file(), "generate wrote the tasks")
both(home, work, ["export", "--to", "verifiers", "--force"], show=True)
check(len(list((work / "export").glob("eval-*.json"))) == 3, "export wrote three verifiers configs")
code, out, _ = both(home, work, ["verify", "--arm", "depth:d3", "--task", "7", "--self-check"], show=True)
check(first(out).startswith("ok  depth:d3 task 7"), "verify --self-check holds")
code, out, _ = both(home, work, ["card", "--published"], show=True)
check("gpt-5-nano" in out and "qwen3-8b" in out and first(out).startswith("ok  every published card rebuilds"),
      "card --published rebuilds both cards from the installed package")
check("not current" in out, "card --published says the cards are not current for this release")
code, out, _ = both(home, work, ["run", "--dry-run", "--offline"], show=True)
check("estimate  from the published gpt-5-nano card for this model" in out,
      "the run plan's estimate reads the published card from the installed package")
check("plan  30 episodes against gpt-5-nano-2025-08-07" in out, "the run plan is for 30 episodes against gpt-5-nano")

say("\n## your own tools, against the repo's fixture files (docs/own-tools.md's path)")
own = WORK / "own"
own.mkdir()
acme = ["--own-name", "acme", "--own-read", "get_order", "--own-read", "search_orders", "--own-read", "list_channels",
        "--own-flow", "get_order.id:refund_order.order_id"]
fixture = FIX / "acme-openai-chat.json"
both(home, own, ["init", "--yes", "--no-check-key", "--no-fetch", "--force", "--own-file", str(fixture), *acme], show=True)
check((own / "tasks.toml").is_file(), "init --own-file wrote tasks.toml")
code, out, _ = both(home, own, ["doctor", "--offline"], show=True)
check(first(out).startswith("ok  this environment is ready") and "tools" in out, "doctor reads the tools file and says ready")
code, out, _ = both(home, own, ["generate", "--force"], show=True)
check(first(out).startswith("ok  generated 20 tasks") and "acme" in out, "generate made 20 tasks on the acme tools")
check((own / "tasks/depth-d1.jsonl").is_file() and (own / "tasks/depth-d2.jsonl").is_file(), "generate wrote both own-tools arms")
code, out, _ = both(home, own, ["run", "--dry-run", "--offline"], show=True)
check(first(out).startswith("plan  20 episodes against gpt-5-nano-2025-08-07"), "the own-tools run plan is for 20 episodes")
code, out, err = both(home, own, ["verify", "--tasks", "tasks/depth-d1.jsonl", "--task", "1", "--self-check"], expect=1, show=True)
text = (err or out).strip()
check(len(text.splitlines()) == 1 and text.startswith("error: tasks/depth-d1.jsonl holds tasks on your own tools, which verify does not judge on its own yet"),
      "verify --tasks <own-tools file> refuses in the one line the README quotes")

say("\n## every fixture format, init then generate (plain only)")
for path in sorted(FIX.glob("*.json")) + sorted(FIX.glob("*.yaml")):
    sub = WORK / f"own-{path.stem}"
    sub.mkdir()
    if path.name.startswith(("acme-openai",)):
        flags = acme                                    # an OpenAI tools file has no output schema: the docs' flow holds
    elif path.name.startswith("acme-"):
        flags = acme[:acme.index("--own-flow")]         # MCP and OpenAPI files state their outputs: no flow named here
    else:
        flags = ["--own-name", path.stem.split("-")[0]]
    c1, o1, e1 = piped(home, sub, ["init", "--yes", "--no-check-key", "--no-fetch", "--force", "--own-file", str(path), *flags])
    c2, o2, e2 = piped(home, sub, ["generate", "--force"])
    say(f"  {path.name:34s} init exit {c1}, generate exit {c2}: {first(o2 or e2)[:80]!r}")
    check(c1 == 0 and c2 == 0, f"{path.name}: init --own-file and generate both exit 0")

failed = [r["check"] for r in results if not r["ok"]]
(WORK / "results.json").write_text(json.dumps({"label": args.label, "info": info, "bare_doctor": bare_doctor, "checks": results}, indent=1))
say(f"\n# {args.label}: {len(results) - len(failed)} of {len(results)} checks held")
say("ALL CHECKS HELD" if not failed else f"{len(failed)} FAILED: " + "; ".join(failed))
sys.exit(1 if failed else 0)
