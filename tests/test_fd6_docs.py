"""The README, the docs and the changelog, frozen as tests, with the launch's wording on the dials.

- **The first screen.**  Above the README's first `---` come the install, `init`, `run` and
  `card` lines, in that order, then the platform line.  Every link in the README, images included,
  is an absolute `https` link, because the README is the PyPI page too.  The two kinds of user are
  named right after the first screen.
- **Plain words.**  The README, `docs/` (but the three standards, `repo-hygiene.md`,
  `cli-look.md` and `releasing.md`), `CHANGELOG.md` and the text of a card carry no internal
  identifier: the pattern of `tests/test_cal_plain_words.py` (`tests.helpers.INTERNAL`, which
  those frozen tests are not edited for) and the other kinds `OTHER` names.  The pin ledger's row ids stand only beside
  their names: in the ledger table of `docs/knobs-and-arms.md`, or after the word "row".
- **Markers.**  Every fenced `bash`, `console` and `python` block in the README, `docs/` and
  `CONTRIBUTING.md` carries a docs-check marker on the line before it, and a marker
  is well formed, sits on a block, and an `output` block follows a `run` block.  The clean-install
  job runs the blocks; this is the cheap check that none is left out.
- **The export page.**  `docs/verifiers-export.md` keeps what frozen tests pin (they stay green) and
  its sentence on the dotted form says an arm is given by its id, or as its six fields in one JSON
  object, and that the dotted form is not a way to give one.
- **The dials.**  Every dial is in the README with the status the evidence gives it, read from
  `poisson_tasks.arms.knob_status()` and the published cards; the decoy-tools dial is experimental;
  similarity, block, arguments and spread are "Available · retested in v2".
- **`verify`.**  Everywhere `verify` is documented, the docs say that in this release it refuses a
  tasks file made on your own tools, in one line.
- **The changelog.**  The changelog has one section for the release, headed with the version
  `pyproject.toml` declares and its date, which names the front door, own tools part two and the
  knob probe, and no entry in it is repeated.  (Retrofitted for the 0.1.0 release: the section
  was `Unreleased` until then.)
- **The look.**  `docs/cli-look.md` is the look in words that fit any of the lab's three tools.

The docs set is the design's, with the own-tools page and the release checklist,
`docs/releasing.md` (retrofitted for 0.2.1: a standard, so the README need not link it).
Retrofitted for the docs rewrite after 0.2.1, as ruled on 2026-10-26: the set gains
`docs/published-cards.md`, which holds the published cards' per-level lines the README held
(the test that renders them reads that page now); and `docs/proofload.md`, a maintainer's page
for an optional route, is no longer linked from the README, while staying under plain words.
`docs/commands.md` holds each command's help, which this file holds equal to what the command
prints.
"""

from __future__ import annotations

import dataclasses
import re
import subprocess
import sys
from pathlib import Path


from tests.helpers import INTERNAL

REPO = Path(__file__).resolve().parent.parent
DOCS = REPO / "docs"
README = REPO / "README.md"
CHANGELOG = REPO / "CHANGELOG.md"
CONTRIBUTING = REPO / "CONTRIBUTING.md"
STANDARDS = ("repo-hygiene.md", "cli-look.md", "releasing.md")
DOC_SET = {
    "calibration.md", "cli-look.md", "commands.md", "config.md", "knobs-and-arms.md",
    "own-tools.md", "proofload.md", "published-cards.md", "python.md", "reading-a-card.md",
    "releasing.md", "repo-hygiene.md", "the-task.md", "verifiers-export.md",
}
LINKED_FROM_README = DOC_SET - set(STANDARDS) - {"proofload.md"}
BASE = "https://github.com/poisson-labs/tasks/blob/main/"


def checked_files() -> list[Path]:
    """The README, every file in `docs/` and `CONTRIBUTING.md`: where a fenced command is run."""
    return [README, *sorted(DOCS.glob("*.md")), CONTRIBUTING]


def user_files() -> list[Path]:
    """What a user reads: the README, `docs/` but the three standards, and the changelog."""
    return [README, *sorted(p for p in DOCS.glob("*.md") if p.name not in STANDARDS), CHANGELOG]


