"""Where did each installed environment's poisson-tasks, and each of its dependencies, come from?  Run after
install_from_pypi.py (step 11 of docs/releasing.md).

    python -I scripts/release/provenance_pypi.py SCRATCH WHEEL [MATRIX_DIR]

The version is read from WHEEL's name.

Per environment (SCRATCH/venvs/TAG), with python -I from /:
  * the Python and the poisson-tasks version it reports; the installer the dist-info records; whether a direct_url.json is there (an install from
    a file or URL leaves one; an install from an index, or from --find-links, does not);
  * every file of WHEEL (the wheel built for the release) against the installed file, by sha256, leaving out the three dist-info files an
    installer writes itself (RECORD, INSTALLER, REQUESTED): installers rewrite RECORD, so RECORD cannot be compared byte for byte.
Across environments: the dependency sets, compared by normalised name and version.
Every installed distribution other than poisson-tasks: does pypi.org hold that exact name and version (GET /pypi/NAME/VERSION/json is 200)?
Here PyPI is the only index, so this is a consistency check on the freezes.
And, from the pip logs, which poisson_tasks files pip fetched from files.pythonhosted.org, and that none came from TestPyPI's file host.
"""
import hashlib
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

S, WHEEL = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
VERSION = WHEEL.name.split("-")[1]
OUT = S / (sys.argv[3] if len(sys.argv) > 3 else "matrix")
SKIP = ("/RECORD", "/INSTALLER", "/REQUESTED")
norm = lambda n: re.sub(r"[-_.]+", "-", n).lower()

with zipfile.ZipFile(WHEEL) as z:
    members = {n: hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist() if not n.endswith("/") and not n.endswith(SKIP)}
print(f"wheel {WHEEL.name}  sha256 {hashlib.sha256(WHEEL.read_bytes()).hexdigest()}\ncompared file by file: {len(members)} files (RECORD, INSTALLER, REQUESTED left out)\n")

ok_all = True
freezes: dict[str, dict[str, str]] = {}
for venv in sorted((S / "venvs").iterdir()):
    tag = venv.name
    probe = subprocess.run([str(venv / "bin/python"), "-I", "-c",
                            "import sys, importlib.metadata as m, json;d=m.distribution('poisson-tasks');"
                            "print(json.dumps({'python':sys.version.split()[0],'version':d.version,'dist':str(d._path)}))"],
                           cwd="/", capture_output=True, text=True, env={"PATH": "/usr/bin:/bin"})
    if probe.returncode != 0:
        print(f"{tag:12s} FAIL: {probe.stderr[-200:]}")
        ok_all = False
        continue
    info = json.loads(probe.stdout)
    dist = Path(info["dist"])
    site = dist.parent
    installer = (dist / "INSTALLER").read_text().strip() if (dist / "INSTALLER").exists() else "(none)"
    direct = (dist / "direct_url.json").exists()
    bad = [n for n, h in members.items() if not (site / n).is_file() or hashlib.sha256((site / n).read_bytes()).hexdigest() != h]
    good = info["version"] == VERSION and not direct and not bad
    ok_all &= good
    print(f"{tag:12s} {'ok  ' if good else 'FAIL'} python {info['python']:8s} poisson-tasks {info['version']}  installer={installer:5s} "
          f"direct_url.json={'PRESENT' if direct else 'absent'}  files: {len(members) - len(bad)} of {len(members)} identical to the built wheel")
    for n in bad[:5]:
        print(f"      differs or missing: {n}")
    freezes[tag] = {norm(k): v for k, v in (l.split("==", 1) for l in (OUT / f"{tag}.freeze.txt").read_text().splitlines() if "==" in l)}

print("\n--- the dependency sets (every freeze minus poisson-tasks, by normalised name and version), against the first environment")
deps = {t: {k: v for k, v in f.items() if k != "poisson-tasks"} for t, f in freezes.items()}
ref = next(iter(deps))
for t, d in deps.items():
    diff = {k: (deps[ref].get(k), d.get(k)) for k in set(deps[ref]) | set(d) if deps[ref].get(k) != d.get(k)}
    print(f"  {t:12s} {len(d)} dependencies; vs {ref}: {'identical' if not diff else str(len(diff)) + ' differ: ' + ', '.join(f'{k} {a} vs {b}' for k, (a, b) in sorted(diff.items()))}")

print("\n--- does pypi.org hold every installed dependency at its installed version?")
pairs = sorted({(k, v) for d in deps.values() for k, v in d.items()})


def on_pypi(pair: tuple[str, str]) -> tuple[str, str, int]:
    name, version = pair
    try:
        with urllib.request.urlopen(f"https://pypi.org/pypi/{name}/{version}/json", timeout=60) as r:
            return name, version, r.status
    except urllib.error.HTTPError as e:
        return name, version, e.code
    except Exception:
        return name, version, 0


with ThreadPoolExecutor(max_workers=12) as pool:
    answers = list(pool.map(on_pypi, pairs))
missing = [(n, v, c) for n, v, c in answers if c != 200]
print(f"  {len(pairs) - len(missing)} of {len(pairs)} distinct (name, version) pairs are on PyPI" + ("" if not missing else "; NOT on PyPI: " + str(missing)))
ok_all &= not missing

print("\n--- what each pip log says it downloaded for poisson-tasks, and whether anything came from TestPyPI's file host")
for log in sorted(OUT.glob("*-pip.install.log")):
    text = log.read_text(errors="replace")
    mine = sorted(set(re.findall(r"https://files\.pythonhosted\.org/\S+/(poisson_tasks[^/\s#]*)", text)))
    test = sorted(set(re.findall(r"https://test-files\.pythonhosted\.org/\S+/([^/\s#]+)", text)))
    print(f"  {log.name}: poisson_tasks files from files.pythonhosted.org: {mine or 'none'}; from test-files.pythonhosted.org: {test or 'none'}")
    # pip -v prints the .whl.metadata URL, not the wheel's own; the file comparison above is the stronger proof, so the log
    # only has to name this wheel on files.pythonhosted.org and nothing else
    ok_all &= bool(mine) and all(n.startswith(WHEEL.name) for n in mine) and not test

print("\nALL PROVENANCE CHECKS HELD" if ok_all else "\nA PROVENANCE CHECK FAILED")
sys.exit(0 if ok_all else 1)
