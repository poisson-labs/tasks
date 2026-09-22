"""The frozen tests for TG-M1, the domain engine: E1-E10, P1, T1-T3, VT1-VT4.

Frozen on 2026-09-11 against spec v0 rev. 3.2 with the amendments of that date
(TG-ADR-35 and TG-ADR-36). The module is written against this file, which is not
edited to suit it. Where the spec's text could not be used as written, this
docstring is authoritative.

The public surface these tests pin
----------------------------------
`task_generator.engine.__all__` is exactly::

    EngineSpec  Scenario  DomainState  init_state  apply  replay  mutations  engine_hash

`task_generator.tokenizer.__all__` is exactly::

    reference_encoding  count_tokens

Shapes the spec names but does not define
-----------------------------------------
* ``Scenario(records, token_key, visible_items)``, frozen, with a public
  constructor this file calls by hand.  ``records`` maps ``(qualifier, record_id)``
  to the stage-1 entry code that record accepts.  ``token_key`` is the key for
  E3's keyed hash.  ``visible_items`` are the catalogue item codes reads can see.
  It draws nothing from a seed: that is TG-M2's (finding 15).
* ``DomainState`` has ``.records`` and ``.next_seq`` (TG-ADR-35).  ``.records``
  maps ``(qualifier, record_id)`` to a record with ``.stage`` (0-8), ``.token``
  (the chain token the last successful transition emitted, or ``None`` at stage
  0) and ``.audit`` (the ``seq`` of that transition, 0 before any: TG-ADR-36).
* A ``call`` is the 2-tuple ``(tool_name, args)`` with ``args`` a ``dict``.
  ``apply`` is total over any such pair, including names outside the block and
  malformed arguments (finding 5).
* An ``observation`` is an ASCII ``str`` of exactly ``L_obs`` bytes.
* ``EngineSpec.load(path=None)`` and ``EngineSpec.from_mapping(mapping)`` build a
  spec; neither is public, so neither is in ``__all__``.  ``init_state`` and
  ``apply`` take no spec argument, exactly as the spec writes them, so the spec
  reaches them through the module and not through a file read inside ``apply``
  (finding 11).
* ``mutations`` returns ``(class, id, field)`` triples in sorted order.  Sorted,
  because E1 makes every output deterministic and this is the one natural order;
  the class is in the key because E7's cross-class clause cannot be stated
  without it (TG-ADR-36).

What is deliberately not tested here
------------------------------------
E8's live half.  ``replay`` is checked against the left fold of ``apply``, which
is all TG-M1 can see.  The comparison against the live toolset is A8, run per
episode in TG-M5 (finding 7).
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
import os
import pathlib
import subprocess
import sys
import textwrap

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# --------------------------------------------------------------------------
# frozen literals
# --------------------------------------------------------------------------

DATA = pathlib.Path(__file__).resolve().parent.parent / "src" / "task_generator" / "data"
TABLE_PATH = DATA / "vocabulary-v2.json"
ENCODING_PATH = DATA / "o200k_base.tiktoken"

# T1: the expected_hash tiktoken 0.14.0 pins for o200k_base, read from
# tiktoken_ext/openai_public.py at step zero.  An independent source.
ENCODING_SHA256 = "446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d"
# VT4: the table as it was frozen, at commit zero.
TABLE_SHA256 = "9f3a8c4f4711574e947ec8b3396ff552c9b7aa730fbb5d565db4f10776653037"

ENGINE_EXPORTS = (
    "EngineSpec", "Scenario", "DomainState",
    "init_state", "apply", "replay", "mutations", "engine_hash",
)
TOKENIZER_EXPORTS = ("reference_encoding", "count_tokens")

# E9, finding 13.  Checked case-insensitively, as a substring.  DENY applies to
# every authored table string except the ones that must carry digits; DENY_NAMES
# is this file's extension and applies to the stage names and tool names only.
DENY = (
    "first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth",
    "one", "two", "three", "four", "five", "six", "seven", "eight",
    "zero", "nine", "ninth", "ten", "tenth",
    "next", "previous", "prior", "final", "last", "initial", "start", "begin", "end",
    "pre", "post", "step", "stage", "phase", "then", "after", "before",
)
DENY_NAMES = DENY + (
    "order", "sequence", "index", "rank", "follow", "precede", "succeed",
    "earlier", "later", "subsequent", "ultimate", "terminal",
    "head", "tail", "front", "rear", "chain", "queue", "cursor",
)

# T3: minted at step zero from tiktoken.get_encoding("o200k_base"), which is an
# independent source and not the offline encoder's own output read back.  No test
# in this file touches the network.
PINNED_TOKEN_COUNTS = (
    ('submit', 1),
    ('review', 1),
    ('sample', 1),
    ('measure', 1),
    ('invoice', 1),
    ('payment', 1),
    ('salary', 1),
    ('lookup', 1),
    ('fetch', 1),
    ('region', 1),
    ('volume', 1),
    ('ok', 1),
    ('no_such_tool', 4),
    ('back', 1),
    ('best', 1),
    ('user-right-pass-product', 4),
    ('case-good-high-file', 4),
    ('3183630de2a110fb56814e2b8b4a506d', 19),
    ('647970288705b44cbdd0699c2c5a0ea4', 18),
    ('submit_review_invoice', 3),
    ('lookup_region', 2),
    ('requires the token returned by submit_review_invoice', 8),
    ('returns the region field of the named catalogue item', 9),
    ('requires the entry code stated in the request for a invoice record', 12),
    ('able-account-active-address', 4),
    (' access-action-added-adjust', 4),
    ('000001 ok           00000000000000000000000000000000', 16),
)

TABLE = json.loads(TABLE_PATH.read_text())
LAYOUT = TABLE["observation_layout"]
L_OBS = TABLE["L_obs"]
BAND_LO, BAND_HI = TABLE["token_band"]

# --------------------------------------------------------------------------
# the shared helper
# --------------------------------------------------------------------------


def stage_tool(stage_name: str, qualifier: str) -> str:
    return f"{TABLE['write_verb']}_{stage_name}_{qualifier}"


def read_tool(verb: str, facet: str) -> str:
    return f"{verb}_{facet}"


def all_stage_tools() -> list[str]:
    return [stage_tool(s, q) for s in TABLE["stage_names"] for q in TABLE["qualifiers"]]


def all_read_tools() -> list[str]:
    return [read_tool(v, f) for v, f in zip(TABLE["read_verbs"], TABLE["facets"])]


def record_id(words) -> str:
    return TABLE["record_id_separator"].join(words)


def obs_fields(observation: str) -> tuple[str, str, str]:
    """Split an observation into (seq, status, payload) by the declared widths."""
    w, sw, pw = LAYOUT["seq_width"], LAYOUT["status_width"], LAYOUT["payload_width"]
    seq = observation[:w]
    status = observation[w + 1 : w + 1 + sw]
    payload = observation[w + 2 + sw : w + 2 + sw + pw]
    return seq, status, payload


def obs_status(observation: str) -> str:
    return obs_fields(observation)[1].strip()


def obs_seq(observation: str) -> int:
    return int(obs_fields(observation)[0])


def records_bytes(state, audit: bool = True) -> bytes:
    """A canonical rendering of the records alone, for E4's and E7's byte equality.

    Built from the public fields only, so it is independent of whatever `mutations`
    reports: E4 and E7 assert on both, and a `mutations` that missed a change
    cannot hide one from this.
    """
    rows = []
    for (cls, rid), rec in sorted(state.records.items()):
        tail = f"|{rec.audit}" if audit else ""
        rows.append(f"{cls}|{rid}|{rec.stage}|{rec.token}{tail}")
    return "\n".join(rows).encode("ascii")


def make_scenario(n_records: int = 4, token_key: bytes = b"oracle-key-a", *,
                  split: str = "eval", shared_id: bool = False, n_items: int = 4):
    """Build a Scenario by hand.  No seed is drawn: that is TG-M2's (finding 15)."""
    from task_generator.engine import Scenario

    words = TABLE["record_id_words"][split]
    quals = TABLE["qualifiers"]
    codes = TABLE["entry_codes"]
    records = {}
    for i in range(n_records):
        rid = record_id([words[(i * 37 + k * 11) % 256] for k in range(4)])
        records[(quals[i % len(quals)], rid)] = codes[i % len(codes)]
    if shared_id:
        # one id present in two classes: the only shape that can expose a redirect
        (first_cls, first_rid) = next(iter(records))
        other = quals[(quals.index(first_cls) + 1) % len(quals)]
        records[(other, first_rid)] = codes[1]
    return Scenario(
        records=records,
        token_key=token_key,
        visible_items=tuple(TABLE["catalogue_items"][:n_items]),
    )


