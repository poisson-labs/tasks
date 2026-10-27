"""Look in unpacked artifacts for an upload token: any 12 characters of it in a row, and the `pypi-` token shape.

usage: python -I scripts/release/scan_token.py NAME ENV_FILE FOLDER [FOLDER ...]

NAME is the variable to read from ENV_FILE (PYPI_API_TOKEN for the real index, TESTPYPI_API_TOKEN for the test one).
key_scan.py knows only MODEL_API_KEY; this covers the secret the upload uses.
Reads the one NAME= line in memory.  Prints file names, line numbers and counts, never a value.
Exit 1 on any hit, 2 if the variable is missing.
"""
import re
import sys
from pathlib import Path

RUN = 12
SHAPE = re.compile(r"\bpypi-[A-Za-z0-9_\-]{12,}")

name, env = sys.argv[1], Path(sys.argv[2])
value = next((line.split("=", 1)[1].strip().strip("\"'") for line in env.read_text().splitlines()
              if line.startswith(name + "=")), None)
if not value:
    print(f"{name} not found in {env}")
    sys.exit(2)
runs = {value[i:i + RUN] for i in range(len(value) - RUN + 1)}
print(f"# {name}: present, {len(value)} characters, {len(runs)} distinct {RUN}-character runs (value not shown)")

hits = 0
for folder in map(Path, sys.argv[3:]):
    files = sorted(p for p in folder.rglob("*") if p.is_file())
    for path in files:
        text = path.read_bytes().decode("utf-8", errors="replace")
        for n, line in enumerate(text.splitlines(), start=1):
            if any(run in line for run in runs):
                hits += 1
                print(f"HIT  {folder.name}/{path.relative_to(folder)}:{n}  {RUN} characters of the token in a row")
            if SHAPE.search(line):
                hits += 1
                print(f"HIT  {folder.name}/{path.relative_to(folder)}:{n}  pypi- token shape")
    print(f"# {folder.name}: {len(files)} files scanned")
print(f"# {hits} hits")
sys.exit(1 if hits else 0)
