# The commands

`poisson-tasks` is one command with seven verbs: `init`, `generate`, `run`, `card`, `verify`, `export` and `doctor`. `python -m poisson_tasks` is the same command. This page gives each verb's help as it prints, and what the help does not say: what the verb writes, what it refuses, and how it ends.

Every verb takes `--config PATH` (the settings file; `tasks.toml` in the current folder by default), `--json`, `--plain` and `--debug`. Options may come before or after the verb, and an abbreviated option is refused. The settings file is described in [config.md](config.md).

## How a command ends

The first line a verb prints on standard output is a verdict line: a word, two spaces and a sentence (`ok  card for gpt-5-nano-2025-08-07: ...`). Detail follows, and the last line, when there is an obvious next step, is `next: <the command>`. A problem is one line on standard error that starts with `error:` and says what to do; an unexpected failure prints one line that names a log file, and the traceback goes to that file (`--debug` prints it too).

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

Every result is drawn one of two ways. The pretty rendering uses colour and a live display, and runs only when both standard output and standard error are terminals, `NO_COLOR` is unset or empty, `CI` is unset, `TERM` is not `dumb`, standard output is UTF-8, and neither `--json` nor `--plain` was given. Everywhere else, and always when you ask with `--plain`, the plain rendering runs: text only, the same facts in the same order. This page shows the plain rendering. [The look](cli-look.md) says more.

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

## init

