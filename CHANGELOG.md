# Changelog

All notable changes to Poisson Tasks. The package has not been released; everything below is
unreleased and sits at version `0.0.1`.

## Unreleased

### The knob probe's outcome: faults, history and shape ship

- **Three knobs shipped.** The knob probe measured the seven newer knobs on `gpt-5-nano` and
  `Qwen3-8B`. `faults` (bites on Qwen3-8B), `history` (bites on both) and `shape` (bites on
  Qwen3-8B, the four-wide arrangement the harder) shipped: `arms.SHIPPED_KNOBS` is those three,
  and the recipes that measure them are offered (`error-recovery`, `long-sessions`, `planning`,
  `profile`, beside `first-look` and `card`). `tool-choice` and `reading-and-filling` wait on
  knobs that did not ship. `similarity`, `block`, `arguments` and `spread` did not ship; they stay
  in the generator and their arms work as before.
- **Each knob's measured status, in the package.** `poisson_tasks.arms.knob_status()` reads
  `knob_status.json`: each knob's status on each model (bites, does not bite, top easier, cannot
  tell), the base and top arms' strict pass@1, and each contrast's drop and 95% interval. No knob
  is called a non-biter on a model where its base passed below 0.15, since a drop of 0.15 could
  not show there: that reading is "cannot tell" (spread on Qwen3-8B, base 0.008). A top-easier
  reading is "cannot tell" where the top passed above 0.85. `docs/knobs-and-arms.md` has the
  table.
- **Disclosed with the outcome.** Phase 1's no-call check was changed after gpt-5-nano's first
  phase 1 stopped on 1 of 21 base episodes (the model asked for the record id in plain text), to
  the cards' own rule (3 or more of 21 stop); the recorded phase 1 was read again once under it,
  with no episode run again, and passed. gpt-5-nano's run crashed at its start on macOS's
  open-file limit; the limit was raised and the run resumed, and its first arm, void because
  episodes in flight at the crash failed on our side, was run once more, as the pre-registration
  allows for a cause on our side. Qwen3-8B's run reached its two-hour allowance with 14 of 18 arms
  done, stopped cleanly, and was resumed with more time; it used 2.56 hours in all.

### The command

- **The command.** `poisson-tasks` (and `python -m poisson_tasks`) puts the library behind seven
  verbs. `init` asks what to measure, in plain words, and writes one settings file, `tasks.toml`,
  printing the same setup as one command that asks nothing; it fetches the tokenizer file first if
  it is missing. `generate` makes the plan's tasks with no model and no network and writes them
  as files, or shows one task in full. `run` shows the plan, the expected calls and cost and the
  cap, asks, and runs it against the model, stopping at the cap and resuming after Ctrl-C.
  `card` builds a run's card and says what it means and what it does not claim. `verify` judges
  an answer with the task's own verifier. `export` writes the configs verifiers' `eval` runs.
  `doctor` says whether this environment is ready. Every command prints its result first, puts
  problems on stderr as one `error:` line, exits 0, 1, 2, 3, 4 or 130 by one table, and gives
  `--json`.
- **Two looks, one result.** On a terminal the command draws its result with Rich, with arrow-key
  menus in `init`; in a pipe, under `NO_COLOR` or `CI`, with `TERM=dumb`, on a stdout that is not
  UTF-8, or with `--json` or `--plain`, it prints plain text, byte for byte the same facts in the
  same order. Rich and questionary are ordinary dependencies.
- **A plan expected to cost more than its cap is refused before the question**, with a cap that
  would let it finish; `generate`, `export` and `card` refuse to overwrite their files without
  `--force`; a `next:` command carries the `--config` you gave; `doctor` with no settings file
  reports on the environment alone; `export` writes JSON (TOML cannot carry an arm with no
  control arm) and opens no socket.
- **Two refusals reworded.** A key variable written as a shell writes it (`$OPENAI_API_KEY`) is
  told to write the name alone; a knob the library has and the settings file does not offer yet
  is said to be not offered here yet, not "not a knob".
- **Library names added for the command:** `config.INIT_FLAG_ALIASES`,
  `providers.refuse_plain_http_key`, and `poisson_tasks.transcripts` (`read_transcript`,
  `verdict_of`), which reads an attempt's three forms. `cards.published()` no longer needs the
  tokenizer file.

### The run engine's key mask: the key where a provider can put it, and nothing else

