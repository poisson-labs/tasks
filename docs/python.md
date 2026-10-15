# Using it from Python

Everything the command does is a library, and you can use the library without the command: make tasks, judge answers, check a contrast, hand tasks to another runner, read the published cards and read your own tools. This page shows each piece with a snippet you can run. The names on it are the package's public API; a name that starts with an underscore is not.

Generating a task needs the tokenizer file, a 3.6 MB file the package fetches once, because it counts tokens in the way the published cards do. `poisson-tasks init` offers to fetch it, `poisson-tasks doctor --fix` fetches it, and so does:

<!-- docs-check: skip reason="fetches the tokenizer file over the network; the job puts the file in place before it runs the blocks" -->
```bash
python -m poisson_tasks.fetch_encoding
```

## One task, and the verdict on an answer

An arm is one setting of one dial. `ArmSpec` names it with six fields: the knob, the level, the control (a higher level this arm stands in for, or none), the strictness, the split and the generator version. `generate(arm, seed)` returns the task: its prompts, the tools in the order the model sees them, the goal, a reference solution with what the domain returns for every call, the wrong answers it ships with, and the hashes that identify it. `verify` judges a transcript against it with no model.

<!-- docs-check: run -->
```python
from poisson_tasks.knobs import ArmSpec
from poisson_tasks.tasks import FormatSpec, Turn, generate, verify

arm = ArmSpec("depth", 3, None, "strict", "eval", "0")
bundle = generate(arm, seed=7)

turns = tuple(Turn("", (call,), "tool_calls") for call in bundle.reference_calls)
turns += (Turn("Done.", (), "stop"),)

verdict = verify(bundle, turns, True, False, FormatSpec("direct", ()))
assert verdict.label == "passed"
print(bundle.task_id)
print(verdict.label)
```
<!-- docs-check: output -->
```
dab5794b7cd35eaefc337817fbcd61efbd5e8db27d3203f04dcf06867ec8a3d4
passed
```

`verify(bundle, turns, ended_with_reply, turn_limit_hit, fmt)` is a pure function of those five arguments. Its label is one of ten, in this order of precedence: `verifier_error`, `replay_mismatch`, `api_error`, `wall_timeout`, `malformed_call`, `turn_limit`, `overshoot`, `wrong_state`, `collateral_mutation`, `passed`. Every episode is judged strict and leaky at once (`strict_label` and `leaky_pass`). [The task](the-task.md) describes the domain and the verdicts.

`poisson_tasks.outcomes.describe(label)` gives each label's plain sentence, the one `verify` and the cards print.

## Arms by their id

A user names an arm by its id, such as `depth:d3`, and never by six fields. `arms.arm_from_id` is the inverse of `knobs.arm_id`; the other three fields are given by name.

<!-- docs-check: run -->
```python
from poisson_tasks import arms
from poisson_tasks.knobs import arm_id

arm = arms.arm_from_id("depth:d3")
print(arm)
print(arm_id(arm))
print(arms.arm_from_id("faults:f2", strictness="leaky", generator_version="0").strictness)
```
<!-- docs-check: output -->
```
ArmSpec(knob='depth', level=3, control=None, strictness='strict', split='eval', generator_version='1')
depth:d3
leaky
```

An id that is not written the way `arm_id` writes it (`bogus:d1`, or `depth:d03` for `depth:d3`) is refused in one line that names what is wrong. The level is not judged here: the settings file and the export config refuse a level the generator cannot make, and take a level that is legitimate but on no published card, such as `depth:d4`, with a note that no card measured it.

## A contrast, held to the pin ledger

Two arms of one knob should differ in that knob and in nothing else. The pin ledger is thirty equalities across the arms of a contrast, measured on the generated tasks; [knobs-and-arms.md](knobs-and-arms.md) lists them. `check_pins` runs them, and `arms.describe_pins` turns the report into one sentence.

<!-- docs-check: run -->
```python
from poisson_tasks import arms
from poisson_tasks.knobs import check_pins
from poisson_tasks.tasks import generate

ids = ["depth:d1", "depth:d3", "depth:d8"]
bundles = {i: generate(arms.arm_from_id(i, generator_version="0"), 404) for i in ids}
report = check_pins(bundles)
print(report.refused)
print(arms.describe_pins(report))
```
<!-- docs-check: output -->
```
False
The depth contrast across depth:d1, depth:d3 and depth:d8 holds everything but the depth level fixed.
```

A contrast that breaks a row is refused before any model runs: `report.refused` is true and `report.violations` names the rows.

## Task ids and the generator version

A task's id is a hash of the task, the generator's source and a short label, the generator version. Change any of them and the id changes. Two labels give the same prompt, tools, goal and reference solution, and different ids.

- The command and the settings file use the package's default label, `arms.DEFAULT_GENERATOR_VERSION`, and never ask. `poisson-tasks generate --generator-version` and `[tasks] generator_version` set another, for a library user who needs to reproduce tasks made under another label; the plan then says that the tasks match no published card.
- Both published cards were measured at label `"0"`, on an earlier build of the generator. The tasks they hold regenerate today with the same text, and with other ids, so `card --published` says each card is *not current for this install*, and a run's card cannot be read beside them. The next release measures the cards again on the current generator.
- The examples use `"0"`, to match the label the cards carry.

