"""What produced a card, the pure part, frozen as tests: the frozen files and both generator
hashes, and the tool file's contract hash.

The invariants:
- the generator's source files, the domain, the vocabulary table and the knob probe's table keep
  their bytes, and both generators keep their hashes, so recording what produced a run moves no
  task;
- `poisson_tasks.provenance.tool_spec_hash(data)` is the SHA-256 of the file's canonical JSON:
  parsed as the own-tools reader parses it, dates and datetimes as their ISO text, a key that is
  not a string as its JSON text, then `json.dumps(sort_keys=True, separators=(",", ":"),
  ensure_ascii=False, allow_nan=False)` in UTF-8, with no prefix, so anyone can recompute it;
- re-encoding a file (indentation, key order, JSON against YAML, `\\u` escapes) keeps it and moves
  the file's own hash; changing a description or the order of an array moves it;
- a mapping whose keys collide once written as JSON text, and a value JSON cannot carry, are
  refused with a `ValueError` of one line that names the place as a JSON pointer.

Every expectation is our own copy of the rule (`tests/pv_support.py`) and the literals measured on
the commit these tests were written on.  No run, no tokenizer beyond the generator's own call.
"""

from __future__ import annotations

import copy
import hashlib
import importlib
import json
from typing import Any

import pytest
import yaml

from tests.pv_support import (
    BUILT_IN_GENERATOR,
    FIXTURE_HASHES,
    OWN_TOOLS_GENERATOR,
    REPO,
    VOCABULARY,
    canonical,
    fixture,
    json_model,
    parsed,
    sha256,
    spec_hash,
)

# The bytes of the files the generators and the domain are made of, as they are on the commit
# these tests were written on.
FROZEN = {
    "src/poisson_tasks/tasks.py": "d7911984a0ac3d05df70b5168fd49793502455a7ebce768d660fd873be803849",
    "src/poisson_tasks/surface.py": "f3e6d7831c76cb10885fea074c318fbb0300b7970532419ade564689c51cca68",
    "src/poisson_tasks/knobs.py": "d7afa15d55c1379b985dbd73240c8c518ceb829392a35f161127d2e9915a3fb5",
    "src/poisson_tasks/engine.py": "5ae0ae984b960cf52fe9691141ff05f63a2df33bdcbcc767330c0f0177aaa725",
    "src/poisson_tasks/data/vocabulary-v2.json": VOCABULARY,
    "src/poisson_tasks/knob_status.json": "6a9cc69cf9ebb34d9a7627d540648a20b97b0e0a9048b29c3ae99715dbdae9c5",
}


def provenance() -> Any:
    return importlib.import_module("poisson_tasks.provenance")


def test_pv_1_the_frozen_files_and_both_generator_hashes_hold() -> None:
    from poisson_tasks.arms import arm_from_id
    from poisson_tasks.own import generator as own_generator
    from poisson_tasks.tasks import generate

    for name, digest in FROZEN.items():
        assert sha256((REPO / name).read_bytes()) == digest, name
    assert generate(arm_from_id("depth:d3"), 404).generator_hash == BUILT_IN_GENERATOR
    assert own_generator.generator_hash() == OWN_TOOLS_GENERATOR


def test_pv_2_the_spec_hash_of_each_fixture_is_the_documented_rule() -> None:
    for name, (file_hash, spec) in FIXTURE_HASHES.items():
        data = fixture(name)
        assert sha256(data) == file_hash, name
        assert spec_hash(data) == spec, name
        assert provenance().tool_spec_hash(data) == spec, name


# ---------------------------------------------------------------------------
# re-encoding keeps it, editing moves it
# ---------------------------------------------------------------------------


def keys_reversed(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: keys_reversed(value[key]) for key in reversed(list(value))}
    if isinstance(value, list):
        return [keys_reversed(item) for item in value]
    return value