def a_record(scenario):
    return sorted(scenario.records)[0]


def advance(state, scenario, cls, rid, upto):
    """Drive a record from its current stage to `upto` through the public surface.

    The scenario is passed in rather than read back off the state: this file
    already holds it, and asking DomainState for it would invent a surface the
    spec does not name.
    """
    from task_generator.engine import apply

    obs = []
    while state.records[(cls, rid)].stage < upto:
        rec = state.records[(cls, rid)]
        name = stage_tool(TABLE["stage_names"][rec.stage], cls)
        if rec.stage == 0:
            args = {"record_id": rid, "entry_code": scenario.records[(cls, rid)]}
        else:
            args = {"record_id": rid, "chain_token": rec.token}
        state, o = apply(state, (name, args))
        assert obs_status(o) == "ok", (name, o)
        obs.append(o)
    return state, obs


def a_valid_first_call(cls, rid, entry_code):
    return (stage_tool(TABLE["stage_names"][0], cls),
            {"record_id": rid, "entry_code": entry_code})


def a_valid_read(scenario):
    return (all_read_tools()[0], {"item_code": scenario.visible_items[0],
                                  "page_key": TABLE["page_keys"][0]})


def rejected_calls(scenario, at_stage_1, at_stage_0):
    """One call per rejection reason, over two records the caller has positioned.

    Two are needed, not one.  `bad_token` needs a call whose stage precondition
    passes so that the token is what is rejected, which takes a record standing at
    stage 1; `bad_entry` needs a stage-1 tool whose precondition passes, which
    takes a record still at stage 0; and `not_ready` needs one whose precondition
    fails.

    Precedence, which the spec leaves open and these tests therefore fix: the
    stage precondition is decided before the argument.  A stage-3 tool aimed at a
    record standing at stage 1 is `not_ready` whatever token it carries, because
    no token could have been right for it (TG-ADR-36).
    """
    cls1, rid1 = at_stage_1
    cls0, rid0 = at_stage_0
    entry0 = scenario.records[at_stage_0]
    entry1 = scenario.records[at_stage_1]
    reader = all_read_tools()[0]
    good_item = scenario.visible_items[0]
    return [
        ("no_such_tool", ("submit_not_a_tool_at_all",
                          {"record_id": rid1, "entry_code": entry1})),
        ("no_such_rec", (stage_tool(TABLE["stage_names"][0], cls0),
                         {"record_id": record_id(["able", "able", "able", "able"]),
                          "entry_code": entry0})),
        ("bad_args", (stage_tool(TABLE["stage_names"][1], cls1), {"record_id": rid1})),
        ("bad_entry", (stage_tool(TABLE["stage_names"][0], cls0),
                       {"record_id": rid0, "entry_code": "not" + entry0})),
        ("bad_token", (stage_tool(TABLE["stage_names"][1], cls1),
                       {"record_id": rid1, "chain_token": "f" * 32})),
        ("not_ready", (stage_tool(TABLE["stage_names"][2], cls1),
                       {"record_id": rid1, "chain_token": "f" * 32})),
        ("no_such_item", (reader, {"item_code": "no-such-item-code",
                                   "page_key": TABLE["page_keys"][0]})),
        ("no_such_page", (reader, {"item_code": good_item, "page_key": "e" * 32})),
    ]


@st.composite
def call_sequences(draw, scenario=None, length=None):
    """Mixed valid and invalid calls over a hand-built scenario."""
    n = length if length is not None else draw(st.integers(min_value=1, max_value=12))
    quals = TABLE["qualifiers"]
    stages = TABLE["stage_names"]
    calls = []
    for _ in range(n):
        kind = draw(st.sampled_from(["stage", "read", "junk"]))
        if kind == "stage":
            cls = draw(st.sampled_from(quals))
            s = draw(st.integers(min_value=0, max_value=7))
            rid = draw(st.sampled_from(sorted({r for _, r in (scenario or {}).records})))\
                if scenario else "able-account-active-address"
            key = "entry_code" if s == 0 else "chain_token"
            val = draw(st.sampled_from(TABLE["entry_codes"])) if s == 0 else draw(
                st.text(alphabet="0123456789abcdef", min_size=32, max_size=32))
            calls.append((stage_tool(stages[s], cls), {"record_id": rid, key: val}))
        elif kind == "read":
            calls.append((draw(st.sampled_from(all_read_tools())),
                          {"item_code": draw(st.sampled_from(TABLE["catalogue_items"])),
                           "page_key": draw(st.sampled_from(TABLE["page_keys"]))}))
        else:
            calls.append((draw(st.sampled_from(["nope", "submit_", "", "lookup"])), {}))
    return calls


SLOW = settings(max_examples=40, deadline=None,
                suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])

# --------------------------------------------------------------------------
# E1 Purity
# --------------------------------------------------------------------------

_CHILD = textwrap.dedent(
    """
    import hashlib, json, sys
    import task_generator.engine as E
    sys.path.insert(0, {tests!r})
    import test_tg_m1_engine as O

    scenario = O.make_scenario()
    state = E.init_state(scenario, 41)
    out = []
    for name, args in json.loads({calls!r}):
        state, obs = E.apply(state, (name, tuple(args) if isinstance(args, list) else args))
        out.append(obs)
    print(json.dumps({{
        "file": E.__file__,
        "digest": hashlib.sha256(
            ("".join(out)).encode("ascii") + O.records_bytes(state)).hexdigest(),
        "next_seq": state.next_seq,
    }}))
    """
)


def _run_child(calls, hashseed):
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = hashseed
    src = _CHILD.format(tests=str(pathlib.Path(__file__).resolve().parent),
                        calls=json.dumps(calls))
    p = subprocess.run([sys.executable, "-c", src], capture_output=True, text=True, env=env)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