# ---------------------------------------------------------------------------
# fenced blocks and their markers
# ---------------------------------------------------------------------------

COMMAND_FENCES = {"bash", "console", "python", "sh", "shell", "zsh", "py"}
MARKER = re.compile(r"^<!-- docs-check: (?P<body>.*) -->$")
RUN = re.compile(r'^run(?: exit=\d+)?(?: tty)?(?: fixture(?: env="[A-Z][A-Z0-9_,]*")?)?'
                 r'(?: answers="[^"]*")?$')
SKIP = re.compile(r'^skip reason="[^"]{12,}"$')
OPEN = re.compile(r"^(?P<fence>`{3,})(?P<info>[^`]*)$")


@dataclasses.dataclass
class Block:
    path: Path
    line: int
    """The line the opening fence is on, counting from 1."""
    info: str
    marker: str | None
    """The marker's body when the line before the fence is one."""
    body: str

    @property
    def language(self) -> str:
        return self.info.split()[0].lower() if self.info.strip() else ""


def blocks_of(text: str, path: Path | None = None) -> list[Block]:
    lines = text.splitlines()
    found: list[Block] = []
    i = 0
    while i < len(lines):
        opened = OPEN.match(lines[i])
        if opened is None:
            i += 1
            continue
        fence, start = opened.group("fence"), i
        close = i + 1
        while close < len(lines) and not (lines[close].startswith(fence)
                                          and lines[close].strip() == fence):
            close += 1
        previous = MARKER.match(lines[start - 1].strip()) if start else None
        found.append(Block(path or Path("<text>"), start + 1, opened.group("info").strip(),
                           previous.group("body") if previous else None,
                           "\n".join(lines[start + 1:close])))
        i = close + 1
    return found


def unmarked(blocks: list[Block]) -> list[Block]:
    return [b for b in blocks if b.language in COMMAND_FENCES and b.marker is None]


def malformed(text: str, path: Path | None = None) -> list[str]:
    """What is wrong with the markers of `text`: one with a body no mode names, one that is not
    on the line before a fence, an `output` block that does not follow a `run` block.  A line
    inside a fenced block is the block's own, so a page can show what a marker looks like."""
    problems: list[str] = []
    lines = text.splitlines()
    parsed = blocks_of(text, path)
    inside: set[int] = set()
    for block in parsed:
        inside.update(range(block.line + 1, block.line + 2 + block.body.count("\n") + (1 if block.body else 0)))
    for number, line in enumerate(lines, 1):
        if number in inside:
            continue
        marker = MARKER.match(line.strip())
        if marker is None:
            if line.lstrip().startswith("<!--") and "docs-check" in line:
                problems.append(f"{number}: not a marker the check reads: {line.strip()}")
            continue
        body = marker.group("body")
        if body != "output" and not RUN.match(body) and not SKIP.match(body):
            problems.append(f"{number}: no mode of the check is named {body!r}")
        after = lines[number] if number < len(lines) else ""
        if OPEN.match(after) is None:
            problems.append(f"{number}: the marker is not on the line before a fenced block")
    last_run = False
    for block in parsed:
        if block.marker == "output" and not last_run:
            problems.append(f"{block.line}: an output block with no run block before it")
        last_run = block.marker is not None and RUN.match(block.marker) is not None
    return problems


def test_fd6_5_every_command_fence_in_the_readme_the_docs_and_contributing_has_a_marker() -> None:
    missing = [f"{b.path.relative_to(REPO)}:{b.line} ```{b.info}"
               for path in checked_files() for b in unmarked(blocks_of(path.read_text("utf-8"), path))]
    assert missing == []


def test_fd6_5_every_marker_is_well_formed_and_sits_on_a_block() -> None:
    problems = [f"{path.relative_to(REPO)}:{p}" for path in checked_files()
                for p in malformed(path.read_text("utf-8"), path)]
    assert problems == []