- **A fix to traces written with a project key.** The run engine masked any four characters of
  the key wherever they occurred in a trace line. Every OpenAI project key starts with
  `sk-proj-`, and the tasks' item codes hold `-pro`, so earlier runs made with a project key
  could have had nearly every trace line rewritten: a masked number left a line that was no
  longer JSON, and a masked reply, argument or task text failed the replay check or the verdict
  check when the records were read. Any key could have had some lines rewritten, wherever four
  of its characters happened to occur in the run's own text, and a key holding a quote or a
  backslash could break a line's JSON. Runs made without a key, and the published cards, were
  not affected. Run again any run made with a key before this fix whose records you rely on.
- **A key's public prefix is not secret.** The prefix every key of a kind starts with, such as
  `sk-proj-`, `sk-ant-api03-` or `gsk_`, no longer counts as part of the key.
- **Where a provider can put the key, any four of its characters are masked**: in each provider
  error a trace records, in the first error a run reports, and in `run.log`. The prefix stays,
  so a masked key reads `sk-proj-****`.
- **Every other byte of a trace line is written as the run produced it.** Twelve characters of a
  key in a row are the key's, wherever they are: no text a run makes for itself holds that many
  by chance. A trace line that holds that many outside its errors has them masked in the string
  that holds them, and is still one JSON document. No file of a run folder, and neither stream,
  holds twelve characters of the key in a row.
- **The free key check no longer counts the public prefix either.** It shows a provider's short
  value, a refusal's error code or a server's version, only when the value holds no four
  characters of the key in a row. With a project key, a code holding `proj` or a version holding
  `-pro` was dropped from the check's sentence; it is now shown. Four characters of the rest of
  the key still keep a value out.

### Information spread

- **A ninth knob makes tasks: `spread`**, at levels 1, 2 and 4: how many tool answers the entry
  code is split across. The request no longer states the entry code. It names four reads, by
  item, facet and page, the same at every level, and at level P the first P of their answers
  carry the code's parts, in order, each part followed by a full stop and filler; the rest
  answer `none`. The first stage tool says its code is assembled from the reads the request names.
- **Everything else is the base task's**: the block, the system prompt, and the six calls the
  reference makes, the four reads then the two stage calls. Only those four reads, made exactly
  as named, are answered with parts; every other read is the engine's.
- **No control arm**: the request and the calls are the same at every level.
- **A spread run's tool messages are replayed against the engine**, the named reads' answers
  included, when its records are read; a disagreement is `replay_mismatch` and scores nothing.
- **`eval` takes a spread arm, with one note**: no published card covers it. A level outside 1
  to 4, or a control arm, is refused in one line. Every knob now has tasks.
- **`init` and `tasks.toml` do not offer information spread** until its probe has shown it bites.
- **Every task id and the generator hash moved**; no task of the other eight knobs changed. The
  built-in generator is now frozen until the probe.

### Task shape

- **An eighth knob makes tasks: `shape`**, at widths 1, 2 and 4: whether four stage calls form
  one chain or run side by side. `shape:w1` advances one record through four stages; `shape:w2`
  advances the target record and the decoy two stages each; `shape:w4` advances the target
  record one stage in four ledgers. Every width makes four stage calls and a reply, in a block of
  sixteen tools holding exactly the stage tools it needs, so no tool can carry a record past its
  goal.
- **The request lists one line per goal**; nothing else in it moves with the width.
- **A control arm, `shape:w1+len(w4)`**: the one-chain task, with neutral words after the request
  as long as what the four-line request adds.
- **A task with several records to advance is judged on all of them**: every one must reach its
  goal, and a change to any other record is `collateral_mutation`. `shape:w2` has no
  `collateral_mutation` control, because no tool in its block can change a record that is not
  one of its two.
- **Calls may be batched**: an episode that makes independent calls in one turn passes, and the
  card's model calls and tool calls show it.
- **A shape run's tool messages are replayed against the engine** when its records are read; a
  disagreement is `replay_mismatch` and scores nothing.
- **`eval` takes a shape arm, with one note**: no published card covers it. A width other than 1,
  2 or 4 is refused in one line. The one knob whose tasks are not built yet is still refused in
  one line.
- **`init` and `tasks.toml` do not offer task shape** until its probe has shown it bites.
- **Every task id and the generator hash moved**; no task of the other seven knobs changed.

