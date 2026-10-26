"""What produced a run: the record a run writes before its first request, the hash of a tool
file's contract, and the rules two runs are compared by on them.

**The record** is one JSON object, `produced_by`, the same shape wherever it appears: in the run
folder's `produced_by.jsonl`, in a card's `artifact.json` and `--json`, and in the export's
`produced_by.json`.  Every key of `KEYS` is always present, `null` where it does not apply:
the package and verifiers versions that started the run, the generator's label and both
generators' hashes, the domain's and the vocabulary's hashes, on your own tools the tool file's
format, its contract hash and the SHA-256 of its bytes, and the plan's hash, preset, seeds and
seed-list hash.  On a card it gains `resumed_with`: the package versions of later segments that
differ from the first, in order, without repeats.

**The run's file** holds one line per segment that dispatches episodes: the folder's first is
`started`, every later one `resumed`.  A line is the object with `at` (UTC, `Z`) and `segment`
first after `schema`, appended and flushed before the segment's first request.  A torn last line,
left by a process that died writing it, is dropped when the file is read, as the ledger's is.
`plan.json` is not touched, so every folder is found and resumed as before.  A resume of a folder
whose `started` line names another generator or tool contract than this install and the file give
now is refused before anything is spent.

**The tool file's contract hash** (`tool_spec_hash`) is the SHA-256 of the file as canonical
JSON: parsed as the own-tools reader parses it (JSON first, YAML second), a YAML date or datetime
as its ISO text and a mapping key that is not a string as its JSON text, then rendered with sorted
keys, no spaces, UTF-8, `ensure_ascii=False` and `allow_nan=False`, with no prefix, so anyone can
recompute it.  What JSON cannot carry (NaN, an infinity, binary data, a set, two keys that become
one) is refused in one line naming the place as a JSON pointer.

No module the generators hash imports this one: the version is read through `importlib.metadata`
and the generators' hashes through their own public calls, so recording what produced a run moves
no task.
"""

from __future__ import annotations

import dataclasses
import datetime
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from importlib import metadata
from pathlib import Path
from typing import Any

__all__ = [
    "KEYS",
    "RECORD_FILE",
    "SCHEMA",
    "Compared",
    "check_resume",
    "compare",
    "made_with",
    "produced_by",
    "read_run",
    "section",
    "segment",
    "table",
    "tool_spec_hash",
    "unrecorded_resumes",
    "write_segment",
]

SCHEMA = "poisson-tasks.produced-by/1"
KEYS = (
    "schema", "poisson_tasks_version", "verifiers_version", "generator_version",
    "builtin_generator_hash", "own_generator_hash", "engine_hash", "vocabulary_hash",
    "tool_format", "tool_spec_hash", "tool_file_sha256", "plan_hash", "preset", "seeds",
    "seed_list_hash",
)
"""The record's keys, in the order the docs list them."""
RECORD_FILE = "produced_by.jsonl"
SHOWN = 12
"""How many characters of a hash a row or a sentence shows, as `doctor` shows a digest."""
STARTED, RESUMED = "started", "resumed"
FORMAT_WORDS = {
    "openai": "an OpenAI tools file",
    "mcp": "an MCP tool list",
    "openapi": "an OpenAPI document",
}
NOT_RECORDED = "the run was made before poisson-tasks 0.2.0"


# ---------------------------------------------------------------------------
# the tool file's contract hash
# ---------------------------------------------------------------------------


def _pointer(path: Sequence[str]) -> str:
    """The place as a JSON pointer, or the document itself."""
    if not path:
        return "the document's top level"
    return "".join("/" + part.replace("~", "~0").replace("/", "~1") for part in path)


def _cannot(path: Sequence[str], what: str) -> ValueError:
    return ValueError(f"{_pointer(path)} holds {what}, which JSON cannot carry; write it as JSON "
                      "would")


def _key_text(key: Any, path: Sequence[str]) -> str:
    """A mapping key as JSON text: a date as its ISO text, anything else as `json.dumps` writes
    it (`200` is `"200"`, `true` is `"true"`)."""
    if isinstance(key, str):
        return key
    if isinstance(key, datetime.date):
        return key.isoformat()
    try:
        return json.dumps(key, allow_nan=False)
    except (TypeError, ValueError):
        raise _cannot(path, f"a key that is {_what(key)}") from None