def test_fd6_5_the_check_catches_what_it_is_for_and_lets_a_marked_block_through() -> None:
    """The control: a block with no marker, a marker no mode names, a marker apart from its block
    and an output block with nothing run before it are each found; the same blocks done right are
    not."""
    bare = "text\n\n```bash\npoisson-tasks run\n```\n"
    assert len(unmarked(blocks_of(bare))) == 1
    good = "<!-- docs-check: run -->\n```bash\npoisson-tasks run\n```\n"
    assert unmarked(blocks_of(good)) == [] and malformed(good) == []
    assert malformed("<!-- docs-check: runn -->\n```bash\nx\n```\n")
    assert malformed("<!-- docs-check: run -->\n\n```bash\nx\n```\n")
    assert malformed("<!-- docs-check: output -->\n```\nx\n```\n")
    both = good + "<!-- docs-check: output -->\n```\nout\n```\n"
    assert malformed(both) == []
    for body in ('run exit=2', 'run tty answers="1,,,y"', 'run fixture env="MODEL,MODEL_API_KEY"',
                 'run tty fixture answers=",,"', 'skip reason="installs from PyPI, not the wheel"'):
        assert malformed(f"<!-- docs-check: {body} -->\n```bash\nx\n```\n") == [], body
    assert malformed('<!-- docs-check: skip reason="" -->\n```bash\nx\n```\n')
    # a fence inside a longer fence is a line of the outer block, not a block of its own
    nested = "````markdown\n```bash\nx\n```\n````\n"
    assert unmarked(blocks_of(nested)) == []
    # a page can show a marker inside a fence
    shown = "```text\n<!-- docs-check: run -->\n<!-- docs-check: nonsense -->\n```\n"
    assert malformed(shown) == []


# ---------------------------------------------------------------------------
# the first screen
# ---------------------------------------------------------------------------


def first_screen() -> str:
    text = README.read_text("utf-8")
    return text.split("\n---\n", 1)[0]


def test_fd6_3_the_first_screen_has_install_init_run_card_then_the_platform_line() -> None:
    lines = first_screen().splitlines()

    def at(pattern: str) -> int:
        found = [i for i, line in enumerate(lines) if re.fullmatch(pattern, line.strip())]
        assert len(found) == 1, (pattern, found)
        return found[0]

    install, init, run, card = (at(r"pip install poisson-tasks"), at(r"poisson-tasks init"),
                                at(r"poisson-tasks run"), at(r"poisson-tasks card"))
    platform = next(i for i, line in enumerate(lines)
                    if re.match(r"Python 3\.11 to 3\.13, on macOS or Linux\b", line))
    assert install < init < run < card < platform
    assert lines[0] == "# Poisson Tasks"
    assert len(first_screen().splitlines()) <= 60


def test_fd6_3_both_kinds_of_user_are_named_right_after_the_first_screen() -> None:
    after = README.read_text("utf-8").split("\n---\n", 2)[1]
    assert re.search(r"people training models", after, re.I)
    assert re.search(r"agent teams?", after, re.I)
    for needle in ("verifiers", "OpenAI tools file", "MCP", "OpenAPI"):
        assert needle in after, needle


LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)|(?:src|href)=\"([^\"]+)\"")


def test_fd6_3_every_link_in_the_readme_is_an_absolute_https_link() -> None:
    urls = [a or b for a, b in LINK.findall(README.read_text("utf-8"))]
    assert urls, "the README links nothing"
    assert [u for u in urls if not u.startswith("https://")] == []


def test_fd6_3_the_readme_links_every_docs_page_it_is_for_and_each_link_names_a_file() -> None:
    text = README.read_text("utf-8")
    urls = {a or b for a, b in LINK.findall(text)}
    for name in LINKED_FROM_README:
        assert f"{BASE}docs/{name}" in urls, name
    for url in urls:
        if url.startswith(BASE):
            assert (REPO / url.removeprefix(BASE).split("#")[0]).exists(), url


def test_every_relative_link_in_the_docs_names_a_file() -> None:
    broken = []
    for path in [*sorted(DOCS.glob("*.md")), CONTRIBUTING]:
        for a, b in LINK.findall(path.read_text("utf-8")):
            url = (a or b).split("#")[0]
            if not url or url.startswith(("https://", "http://", "mailto:")):
                if url.startswith(BASE) and not (REPO / url.removeprefix(BASE)).exists():
                    broken.append((path.name, url))
                continue
            if not (path.parent / url).resolve().exists():
                broken.append((path.name, url))
    assert broken == []


