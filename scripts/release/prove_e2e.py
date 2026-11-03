#!/usr/bin/env python3
"""The Prove route, end to end, from two published packages and no local Prove.

    python scripts/release/prove_e2e.py --wheel dist/poisson_tasks-X.Y.Z-py3-none-any.whl \\
        --work SCRATCH [--example examples/prove_sweep/run.py] [--tokenizer FILE] \\
        [--prove-version X.Y.Z] [--python PYTHON] [--pip-cache DIR]

It takes the wheel built from the tree, makes a fresh virtual environment in `--work`, and
installs the wheel with its `prove` extra, so that `poisson-prove` resolves from PyPI and from
nowhere else.  It then runs the route `docs/prove.md` documents -- the example, which runs three
real `poisson-prove sweep` processes on the built-in tasks driven by the scripted reference
policy, and a `diff` -- reads the stored episodes back, runs the real `poisson-prove` command on
the files the example wrote, and finally uninstalls Prove and checks that Tasks still imports and
that the adapter is refused with the extra's name.

**No local Prove, anywhere.**  Every child runs with a scrubbed environment: no `PYTHONPATH`,
`VIRTUAL_ENV` or `PIP_*` setting the caller had, pip pointed at pypi.org, a home of its own, and
the new environment's `bin/` first on `PATH`.  The script then checks, and prints, that
`poisson_tasks` and `poisson_prove` are both imported from that environment, that Prove has no
`direct_url.json` (so it was not installed from a path, a checkout or an editable link), and that
the `poisson-prove` the shell finds is the environment's.

`--prove-version` adds `poisson-prove==X` to the install beside the extra, which is how the
floor of the extra's range is measured: the same check against each published version.

Output is one line per check, `ok   <what>` or `FAIL <what>`, and a last line `PROVE E2E OK:
poisson-tasks A + poisson-prove B` or `PROVE E2E FAILED: n of m checks`.  Exit 0 when every check
held, 1 when one did not, 2 when the arguments name something that is not there.  It needs the
network (PyPI) and writes only under `--work`.  It uses the standard library only, so it runs from
any Python 3.11 or later, `python -I` included.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ARMS = {"depth:d1": 2.0, "depth:d3": 4.0, "depth:d1+h3": 2.0}
"""The example's three arms and the turns the reference policy takes on each."""

SALT = "0123456789abcdef"
MAX_MDE = "0.99"
"""What the example uses: a made-up run salt, and a loose bound on the design's power, because
the run is about the plumbing and its outcome is known in advance."""

REFUSAL = 'pip install "poisson-tasks[prove]"'

failures: list[str] = []
total = 0


def check(ok: bool, what: str, detail: str = "") -> bool:
    global total
    total += 1
    print(f"{'ok  ' if ok else 'FAIL'} {what}", flush=True)
    if not ok:
        failures.append(what)
        if detail:
            print("     " + detail.strip().replace("\n", "\n     "), flush=True)
    return ok


def scrubbed_env(work: Path, venv_bin: Path, cache: Path) -> dict[str, str]:
    """The environment every child gets: the caller's, less everything that could name a local
    Prove, with pip pointed at the public index."""
    drop_exact = {"PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONUSERBASE", "VIRTUAL_ENV",
                  "CONDA_PREFIX", "UV_PYTHON", "UV_INDEX_URL", "UV_EXTRA_INDEX_URL"}
    env = {k: v for k, v in os.environ.items() if k not in drop_exact and not k.startswith("PIP_")}
    home = work / "home"
    home.mkdir(parents=True, exist_ok=True)
    env.update({
        "HOME": str(home),
        "PATH": str(venv_bin) + os.pathsep + env.get("PATH", ""),
        "PIP_INDEX_URL": "https://pypi.org/simple",
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "PIP_CACHE_DIR": str(cache),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUNBUFFERED": "1",
        "NO_COLOR": "1",
    })
    return env


def run(argv: list[str], env: dict[str, str], cwd: Path, timeout: int = 1800
        ) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(argv, env=env, cwd=cwd, capture_output=True, text=True,
                              timeout=timeout, check=False)
    except FileNotFoundError as exc:
        # A command that is not there is a failed check, not a crash of the script.
        return subprocess.CompletedProcess(argv, 127, "", str(exc))