### Argument difficulty

- **A seventh knob makes tasks: `arguments`**, at levels 2, 4, 6 and 8: how many values each
  stage call must carry, copied from the request. Each stage tool lists eight parameters at every
  level, the two the task always needs and six more, of which only the two are required; the
  request states the level less two of the six, and both stage calls must carry exactly those,
  with exactly those values. The task is otherwise the base task.
- **A call that leaves out a stated value, gets one wrong, or adds one the request did not state
  is answered `bad_args`**: nothing changes and the call takes its number, as any refused call
  does. The tool server, the verifier and the replay of a run apply the same check.
- **An empty value in a parameter the request did not state is refused too**: it is a value the
  request did not state, not an absent one.
- **A control arm, `arguments:a2+len(a8)`**: the two-value task, with neutral words after the
  request as long as what the eight-value request adds.
- **An arguments run's tool messages are replayed against the engine** when its records are read;
  a disagreement is `replay_mismatch` and scores nothing.
- **`eval` takes an arguments arm, with one note**: no published card covers it. Levels between 2
  and 8 run too. The two knobs whose tasks are not built yet are still refused in one line.
- **`init` and `tasks.toml` do not offer argument difficulty** until its probe has shown it bites.
- **Every task id and the generator hash moved**; no task of the other six knobs changed.

### Recipes in the settings file

- **Recipes.** `poisson_tasks.arms.RECIPES` holds eight ready-made measurements, each a named set
  of arms with a task count and an attempt count: `first-look`, `tool-choice`, `error-recovery`,
  `long-sessions`, `planning`, `reading-and-filling`, `profile` and `card`. Each is built from the
  knobs' own levels. A recipe is offered once a knob it measures has shipped; today that is
  `first-look` and `card`, and the other six wait for their knobs' probe.
- **`[measure] preset` takes a recipe.** The key keeps its name. It takes each recipe offered, and
  `custom`; a recipe not offered yet is refused in one line naming it and the knobs it waits on, and
  the file's comment lists only what is offered. A recipe sets the tasks per level and the
  attempts; `--tasks-per-level`, `--seeds` and `--attempts` still override them.
- **`--recipe`** is the setting's flag among init's settings. `--measure` still works as its alias,
  for one release.

### Cards for any plan

- **Cards for any plan.** `calibration.card_from_run(folder)` builds the card of a run folder from
  what the run left in it: every level's records, the artifact, the document and its verdict. A
  card is measured under the plan's own design (`Provenance.for_plan`): its seeds, its tasks per
  level, its attempts, its decoding (a field not sent is shown as not sent) and its turn cap. A run
  that did not finish, or whose failed attempts were not run again, gives a partial card that says
  how many attempts it owes and marks those levels incomplete; a level the run never reached is
  listed as not run, never as zero. `card_claims` says what a card means and what it does not
  claim. `comparable` and `render_side_by_side` read a card beside the published ones and refuse
  cards measured differently. `poisson_tasks.cards` lists the published cards by their model's
  short name and recomputes each from its records; `poisson_tasks.outcomes` gives one plain
  sentence per outcome label. A model served by its user is recorded as such, with what its server
  reported.

### Block size

- **A sixth knob makes tasks: `block`**, at levels 8, 16, 32 and 64: how many tools the model
  is offered. The first eight are the same at every level: the two tools the task needs and six
  read tools, in an order drawn for the task, so the right tools sit in the same places. Higher
  levels add the table's other read tools, then read tools under names of their own: each pairs
  one of the table's read verbs with one of its fields, is described in its own words, and
  answers exactly as the table's read of that field. The task is otherwise the base task: the
  same system prompt, the same request and the same two calls to make.
- **A control arm, `block:k8+len(k64)`**: the eight-tool block, with neutral words added to the
  system prompt as long as what the sixty-four-tool block adds, so a drop can be read against
  the same length.
- **A block run's tool messages are replayed against the engine** when its records are read,
  the renamed reads included; a disagreement is `replay_mismatch` and scores nothing.
- **`eval` takes a block arm, with one note**: no published card covers it. Levels between 8
  and 64 run too. The three knobs whose tasks are not built yet are still refused in one line,
  by the generator and by `eval`.
- **A block of more than 258 tools is refused when the arm is made**: the two tools the task
  needs and every read name the table can make.