def test_the_docs_set_is_the_specs_with_the_own_tools_page() -> None:
    assert {p.name for p in DOCS.glob("*.md")} == DOC_SET
    assert CONTRIBUTING.is_file()
    assert not (DOCS / "calibration-guide.md").exists()


# ---------------------------------------------------------------------------
# plain words
# ---------------------------------------------------------------------------

# The design names more kinds than the frozen pattern: the other invariant families, work-session
# and module names, and the words "frozen" and "oracle".
OTHER = re.compile(
    r"\bKC\d+\b|\bSF\d+\b|\bPG-\d+|\bTG-|\bfrozen\b|\boracle\b|\bSession [AB]\b|\bFD\d\b"
    r"|\bK(?:10|[0-9])\b|\bO[12]\b|\bPT4\b|\bP(?:[1-9]|1[0-5])\b|\bruled \d{4}-|\byes/no\b"
)
ROW_ID = re.compile(r"N(?:[1-9]|1[0-3]|19|2\d|3[0-5])")
ROW_WORD = re.compile(r"\brows?\b")
TEXT_FENCES = {"bibtex"}


def plain_hits(text: str, name: str) -> list[tuple[int, str]]:
    """Every internal reference in `text`, as (line, match).  A BibTeX entry carries its
    author's name and is left out; a ledger row id stands in the ledger table, or after the
    word "row"."""
    hits: list[tuple[int, str]] = []
    in_ledger = False
    lines = text.splitlines()
    fenced: set[int] = set()
    for block in blocks_of(text):
        if block.language in TEXT_FENCES:
            fenced.update(range(block.line - 1, block.line + block.body.count("\n") + 2))
    for number, line in enumerate(lines):
        if line.startswith("## "):
            in_ledger = name == "knobs-and-arms.md" and line.startswith("## The pin ledger")
        if number in fenced:
            continue
        spans = [m for m in (*INTERNAL.finditer(line), *OTHER.finditer(line))]
        for m in spans:
            word = m.group(0)
            if ROW_ID.fullmatch(word) and (in_ledger or ROW_WORD.search(line)):
                continue
            hits.append((number + 1, word))
    return hits


def test_fd6_4_no_file_a_user_reads_names_an_internal_reference() -> None:
    found = {f"{path.name}:{n} {word}": None for path in user_files()
             for n, word in plain_hits(path.read_text("utf-8"), path.name)}
    assert list(found) == []


def test_fd6_4_the_text_of_a_card_names_none() -> None:
    from poisson_tasks import calibration

    texts = [value for name, value in vars(calibration).items()
             if name.startswith("_LINE_") and isinstance(value, str)]
    texts += [text for _flag, text in calibration._OWN_LINES]
    assert len(texts) >= 6
    from poisson_tasks.own import card as own_card

    texts.append(own_card.PROBE_SENTENCE)
    hits = [(text[:60], m.group(0)) for text in texts
            for m in (*INTERNAL.finditer(text), *OTHER.finditer(text))]
    assert hits == []


def test_fd6_4_the_pattern_catches_what_it_is_for_and_lets_a_row_id_stand_beside_its_name() -> None:
    for old in ("(G4) the reference passes", "see CAL24", "the oracle", "Session A", "frozen tests",
                "ruling 17", "KC3", "N5 reports", "TG-ADR-35"):
        assert plain_hits(old, "the-task.md"), old
    assert plain_hits("a plain sentence about depth:d3 and pass@1", "the-task.md") == []
    assert plain_hits("the pin-ledger row N3 holds the system prompt", "the-task.md") == []
    ledger = "## The pin ledger\n\n| N3 | the system prompt |\n"
    assert plain_hits(ledger, "knobs-and-arms.md") == []
    assert plain_hits(ledger, "the-task.md")
    bibtex = "```bibtex\n@misc{x,\n  author = {Kolasinski, Taylor},\n}\n```\n"
    assert plain_hits(bibtex, "README.md") == []


# ---------------------------------------------------------------------------
# the dials, from the evidence
# ---------------------------------------------------------------------------

PROBE_KNOBS = ("similarity", "faults", "history", "block", "arguments", "shape", "spread")