def test_e1_two_processes_agree_byte_for_byte():
    """E1: two runs over the same inputs are byte-identical.

    Two fresh interpreters at different PYTHONHASHSEED values, so set and dict
    iteration order cannot leak into the bytes (finding 11).
    """
    import task_generator.engine as engine

    calls = [
        [stage_tool(TABLE["stage_names"][0], TABLE["qualifiers"][0]),
         {"record_id": record_id([TABLE["record_id_words"]["eval"][(0 * 37 + k * 11) % 256]
                                  for k in range(4)]),
          "entry_code": TABLE["entry_codes"][0]}],
        [all_read_tools()[2], {"item_code": TABLE["catalogue_items"][1],
                               "page_key": TABLE["page_keys"][3]}],
        ["submit_not_a_tool_at_all", {}],
        [all_read_tools()[0], {"item_code": TABLE["catalogue_items"][0],
                               "page_key": TABLE["page_keys"][0]}],
    ]
    a = _run_child(calls, "0")
    b = _run_child(calls, "1")
    # mutation-harness fact 1: if the children import the original tree instead of
    # the copy under test, every row of a mutation table reads "survives".
    assert a["file"] == engine.__file__ == b["file"]
    assert a["digest"] == b["digest"]
    assert a["next_seq"] == b["next_seq"]


def test_e1_repeat_within_one_process_agrees():
    """E1: no process-local state.

    NOT INDEPENDENT, and kept anyway.  It compares the engine with itself inside
    one interpreter, so it cannot catch anything a fresh process would: state
    inherited at import, an environment variable read at module load, a value
    that resets per process.  Cross-process determinism rests on
    test_e1_two_processes_agree_byte_for_byte and on E10's "only if" direction,
    not on this test.  It is here because it is the only clause that catches a
    module-level counter, which two fresh processes agree on and therefore
    cannot see (finding 11, and Taylor's review of 2026-09-11).
    """
    from task_generator.engine import apply, init_state

    scenario = make_scenario()
    cls, rid = a_record(scenario)

    def once():
        state = init_state(scenario, 1)
        state, obs = advance(state, scenario, cls, rid, 2)
        state, o = apply(state, ("submit_not_a_tool_at_all", {}))
        return "".join(obs) + o, records_bytes(state)

    first = once()
    # unrelated calls in between, which a module-level counter would number
    unrelated = make_scenario(token_key=b"unrelated")
    interference = init_state(unrelated, 900)
    for _ in range(5):
        interference, _ = apply(interference, a_valid_read(unrelated))
    second = once()
    assert first == second


def test_e1_engine_source_has_no_impurity():
    """E1's static clause, as an `ast` walk and never a substring match on source.

    The rule, restated: `apply` is a pure function of `(state, call)`.  The engine
    module may not reach a clock, a random source, the filesystem, the process
    environment or the network.  So it may not import or bind any of the names in
    FORBIDDEN_MODULES, and may not call any of FORBIDDEN_CALLS.  The table is
    loaded into an EngineSpec once and `apply` opens no file (finding 11).
    """
    import task_generator.engine as engine

    # Never reached at all: a clock, a random source, the environment, the network.
    FORBIDDEN_MODULES = {
        "time", "datetime", "random", "secrets", "os", "socket", "ssl",
        "urllib", "http", "requests", "subprocess", "uuid", "platform", "getpass",
    }
    # Reached only where the table is read, which is EngineSpec.load and nowhere
    # else: finding 11 says the table is loaded into EngineSpec once, so a blanket
    # ban would make the loader unwritable. `apply` must not touch these, and must
    # not call the loader either.
    FILESYSTEM_MODULES = {"pathlib", "io", "shutil", "tempfile", "importlib"}
    FORBIDDEN_CALLS = {"input", "eval", "exec", "compile", "__import__", "globals", "vars"}
    LOADER = "load"

    tree = ast.parse(pathlib.Path(engine.__file__).read_text())
    functions = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    assert "apply" in functions, "engine.py defines no apply"

    def imported(node):
        for n in ast.walk(node):
            if isinstance(n, ast.Import):
                for alias in n.names:
                    yield alias.name.split(".")[0]
            elif isinstance(n, ast.ImportFrom) and n.module:
                yield n.module.split(".")[0]

    def called(node):
        for n in ast.walk(node):
            if isinstance(n, ast.Call):
                if isinstance(n.func, ast.Name):
                    yield n.func.id
                elif isinstance(n.func, ast.Attribute):
                    yield n.func.attr

    module_imports = set(imported(tree))
    assert module_imports & FORBIDDEN_MODULES == set(), \
        f"engine.py reaches a clock, an RNG, the environment or the network: " \
        f"{sorted(module_imports & FORBIDDEN_MODULES)}"
    assert not (set(called(tree)) & FORBIDDEN_CALLS), \
        f"engine.py calls an impure builtin: {sorted(set(called(tree)) & FORBIDDEN_CALLS)}"

    # the filesystem is reachable from the module, but never from apply
    apply_names = set(called(functions["apply"])) | set(imported(functions["apply"]))
    assert not (apply_names & FILESYSTEM_MODULES), \
        f"apply imports a filesystem module: {sorted(apply_names & FILESYSTEM_MODULES)}"
    assert "open" not in apply_names, "apply calls open()"
    assert LOADER not in apply_names, "apply calls the spec loader, so it reads a file"
    for helper, node in sorted(functions.items()):
        if helper in ("apply", LOADER) or helper.startswith("__"):
            continue
        if helper in set(called(functions["apply"])):
            assert "open" not in set(called(node)), f"apply reaches open() through {helper}"

# --------------------------------------------------------------------------
# E2 Fixed observation size
# --------------------------------------------------------------------------


def test_e2_every_status_code_renders_l_obs_bytes():
    """E2, exhaustive over status codes: every one renders exactly L_obs bytes."""
    from task_generator.engine import apply, init_state

    scenario = make_scenario(shared_id=False)
    at1, at0 = sorted(scenario.records)[:2]
    state = init_state(scenario, 1)
    seen = {}
    at_stage_1, ok_obs = advance(state, scenario, *at1, 1)
    seen["ok"] = ok_obs[0]
    for expected, call in rejected_calls(scenario, at1, at0):
        _, obs = apply(at_stage_1, call)
        assert obs_status(obs) == expected, (call, obs)
        seen[expected] = obs
    assert set(seen) == set(TABLE["status_codes"]), "a status code was not reached"
    for status, obs in sorted(seen.items()):
        assert obs.isascii(), status
        assert len(obs.encode("ascii")) == L_OBS, (status, len(obs), obs)


@given(payload_seed=st.integers(min_value=0, max_value=2**32 - 1))
@SLOW
def test_e2_observation_token_count_in_band(payload_seed):
    """E2: the token count under the reference tokenizer lies in the declared band.

    The band is a frozen literal minted at step zero on a 300k sample and checked
    on a disjoint 300k sample (standing rule 8).  This test draws fresh payloads,
    so it is a third sample and can disagree with both.
    """
    from task_generator.engine import apply, init_state
    from task_generator.tokenizer import count_tokens

    scenario = make_scenario(token_key=payload_seed.to_bytes(4, "big") + b"-band")
    cls, rid = a_record(scenario)
    state = init_state(scenario, (payload_seed % 900_000) + 1)
    state, obs = advance(state, scenario, cls, rid, 8)
    state, r = apply(state, a_valid_read(scenario))
    state, e = apply(state, ("submit_not_a_tool_at_all", {}))
    for o in [*obs, r, e]:
        assert len(o.encode("ascii")) == L_OBS
        assert BAND_LO <= count_tokens(o) <= BAND_HI, (count_tokens(o), o)