- **`init` and `tasks.toml` do not offer block size** until its probe has shown it bites.
- **Every task id and the generator hash moved**; no task of the other five knobs changed.

### The run engine: the estimate, the cap, resume and Ctrl-C

- **What a plan will cost, before anything is spent.** `poisson_tasks.runs.estimate` reads the
  published card of the plan's model (model A's card for a model no card measured, or the card
  named) and gives the plan's episodes, its least and most model calls, the calls, tokens and
  dollars expected at the plan's prices, and which card it read. Every mean is computed from the
  card's records; nothing is a typed number.
- **One folder per plan.** A run goes in `runs/<preset>-<model>/`, then `-2`, `-3` for a second
  run of the same plan or a changed one, with no hash in its name. The folder that holds a plan
  is found by the hash inside its `plan.json`, so a renamed folder is still found; `find_run`
  says whether a folder is new, resumed or complete, names the folder a changed plan came after
  and the fields that changed, and only reads.
- **The cap is a bound on what is spent, not an estimate.** The spend and token caps are checked
  before every model call, through the harness's relay in the run's own process, so the final
  spend is at most the cap plus the calls in flight when it was reached. Before an episode starts,
  the measured spend plus a reservation for every episode in flight must leave room; the
  reservation is the largest episode the run has seen, and before any, the card's 95th
  percentile for the arm. The cap holds the folder's total across runs: running again at the same
  cap sends nothing. An episode the cap cuts short is not an instrument failure and is owed
  again; what its calls cost is in the ledger.
- **The ledger**, `spend.jsonl`, has one line per episode that ended: the arm, the seed, the
  attempt, the tokens and the dollars (`null` without a price). It is append only; a torn last
  line, left by a process that died while writing, is dropped when the ledger is opened.
- **Resume loses nothing and runs nothing twice.** A stopped run keeps every finished episode,
  byte for byte, and a resume runs exactly the episodes owed, through the wheel's own resume. A
  run in which some episodes failed is resumed too: the failed ones run again, and the instrument
  tally keeps the failure.
- **Ctrl-C.** The first stops dispatching and gives the episodes in flight ten seconds to finish
  and be recorded; the run then returns with the interrupted verdict and the ledger written. A
  second stops at once. Nothing the run started is left running.
- **Stops.** The provider saying it is out of credit stops the run after the episode that heard
  it. Five episodes in a row failing before any was scored stop it, with the first error's status
  and the provider's own words; a run in which every episode failed is never done. A run that
  makes no model call and finishes no episode within the watchdog's limit (600 seconds) is
  stopped, with whatever it started, quoting the last lines of `run.log`.
- **`run.log`** holds the run's own progress, the harness's records of warning level and above,
  and any traceback. The key never shows: every run of four or more characters of it is masked
  in the log, in the trace lines and in the first error a run reports.
- **The machine.** The harness runs with `PIP_REQUIRE_VIRTUALENV=1`, so its bootstrap takes uv's
  installer every time, and `UV_NO_MODIFY_PATH=1`, so that installer edits no shell start-up
  file. Besides the run folder, a run writes only what the harness, uv and uv's installer write
  for themselves: `~/.cache/verifiers`, `~/.local/bin/uv` and `uvx`, `~/.cache/uv`, uv's receipt
  in `~/.config/uv`, one `/tmp/vf-port-*` file per episode and one empty uv lock file in the
  temporary folder.
- **`run` and `export` are one path.** `runs.verifiers_config` is the eval config the run uses for
  an arm, as a mapping `eval @` reads: the same taskset, arm, seeds, attempts, model, endpoint,
  key variable's name, decoding and turn cap, with `push` off. A decoding field declared
  `"not sent"` is in no request.
- **`calibration.run_cell`** runs one arm's cell for any design (the seeds, attempts and decoding
  given) through the same runner as `run_arm`, which is unchanged: `run_arm` is `run_cell` with
  the published design.
- **Until the cards ship inside the package**, the estimate reads their records from the
  checkout's `calibration/` folder; a wheel installed on its own refuses the estimate in one line
  that says so, and a run from it reserves nothing before its first episode and says so in
  `run.log`.

### History in tokens