def tail(text: str, lines: int = 25) -> str:
    return "\n".join(text.strip().splitlines()[-lines:])


def probe(py: Path, env: dict[str, str], cwd: Path, code: str) -> dict[str, object]:
    """Run `code` in the new environment with `-I` and read the JSON it prints last."""
    done = run([str(py), "-I", "-c", code], env, cwd, timeout=600)
    if done.returncode != 0:
        raise RuntimeError(f"probe failed ({done.returncode}):\n{tail(done.stderr)}")
    result: dict[str, object] = json.loads(done.stdout.strip().splitlines()[-1])
    return result


FACTS = """
import importlib.metadata as m, json, pathlib, sys
import poisson_tasks, poisson_prove
def direct(name):
    return m.distribution(name).read_text("direct_url.json")
requires = [r for r in (m.requires("poisson-tasks") or []) if r.startswith("poisson-prove")]
print(json.dumps({
    "prefix": sys.prefix,
    "tasks_file": poisson_tasks.__file__,
    "prove_file": poisson_prove.__file__,
    "tasks_version": m.version("poisson-tasks"),
    "prove_version": m.version("poisson-prove"),
    "tasks_direct": direct("poisson-tasks"),
    "prove_direct": direct("poisson-prove"),
    "requires": requires,
    "encoding_path": __import__("poisson_tasks.fetch_encoding", fromlist=["x"]).ENCODING_PATH.__str__(),
}))
"""

STORE = """
import json, sys, pathlib
import pyarrow.parquet as pq
out = {}
for run in sorted(pathlib.Path(sys.argv[1]).iterdir()):
    if not run.is_dir() or run.name.startswith("."):
        continue
    rows = []
    for part in sorted((run / "episodes").glob("part-*.parquet")):
        rows.extend(pq.read_table(part).to_pylist())
    meta = [json.loads(r["meta"]) for r in rows]
    out[run.name] = {
        "n": len(rows),
        "outcomes": sorted({r["outcome"] for r in rows}),
        "t": sorted({r["t"] for r in rows}),
        "arms": sorted({m["arm_id"] for m in meta}),
        "hashes": sorted({m["generator_hash"] for m in meta}),
        "errors": [r["error"] for r in rows if r["error"]],
    }
print(json.dumps(out))
"""

