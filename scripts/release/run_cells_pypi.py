"""Run the three stages in each environment installed from PyPI, all nine in parallel, each environment's stages one after the other
(step 11 of docs/releasing.md; run after install_from_pypi.py).

    python -I scripts/release/run_cells_pypi.py VERSION SCRATCH [TAG ...]

Per environment TAG (SCRATCH/venvs/TAG):
  1. matrix_cell.py        (offline, both looks, every command), --expect-version VERSION
  2. bare_first_screen.py  (the guided session's first screen, both looks, --version, the off-terminal exit 2)
  3. smoke_cell.py         (doctor and generate --arm depth:d3 --show, both looks)
The tokenizer file is placed by hand for stages 1 and 3 (the network is off): it is read from RELEASE_TOKENIZER, by default
src/poisson_tasks/data/o200k_base.tiktoken in this checkout.  The fixtures are this checkout's tests/fixtures/.  Transcripts:
SCRATCH/matrix/TAG.matrix_cell.txt, TAG.first_screen.txt, TAG.smoke.txt; exit codes in SCRATCH/matrix/cells.status.  No model is
called: nothing in a stage can reach one (dead proxies, uv offline, a made-up key, the fixture on loopback).  A pipx cell also gets
--shim (the console script in that Python's PIPX_BIN_DIR).
"""
import os
import signal
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

VERSION, S = sys.argv[1], Path(sys.argv[2]).resolve()
SCRIPTS = Path(__file__).resolve().parent
MATRIX_CELL = SCRIPTS / "matrix_cell.py"
BARE = SCRIPTS / "bare_first_screen.py"
SMOKE = SCRIPTS / "smoke_cell.py"
REPO = SCRIPTS.parents[1]      # holds tests/fixtures/o1/ and tests/fixtures/model_server.py
TOKENIZER = Path(os.environ.get("RELEASE_TOKENIZER") or REPO / "src/poisson_tasks/data/o200k_base.tiktoken")
OUT = S / "matrix"


def stage(argv: list[str], transcript: Path) -> int:
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "VIRTUAL_ENV", "PYTHONHOME", "PYTHONDONTWRITEBYTECODE")
           and not any(w in k.upper() for w in ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "TWINE"))}
    with open(transcript, "w") as fh:
        done = subprocess.run(argv, stdout=fh, stderr=subprocess.STDOUT, env=env, stdin=subprocess.DEVNULL,
                              preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_DFL))
    return done.returncode


def cell(tag: str) -> tuple[str, list[int]]:
    py_tag, how = tag.split("-")
    venv = S / "venvs" / tag
    shim = ["--shim", str(S / f"pipx-bin-{py_tag}" / "poisson-tasks")] if how == "pipx" else []
    codes = [
        stage([sys.executable, "-I", str(MATRIX_CELL), "--venv", str(venv), "--label", tag, "--work", str(S / "work" / tag / "cell"),
               "--fixtures", str(REPO), "--tokenizer", str(TOKENIZER), "--expect-version", VERSION, *shim], OUT / f"{tag}.matrix_cell.txt"),
        stage([sys.executable, "-I", str(BARE), "--venv", str(venv), "--label", tag, "--work", str(S / "work" / tag / "bare"),
               "--expect-version", VERSION, *shim], OUT / f"{tag}.first_screen.txt"),
        stage([sys.executable, "-I", str(SMOKE), "--venv", str(venv), "--label", tag, "--work", str(S / "work" / tag / "smoke"),
               "--tokenizer", str(TOKENIZER), "--expect-version", VERSION], OUT / f"{tag}.smoke.txt"),
    ]
    line = f"{tag:12s} matrix_cell exit {codes[0]}   first_screen exit {codes[1]}   smoke exit {codes[2]}"
    with open(OUT / "cells.status", "a") as fh:
        fh.write(line + "\n")
    print(line, flush=True)
    return tag, codes


if __name__ == "__main__":
    tags = sys.argv[3:] or [f"{p}-{h}" for p in ("py311", "py312", "py313") for h in ("pip", "uv", "pipx")]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "cells.status").unlink(missing_ok=True)
    with ThreadPoolExecutor(max_workers=len(tags)) as pool:
        results = list(pool.map(cell, tags))
    bad = [t for t, c in results if any(c)]
    print("ALL STAGES EXITED 0" if not bad else f"NONZERO EXIT IN: {bad}", flush=True)
    sys.exit(1 if bad else 0)
