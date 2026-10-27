"""Read a release of poisson-tasks back from PyPI and compare it with what was built (step 10 of docs/releasing.md).

    python -I scripts/release/readback_pypi.py VERSION OUT_DIR WHEEL_SHA256 SDIST_SHA256

GET https://pypi.org/pypi/poisson-tasks/json and .../VERSION/json must be 200, the project must hold VERSION as its latest
version, with a wheel and an sdist, each with the sha256 passed in (the hashes of the files built), not yanked.  Prints the
metadata PyPI shows (Requires-Python, classifiers, project URLs, dependencies) and writes the raw JSON of the release to
OUT_DIR/pypi-json-VERSION.json.  Exit 0 only when every check held.
"""
import json
import sys
import urllib.request
from pathlib import Path

version, out, want_wheel, want_sdist = sys.argv[1], Path(sys.argv[2]), sys.argv[3], sys.argv[4]
out.mkdir(parents=True, exist_ok=True)
ok = True


def check(good: bool, what: str) -> None:
    global ok
    ok &= bool(good)
    print(f"  {'ok  ' if good else 'FAIL'} {what}")


def get(url: str) -> tuple[int, bytes]:
    with urllib.request.urlopen(url, timeout=60) as r:
        return r.status, r.read()


status_all, raw_all = get("https://pypi.org/pypi/poisson-tasks/json")
status_rc, raw_rc = get(f"https://pypi.org/pypi/poisson-tasks/{version}/json")
(out / f"pypi-json-{version}.json").write_bytes(raw_rc)
allj, rc = json.loads(raw_all), json.loads(raw_rc)
print("GET /pypi/poisson-tasks/json ->", status_all, f"| GET /pypi/poisson-tasks/{version}/json ->", status_rc)
check(status_all == 200 and status_rc == 200, "both endpoints answer 200")
check(version in allj["releases"], f"the project holds {version}: {sorted(allj['releases'])}")
check(allj["info"]["version"] == version, f"the latest version is {version} ({allj['info']['version']})")
files = {f["packagetype"]: f for f in rc["urls"]}
check(sorted(files) == ["bdist_wheel", "sdist"], f"the release holds a wheel and an sdist: {sorted(files)}")
for kind, want, name in (("bdist_wheel", want_wheel, f"poisson_tasks-{version}-py3-none-any.whl"),
                         ("sdist", want_sdist, f"poisson_tasks-{version}.tar.gz")):
    f = files.get(kind, {})
    print(f"  {kind:12s} {f.get('filename')}  {f.get('size'):,} bytes  sha256 {f.get('digests', {}).get('sha256')}  uploaded {f.get('upload_time_iso_8601')}")
    check(f.get("filename") == name and f.get("digests", {}).get("sha256") == want and not f.get("yanked"),
          f"{kind}: name {name}, sha256 equal to the file built, not yanked")
info = rc["info"]
print("\nname:", info["name"], "| version:", info["version"], "| Requires-Python:", info["requires_python"], "| summary:", info["summary"][:80] + "...")
print("description_content_type:", info["description_content_type"], "| description:", len(info["description"]), "characters")
print("project_urls:", json.dumps(info["project_urls"]))
print("author_email:", info["author_email"], "| keywords:", info.get("keywords"))
print("classifiers:\n  " + "\n  ".join(info["classifiers"]))
print("requires_dist:\n  " + "\n  ".join(info["requires_dist"]))
check(info["requires_python"] == "<3.14,>=3.11", "Requires-Python is <3.14,>=3.11")
check(info["description_content_type"] == "text/markdown", "the description is text/markdown")
print("\nALL READ-BACK CHECKS HELD" if ok else "\nA READ-BACK CHECK FAILED")
sys.exit(0 if ok else 1)