- **A fifth knob makes tasks: `history`**, at levels 0, 300, 600, 1200 and 2400 reference tokens.
  At level T the conversation holds earlier tool work before the model's first move: read calls
  on tools in the block, each answered by the tool, whose tokens (tool name, arguments and answer,
  as the reference tokenizer counts them) total exactly T. The task is otherwise the base task:
  the same system prompt, the same sixteen tools, the same request and the same two calls to make.
  Level 0 is the base task under history's name.
- **The history is real tool work.** Every seeded call is a read the tool server would have
  answered the same way, and none changes a record, so the model starts from the state the task
  describes; the tool server numbers its own answers from where the history leaves off.
- **A history run's tool messages are replayed against the engine** when its records are read,
  from the first call the model made; a disagreement is `replay_mismatch` and scores nothing.
- **`eval` takes a history arm, with one note**: no published card covers it. Levels between the
  card's, up to 2400, run too. The four knobs whose tasks are not built yet are still refused in
  one line, by the generator and by `eval`.
- **`init` and `tasks.toml` do not offer history** until its probe has shown it bites.
- **Every task id and the generator hash moved**; no task of the other four knobs changed.

### Your own tools: the readers

- **Tasks reads a tool file you already have into one normal form**: an OpenAI tools list
  (Chat Completions or Responses functions, bare or under a `tools` key), an MCP `tools/list`
  result (bare, in its JSON-RPC envelope, or a list of pages), or an OpenAPI 3.0 or 3.1
  document in JSON or YAML. The format is told from the file's shape, or named. Every tool
  becomes a name, a description, an argument schema with every `$ref` inlined, an output
  schema where the format has one, and whether it reads or writes. An OpenAPI operation's
  path, query and header parameters and its JSON body merge into one argument object.
- **What it cannot handle, it refuses in one line each, and reads the rest.** A tool is
  refused when its name is empty or repeats another's once renamed (characters outside
  letters, digits, `_` and `-` become `_`; a name over 64 characters is cut and given eight
  hex digits of its digest; the original is kept as the tool's title), when its argument
  schema is not an object or uses what a simulator cannot check exactly (`anyOf`, `oneOf`,
  `allOf`, `not`, `patternProperties`, a schema-valued `additionalProperties`, a `$ref`
  cycle, nesting deeper than three levels), when it takes a file, a binary string or a
  stream, or when an OpenAPI parameter and a body field would merge under one name. A whole
  file is refused when it matches none of the three shapes, when fewer than 2 or more than
  256 usable tools remain, or when no tool takes an argument a task could check exactly.
- **Read or write comes from the file where it says so**: MCP's `readOnlyHint` and OpenAPI's
  HTTP methods. OpenAI tools do not say, and count as writes until the settings say
  otherwise.
- **A summary and a digest.** Reading gives one line with how many tools read, write and are
  not known, then each refusal, the SHA-256 of the file's bytes, and every renamed tool
  beside its original name.
- **A user's MCP server can be listed once, with their consent**: Tasks starts it, asks for
  its tool list page by page, calls no tool, stops it, and keeps the listing as canonical
  JSON. A program that is not an MCP server, or one that never answers, is refused in one
  line.
- **Nothing calls your endpoints or your tools.** No task, verdict, card or `init` question
  is built on these readers yet; that is the second half.
- **PyYAML is a declared dependency**, for OpenAPI documents written as YAML.

### Faulty tools

- **A fourth knob makes tasks: `faults`**, at levels 0, 1, 2 and 4. At level F the first
  ceil(F/2) calls to the task's first stage tool and the first floor(F/2) calls to its second
  answer `unavailable`: nothing changed, and the same call works when it is made again. The task
  is otherwise the base task, and its system prompt says so in one sentence at every level,
  level 0 included, so the knob does not also test whether a model guesses that.
- **A failure is counted per tool, over the calls that reach the tool server.** A call the
  harness answers itself (arguments that are not a JSON object, or a tool the block does not
  show) uses up no planned failure. The tool server and the verifier apply the plan through one
  function, so a verdict replays exactly what the model was told.
- **A control arm, `faults:f0+len(f4)`,** puts earlier tool work before the first move, three
  read pairs as long as level 4's four failed calls, so a drop can be read against length alone.
- **A record says whether the episode gave up after a fault**: `gave_up_after_fault`, true when a
  tool answered `unavailable` and was never called again, and left out on an arm that plans no
  failure. A faults cell counts them; nothing is gated on it.
- **A faults run's tool messages are replayed against the engine** when its records are read; a
  disagreement is `replay_mismatch` and scores nothing.
