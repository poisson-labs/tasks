#!/bin/zsh
# Steps 5 and 6 of docs/releasing.md on one build: twine, the version, no tokenizer, the key and
# token scans (against the last release's), the comparison with the last release's files, and the
# wheel gate.
#
#   RELEASE_ENV_FILE=<checkout>/.env zsh scripts/release/release_checks.sh \
#       VERSION WORKTREE OLD_VERSION OLD_DIST OLD_REV SCRATCH OUT
#
# WORKTREE holds dist/ (the build) and tests/; OLD_DIST the last release's two files; OLD_REV its
# commit; SCRATCH a fresh folder for unpacked files and venvs; OUT where the evidence goes.
# RELEASE_ENV_FILE is the .env that holds the model key and the upload tokens (read for the scans,
# never printed); RELEASE_TOKENIZER is the tokenizer file (default: this checkout's
# src/poisson_tasks/data/o200k_base.tiktoken); RELEASE_PYTHON the Python 3.11 that runs the checks
# (default: python3.11).  uv, uvx, git, unzip and tar are on the PATH.
set -u
setopt pipefail
V=$1 W=$2 OV=$3 OLD=$4 OREV=$5 T=$6 OUT=$7
S=${0:A:h}
P=${RELEASE_PYTHON:-python3.11}
ENV=${RELEASE_ENV_FILE:?set RELEASE_ENV_FILE to the .env that holds the keys}
TOK=${RELEASE_TOKENIZER:-${S:h:h}/src/poisson_tasks/data/o200k_base.tiktoken}
[[ -f $TOK ]] || { print "no tokenizer file at $TOK: set RELEASE_TOKENIZER"; exit 2 }
NREV=$(git -C $W rev-parse HEAD)
WHL=$W/dist/poisson_tasks-$V-py3-none-any.whl SDIST=$W/dist/poisson_tasks-$V.tar.gz
failed=0
mkdir -p $T/u $OUT/build $OUT/twine $OUT/key-scan $OUT/wheel-gate
step() { print -- "=== $1 ($(date -u +%H:%M:%SZ))"; }

step "the build: $NREV"
shasum -a 256 $WHL $SDIST | sed "s|$W/dist/||" | tee $OUT/build/checksums.txt
ls -l $WHL $SDIST | awk '{print $5, $NF}' | sed "s|$W/dist/||" >> $OUT/build/checksums.txt

step "unpack"
for d in wheel sdist old-wheel old-sdist; do mkdir -p $T/u/$d; done
(cd $T/u/wheel && unzip -q -o $WHL) && (cd $T/u/sdist && tar -xzf $SDIST)
(cd $T/u/old-wheel && unzip -q -o $OLD/poisson_tasks-$OV-py3-none-any.whl) && (cd $T/u/old-sdist && tar -xzf $OLD/poisson_tasks-$OV.tar.gz)
(cd $T/u/wheel && find . -type f | sort) > $OUT/build/wheel-files.txt
(cd $T/u/sdist && find . -type f | sort) > $OUT/build/sdist-files.txt
print "wheel $(wc -l < $OUT/build/wheel-files.txt) files, sdist $(wc -l < $OUT/build/sdist-files.txt) files"

step "twine check --strict"
uvx twine@7.0.0 check --strict $WHL $SDIST 2>&1 | tee $OUT/twine/twine-check.txt || failed=1

step "version and tokenizer"
$P -I - $V $T/u/wheel $T/u/sdist $W/pyproject.toml <<'PY' | tee $OUT/build/version-and-tokenizer.txt || failed=1
import hashlib, re, sys
from pathlib import Path
v, wheel, sdist, pyproject = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4])
ok = True
meta = next(wheel.glob("*.dist-info/METADATA")).read_text()
pkg = next(sdist.glob("*/PKG-INFO")).read_text()
for name, text in (("METADATA", meta), ("PKG-INFO", pkg)):
    got = re.search(r"^Version: (.+)$", text, re.M).group(1)
    print(f"{name}: Version {got}"); ok &= got == v
got = re.search(r'^version = "(.+)"$', pyproject.read_text(), re.M).group(1)
print(f"pyproject.toml: version {got}"); ok &= got == v
for root in (wheel, sdist):
    files = [p for p in root.rglob("*") if p.is_file()]
    by_name = [p for p in files if "tiktoken" in p.name or "o200k" in p.name]
    by_size = [p for p in files if p.stat().st_size == 3_613_922]
    by_hash = [p for p in files if hashlib.sha256(p.read_bytes()).hexdigest().startswith("446a9538")]
    print(f"{root.name}: tokenizer by name {len(by_name)}, by size {len(by_size)}, by sha256 prefix {len(by_hash)}")
    ok &= not (by_name or by_size or by_hash)
