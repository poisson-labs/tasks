# Releasing Poisson Tasks

The checklist every release of `poisson-tasks` follows, in order. It was written from the 0.2.0
release and is followed as written; a step that changes is changed here first.

Two people's work, kept apart. The **preparer** builds, checks and tags on their own machine; they
push a branch for review, and never `main`, a tag or a file to PyPI. The **release owner** merges
the branch and runs the three hand-off blocks: the upload, the tag push with the GitHub release, and
the site's changelog entry. Nothing is uploaded that the preparer has not
checked, and the checks are read again after the upload.

Below, `X.Y.Z` is the release, `P.Q.R` the release before it, `<checkout>` the repository's main
checkout (the one that holds `.env`), and `<release worktree>` the fresh worktree of step 2. The
check scripts named here are kept with each release's evidence in the lab's private notes, not in
this repository; each step says what its script checks, so it can be done without it. Commands are
for zsh.

## 1. Before the build

- [ ] Everything the release holds is merged into `main` on GitHub, by the release owner. The
  preparer may build and check the branch's tip first; the release itself is built again from
  `origin/main` after the merge (step 2), and its hashes must equal the tip's.
- [ ] `CHANGELOG.md` opens with `## X.Y.Z (YYYY-MM-DD)`, dated the UTC day the upload is expected
  to land. A patch release's section holds fixes and tests only.
- [ ] `pyproject.toml` says `version = "X.Y.Z"`.
- [ ] If the test count changed, the README's sentence on the suite gives the whole suite's count
  on the commit being released.
- [ ] The gates ran after the version was raised, in a venv where the checkout was installed
  again (`pip install -e .`), since some tests read the installed version.
- [ ] The gates passed on that commit: `ruff check .`, `mypy`, the generator-hash step of the fast
  lane, the frozen generator and digest tests, and the docs tests. The whole suite ran when the
  change touched more than one line of code.

## 2. A clean worktree at `origin/main`

<!-- docs-check: skip reason="the release commands touch git and PyPI" -->
```bash
git -C <checkout> fetch origin
git -C <checkout> worktree add --detach <release worktree> origin/main
git -C <release worktree> status --short --ignored
```

- [ ] `status --short --ignored` prints nothing before the build, and only `dist/` after it.
- [ ] The commit is the merge on GitHub, and GitHub says its signature is valid
  (`gh api repos/poisson-labs/tasks/commits/<sha> --jq .commit.verification`).

## 3. The tools, shown to be the last release's

The build tools are pinned so a release is reproducible: Python 3.11.7, `build` 1.3.0 and
`hatchling` 1.32.4, with `packaging` 26.3, `pathspec` 1.1.1, `pluggy` 1.7.0, `pyproject_hooks`
1.3.3, `tomlkit` 0.15.2 and `trove-classifiers` 2026.9.21.13, in a venv of their own.

<!-- docs-check: skip reason="a release build, not a docs example" -->
```bash
python3.11 -m venv <tools venv>
<tools venv>/bin/pip install build==1.3.0 hatchling==1.32.4 packaging==26.3 pathspec==1.1.1 pluggy==1.7.0 pyproject_hooks==1.3.3 tomlkit==0.15.2 trove-classifiers==2026.9.21.13
```

- [ ] Rebuild `P.Q.R` from its tag (`git archive vP.Q.R` into a scratch folder, the same venv,
  the command of step 4) and compare the two files' sha256 with PyPI's
  (`https://pypi.org/pypi/poisson-tasks/P.Q.R/json`). They are equal byte for byte, or the tools
  are not the last release's and the build stops here.

## 4. The build, twice

<!-- docs-check: skip reason="a release build, not a docs example" -->
```bash
cd <release worktree>
<tools venv>/bin/python -m build --no-isolation --outdir dist .
<tools venv>/bin/python -m build --no-isolation --outdir <scratch>/dist2 .
shasum -a 256 dist/* <scratch>/dist2/*
```

- [ ] The two builds give the same two hashes. Write them down with the sizes and file counts:
  every later step checks against them.

## 5. What is in the files

- [ ] `uvx twine@7.0.0 check --strict dist/*` passes on both files.
- [ ] The version is `X.Y.Z` in `pyproject.toml`, the wheel's `METADATA` and the sdist's
  `PKG-INFO`.
- [ ] The tokenizer file is in neither file: no member named `*tiktoken*` or `*o200k*`, none of
  3,613,922 bytes, none whose sha256 starts `446a9538`. It is fetched on first use, never shipped.