- **`eval` takes a faults arm, with one note**: no published card covers it. The five knobs whose
  tasks are not built yet are still refused in one line, by the generator and by `eval`.
- **`init` and `tasks.toml` do not offer faults** until its probe has shown it bites.
- **Every task id and the generator hash moved**; no task of the other three knobs changed.

### Tool similarity

- **A third knob makes tasks: `similarity`**, at levels 0, 1, 2 and 3. Every ledger has a
  four-digit number, carried in its tools' names and descriptions, and the request names the
  target ledger by its number. The block is the base task's with twelve of its reads swapped
  for lookalikes: the first two stage tools of six other ledgers, each named by its own number.
  The level is how many of the four digits each lookalike ledger's number shares, in place,
  with the target's; at level 3 the right tool sits among six one digit apart. The block's
  length is held exactly equal across the levels, so the knob has no control arm.
- **The verdict is strict, with leaky beside it.** A lookalike is another ledger's real tool,
  and the target record exists in every ledger, so a call to a lookalike succeeds on the wrong
  ledger: `collateral_mutation`, which strict fails and leaky can pass. A call to a tool name
  the block does not show, a hidden engine name included, changes nothing.
- **The tool server shows the numbered names and serves them.** The names, descriptions and
  schemas a model sees are the task's byte for byte, and a call by a shown name reaches the
  engine under the tool it stands for. When a run's records are read, a similarity episode's
  tool messages are replayed against the engine; a disagreement is `replay_mismatch` and
  scores nothing.
- **`eval` takes a similarity arm, with one note**: no published card covers it. Its help
  describes the knob. The six knobs whose tasks are not built yet are still refused in one
  line, by the generator and by `eval`.
- **`init` and `tasks.toml` do not offer similarity** until its probe has shown it bites.
- **Every task id and the generator hash moved**; no task of the two card knobs changed.

### The knobs' shared base

- **Every task id moved, and no task did.** The generator version a user gets is now `"1"`,
  and the generator hash covers the three modules that shape a task (`tasks.py`, `surface.py`
  and `knobs.py`). Every task the two published cards measured regenerates with the same
  prompt, tools, goal and reference solution under a new id.
- **Both published cards say they are stale.** They were measured at generator 0. They still
  recompute from their records and render every table.
- **Seven more knobs are named**: `similarity`, `faults`, `history`, `block`, `arguments`,
  `shape` and `spread`, each with its levels, its arm ids and its turn budget. The generator
  makes no tasks for them yet and says so in one line.
- **The pin ledger has thirty rows.** Seventeen are the new knobs'. Every row but the two that
  need a run is measured on every task.
- **A call to a tool the block does not show changes nothing when an episode is verified**, as
  it changes nothing when the episode runs.
- **`eval --help` calls the distractor dial retired**, and its example arm is at generator
  version `"1"`.

### Cost and time on every card

- **Every card shows what each level cost, beside its pass rates.** Every level table and
  the control-arm table gain three columns: median model calls, median tokens and median
  episode seconds.
- **The cost section is three tables**: calls and tokens per episode (means, medians, the
  90th-percentile tokens, and tokens per strict pass); time per episode (the median and 90th
  percentile of episode, model and harness seconds, and the median setup seconds); and the
  token totals and dollars that were already there, unchanged.
- **A record carries its episode's time and the size of its first request**, read from the
  trace by `records_from_run`: `episode_seconds`, `model_seconds`, `harness_seconds`,
  `setup_seconds` and `first_request_prompt_tokens`. Each is optional and left out of the
  written line when it was not recorded, so an `episodes.jsonl` written before these fields
  existed reads and writes back unchanged.
- **A figure that was not recorded is shown as *not recorded*, never as zero.** A phase that
  never ended, or a zero in an episode that made no model call, is missing, and a cell's
  time figures are over the episodes that kept time.
- **Time is printed and never compared.** It belongs to the serving and its load as much as
  to the task. `Provenance` gains an optional `concurrency`, how many episodes ran at once
  (`Provenance.for_run(..., concurrency=...)`); the card prints it wherever it prints seconds,
  and the combined page says it does not compare one card's time with another's. No
  comparison, ordering or verdict reads a time figure, and two cards need not share a
  concurrency to share a page.
