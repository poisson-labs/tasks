# Tasks on your own tools

Bring the tool definitions you already have, and Tasks makes tasks on those tools: checkable, at a difficulty you choose, with a card that shows where your setup breaks. This page is for teams that build an agent. If you train models, [the README](https://github.com/poisson-labs/tasks/blob/main/README.md) is the place to start.

**What the result measures.** Tasks never calls your backend. Every response your tools give in an episode is made by Tasks' simulator, shaped by your schemas. So a result on your tools measures how a model chooses, fills in, sequences and recovers with tools that look like yours. It does not measure whether your real tools' outputs are understandable, whether your backend's errors are recoverable, or whether your app works. The card says so first.

## What you can bring

| format | what Tasks reads | a tool's effect |
|---|---|---|
| an OpenAI tools file | a JSON list of Chat Completions tools (`{"type": "function", "function": {...}}`) or Responses tools (`{"type": "function", "name": ...}`), or an object with a `tools` list of either | not in the format; Tasks asks (below) |
| an MCP tool list | the result of `tools/list` as JSON, bare or in its JSON-RPC envelope, merged across pages; or a server of yours, started with `--mcp-command` | `readOnlyHint: true` reads; annotations present and no `readOnlyHint` is a write; no annotations is unknown |
| an OpenAPI document | version 3.0 or 3.1, as YAML or JSON | `GET` and `HEAD` read; `POST`, `PUT`, `PATCH` and `DELETE` write |

`--own-format auto` (the default) tells them apart by shape, and refuses a file that is none of the three, naming the three. With `--mcp-command 'python my_server.py'`, Tasks starts your server once, with your consent (`--yes` is the consent), only to list its tools, writes them to `tools.mcp.json` beside `tasks.toml`, and stops the server. The command itself is kept nowhere. It never calls any of your server's tools.

## A first run

Save a tool file. This one is a small order-support set in the OpenAI format:

<!-- docs-check: run -->
```bash
cat > tools.json <<'EOF'
[
  {"type": "function", "function": {
    "name": "get_order", "description": "Look up one order by its id.",
    "parameters": {"type": "object", "required": ["order_id"], "properties": {
      "order_id": {"type": "string", "minLength": 6, "maxLength": 6,
                   "description": "The order's id, six characters such as A-3317."}}}}},
  {"type": "function", "function": {
    "name": "search_orders", "description": "Find orders whose notes match some words.",
    "parameters": {"type": "object", "properties": {
      "query": {"type": "string", "description": "Words to look for in the order notes."}}}}},
  {"type": "function", "function": {
    "name": "refund_order", "description": "Refund part or all of an order.",
    "parameters": {"type": "object", "required": ["order_id", "amount"], "properties": {
      "order_id": {"type": "string", "minLength": 6, "maxLength": 6,
                   "description": "The order's id, six characters such as A-3317."},
      "amount": {"type": "number", "minimum": 0, "description": "The amount to refund, in dollars."},
      "reason": {"type": "string", "enum": ["damaged", "late", "other"],
                 "description": "Why the order is refunded."}}}}},
  {"type": "function", "function": {
    "name": "notify_customer", "description": "Send the customer a note about an order.",
    "parameters": {"type": "object", "required": ["order_id", "channel"], "properties": {
      "order_id": {"type": "string", "minLength": 6, "maxLength": 6},
      "channel": {"type": "string", "enum": ["email", "sms"]}}}}},
  {"type": "function", "function": {
    "name": "list_channels", "description": "List the channels a note can go out on.",
    "parameters": {"type": "object", "properties": {}}}}
]
EOF
```

Point `init` at it. An OpenAI tools file does not say which tools only read, so the options say so; `--own-flow` says that the `id` in what `get_order` returns is what `refund_order` takes as its `order_id`:

<!-- docs-check: run -->
```bash
poisson-tasks init --yes --no-check-key --own-file tools.json --own-name acme --own-read get_order --own-read search_orders --own-read list_channels --own-flow get_order.id:refund_order.order_id
```
<!-- docs-check: output -->
```
ok  wrote tasks.toml: the first-look recipe on your tools (acme), 10 tasks each, against gpt-5-nano-2025-08-07
  tokenizer   …
  key         …
  your tools  acme: 5 tools: 3 read, 0 write, 2 not known (treated as write), 0 refused; file: an OpenAI tools file, sha256 bf34e029e3fa609162c90e8709251c32db608d8aa0afd1f23432d500bd007ece; the responses are simulated from your schemas, and your backend is never called
  the same setup, without questions:
    poisson-tasks init --yes --provider openai --model gpt-5-nano-2025-08-07 \
      --base-url https://api.openai.com/v1 --api-key-env OPENAI_API_KEY \
      --price 0.05,0.005,0.4 --price-read-on 2026-09-25 --recipe first-look \
      --tasks-per-level 10 --attempts 1 --temperature 1.0 --top-p 1.0 \
      --reasoning-effort low --max-tokens 2048 --spend-cap 1.0 \
      --max-model-calls 32 --concurrency 8 --runs-dir runs --tasks-dir tasks \
      --own-file tools.json --own-format auto --own-name acme --own-read get_order \
      --own-read search_orders --own-read list_channels --own-flow get_order.id:refund_order.order_id
next: poisson-tasks run
```

The first lines are the summary of your file: how many tools, how many read and write, how many Tasks could not use, and the file's digest. The read and write counts are of your set as you declared it: the three tools named with `--own-read` count as reads, and the two that nothing has said anything about stay "not known (treated as write)". A tool Tasks cannot use is refused in one line, and the rest of the set still runs. The digest goes into every task's id, so a task is a pure function of your file's bytes, the arm and the seed.

`doctor` reads the file again and reports the same summary, each refusal, which dials your set reaches, and what the knob probe found for each on the built-in tasks:

<!-- docs-check: run fixture -->
```bash
poisson-tasks doctor --offline
```
<!-- docs-check: output -->
```
ok  this environment is ready to run tasks.toml
  python      ok      …
  package     ok      …
  tokenizer   ok      …
  config      ok      tasks.toml: the first-look recipe on your tools (acme), 10 tasks each, against gpt-5-nano-2025-08-07
  key         ok      OPENAI_API_KEY is set (not checked: --offline)
  tools       ok      5 tools: 3 read, 0 write, 2 not known (treated as write), 0 refused in tools.json
  file        ok      file: an OpenAI tools file, sha256 bf34e029e3fa609162c90e8709251c32db608d8aa0afd1f23432d500bd007ece
  knobs       ok      faults, history, depth, shape, similarity, arguments and spread reach a level on this set; faults, history, depth and shape shipped and lead the recipes
  faults      ok      the knob probe's status on the built-in tasks: does not bite on gpt-5-nano; bites on Qwen3-8B
  history     ok      the knob probe's status on the built-in tasks: bites on gpt-5-nano; bites on Qwen3-8B
  depth       ok      measured on the published cards, not by the knob probe
  shape       ok      the knob probe's status on the built-in tasks: does not bite on gpt-5-nano; bites on Qwen3-8B
  similarity  ok      the knob probe's status on the built-in tasks: does not bite on gpt-5-nano; does not bite on Qwen3-8B
  arguments   ok      the knob probe's status on the built-in tasks: does not bite on gpt-5-nano; does not bite on Qwen3-8B
  spread      ok      the knob probe's status on the built-in tasks: top easier on gpt-5-nano; cannot tell on Qwen3-8B
  harness     ok      …
  platform    ok      …
```

Make the tasks and look at the plan. Neither sends anything:

<!-- docs-check: run -->
```bash
poisson-tasks generate
```
<!-- docs-check: output -->
```
ok  generated 20 tasks: depth at 1 and 2, 10 tasks each, no model and no network
  pin ledger  none on your tools: each arm's tasks differ in the knob's level alone by the generator's own construction, and there is no built-in table to hold fixed
  your tools  acme, 5 tools from tools.json; the responses are simulated from your schemas, and your backend is never called
  wrote       tasks/depth-d1.jsonl (10 tasks), tasks/depth-d2.jsonl (10 tasks)
next: poisson-tasks run
```

<!-- docs-check: run -->
```bash
poisson-tasks run --dry-run --offline
```
<!-- docs-check: output -->
```
plan  20 episodes against gpt-5-nano-2025-08-07: about $0.005, and the run stops at $1.00
  tasks       depth at 1 and 2, 10 tasks each · strict
  your tools  acme, 5 tools from tools.json; the responses are simulated from your schemas, and your backend is never called
  model       gpt-5-nano-2025-08-07 at api.openai.com · key in OPENAI_API_KEY: not checked (--offline)
  calls       50 if every task is solved the shortest way · about 50 expected · at most 640 (32 per episode)
  cost        about $0.005 expected · the run stops at $1.00
  estimate    from the published gpt-5-nano card for this model
  harness     the first episode runs uv's installer (astral.sh inside a virtualenv) and fetches four packages and their dependencies from PyPI
  folder      runs/first-look-gpt-5-nano-2025-08-07 (a new run)
```

`run` and `card` then work as they do on the built-in tasks ([commands.md](commands.md)): `run` asks, runs every episode against your model and stops at the cap, and `card` says what each level was worth. The plan's estimate scales the published card's per-call figures by the size of your tool block, so it is a rough guide, and the cap is what holds.

## What Tasks refuses

A refusal is per tool where it can be, in one line, and a set with some refused tools still runs on the rest. A tool is refused when:

- its name, after one fixed renaming, is not 1 to 64 characters of letters, digits, `_` and `-` (the providers' rule), or repeats another's. Characters outside that set become `_`; a name over 64 characters is cut and given 8 characters of its digest. The original name is kept as the tool's title, and `init` and `doctor` list both;
- its argument schema is not a JSON object schema;
- its schema uses what the simulator cannot check exactly: `anyOf`, `oneOf`, `allOf`, `not`, `patternProperties`, `propertyNames`, `if`, `then`, `else`, `dependentSchemas`, `dependentRequired`, `contains`, `uniqueItems`, `multipleOf`, `minProperties`, `maxProperties`, `unevaluatedItems`, `unevaluatedProperties`, a recursive reference, a schema-valued `additionalProperties`, or nesting deeper than three levels;
- it takes a file, a binary string or a stream;
- (OpenAPI) a path or query parameter has the same name as a field of the request body.

A tool can be offered but never be a task's target when its only arguments are free text with no format, enum or bound (a lone `query: string`): no exact argument can be checked, so it can stand in a block, be a lookalike or be called in history, but no task requires a call to it with particular values.

A set is refused as a whole when fewer than 2 usable tools remain, more than 256, or no usable tool can be a target.

## Which tools read and which write

A stray write is a side effect, and a stray read is not, so Tasks has to know. MCP and OpenAPI say it; an OpenAI tools file does not. A tool whose effect is unknown is treated as a write (an extra call to it counts against the model) until you say otherwise: `read = ["get_order"]` and `write = [...]` in `tasks.toml`, or `--own-read` and `--own-write` to `init`, which asks once when it is run with questions. The summary `init` and `doctor` print counts what you declared, and what you answered to that question, as well as what the file says: three tools declared as reads read `3 read`, and what is left is `not known`.

## How the responses are made

- A call the task expects, or any read, answers with a JSON object. When the tool has an output schema, the object conforms to it, with values drawn from the file's digest, the seed, the tool and its arguments; otherwise it is `{"ok": true, "id": "<value>"}`. Strings respect `format`, enums and bounds. The draw depends on the call's content and not on its position, so the same call in the same episode always gets the same answer.
- The values a task needs (a value that one call hands the next) sit in a named string field of a response, chosen when the task is made.
- Errors come in each format's own idiom: for OpenAI tools, `{"error": {"code": "...", "message": "..."}}`; for MCP, a result with `isError: true` and the message as text; for OpenAPI, `{"status": 404, "detail": "..."}`. The codes are `not_found` (404), `invalid_arguments` (422), `not_ready` (409, a step before its prerequisite) and `unavailable` (503, a planned fault).
- A small store of records keyed by the values the task names. A write the task expects moves its record; any other accepted write is recorded as a side effect. Reads change nothing. The expected write made a second time is accepted and recorded as a side effect, because Tasks cannot know that a write of yours is idempotent.

Everything is pure: no clock but a fixed one, no randomness but the keyed draw, and no network.

## A task on your tools, and how it is checked

| form | the model must | needs |
|---|---|---|
| call | make one write call with the values the request states | a write tool that can be a target |
| read then call | read a value with one of your read tools and use it in the write call | a read tool with an argument, and a write tool |
| flow | follow a chain of your tools where an output feeds the next input, as you declared | flows in `tasks.toml` |

The verdict is the same vocabulary as on the built-in tasks, judged by replaying the model's calls through the simulator: `passed` (the store ends exactly as expected and the episode ends with a reply), `collateral_mutation` (the goal was reached but another write was accepted), `wrong_state` (it was not reached), `malformed_call` (a call named a tool outside the block, or broke its schema) and `turn_limit`. Arguments compare exactly: strings byte for byte, numbers by value, booleans and enums exactly. On your tools every dial, depth included, is read on strict pass@1 against its first level, because a tool of yours has no stage past its goal, and what the leaky rate accepts is a side effect.

The request names what to do without naming the tool, or choosing the tool would be a word match. With a line of intent per tool (`[own.intents]`), requests use it; without, they use the first sentence of the tool's description, and the card says that choosing was partly a word match.

The request states every value the call takes that Tasks can make up from the schema, required or not, so the model never has to ask which record to change or what to change it to: `Update an existing pet: id 482, name "mjmkhns", ...` rather than `Update an existing pet: photoUrls ["stvfi"].` A free-text value is stated and not checked. On the arguments dial the number of values stated is the level, so there the request states that many.

## The dials on your tools

All the dials are offered on your tools, within what each set can support, whether or not the knob probe showed them to bite; the recipes lead with the ones it did. The probe ran on the built-in tasks and two models, so the statuses `doctor` prints beside each dial are about those, not about your tools; the card on your tools measures your tools.

| dial | how it is applied to your tools | what it needs |
|---|---|---|
| `similarity` | lookalikes are copies of the target tool scoped to other accounts: the same name and description with a different four-digit number, and the request names the account | a tool that can be a target; levels 0, 1, 2, 3 |
| `faults` | planned `unavailable` answers in your format's error idiom; the same call then works | none; levels 0, 1, 2, 4 |
| `history` | seeded calls to your read tools totalling a number of tokens | a read tool; levels 0, 300, 600, 1200, 2400 |
| `block` | blocks drawn from your tools only, the target always present | levels of 8, 16, 32, 64 tools that your set reaches |
| `arguments` | how many of the target tool's own parameters the request states and the verifier checks | levels from 2 (or the target's required count) to 8 (or its count of checkable parameters) |
| `spread` | a target value split across the answers of 1, 2 or 4 named reads | a read that takes a checkable argument |
| `depth` | the chain follows your declared output-to-input links | flows; levels up to your longest declared chain |
| `shape` | chains of your declared links run in sequence or side by side | one declared chain whose first call takes a checkable argument |

The decoy-tools dial (`distractor`) is not offered on your tools, and no dial has a control arm there. Without flows, depth and shape are listed as unavailable with the sentence that says what to declare.

## The settings for your tools

An `[own]` table in `tasks.toml` means the tasks are on your tools; the rest of the file is as in [config.md](config.md). Every setting has an `init` option, so the command `init` prints writes the same file.

| setting | option | what it is |
|---|---|---|
| `file` | `--own-file PATH` | your tool file, beside `tasks.toml` |
| `format` | `--own-format NAME` | `auto`, `openai`, `mcp` or `openapi` |
| `name` | `--own-name NAME` | the set's name, shown on the card (default: the file's name) |
| `read`, `write` | `--own-read TOOL`, `--own-write TOOL` (repeatable) | effects the file does not say |
| `[own.intents]` | `--own-intent TOOL=TEXT` (repeatable) | what a request says instead of the tool's name |
| `[[own.flow]]` | `--own-flow FROM.FIELD:TO.PARAM` (repeatable) | a value from one tool's output (a path in it, such as `orders[].order_id`) into another's input |
| | `--mcp-command CMD` | list an MCP server's tools, with your consent |