print("VERSION AND TOKENIZER OK" if ok else "VERSION OR TOKENIZER FAILED")
sys.exit(0 if ok else 1)
PY

step "key scan, this build and the last release's"
scan() { for v in "$@"; do for form in shapes env; do print -- "### unpack-$v  form=$form"; if [[ $form == env ]]; then (cd $T/u && $P -I "$S/key_scan.py" unpack-$v --env $ENV); else (cd $T/u && $P -I "$S/key_scan.py" unpack-$v); fi; print "script exit code: $?"; done; done; }
(cd $T/u && rm -f unpack-wheel unpack-sdist unpack-oldwheel unpack-oldsdist && ln -s wheel unpack-wheel && ln -s sdist unpack-sdist && ln -s old-wheel unpack-oldwheel && ln -s old-sdist unpack-oldsdist)
scan wheel sdist > $OUT/key-scan/key-scan-runs.txt 2>&1
scan oldwheel oldsdist > $T/oldscan.txt 2>&1
grep '^HIT' $T/oldscan.txt | sed -e 's/unpack-oldwheel/unpack-wheel/' -e 's/unpack-oldsdist/unpack-sdist/' -e "s/poisson_tasks-$OV/poisson_tasks-V/" > $T/old-hits.txt
grep '^HIT' $OUT/key-scan/key-scan-runs.txt | sed -e "s/poisson_tasks-$V/poisson_tasks-V/" > $T/new-hits.txt
diff $T/old-hits.txt $T/new-hits.txt > $OUT/key-scan/hits.diff; print "hits: $(wc -l < $T/new-hits.txt) here, $(wc -l < $T/old-hits.txt) in $OV; differing lines: $(grep -c '^[<>]' $OUT/key-scan/hits.diff)"
grep -q 'run of the key' $OUT/key-scan/key-scan-runs.txt && { print "A RUN OF THE MODEL KEY"; failed=1 }
{ for n in PYPI_API_TOKEN TESTPYPI_API_TOKEN; do print "## $n"; (cd $T/u && $P -I "$S/scan_token.py" $n $ENV unpack-wheel unpack-sdist); print "exit code: $?"; done } > $OUT/key-scan/token-scan.txt 2>&1
grep -E '^# [0-9]+ hits|exit code' $OUT/key-scan/token-scan.txt
grep -q 'exit code: [12]' $OUT/key-scan/token-scan.txt && failed=1

step "against $OV's files"
git -C $W diff --name-only $OREV $NREV > $OUT/build/git-diff-names-$OV-to-$V.txt
print "$(wc -l < $OUT/build/git-diff-names-$OV-to-$V.txt) paths in git diff $OREV $NREV"
mkdir -p $T/olddist $T/newdist && cp $OLD/poisson_tasks-$OV* $T/olddist/ && cp $WHL $SDIST $T/newdist/
$P -I "$S/content_compare.py" $T/olddist $T/newdist $OV $V $OUT/build/git-diff-names-$OV-to-$V.txt $OUT/build/content-comparison.txt
grep -i -E 'unexplained' $OUT/build/content-comparison.txt | tail -3
$P -I "$S/explain_diff.py" $W $OREV $NREV $OREV $NREV $OUT/build/git-diff-names-$OV-to-$V.txt $OUT/build/explain-diff.txt
grep -E '^counts' $OUT/build/explain-diff.txt

step "the wheel gate"
for v in gate/venv driver; do rm -rf "${T:?}/$v"; $P -m venv $T/$v; done
$T/gate/venv/bin/python -m pip install -q --disable-pip-version-check --no-cache-dir --index-url https://pypi.org/simple "$WHL" > $T/gate-install.log 2>&1 || failed=1
$T/driver/bin/python -m pip install -q --disable-pip-version-check --index-url https://pypi.org/simple "$WHL" pytest hypothesis > $T/driver-install.log 2>&1 || failed=1
for v in gate/venv driver; do d=$($T/$v/bin/python -c 'import poisson_tasks,pathlib;print(pathlib.Path(poisson_tasks.__file__).parent/"data")'); cp $TOK "$d/"; done
$T/gate/venv/bin/python -m poisson_tasks --version
(cd $T && trap - INT && unset PYTHONDONTWRITEBYTECODE && PYTHONDONTWRITEBYTECODE=1 $T/driver/bin/python -I "$S/drive.py" $W $T/gate $OUT/wheel-gate/transcripts > $OUT/wheel-gate/drive.log 2>&1) || failed=1
tail -3 $OUT/wheel-gate/drive.log

step "end: failed=$failed"
exit $failed
