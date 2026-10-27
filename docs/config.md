# The settings file: `tasks.toml`

One file says what to run, against which model, and when to stop. [`init`](commands.md) writes it, once, at the end of its questions; every other command reads it. You can edit it freely, and `poisson-tasks doctor` checks it. It never holds a key, only the name of the environment variable that does.

The file is TOML. A command reads `tasks.toml` in the current folder, or the file `--config PATH` names. Every key can also be given to `init` as an option, so `poisson-tasks doctor --show-command` prints the one command that writes the file you have.

This is the file `init` writes for a first look:

<!-- docs-check: run -->
```bash
poisson-tasks init --yes --no-check-key --provider openai --recipe first-look
```
<!-- docs-check: output -->
```
ok  wrote tasks.toml: depth at 1, 3 and 8, 10 tasks each, against gpt-5-nano-2025-08-07
  tokenizer       …
  key             …
  as one command  poisson-tasks doctor --show-command prints it
next: poisson-tasks run
```

The file it wrote:

```toml
# Poisson Tasks: what to run, against which model, and when to stop.
# Edit it freely.  It never holds a key, only the name of the variable that does.
version = 1

[model]
provider = "openai"                 # openai | anthropic | ollama | vllm | openai-compatible
name = "gpt-5-nano-2025-08-07"      # the model id the endpoint expects
base_url = "https://api.openai.com/v1"
api_key_env = "OPENAI_API_KEY"      # the NAME of the variable that holds the key; "" for none.
                                    # Its name must contain API_KEY, which keeps the key from the program under test.
# allow_plain_http_key = false      # send the key over plain http to another machine

[model.price]                       # dollars per million tokens, from your provider's price page
input = 0.05
cached_input = 0.005
output = 0.4
read_on = "2026-09-25"              # when you read them

[measure]
preset = "first-look"               # first-look | error-recovery | long-sessions | planning | profile | card | custom
# With preset = "custom":
# knob = "depth"                    # depth | distractor (experimental)
# levels = [1, 3, 8]
# controls = false
# strictness = "strict"             # strict | leaky

[tasks]
per_level = 10                      # 1 to 60, from the published cards' seed list; or:
# seeds = [404, 55, 2121]
attempts = 1
# generator_version = "1"           # leave unset: another version moves every task id

[decoding]                          # sent with every model call; "not sent" leaves a field out
temperature = 1.0
top_p = 1.0
reasoning_effort = "low"
max_tokens = 2048

[limits]
spend_usd = 1.00                    # the run stops once it has spent this
# tokens = 2_000_000
max_model_calls = 32                # per episode
concurrency = 8

[output]
runs = "runs"                       # run folders go here, beside this file
tasks = "tasks"
```

## Every key

An unknown key or table is refused with the line it is on, and with the nearest one it could be when one is near (`[tasks] "per_levle" is not a setting; did you mean "per_level"?`); a value that is out of range is refused the same way:

```text
error: tasks.toml line 28: [tasks] per_level is 61; it must be from 1 to 60
```

### `version`

The settings file's version, `1`. A file written by a newer Poisson Tasks is refused, and says so.

### `[model]`