- [ ] The key scan (`key_scan.py`) finds the same hits as `P.Q.R`'s, by file and kind, and no run
  of a model key; a hit whose line number moved is the same line text. The token scan
  (`scan_token.py`, counts only, never a value) finds 0 of `PYPI_API_TOKEN` and of
  `TESTPYPI_API_TOKEN` in both files.
- [ ] Against `P.Q.R`'s files nothing is unexplained (`content_compare.py`, `explain_diff.py`):
  every member added or changed is a path of `git diff vP.Q.R <commit>`, each path is accounted
  for by a merge, and each is code, docs or config.

## 6. The wheel gate

`drive.py` drives the built wheel in a real terminal, offline, against the fixture models: the
built-in tasks and the Petstore tool file, each in the coloured look and in `--plain`.

- [ ] A product venv holds the wheel with its dependencies from pypi.org; a driver venv holds the
  same wheel with pytest and hypothesis; the tokenizer file is copied into both venvs'
  `poisson_tasks/data/`.
- [ ] All four scenes exit 0, every word is driven, and the only host the scenes name is
  `127.0.0.1`.
- [ ] Keep each scene's `plan.json`, `produced_by.jsonl` and cards with the evidence, not its
  traces.

## 7. The date

- [ ] The upload will land on the changelog's date, in UTC. If it will not, stop: re-date the
  section, which is a new commit through review, and start again at step 2.

## 8. The tag

<!-- docs-check: skip reason="tags the release commit in git" -->
```bash
git -C <checkout> tag -s -m 'Poisson Tasks X.Y.Z' vX.Y.Z <commit>
git -C <checkout> tag -v vX.Y.Z
git -C <checkout> ls-remote --tags origin vX.Y.Z
```

- [ ] The tag is annotated and signed with the maintainer's key, its signature is good, and it is
  local only: `ls-remote` prints nothing.
- [ ] PyPI does not hold `X.Y.Z` yet (`https://pypi.org/pypi/poisson-tasks/X.Y.Z/json` answers
  404).

## 9. The hand-off blocks

Each is one line that pastes into zsh as it is: no comment lines and nothing to read halfway. The
preparer fills in the values and checks each part without running the upload; the release owner
runs them in this order. Each block starts only once the one before it has landed, and a block
that stops says why in one line, so a refusal never reads as done.

**Block one, the upload.** It refuses on any UTC day but the changelog's, saying so, and on any
file whose hash is not the build's (`shasum` prints `FAILED`), and reads the token from `.env`
without printing it. It has landed when twine prints `View at:`; block two waits for that.

<!-- docs-check: skip reason="uploads the release to PyPI" -->
```bash
if [[ "$(date -u +%F)" != YYYY-MM-DD ]]; then echo "stopped, nothing uploaded: the UTC date is $(date -u +%F) and this release uploads on YYYY-MM-DD"; else cd <release worktree>/dist && printf '%s  %s\n' <wheel sha256> poisson_tasks-X.Y.Z-py3-none-any.whl <sdist sha256> poisson_tasks-X.Y.Z.tar.gz | shasum -a 256 -c - && TWINE_USERNAME=__token__ TWINE_PASSWORD="$(sed -n 's/^PYPI_API_TOKEN=//p' <checkout>/.env)" uvx twine@7.0.0 upload --non-interactive --repository-url https://upload.pypi.org/legacy/ poisson_tasks-X.Y.Z-py3-none-any.whl poisson_tasks-X.Y.Z.tar.gz; fi
```

**Block two, the tag and the GitHub release.** It starts only when PyPI answers for `X.Y.Z`, so
the release never links a page that is not there; right after the upload PyPI can take a minute
to answer. The notes are the changelog's `X.Y.Z` section without its heading, in a file outside
the repository.

<!-- docs-check: skip reason="pushes the tag and makes the GitHub release" -->
```bash
if [[ "$(curl -s -o /dev/null -w '%{http_code}' https://pypi.org/pypi/poisson-tasks/X.Y.Z/json)" != 200 ]]; then echo "stopped, nothing pushed: PyPI does not answer for X.Y.Z yet; run block one, or wait a minute after it"; else cd <checkout> && git push origin refs/tags/vX.Y.Z && gh release create vX.Y.Z --repo poisson-labs/tasks --verify-tag --title "Poisson Tasks X.Y.Z" --notes-file <notes file> <release worktree>/dist/poisson_tasks-X.Y.Z-py3-none-any.whl <release worktree>/dist/poisson_tasks-X.Y.Z.tar.gz; fi
```

