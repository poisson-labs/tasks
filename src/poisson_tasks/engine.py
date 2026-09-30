"""The domain engine: a deterministic state machine over one record domain.

The invariants this file is built against are E1-E10, tested in `tests/test_tg_m1_engine.py`;
where a requirement could not be used as written, that file's module docstring is
authoritative.

Three shapes the requirements name but do not define, decided here:

* **`DomainState` carries the scenario.**  The interface is `apply(state, call)`, with no
  scenario and no spec argument, and stage 1 has to check the entry code the scenario
  gave a record while every transition has to derive a token from the scenario's token
  key.  Neither is reachable from the records alone, so the state carries the scenario
  it was initialised from.  The tests anticipate the field: their hand-built state pairs
  rebuild a `DomainState` by carrying over every dataclass field beyond `records` and
  `next_seq`.  The escape hatch, if a later module wants the state free of it, is to
  pass an `EngineSpec`-like context to `apply` -- which changes the interface's signature.
* **Precedence: the stage precondition is decided before the argument.**  A stage-3
  tool aimed at a record standing at stage 1 is `not_ready` whatever token it carries,
  because no token could have been right for it.  The record must be addressable first,
  so a missing or non-string `record_id` is `bad_args` and an absent record is
  `no_such_rec`, both ahead of the precondition; the rest of the schema is checked
  after it.
* **The chain token** is `blake2b(class, id, stage)` keyed by the sha256 of the
  scenario's token key, rendered as 32 lowercase hex characters.  The sha256 step is
  what lets a scenario carry a token key of any length, since blake2b caps its key at
  64 bytes.

`apply` is pure: no clock, no RNG, no IO, no environment, no network.  The vocabulary
table is read once, at import, into the module's `EngineSpec`.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
from dataclasses import dataclass
from typing import Any

__all__ = [
    "EngineSpec",
    "Scenario",
    "DomainState",
    "init_state",
    "apply",
    "replay",
    "mutations",
    "engine_hash",
]

_TABLE_PATH = pathlib.Path(__file__).resolve().parent / "data" / "vocabulary-v2.json"

# The three record fields E7 names.  Their order here is not the order `mutations`
# reports: that one is sorted, because E1 makes every output deterministic.
_RECORD_FIELDS = ("stage", "token", "audit")

# `engine_hash`'s domain separator.  It changes only if the hash construction changes,
# which would be a new engine version anyway.  Its spelling is deliberately not the
# package's: these bytes are hash input, and the 2026-09-22 rename left them alone.
_HASH_DOMAIN = b"task-generator/engine_hash/1\n"

_RecordKey = tuple[str, str]


@dataclass(frozen=True)
class _Record:
    """One ledger record.  Keyed by `(class, id)` in the state, never by id alone."""

    stage: int
    token: str | None
    audit: int


@dataclass(frozen=True)
class _ToolDef:
    """One entry of the tool block: what E6 and E9 make their statements about."""

    name: str
    description: str
    parameters: dict[str, str]


@dataclass(frozen=True)
class Scenario:
    """What the engine reads of a scenario, and nothing else.

    `records` maps `(class, id)` to the stage-1 entry code that record accepts.
    `token_key` keys E3's hash.  `visible_items` are the catalogue item codes the read
    tools can see.  Nothing here is drawn from a seed: drawing a scenario is `knobs.py`'s,
    and `seq_start` is an argument to `init_state`, never a field here (N1's scope).
    """

    records: dict[_RecordKey, str]
    token_key: bytes
    visible_items: tuple[str, ...]


@dataclass(frozen=True)
class DomainState:
    """The records beside the sequence counter, plus the scenario.

    E4 is a statement about `records`; E5 is a statement about `next_seq`.  Keeping
    them apart is what stops the two invariants contradicting each other.  `scenario`
    is neither: it is the immutable context `apply` reads and never writes, and it is
    equal in every state derived from one `init_state`.
    """

    records: dict[_RecordKey, _Record]
    next_seq: int
    scenario: Scenario


@dataclass(frozen=True)
class EngineSpec:
    """Frozen.  The stage list, ledger classes, record schema, orthogonal tool set,
    vocabulary version and `L_obs`, all derived from the frozen vocabulary table.

    Nothing here validates the table.  `engine_hash`'s "if" direction has to be able to
    hash a table with any single entry changed, including entries that would make an
    unusable engine, so validation would turn E10's test into an exception.  The table
    is validated by the tests' VT rows instead, against the one table that ships.
    """

    table: dict[str, Any]
    canonical: str
    tools: tuple[_ToolDef, ...]
    stage_names: tuple[str, ...]
    qualifiers: tuple[str, ...]
    stage_tools: dict[str, tuple[int, str]]
    read_tools: dict[str, str]
    parameters: dict[str, tuple[str, ...]]
    parameter_names: dict[str, str]
    catalogue_values: dict[str, Any]
    page_keys: frozenset[str]
    status_codes: tuple[str, ...]
    layout: dict[str, Any]
    L_obs: int
    engine_version: str
    vocabulary_version: str

    @classmethod
    def from_mapping(cls, mapping: dict[str, Any]) -> EngineSpec:
        """Build a spec from a vocabulary table.  Not public, so not in `__all__`."""
        canonical = json.dumps(mapping, sort_keys=True, separators=(",", ":"))
        table: dict[str, Any] = json.loads(canonical)
        families = table["tool_families"]
        templates = table["description_templates"]
        stage_names = tuple(table["stage_names"])
        qualifiers = tuple(table["qualifiers"])
        parameters = {
            family: tuple(name for name, _type in families[family]["parameters"])
            for family in ("stage_first", "stage_chain", "read")
        }
        schemas = {
            family: {name: kind for name, kind in families[family]["parameters"]}
            for family in ("stage_first", "stage_chain", "read")
        }

        tools: list[_ToolDef] = []
        stage_tools: dict[str, tuple[int, str]] = {}
        for index, stage in enumerate(stage_names):
            for qualifier in qualifiers:
                name = f"{table['write_verb']}_{stage}_{qualifier}"
                if index == 0:
                    family = "stage_first"
                    description = templates["stage_first"].format(qualifier=qualifier)
                else:
                    family = "stage_chain"
                    previous = f"{table['write_verb']}_{stage_names[index - 1]}_{qualifier}"
                    description = templates["stage_chain"].format(previous_tool=previous)
                stage_tools[name] = (index, qualifier)
                tools.append(_ToolDef(name, description, dict(schemas[family])))

        read_tools: dict[str, str] = {}
        for verb, facet in zip(table["read_verbs"], table["facets"], strict=False):
            name = f"{verb}_{facet}"
            read_tools[name] = facet
            tools.append(
                _ToolDef(name, templates["read"].format(facet=facet), dict(schemas["read"]))
            )

        return cls(
            table=table,
            canonical=canonical,
            tools=tuple(tools),
            stage_names=stage_names,
            qualifiers=qualifiers,
            stage_tools=stage_tools,
            read_tools=read_tools,
            parameters=parameters,
            parameter_names=dict(table["parameter_names"]),
            catalogue_values=table["catalogue_values"],
            page_keys=frozenset(table["page_keys"]),
            status_codes=tuple(table["status_codes"]),
            layout=table["observation_layout"],
            L_obs=table["L_obs"],
            engine_version=table["engine_version"],
            vocabulary_version=table["vocabulary_version"],
        )

    @classmethod
    def load(cls, path: str | pathlib.Path | None = None) -> EngineSpec:
        """Read the frozen table from disk.  Not public, so not in `__all__`.

        The only file read in this module, and it happens once, at import.  `apply`
        never reaches it: E1's static clause asserts exactly that.
        """
        source = pathlib.Path(path) if path is not None else _TABLE_PATH
        return cls.from_mapping(json.loads(source.read_text(encoding="ascii")))


_SPEC = EngineSpec.load()

_PARAM_RECORD = _SPEC.parameter_names["record"]
_PARAM_ENTRY = _SPEC.parameter_names["entry"]
_PARAM_TOKEN = _SPEC.parameter_names["token"]
_PARAM_ITEM = _SPEC.parameter_names["item"]
_PARAM_PAGE = _SPEC.parameter_names["page"]

_OK = "ok"
_NO_SUCH_TOOL = "no_such_tool"
_NO_SUCH_REC = "no_such_rec"
_BAD_ARGS = "bad_args"
_BAD_TOKEN = "bad_token"
_BAD_ENTRY = "bad_entry"
_NOT_READY = "not_ready"
_NO_SUCH_ITEM = "no_such_item"
_NO_SUCH_PAGE = "no_such_page"

# Every status this module can emit.  E6 closes the vocabulary, so the set the engine
# can produce and the set the table declares have to be the same set, and a drift
# between them is an import-time failure rather than a silent E6 violation.
_EMITTED_STATUS = (
    _OK,
    _NO_SUCH_TOOL,
    _NO_SUCH_REC,
    _BAD_ARGS,
    _BAD_TOKEN,
    _BAD_ENTRY,
    _NOT_READY,
    _NO_SUCH_ITEM,
    _NO_SUCH_PAGE,
)
if set(_EMITTED_STATUS) != set(_SPEC.status_codes):
    raise ValueError(
        "the engine's status codes and the frozen table's have drifted: "
        f"engine-only {sorted(set(_EMITTED_STATUS) - set(_SPEC.status_codes))}, "
        f"table-only {sorted(set(_SPEC.status_codes) - set(_EMITTED_STATUS))}"
    )

_Outcome = tuple[str, str, dict[_RecordKey, _Record]]


def _error_payload() -> str:
    """The fixed filler an error observation carries in place of a token or a value."""
    payload: str = _SPEC.layout["error_payload"]
    return payload


def _chain_token(token_key: bytes, qualifier: str, record: str, stage: int) -> str:
    """E3's keyed hash of `(token key, record, stage)`, as fixed-width lowercase hex.

    The key is hashed to a fixed 32 bytes first, so a scenario may carry a token key of
    any length: blake2b refuses a key over 64 bytes.
    """
    key = hashlib.sha256(token_key).digest()
    message = f"{qualifier}\x1f{record}\x1f{stage}".encode("ascii")
    width: int = _SPEC.layout["token_hex_chars"]
    return hashlib.blake2b(message, key=key, digest_size=width // 2).hexdigest()


def _well_formed(args: dict[str, Any], family: str) -> bool:
    """The tool's schema: exactly its parameters, each one a string."""
    expected = _SPEC.parameters[family]
    if set(args) != set(expected):
        return False
    return all(isinstance(args[name], str) for name in expected)


def _stage_call(
    state: DomainState, seq: int, stage: int, qualifier: str, args: dict[str, Any]
) -> _Outcome:
    """One stage transition, or the reason it was refused.

    The order is the precedence this module fixes: address the record, then the stage
    precondition, then the schema, then the argument's value.
    """
    record_id = args.get(_PARAM_RECORD)
    if not isinstance(record_id, str):
        return _BAD_ARGS, _error_payload(), state.records
    key = (qualifier, record_id)
    record = state.records.get(key)
    if record is None:
        # never redirected to the same id in another class: the class is in the key
        return _NO_SUCH_REC, _error_payload(), state.records
    if record.stage != stage:
        return _NOT_READY, _error_payload(), state.records
    family = "stage_first" if stage == 0 else "stage_chain"
    if not _well_formed(args, family):
        return _BAD_ARGS, _error_payload(), state.records
    if stage == 0:
        if args[_PARAM_ENTRY] != state.scenario.records[key]:
            return _BAD_ENTRY, _error_payload(), state.records
    elif args[_PARAM_TOKEN] != record.token:
        return _BAD_TOKEN, _error_payload(), state.records
    token = _chain_token(state.scenario.token_key, qualifier, record_id, stage + 1)
    records = dict(state.records)
    records[key] = _Record(stage=stage + 1, token=token, audit=seq)
    return _OK, token, records


def _read_call(state: DomainState, facet: str, args: dict[str, Any]) -> _Outcome:
    """One orthogonal read.  It never touches the records (E7); the counter still moves."""
    if not _well_formed(args, "read"):
        return _BAD_ARGS, _error_payload(), state.records
    item = args[_PARAM_ITEM]
    if item not in state.scenario.visible_items:
        return _NO_SUCH_ITEM, _error_payload(), state.records
    if args[_PARAM_PAGE] not in _SPEC.page_keys:
        # the page key is validated and then not read: it is what makes a read call's
        # argument size matchable to a stage call's (N9), not a selector
        return _NO_SUCH_PAGE, _error_payload(), state.records
    row = _SPEC.catalogue_values.get(item)
    value = row.get(facet) if isinstance(row, dict) else None
    if not isinstance(value, str):
        return _NO_SUCH_ITEM, _error_payload(), state.records
    return _OK, value, state.records


def _outcome(state: DomainState, seq: int, tool_name: Any, args: Any) -> _Outcome:
    """Resolve a call to `(status, payload, records)`.  Total over any `(name, args)`."""
    stage_entry = _SPEC.stage_tools.get(tool_name) if isinstance(tool_name, str) else None
    facet = _SPEC.read_tools.get(tool_name) if isinstance(tool_name, str) else None
    if stage_entry is None and facet is None:
        return _NO_SUCH_TOOL, _error_payload(), state.records
    if not isinstance(args, dict):
        return _BAD_ARGS, _error_payload(), state.records
    if stage_entry is not None:
        return _stage_call(state, seq, stage_entry[0], stage_entry[1], args)
    return _read_call(state, str(facet), args)


def _render(seq: int, status: str, payload: str) -> str:
    """The fixed-width observation: `seq`, a status code and a token or payload.

    Every field is fixed width by construction, so no observation is ever short of
    `L_obs` and none is padded up to it.  A field that will not fit raises rather than
    rendering at the wrong width: a silently truncated status would still be `L_obs`
    bytes and would break E6, and a `seq` that overflowed its field would break E5's
    "no gap and no repeat".  Neither is reachable from a call -- both mean the table and
    this module have drifted, or a caller started an episode past the counter's ceiling.
    """
    layout = _SPEC.layout
    seq_width: int = layout["seq_width"]
    status_width: int = layout["status_width"]
    payload_width: int = layout["payload_width"]
    rendered_seq = str(seq).rjust(seq_width, layout["seq_fill"])
    if len(rendered_seq) != seq_width:
        raise ValueError(f"seq {seq} does not fit the {seq_width}-byte field")
    if len(status) > status_width:
        raise ValueError(f"status {status!r} does not fit the {status_width}-byte field")
    if len(payload) != payload_width:
        raise ValueError(f"payload {payload!r} is not {payload_width} bytes")
    rendered_status = status.ljust(status_width, layout["status_fill"])
    separator: str = layout["separator"]
    return separator.join((rendered_seq, rendered_status, payload))


def init_state(scenario: Scenario, seq_start: int) -> DomainState:
    """The state a scenario starts in: every record at stage 0, the counter at `seq_start`.

    `seq_start` is its own argument and never a scenario field, so N14 can vary it by
    arm while N1 holds the scenario equal across arms.
    """
    records = {key: _Record(stage=0, token=None, audit=0) for key in scenario.records}
    return DomainState(records=records, next_seq=seq_start, scenario=scenario)


def apply(state: DomainState, call: tuple[str, Any]) -> tuple[DomainState, str]:
    """Run one call.  A pure function of `(state, call)`, total over any call.

    Every call advances the counter, errors included (E5).  An error leaves the records
    byte-identical (E4); a transition moves the addressed record's stage, token and
    audit field and nothing else (E7).
    """
    tool_name, args = call
    seq = state.next_seq
    status, payload, records = _outcome(state, seq, tool_name, args)
    after = DomainState(records=records, next_seq=seq + 1, scenario=state.scenario)
    return after, _render(seq, status, payload)


def replay(
    scenario: Scenario, calls: list[tuple[str, Any]], seq_start: int
) -> tuple[DomainState, list[str]]:
    """Fold `apply` over `calls` from `init_state(scenario, seq_start)`.

    Calls are numbered `seq_start, seq_start + 1, ...` in list order.  The caller sorts
    the sampled calls by the `seq` in their tool messages before calling this (X4, in
    `tasks.py` and the export); `replay` numbers what it is handed, in the order it is handed.
    """
    state = init_state(scenario, seq_start)
    observations: list[str] = []
    for call in calls:
        state, observation = apply(state, call)
        observations.append(observation)
    return state, observations


def mutations(state_a: DomainState, state_b: DomainState) -> list[tuple[str, str, str]]:
    """Every record field that differs, as sorted `(class, id, field)` triples.

    The class is in the key because E7's cross-class clause cannot be stated without it:
    a call names a class through its tool's qualifier and is never redirected, so
    the verifier's `collateral_mutation` has to be able to tell a mutation in another ledger
    class from one in the target's.  A record present in one state and absent from the
    other counts as differing in every field; the engine never adds or drops a record,
    so that case only arises between states built by hand.
    """
    changed: list[tuple[str, str, str]] = []
    for key in set(state_a.records) | set(state_b.records):
        before = state_a.records.get(key)
        after = state_b.records.get(key)
        for name in _RECORD_FIELDS:
            if before is None or after is None:
                changed.append((key[0], key[1], name))
            elif getattr(before, name) != getattr(after, name):
                changed.append((key[0], key[1], name))
    return sorted(changed)


def engine_hash(spec: EngineSpec) -> str:
    """A digest over the spec, the vocabulary and the engine version.

    It moves if any one of them changes, and for nothing else: not the process, not
    `PYTHONHASHSEED`, not the insertion order of a table built two ways, and not the
    path the table was loaded from.  The canonical form is the table's JSON with every
    key sorted, at every depth, which is what makes the order and path irrelevant; the
    engine and vocabulary versions are entries in that table.
    """
    return hashlib.sha256(_HASH_DOMAIN + spec.canonical.encode("utf-8")).hexdigest()