## Handing tasks to another runner

`generate` writes one JSON Lines file for every arm, one task per line, in the form `poisson_tasks.export` defines. A custom pipeline can read those files directly, and `bundle_from_data` turns a line back into the task `generate` returned.

<!-- docs-check: run -->
```bash
poisson-tasks generate --arm depth:d1 --tasks-per-level 2
```
<!-- docs-check: output -->
```
ok  generated 2 tasks: depth at 1, 2 tasks each, no model and no network
  pin ledger  one arm, depth:d1: there is no contrast to check
  wrote       tasks/depth-d1.jsonl (2 tasks)
next: poisson-tasks run
```

<!-- docs-check: run -->
```python
import json

from poisson_tasks.export import ExportTaskData, bundle_from_data

with open("tasks/depth-d1.jsonl", encoding="utf-8") as lines:
    for line in lines:
        bundle = bundle_from_data(ExportTaskData.model_validate(json.loads(line)))
        print(bundle.arm_id, bundle.task_id[:12], len(bundle.tools), "tools")
```
<!-- docs-check: output -->
```
depth:d1 …
depth:d1 …
```

To run the tasks under verifiers yourself, `ExportTaskset` is a verifiers taskset over a declared list of seeds, scored by the generator's own verifier, with the task's tools served over MCP. [verifiers-export.md](verifiers-export.md) has the names, the signals and the tool server.

<!-- docs-check: run -->
```python
import dataclasses

from poisson_tasks.export import ExportTaskset, ExportTasksetConfig
from poisson_tasks.knobs import ArmSpec

arm = ArmSpec(knob="depth", level=3, control=None, strictness="strict",
              split="eval", generator_version="0")
taskset = ExportTaskset(ExportTasksetConfig(arm=dataclasses.asdict(arm), seeds=[404, 55, 2121]))
for task in taskset.load():
    print(task.key[:12], len(task.data.tools), "tools")
```
<!-- docs-check: output -->
```
…
…
…
```

## The published cards, and what the knob probe found

The cards ship inside the package. `cards.published()` lists them by their model's short name, `cards.recompute` rebuilds one from its own records and says whether the rebuilt card is the stored one byte for byte and whether it is current for this install, and `arms.knob_status()` is the table of what the knob probe found, read from a file in the package.

<!-- docs-check: run -->
```python
from poisson_tasks import arms, cards

for card in cards.published():
    made = cards.recompute(card)
    print(card.name, made.identical, made.current, made.records)

print(arms.knob_status()["knobs"]["history"]["says"])
print(arms.SHIPPED_KNOBS)
```
<!-- docs-check: output -->
```
gpt-5-nano True False 4200
qwen3-8b True False 4200
ships: bites on gpt-5-nano; bites on Qwen3-8B
('faults', 'history', 'shape')
```

## Your own tools

`own.read_tools` reads an OpenAI tools file, an MCP tool list or an OpenAPI document (as bytes) into one form, refusing in one line each what it cannot use. [own-tools.md](own-tools.md) describes what to do with the result.

<!-- docs-check: run -->
```python
import json

from poisson_tasks import own

tools = [
    {"type": "function", "function": {
        "name": "get_order", "description": "Look up one order by its id.",
        "parameters": {"type": "object", "required": ["order_id"],
                       "properties": {"order_id": {"type": "string", "minLength": 6, "maxLength": 6}}}}},
    {"type": "function", "function": {
        "name": "refund_order", "description": "Refund part or all of an order.",
        "parameters": {"type": "object", "required": ["order_id", "amount"],
                       "properties": {"order_id": {"type": "string", "minLength": 6, "maxLength": 6},
                                      "amount": {"type": "number", "minimum": 0}}}}},
]
reading = own.read_tools(json.dumps(tools).encode("utf-8"), name="orders")
print(own.summary(reading).splitlines()[0])
```
<!-- docs-check: output -->
```
2 tools: 0 read, 0 write, 2 not known (treated as write), 0 refused
```

## The examples, as source to read

The repository's `examples` folder holds four short programs that use the library. They are not installed with the package; read them, and copy what you need. Each takes `--help`, and a mistaken argument gets one line.

| file | what it shows |
|---|---|
| [`examples/one_task.py`](https://github.com/poisson-labs/tasks/blob/main/examples/one_task.py) | one task, its reference solution, and the verdict on every answer it ships with (`poisson-tasks generate --show` and `verify --self-check` do the same from the command line) |
| [`examples/a_contrast.py`](https://github.com/poisson-labs/tasks/blob/main/examples/a_contrast.py) | the arms of a knob and the pin ledger over them, and a contrast the ledger refuses |
| [`examples/calibration_card.py`](https://github.com/poisson-labs/tasks/blob/main/examples/calibration_card.py) | a published card recomputed from its records (`poisson-tasks card --published` does the same) |
| [`examples/proofload_sweep/run.py`](https://github.com/poisson-labs/tasks/blob/main/examples/proofload_sweep/run.py) | the scripted path through Proofload; see [proofload.md](proofload.md) |