def test_e2_l_obs_holds_across_tool_families():
    """E2's "from any tool": all three families, success and error, and seq's width."""
    from task_generator.engine import apply, init_state

    scenario = make_scenario()
    cls, rid = a_record(scenario)
    entry = scenario.records[(cls, rid)]
    for seq_start in (1, 9, 99, 1000, 999_999 - 3):
        state = init_state(scenario, seq_start)
        state, first = apply(state, a_valid_first_call(cls, rid, entry))
        state, second = apply(state, (stage_tool(TABLE["stage_names"][1], cls),
                                      {"record_id": rid,
                                       "chain_token": state.records[(cls, rid)].token}))
        state, red = apply(state, a_valid_read(scenario))
        state, err = apply(state, ("nope", {}))
        for o in (first, second, red, err):
            assert len(o.encode("ascii")) == L_OBS, o
            assert len(obs_fields(o)[0]) == LAYOUT["seq_width"]
        assert [obs_seq(o) for o in (first, second, red, err)] == \
            [seq_start, seq_start + 1, seq_start + 2, seq_start + 3]

# --------------------------------------------------------------------------
# E3 Token chaining
# --------------------------------------------------------------------------


def test_e3_chain_requires_the_previous_stage_token():
    """E3: stage i+1 succeeds only with stage i's token, on a record at stage i.

    The stage precondition is TG-ADR-36 (finding 3): without it a stage-3 call
    carrying stage 2's token would succeed on a stage-5 record and rewind it,
    which `overshoot` and G5 both rule out by assumption.
    """
    from task_generator.engine import apply, init_state, mutations

    scenario = make_scenario(n_records=3)
    (cls, rid), (other_cls, other_rid) = sorted(scenario.records)[:2]
    entry = scenario.records[(cls, rid)]
    state = init_state(scenario, 1)
    state, _ = advance(state, scenario, cls, rid, 3)
    state, _ = advance(state, scenario, other_cls, other_rid, 3)
    good = state.records[(cls, rid)].token
    stage4 = stage_tool(TABLE["stage_names"][3], cls)

    # the right token on the right record at the right stage advances it
    after, obs = apply(state, (stage4, {"record_id": rid, "chain_token": good}))
    assert obs_status(obs) == "ok"
    assert after.records[(cls, rid)].stage == 4

    # every neighbouring wrong token is rejected and changes no record
    wrong = {
        "another record's token at the same stage":
            state.records[(other_cls, other_rid)].token,
        "an earlier stage's token on this record":
            init_state(scenario, 1).records[(cls, rid)].token or "0" * 32,
        "a well-formed token from another key":
            init_state(make_scenario(n_records=3, token_key=b"oracle-key-b"), 1)
            .records[(cls, rid)].token or "a" * 32,
        "a token of the right width but no provenance": "f" * 32,
    }
    for why, tok in wrong.items():
        rejected, obs = apply(state, (stage4, {"record_id": rid, "chain_token": tok}))
        assert obs_status(obs) == "bad_token", (why, obs)
        assert records_bytes(rejected) == records_bytes(state), why
        assert mutations(state, rejected) == [], why

    # the right token on a record already past that stage is a rewind, and refused
    past, _ = apply(state, (stage4, {"record_id": rid, "chain_token": good}))
    replayed, obs = apply(past, (stage4, {"record_id": rid, "chain_token": good}))
    assert obs_status(obs) == "not_ready", obs
    assert records_bytes(replayed) == records_bytes(past)

    # and stage 1 cannot run twice
    again, obs = apply(state, (stage_tool(TABLE["stage_names"][0], cls),
                               {"record_id": rid, "entry_code": entry}))
    assert obs_status(obs) == "not_ready", obs
    assert records_bytes(again) == records_bytes(state)

    # The precondition in full, and in both directions: with the record standing
    # at stage 3, *every* stage tool except stage 4's is refused, whatever token
    # it carries -- the record's own current token included.  Testing only the
    # rewind leaves the skip-ahead open, and a skip-ahead would reach the goal
    # stage in fewer calls than the level, which is exactly what G5 forbids.
    for offset, name in enumerate(TABLE["stage_names"]):
        if offset == 3:
            continue
        if offset == 0:
            # stage 1's tool takes the entry code, so a chain token there is a
            # schema failure and would test the wrong clause
            candidates = (("the prompt's entry code", {"entry_code": entry}),
                          ("a wrong entry code", {"entry_code": "not" + entry}))
        else:
            candidates = (("the record's current token", {"chain_token": good}),
                          ("a wrong token", {"chain_token": "f" * 32}))
        for label, arg in candidates:
            skipped, obs = apply(state, (stage_tool(name, cls), {"record_id": rid, **arg}))
            assert obs_status(obs) == "not_ready", (offset, label, obs)
            assert records_bytes(skipped) == records_bytes(state), (offset, label)
            assert mutations(state, skipped) == [], (offset, label)


def test_e3_tokens_depend_on_the_key():
    """E3: the hash is *keyed*.  Two scenarios equal but for the token key.

    This is the only clause that can catch a token derived from (record, stage)
    with the key left out.
    """
    from task_generator.engine import init_state

    a = make_scenario(n_records=6, token_key=b"oracle-key-a")
    b = make_scenario(n_records=6, token_key=b"oracle-key-b")
    assert set(a.records) == set(b.records), "the two scenarios must differ only in the key"

    def tokens(scenario):
        out = set()
        for (cls, rid) in sorted(scenario.records):
            state = init_state(scenario, 1)
            state, _ = advance(state, scenario, cls, rid, 8)
            for s in range(1, 9):
                st_ = init_state(scenario, 1)
                st_, _ = advance(st_, scenario, cls, rid, s)
                out.add(st_.records[(cls, rid)].token)
        return out

    ta, tb = tokens(a), tokens(b)
    assert len(ta) == len(tb) == 6 * 8, "tokens collide within one key"
    assert ta.isdisjoint(tb), "the key does not reach the token"


def test_e3_tokens_are_fixed_width_lowercase_hex():
    """E3: rendered as fixed-width hex."""
    from task_generator.engine import init_state

    width = LAYOUT["token_hex_chars"]
    scenario = make_scenario(n_records=3)
    for (cls, rid) in sorted(scenario.records):
        state = init_state(scenario, 1)
        for s in range(1, 9):
            state, obs = advance(state, scenario, cls, rid, s)
            tok = state.records[(cls, rid)].token
            assert len(tok) == width, (s, tok)
            assert set(tok) <= set("0123456789abcdef"), (s, tok)
            assert obs_fields(obs[-1])[2] == tok


def test_e3_no_token_appears_in_the_tool_block():
    """E3: no token is derivable from the prompt or the schemas.

    A necessary condition and not a sufficient one, stated as such: it refutes a
    token that can be copied verbatim out of the block, not one a model could
    compute.  Sufficiency is E3's key clause above.
    """
    from task_generator.engine import EngineSpec, init_state

    spec = EngineSpec.load()
    block = "\n".join(
        [json.dumps(TABLE, sort_keys=True)]
        + [f"{t.name} {t.description} {json.dumps(t.parameters, sort_keys=True)}"
           for t in spec.tools]
    )
    scenario = make_scenario(n_records=3)
    for (cls, rid) in sorted(scenario.records):
        state = init_state(scenario, 1)
        for s in range(1, 9):
            state, _ = advance(state, scenario, cls, rid, s)
            tok = state.records[(cls, rid)].token
            assert tok not in block, (cls, rid, s, tok)
            assert tok not in rid and tok not in cls

# --------------------------------------------------------------------------
# E4 Rejected calls don't mutate the records  (TG-ADR-35)
# --------------------------------------------------------------------------