- **Both committed cards were rebuilt from their records**, with no new model calls and every
  earlier figure unchanged. Each cell of `artifact.json` gains fourteen keys. Neither run
  kept time or its concurrency, so both cards read *not recorded* for them; the first cards
  with time will come from the next runs.

### Depth read on reaching the goal, one page for every card, and plain words

- **Depth is read on reaching the goal, with stopping at the goal shown beside it.** Every
  depth level offers the whole stage ladder, so below the top level the strict rate also
  asks the model to stop at the goal, and the two calibrated models do not fail these the
  same way. So:
  - every cell now carries its overshoot share and an interval on leaky pass@1;
  - depth's adjacent levels are also compared on leaky pass@1;
  - the card reads depth on that comparison, with the overshoot column beside it.

  Strict stays computed, published and first in every table. Both committed cards were
  rebuilt from their records, with no new model calls and every earlier figure unchanged.
  What it shows:
  - on reaching the goal, depth does not order difficulty for either model: saturated
    everywhere for Qwen3-8B, and for gpt-5-nano only d5 against d8 is distinguishable, with
    d8 higher (its fall from d2 to d3 starts at a saturated level, so it is not called);
  - what depth changes for both models is stopping at the goal.
- **`docs/calibration.md`**, one page for every calibrated model, rendered from the cards:
  where their difficulty orderings agree, read from each card's own verdicts, then each card
  in full. `examples/calibration_card.py --page` prints it. Of 12 adjacent pairs of levels,
  the two models agree on none and disagree on one. Cards measured differently refuse to
  share a page.
- **The distractor dial is experimental.** It does not make tasks harder for either
  calibrated model, so it is not a difficulty setting. `eval --help` says so beside the arm
  option.
- **`verify` accepts a bundle written before a card gained a figure,** checking every figure
  it carries. A missing cell or a changed number is still refused.
- **Plain words.** The card, the calibration module's and the Colab driver's messages and
  help, the notebook, the engine, knobs and adapter modules, the tests' comments and
  docstrings, and `gap-log.md` (one recorded exception to its append-only rule) no longer
  cite internal decision ids, specification sections, private notes or people.
- `LICENSE` reads "Copyright (c) 2026 Taylor Kolasinski / Poisson Labs". `outputs/`, where
  `eval` writes its runs, is ignored.

### Model B's card: Qwen3-8B