| key | what it is | allowed |
|---|---|---|
| `provider` | the kind of endpoint | `openai`, `anthropic` (through Anthropic's OpenAI-compatible endpoint), `ollama`, `vllm`, `openai-compatible` |
| `name` | the model's name as the endpoint spells it | text; the default depends on the provider |
| `base_url` | the endpoint | a URL that starts with `http://` or `https://` |
| `api_key_env` | the NAME of the variable that holds the key | a variable's name that contains `API_KEY`, or `""` for a model that needs no key. verifiers starts each episode's program in a process of its own and leaves every variable whose name contains `API_KEY` out of its environment, so a key named this way never reaches the program under test |
| `allow_plain_http_key` | send the key over plain `http` to another machine | `true` or `false`; the default is `false`, and a key is never sent in the clear to a host that is not on this machine |

`init` reads `OPENAI_BASE_URL` from your shell for the `openai` provider, and says so when it asks its questions.

### `[model.price]`

Dollars per million tokens, from your provider's price page: `input`, `cached_input`, `output`, and `read_on`, the date you read them (`"2026-09-25"`). The only price Tasks fills in is `gpt-5-nano-2025-08-07`'s, with the date it was read; check it. No price table ships. Without a price a run is capped in tokens, not dollars, and its plan shows no dollar figure.

### `[measure]`

`preset` says what to measure:

| preset | what it measures | tasks per level, attempts |
|---|---|---|
| `first-look` | where does depth start to hurt? Depth at 1, 3 and 8 | 10, 1 |
| `error-recovery` | does it retry when a call fails? Faults at 0, 1, 2 and 4 | 10, 1 |
| `long-sessions` | does earlier work in the conversation throw it off? History at 0, 600 and 2400 | 10, 1 |
| `planning` | chains and parallel steps: depth at 1, 3 and 8, and shape at 1 and 4 | 10, 1 |
| `profile` | one line per knob: depth at 1 and 8, faults at 0 and 4, history at 0 and 2400, shape at 1 and 4 | 20, 2 |
| `card` | the published cards' design: depth and the decoy-tools dial at every level, with their control arms | 60, 5 |
| `custom` | the knob and levels you name | yours |

`tool-choice` (similarity and block) and `reading-and-filling` (spread and arguments) are recipes that wait on knobs the knob probe did not ship; the file refuses them, naming the knobs. The knobs themselves stay available ([knobs-and-arms.md](knobs-and-arms.md) says what the probe found).

With `preset = "custom"`:

| key | what it is | allowed |
|---|---|---|
| `knob` | the dial | `depth`, or `distractor` (experimental); on your own tools any knob the set reaches |
| `levels` | the levels to run | a list of the levels the published cards measured: 1, 2, 3, 5 and 8 for depth, 0, 2, 4, 8 and 14 for the decoy-tools dial; on your own tools, the levels the set reaches |
| `controls` | add the control arms | `true` or `false` |
| `strictness` | what counts as a pass | `strict` or `leaky`; leaky tasks carry other ids than strict ones, so they cannot sit beside the published cards |

`knob`, `levels`, `controls` and `strictness` are refused under any other preset.

### `[tasks]`

| key | what it is | allowed |
|---|---|---|
| `per_level` | how many tasks at each level | 1 to 60. It takes the first `n` of the published cards' sixty seeds, so a first look runs the same tasks the cards measured |
| `seeds` | the tasks' seeds | a list of whole numbers, instead of `per_level` |
| `attempts` | how many attempts at each task | 1 or more; more than one shows pass@k. The published cards use 5 |
| `generator_version` | the label that enters every task id | leave it unset; another version moves every task id, so the tasks are none a published card measured |

The `card` preset is the published cards' design, so it refuses a `per_level` or `attempts` that is not that design's (60 and 5), and refuses `seeds`.

### `[decoding]`

Sent with every model call. A value of `"not sent"` leaves a field out of every request, for a provider that refuses it.

| key | allowed | default |
|---|---|---|
| `temperature` | a number above 0; it is always sent, because repeated attempts at a task need a decoding that is not deterministic | `1.0` |
| `top_p` | a number above 0 and at most 1, or `"not sent"` | `1.0` |
| `reasoning_effort` | text such as `"low"`, or `"not sent"` | `"low"` |
| `max_tokens` | a whole number, 1 or more, or `"not sent"` | `2048` |

### `[limits]`

| key | what it is | allowed | default |
|---|---|---|---|
| `spend_usd` | the run stops once it has spent this many dollars | a number above 0 | the larger of $1.00 and twice the estimate, rounded up to a whole dollar |
| `tokens` | the run stops once it has used this many tokens | a whole number | `2_000_000` when there is no price |
| `max_model_calls` | model calls allowed per episode | 1 or more | `32` |
| `concurrency` | episodes at once | 1 or more | `8` |

A run has to have a finite cap: a price and `spend_usd`, or `tokens`, or both. The cap is not part of what identifies a run, so raising it resumes the same run.

### `[output]`

`runs` and `tasks` are the folders, beside the settings file, where run folders and `generate`'s files go. They default to `runs` and `tasks`.

### `[own]`

The presence of an `[own]` table means the tasks are made on your own tools. Its keys are `file`, `format`, `name`, `read`, `write`, `[own.intents]` and `[[own.flow]]`, each with an `init` option; [own-tools.md](own-tools.md) describes them.

## Checking the file

`poisson-tasks doctor` reads the file and says what is wrong in it, with the line. `poisson-tasks run --dry-run --offline` prints the plan the file asks for without sending anything.