@given(data=st.data())
@SLOW
def test_e4_error_calls_do_not_touch_the_records(data):
    """E4: an error leaves the records byte-identical and `mutations` empty.

    Asserted twice over, on the direct field comparison and on `mutations`.  They
    are independent: a `mutations` that missed changes could not hide one here.
    """
    from task_generator.engine import apply, init_state, mutations

    scenario = make_scenario(n_records=4)
    state = init_state(scenario, data.draw(st.integers(min_value=1, max_value=5000)))
    for call in data.draw(call_sequences(scenario)):
        before = state
        state, obs = apply(state, call)
        if obs_status(obs) != "ok":
            assert records_bytes(state) == records_bytes(before), (call, obs)
            assert mutations(before, state) == [], (call, obs)


@given(data=st.data())
@SLOW
def test_e4_error_calls_advance_next_seq_by_one(data):
    """E4 with E5: the counter is the one thing an error does change."""
    from task_generator.engine import apply, init_state

    scenario = make_scenario(n_records=4)
    state = init_state(scenario, data.draw(st.integers(min_value=1, max_value=5000)))
    for call in data.draw(call_sequences(scenario)):
        before = state
        state, obs = apply(state, call)
        if obs_status(obs) != "ok":
            assert state.next_seq == before.next_seq + 1, (call, obs)

# --------------------------------------------------------------------------
# E5 Sequence numbers  (TG-ADR-35)
# --------------------------------------------------------------------------


def test_e5_seq_numbers_every_call_from_seq_start():
    """E5: seq starts at seq_start and advances once per call, errors included."""
    from task_generator.engine import apply, init_state

    scenario = make_scenario()
    cls, rid = a_record(scenario)
    entry = scenario.records[(cls, rid)]
    # 8 is knob D's top level; H - dL + 1 is the D control's seq_start (N14)
    for seq_start in (1, 2, 8 - 1 + 1, 1234):
        state = init_state(scenario, seq_start)
        assert state.next_seq == seq_start
        calls = [a_valid_first_call(cls, rid, entry),
                 ("nope", {}),
                 a_valid_read(scenario),
                 ("submit_not_a_tool_at_all", {"record_id": rid}),
                 (stage_tool(TABLE["stage_names"][1], cls), {"record_id": rid,
                                                             "chain_token": "f" * 32})]
        seqs = []
        for call in calls:
            state, obs = apply(state, call)
            seqs.append(obs_seq(obs))
        assert seqs == list(range(seq_start, seq_start + len(calls)))
        assert state.next_seq == seq_start + len(calls)


def test_e5_counter_is_the_only_error_effect():
    """E5: on an error, (records, next_seq) differs in next_seq alone."""
    from task_generator.engine import apply, init_state

    scenario = make_scenario()
    at1, at0 = sorted(scenario.records)[:2]
    state = init_state(scenario, 7)
    state, _ = advance(state, scenario, *at1, 1)
    for _, call in rejected_calls(scenario, at1, at0):
        after, obs = apply(state, call)
        assert obs_status(obs) != "ok", call
        assert records_bytes(after) == records_bytes(state)
        assert after.next_seq == state.next_seq + 1


def test_e5_seq_start_is_an_argument_not_a_scenario_field():
    """E5: seq_start comes from the argument, never from the scenario (N1's scope).

    One scenario under two seq_starts gives observations that differ in the seq
    field and nowhere else.  This is what lets N14 vary seq_start by arm while N1
    holds the scenario equal (TG-ADR-35).
    """
    from task_generator.engine import Scenario, apply, init_state

    scenario = make_scenario()
    cls, rid = a_record(scenario)
    entry = scenario.records[(cls, rid)]
    assert not hasattr(scenario, "seq_start")
    assert "seq_start" not in getattr(Scenario, "__dataclass_fields__", {})

    def run(seq_start):
        state = init_state(scenario, seq_start)
        out = []
        for call in (a_valid_first_call(cls, rid, entry), ("nope", {}),
                     a_valid_read(scenario)):
            state, obs = apply(state, call)
            out.append(obs)
        return out, records_bytes(state, audit=False), state.records[(cls, rid)].audit

    (a_obs, a_rec, a_audit), (b_obs, b_rec, b_audit) = run(1), run(500)
    # every record field but the audit is untouched by seq_start
    assert a_rec == b_rec
    # and the audit field, being a seq, moves with seq_start by exactly the offset.
    # TG-M3 inherits this: expected_final_state is arm-dependent through seq_start,
    # or the verdict excludes the audit field. See the spec's open question and
    # gap-log entry PG-16.
    assert b_audit - a_audit == 499
    for x, y in zip(a_obs, b_obs):
        assert obs_fields(x)[1:] == obs_fields(y)[1:]
        assert obs_seq(y) - obs_seq(x) == 499


def test_e5_replay_numbers_in_list_order():
    """E5: replay numbers calls in list order from seq_start (finding 7).

    The caller sorts the sampled calls by the seq in their tool messages (X4, in
    TG-M3 and TG-M4); replay numbers what it is handed, in the order it is handed.
    """
    from task_generator.engine import replay

    scenario = make_scenario()
    cls, rid = a_record(scenario)
    entry = scenario.records[(cls, rid)]
    calls = [
        (stage_tool(TABLE["stage_names"][0], cls), {"record_id": rid, "entry_code": entry}),
        ("nope", {}),
        (all_read_tools()[0], {"item_code": TABLE["catalogue_items"][0],
                               "page_key": TABLE["page_keys"][0]}),
    ]
    for seq_start in (1, 42, 900):
        _, observations = replay(scenario, calls, seq_start)
        assert [obs_seq(o) for o in observations] == \
            [seq_start, seq_start + 1, seq_start + 2]
    # order is the list's, not the calls' own: reversing the list renumbers them
    _, forward = replay(scenario, calls, 1)
    _, backward = replay(scenario, list(reversed(calls)), 1)
    assert [obs_seq(o) for o in backward] == [1, 2, 3]
    # position 0 holds a different call in each list, so its payload differs; the
    # rejected call sits at index 1 in both and is numbered 2 in both
    assert obs_fields(forward[0])[2] != obs_fields(backward[0])[2]
    assert obs_status(forward[1]) == obs_status(backward[1]) == "no_such_tool"

# --------------------------------------------------------------------------
# E6 Closed vocabulary
# --------------------------------------------------------------------------


def test_e6_public_surface_draws_only_from_the_table():
    """E6: every name, parameter and description comes from the frozen table."""
    from task_generator.engine import EngineSpec

    spec = EngineSpec.load()
    stage_names, quals = set(TABLE["stage_names"]), set(TABLE["qualifiers"])
    verbs, facets = set(TABLE["read_verbs"]), set(TABLE["facets"])
    allowed_params = set(TABLE["parameter_names"].values())
    templates = TABLE["description_templates"]
    rendered = (
        {templates["stage_first"].format(qualifier=q) for q in quals}
        | {templates["stage_chain"].format(previous_tool=t) for t in all_stage_tools()}
        | {templates["read"].format(facet=f) for f in facets}
    )
    assert spec.tools, "the spec exposes no tools"
    for tool in spec.tools:
        if tool.name.startswith(TABLE["write_verb"] + "_"):
            _, stage, qual = tool.name.split("_", 2)
            assert stage in stage_names, tool.name
            assert qual in quals, tool.name
        else:
            verb, facet = tool.name.split("_", 1)
            assert verb in verbs and facet in facets, tool.name
        assert tool.description in rendered, tool.description
        assert set(tool.parameters) <= allowed_params, tool.parameters
    assert spec.vocabulary_version == TABLE["vocabulary_version"]
    assert spec.engine_version == TABLE["engine_version"]
    assert spec.L_obs == L_OBS