def dial_rows() -> dict[str, str]:
    """The README's table of dials: a dial's key (its first backticked word) to its row."""
    rows = {}
    for line in README.read_text("utf-8").splitlines():
        match = re.match(r"^\|\s*`(\w+)`", line)
        if match:
            rows[match.group(1)] = line
    return rows


def test_every_dial_is_in_the_readme_with_the_status_the_evidence_gives_it() -> None:
    from poisson_tasks import arms

    rows = dial_rows()
    assert set(rows) >= {"depth", "distractor", *PROBE_KNOBS}, sorted(rows)
    status = arms.knob_status()
    short = status["models"]
    for knob in PROBE_KNOBS:
        for model, entry in status["knobs"][knob]["models"].items():
            assert f"{short[model]}: {entry['status']}" in rows[knob], (knob, model, rows[knob])


def test_the_readme_labels_the_dials_as_the_launch_words_them() -> None:
    from poisson_tasks import arms

    rows = dial_rows()
    for knob in ("depth", "faults", "history", "shape"):
        assert "Shown to make tasks harder" in rows[knob], knob
    assert "Experimental" in rows["distractor"] and "did not make tasks harder" in rows["distractor"]
    for knob in ("similarity", "block", "arguments", "spread"):
        assert "Available · retested in v2" in rows[knob], knob
    assert set(arms.SHIPPED_KNOBS) == {"faults", "history", "shape"}


def test_the_readme_never_calls_a_dial_that_did_not_bite_harder_than_the_evidence() -> None:
    """A dial is "shown to make tasks harder" only on the models it bit on, and a model it did
    not bite on is never given the word."""
    from poisson_tasks import arms

    rows = dial_rows()
    status = arms.knob_status()
    short = status["models"]
    for knob in PROBE_KNOBS:
        models = status["knobs"][knob]["models"]
        if not any(entry["status"] == "bites" for entry in models.values()):
            assert "Shown to make tasks harder" not in rows[knob], knob
        for model, entry in models.items():
            if entry["status"] != "bites":
                assert f"{short[model]}: bites" not in rows[knob], (knob, short[model])


# ---------------------------------------------------------------------------
# verify, and an own tasks file
# ---------------------------------------------------------------------------

OWN_REFUSAL = "which verify does not judge on its own yet"


def test_the_refusal_the_docs_quote_is_the_one_the_command_prints() -> None:
    source = (REPO / "src" / "poisson_tasks" / "cli" / "_verify.py").read_text("utf-8")
    joined = re.sub(r'"\s*\n\s*f?"', "", source)  # adjacent string literals are one string
    assert f"holds tasks on your own tools, {OWN_REFUSAL}: a run's card judges every episode" in joined


def test_everywhere_verify_is_documented_the_docs_say_it_refuses_an_own_tasks_file() -> None:
    documented = [p for p in [README, *sorted(DOCS.glob("*.md"))]
                  if "poisson-tasks verify" in p.read_text("utf-8") and p.name != "cli-look.md"]
    assert {p.name for p in documented} >= {"README.md", "commands.md", "own-tools.md"}
    missing = [p.name for p in documented if OWN_REFUSAL not in " ".join(p.read_text("utf-8").split())]
    assert missing == []


# ---------------------------------------------------------------------------
# docs/commands.md is the help
# ---------------------------------------------------------------------------

VERBS = ("init", "generate", "run", "card", "verify", "export", "doctor")


def printed(*argv: str) -> str:
    done = subprocess.run([sys.executable, "-m", "poisson_tasks", *argv], capture_output=True,
                          text=True, encoding="utf-8", check=True,
                          env={"COLUMNS": "80", "PATH": "", "NO_COLOR": "1", "TERM": "dumb",
                               "HOME": "/nonexistent", "PYTHONIOENCODING": "utf-8"})
    return done.stdout


