"""The docs' marked blocks, run from an installed wheel, page by page, each output block compared.

    python scripts/docs_blocks.py --venv VENV [--tokenizer FILE] [--out FILE] [PAGE ...]

VENV is a venv that holds the wheel built from the commit, with its dependencies; the PAGEs are
Markdown files, by default every page of the README and `docs/` that has a `docs-check: run`
block. Each page runs in a fresh folder with a fresh HOME, its blocks in file order, the markers
read as CONTRIBUTING.md gives them. A `run` block runs under bash (a `python` block under VENV's
python) and must exit 0, or the `exit=N` its marker names; a `tty` block runs on a
pseudo-terminal, typing the marker's answers; a `fixture` block runs against the repository's
fixture model (`tests/fixtures/model_server.py`), with a made-up key. An `output` block is
compared line by line with what the block before it printed to standard output, trailing spaces
ignored and a `…` matching any run of characters. The blocks marked `skip` are listed, not run.

Run it with a Python that can import this checkout's tests (the checkout's dev venv): it reads
the blocks with `tests/test_fd6_docs.py`'s own parser, the one the marker test uses. The
tokenizer file is copied into VENV's `poisson_tasks/data/` when it is not there yet, as
`docs/python.md`'s first block says the check does (by default this checkout's copy, which
`python -m poisson_tasks.fetch_encoding` puts in place). `uv` must be on the PATH, for the export
page's `uv run eval`, and that block needs PyPI.

Prints a transcript, writes it to `--out` too when given, and exits 0 only when every block held.
"""

from __future__ import annotations

import argparse
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from tests.test_fd6_docs import RUN, Block, blocks_of  # noqa: E402

ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*\x07|\r")
TOKENIZER = REPO / "src" / "poisson_tasks" / "data" / "o200k_base.tiktoken"
MADE_UP_KEY = "sk-fixture-made-up"
RUN_TIMEOUT = 1800
TTY_TIMEOUT = 900


def default_pages() -> list[Path]:
    pages = [REPO / "README.md", *sorted((REPO / "docs").glob("*.md"))]
    return [page for page in pages
            if any(RUN.match(block.marker or "") for block in blocks_of(page.read_text("utf-8")))]


def place_tokenizer(venv: Path, tokenizer: Path) -> str:
    """Where VENV imports `poisson_tasks` from, after the tokenizer file is put beside it."""
    found = subprocess.run([str(venv / "bin" / "python"), "-I", "-c",
                            "import poisson_tasks; print(poisson_tasks.__file__)"],
                           capture_output=True, text=True, check=True).stdout.strip()
    data = Path(found).parent / "data"
    if not (data / tokenizer.name).exists():
        shutil.copyfile(tokenizer, data / tokenizer.name)
    return found