def test_e6_observation_fields_decode_to_table_values():
    """E6: the engine generates no free text, in either observation field.

    The status assertion is what catches a status code silently truncated into
    the 12-byte field; E2's byte clause cannot see that, because the truncation
    keeps the observation exactly L_obs bytes.
    """
    from task_generator.engine import apply, init_state

    codes = set(TABLE["status_codes"])
    values = {v for row in TABLE["catalogue_values"].values() for v in row.values()}
    scenario = make_scenario()
    cls, rid = a_record(scenario)
    at1, at0 = sorted(scenario.records)[1], sorted(scenario.records)[2]
    state = init_state(scenario, 1)
    state, ok = advance(state, scenario, cls, rid, 8)
    state, _ = advance(state, scenario, *at1, 1)
    observations = list(ok)
    for _, call in rejected_calls(scenario, at1, at0):
        _, obs = apply(state, call)
        observations.append(obs)
    state, red = apply(state, a_valid_read(scenario))
    observations.append(red)
    for obs in observations:
        seq, status, payload = obs_fields(obs)
        assert status.strip() in codes, obs
        assert status == status.strip().ljust(LAYOUT["status_width"], LAYOUT["status_fill"])
        assert seq.isdigit(), obs
        assert (set(payload) <= set("0123456789abcdef")
                or payload == LAYOUT["error_payload"]), obs
        if obs is red:
            assert payload in values, obs


def test_e6_error_observations_echo_no_input():
    """E6: nothing from the call reaches the observation."""
    from task_generator.engine import apply, init_state

    scenario = make_scenario()
    state = init_state(scenario, 5)
    calls = [
        ("submit_review_wildlyunknownclass", {"record_id": "zzz", "entry_code": "qqq"}),
        ("a_completely_different_unknown_name", {"whatever": "payload-to-echo"}),
        ("submit_not_a_tool_at_all", {}),
    ]
    observations = [apply(state, c)[1] for c in calls]
    assert len({o for o in observations}) == 1, observations
    for obs, (name, _args) in zip(observations, calls):
        assert name not in obs and "payload-to-echo" not in obs

# --------------------------------------------------------------------------
# E7 Scope of effect  (TG-ADR-36)
# --------------------------------------------------------------------------


@given(data=st.data())
@SLOW
def test_e7_reads_leave_the_records_unchanged(data):
    """E7: read tools never mutate the records; the counter still advances."""
    from task_generator.engine import apply, init_state

    scenario = make_scenario(n_records=4)
    state = init_state(scenario, 1)
    cls, rid = a_record(scenario)
    state, _ = advance(state, scenario, cls, rid, 3)
    for _ in range(8):
        call = (data.draw(st.sampled_from(all_read_tools())),
                {"item_code": data.draw(st.sampled_from(TABLE["catalogue_items"] + ["nope"])),
                 "page_key": data.draw(st.sampled_from(TABLE["page_keys"] + ["b" * 32]))})
        before = state
        state, obs = apply(state, call)
        assert records_bytes(state) == records_bytes(before), call
        assert state.next_seq == before.next_seq + 1, call


def test_e7_transition_touches_one_record_and_three_fields():
    """E7: a transition mutates only the addressed record's stage, token and audit.

    Asserted on `mutations` and, independently, by comparing every other record
    field by field.
    """
    from task_generator.engine import apply, init_state, mutations

    scenario = make_scenario(n_records=5)
    cls, rid = a_record(scenario)
    entry = scenario.records[(cls, rid)]
    before = init_state(scenario, 30)
    after, obs = apply(before, a_valid_first_call(cls, rid, entry))
    assert obs_status(obs) == "ok"
    assert mutations(before, after) == sorted(
        [(cls, rid, "stage"), (cls, rid, "token"), (cls, rid, "audit")])
    for key in sorted(before.records):
        if key == (cls, rid):
            continue
        b, a = before.records[key], after.records[key]
        assert (b.stage, b.token, b.audit) == (a.stage, a.token, a.audit), key
    # the audit field is the seq of the last successful transition (TG-ADR-36)
    assert after.records[(cls, rid)].audit == obs_seq(obs) == 30
    assert before.records[(cls, rid)].audit == 0


def test_e7_calls_are_never_redirected_across_classes():
    """E7: a transition on another ledger class mutates that record, not the target.

    Uses a scenario where one id lives in two classes, which is the only shape
    that can expose a redirect (finding 4).
    """
    from task_generator.engine import apply, init_state, mutations

    scenario = make_scenario(n_records=3, shared_id=True)
    shared = [key for key in scenario.records
              if sum(1 for c, r in scenario.records if r == key[1]) > 1]
    assert len(shared) == 2, "the fixture must put one id in two classes"
    (cls_a, rid), (cls_b, _) = sorted(shared)
    before = init_state(scenario, 1)

    after, obs = apply(before, (stage_tool(TABLE["stage_names"][0], cls_b),
                                {"record_id": rid,
                                 "entry_code": scenario.records[(cls_b, rid)]}))
    assert obs_status(obs) == "ok", obs
    assert {(c, r) for c, r, _ in mutations(before, after)} == {(cls_b, rid)}
    a, b = before.records[(cls_a, rid)], after.records[(cls_a, rid)]
    assert (a.stage, a.token, a.audit) == (b.stage, b.token, b.audit), "the target moved"

    # a class with no such record is rejected, never redirected to one that has it
    absent = [q for q in TABLE["qualifiers"] if (q, rid) not in scenario.records][0]
    rejected, obs = apply(before, (stage_tool(TABLE["stage_names"][0], absent),
                                   {"record_id": rid, "entry_code": scenario.records[(cls_a, rid)]}))
    assert obs_status(obs) == "no_such_rec", obs
    assert records_bytes(rejected) == records_bytes(before)


def test_mutations_against_hand_built_state_pairs():
    """E7: `mutations` is itself correct, against pairs built by hand.

    Not produced by `apply`.  A `mutations` that missed changes would make every
    E4 and E7 row that leans on it read green, so it is pinned on its own.
    """
    from task_generator.engine import init_state, mutations

    scenario = make_scenario(n_records=4)
    base = init_state(scenario, 1)
    keys = sorted(base.records)
    k0, k1 = keys[0], keys[1]

    def edited(**by_key):
        records = dict(base.records)
        for key, changes in by_key.items():
            key = keys[int(key[1:])]
            rec = records[key]
            records[key] = type(rec)(**{**{"stage": rec.stage, "token": rec.token,
                                           "audit": rec.audit}, **changes})
        return type(base)(records=records, next_seq=base.next_seq,
                          **{f: getattr(base, f) for f in base.__dataclass_fields__
                             if f not in ("records", "next_seq")})

    assert mutations(base, base) == []
    assert mutations(base, edited(k0={"stage": 1})) == [(*k0, "stage")]
    assert mutations(base, edited(k0={"stage": 1, "token": "a" * 32, "audit": 4})) == \
        sorted([(*k0, "stage"), (*k0, "token"), (*k0, "audit")])
    assert mutations(base, edited(k0={"audit": 9}, k1={"stage": 2})) == \
        sorted([(*k0, "audit"), (*k1, "stage")])
    # a rewrite to the same value is not a mutation
    assert mutations(base, edited(k0={"stage": base.records[k0].stage})) == []
    # the counter is not a record field and never appears
    bumped = type(base)(records=base.records, next_seq=base.next_seq + 5,
                        **{f: getattr(base, f) for f in base.__dataclass_fields__
                           if f not in ("records", "next_seq")})
    assert mutations(base, bumped) == []

