"""Pending a yes/no: what the simulator does with an output schema keyword it cannot fill.

**Why it is open.**  O1 kept every output schema as written (its frozen tests read an output `anyOf`,
a deep output and Petstore's maps unchanged; the simulator "generates from it and checks nothing").
Spec §4 says an answer conforms to the output schema, and O2.2 pins that by a sweep.  Some keywords
cannot be filled by a draw keyed on the call: a `pattern`, a `not`, the conditionals, the containment
family, and the others the readers refuse in an argument schema.

**Recommendation: yes.**  The simulator honours `anyOf` (its first branch), `oneOf` (the first branch
whose value no other branch accepts) and every keyword the sweep draws, and passes over each of
`simulator.OUTPUT_PASSED_OVER`: the answer conforms to the schema with those keywords taken out.  The
tool is still offered and still answers.  A no refuses, at reading, a tool whose output schema uses
one of them, which changes O1's rule and the summary of a set that has one.
"""

from __future__ import annotations

from typing import Any

import jsonschema  # type: ignore[import-untyped]

from poisson_tasks import own
from tests.o2_support import simulator

PASSED_OVER = (
    "pattern", "not", "if", "then", "else", "allOf", "contains", "minContains", "maxContains",
    "propertyNames", "dependentSchemas", "dependentRequired", "dependencies",
    "unevaluatedProperties", "unevaluatedItems", "patternProperties", "minProperties",
    "maxProperties", "multipleOf", "uniqueItems",
)
WITH = {
    "pattern": ("code", {"type": "string", "pattern": "^[A-Z]{3}$"}),
    "not": ("code", {"type": "string", "not": {"const": "x"}}),
    "if": ("code", {"type": "string", "if": {"const": "a"}, "then": {"maxLength": 1}}),
    "then": ("code", {"type": "string", "then": {"maxLength": 40}}),
    "else": ("code", {"type": "string", "else": {"maxLength": 40}}),
    "allOf": ("code", {"allOf": [{"type": "string"}, {"maxLength": 40}]}),
    "contains": ("list", {"type": "array", "items": {"type": "string"}, "contains": {"const": "x"}}),
    "minContains": ("list", {"type": "array", "items": {"type": "string"}, "minContains": 1}),
    "maxContains": ("list", {"type": "array", "items": {"type": "string"}, "maxContains": 3}),
    "propertyNames": ("map", {"type": "object", "properties": {"ab": {"type": "string"}}, "propertyNames": {"maxLength": 2}}),
    "dependentSchemas": ("map", {"type": "object", "properties": {"a": {"type": "string"}}, "dependentSchemas": {"a": {}}}),
    "dependentRequired": ("map", {"type": "object", "properties": {"a": {"type": "string"}}, "dependentRequired": {"a": []}}),
    "dependencies": ("map", {"type": "object", "properties": {"a": {"type": "string"}}, "dependencies": {"a": []}}),
    "unevaluatedProperties": ("map", {"type": "object", "properties": {"a": {"type": "string"}}, "unevaluatedProperties": False}),
    "unevaluatedItems": ("list", {"type": "array", "items": {"type": "string"}, "unevaluatedItems": False}),
    "patternProperties": ("map", {"type": "object", "patternProperties": {"^x": {"type": "string"}}}),
    "minProperties": ("map", {"type": "object", "properties": {"a": {"type": "string"}}, "minProperties": 1}),
    "maxProperties": ("map", {"type": "object", "properties": {"a": {"type": "string"}}, "maxProperties": 5}),
    "multipleOf": ("n", {"type": "integer", "minimum": 0, "maximum": 100, "multipleOf": 5}),
    "uniqueItems": ("list", {"type": "array", "items": {"type": "string"}, "uniqueItems": True}),
}


def without(schema: Any, keywords: tuple[str, ...]) -> Any:
    if isinstance(schema, dict):
        return {k: without(v, keywords) for k, v in schema.items() if k not in keywords}
    if isinstance(schema, list):
        return [without(v, keywords) for v in schema]
    return schema


def test_the_keywords_passed_over_are_the_list() -> None:
    assert tuple(simulator().OUTPUT_PASSED_OVER) == PASSED_OVER


def test_an_answer_conforms_to_its_output_schema_with_the_passed_over_keywords_taken_out() -> None:
    sim = simulator()
    for keyword, (name, sub) in WITH.items():
        output = {"type": "object", "properties": {name: sub}, "required": [name]}
        tool = own.OwnTool("probe", "Probes.", {"type": "object", "properties": {}}, output, "read")
        for seed in range(30):
            value = sim.respond(tool, {}, digest="d" * 64, seed=seed, split="eval")
            jsonschema.validate(value, without(output, PASSED_OVER))
            assert name in value, keyword