def _what(value: Any) -> str:
    if isinstance(value, float):
        return "NaN" if math.isnan(value) else "an infinity"
    if isinstance(value, (bytes, bytearray)):
        return "binary data"
    if isinstance(value, (set, frozenset)):
        return "a set"
    return f"a {type(value).__name__}"


def _json_model(value: Any, path: list[str]) -> Any:
    """The parsed value in JSON's data model, or the refusal naming where it is not."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            text = _key_text(key, path)
            if text in out:
                raise _cannot(path, f"two keys that are both {json.dumps(text)} as JSON text")
            out[text] = _json_model(item, [*path, text])
        return out
    if isinstance(value, list):
        return [_json_model(item, [*path, str(index)]) for index, item in enumerate(value)]
    if isinstance(value, datetime.date):
        # a datetime is a date too, and both write their ISO text
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        raise _cannot(path, _what(value))
    if value is None or isinstance(value, (str, int, float)):
        return value
    raise _cannot(path, _what(value))


def tool_spec_hash(data: bytes) -> str:
    """The SHA-256 of the tool file's canonical JSON, lowercase hex, with no prefix.  A value
    JSON cannot carry is a `ValueError` of one line naming its place."""
    from poisson_tasks.own import _readers

    value = _json_model(_readers.parse(data), [])
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# the record
# ---------------------------------------------------------------------------


def produced_by(plan: Any) -> dict[str, Any]:
    """The record for a run of `plan` (a `config.Plan`) by this install, in `KEYS` order.

    On the built-in tasks the generator's hash is the one the plan's tasks carry; on your own
    tools it is the built-in generator's at the package's default version, beside the own-tools
    generator's, and the tool file is read again: bytes that no longer have the plan's digest are
    refused as `config.plan_toolset` refuses them, and a file JSON cannot carry is refused naming
    the file."""
    from poisson_tasks import calibration, config
    from poisson_tasks.engine import EngineSpec, engine_hash
    from poisson_tasks.tasks import generate

    if not plan.arms or not plan.seeds:
        raise ValueError("a plan with no seed or no arm records nothing")
    seeds = [int(seed) for seed in plan.seeds]
    own = getattr(plan, "own", None)
    own_hash = tool_format = spec_hash = file_hash = None
    if own is None:
        builtin = str(generate(plan.arms[0], seeds[0]).generator_hash)
    else:
        from poisson_tasks.own import generator as own_generator

        builtin = calibration._package_generator_hash()
        own_hash = own_generator.generator_hash()
        data = config.plan_tool_bytes(plan)
        try:
            spec_hash = tool_spec_hash(data)
        except ValueError as refused:
            raise ValueError(f"{own['file']} cannot be hashed: {refused}") from None
        tool_format = str(own["source_format"])
        file_hash = str(own["file_digest"])
    return {
        "schema": SCHEMA,
        "poisson_tasks_version": metadata.version("poisson-tasks"),
        "verifiers_version": metadata.version("verifiers"),
        "generator_version": str(plan.arms[0].generator_version),
        "builtin_generator_hash": builtin,
        "own_generator_hash": own_hash,
        "engine_hash": engine_hash(EngineSpec.load()),
        "vocabulary_hash": calibration._vocabulary_hash(),
        "tool_format": tool_format,
        "tool_spec_hash": spec_hash,
        "tool_file_sha256": file_hash,
        "plan_hash": config.plan_hash(plan),
        "preset": str(plan.preset),
        "seeds": seeds,
        "seed_list_hash": hashlib.sha256(json.dumps(seeds).encode("utf-8")).hexdigest(),
    }


def _lines(folder: Path) -> list[dict[str, Any]]:
    """The whole lines of the folder's record that parse; a torn or malformed line is
    skipped."""
    path = Path(folder) / RECORD_FILE
    if not path.is_file():
        return []
    out: list[dict[str, Any]] = []
    for piece in path.read_bytes().splitlines(keepends=True):
        if not piece.endswith(b"\n"):
            continue
        try:
            line = json.loads(piece)
        except ValueError:
            continue
        if isinstance(line, dict):
            out.append(line)
    return out


def _started(folder: Path) -> dict[str, Any] | None:
    lines = _lines(folder)
    return lines[0] if lines and lines[0].get("segment") == STARTED else None


def _later_versions(first: str, lines: Sequence[Mapping[str, Any]]) -> list[str]:
    out: list[str] = []
    for line in lines:
        version = str(line.get("poisson_tasks_version"))
        if version != first and version not in out:
            out.append(version)
    return out


def read_run(folder: Path) -> dict[str, Any] | None:
    """The card's record of the run folder: its `started` line less `at` and `segment`, with
    `resumed_with` from the later lines; `None` for a run that recorded none, or that was
    started before there was a record to write."""
    lines = _lines(folder)
    if not lines or lines[0].get("segment") != STARTED:
        return None
    first = {key: lines[0].get(key) for key in KEYS}
    return {**first, "resumed_with": _later_versions(str(first["poisson_tasks_version"]),
                                                      lines[1:])}


def unrecorded_resumes(folder: Path) -> list[str]:
    """The package versions that resumed a run started before there was a record to write, in
    order, without repeats; empty when the run recorded its start, or nothing."""
    lines = _lines(folder)
    if not lines or lines[0].get("segment") == STARTED:
        return []
    return _later_versions("", lines)


def segment(folder: Path) -> str:
    """The word for the segment a run of the folder would start now: `started` when the folder
    holds no record and no episode yet, else `resumed`."""
    folder = Path(folder)
    if _lines(folder):
        return RESUMED
    held = [folder / "spend.jsonl", *folder.glob("*/traces.jsonl")]
    if any(path.is_file() and path.stat().st_size for path in held):
        return RESUMED
    return STARTED


_CHECKED = (
    ("builtin_generator_hash", "with another generator than this install's"),
    ("own_generator_hash", "with another own-tools generator than this install's"),
    ("tool_spec_hash", "on another tool contract than this file's"),
)


def check_resume(folder: Path, record: Mapping[str, Any], *, name: str | None = None) -> None:
    """Refuse (`ValueError`, one line) a resume of a folder whose `started` line names another
    generator or tool contract than `record`, the one this install would write now.  A folder
    with no `started` line cannot be checked and is not refused; nor is one where only a version
    differs.  `name` is the folder as the message shows it."""
    there = _started(Path(folder))
    if there is None:
        return
    for key, words in _CHECKED:
        if there.get(key) != record.get(key):
            shown_there = "none" if there.get(key) is None else str(there.get(key))[:SHOWN]
            shown_here = "none" if record.get(key) is None else str(record.get(key))[:SHOWN]
            raise ValueError(
                f"{name if name is not None else folder} was started {words} ({shown_there} "
                f"there, {shown_here} here), so its tasks are not the ones this install makes; "
                f"finish it with poisson-tasks {there.get('poisson_tasks_version')}, or move the "
                "folder aside to run the plan from the start"
            )


def write_segment(folder: Path, record: Mapping[str, Any], word: str) -> None:
    """Append the segment's line to the folder's record and flush it.  A torn last line is
    closed first, so it stays a line of its own that the reader drops."""
    at = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = {"schema": record["schema"], "at": at, "segment": word,
            **{key: record[key] for key in KEYS[1:]}}
    path = Path(folder) / RECORD_FILE
    torn = path.is_file() and path.stat().st_size and not path.read_bytes().endswith(b"\n")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(("\n" if torn else "") + json.dumps(line, ensure_ascii=False) + "\n")
        handle.flush()


# ---------------------------------------------------------------------------
# what a card says of it
# ---------------------------------------------------------------------------


def _short(value: Any) -> str:
    return str(value)[:SHOWN]


def _not_recorded(resumes: Sequence[str]) -> str:
    if resumes:
        return (f"the run was started before poisson-tasks 0.2.0 (resumed with "
                f"{', '.join(resumes)})")
    return NOT_RECORDED


def made_with(record: Mapping[str, Any] | None, *, resumes: Sequence[str] = ()) -> str:
    """The `made with` row: what produced the run, with hashes cut to twelve characters, or
    that it recorded nothing (`resumes` are the versions that resumed a run started before)."""
    if record is None:
        return f"not recorded: {_not_recorded(resumes)}"
    first = f"poisson-tasks {record['poisson_tasks_version']}"
    if record.get("resumed_with"):
        first += ", resumed with " + ", ".join(str(v) for v in record["resumed_with"])
    parts = [first, f"generator {_short(record['builtin_generator_hash'])}"]
    if record.get("own_generator_hash") is not None:
        words = FORMAT_WORDS.get(str(record["tool_format"]), str(record["tool_format"]))
        parts += [f"own-tools generator {_short(record['own_generator_hash'])}",
                  f"tool spec {_short(record['tool_spec_hash'])} ({words})"]
    parts += [f"plan {_short(record['plan_hash'])} ({record['preset']})",
              f"{len(record['seeds'])} seeds, list {_short(record['seed_list_hash'])}"]
    return " · ".join(parts)


def section(record: Mapping[str, Any] | None, *, resumes: Sequence[str] = ()) -> list[str]:
    """`card.md`'s `## What produced it`, with the full hashes."""
    out = ["", "## What produced it", ""]
    if record is None:
        return [*out, f"Not recorded: {_not_recorded(resumes)}."]
    own = record.get("own_generator_hash") is not None
    from poisson_tasks.arms import DEFAULT_GENERATOR_VERSION

    builtin_version = DEFAULT_GENERATOR_VERSION if own else record["generator_version"]
    out += [
        "Recorded by the run before its first request.",
        "",
        f"- poisson-tasks {record['poisson_tasks_version']}, verifiers "
        f"{record['verifiers_version']}",
        f"- built-in generator `{record['builtin_generator_hash']}` (generator version "
        f"\"{builtin_version}\")",
    ]
    if own:
        words = FORMAT_WORDS.get(str(record["tool_format"]), str(record["tool_format"]))
        out += [
            f"- own-tools generator `{record['own_generator_hash']}` (generator version "
            f"\"{record['generator_version']}\")",
            f"- tool spec `{record['tool_spec_hash']}`: the canonical JSON of your tool file, "
            f"{words}; the file's own bytes hash to `{record['tool_file_sha256']}`",
        ]
    else:
        out.append("- tools: the built-in tools, made by the generator above")
    out += [
        f"- domain `{record['engine_hash']}`, vocabulary `{record['vocabulary_hash']}`",
        f"- plan `{record['plan_hash']}` (preset {record['preset']}), {len(record['seeds'])} "
        f"seeds, seed list `{record['seed_list_hash']}`",
    ]
    out += [f"- resumed with poisson-tasks {version}" for version in
            record.get("resumed_with") or ()]
    return out


