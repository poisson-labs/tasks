# The commands

`poisson-tasks` is one command with seven verbs: `init`, `generate`, `run`, `card`, `verify`, `export` and `doctor`. `python -m poisson_tasks` is the same command. This page gives each verb's help as it prints, and what the help does not say: what the verb writes, what it refuses, and how it ends.

Every verb takes `--config PATH` (the settings file; `tasks.toml` in the current folder by default), `--json`, `--plain` and `--debug`. Options may come before or after the verb, and an abbreviated option is refused. The settings file is described in [config.md](config.md).

## How a command ends

The first line a verb prints on standard output is a verdict line: a word, two spaces and a sentence (`ok  card for gpt-5-nano-2025-08-07: ...`). Detail follows, and the last line, when there is an obvious next step, is `next: <the command>`. A problem is an `error:` line on standard error that says what to do, followed by a `next:` line when there is a command to run; an unexpected failure prints one line that names a log file, and the traceback goes to that file (`--debug` prints it too).

| code | meaning |
|---|---|
| 0 | Done: the result is printed, whatever it says. |
| 1 | Refused: nothing was spent or written. |
| 2 | The command line is wrong. |
| 3 | Stopped or failed after work started; what was kept is printed. |
| 4 | A check you asked for did not pass: `verify` did not give `passed`, `doctor` found the environment not ready, `card --check` or `card --published` found a card that does not rebuild. |
| 130 | Interrupted with Ctrl-C. |

`--json` prints the result as one JSON document on standard output (its first key, `schema`, names the document), with the same exit code. Errors stay on standard error, in text.

## Two renderings

Every result is drawn one of two ways. The pretty rendering uses colour and a live display, and runs only when both standard output and standard error are terminals, `NO_COLOR` is unset or empty, `CI` is unset, `TERM` is not `dumb`, standard output is UTF-8, and neither `--json` nor `--plain` was given. Everywhere else, and always when you ask with `--plain`, the plain rendering runs: text only, the same facts in the same order. This page shows the plain rendering.

## poisson-tasks

<!-- docs-check: run -->
```bash
poisson-tasks --help
```
<!-- docs-check: output -->
```
usage: poisson-tasks [-h] [--version] [--config PATH] [--json] [--plain]
                     [--debug]
                     command ...

Tool-use tasks with a known right answer, generated on your machine, and a
card that says what each level of difficulty was worth to the model you ran.

options:
  -h, --help     show this help message and exit
  --version      print the version of this package, verifiers and Python, and
                 exit
  --config PATH  the settings file to read, or to write (default:
                 ./tasks.toml)
  --json         print the result as one JSON document on stdout (default:
                 text)
  --plain        the plain style, text only, even on a terminal (default:
                 pretty on a terminal, plain in a pipe, under NO_COLOR or CI,
                 or with --json)
  --debug        on an unexpected failure, print the traceback as well as
                 writing it to the log (default: the log only)

commands:
  command
    init         ask what to test and write tasks.toml; spends nothing
    generate     make the plan's tasks with no model and no network, or show
                 one
    run          show the plan and its cost, ask, then run the tasks against
                 the model
    card         what each level was worth, from a run
    verify       judge an answer with the task's own verifier, with no model
    export       write the configs another runner reads
    doctor       say whether this environment is ready, and what to do if not

examples:
  poisson-tasks             on a terminal, with no command: a guided session
  poisson-tasks init        answer a few questions; writes tasks.toml and spends nothing
  poisson-tasks run         show the plan and its cost, ask, then run
  poisson-tasks card        what each level was worth to the model
  poisson-tasks run --help  one command's flags, defaults and examples

exit codes:
  0    done: the result is printed, whatever it says
  1    refused: nothing was spent or written
  2    the command line is wrong
  3    stopped or failed after work started; what was kept is printed
  4    a check you asked for did not pass
  130  interrupted
```

`--version` prints the package's version, the version of verifiers it runs on and Python's, and exits 0.

## The guided session

`poisson-tasks` with no command, on a terminal (standard input, output and error all terminals, `CI` unset, no `--json`), opens a guided session and stays open. It may carry `--config PATH`, `--plain` and `--debug`. Anywhere else, in a pipe, with standard input redirected, under `CI` or with `--json`, a bare command is a usage error, exit 2, whose line names the session and ends with `next: <the folder's first step>` as a command.

The session opens with its banner, then one of two screens:

- **with no `tasks.toml` at the config path, the run-through**, five steps in order, each a verb: set up (`init`'s dialogue, which first asks what to test, a model on the built-in tasks or on your own tools), one task (`generate --show`), the run (`run`, with its plan, cost and `Start? [y/N]`), the card (`card`), and what next. A no at the run's question, or Ctrl-C inside any step, ends the run-through on the home screen for whatever is now on disk;
- **otherwise, the home screen**: a status block read from the folder alone (the settings in words, the key's variable and whether it is set, the environment, each run with its episodes kept of total, dollars and card, the latest card's levels), then `next`, at most five numbered steps for the folder's state.

The prompt takes a step's number (Enter is step 1) or a word: `run`, `again`, `card`, `more`, `replies`, `task`, `verify`, `runs`, `settings`, `setup`, `flow`, `export`, `check`, `home`, `help` and `quit`. A word may take one argument: `card 2` is the second run listed, `task 3` the third task of the first arm, `task d3` the first task of the arm whose id ends `d3`. Tab completes a word; `help` lists them.

Every action is one of the seven verbs' command lines, run through the same parser and verb as the command, so what it writes is byte for byte what that command writes from a shell; under its result the session prints `same as  <the command>`, dim. Nothing calls a model until you answer yes at `run`'s own question, and the session never passes `--yes` to `run`. The home screen, the card view, `task`, `runs`, `settings`, `replies`, `more` and `flow` open no socket; `check` runs `doctor --offline` and then offers the key check as a step.

Ctrl-C at a question inside a step stops that step as the command does (nothing written) and the session returns to its prompt; during a run it is the run's own interrupt, and step 1 is then the resume; at the prompt it clears the line, and twice on an empty line it leaves. `quit` and Ctrl-D leave the same way. Leaving at the prompt exits 0. An unexpected failure inside an action is its one `error:` line, and the session stays open; one in the session itself exits 3.

On a terminal with `--plain`, `NO_COLOR` or `TERM=dumb` the session opens in the plain look: numbered menus answered by typing, a plain prompt, no escape sequence, the same facts in the same order. Under `NO_COLOR` the banner is its text alone; with `--plain`, with `TERM=dumb`, or below 26 columns, it is the one line `Poisson Labs  tasks <version>`.

## init

Asks what to test (a model on the built-in tasks, or on your own tools), which model, which environment variable holds its key (it records the variable's name and never the key), what to measure and when to stop, and writes `tasks.toml`; its questions are numbered as asked, and its closing screen points at `doctor --show-command`, which prints the same setup as one command you can run again with no questions. It spends nothing. If the tokenizer file is missing it asks to fetch it first (3.6 MB, once, into the installed package). It can check your key with one free request, after asking.

The providers are `openai`, `anthropic` (through its OpenAI-compatible endpoint), `ollama`, `vllm` and `openai-compatible` (any endpoint that speaks the OpenAI chat API). Measuring tasks on your own tools, an OpenAI tools file, an MCP tool list or an OpenAPI document, is the first question's second answer, after which `init` asks for the file before any recipe; [own-tools.md](own-tools.md) describes it. `init --force` keeps the file it replaces as `tasks.toml.bak` and says so.

`init` refuses to replace a `tasks.toml` that is already there unless you pass `--force`, and refuses to ask questions when standard input is not a terminal (pass `--yes` and the answers as options). Ctrl-C at any question writes nothing.

A setup with no questions, for a script or a second machine:

<!-- docs-check: run -->
```bash
poisson-tasks init --yes --no-check-key --provider openai --recipe first-look --tasks-per-level 10
```
<!-- docs-check: output -->
```
ok  wrote tasks.toml: depth at 1, 3 and 8, 10 tasks each, against gpt-5-nano-2025-08-07
  tokenizer       …
  key             …
  as one command  poisson-tasks doctor --show-command prints it
next: poisson-tasks run
```

<!-- docs-check: run -->
```bash
poisson-tasks init --help
```
<!-- docs-check: output -->
```
usage: poisson-tasks init [-h] [--config PATH] [--json] [--plain] [--debug]
                          [--yes] [--force] [--fetch] [--no-fetch]
                          [--check-key] [--no-check-key] [--provider NAME]
                          [--model TEXT] [--base-url URL] [--api-key-env TEXT]
                          [--allow-plain-http-key] [--price I,C,O]
                          [--price-read-on DATE] [--no-price] [--recipe NAME]
                          [--measure NAME] [--knob NAME] [--levels L,L,…]
                          [--controls] [--no-controls] [--strictness NAME]
                          [--tasks-per-level N] [--seeds L,L,…] [--attempts N]
                          [--generator-version TEXT] [--temperature X]
                          [--top-p X] [--reasoning-effort TEXT]
                          [--max-tokens N] [--spend-cap X] [--token-cap N]
                          [--max-model-calls N] [--concurrency N]
                          [--runs-dir TEXT] [--tasks-dir TEXT]
                          [--own-file PATH] [--own-format NAME]
                          [--own-name NAME] [--own-read TOOL]
                          [--own-write TOOL] [--own-intent TOOL=TEXT]
                          [--own-flow FROM.FIELD:TO.PARAM] [--mcp-command CMD]

A guided setup. It asks what to test (a model on the built-in tasks, or on
your own tools), which model, which environment variable holds its key (it
records the variable's name, never the key), what to measure and when to stop,
then writes tasks.toml; doctor --show-command prints the same setup as one
command. It fetches the tokenizer file first if it is missing. It spends
nothing.

options:
  -h, --help            show this help message and exit
  --config PATH         the settings file to read, or to write (default:
                        ./tasks.toml)
  --json                print the result as one JSON document on stdout
                        (default: text)
  --plain               the plain style, text only, even on a terminal
                        (default: pretty on a terminal, plain in a pipe, under
                        NO_COLOR or CI, or with --json)
  --debug               on an unexpected failure, print the traceback as well
                        as writing it to the log (default: the log only)
  --yes                 no questions: every answer from a flag or its default
                        (default: ask)
  --force               replace an existing settings file (default: refuse)
  --fetch               fetch the tokenizer file if it is missing (default:
                        ask, then fetch)
  --no-fetch            do not fetch the tokenizer file; the file is still
                        written, with no estimate
  --check-key           check the key with one free request (default: ask,
                        then check)
  --no-check-key        make no network call
  --provider NAME       the provider: openai, anthropic, ollama, vllm or
                        openai-compatible (default: openai)
  --model TEXT          the model's name, as the provider spells it (default:
                        the preset's; no default for openai-compatible)
  --base-url URL        the endpoint; required for openai-compatible, else the
                        preset's (default: the preset's; no default for
                        openai-compatible)
  --api-key-env TEXT    the variable that holds the key; "" for none (default:
                        the preset's; no default for openai-compatible)
  --allow-plain-http-key
                        send the key over plain http to another machine
  --price I,C,O         the price, dollars per million tokens: input, cached
                        input, output (default: the published price for
                        gpt-5-nano-2025-08-07, else none)
  --price-read-on DATE  the date the prices were read, as 2026-09-25 (default:
                        none)
  --no-price            no price: the cap is then in tokens
  --recipe NAME         what to measure: first-look, card or custom, or a
                        recipe your tools reach (default: first-look)
  --measure NAME        an alias of --recipe, kept for one release
  --knob NAME           with --recipe custom: depth or distractor (default:
                        depth)
  --levels L,L,…        with --recipe custom: the levels, comma-separated
                        (default: every level of the knob)
  --controls            with --recipe custom: add the control arms
  --no-controls         with --recipe custom: no control arms
  --strictness NAME     with --recipe custom: strict or leaky (default:
                        strict)
  --tasks-per-level N   how many tasks per level (default: 10)
  --seeds L,L,…         the tasks' seeds, comma-separated, instead of --tasks-
                        per-level (default: none)
  --attempts N          how many attempts at each task (default: 1)
  --generator-version TEXT
                        the label that enters every task id (default: none)
  --temperature X       the decoding's temperature (default: 1.0)
  --top-p X             the decoding's top-p, or "not sent" (default: 1.0)
  --reasoning-effort TEXT
                        the decoding's reasoning effort, or "not sent"
                        (default: low)
  --max-tokens N        the decoding's token limit per reply, or "not sent"
                        (default: 2048)
  --spend-cap X         stop the run once it has spent this many dollars
                        (default: the larger of $1.00 and twice the estimate)
  --token-cap N         stop the run once it has used this many tokens
                        (default: 2,000,000 without a price)
  --max-model-calls N   the model calls allowed per episode (default: 32)
  --concurrency N       how many episodes run at once (default: 8)
  --runs-dir TEXT       where runs are kept (default: runs)
  --tasks-dir TEXT      where generate writes its files (default: tasks)
  --own-file PATH       your own tools: the tool file, an OpenAI tools file,
                        an MCP tool list or an OpenAPI document, beside
                        tasks.toml (default: none)
  --own-format NAME     with --own-file: auto, openai, mcp or openapi
                        (default: auto)
  --own-name NAME       with --own-file: the set's name, shown on the card
                        (default: the file's name)
  --own-read TOOL       with --own-file: a tool whose effect the file does not
                        say is a read; repeatable (default: none)
  --own-write TOOL      with --own-file: a tool whose effect the file does not
                        say is a write; repeatable (default: none)
  --own-intent TOOL=TEXT
                        with --own-file: TOOL=TEXT, what a request says
                        instead of the tool's name; repeatable (default: none)
  --own-flow FROM.FIELD:TO.PARAM
                        with --own-file: FROM.FIELD:TO.PARAM, a value from one
                        tool's output into another's input, which depth and
                        shape need; repeatable (default: none)
  --mcp-command CMD     your own tools from an MCP server: the command that
                        starts it over stdio; it is started once, with your
                        consent (--yes is consent), to list its tools into
                        tools.mcp.json beside tasks.toml, and stopped; the
                        command itself is kept nowhere (default: none)

examples:
  poisson-tasks init
  poisson-tasks init --yes --provider openai --spend-cap 1.00
  poisson-tasks init --force
  poisson-tasks init --yes --recipe custom --knob depth --levels 1,3 --no-check-key
  poisson-tasks init --own-file tools.json --own-flow get_order.order_id:refund_order.order_id
  poisson-tasks init --yes --mcp-command 'python my_server.py'
```

## generate

Makes the plan's tasks with no model and no network, checks the contrast through the pin ledger (the checks that two levels of a knob differ in that knob and in nothing else; see [knobs-and-arms.md](knobs-and-arms.md)), and writes them as files, one file per level, in the form `poisson_tasks.export` reads (JSON Lines, one task per line). Without a settings file it takes `--arm depth:d3` (repeatable), or `--knob` with `--levels`. It refuses to replace files that are already there unless you pass `--force`.

With `--show` it prints one task the way a model would see it: the system prompt and the request, the tools and which of them the task needs, the reference solution with what the domain returns for each call, and the verdict on every wrong answer the task ships with. `--task N` picks the task by its place in the plan, counting from 1; `--seed S` picks one by a seed you chose. With no `--arm` it shows the plan's first arm's first task and names the other arms in a row of its own.

<!-- docs-check: run -->
```bash
poisson-tasks generate --arm depth:d3 --show --task 7 | head -n 13
```
<!-- docs-check: output -->
```
ok  depth:d3 task 7 (seed 394421153): needs 3 tool calls and a reply (4 model calls); a run allows 32 model calls
  task id  …

what the model is shown
  You operate a record ledger through the tools you are given.
  Each tool call returns one fixed-width line: a sequence number, a status word, and a payload.
  A ledger record moves one stage at a time, and each stage tool needs what the stage before it returned.
  Make one tool call per turn, and reply in plain text once the request is satisfied.

  Advance record "building-login-growth-party" of the inventory ledger.
  Stage ladder: review then sample then measure then monitor then compare then bundle then route then label.
  Raise that record through measure, and no further.
  Open with entry code "inform"; each later stage needs what the stage before returned.
```

<!-- docs-check: run -->
```bash
poisson-tasks generate --help
```
<!-- docs-check: output -->
```
usage: poisson-tasks generate [-h] [--config PATH] [--json] [--plain]
                              [--debug] [--arm ID] [--knob NAME]
                              [--levels L,L,…] [--controls] [--no-controls]
                              [--tasks-per-level N] [--seeds S,S,…]
                              [--strictness NAME] [--generator-version V]
                              [--out DIR] [--print] [--show] [--task N]
                              [--seed S] [--force]

Generates the plan's tasks with no model and no network, checks the contrast
through the pin ledger, and writes them as files, one per level, in the form
other runners read. With --show it prints one task the way a model would see
it, with its reference solution and the verdict on every wrong answer it ships
with.

options:
  -h, --help            show this help message and exit
  --config PATH         the settings file to read, or to write (default:
                        ./tasks.toml)
  --json                print the result as one JSON document on stdout
                        (default: text)
  --plain               the plain style, text only, even on a terminal
                        (default: pretty on a terminal, plain in a pipe, under
                        NO_COLOR or CI, or with --json)
  --debug               on an unexpected failure, print the traceback as well
                        as writing it to the log (default: the log only)
  --arm ID              an arm to generate, as depth:d3; repeatable (default:
                        the settings file's plan)
  --knob NAME           instead of --arm: the knob, depth or distractor; on
                        your own tools, any knob the set reaches (default:
                        none)
  --levels L,L,…        with --knob: the levels, comma-separated (default:
                        every level)
  --controls            with --knob: add the control arms (default: no)
  --no-controls         with --knob: no control arms
  --tasks-per-level N   how many tasks per level, the published seeds' first N
                        (default: 10, or the settings file's)
  --seeds S,S,…         the tasks' seeds, comma-separated, instead of --tasks-
                        per-level
  --strictness NAME     strict or leaky (default: strict, or the settings
                        file's)
  --generator-version V
                        the label that enters every task id (default: the
                        package's)
  --out DIR             where the files go (default: the settings file's tasks
                        folder, or ./tasks/)
  --print               write the tasks to stdout as JSON Lines instead of
                        files
  --show                print one task in full, with one arm; writes nothing
  --task N              with --show: the task's place in the plan, counting
                        from 1 (default: 1)
  --seed S              with --show: a seed you chose, instead of --task
  --force               write over files already there (default: refuse)

examples:
  poisson-tasks generate
  poisson-tasks generate --arm depth:d3 --show --task 7
  poisson-tasks generate --knob depth --levels 1,3 --tasks-per-level 5 --print
```

## run

Reads `tasks.toml`, makes the tasks, checks your key with a free request, prints the plan, asks, and then runs every episode against the model, one arm after another. The plan says how many episodes there are, how many model calls to expect and what they will cost, where the estimate comes from, the cap, and what the first episode installs (see [the README](https://github.com/poisson-labs/tasks/blob/main/README.md)). It asks `Start? [y/N]` on standard error; `--yes` skips the question, and without a terminal and without `--yes` it prints the plan and refuses.

The cap is a bound on what the run spends: the run stops once its measured spend plus what it has reserved for the episodes in flight would reach the cap, so it can pass the cap by at most the cost of the calls already in flight. Ctrl-C stops dispatching, waits up to ten seconds for the episodes in flight, keeps everything finished and exits 130; run the command again to pick up where it stopped. A second Ctrl-C stops at once, and nothing finished is lost. `--spend-cap` and `--token-cap` change the cap for one run, and raising it resumes the same run. `--again` starts a second run of the same plan in a folder of its own.

How a run ends:

| ends | first line | code |
|---|---|---|
| every episode ran | `done  30 of 30 episodes, $0.011 spent`, then `next: poisson-tasks card` | 0 |
| the cap | `stopped  the spend cap: ...`, then `next: poisson-tasks run --spend-cap ...` | 3 |
| the provider is out of credit | `stopped  the provider says the account is out of credit ...` | 3 |
| the first five episodes all fail | `stopped  the first 5 episodes all failed before the model answered: ...` | 3 |
| no model call and no finished episode in the first 600 seconds | `stopped  nothing happened: no model call and no finished episode before the start-up watchdog fired; ...` | 3 |
| Ctrl-C | `stopped  interrupted: ... kept`, then `next: poisson-tasks run` | 130 |

A run writes into its folder, `runs/<preset>-<model>/`: `plan.json` (the plan and its hash, by which the folder is found again), `spend.jsonl` (one line for each episode that ended), `run.log`, one folder of traces per arm, and `produced_by.jsonl`, what produced the run, written before its first request: the package and verifiers versions, the generator's hash (and on your own tools the own-tools generator's and your tool file's contract hash), the plan's hash and its seeds. A resume adds a line to it; a run with nothing left to do adds none. `--json` carries the line the run wrote as `produced_by`, or `null`. A folder started with another generator or another tool contract than this install and the file give now holds other tasks, so a resume of it is refused before anything is spent, naming the two hashes: `error: runs/first-look-gpt-5-nano was started with another generator than this install's (b460964dc153 there, 1a2b3c4d5e6f here), so its tasks are not the ones this install makes; finish it with poisson-tasks 0.2.0, or move the folder aside to run the plan from the start`. Another package version alone is not refused.

An episode that ran and failed for a reason that is not the model's (an API error, a timeout) is owed again and counted apart; a run of which every episode failed never exits 0. A run that is refused before anything is spent exits 1 with one line: the key is not set or refused, the model is not found, the endpoint cannot be reached, a setting is wrong, the tokenizer file is missing, or the estimate is above the cap. `run` does not work on Windows, and says so.

A plan, without sending anything:

<!-- docs-check: run -->
```bash
poisson-tasks run --dry-run --offline
```
<!-- docs-check: output -->
```
plan  30 episodes against gpt-5-nano-2025-08-07: about $0.02, and the run stops at $1.00
  tasks     depth at 1, 3 and 8, 10 tasks each · strict
  model     gpt-5-nano-2025-08-07 at api.openai.com · key in OPENAI_API_KEY: not checked (--offline)
  calls     150 if every task is solved the shortest way · about 190 expected · at most 960 (32 per episode)
  cost      about $0.02 expected · the run stops at $1.00
  estimate  from the published gpt-5-nano card for this model
  harness   the first episode runs uv's installer (astral.sh inside a virtualenv) and fetches four packages and their dependencies from PyPI
  folder    runs/first-look-gpt-5-nano-2025-08-07 (a new run)
```

<!-- docs-check: run -->
```bash
poisson-tasks run --help
```
<!-- docs-check: output -->
```
usage: poisson-tasks run [-h] [--config PATH] [--json] [--plain] [--debug]
                         [--yes] [--dry-run] [--offline] [--spend-cap USD]
                         [--token-cap N] [--again] [--run NAME]
                         [--concurrency N]

Reads the settings file, generates the tasks, checks the key with a free
request, prints the plan with the expected calls and cost and the cap, asks,
then runs every episode, stopping at the cap and resuming an interrupted run
when started again.

options:
  -h, --help       show this help message and exit
  --config PATH    the settings file to read, or to write (default:
                   ./tasks.toml)
  --json           print the result as one JSON document on stdout (default:
                   text)
  --plain          the plain style, text only, even on a terminal (default:
                   pretty on a terminal, plain in a pipe, under NO_COLOR or
                   CI, or with --json)
  --debug          on an unexpected failure, print the traceback as well as
                   writing it to the log (default: the log only)
  --yes            start without asking (default: ask)
  --dry-run        print the plan and exit 0; the free key check still runs
                   unless --offline
  --offline        skip the key check; only with --dry-run
  --spend-cap USD  stop at this many dollars, for this run (default: the
                   settings file's)
  --token-cap N    stop at this many tokens, for this run (default: the
                   settings file's)
  --again          start a second run of the same plan instead of resuming or
                   reporting it complete
  --run NAME       resume or report the run folder of that name (default: the
                   plan's own)
  --concurrency N  how many episodes run at once (default: the settings
                   file's)

examples:
  poisson-tasks run
  poisson-tasks run --yes
  poisson-tasks run --dry-run --offline
  poisson-tasks run --spend-cap 2.00
  poisson-tasks run --again
```

## card

Builds the card from a run folder: a line for every level (strict pass@1 with its 95% interval, leaky pass@1, overshoot, and the tasks and attempts behind them), what the card means, and what it does not claim. It writes `card.md`, `artifact.json`, `episodes.jsonl` and `tallies.json` into the run's `card/` folder, and refuses to replace a card that is already there unless you pass `--force`. [reading-a-card.md](reading-a-card.md) explains every column.

A card from a run that was stopped is built from what ran, and every level that did not finish is marked. A level where more than 10% of attempts made no tool call is not published, and neither is its card: it would measure whether the model starts, not how hard the level is. A level where more than 2% of attempts failed for a reason that is not the model's refuses the card the same way. That refusal exits 1, says that those attempts answered in text instead of calling a tool, names each level's `traces.jsonl` in the run folder, where the replies are, and ends with the command that shows the task they answered.

`--published` rebuilds the cards that ship with the package from their own records, checks each against its stored artifact byte for byte, and says whether it is current for this install. It is free. `--check PATH` does the same for a card folder or a calibration bundle `.zip`; exit 4 means a difference. `--page` writes the one page for every published card. The result names its run in a `run` row (the folder, the dollars spent from its ledger, episodes kept of total) and, when there is something to say, how it stands beside the published cards in one row: on the built-in tasks under a model a published card measured, `measured on an earlier build of the generator, so this release does not set them side by side`; on your own tools, `different tasks, so none of its figures reads against theirs`. `--compare published` reads the card already written (no `--force`), prints that verdict first as one line, `different  ...`, writes `card/compare.md` (your own-tools card beside the published card of its model, each whole, pooling nothing; on the built-in tasks the earlier-build sentence alone) and prints neither card; exit 0. `card` never ends by suggesting it.

The result's `made with` row, right after `run`, says what produced the run as the run recorded it, and `--json` carries the record as `produced_by` (`null` for a run made before poisson-tasks 0.2.0); [reading-a-card.md](reading-a-card.md) says what each hash covers.

`--compare OTHER_RUN` puts this run's card beside another run's, given by its folder, and decides on what produced each. The first answer that applies is the one given:

1. both runs recorded what produced them and a generator differs: `different`, naming both hashes, because their tasks differ and a shift between them is not the model's alone;
2. both recorded, and the tool contract differs (on your own tools): `different`, naming both contract hashes;
3. both recorded, one contract, but the file was reformatted (its bytes differ): `different`, since tasks are drawn from the file's bytes;
4. no level is on both: `different`;
5. a run recorded nothing (made before poisson-tasks 0.2.0) and the task ids differ on a level both hold: `different`, saying that whether its tools or generator changed is not known;
6. the two were measured another way (the seeds, the attempts, the decoding, the strictness, the split): `different`, saying which;
7. both recorded and the task ids still differ: `different`, since their `[own]` settings differ;
8. otherwise `ok`: they measured the same tasks the same way, with one `note:` when only the package or verifiers version differs, or when a run recorded nothing but its task ids match.

A task id is a hash over every field of the task, the generator's hash and the tool file's digest among them, so equal ids are the same tasks. `card/compare.md` in this run's folder starts with a table, **What produced each**, one row per recorded value with both runs' values and the rows that differ marked; for `ok` the two cards follow side by side, and for `different` the verdict line comes first and both cards' documents follow whole, with no figure of one set beside the other's. Nothing is written into the other run's folder, and neither card is printed. Exit 0 for `ok` and `different`, 1 when a card is refused or the other folder is not a run folder (`error: OTHER is not a run folder: it holds no plan.json`), and 2 when it names this run's own folder. `--json` carries `verdict`, `sentence`, `note`, `changed` (the recorded values that differ), `a` and `b` (each run's `folder` and `produced_by`) and `wrote`.

<!-- docs-check: run -->
```bash
poisson-tasks card --published
```
<!-- docs-check: output -->
```
ok  every published card rebuilds from its records byte for byte
  gpt-5-nano  rebuilds byte for byte from 4,200 records · not current: this install's generator differs from the card's
  qwen3-8b    rebuilds byte for byte from 4,200 records · not current: this install's generator differs from the card's
```

<!-- docs-check: run -->
```bash
poisson-tasks card --help
```
<!-- docs-check: output -->
```
usage: poisson-tasks card [-h] [--config PATH] [--json] [--plain] [--debug]
                          [--print] [--published [NAME]] [--page] [--out FILE]
                          [--compare WHAT] [--check PATH] [--force]
                          [RUN]

Builds the card from a run folder: the per-episode records, the machine-
readable artifact and the document, and prints the verdict, a line per level,
and the card's plain statement of what it means and what it does not claim.

positional arguments:
  RUN                 a run folder (default: the settings file's newest run)

options:
  -h, --help          show this help message and exit
  --config PATH       the settings file to read, or to write (default:
                      ./tasks.toml)
  --json              print the result as one JSON document on stdout
                      (default: text)
  --plain             the plain style, text only, even on a terminal (default:
                      pretty on a terminal, plain in a pipe, under NO_COLOR or
                      CI, or with --json)
  --debug             on an unexpected failure, print the traceback as well as
                      writing it to the log (default: the log only)
  --print             print the whole card document after the summary
  --published [NAME]  recompute a card shipped with the package from its
                      records, by the model's short name (gpt-5-nano or
                      qwen3-8b), or every one (default: the run's card)
  --page              write the one page for every published card, plus this
                      run's card when it was measured the same way
  --out FILE          with --page: where to write it (default: calibration.md)
  --compare WHAT      put this run's card beside the published ones (--compare
                      published) or beside another run's (--compare OTHER_RUN)
  --check PATH        recompute a card folder, or a calibration bundle .zip,
                      from its records and compare it with its artifact; exit
                      4 on any difference
  --force             write over a card already there (default: refuse)

examples:
  poisson-tasks card
  poisson-tasks card runs/first-look-my-model
  poisson-tasks card --published
  poisson-tasks card --published gpt-5-nano
  poisson-tasks card --print
  poisson-tasks card runs/first-look-my-model --compare runs/first-look-my-model-2
```

## verify

Runs the verifier a task was generated with, with no model. With `--self-check` it checks the task's own answers: the reference solution passes under both strictnesses, and each wrong answer the task ships with earns the outcome it is named for. With `--transcript FILE` it judges your own agent's attempt at the task, in one of three forms (OpenAI chat messages, one row of a verifiers `traces.jsonl`, or this tool's own turns). A task is named by its arm and its place in the plan (`--arm depth:d3 --task 7`), or by a seed you chose, or by a file `generate` wrote (`--tasks FILE`, with `--task N`).

The verdict word is the outcome itself (`passed`, `overshoot`, `wrong_state`, ...). `verify` exits 0 when the verdict is `passed` and 4 otherwise, so a script can gate on it.

In this release `verify` refuses a tasks file made on your own tools, in one line, and exits 1: `error: <file> holds tasks on your own tools, which verify does not judge on its own yet: a run's card judges every episode on them, by replay`. It refuses `--arm` in a folder set up for your own tools the same way, and exits 1: `error: tasks.toml puts the tasks on your own tools, which verify does not judge on its own yet: a run's card judges every episode on them, by replay`. A run on your own tools is judged by that replay, and its card reports it; judging a single own-tools task with `verify` comes in a later release. The `--arm` refusal ends with a `next:` line that is a complete command: `card` when the folder holds a run, else `generate --show`. With nothing to judge, or no task named, `verify` refuses with `next: poisson-tasks verify --self-check --arm <the plan's first arm> --task 1`.

<!-- docs-check: run -->
```bash
poisson-tasks verify --arm depth:d3 --task 7 --self-check
```
<!-- docs-check: output -->
```
ok  depth:d3 task 7 (seed 394421153): the reference solution passes and each of the 7 wrong answers earns its outcome
  reference solution       passed under both strictnesses (3 tool calls)
  wrong_state              wrong_state · The model stopped with the record in a state that is not the goal.
  turn_limit               turn_limit · The model used every model call it was allowed before it finished.
  collateral_mutation      collateral_mutation · The model reached the goal but also changed something the task did not ask for.
  overshoot                overshoot · The model reached the goal and then kept changing the record past it.
  malformed_call_clause_2  malformed_call · The model wrote a tool call the harness could not read.
  malformed_call_clause_3  malformed_call · The model wrote a tool call the harness could not read.
  malformed_call_clause_4  malformed_call · The model wrote a tool call the harness could not read.
```

<!-- docs-check: run -->
```bash
poisson-tasks verify --help
```
<!-- docs-check: output -->
```
usage: poisson-tasks verify [-h] [--config PATH] [--json] [--plain] [--debug]
                            [--arm ID] [--task N] [--seed S] [--tasks FILE]
                            [--self-check] [--transcript FILE]
                            [--hit-turn-limit]

Runs the verifier a task was generated with. With --self-check, the reference
solution passes and each wrong answer the task ships with earns the outcome it
is named for. With --transcript, your own agent's attempt at the task is
judged: OpenAI chat messages, one row of a verifiers traces.jsonl, or this
tool's own turns. Exit 0 when the verdict is passed, 4 otherwise.

options:
  -h, --help         show this help message and exit
  --config PATH      the settings file to read, or to write (default:
                     ./tasks.toml)
  --json             print the result as one JSON document on stdout (default:
                     text)
  --plain            the plain style, text only, even on a terminal (default:
                     pretty on a terminal, plain in a pipe, under NO_COLOR or
                     CI, or with --json)
  --debug            on an unexpected failure, print the traceback as well as
                     writing it to the log (default: the log only)
  --arm ID           the task's arm, as depth:d3 (default: none; or --tasks)
  --task N           the task's place in the plan, counting from 1: the
                     settings file's seeds, or the published sixty (default:
                     1)
  --seed S           a seed you chose, instead of --task
  --tasks FILE       a file generate wrote; --task N counts in it (default:
                     none)
  --self-check       check the task's own answers: the reference solution and
                     each wrong one
  --transcript FILE  your agent's attempt, in one of the three forms (default:
                     none)
  --hit-turn-limit   the attempt was cut off by a turn limit, when the form
                     cannot say

examples:
  poisson-tasks verify --arm depth:d3 --task 7 --self-check
  poisson-tasks verify --arm depth:d3 --task 7 --transcript attempt.json
  poisson-tasks verify --tasks tasks/depth-d3.jsonl --task 2 --self-check
```

## export

Writes the plan's tasks as configs another runner reads. There is one target now, `--to verifiers`: one eval config for every arm, `eval-<arm>.json`, holding the taskset, the arm, the seeds, the model, the endpoint, the name of the key's variable (never the key) and the decoding, with `push` off. It prints, for each file, the command that runs it, with verifiers' `eval` by its absolute path in this environment, so that the shell's own `eval` builtin cannot take its place ([verifiers-export.md](verifiers-export.md) says why that matters). Beside the configs it writes `produced_by.json`: what produces the plan's tasks (the package and verifiers versions, the generator's hash, on your own tools the own-tools generator's and your tool file's contract hash, the plan's hash and its seeds), with no time in it, so two exports of one plan write the same bytes; `--json` carries it as `produced_by`. The configs carry nothing of it: they are what `run` sends. `export` reads no key and opens no socket, and refuses to replace files that are already there unless you pass `--force`.

Run that way, `eval` runs what `run` runs for the arm, without what `run` adds: the plan, the spend cap, the tally of failures that are not the model's, the stop when the account is out of credit, the stop for a streak of failures, and the watchdog. It also exits 0 when every episode errored. So each printed command calls the model and spends money with no cap and no estimate, and `export` says so in the line above them.

<!-- docs-check: run -->
```bash
poisson-tasks export --to verifiers | head -n 4
```
<!-- docs-check: output -->
```
ok  wrote 3 verifiers configs, one per arm: depth at 1, 3 and 8, 10 tasks each
  note  run that way, eval leaves out what run adds (the plan, the instrument tally, the out-of-credit stop, the failure-streak stop and the watchdog), and it exits 0 when every episode errored

Each of these runs calls the model and spends money with no cap; poisson-tasks run is the way with a cap.
```

<!-- docs-check: run -->
```bash
poisson-tasks export --help
```
<!-- docs-check: output -->
```
usage: poisson-tasks export [-h] [--config PATH] [--json] [--plain] [--debug]
                            [--to RUNNER] [--out DIR] [--force]

Writes the plan's tasks as configs another runner reads: with --to verifiers,
one eval config per level, each the one run uses for that level, and prints
the command that runs it. Run that way, eval leaves out what run adds: the
plan, the spend cap, the instrument tally, the out-of-credit stop, the
failure-streak stop and the watchdog, and it exits 0 when every episode
errored.

options:
  -h, --help     show this help message and exit
  --config PATH  the settings file to read, or to write (default:
                 ./tasks.toml)
  --json         print the result as one JSON document on stdout (default:
                 text)
  --plain        the plain style, text only, even on a terminal (default:
                 pretty on a terminal, plain in a pipe, under NO_COLOR or CI,
                 or with --json)
  --debug        on an unexpected failure, print the traceback as well as
                 writing it to the log (default: the log only)
  --to RUNNER    the runner (default: verifiers, the one runner there is)
  --out DIR      where the configs go (default: export/ beside the settings
                 file)
  --force        write over files already there (default: refuse)

examples:
  poisson-tasks export --to verifiers
  poisson-tasks export --to verifiers --out configs/
```

## doctor

Says whether this environment can run the settings file, line by line: Python, the package, the tokenizer file, the settings, the key, the harness and the platform. Each line carries its own status word: `ok` for a check that passed, `note` for information (the knob probe's rows, a flows row), `refused` for a tool in your file that Tasks will not use, and `not ok` for a check that failed, which ends with what to run. Exit 0 when ready, 4 when not (the verdict is `not ready`). With no settings file it reports on the environment alone. It is free.

`--fix` fetches the tokenizer file when it is missing, which is the only thing `doctor` ever changes. `--offline` skips the key check, so that no socket is opened. `--show-command` prints the `init --yes` command that writes the settings file.

On a tasks file made on your own tools, `doctor` reads the tool file again and reports its summary, each refusal, the file's digest, which knobs the set reaches with what the knob probe found on each, and the newest run on the same file ([own-tools.md](own-tools.md)).

<!-- docs-check: run fixture -->
```bash
poisson-tasks doctor --offline
```
<!-- docs-check: output -->
```
ok  this environment is ready to run tasks.toml
  python     ok      …
  package    ok      …
  tokenizer  ok      …
  config     ok      tasks.toml: depth at 1, 3 and 8, 10 tasks each, against gpt-5-nano-2025-08-07
  key        ok      OPENAI_API_KEY is set (not checked: --offline)
  harness    ok      …
  platform   ok      …
```

<!-- docs-check: run -->
```bash
poisson-tasks doctor --help
```
<!-- docs-check: output -->
```
usage: poisson-tasks doctor [-h] [--config PATH] [--json] [--plain] [--debug]
                            [--fix] [--yes] [--offline] [--show-command]

Says whether this environment can run the settings file, line by line: Python,
the package, the tokenizer file, the settings, the key, the harness and the
platform. Exit 0 when ready, 4 when not, each failing line ending with what to
run. Free.

options:
  -h, --help      show this help message and exit
  --config PATH   the settings file to read, or to write (default:
                  ./tasks.toml)
  --json          print the result as one JSON document on stdout (default:
                  text)
  --plain         the plain style, text only, even on a terminal (default:
                  pretty on a terminal, plain in a pipe, under NO_COLOR or CI,
                  or with --json)
  --debug         on an unexpected failure, print the traceback as well as
                  writing it to the log (default: the log only)
  --fix           fetch the tokenizer file when it is missing, the one thing
                  doctor changes (default: report only)
  --yes           with --fix: fetch without asking
  --offline       skip the key check, so no socket is opened
  --show-command  print the init --yes command that writes this settings file

examples:
  poisson-tasks doctor
  poisson-tasks doctor --fix
  poisson-tasks doctor --offline
  poisson-tasks doctor --show-command
```