# --------------------------------------------------------------------------
# E8 Replay equals live  (TG-M1's half; the live half is A8, in TG-M5)
# --------------------------------------------------------------------------


@given(data=st.data())
@SLOW
def test_e8_replay_equals_the_left_fold_of_apply(data):
    """E8 at TG-M1: replay is the left fold of apply from init_state.

    The comparison against the live toolset is A8, run per episode in TG-M5
    (finding 7).  Nothing in this file can see a live toolset.
    """
    from task_generator.engine import apply, init_state, replay

    scenario = make_scenario(n_records=4)
    seq_start = data.draw(st.integers(min_value=1, max_value=5000))
    calls = data.draw(call_sequences(scenario))

    state = init_state(scenario, seq_start)
    folded = []
    for call in calls:
        state, obs = apply(state, call)
        folded.append(obs)

    final, observations = replay(scenario, calls, seq_start)
    assert observations == folded
    assert records_bytes(final) == records_bytes(state)
    assert final.next_seq == state.next_seq

# --------------------------------------------------------------------------
# E9 No stage-order leakage in names
# --------------------------------------------------------------------------


def test_e9_names_are_clean_against_the_frozen_denylist():
    """E9: no ordinal or sequence word in a stage name or a tool name."""
    from task_generator.engine import EngineSpec

    spec = EngineSpec.load()
    names = [t.name for t in spec.tools] + list(TABLE["stage_names"])
    tier1 = [(n, w) for n in names for w in DENY_NAMES if w in n.lower()]
    assert tier1 == [], tier1
    assert any(ch.isdigit() for ch in "".join(names)) is False

    tier2_strings = (
        TABLE["entry_codes"]
        + TABLE["record_id_words"]["eval"] + TABLE["record_id_words"]["train"]
        + TABLE["catalogue_items"] + list(TABLE["parameter_names"].values())
        + TABLE["status_codes"]
        + [t.description for t in spec.tools]
    )
    tier2 = [(s, w) for s in tier2_strings for w in DENY if w in s.lower()]
    assert tier2 == [], tier2


def test_e9_descriptions_come_only_from_the_three_templates():
    """E9: the dependency is stated only in the description, through the slot."""
    from task_generator.engine import EngineSpec

    spec = EngineSpec.load()
    templates = TABLE["description_templates"]
    stage_tools = set(all_stage_tools())
    for tool in spec.tools:
        d = tool.description
        assert "{" not in d and "}" not in d, d
        if tool.name in stage_tools:
            _, stage, qual = tool.name.split("_", 2)
            if stage == TABLE["stage_names"][0]:
                assert d == templates["stage_first"].format(qualifier=qual), d
                named = [n for n in stage_tools if n in d]
                assert named == [], f"a stage-1 description names a tool: {named}"
            else:
                prev = stage_tool(TABLE["stage_names"][TABLE["stage_names"].index(stage) - 1], qual)
                assert d == templates["stage_chain"].format(previous_tool=prev), d
                # exactly one tool name, and only through the slot
                assert [n for n in stage_tools if n in d] == [prev], d
        else:
            facet = tool.name.split("_", 1)[1]
            assert d == templates["read"].format(facet=facet), d
            assert [n for n in stage_tools if n in d] == [], d

# --------------------------------------------------------------------------
# E10 Hash stability
# --------------------------------------------------------------------------


def test_e10_hash_moves_on_any_single_change():
    """E10's "if": the spec, any one table entry, or the version moves the hash."""
    from task_generator.engine import EngineSpec, engine_hash

    base = engine_hash(EngineSpec.from_mapping(TABLE))
    moved = {}
    for key in sorted(TABLE):
        changed = json.loads(json.dumps(TABLE))
        value = changed[key]
        if isinstance(value, str):
            changed[key] = value + "x"
        elif isinstance(value, int):
            changed[key] = value + 1
        elif isinstance(value, list):
            changed[key] = value[:-1] if len(value) > 1 else value + ["x"]
        elif isinstance(value, dict):
            changed[key] = {**value, "an_added_entry": "x"}
        else:
            continue
        moved[key] = engine_hash(EngineSpec.from_mapping(changed))
    assert len(moved) >= 15, f"too few table keys exercised: {sorted(moved)}"
    for key, h in sorted(moved.items()):
        assert h != base, f"changing {key} did not move engine_hash"
    assert len(set(moved.values())) == len(moved), "two different tables share a hash"

    for key in ("L_obs", "engine_version", "token_band"):
        assert moved[key] != base, key