Beside `[own]`, `[measure] preset` names any recipe the set supports (not `card`), or `custom` with any knob the set reaches; `controls = true` is refused. `[tasks] generator_version`, when set, must be `own-1`, the label of the generator that makes tasks on your tools.

## The card on your tools

Its first lines say: "Measured on your tools (acme, 5 tools from an OpenAI tools file), with responses simulated from your schemas. Your backend was never called." Then each dial's table against its first level, and beside it what the knob probe found for that dial on the built-in tasks, with the plain statement that the probe's statuses come from those tasks on two models, not from your tools.

What it does not claim, every line that applies:

- it says nothing about your real tools' outputs, errors or latency, or about your app;
- it is not comparable with the published cards or with built-in runs: the tasks differ;
- within this card, levels compare with each other; across two cards, only when the tool file, the settings and the seeds are the same;
- without an intent for every tool, choosing a tool was partly a word match with its description;
- a knob that shows no effect here may still matter in your app, and the reverse.

`poisson-tasks card --compare published` prints your card beside the published card of the same model, each whole, and pools nothing; when no published card measured your model it says so in one line and your card is read on its own. `card` ends with that command only when a published card measured your model, so the command you are shown is one that works.

## `verify`, `export` and `doctor` on your tools

In this release `poisson-tasks verify` refuses a tasks file made on your own tools, in one line (`error: <file> holds tasks on your own tools, which verify does not judge on its own yet: a run's card judges every episode on them, by replay`), and `--arm` in a folder set up for your tools the same way (`error: tasks.toml puts the tasks on your own tools, which verify does not judge on its own yet: a run's card judges every episode on them, by replay`). A run on your tools is judged by that replay, and its card reports it. `export --to verifiers` writes eval configs that name the taskset `poisson-tasks-own` and carry your set whole, so verifiers' own `eval` can run them; [verifiers-export.md](verifiers-export.md) describes the command. `doctor` also says when the newest run on the same tool file carries another digest than the file has now, because the tasks changed. A changed file changes every task's id, so the next run on it starts a new run folder and says why.
