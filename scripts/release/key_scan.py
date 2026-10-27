"""Scan a folder for keys: key-shaped strings, and with --env any 12 characters of the key in a row.

    python -I scripts/release/key_scan.py <folder>                # key-shaped strings only
    python -I scripts/release/key_scan.py <folder> --env <.env>   # also every 12-character run

Prints file names, line numbers, the kind of hit and counts, never a matched value.  Without
--env it reads no key: a fragment of a key that is not shaped like one cannot be seen that way.
With --env it reads the one MODEL_API_KEY= line of that file and checks every file for each of
the key's 12-character runs.  Exit 1 on any hit.  Step 5 of `docs/releasing.md` runs it on the
unpacked wheel and sdist, and on the last release's, and compares the hits.
"""
import re
import sys
from pathlib import Path

SHAPES = {
    "openai or anthropic key": r"\bsk-[A-Za-z0-9_\-]{12,}",
    "hugging face token": r"\bhf_[A-Za-z0-9]{12,}",
    "github token": r"\b(?:gh[pousr]_[A-Za-z0-9]{12,}|github_pat_[A-Za-z0-9_]{12,})",
    "aws key id": r"\b(?:AKIA|ASIA)[0-9A-Z]{12,}",
    "slack token": r"\bxox[abpr]-[A-Za-z0-9\-]{12,}",
    "google key": r"\bAIza[0-9A-Za-z_\-]{12,}",
    "bearer header": r"Bearer\s+[A-Za-z0-9._\-]{12,}",
    "assigned secret": r"(?i)(?:api[_-]?key|secret|password|access[_-]?token)[\"']?\s*[:=]\s*"
                       r"[\"']?(?!\*)[A-Za-z0-9._\-]{12,}",
}
RUN = 12


def key_from(env: Path) -> str:
    for line in env.read_text().splitlines():
        if line.startswith("MODEL_API_KEY="):
            return line.split("=", 1)[1].strip().strip("\"'")
    sys.exit(f"no MODEL_API_KEY= line in {env}")


def main() -> int:
    folder = Path(sys.argv[1])
    key = key_from(Path(sys.argv[3])) if len(sys.argv) > 3 and sys.argv[2] == "--env" else None
    runs = {key[i:i + RUN] for i in range(len(key) - RUN + 1)} if key else set()
    files = sorted(p for p in folder.rglob("*") if p.is_file())
    hits = 0
    for path in files:
        text = path.read_bytes().decode("utf-8", errors="replace")
        for n, line in enumerate(text.splitlines(), start=1):
            for kind, pattern in SHAPES.items():
                if re.search(pattern, line):
                    hits += 1
                    print(f"HIT  {path.relative_to(folder)}:{n}  {kind}")
            if runs and any(run in line for run in runs):
                hits += 1
                print(f"HIT  {path.relative_to(folder)}:{n}  12 characters of the key in a row")
    form = "key-shaped strings and 12-character runs of the key" if key else "key-shaped strings"
    print(f"# {len(files)} files scanned for {form}: {hits} hits")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
