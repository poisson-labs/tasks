"""Shared ground for the `tests/test_pv_*.py` tests: what a run records about what produced it,
written out here apart from the code under test.  Frozen with them.

**The canonical rule, our own copy.**  A tool file's contract hash is computed here the way the
docs give it, in a few lines that need nothing of this package but the own-tools reader's parse:
parse the bytes (JSON first, YAML second), render a YAML date or datetime as its ISO text and a
mapping key that is not a string as its JSON text, then `json.dumps` with sorted keys, no spaces,
`ensure_ascii=False` and `allow_nan=False`, encoded UTF-8, and SHA-256 with no prefix.  A test
compares the package's value with this one and with the literals measured on the commit the tests
were written on.

**The record, our own copy.**  `expected_record` builds the object a run should record for a plan
from the plan, the installed distributions and the literals below; `SECTION_1` is its keys in the
order the docs list them.  Nothing here is read from `poisson_tasks.provenance`.

**Run folders are copied before they are touched.**  The scenario folders of
`tests/fd4_support.py` are shared by every test of a session, so a test that edits a record,
deletes it or writes a card copies the folder first (`copy_run`).

Every module under test is reached inside the test that needs it, so a tree without the new module
fails each test on its own, at the line that needs it.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import re
import shutil
from collections.abc import Mapping, Sequence
from importlib import metadata
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
SHIPPED = REPO / "calibration"
FIXTURES = REPO / "tests" / "fixtures" / "o1"
PROG = "poisson-tasks"

SCHEMA = "poisson-tasks.produced-by/1"
BUILT_IN_GENERATOR = "b0aa26c77259dd16a07f814fc4b250ce0ba69d372aff520663db089daa9b0db4"
OWN_TOOLS_GENERATOR = "0cf69e660b66ff0c9a36d906cd7dad10e0c7a5f63b71c950bed7bdfd67888a14"
GENERATOR_0_PREFIX = "53c243df0a80"
"""The first twelve characters of what generator version "0" hashes to.  Moved 2026-10-29 for
0.3.0 with the two hashes above: the label enters the hash over the same changed files."""
VOCABULARY = "9f3a8c4f4711574e947ec8b3396ff552c9b7aa730fbb5d565db4f10776653037"
"""The bytes of `data/vocabulary-v2.json`: the vocabulary hash is their SHA-256."""

SECTION_1 = (
    "schema", "poisson_tasks_version", "verifiers_version", "generator_version",
    "builtin_generator_hash", "own_generator_hash", "engine_hash", "vocabulary_hash",
    "tool_format", "tool_spec_hash", "tool_file_sha256", "plan_hash", "preset", "seeds",
    "seed_list_hash",
)
GENERATOR_KEYS = ("generator_version", "builtin_generator_hash", "own_generator_hash")
TOOL_KEYS = ("tool_format", "tool_spec_hash", "tool_file_sha256")

# The six fixture files: the SHA-256 of their bytes and of their canonical JSON.
FIXTURE_HASHES = {
    "acme-openai-chat.json": (
        "5038e1bbef2e2e65c00227bf715cae357b8af056005591e35d8edc4b3251c647",
        "a2d89128c189d42ef7e9103ae919ed862d2c9a4b7598c687b7903fc6ef9464b5"),
    "acme-openai-responses.json": (
        "8f600fb19fe89ed44ee970f285a16e14eee750094ae425228a369f8e21611c30",
        "57b647defa3438bfab347e318db8825d15f48893565c227ede186fed1f4ec559"),
    "acme-mcp-tools-list.json": (
        "0de506261513f27acb6672ce74a25b7ce1967e97d49cf174c53068d00d5243e7",
        "1777970454047542102d901ddc5d1025a9fb258a621ce77855d82cee22d815f6"),
    "acme-openapi-3.0.json": (
        "25944a0c778442455f72f6f05d42e68e68651ee47cf4a18e0a51faaa9f13f998",
        "215a1be222ac1fc091dd8771fa9b34f36b4406abed621cd72c7f8f1f4105a38a"),
    "acme-openapi-3.1.yaml": (
        "ae58133dfa705fb890a927ce383aca5c1ccf0d7c9644795899902ca2a38da627",
        "ce4835e8c4bf6673574db78add19e8dc0b8e4577e3ee84bca639e95e93596b49"),
    "petstore-openapi-3.0.json": (
        "00441c05add60f28da55eb4563d3fb6bbda364ba8eb7b381e2e2c98613005c82",
        "371bf7809f1aa3ac786fbadb5331254ad6c6b74e5d67028e779858bc8d279780"),
}


# ---------------------------------------------------------------------------
# the canonical rule
# ---------------------------------------------------------------------------


def json_model(value: Any) -> Any:
    """The parsed value in JSON's data model: dates as ISO text, keys as JSON text."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            text = key if isinstance(key, str) else json.dumps(key)
            assert text not in out, f"two keys become {text!r}"
            out[text] = json_model(item)
        return out
    if isinstance(value, list):
        return [json_model(item) for item in value]
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    return value


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def parsed(data: bytes) -> Any:
    from poisson_tasks.own import _readers

    return _readers.parse(data)