Asks which model to test, which environment variable holds its key (it records the variable's name and never the key), what to measure and when to stop, writes `tasks.toml`, and prints the same setup as one command you can run again with no questions. It spends nothing. If the tokenizer file is missing it asks to fetch it first (3.6 MB, once, into the installed package). It can check your key with one free request, after asking.

The providers are `openai`, `anthropic` (through its OpenAI-compatible endpoint), `ollama`, `vllm` and `openai-compatible` (any endpoint that speaks the OpenAI chat API). Measuring tasks on your own tools, an OpenAI tools file, an MCP tool list or an OpenAPI document, is one of the choices of question 6; [own-tools.md](own-tools.md) describes it.

`init` refuses to replace a `tasks.toml` that is already there unless you pass `--force`, and refuses to ask questions when standard input is not a terminal (pass `--yes` and the answers as options). Ctrl-C at any question writes nothing.

A setup with no questions, for a script or a second machine:

<!-- docs-check: run -->
```bash
poisson-tasks init --yes --no-check-key --provider openai --recipe first-look --tasks-per-level 10
```
<!-- docs-check: output -->
```
ok  wrote tasks.toml: depth at 1, 3 and 8, 10 tasks each, against gpt-5-nano-2025-08-07
  tokenizer  …
  key        …
  the same setup, without questions:
    poisson-tasks init --yes --provider openai --model gpt-5-nano-2025-08-07 \
      --base-url https://api.openai.com/v1 --api-key-env OPENAI_API_KEY \
      --price 0.05,0.005,0.4 --price-read-on 2026-09-25 --recipe first-look \
      --tasks-per-level 10 --attempts 1 --temperature 1.0 --top-p 1.0 \
      --reasoning-effort low --max-tokens 2048 --spend-cap 1.0 \
      --max-model-calls 32 --concurrency 8 --runs-dir runs --tasks-dir tasks
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

A guided setup. It asks which model to test, which environment variable holds
its key (it records the variable's name, never the key), what to measure and
when to stop, then writes tasks.toml and prints the same setup as one command.
It fetches the tokenizer file first if it is missing. It spends nothing.

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
  --provider NAME       question 1: openai, anthropic, ollama, vllm or openai-
                        compatible (default: openai)
  --model TEXT          question 2: the model's name, as the provider spells
                        it (default: the preset's; no default for openai-
                        compatible)
  --base-url URL        question 3: the endpoint; required for openai-
                        compatible, else the preset's (default: the preset's;
                        no default for openai-compatible)
  --api-key-env TEXT    question 4: the variable that holds the key; "" for
                        none (default: the preset's; no default for openai-
                        compatible)
  --allow-plain-http-key
                        send the key over plain http to another machine
  --price I,C,O         question 5: dollars per million tokens, input, cached
                        input, output (default: the published price for
                        gpt-5-nano-2025-08-07, else none)
  --price-read-on DATE  the date the prices were read, as 2026-09-25 (default:
                        none)
  --no-price            no price: the cap is then in tokens
  --recipe NAME         question 6: first-look, card or custom (default:
                        first-look)
  --measure NAME        an alias of --recipe, kept for one release
  --knob NAME           with --recipe custom: depth or distractor (default:
                        depth)
  --levels L,L,…        with --recipe custom: the levels, comma-separated
                        (default: every level of the knob)
  --controls            with --recipe custom: add the control arms
  --no-controls         with --recipe custom: no control arms
  --strictness NAME     with --recipe custom: strict or leaky (default:
                        strict)
  --tasks-per-level N   question 7: how many tasks per level (default: 10)
  --seeds L,L,…         the tasks' seeds, comma-separated, instead of --tasks-
                        per-level (default: none)
  --attempts N          question 8: how many attempts at each task (default:
                        1)
  --generator-version TEXT
                        the label that enters every task id (default: none)
  --temperature X       the decoding's temperature (default: 1.0)
  --top-p X             the decoding's top-p, or "not sent" (default: 1.0)
  --reasoning-effort TEXT
                        the decoding's reasoning effort, or "not sent"
                        (default: low)
  --max-tokens N        the decoding's token limit per reply, or "not sent"
                        (default: 2048)
  --spend-cap X         question 9: stop the run once it has spent this many
                        dollars (default: the larger of $1.00 and twice the
                        estimate)
  --token-cap N         stop the run once it has used this many tokens
                        (default: 2,000,000 without a price)
  --max-model-calls N   the model calls allowed per episode (default: 32)
  --concurrency N       how many episodes run at once (default: 8)
  --runs-dir TEXT       where runs are kept (default: runs)
  --tasks-dir TEXT      where generate writes its files (default: tasks)
  --own-file PATH       question 6, your own tools: the tool file, an OpenAI
                        tools file, an MCP tool list or an OpenAPI document,
                        beside tasks.toml (default: none)
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

With `--show` it prints one task the way a model would see it: the system prompt and the request, the tools and which of them the task needs, the reference solution with what the domain returns for each call, and the verdict on every wrong answer the task ships with. `--task N` picks the task by its place in the plan, counting from 1; `--seed S` picks one by a seed you chose.

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
| no model call and no finished episode in 600 seconds | `stopped  no model call and no finished episode within 600 s: ...` | 3 |
| Ctrl-C | `stopped  interrupted: ... kept`, then `next: poisson-tasks run` | 130 |

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

A card from a run that was stopped is built from what ran, and every level that did not finish is marked. A level where more than 10% of attempts made no tool call is not published, and neither is its card: it would measure whether the model starts, not how hard the level is. That refusal exits 1.

`--published` rebuilds the cards that ship with the package from their own records, checks each against its stored artifact byte for byte, and says whether it is current for this install. It is free. `--check PATH` does the same for a card folder or a calibration bundle `.zip`; exit 4 means a difference. `--page` writes the one page for every published card. `--compare published` puts a run's card beside the published ones, or says in one line why it cannot. In this release it cannot for a card on the built-in tasks, because the published cards were measured on an earlier build of the generator: it refuses with `the generators differ` (exit 1), and `card` does not end by suggesting it. A card on your own tools is put beside the published card of its model. `card` ends with the command when a published card measured your model, and leaves it out for any other model, because it would refuse in one line.

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
  --compare WHAT      put this run's card beside the published ones: --compare
                      published
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
```

## verify

Runs the verifier a task was generated with, with no model. With `--self-check` it checks the task's own answers: the reference solution passes under both strictnesses, and each wrong answer the task ships with earns the outcome it is named for. With `--transcript FILE` it judges your own agent's attempt at the task, in one of three forms (OpenAI chat messages, one row of a verifiers `traces.jsonl`, or this tool's own turns). A task is named by its arm and its place in the plan (`--arm depth:d3 --task 7`), or by a seed you chose, or by a file `generate` wrote (`--tasks FILE`, with `--task N`).

The verdict word is the outcome itself (`passed`, `overshoot`, `wrong_state`, ...). `verify` exits 0 when the verdict is `passed` and 4 otherwise, so a script can gate on it.

In this release `verify` refuses a tasks file made on your own tools, in one line, and exits 1: `error: <file> holds tasks on your own tools, which verify does not judge on its own yet: a run's card judges every episode on them, by replay`. A run on your own tools is judged by that replay, and its card reports it; judging a single own-tools task with `verify` comes in a later release.

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

Writes the plan's tasks as configs another runner reads. There is one target now, `--to verifiers`: one eval config for every arm, `eval-<arm>.json`, holding the taskset, the arm, the seeds, the model, the endpoint, the name of the key's variable (never the key) and the decoding, with `push` off. It prints, for each file, the command that runs it, with verifiers' `eval` by its absolute path in this environment, so that the shell's own `eval` builtin cannot take its place ([verifiers-export.md](verifiers-export.md) says why that matters). `export` reads no key and opens no socket, and refuses to replace files that are already there unless you pass `--force`.

Run that way, `eval` runs what `run` runs for the arm, without what `run` adds: the plan, the spend cap, the tally of failures that are not the model's, the stop when the account is out of credit, the stop for a streak of failures, and the watchdog. It also exits 0 when every episode errored.

<!-- docs-check: run -->
```bash
poisson-tasks export --to verifiers | head -n 4
```
<!-- docs-check: output -->
```
ok  wrote 3 verifiers configs, one per arm: depth at 1, 3 and 8, 10 tasks each
  note  run that way, eval leaves out what run adds (the plan, the spend cap, the instrument tally, the out-of-credit stop, the failure-streak stop and the watchdog), and it exits 0 when every episode errored

run each with
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

Says whether this environment can run the settings file, line by line: Python, the package, the tokenizer file, the settings, the key, the harness and the platform. Each line carries its own status word, `ok` or `not ok`, and each failing line ends with what to run. Exit 0 when ready, 4 when not (the verdict is `not ready`). With no settings file it reports on the environment alone. It is free.

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