def first_description(value: Any) -> list[Any] | None:
    """The path to the first string under a `description` key, depth first."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "description" and isinstance(item, str) and item:
                return [key]
            found = first_description(item)
            if found is not None:
                return [key, *found]
    if isinstance(value, list):
        for index, item in enumerate(value):
            found = first_description(item)
            if found is not None:
                return [index, *found]
    return None


def first_unequal_pair(value: Any) -> list[Any] | None:
    """The path to the first array whose first two items differ, depth first."""
    if isinstance(value, list):
        if len(value) >= 2 and value[0] != value[1]:
            return []
        items: Any = enumerate(value)
    elif isinstance(value, dict):
        items = value.items()
    else:
        return None
    for key, item in items:
        found = first_unequal_pair(item)
        if found is not None:
            return [key, *found]
    return None


def at(value: Any, path: list[Any]) -> Any:
    for step in path:
        value = value[step]
    return value


def test_pv_3_re_encoding_keeps_the_spec_hash_and_editing_moves_it() -> None:
    for name, (file_hash, spec) in FIXTURE_HASHES.items():
        doc = json_model(parsed(fixture(name)))
        kept = {
            "re-indented": json.dumps(doc, indent=4, ensure_ascii=True).encode("utf-8"),
            "keys reversed": json.dumps(keys_reversed(doc), ensure_ascii=False).encode("utf-8"),
            "as YAML": yaml.safe_dump(doc, allow_unicode=True, sort_keys=False).encode("utf-8"),
        }
        for how, data in kept.items():
            assert sha256(data) != file_hash, (name, how)
            assert spec_hash(data) == spec, (name, how)
            assert provenance().tool_spec_hash(data) == spec, (name, how)

        described = copy.deepcopy(doc)
        path = first_description(described)
        assert path is not None, name
        text = at(described, path[:-1])[path[-1]]
        at(described, path[:-1])[path[-1]] = text[:-1] + ("x" if text[-1] != "x" else "y")
        swapped = copy.deepcopy(doc)
        path = first_unequal_pair(swapped)
        assert path is not None, name
        array = at(swapped, path)
        array[0], array[1] = array[1], array[0]
        for how, edited in (("a description", described), ("an array's order", swapped)):
            data = json.dumps(edited, indent=2).encode("utf-8")
            assert spec_hash(data) != spec, (name, how)
            assert provenance().tool_spec_hash(data) == spec_hash(data), (name, how)

    # Text beyond ASCII: escaped and literal are one contract, hashed as UTF-8; a precomposed and
    # a decomposed letter are two, since nothing is normalised.
    literal = '{"description": "Caf\u00e9 \u2014 r\u00e9sum\u00e9"}'.encode("utf-8")
    escaped = b'{"description": "Caf\\u00e9 \\u2014 r\\u00e9sum\\u00e9"}'
    assert literal != escaped
    expected = hashlib.sha256('{"description":"Caf\u00e9 \u2014 r\u00e9sum\u00e9"}'.encode("utf-8"))
    assert provenance().tool_spec_hash(literal) == provenance().tool_spec_hash(escaped) == (
        expected.hexdigest())
    decomposed = '{"description": "Cafe\u0301 \u2014 re\u0301sume\u0301"}'.encode("utf-8")
    assert provenance().tool_spec_hash(decomposed) == spec_hash(decomposed) != spec_hash(literal)


# ---------------------------------------------------------------------------
# what JSON cannot carry
# ---------------------------------------------------------------------------


def hash_of(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def test_pv_4_a_yaml_date_and_a_key_that_is_not_a_string_hash_as_their_json_text() -> None:
    dated = b"info:\n  released: 2026-10-26\n  at: 2026-10-26T11:00:00Z\n"
    quoted = b'info:\n  released: "2026-10-26"\n  at: "2026-10-26T11:00:00+00:00"\n'
    assert parsed(dated)["info"]["released"] != "2026-10-26"
    assert spec_hash(dated) == spec_hash(quoted)
    assert provenance().tool_spec_hash(dated) == provenance().tool_spec_hash(quoted) == hash_of(
        {"info": {"released": "2026-10-26", "at": "2026-10-26T11:00:00+00:00"}})

    keyed = b"responses:\n  200:\n    description: ok\n  true: x\n  null: y\n"
    assert set(parsed(keyed)["responses"]) == {200, True, None}
    assert provenance().tool_spec_hash(keyed) == spec_hash(keyed) == hash_of(
        {"responses": {"200": {"description": "ok"}, "true": "x", "null": "y"}})


def refusal(data: bytes) -> str:
    """The refusal's one line."""
    with pytest.raises(ValueError) as refused:
        provenance().tool_spec_hash(data)
    message = str(refused.value)
    assert message.strip() and "\n" not in message.strip(), message
    return message


def test_pv_4_what_json_cannot_carry_is_refused_in_one_line_naming_the_place() -> None:
    """Each refusal beside the same file without the clause, which is hashed."""
    head = b'paths:\n  /orders:\n    get:\n      responses:\n        200: {description: ok}\n'
    accepted = provenance().tool_spec_hash(head)
    assert accepted == spec_hash(head)
    message = refusal(head + b'        "200": {description: also ok}\n')
    assert "/paths/~1orders/get/responses" in message, message
    assert "JSON cannot carry" in message, message

    number = b'{"tools": [{"name": "get_order", "limit": 1.5}]}'
    assert provenance().tool_spec_hash(number) == spec_hash(number)
    message = refusal(number.replace(b"1.5", b"NaN"))
    assert "/tools/0/limit" in message, message
    assert "JSON cannot carry" in message, message