def spec_hash(data: bytes) -> str:
    """Our own reading of the contract hash."""
    return hashlib.sha256(canonical(json_model(parsed(data)))).hexdigest()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


# ---------------------------------------------------------------------------
# the record
# ---------------------------------------------------------------------------


def engine_hash() -> str:
    """The domain's hash, as the published cards recorded it: the engine is frozen, so every
    shipped card holds the one value a run of this install records."""
    found = {json.loads(path.read_text(encoding="utf-8"))["provenance"]["engine_hash"]
             for path in SHIPPED.glob("*/artifact.json")}
    assert len(found) == 1, found
    value: str = found.pop()
    return value


def seed_list_hash(seeds: Sequence[int]) -> str:
    return hashlib.sha256(json.dumps(list(seeds)).encode("utf-8")).hexdigest()


def expected_record(plan: Any, *, tools: tuple[str, str, str] | None = None) -> dict[str, Any]:
    """The object a run of `plan` records, from the plan and the installed distributions.
    `tools` is the own-tools plan's format, spec hash and file hash; `None` on the built-in
    tasks."""
    from poisson_tasks import config

    labels = {str(spec.generator_version) for spec in plan.arms}
    assert len(labels) == 1, labels
    seeds = [int(seed) for seed in plan.seeds]
    return {
        "schema": SCHEMA,
        "poisson_tasks_version": metadata.version("poisson-tasks"),
        "verifiers_version": metadata.version("verifiers"),
        "generator_version": labels.pop(),
        "builtin_generator_hash": BUILT_IN_GENERATOR,
        "own_generator_hash": OWN_TOOLS_GENERATOR if tools is not None else None,
        "engine_hash": engine_hash(),
        "vocabulary_hash": VOCABULARY,
        "tool_format": tools[0] if tools is not None else None,
        "tool_spec_hash": tools[1] if tools is not None else None,
        "tool_file_sha256": tools[2] if tools is not None else None,
        "plan_hash": config.plan_hash(plan),
        "preset": str(plan.preset),
        "seeds": seeds,
        "seed_list_hash": seed_list_hash(seeds),
    }


RECORD = "produced_by.jsonl"
AT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")


def record_lines(folder: Path) -> list[dict[str, Any]]:
    """Every line of the folder's record, each one whole JSON object."""
    text = (folder / RECORD).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines()]


def bare(line: Mapping[str, Any]) -> dict[str, Any]:
    """A record line less `at` and `segment`: the object itself."""
    return {key: value for key, value in line.items() if key not in ("at", "segment")}


def rewrite_first_line(folder: Path, **changes: Any) -> dict[str, Any]:
    """The folder's first record line with `changes` made; returns the line as it was."""
    path = folder / RECORD
    lines = path.read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    lines[0] = json.dumps({**first, **changes})
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return dict(first)


def other_hash(word: str) -> str:
    """A 64-hex value no generator or file of this repository has."""
    return hashlib.sha256(f"not this install's {word}".encode()).hexdigest()


def copy_run(folder: Path, target: Path) -> Path:
    """A copy of a run folder at `target`, without any card written into it."""
    shutil.copytree(folder, target)
    shutil.rmtree(target / "card", ignore_errors=True)
    return target


def changed(a: Mapping[str, Any], b: Mapping[str, Any]) -> list[str]:
    """The keys of the object whose values differ, in the docs' order."""
    return [key for key in SECTION_1 if a.get(key) != b.get(key)]


# ---------------------------------------------------------------------------
# what the command printed
# ---------------------------------------------------------------------------

ROW = re.compile(r"^  ([a-z][a-z ]*[a-z])\s{2,}(\S.*)$")


def rows(text: str) -> list[tuple[str, str, int, int]]:
    """The result's `label  value` rows: each label, its value with the wrapped lines joined,
    and the first and last line it takes."""
    lines = text.splitlines()
    out: list[tuple[str, str, int, int]] = []
    index = 0
    while index < len(lines):
        match = ROW.match(lines[index])
        if match is None:
            index += 1
            continue
        start, parts = index, [match.group(2)]
        index += 1
        while (index < len(lines) and lines[index].startswith("   ")
               and not lines[index].strip().startswith("- ")):
            parts.append(lines[index].strip())
            index += 1
        out.append((match.group(1), " ".join(parts), start, index - 1))
    return out


def card_md_section(document: str, heading: str) -> list[str]:
    """The lines of `card.md`'s section under `## heading`, up to the next heading."""
    lines = document.splitlines()
    start = lines.index(f"## {heading}")
    out: list[str] = []
    for line in lines[start + 1:]:
        if line.startswith("#"):
            break
        out.append(line)
    return out


def invoke_json(argv: Sequence[str], monkeypatch: Any) -> tuple[Any, dict[str, Any]]:
    """The command in this process with `--json`, and the document it printed."""
    from tests.fd5_support import invoke, strict_json

    ran = invoke([*argv, "--json"], prog=PROG, monkeypatch=monkeypatch)
    document = strict_json(ran.out) if ran.out.strip() else {}
    return ran, document