def test_commands_md_holds_each_commands_help_as_it_is_printed() -> None:
    page = blocks_of((DOCS / "commands.md").read_text("utf-8"))
    outputs = {}
    for index, block in enumerate(page):
        if block.marker is not None and RUN.match(block.marker):
            command = block.body.strip()
            if command.startswith("poisson-tasks") and command.endswith("--help"):
                follower = page[index + 1]
                assert follower.marker == "output", command
                outputs[command] = follower.body.strip()
    wanted = {"poisson-tasks --help", *(f"poisson-tasks {verb} --help" for verb in VERBS)}
    assert set(outputs) == wanted
    for command, shown in outputs.items():
        assert shown == printed(*command.split()[1:]).strip(), command


# ---------------------------------------------------------------------------
# docs/verifiers-export.md
# ---------------------------------------------------------------------------


def export_text() -> str:
    return " ".join((DOCS / "verifiers-export.md").read_text("utf-8").split())


def test_fd6_7_the_export_page_says_an_arm_is_given_by_its_id_or_as_one_json_object() -> None:
    text = export_text()
    assert "--env.taskset.arm.<field>) also parses" not in text and "also parses" not in text
    sentence = next(s for s in re.split(r"(?<=[.!?])\s+", text) if "dotted" in s)
    assert re.search(r"not a way to give an arm", sentence), sentence
    assert "--env.taskset.arm depth:d3" in text
    assert '"strictness": "leaky"' in text
    assert re.search(r"id.{0,200}(six fields|one JSON (object|value))", text)


def test_fd6_7_the_pinned_block_opens_the_first_run_block_and_the_new_material_follows() -> None:
    blocks = blocks_of((DOCS / "verifiers-export.md").read_text("utf-8"))
    first = next(b for b in blocks if "eval poisson-tasks" in b.body.splitlines()[0]) if blocks else None
    assert first is not None and first.language == "bash" and first.body.startswith("uv run eval poisson-tasks ")
    text = export_text()
    assert text.index("The measured harness is `null`.") > text.index("uv run eval poisson-tasks")
    assert "poisson-tasks export --to verifiers" in text
    assert "shell builtin" in text


# ---------------------------------------------------------------------------
# the changelog, and the look
# ---------------------------------------------------------------------------


RELEASE_HEADING = re.compile(r"^## (\d+\.\d+\.\d+) \((\d{4}-\d{2}-\d{2})\)$", re.M)


def declared_version() -> str:
    import tomllib

    return str(tomllib.loads((REPO / "pyproject.toml").read_text("utf-8"))["project"]["version"])


FIRST_RELEASE = "## 0.1.0 (2026-10-22)"


def unreleased() -> str:
    """The 0.1.0 release's section, found by its heading: from the heading to the next `## `
    heading.  (The name is the frozen one; the section was `Unreleased` until the 0.1.0 release,
    and the newest section until a later release was added above it.)"""
    text = CHANGELOG.read_text("utf-8")
    start = re.search(rf"^{re.escape(FIRST_RELEASE)}$", text, re.M).start()  # type: ignore[union-attr]
    nxt = re.search(r"^## ", text[start + 3:], re.M)
    return text[start:start + 3 + nxt.start()] if nxt else text[start:]


def test_fd6_9_the_changelog_has_one_unreleased_section_that_covers_the_three_pieces() -> None:
    text = CHANGELOG.read_text("utf-8")
    assert len(RELEASE_HEADING.findall(text)) >= 1
    assert not re.search(r"^## Unreleased\b", text, re.M)
    section = unreleased().lower()
    for needle in ("poisson-tasks", "your own tools", "knob probe", "wheel", "verify"):
        assert needle in section, needle


def test_fd6_9_the_changelog_says_it_is_unreleased_and_names_no_version_it_has_not_got() -> None:
    text = CHANGELOG.read_text("utf-8")
    versions = [version for version, _date in RELEASE_HEADING.findall(text)]
    assert versions[0] == declared_version()
    assert len(versions) == len(set(versions)), versions
    head = text[:RELEASE_HEADING.search(text).start()]  # type: ignore[union-attr]
    assert "not been released" not in head and "unreleased" not in head.lower()
    headings = re.findall(r"^### .*$", unreleased(), re.M)
    assert len(headings) == len(set(headings)) >= 5


def test_fd6_9_no_entry_of_the_unreleased_section_is_repeated() -> None:
    bullets = [" ".join(line.split()) for line in unreleased().splitlines() if line.startswith("- ")]
    firsts = [b[:80] for b in bullets]
    assert len(set(firsts)) == len(firsts), [f for f in firsts if firsts.count(f) > 1]
    assert len(bullets) >= 8


