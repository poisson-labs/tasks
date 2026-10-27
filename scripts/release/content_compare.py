"""Compare two releases' wheel and sdist member by member, by sha256 of the bytes.

usage: python -I scripts/release/content_compare.py OLD_DIST NEW_DIST OLD_VERSION NEW_VERSION GIT_DIFF_NAMES.txt OUT.txt

OLD_DIST and NEW_DIST each hold a release's wheel and sdist.  OLD_VERSION is rewritten to NEW_VERSION in member names
for the lookup only (0.2.0 -> 0.2.1).  GIT_DIFF_NAMES.txt is `git diff --name-only <old commit> <new commit>`.  Every member that is
added, removed or differs is tagged with whether its tracked path is in the git diff between the two builds' commits.
The wheel ships the repository's `calibration/` folder as `poisson_tasks/cards/`, so that prefix maps back to
`calibration/` before the lookup.  Prints no file content.
"""
import hashlib
import sys
import tarfile
import zipfile
from pathlib import Path

old_dir, new_dir = Path(sys.argv[1]), Path(sys.argv[2])
old_v, new_v = sys.argv[3], sys.argv[4]
names_file, out = Path(sys.argv[5]), Path(sys.argv[6])
in_git = set(names_file.read_text().split())
GENERATED = ("pyproject.toml", "PKG-INFO")


def wheel_rows(path, rename):
    with zipfile.ZipFile(path) as z:
        return {(i.filename.replace(old_v, new_v) if rename else i.filename): hashlib.sha256(z.read(i.filename)).hexdigest()
                for i in z.infolist() if not i.is_dir()}


def sdist_rows(path, rename):
    with tarfile.open(path) as t:
        return {(m.name.replace(old_v, new_v) if rename else m.name): hashlib.sha256(t.extractfile(m).read()).hexdigest()
                for m in t.getmembers() if m.isfile()}


def tracked(member, kind):
    if kind == "sdist":
        return member.split("/", 1)[1] if "/" in member else member
    if member.startswith("poisson_tasks/cards/"):
        return "calibration/" + member[len("poisson_tasks/cards/"):]
    return "src/" + member if member.startswith("poisson_tasks") and ".dist-info/" not in member else member


def tag(member, kind):
    p = tracked(member, kind)
    if p in in_git:
        return "in the git diff between the builds", 0
    if p in GENERATED or p.endswith(".dist-info/METADATA") or p.endswith(".dist-info/RECORD"):
        return "generated or the version line", 0
    return "NOT in the git diff -> FINDING", 1


lines, unexplained, seen = [], 0, set()
for kind, old, new in (
    ("wheel", wheel_rows(next(old_dir.glob("*.whl")), True), wheel_rows(next(new_dir.glob("*.whl")), False)),
    ("sdist", sdist_rows(next(old_dir.glob("*.tar.gz")), True), sdist_rows(next(new_dir.glob("*.tar.gz")), False)),
):
    lines.append(f"=== {kind}: {old_v} {len(old)} members, {new_v} {len(new)}")
    for label, group in ((f"only in {new_v} (added)", sorted(set(new) - set(old))),
                         (f"only in {old_v} (removed)", sorted(set(old) - set(new))),
                         ("same name, different bytes", sorted(n for n in set(old) & set(new) if old[n] != new[n]))):
        lines.append(f"-- {label}: {len(group)}")
        for n in group:
            t, u = tag(n, kind)
            unexplained += u
            seen.add(tracked(n, kind))
            lines.append(f"   {n}   [{t}]")
    same = sum(1 for n in set(old) & set(new) if old[n] == new[n])
    lines.append(f"-- identical: {same}")
    lines.append("")
lines.append("git-diff paths that changed no member of either file (expected: paths hatch leaves out of both):")
for p in sorted(in_git - seen):
    lines.append(f"   {p}")
lines.append("")
lines.append(f"members that differ for a reason the git diff and the version line do not explain: {unexplained}")
out.write_text("\n".join(lines) + "\n")
print("\n".join(lines))