# ---------------------------------------------------------------------------
# two runs compared
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Compared:
    """Two runs read on what produced them: `verdict` is `ok` (the figures are set side by
    side) or `different`; `sentence` says why; `note` is the one line on what differs without
    changing the tasks, or `None`; `changed` the record's keys whose values differ, in `KEYS`
    order, empty when a side recorded nothing."""

    verdict: str
    sentence: str
    note: str | None
    changed: tuple[str, ...]


_NOT_THE_MODEL = "so their tasks differ and a shift between them is not the model's alone"


def compare(
    names: tuple[str, str],
    records: tuple[Mapping[str, Any] | None, Mapping[str, Any] | None],
    task_ids: tuple[Mapping[str, set[str]], Mapping[str, set[str]]],
    *,
    shared_arms: Sequence[str],
    reason: str | None,
) -> Compared:
    """The answer for two runs `names` with their records (`None` for one that recorded none)
    and the task ids each holds per arm, given the arms both hold a cell of and the reason
    `calibration.comparable` gives, or `None`.  The first rule that applies gives the answer:
    a generator, the tool contract, or the tool file's bytes differ between two records; no
    arm on both; a side that recorded nothing with other task ids; what `comparable` names; two
    records with other task ids; else the same tasks the same way."""
    a, b = names
    ra, rb = records
    both = ra is not None and rb is not None
    keys: tuple[str, ...] = ()
    if ra is not None and rb is not None:
        keys = tuple(key for key in KEYS if ra.get(key) != rb.get(key))

    def different(sentence: str) -> Compared:
        return Compared("different", sentence, None, keys)

    if ra is not None and rb is not None:
        if ra["builtin_generator_hash"] != rb["builtin_generator_hash"]:
            return different(
                f"{a} and {b} were made by different generators "
                f"({_short(ra['builtin_generator_hash'])} and "
                f"{_short(rb['builtin_generator_hash'])}), {_NOT_THE_MODEL}")
        if (ra["own_generator_hash"] is None) != (rb["own_generator_hash"] is None):
            own, built_in = (a, b) if ra["own_generator_hash"] is not None else (b, a)
            return different(
                f"{a} and {b} were made by different generators ({own} on your own tools, "
                f"{built_in} on the built-in tasks), {_NOT_THE_MODEL}")
        if ra["own_generator_hash"] != rb["own_generator_hash"]:
            return different(
                f"{a} and {b} were made by different own-tools generators "
                f"({_short(ra['own_generator_hash'])} and {_short(rb['own_generator_hash'])}), "
                f"{_NOT_THE_MODEL}")
        if ra["tool_spec_hash"] != rb["tool_spec_hash"]:
            return different(
                f"{a} and {b} were made on different tool contracts (tool spec "
                f"{_short(ra['tool_spec_hash'])} and {_short(rb['tool_spec_hash'])}), "
                f"{_NOT_THE_MODEL}")
        if ra["tool_file_sha256"] != rb["tool_file_sha256"]:
            return different(
                f"{a} and {b} share one tool contract (tool spec "
                f"{_short(ra['tool_spec_hash'])}), but the file was rewritten without changing "
                "it, and tasks are drawn from the file's bytes, so their tasks differ")
    if not shared_arms:
        return different(f"{a} and {b} cannot be read side by side: no level is on both")
    ids_a, ids_b = task_ids
    same_ids = all(set(ids_a.get(arm, ())) == set(ids_b.get(arm, ())) for arm in shared_arms)
    if not both and not same_ids:
        who = f"{a} and {b}" if ra is None and rb is None else (a if ra is None else b)
        return different(
            f"{a} and {b} did not measure the same tasks, and {who} recorded nothing of what "
            f"produced it (made before poisson-tasks 0.2.0), so whether its tools or generator "
            "changed is not known")
    if reason is not None:
        return different(f"{a} and {b} cannot be read side by side: {reason}")
    if not same_ids:
        return different(f"{a} and {b} did not measure the same tasks: their [own] settings "
                         "differ")
    note: str | None = None
    if ra is None or rb is None:
        if ra is None and rb is None:
            note = (f"note: {a} and {b} were made before poisson-tasks 0.2.0 and recorded "
                    "nothing of what produced them; their task ids match, so the tasks are the "
                    "same")
        else:
            gone, kept = (a, b) if ra is None else (b, a)
            note = (f"note: {gone} was made before poisson-tasks 0.2.0 and recorded nothing of "
                    f"what produced it; its task ids match {kept}'s, so the tasks are the same")
    elif (ra["poisson_tasks_version"], ra["verifiers_version"]) != (
            rb["poisson_tasks_version"], rb["verifiers_version"]):
        note = (f"note: {a} was made with poisson-tasks {ra['poisson_tasks_version']} and "
                f"verifiers {ra['verifiers_version']}, {b} with poisson-tasks "
                f"{rb['poisson_tasks_version']} and verifiers {rb['verifiers_version']}; the "
                "generator and the tasks are the same")
    return Compared(
        "ok", f"{a} and {b} measured the same tasks the same way: compare.md sets them side by "
        "side", note, keys)


def _cell(record: Mapping[str, Any] | None, key: str) -> str:
    if record is None:
        return "not recorded"
    value = record.get(key)
    if value is None:
        return "none"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return f"`{value}`"


def table(names: tuple[str, str],
          records: tuple[Mapping[str, Any] | None, Mapping[str, Any] | None],
          changed: Sequence[str]) -> list[str]:
    """`compare.md`'s `## What produced each`: a row per key of the record with both values,
    the rows that differ marked."""
    a, b = names
    out = ["## What produced each", "", f"| what | {a} | {b} | |", "|---|---|---|---|"]
    for key in KEYS:
        mark = "differs" if key in changed else ""
        out.append(f"| {key} | {_cell(records[0], key)} | {_cell(records[1], key)} | {mark} |")
    return out
