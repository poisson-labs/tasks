# Your own tools: how the responses are made, and the contract hash

The reference half of [own-tools.md](own-tools.md): the rules Tasks' simulator answers your tools by, and how your tool file's contract hash is computed. The examples use the tool file of that page's first run:

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

## How the responses are made

Everything is pure: no clock but a fixed one, no randomness but the keyed draw, and no network.

### Answers to calls and reads

- A call the task expects, or any read, answers with a JSON object. When the tool has an output schema, the object conforms to it, with values drawn from the file's digest, the seed, the tool and its arguments; otherwise it is `{"ok": true, "id": "<value>"}`.
- Strings respect `format`, enums and bounds.
- The draw depends on the call's content and not on its position, so the same call in the same episode always gets the same answer.
- The values a task needs (a value that one call hands the next) sit in a named string field of a response, chosen when the task is made.

### Answers to writes

A write that is accepted answers with what it was sent: every argument under its name.

- When the tool has an output schema, each argument goes into the matching field of the tool's output schema when the value fits that field (drawn as usual when it does not).
- When the tool has no output schema, each goes beside `ok` and `id` (an argument named `id` is the answer's `id`).

The values a task hands from one call to the next are placed after that, so a value the task serves is never overwritten.

### Errors

Errors come in each format's own idiom:

| format | an error is |
|---|---|
| OpenAI tools | `{"error": {"code": "...", "message": "..."}}` |
| MCP | a result with `isError: true` and the message as text |
| OpenAPI | `{"status": 404, "detail": "..."}` |

| code | status | when |
|---|---|---|
| `not_found` | 404 | |
| `invalid_arguments` | 422 | |
| `not_ready` | 409 | a step before its prerequisite |
| `unavailable` | 503 | a planned fault |
| `timeout` | 504 | a planned timeout: whether the call went through is not known |
| `rate_limited` | 429 | a planned rate limit, with `retry_after: 1` beside the message in the OpenAI and OpenAPI idioms |

### The store

A small store of records keyed by the values the task names.

- A write the task expects moves its record; any other accepted write is recorded as a side effect.
- The store keeps every accepted write, and a read reflects them. After a write, a read whose checkable arguments all name values the write was sent, under the same names, answers with the written values (the latest such write wins).
- Before any such write, and for a read that shares no argument name with a write, a read answers as it always did.
- The expected write made a second time is accepted and recorded as a side effect and as a duplicate write, because Tasks cannot know that a write of yours is idempotent.

### Reads on the bad-data dials

On a `baddata` or `lagged` arm, and on no other, a read's answer also says what it was asked. The call's arguments are placed in it by the rule a write's answer follows: each under its own name in the matching field of the output schema when the value fits that field, or beside `ok` and `id` when the tool has no output schema.

An answer for another record can then be told from an answer for the record asked. A read whose output schema has no field named as one of its arguments cannot say it. On every other dial a read answers as before.

- On a `baddata` arm above level 0, the one read the request names answers wrongly the first time it is made and correctly from then on.
- On a `lagged` arm at level 1, the first read that would show the target write answers as if the write had not landed, once in an episode, and every later read shows it.

Neither is an error: both come back in the tool's ordinary answer shape, with nothing on them to say so.

## Your tool file's contract hash

Every run on your tools records, before its first request, two hashes of your file beside the generators' ([reading-a-card.md](reading-a-card.md) shows where the card prints them).

- The file's own hash is the SHA-256 of its bytes, the digest `init` shows.
- The **contract hash** is the SHA-256 of what the file says, written one fixed way, so that two files that say the same thing have the same contract hash however they are laid out.

### How it is computed

1. Read the file's bytes. Each command makes its plan from the file as it is when the command starts; a plan already made, such as the one an exported config carries, refuses a file whose bytes have changed since, because its tasks have changed.
2. Parse them as Tasks parses a tool file: as JSON, or else as YAML.
3. Write what was parsed in JSON's own terms: a YAML date or time becomes its ISO text (`2026-10-26`), and a key that is not text becomes its JSON text (an OpenAPI document's unquoted `200:` becomes `"200"`). A value JSON cannot carry (NaN, an infinity, binary data, a set, or two keys that become one, such as `200` and `"200"`) is refused in one line that names the place, and nothing is spent or written.
4. Write it as JSON with the keys sorted, no spaces, the text as UTF-8 and no escapes for characters beyond ASCII.
5. Take the SHA-256 of those bytes, in lower-case hex, with nothing added in front.

For a JSON file that is three lines of Python, with nothing of this package; on the first run's tool file it gives the same value as `poisson_tasks.provenance.tool_spec_hash`:

<!-- docs-check: run -->
```python
import hashlib, json
doc = json.loads(open("tools.json", "rb").read())
print(hashlib.sha256(json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest())

from poisson_tasks import provenance
print(provenance.tool_spec_hash(open("tools.json", "rb").read()))
```
<!-- docs-check: output -->
```
cf8af7f03f9931e506b7ba9a67ad16386c55be943bc2eb31e1f97e1d0b659157
cf8af7f03f9931e506b7ba9a67ad16386c55be943bc2eb31e1f97e1d0b659157
```

### What moves it and what does not

**What does not move it:**

- whitespace and indentation;
- the order of the keys in any object;
- JSON against YAML for the same document;
- `\u00e9` against `é`;
- a YAML date against the same text in quotes.

**What moves it:**

- any change to a string (one character of a description is enough);
- the order of a list;
- a value added or removed;
- a number's type (`1` and `1.0` are two values).

Text is hashed as it was written, with no Unicode normalisation, so an `é` written as one character and as `e` with an accent are two contracts.

The hash covers the whole file you gave, not only the tools Tasks kept from it: the file is the contract you bring and version, so a change Tasks does not read, such as a refused tool, an `info.version` or a server URL, moves it too.

### A reformatted file

**A reformatted file keeps its contract hash and still gives other tasks.** Tasks draws every task from the file's bytes, so the same tools with other whitespace give other tasks, with other ids.

`card --compare` between two such runs says so: they share one tool contract, but the file was reformatted, and tasks are drawn from the file's bytes, so their tasks differ, and no figure of one is set beside the other's.
