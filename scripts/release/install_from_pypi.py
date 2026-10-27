"""Install poisson-tasks==VERSION from PyPI into fresh environments: Python 3.11, 3.12, 3.13, each with pip, uv pip and pipx
(step 11 of docs/releasing.md).

    python -I scripts/release/install_from_pypi.py VERSION SCRATCH [TAG ...]   TAG is py311-pip, py311-uv, py311-pipx, ... (default: all nine)

PyPI is the only index, the pin is `poisson-tasks==VERSION` (PyPI also holds the 0.0.1 placeholder, so the pin matters), and nothing
is cached, so the package file is fetched from files.pythonhosted.org on every cell:
  pip   python -m venv; pip install --no-cache-dir --index-url https://pypi.org/simple/ -v poisson-tasks==VERSION
  uv    uv venv --python PY; uv pip install --no-cache --index-url https://pypi.org/simple/ -v poisson-tasks==VERSION
  pipx  pipx install --python PY --pip-args "--no-cache-dir --index-url https://pypi.org/simple/" poisson-tasks==VERSION     (the backend pipx picks is recorded)
The three Pythons are read from RELEASE_PY311, RELEASE_PY312 and RELEASE_PY313, each the path of an interpreter, and default to
python3.11, python3.12 and python3.13 on the PATH.  pipx 1.18.4 is installed into SCRATCH/pipx-venv when that is not there yet.

Per tag, in SCRATCH/$PYPI_MATRIX_DIR (default matrix): TAG.install.log (each command, then everything it printed), TAG.freeze.txt, TAG.install.json.
Environments: SCRATCH/venvs/TAG; one pipx home per Python.  The children get SIGINT back at its default (a background run starts with it ignored).
"""
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

VERSION, S = sys.argv[1], Path(sys.argv[2]).resolve()
PIN = f"poisson-tasks=={VERSION}"
PYPI = "https://pypi.org/simple/"
OUT = S / os.environ.get("PYPI_MATRIX_DIR", "matrix")
PYTHONS = {f"py31{n}": os.environ.get(f"RELEASE_PY31{n}") or shutil.which(f"python3.1{n}") or f"python3.1{n}"
           for n in (1, 2, 3)}
PIPX = S / "pipx-venv" / "bin" / "pipx"
PIPX_VERSION = "1.18.4"


def pipx_venv() -> None:
    """pipx in a venv of its own under SCRATCH, made once."""
    if PIPX.exists():
        return
    subprocess.run([sys.executable, "-m", "venv", str(PIPX.parent.parent)], check=True)
    subprocess.run([str(PIPX.parent / "pip"), "install", "-q", "--disable-pip-version-check", f"pipx=={PIPX_VERSION}"],
                   check=True)


def env_for(tag: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items()
           if k not in ("PYTHONPATH", "VIRTUAL_ENV", "PYTHONHOME", "PYTHONDONTWRITEBYTECODE")
           and not any(w in k.upper() for w in ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "TWINE"))}
    env.update({"UV_PYTHON_PREFERENCE": "only-system", "UV_PYTHON_DOWNLOADS": "never", "PIP_DISABLE_PIP_VERSION_CHECK": "1",
                "PIPX_HOME": str(S / f"pipx-home-{tag.split('-')[0]}"), "PIPX_BIN_DIR": str(S / f"pipx-bin-{tag.split('-')[0]}")})
    return env


def run(tag: str, argv: list[str], log) -> int:
    log.write(f"$ {' '.join(argv)}\n")
    log.flush()
    done = subprocess.run(argv, stdout=log, stderr=subprocess.STDOUT, env=env_for(tag), stdin=subprocess.DEVNULL,
                          preexec_fn=lambda: signal.signal(signal.SIGINT, signal.SIG_DFL))
    log.write(f"[exit {done.returncode}]\n")
    log.flush()
    return done.returncode


def one(tag: str) -> dict[str, object]:
    py_tag, how = tag.split("-")
    py = PYTHONS[py_tag]
    venv = S / "venvs" / tag
    OUT.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(venv, ignore_errors=True)
    home = S / f"pipx-home-{py_tag}"
    if how == "pipx":
        shutil.rmtree(home, ignore_errors=True)
        shutil.rmtree(S / f"pipx-bin-{py_tag}", ignore_errors=True)
    t0 = time.monotonic()
    with open(OUT / f"{tag}.install.log", "w") as log:
        log.write(f"# PyPI only; pin {PIN}; no cache\n")
        if how == "pip":
            code = run(tag, [py, "-m", "venv", str(venv)], log)
            pip = str(venv / "bin/pip")
            code = code or run(tag, [pip, "install", "--no-cache-dir", "-v", "--index-url", PYPI, PIN], log)
            tool = subprocess.run([pip, "--version"], capture_output=True, text=True).stdout.split(" from ")[0]
            freeze = [pip, "freeze"]
        elif how == "uv":
            code = run(tag, ["uv", "venv", "--python", py, str(venv)], log)
            target = ["--python", str(venv / "bin/python")]
            code = code or run(tag, ["uv", "pip", "install", *target, "--no-cache", "-v", "--index-url", PYPI, PIN], log)
            tool = subprocess.run(["uv", "--version"], capture_output=True, text=True).stdout.strip()
            freeze = ["uv", "pip", "freeze", *target]
        else:
            pipx = [str(PIPX)]
            code = run(tag, [*pipx, "install", "--python", py, "--pip-args", f"--no-cache-dir --index-url {PYPI}", PIN], log)
            env_out = subprocess.run([*pipx, "environment", "--value", "PIPX_BACKEND_SOURCE"], capture_output=True, text=True, env=env_for(tag))
            log.write(f"# pipx environment PIPX_BACKEND_SOURCE: {env_out.stdout.strip() or env_out.stderr.strip()}\n")
            tool = "pipx " + subprocess.run([*pipx, "--version"], capture_output=True, text=True).stdout.strip()
            if (home / "venvs" / "poisson-tasks").exists():
                venv.symlink_to(home / "venvs" / "poisson-tasks")
            freeze = ["uv", "pip", "freeze", "--python", str(home / "venvs/poisson-tasks/bin/python")]   # a pipx environment holds no pip
        made = Path(freeze[freeze.index("--python") + 1] if "--python" in freeze else freeze[0])
        frozen = (subprocess.run(freeze, capture_output=True, text=True, env=env_for(tag)) if made.exists()
                  else subprocess.CompletedProcess(freeze, 1, "", "no environment was created\n"))
    (OUT / f"{tag}.freeze.txt").write_text(frozen.stdout + frozen.stderr)
    info = {"tag": tag, "python": py, "how": how, "tool": tool, "pin": PIN, "exit": code,
            "seconds": round(time.monotonic() - t0, 1), "packages": len([l for l in frozen.stdout.splitlines() if "==" in l])}
    (OUT / f"{tag}.install.json").write_text(json.dumps(info, indent=1))
    print(f"{tag:12s} install exit {code}  {info['seconds']:6.1f}s  {info['packages']} packages  ({tool})", flush=True)
    return info


if __name__ == "__main__":
    tags = sys.argv[3:] or [f"{p}-{h}" for p in PYTHONS for h in ("pip", "uv", "pipx")]
    if any(t.endswith("-pipx") for t in tags):
        pipx_venv()
    with ThreadPoolExecutor(max_workers=len(tags)) as pool:
        results = list(pool.map(one, tags))
    bad = [r["tag"] for r in results if r["exit"] != 0]
    print("ALL INSTALLED" if not bad else f"INSTALL FAILED: {bad}", flush=True)
    sys.exit(1 if bad else 0)
