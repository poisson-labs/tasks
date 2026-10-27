# Releasing Poisson Tasks

The checklist every release of `poisson-tasks` follows, in order. It was written from the 0.2.0
release and is followed as written; a step that changes is changed here first.

Two people's work, kept apart. The **preparer** builds, checks and tags on their own machine; they
push a branch for review, and never `main`, a tag or a file to PyPI. The **release owner** merges
the branch and runs the three hand-off blocks: the upload, the tag push with the GitHub release, and
the site (its changelog entry, its copy of these docs and the tool page's version). Nothing is uploaded that the preparer has not
checked, and the checks are read again after the upload.

Below, `X.Y.Z` is the release, `P.Q.R` the release before it, `<checkout>` the repository's main
checkout (the one that holds `.env`), and `<release worktree>` the fresh worktree of step 2. The
check scripts are in `scripts/release/`; each step names the one it runs and says what it checks.
They read three settings from the environment: `RELEASE_ENV_FILE` (the `.env` with the model key
and the upload tokens, which they read for the scans and never print), `RELEASE_TOKENIZER` (the
tokenizer file, by default the checkout's `src/poisson_tasks/data/o200k_base.tiktoken`) and, for
the installs, `RELEASE_PY311`, `RELEASE_PY312` and `RELEASE_PY313` (by default `python3.11` to
`python3.13` on the PATH). Commands are for zsh, run from the release worktree.

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

`scripts/release/release_checks.sh` runs this step and the next on one build and writes what each
check printed under `<evidence>`; every line below is one of its steps, and each says the script
it calls.

<!-- docs-check: skip reason="the release checks read the keys file" -->
```bash
RELEASE_ENV_FILE=<checkout>/.env zsh scripts/release/release_checks.sh X.Y.Z <release worktree> P.Q.R <P.Q.R dist> <P.Q.R commit> <scratch> <evidence>
```

- [ ] `uvx twine@7.0.0 check --strict dist/*` passes on both files.
- [ ] The version is `X.Y.Z` in `pyproject.toml`, the wheel's `METADATA` and the sdist's
  `PKG-INFO`.
- [ ] The tokenizer file is in neither file: no member named `*tiktoken*` or `*o200k*`, none of
  3,613,922 bytes, none whose sha256 starts `446a9538`. It is fetched on first use, never shipped.
- [ ] The key scan (`scripts/release/key_scan.py`) finds the same hits as `P.Q.R`'s, by file and kind, and no run
  of a model key; a hit whose line number moved is the same line text. The token scan
  (`scripts/release/scan_token.py`, counts only, never a value) finds 0 of `PYPI_API_TOKEN` and of
  `TESTPYPI_API_TOKEN` in both files.
- [ ] Against `P.Q.R`'s files nothing is unexplained (`scripts/release/content_compare.py`,
  `scripts/release/explain_diff.py`):
  every member added or changed is a path of `git diff vP.Q.R <commit>`, each path is accounted
  for by a merge, and each is code, docs or config.

## 6. The wheel gate

`scripts/release/drive.py` drives the built wheel in a real terminal, offline, against the fixture models: the
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

**Block three, the site**, run after block two, since the changelog entry links the release: it
starts only when the GitHub release exists. Its branch is made from the site's `origin/main` in a
worktree of its own once the tag is made, and holds three things, each committed signed:

- the changelog entry, `src/content/changelog/tasks-X-Y-Z.md`, in the form of the entries before
  it. A release gets a changelog entry and no News post;
- the site's copy of these docs, from the release commit:
  `python3 scripts/sync_docs.py --only tasks --commit tasks=<release commit>`. It copies `docs/`,
  the README and this changelog, and leaves out this page and `repo-hygiene.md`;
- the tool page's version: `src/data/tasks-release.json` names `X.Y.Z`, its date and the release
  commit. The page links that version's changelog entry and refuses to build when the entry is
  missing, or when the docs were copied from another commit.

`npm run build` passes with its placeholder gate at 0, and `scripts/check_names.py` and
`scripts/check_links.py dist` find nothing.

<!-- docs-check: skip reason="pushes and merges the site's changelog entry" -->
```bash
if ! gh release view vX.Y.Z --repo poisson-labs/tasks > /dev/null 2>&1; then echo "stopped, nothing pushed: the GitHub release vX.Y.Z does not exist yet; run block two first"; else cd <site worktree> && git push -u origin changelog-tasks-X-Y-Z && git switch --detach -q && gh pr create --repo TaylorKolasinski/poisson-labs-site --base main --head changelog-tasks-X-Y-Z --title "The site gets Tasks X.Y.Z" --body-file <pr body file> && gh pr merge changelog-tasks-X-Y-Z --repo TaylorKolasinski/poisson-labs-site --merge --admin --delete-branch; fi
```

## 10. After the blocks

- [ ] **PyPI** (`python -I scripts/release/readback_pypi.py X.Y.Z <evidence> <wheel sha256> <sdist sha256>`):
  `/pypi/poisson-tasks/json` and `/X.Y.Z/json` answer 200; the
  latest version is `X.Y.Z`; the release holds a wheel and an sdist with the names, sizes and
  sha256 of step 4, neither yanked; `Requires-Python` is `<3.14,>=3.11` and the description is
  `text/markdown`.
- [ ] **GitHub**: the tag on `origin` is the local tag object; the release is published, not a
  draft or a prerelease; its two assets, downloaded, have the build's sha256; its body is the
  notes file byte for byte (read it through the API, not through `--jq`, which adds a newline).
- [ ] **The site**: the PR is merged and `https://poissonlabs.ai/changelog/tasks-X-Y-Z/` answers
  200 and links the release and the PyPI page; `/tools/tasks/` says `X.Y.Z` and links that entry;
  `/docs/tasks/changelog/` lists `X.Y.Z` and every page under `/docs/tasks/` names the release
  commit at its foot.

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
- [ ] Every environment installs (`scripts/release/install_from_pypi.py`, which puts pipx 1.18.4 in
  `<scratch>/pipx-venv` the first time), and in every one the command check
  (`scripts/release/matrix_cell.py`), the first screen (`scripts/release/bare_first_screen.py`) and
  the smoke (`scripts/release/smoke_cell.py`) pass (`scripts/release/run_cells_pypi.py`):
  `poisson-tasks --version` starts `poisson-tasks X.Y.Z (` and `card --published` exits 0.

<!-- docs-check: skip reason="installs the release from PyPI nine ways" -->
```bash
python -I scripts/release/install_from_pypi.py X.Y.Z <scratch> && python -I scripts/release/provenance_pypi.py <scratch> <release worktree>/dist/poisson_tasks-X.Y.Z-py3-none-any.whl && python -I scripts/release/run_cells_pypi.py X.Y.Z <scratch>
```

- [ ] Provenance (`scripts/release/provenance_pypi.py`): in every environment each package file equals the built
  wheel's by sha256, there is no `direct_url.json`, every installed dependency's version is on
  PyPI, and nothing came from TestPyPI's file host. `pip -v` logs the wheel's `.whl.metadata`
  address, not the wheel's own, so the log check reads that.

## 12. Close-out

- [ ] The evidence of every step (hashes, scans, the comparison, the gate, the tag, the blocks as
  run, the read-back, the installs) is filed in the lab's private notes, never in this
  repository, with the devlog entry. The scripts that made it are the ones in `scripts/release/`
  at the release commit; a script changed for a release is changed here, in its own commit.
- [ ] The report says what landed, what was filed, what is owed and what is blocked.
- [ ] Remove the release worktree once nothing still reads its `dist/`.