REFUSED = """
import json
import poisson_tasks, poisson_tasks.tasks, poisson_tasks.cli
try:
    import poisson_tasks.adapter
except ModuleNotFoundError as exc:
    print(json.dumps({"refused": True, "message": str(exc)}))
else:
    print(json.dumps({"refused": False, "message": ""}))
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--wheel", required=True, type=Path)
    parser.add_argument("--work", required=True, type=Path)
    parser.add_argument("--example", type=Path,
                        default=Path(__file__).resolve().parents[2] / "examples" / "prove_sweep" / "run.py")
    parser.add_argument("--tokenizer", type=Path, help="the o200k_base file; fetched when not given")
    parser.add_argument("--prove-version", help="pin poisson-prove==X beside the extra")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--pip-cache", type=Path, help="a pip cache to share (default: one under --work)")
    args = parser.parse_args()

    wheel, work, example = args.wheel.resolve(), args.work.resolve(), args.example.resolve()
    for path, what in ((wheel, "wheel"), (example, "example")):
        if not path.is_file():
            print(f"no {what} at {path}", file=sys.stderr)
            return 2
    if args.tokenizer is not None and not args.tokenizer.is_file():
        print(f"no tokenizer file at {args.tokenizer}", file=sys.stderr)
        return 2
    named = re.fullmatch(r"poisson_tasks-(\S+?)-py3-none-any\.whl", wheel.name)
    if not named:
        print(f"{wheel.name} is not a poisson_tasks wheel", file=sys.stderr)
        return 2
    wheel_version = named.group(1)
    if work.exists() and any(work.iterdir()):
        print(f"{work} is not empty", file=sys.stderr)
        return 2
    work.mkdir(parents=True, exist_ok=True)

    venv = work / "venv"
    cache = (args.pip_cache or work / "pip-cache").resolve()
    env = scrubbed_env(work, venv / "bin", cache)
    cwd = work / "cwd"
    cwd.mkdir()
    py = venv / "bin" / "python"

    print(f"wheel      {wheel.name}")
    print(f"python     {args.python}")
    print(f"index      {env['PIP_INDEX_URL']}")
    made = run([args.python, "-m", "venv", str(venv)], env, cwd)
    if made.returncode != 0:
        print(made.stderr, file=sys.stderr)
        return 2
    wanted = [f"{wheel}[prove]"] + ([f"poisson-prove=={args.prove_version}"] if args.prove_version else [])
    print("install    " + " ".join(wanted), flush=True)
    installed = run([str(py), "-m", "pip", "install", *wanted], env, cwd)
    (work / "pip-install.log").write_text(installed.stdout + installed.stderr, encoding="utf-8")
    if not check(installed.returncode == 0, "the wheel installs with its prove extra from the public index",
                 tail(installed.stdout + installed.stderr)):
        print(f"PROVE E2E FAILED: {len(failures)} of {total} checks")
        return 1
    frozen = run([str(py), "-m", "pip", "freeze"], env, cwd).stdout
    (work / "freeze.txt").write_text(frozen, encoding="utf-8")
    for line in frozen.splitlines():
        if re.match(r"(poisson|verifiers|numpy|pandas|pyarrow|scipy|rich|textual)", line, re.I):
            print(f"     {line}")

    try:
        facts = probe(py, env, cwd, FACTS)
    except RuntimeError as exc:
        # The wheel installed, but the extra brought no Prove (the old wheels had no extra), or
        # one of the two will not import.
        check(False, "poisson_tasks and poisson_prove both import in the new environment", str(exc))
        print(f"PROVE E2E FAILED: {len(failures)} of {total} checks")
        return 1
    if args.tokenizer is not None:
        # The wheel never ships the encoding file; put it where `fetch_encoding` would.
        shutil.copy2(args.tokenizer, str(facts["encoding_path"]))
    else:
        fetched = run([str(py), "-m", "poisson_tasks.fetch_encoding"], env, cwd)
        check(fetched.returncode == 0, "the encoding file is fetched", tail(fetched.stdout + fetched.stderr))

    prefix = Path(str(facts["prefix"])).resolve()
    tasks_file, prove_file = Path(str(facts["tasks_file"])).resolve(), Path(str(facts["prove_file"])).resolve()
    check(tasks_file.is_relative_to(prefix) and "site-packages" in tasks_file.parts,
          "poisson_tasks comes from the wheel's environment", str(tasks_file))
    check(facts["tasks_direct"] is None or "editable" not in str(facts["tasks_direct"]),
          "poisson-tasks is not an editable install")
    check(facts["tasks_version"] == wheel_version, f"poisson-tasks is the wheel's version, {wheel_version}",
          str(facts["tasks_version"]))
    check(prove_file.is_relative_to(prefix) and "site-packages" in prove_file.parts
          and facts["prove_direct"] is None,
          "poisson_prove comes from the index, not a checkout", f"{prove_file} direct_url={facts['prove_direct']}")
    prove_version = str(facts["prove_version"])
    if args.prove_version:
        check(prove_version == args.prove_version, f"poisson-prove is the pinned {args.prove_version}", prove_version)
    requires = [str(r) for r in facts["requires"]]  # type: ignore[attr-defined]
    check(bool(requires) and all(re.search(r"""extra == ['"]prove['"]""", r) for r in requires),
          "the wheel asks for poisson-prove only with its prove extra", "; ".join(requires))

    found = shutil.which("poisson-prove", path=env["PATH"])
    check(found is not None and Path(found).resolve().parent == (venv / "bin").resolve(),
          "the poisson-prove the shell finds is the environment's", str(found))
    version = run(["poisson-prove", "--version"], env, cwd)
    check(version.returncode == 0 and version.stdout.startswith(f"poisson-prove {prove_version} "),
          f"the real command says poisson-prove {prove_version}", version.stdout + version.stderr)

    # The documented route: the example, from the wheel's environment, in an empty folder.
    example_store = work / "example-store"
    ran = run([str(py), str(example), "--store", str(example_store)], env, cwd, timeout=1800)
    (work / "example.log").write_text(ran.stdout + "\n--- stderr\n" + ran.stderr, encoding="utf-8")
    check(ran.returncode == 0, "the example exits 0", tail(ran.stdout + ran.stderr))
    print(tail(ran.stdout, 14))

    runs_dir = example_store / "runs"
    stored = probe(py, env, cwd, STORE.replace("sys.argv[1]", repr(str(runs_dir)))) if runs_dir.is_dir() else {}
    by_arm = {arm: v for v in stored.values() for arm in v["arms"]}  # type: ignore[attr-defined]
    check(len(stored) == 3 and set(by_arm) == set(ARMS),
          "the store holds three runs, one for each of the example's arms", f"{sorted(by_arm)}")
    check(bool(by_arm) and all(v["n"] == 8 and v["outcomes"] == ["passed"] and not v["errors"]  # type: ignore[index]
                               for v in by_arm.values()),
          "every episode of every arm passed", json.dumps(stored, indent=1)[:1500])
    check(all(by_arm.get(arm, {}).get("t") == [turns] for arm, turns in ARMS.items()),  # type: ignore[attr-defined]
          "the arms differ in turns as the policy plays them: 2 at d1, 4 at d3, 2 at the control",
          json.dumps({a: v["t"] for a, v in by_arm.items()}))  # type: ignore[index]
    check(len({h for v in stored.values() for h in v["hashes"]}) == 1,  # type: ignore[attr-defined]
          "all three arms carry the one generator hash")

    # The real command, on the files the example wrote.
    listing = run(["poisson-prove", "--store", str(runs_dir), "--plain", "runs"], env, cwd)
    check(listing.returncode == 0 and all(r in listing.stdout for r in stored) and len(stored) == 3,
          "the real command lists the runs", listing.stdout + listing.stderr)
    modules = example_store / "modules"
    spec = example_store / "sweep.toml"
    sweep_env = dict(env)
    sweep_env["PYTHONPATH"] = str(modules)  # the registry module the example wrote, and nothing else
    ids: dict[str, str] = {}
    for arm, attr in (("depth:d1", "registry:reference_depth_d1"), ("depth:d3", "registry:reference_depth_d3")):
        swept = run(["poisson-prove", "--store", str(work / "real-store"), "sweep", str(spec), "--target", attr,
                     "--max-mde", MAX_MDE, "--salt", SALT, "--yes", "--json"], sweep_env, cwd)
        try:
            document = json.loads(swept.stdout)
        except ValueError:
            document = {}
        ok = swept.returncode == 0 and isinstance(document.get("run_id"), str) and document.get("rows") == 8
        check(ok, f"the real command runs a sweep of {arm} on the built-in tasks", tail(swept.stdout + swept.stderr))
        if ok:
            ids[arm] = str(document["run_id"])
    if len(ids) == 2:
        diffed = run(["poisson-prove", "--store", str(work / "real-store"), "diff", ids["depth:d1"], ids["depth:d3"],
                      "--event", "passed"], env, cwd)
        check(diffed.returncode == 0 and re.search(r"\btruncated=0\b", diffed.stdout) is not None,
              "the real command diffs the two depths and no episode is cut short by the horizon",
              tail(diffed.stdout + diffed.stderr))

    # Without Prove, Tasks is Tasks.
    gone = run([str(py), "-m", "pip", "uninstall", "-y", "poisson-prove"], env, cwd)
    check(gone.returncode == 0, "poisson-prove uninstalls", tail(gone.stdout + gone.stderr))
    refusal = probe(py, env, cwd, REFUSED)
    message = str(refusal["message"])
    check(refusal["refused"] is True and REFUSAL in message and "proofload" not in message.lower(),
          "without poisson-prove the package imports and the adapter is refused naming the extra", message)

    if failures:
        print(f"PROVE E2E FAILED: {len(failures)} of {total} checks")
        return 1
    print(f"PROVE E2E OK: poisson-tasks {facts['tasks_version']} + poisson-prove {prove_version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