- **The second calibration card is in:** `Qwen/Qwen3-8B` at `b968826d`, thinking off, served
  with vLLM 0.29.0 on a Colab L4 (FP8, a 16,384-token context, vLLM's own sampler), each
  episode capped at 32 model calls.
  - 4,200 episodes, all scored, no instrument failure; it published.
  - Records, artifact and instrument tally are in `calibration/qwen3-8b-b968826d/`.
  - `examples/calibration_card.py` now rebuilds any committed card under the provenance its run
    recorded. A test holds both cards to recomputing byte for byte.
- **What it shows:**
  - **Depth runs the opposite way to `gpt-5-nano`:** strict pass@1 rises from 0.000 at d1 to
    0.997 at d8. Qwen reaches the goal at every level (leaky 0.97 or more) but, low on the
    ladder, carries the record past it.
  - **The distractor dial is saturated at every level.**
  - **Seeded history** is what lowers Qwen's leaky rate, to 0.77 and 0.73.
- **Getting it to run took four fixes on Colab, each test-first:**
  - vLLM's FlashInfer sampler could not build its kernel there (no `ninja`), so the pin turns it
    off.
  - Colab's `UV_SYSTEM_PYTHON` broke the harness's setup, so the driver drops it.
  - Long seeded histories outgrew 8,192 tokens, so the context is now 16,384.
  - Qwen looped, so every episode is now capped at 32 model calls.
  - Failures now print the engine's own error and the first episode error. The notebook creates
    its Drive folder.

### An episode ends after 32 model calls

- **The taskset now pins a turn limit**, `agent.max_turns = 32`, beside the measured harness,
  so the documented `eval` command and the calibration run behave the same.
  `--env.agent.max-turns N` overrides it.
- **Why:** verifiers sets no turn limit by default. On model B's second calibration run,
  Qwen3-8B looped in the two long-history control arms: 20 episodes in each made 107 to 112
  model calls on tasks that need one or two. They ended only when the 16,384-token context
  filled, which reads as a setup failure, and the card refused to publish.
- **The number:** four times the deepest task's minimum, eight calls at `depth:d8`. Ordinary
  episodes of both calibrated models end within 18 calls. In the three arms where Qwen
  looped, any cap from 24 to 50 changes 1 episode in 900. An episode that reaches the cap
  is scored `turn_limit`, the model's own failure.
- **The card prints the cap.** Model A's run had none. Its longest episode was 18 calls, so
  its card is what it would be under the cap, and its committed data recomputes byte for
  byte.
- **Added after the fact, and said so:** the limit was added after a run showed the looping.
  The refused runs are kept as evidence.

### Calibration: what each difficulty level is worth

- **`poisson_tasks.calibration`**, a module that measures what each level of `depth` and
  `distractor` is worth to one named model. Per level it computes strict pass@1 (the
  headline) with leaky pass@1 beside it, pass@k by the unbiased estimator for every
  `k <= n`, a 95% interval from a bootstrap that resamples tasks, and the cost each episode
  burned from the provider's own token counts. Neighbouring levels are compared pairwise over
  shared seeds and called distinguishable only when the paired interval excludes zero and the
  difference is at least 0.15. Levels at or below 0.05 or at or above 0.95 are marked
  saturated and left out of every comparison. The design is fixed in code: 60 seeds from the
  eval split, 5 attempts per task, and a declared, non-deterministic decoding.
- **A card, and the refusals that keep it honest.** `build_artifact` computes every figure
  from the per-episode records under a provenance block; `render_document` and
  `render_readme_lines` render them and are never typed by hand. A card refuses to build
  when a cell holds two models, when its instrument-failure rate is above 0.02, when a locally
  served model is missing its serving stack, or when more than 10% of a cell's scored
  episodes made no tool call.
- **A runner that stops cleanly and resumes.** `run_arm` runs one arm through the verifiers
  `eval` body and checks, before each episode, the token budget, the wall-clock limit and
  whether the provider has reported the account out of credit. Instrument failures are
  tallied as they happen, in a file the resume does not rewrite. An interrupted run resumes
  with the same tasks, each with its full number of attempts, none run twice and none skipped.
- **The token limit goes out as `max_completion_tokens`.** OpenAI's reasoning models refuse
  `max_tokens` with an HTTP 400, and vLLM's chat endpoint accepts either.
- **The prompt quotes the record id and the entry code.** Model A's first card had 72.5% of
  its episodes end on a first reply asking for those two values and calling no tool. This
  changes `tasks.py`, so the generator hash, and with it every `task_id`, moved.
- **Two columns and a gate for that failure.** Every cell reports the share of episodes with
  no tool call and the share that stopped short of the task's minimum, and the no-call share
  refuses above 0.10. Phase 1 of a run is a plumbing gate: every episode must make a tool
  call and at least half must reach their minimum.
- **Depth ordering shows leaky beside strict.** Every depth level offers the whole stage
  ladder, so strict below the top level also tests stopping at the goal, which the top level
  cannot.
- **The artifact's call counts are named for what they count**: `tool_calls`, `model_calls`
  and `model_calls_median`. An `artifact.json` written before this change uses the older
  names.
- **Model A's card**: `gpt-5-nano-2025-08-07`, 4,200 episodes, all scored, about $2.52. Its
  records and artifact are in `calibration/gpt-5-nano-2025-08-07/`, and
  `examples/calibration_card.py` recomputes the card from them. Read it with
  `docs/calibration-guide.md`.
- **Model B, prepared**: `poisson_tasks.calibration_run` and
  `notebooks/calibration_model_b.ipynb` serve `Qwen3-8B` at a pinned revision with vLLM
  0.29.0 on a Colab L4 and run the same card, checkpointing to Google Drive so a dropped
  runtime resumes. Not run yet.

### Also since the first public-preparation pass

- **The verifiers export** (`poisson_tasks.export`): a generated task as a verifiers v1
  taskset, scored by the generator's own verifier, with its tool block served over MCP.
- **The standalone model path**: the package is the verifiers taskset id `poisson-tasks`,
  and `eval` runs it with the `null` harness in a local subprocess with no flag.
- **Vocabulary v2**: the record-id word lists are drawn disjoint from every tool name.
- **The rename**: `task-generator` / `task_generator` became `poisson-tasks` /
  `poisson_tasks`. Hash domain separators keep the old spelling, because their bytes are
  hash input.