def test_e10_hash_is_stable_across_everything_else():
    """E10's "only if": nothing but the spec, table or version moves the hash.

    Not the process, not PYTHONHASHSEED, not the insertion order of a spec built
    two ways, and not the path the table was loaded from (finding 12).
    """
    from task_generator.engine import EngineSpec, engine_hash

    base = engine_hash(EngineSpec.load())
    assert engine_hash(EngineSpec.from_mapping(TABLE)) == base

    # a spec built from the same entries in a different insertion order
    reordered = {k: TABLE[k] for k in reversed(sorted(TABLE))}
    assert list(reordered) != list(TABLE)
    assert engine_hash(EngineSpec.from_mapping(reordered)) == base

    # nested dicts reordered too
    deep = json.loads(json.dumps(TABLE))
    deep["catalogue_values"] = {k: {f: v for f, v in reversed(list(row.items()))}
                                for k, row in reversed(list(deep["catalogue_values"].items()))}
    assert engine_hash(EngineSpec.from_mapping(deep)) == base

    # the same table at a different path
    copy = pathlib.Path(os.environ.get("TMPDIR", "/tmp")) / "tg_m1_table_copy.json"
    copy.write_text(TABLE_PATH.read_text())
    try:
        assert engine_hash(EngineSpec.load(copy)) == base, "the load path reached the hash"
    finally:
        copy.unlink(missing_ok=True)

    # two fresh processes at different PYTHONHASHSEED values
    src = ("import task_generator.engine as E;"
           "print(E.engine_hash(E.EngineSpec.load()))")
    out = []
    for seed in ("0", "1"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        p = subprocess.run([sys.executable, "-c", src], capture_output=True, text=True, env=env)
        assert p.returncode == 0, p.stderr
        out.append(p.stdout.strip())
    assert out[0] == out[1] == base, out

# --------------------------------------------------------------------------
# P1 the public surface
# --------------------------------------------------------------------------


def test_p1_module_exports_are_exactly_the_named_surface():
    """P1: runtime equality of each module's __all__, and nothing else public."""
    import task_generator.engine as engine
    import task_generator.tokenizer as tokenizer

    assert tuple(engine.__all__) == ENGINE_EXPORTS
    assert tuple(tokenizer.__all__) == TOKENIZER_EXPORTS
    for module, exports in ((engine, ENGINE_EXPORTS), (tokenizer, TOKENIZER_EXPORTS)):
        public = {
            name for name, value in vars(module).items()
            if not name.startswith("_")
            and not inspect.ismodule(value)
            and getattr(value, "__module__", module.__name__) == module.__name__
        }
        assert public == set(exports), (module.__name__, sorted(public - set(exports)))

# --------------------------------------------------------------------------
# T1-T3 the reference tokenizer
# --------------------------------------------------------------------------


def test_t1_vendored_encoding_matches_the_pinned_sha256():
    """T1: the vendored file is the one tiktoken 0.14.0 pins."""
    assert hashlib.sha256(ENCODING_PATH.read_bytes()).hexdigest() == ENCODING_SHA256


_T2_CHILD = textwrap.dedent(
    """
    import socket, sys

    def no_network(*args, **kwargs):
        raise AssertionError("the tokenizer reached the network")

    socket.socket = no_network
    socket.create_connection = no_network
    socket.getaddrinfo = no_network

    import task_generator.tokenizer as T
    enc = T.reference_encoding()
    assert enc.name == "o200k_base"
    print(T.count_tokens("submit_review_invoice"))
    """
)


def test_t2_tokenizer_builds_with_sockets_disabled(tmp_path):
    """T2: it builds and encodes offline, and writes nothing to a cache directory.

    tiktoken 0.14.0's read_file_cached writes a copy under the cache directory for
    a *local* path too, and load_tiktoken_bpe goes through it, so neither may be
    used (finding 9).  A get_encoding fallback raises on the patched socket.

    Run in a fresh interpreter, not in this one.  The encoding is expensive, so
    any sane tokenizer caches it; an earlier test in the same interpreter would then
    have built it already and this test would assert on a cached object, having
    disabled nothing.  That is not hypothetical -- it is how the first draft of
    this test let the get_encoding fallback through the whole mutation pass.
    """
    cache = tmp_path / "tiktoken-cache"
    cache.mkdir()
    env = dict(os.environ, TIKTOKEN_CACHE_DIR=str(cache))
    proc = subprocess.run([sys.executable, "-c", _T2_CHILD],
                          capture_output=True, text=True, env=env)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "3", proc.stdout
    assert sorted(cache.iterdir()) == [], sorted(p.name for p in cache.iterdir())


def test_t3_offline_counts_match_the_pinned_pairs():
    """T3: the offline counts equal pairs minted from get_encoding at step zero.

    An independent source, not this encoder's own output read back (standing rule
    8).  No test here touches the network.
    """
    from task_generator.tokenizer import count_tokens

    for string, expected in PINNED_TOKEN_COUNTS:
        assert count_tokens(string) == expected, (string, count_tokens(string), expected)

# --------------------------------------------------------------------------
# VT1-VT4 the frozen table
# --------------------------------------------------------------------------


def test_vt1_table_meets_the_required_coverage():
    """VT1: spec 2.1's required-coverage list, item by item, and ASCII."""
    from task_generator.engine import EngineSpec

    spec = EngineSpec.load()
    assert len(TABLE["qualifiers"]) >= 8
    assert len(TABLE["stage_names"]) == 8
    assert len(TABLE["read_verbs"]) >= 14
    assert len(TABLE["read_verbs"]) == len(TABLE["facets"])
    assert set(TABLE["read_verbs"]).isdisjoint(
        set(TABLE["stage_names"]) | {TABLE["write_verb"]})
    for name in all_read_tools():
        assert not any(q in name for q in TABLE["qualifiers"]), name
    fams = TABLE["tool_families"]
    assert fams["read"]["parameters"] != fams["stage_first"]["parameters"]
    assert fams["read"]["parameters"] != fams["stage_chain"]["parameters"]
    assert len(TABLE["record_id_words"]["eval"]) == 256
    assert len(TABLE["record_id_words"]["train"]) == 256
    assert TABLE["entry_codes"] and TABLE["catalogue_items"] and TABLE["page_keys"]
    assert set(TABLE["catalogue_values"]) == set(TABLE["catalogue_items"])
    for row in TABLE["catalogue_values"].values():
        assert set(row) == set(TABLE["facets"])
    assert len(set(TABLE["status_codes"])) == len(TABLE["status_codes"]) >= 2
    assert set(TABLE["description_templates"]) == {"stage_first", "stage_chain", "read"}
    assert TABLE["L_obs"] == L_OBS and len(TABLE["token_band"]) == 2
    assert TABLE["engine_version"] and TABLE["vocabulary_version"]
    assert TABLE_PATH.read_bytes().isascii()
    assert spec.L_obs == L_OBS


def test_vt2_word_lists_are_disjoint_and_single_token():
    """VT2: 256 + 256, disjoint, one token per word in every id position (G14)."""
    from task_generator.tokenizer import count_tokens

    ev = TABLE["record_id_words"]["eval"]
    tr = TABLE["record_id_words"]["train"]
    assert len(ev) == len(set(ev)) == 256
    assert len(tr) == len(set(tr)) == 256
    assert set(ev).isdisjoint(tr)
    assert 256 ** TABLE["record_id_word_count"] == 2 ** 32
    for words in (ev, tr):
        filler = [words[(i * 61) % 256] for i in range(4)]
        for position in range(4):
            for word in words:
                parts = list(filler)
                parts[position] = word
                rid = record_id(parts)
                assert count_tokens(rid) == 4, (position, word, rid)
                assert count_tokens(" " + rid) == 4, (position, word, rid)


def test_vt3_equal_count_sets_have_a_single_count():
    """VT3: one count per equal-count set, in the rendering where it appears.

    The three 32-hex sets are asserted against the declared band instead: hex
    tokenizes unevenly, and forcing them to a single count would make them
    atypical hex and break the very size matching N9 needs.
    """
    from task_generator.tokenizer import count_tokens

    def counts(rendering, strings):
        return {count_tokens(rendering(s)) for s in strings}

    assert counts(lambda s: " " + s, TABLE["stage_names"]) == {1}
    assert counts(lambda s: " " + s, TABLE["qualifiers"]) == {1}
    assert counts(lambda s: " " + s, TABLE["entry_codes"]) == {1}
    assert counts(lambda s: s, all_stage_tools()) == {3}
    assert counts(lambda s: s, all_read_tools()) == {2}
    assert counts(lambda s: s, TABLE["catalogue_items"]) == {4}
    assert counts(lambda s: " " + s, TABLE["catalogue_items"]) == {4}
    templates = TABLE["description_templates"]
    assert counts(lambda q: templates["stage_first"].format(qualifier=q),
                  TABLE["qualifiers"]) == {12}
    assert counts(lambda t: templates["stage_chain"].format(previous_tool=t),
                  all_stage_tools()) == {8}
    assert counts(lambda f: templates["read"].format(facet=f), TABLE["facets"]) == {9}

    values = sorted({v for row in TABLE["catalogue_values"].values() for v in row.values()})
    for group in (TABLE["page_keys"], values):
        for s in group:
            assert len(s) == LAYOUT["token_hex_chars"]
            assert set(s) <= set("0123456789abcdef")
            assert BAND_LO <= count_tokens(s) <= BAND_HI


def test_vt4_table_hash_is_pinned_and_feeds_engine_hash():
    """VT4: the table is the one that was frozen, and it reaches engine_hash."""
    from task_generator.engine import EngineSpec, engine_hash

    assert hashlib.sha256(TABLE_PATH.read_bytes()).hexdigest() == TABLE_SHA256
    base = engine_hash(EngineSpec.load())
    changed = json.loads(json.dumps(TABLE))
    changed["stage_names"] = list(reversed(changed["stage_names"]))
    assert engine_hash(EngineSpec.from_mapping(changed)) != base