**Block three, the site's changelog entry**, run after block two, since the entry links the
release: it starts only when the GitHub release exists. The entry is `src/content/changelog/tasks-X-Y-Z.md` in the site's repository, in the form
of the entries before it, on a new branch from the site's `origin/main` in a worktree of its own,
committed signed; `npm run build` passes with its placeholder gate at 0. A release gets a
changelog entry and no News post.

<!-- docs-check: skip reason="pushes and merges the site's changelog entry" -->
```bash
if ! gh release view vX.Y.Z --repo poisson-labs/tasks > /dev/null 2>&1; then echo "stopped, nothing pushed: the GitHub release vX.Y.Z does not exist yet; run block two first"; else cd <site worktree> && git push -u origin changelog-tasks-X-Y-Z && git switch --detach -q && gh pr create --repo TaylorKolasinski/poisson-labs-site --base main --head changelog-tasks-X-Y-Z --title "The changelog gets Tasks X.Y.Z" --body-file <pr body file> && gh pr merge changelog-tasks-X-Y-Z --repo TaylorKolasinski/poisson-labs-site --merge --admin --delete-branch; fi
```

## 10. After the blocks

- [ ] **PyPI** (`readback_pypi.py`): `/pypi/poisson-tasks/json` and `/X.Y.Z/json` answer 200; the
  latest version is `X.Y.Z`; the release holds a wheel and an sdist with the names, sizes and
  sha256 of step 4, neither yanked; `Requires-Python` is `<3.14,>=3.11` and the description is
  `text/markdown`.
- [ ] **GitHub**: the tag on `origin` is the local tag object; the release is published, not a
  draft or a prerelease; its two assets, downloaded, have the build's sha256; its body is the
  notes file byte for byte (read it through the API, not through `--jq`, which adds a newline).
- [ ] **The site**: the PR is merged and `https://poissonlabs.ai/changelog/tasks-X-Y-Z/` answers
  200 and links the release and the PyPI page.

## 11. Nine installs from PyPI

Python 3.11.7, 3.12.13 and 3.13.11, each with pip, uv and pipx (1.18.4), into fresh environments,
from pypi.org alone, with the pin `poisson-tasks==X.Y.Z` and no cache.

- [ ] Wait until PyPI's simple index lists the wheel, in both forms the installers read: pip
  reads the HTML page and uv the JSON one, and right after an upload the cache can serve either
  without the new version (for 0.2.1, uv and pipx found no version a minute after the upload).

<!-- docs-check: skip reason="polls PyPI after a release upload" -->
```bash
until curl -s https://pypi.org/simple/poisson-tasks/ | grep -q 'poisson_tasks-X.Y.Z-py3-none-any.whl' && curl -s -H 'Accept: application/vnd.pypi.simple.v1+json' https://pypi.org/simple/poisson-tasks/ | grep -q 'poisson_tasks-X.Y.Z-py3-none-any.whl'; do echo "PyPI's index does not list X.Y.Z yet; waiting"; sleep 30; done
```

- [ ] A cell that still says there is no version of `X.Y.Z` met the cache too: install that cell
  again, and keep the first run's log with the evidence.
- [ ] Make the pipx venv first: `install_from_pypi.py` expects `<scratch>/pipx-venv/bin/pipx`.
- [ ] Every environment installs (`install_from_pypi.py`), and in every one the command check
  (`matrix_cell.py`), the first screen (`bare_first_screen.py`) and the smoke (`smoke_cell.py`)
  pass (`run_cells_pypi.py`): `poisson-tasks --version` starts `poisson-tasks X.Y.Z (` and
  `card --published` exits 0.
- [ ] Provenance (`provenance_pypi.py`): in every environment each package file equals the built
  wheel's by sha256, there is no `direct_url.json`, every installed dependency's version is on
  PyPI, and nothing came from TestPyPI's file host. `pip -v` logs the wheel's `.whl.metadata`
  address, not the wheel's own, so the log check reads that.

## 12. Close-out

- [ ] The evidence of every step (hashes, scans, the comparison, the gate, the tag, the blocks as
  run, the read-back, the installs, the scripts) is filed in the lab's private notes, never in
  this repository, with the devlog entry.
- [ ] The report says what landed, what was filed, what is owed and what is blocked.
- [ ] Remove the release worktree once nothing still reads its `dist/`.