def fixture_server(venv: Path, work: Path) -> tuple[subprocess.Popen[bytes], str]:
    port_file = work / ".fixture-port"
    proc = subprocess.Popen([str(venv / "bin" / "python"),
                             str(REPO / "tests" / "fixtures" / "model_server.py"),
                             "--port-file", str(port_file), "--log", str(work / ".fixture.jsonl")],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(100):
        if port_file.exists() and port_file.read_text().strip():
            return proc, f"http://127.0.0.1:{port_file.read_text().strip()}/v1"
        time.sleep(0.1)
    proc.kill()
    raise SystemExit("the fixture model did not start")


def run_tty(cmd: str, env: dict[str, str], cwd: Path, answers: list[str]) -> tuple[int, str]:
    """Run `cmd` on a pseudo-terminal, typing the next answer each time it goes quiet."""
    import pty
    import select

    pid, fd = pty.fork()
    if pid == 0:
        os.chdir(cwd)
        os.execvpe("bash", ["bash", "-c", cmd], env)
    out = b""
    pending = list(answers)
    deadline = time.monotonic() + TTY_TIMEOUT
    while time.monotonic() < deadline:
        ready, _, _ = select.select([fd], [], [], 1.5)
        if ready:
            try:
                chunk = os.read(fd, 65536)
            except OSError:
                break
            if not chunk:
                break
            out += chunk
        elif pending:
            os.write(fd, (pending.pop(0) + "\r").encode())
    else:
        os.kill(pid, 9)
    _, status = os.waitpid(pid, 0)
    os.close(fd)
    return os.waitstatus_to_exitcode(status), ANSI.sub("", out.decode("utf-8", "replace"))


def differences(expected: str, actual: str) -> list[str]:
    want = [line.rstrip() for line in expected.strip("\n").splitlines()]
    got = [line.rstrip() for line in actual.strip("\n").splitlines()]
    problems = []
    for i in range(max(len(want), len(got))):
        w = want[i] if i < len(want) else None
        g = got[i] if i < len(got) else None
        if w is None or g is None or not re.fullmatch(
                ".*".join(re.escape(part) for part in w.split("…")), g):
            problems.append(f"    line {i + 1}: expected {w!r}\n    line {i + 1}: printed  {g!r}")
    return problems


def run_page(page: Path, venv: Path, report: list[str]) -> int:
    blocks: list[Block] = blocks_of(page.read_text("utf-8"), page)
    work = Path(tempfile.mkdtemp(prefix="docs-blocks-"))
    (work / ".home").mkdir()
    (work / ".tmp").mkdir()
    uv = shutil.which("uv")
    path = [str(venv / "bin")] + ([str(Path(uv).parent)] if uv else []) + ["/usr/bin", "/bin"]
    env = {"PATH": os.pathsep.join(dict.fromkeys(path)), "HOME": str(work / ".home"),
           "TMPDIR": str(work / ".tmp"), "COLUMNS": "80",
           "LANG": "C.UTF-8" if sys.platform == "linux" else "en_US.UTF-8"}
    shown = page.relative_to(REPO) if page.is_relative_to(REPO) else page
    report.append(f"## {shown}  (folder {work})")
    failures = 0
    server: subprocess.Popen[bytes] | None = None
    base = ""
    last_out: str | None = None
    try:
        for block in blocks:
            marker = block.marker or ""
            if marker == "output":
                if last_out is None:
                    report.append(f"  output block at line {block.line}: no run before it")
                    failures += 1
                    continue
                problems = differences(block.body, last_out)
                report.append(f"  output block at line {block.line}: "
                              + ("DIFFERS" if problems else "matches"))
                report.extend(problems)
                failures += bool(problems)
                continue
            if not RUN.match(marker):
                if marker.startswith("skip"):
                    report.append(f"  line {block.line}: skipped by its marker ({marker})")
                last_out = None
                continue
            run_env = dict(env)
            if " fixture" in marker:
                if server is None:
                    server, base = fixture_server(venv, work)
                names = re.search(r'env="([^"]*)"', marker)
                for name in names.group(1).split(",") if names else []:
                    run_env[name] = {"MODEL": "fixture-reference",
                                     "MODEL_BASE_URL": base}.get(name, MADE_UP_KEY)
                run_env.update(OPENAI_BASE_URL=base, OPENAI_API_KEY=MADE_UP_KEY)
            exit_named = re.search(r"exit=(\d+)", marker)
            want = int(exit_named.group(1)) if exit_named else 0
            if block.language in ("python", "py"):
                script = work / ".tmp" / f"block-{block.line}.py"
                script.write_text(block.body + "\n")
                cmd = f"python {shlex.quote(str(script))}"
            else:
                cmd = block.body
            started = time.monotonic()
            err = ""
            if " tty" in marker:
                answers = re.search(r'answers="([^"]*)"', marker)
                code, out = run_tty(cmd, run_env, work,
                                    answers.group(1).split(",") if answers else [])
            else:
                try:
                    done = subprocess.run(["bash", "-c", cmd], cwd=work, env=run_env,
                                          stdin=subprocess.DEVNULL, capture_output=True,
                                          text=True, timeout=RUN_TIMEOUT)
                    code, out, err = done.returncode, done.stdout, done.stderr
                except subprocess.TimeoutExpired:
                    code, out, err = -9, "", f"still running after {RUN_TIMEOUT} s"
            last_out = out
            ok = code == want
            failures += not ok
            first = block.body.strip().splitlines()[0][:100]
            report.append(f"  run at line {block.line} [{marker}] {first}: exit {code} "
                          f"(want {want}) in {time.monotonic() - started:.1f}s"
                          + ("" if ok else "  <-- EXIT DIFFERS"))
            if not ok:
                report.extend("    stderr: " + line for line in err.strip().splitlines()[-6:])
                report.extend("    stdout: " + line for line in out.strip().splitlines()[-6:])
    finally:
        if server is not None:
            server.terminate()
            server.wait()
    report.append("")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--venv", type=Path, required=True,
                        help="a venv that holds the wheel built from the commit")
    parser.add_argument("--tokenizer", type=Path, default=TOKENIZER,
                        help="the tokenizer file to put in the venv when it is not there")
    parser.add_argument("--out", type=Path, help="also write the transcript here")
    parser.add_argument("pages", nargs="*", type=Path,
                        help="the pages to run (default: every page with a run block)")
    args = parser.parse_args(argv)
    venv = args.venv.resolve()
    pages = [page.resolve() for page in args.pages] or default_pages()
    report = [f"poisson_tasks from {place_tokenizer(venv, args.tokenizer)}", ""]
    failures = sum(run_page(page, venv, report) for page in pages)
    ran = sum(line.startswith("  run at line") for line in report)
    compared = sum(line.startswith("  output block at line") for line in report)
    report.append(f"{len(pages)} pages, {ran} run blocks, {compared} output blocks, "
                  f"failures: {failures}")
    if not ran:
        report.append("no run block was found, so nothing was checked")
        failures += 1
    text = "\n".join(report) + "\n"
    print(text, end="")
    if args.out:
        args.out.write_text(text)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