def test_fd6_10_cli_look_is_the_look_in_words_that_fit_each_tool() -> None:
    text = (DOCS / "cli-look.md").read_text("utf-8")
    for needle in ("exit code", "standard error", "next:", "--json", "NO_COLOR", "Ctrl-C", "130",
                   "<tool>"):
        assert needle in text, needle
    for rule in range(1, 17):
        assert re.search(rf"\*\*L{rule}\.", text), f"L{rule}"
    for code in ("0", "1", "2", "3", "4", "130"):
        assert re.search(rf"^\| {code} \|", text, re.M), code
    assert not re.search(r"poisson-(?:tasks|trace|prove)|proofload|Tasks|Trace|Prove\b", text)


# ---------------------------------------------------------------------------
# what the README and the pages show is what the code gives
# ---------------------------------------------------------------------------

RAW = "https://raw.githubusercontent.com/poisson-labs/tasks/main/"


BADGE = re.compile(r"https://img\.shields\.io/pypi/(v|pyversions|l)/poisson-tasks(?:\?[\w=&%.-]*)?")


def test_the_readmes_pictures_are_pngs_in_the_repo_and_its_badges_are_this_packages_on_pypi() -> None:
    text = README.read_text("utf-8")
    images = re.findall(r"!\[[^\]]*\]\(([^)\s]+)\)", text) + re.findall(r'<(?:img src|source [^>]*?srcset)="([^"]+)"', text)
    badges = [image for image in images if BADGE.fullmatch(image)]
    pictures = [image for image in images if image not in badges]
    # two pictures: the first screen and the task `generate --show` prints, each a PNG in the repo, linked from an absolute
    # address, under 600 kB; a light-on-dark card, so it reads the same on a light page and a dark one
    assert sorted(picture.removeprefix(RAW) for picture in pictures) == ["docs/images/first-screen.png", "docs/images/generate-show.png"], pictures
    for picture in pictures:
        assert picture.startswith(RAW) and picture.endswith(".png"), picture
        path = REPO / picture.removeprefix(RAW)
        assert path.is_file() and path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n", picture
        assert path.stat().st_size < 600_000, picture
    # three badges, each of this package on PyPI: its version, its Python versions and its licence
    assert sorted(BADGE.fullmatch(badge).group(1) for badge in badges) == ["l", "pyversions", "v"], badges


def test_the_readme_lists_each_published_cards_levels_as_the_code_renders_them() -> None:
    from poisson_tasks import calibration, cards

    # retrofitted for the docs rewrite after 0.2.1: the lines moved from the README to this page
    text = (DOCS / "published-cards.md").read_text("utf-8")
    for card in cards.published():
        lines = calibration.render_readme_lines(cards.recompute(card).artifact).strip().splitlines()
        assert len(lines) >= 10
        for line in lines:
            assert line in text, line


def test_config_md_shows_the_file_init_writes() -> None:
    from poisson_tasks import config

    written = config.dump_config(config.config_from_init_args(["--provider", "openai", "--recipe", "first-look"]))
    shown = next(b.body for b in blocks_of((DOCS / "config.md").read_text("utf-8")) if b.language == "toml")
    assert shown.strip() == written.strip()


def test_the_knob_probes_three_disclosures_are_beside_its_results_table() -> None:
    text = " ".join((DOCS / "knobs-and-arms.md").read_text("utf-8").split())
    assert text.index("What the knob probe measured") < text.index("Three things about how the probe ran")
    assert text.index("Three things about how the probe ran") < text.index("## Arms")
    for sentence in (
        "Phase 1's check changed after its first result (gpt-5-nano).",
        "stopped the probe if any base-arm episode made no tool call",
        "on 1 of 21",
        "3 or more",
        "A crash at the start, and one arm run again (gpt-5-nano).",
        "`similarity:s0`",
        "instrument rate 0.104",
        "$1.5981 of the $4.00 cap",
        "More time for Qwen3-8B.",
        "14 of its 18 arms",
        "2.56 hours in all",
    ):
        assert sentence in text, sentence
