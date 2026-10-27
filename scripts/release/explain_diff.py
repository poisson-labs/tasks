"""Explain every path that differs between two commits: is it comments/docstrings only, or did the code change?

usage: python -I scripts/release/explain_diff.py REPO OLD_REV NEW_REV BASE_REV OLD_TIP NAMES.txt OUT.txt

For each path in NAMES.txt (git diff --name-only OLD_REV NEW_REV):
  * a .py file is parsed at both revisions with every bare-string statement (docstrings, string-only statements)
    removed; if the two ASTs are equal the change is "comments/docstrings/layout only", else "code changed";
  * any other file is "non-code" (docs, changelog, config);
  * a path missing at OLD_REV is "added".
Then, for the "code changed", "non-code" and "added" paths, it names the first-parent commits between BASE_REV and
OLD_TIP that touched the path.  For a release BASE_REV is OLD_REV and OLD_TIP is NEW_REV (they differ only for a
rewritten history, where OLD_TIP is the old tip whose tree equals NEW_REV's).  Prints paths and counts, no file content.
"""
import ast
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

repo, old_rev, new_rev, base_rev, old_tip = sys.argv[1:6]
names = Path(sys.argv[6]).read_text().split()
out = Path(sys.argv[7])


def show(rev, path):
    r = subprocess.run(["git", "-C", repo, "show", f"{rev}:{path}"], capture_output=True)
    return r.stdout if r.returncode == 0 else None


class Strip(ast.NodeTransformer):
    def visit_Expr(self, node):
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            return None
        return self.generic_visit(node)


def dump(src):
    return ast.dump(Strip().visit(ast.parse(src)))


def merges(path):
    r = subprocess.run(["git", "-C", repo, "log", "--first-parent", "--format=%h %s", f"{base_rev}..{old_tip}", "--", path],
                       capture_output=True, text=True)
    return [line.split(" ", 1) for line in r.stdout.splitlines()]


kind = {}
for p in names:
    old, new = show(old_rev, p), show(new_rev, p)
    if old is None:
        kind[p] = "added"
    elif new is None:
        kind[p] = "removed"
    elif not p.endswith(".py"):
        kind[p] = "non-code"
    else:
        try:
            kind[p] = "comments/docstrings only" if dump(old) == dump(new) else "code changed"
        except SyntaxError:
            kind[p] = "UNPARSEABLE"

lines = []
count = Counter(kind.values())
lines.append("counts by kind: " + ", ".join(f"{k}={v}" for k, v in sorted(count.items())))
by_merge = defaultdict(list)
for p, k in sorted(kind.items()):
    if k == "comments/docstrings only":
        continue
    ms = merges(p)
    lines.append(f"{k:>14}  {p}   <- {'; '.join(h for h, _ in ms) if ms else 'NO MERGE FOUND'}")
    for h, s in ms:
        by_merge[(h, s)].append(p)
    if not ms:
        by_merge[("NONE", "no first-parent merge touched it")].append(p)
lines.append("")
lines.append("merges that account for the non-comment changes (paths per merge):")
for (h, s), ps in sorted(by_merge.items(), key=lambda kv: -len(kv[1])):
    lines.append(f"  {h}  {len(ps):>3} paths  {s[:110]}")
out.write_text("\n".join(lines) + "\n")
print("\n".join(lines))
