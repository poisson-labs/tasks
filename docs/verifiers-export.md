# Running a generated task under verifiers

`poisson_tasks.export` packages a generated task as a [verifiers](https://github.com/willccbb/verifiers)
v1 taskset: the task data, the task with its reward, the tool server, and a finite taskset
over a declared list of seeds. Everything on this page is against `verifiers==0.3.1`, which
is the version the package pins.

**The taskset id is `poisson-tasks`.** It is the distribution's name, and verifiers resolves
it to the package itself, which exports the taskset and its environment. `import
poisson_tasks` does not import `verifiers`: the two are exported lazily, and only `eval` (or
whoever asks for them by name) pays for the import.

## Running it against a model

One command. Set `MODEL`, `MODEL_BASE_URL` and `MODEL_API_KEY` for an OpenAI-compatible
endpoint serving a model that calls tools, then:

<!-- docs-check: run fixture env="MODEL,MODEL_BASE_URL,MODEL_API_KEY" -->
```bash
uv run eval poisson-tasks --model "$MODEL" --client.base-url "$MODEL_BASE_URL" --client.api-key-var MODEL_API_KEY --env.taskset.arm '{"knob": "depth", "level": 3, "control": null, "strictness": "strict", "split": "eval", "generator_version": "1"}' --env.taskset.seeds 404 55 2121 --no-push
```

Give the arm by its id, as in `--env.taskset.arm depth:d3`, or, for a leaky arm, as its six
fields in one JSON object, as above with `"strictness": "leaky"`. An arm given by id is always
strict, on the eval split, at the generator version the package uses; a leaky arm is given as
its six fields. The dotted form, `--env.taskset.arm.<field>`, is not a way to give an arm: its
values reach the taskset as text and are refused (`level "3" is not a whole number`), and beside
an id `eval`'s own parser drops them before the taskset sees them, so the arm stays strict. The
seeds are a list. `generator_version` is the label that goes into every task's id; `"1"` is the
one the package uses, and [python.md](python.md) says what the label is. With no harness named,
the run uses the measured harness (below) in a local subprocess; both are this taskset's own
defaults and both show in the run's saved config.

That command, run against OpenAI on 2026-09-22 with `MODEL=gpt-5-nano` on a machine with no
environment prepared, printed this:

```
Using CPython 3.12.13
Creating virtual environment at: .venv
   Building poisson-tasks @ file:///.../task-generator
      Built poisson-tasks @ file:///.../task-generator
Installed 103 packages in 498ms
env       poisson-tasks  ·  null harness  ·  subprocess runtime
model     gpt-5-nano  via https://api.openai.com/v1
taskset   arm={knob=depth,level=3,control=None,strictness=strict,split=eval,gen…
          ·  seeds=[404,55,2121]  ·  task.arm_id=depth:d3
limits    ≤128 episodes     ·  no turn cap         ·  no token cap
output    outputs/poisson-tasks--gpt-5-nano--null--539ec6b0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 3/3 · 48s · reward 0.67 · err 0.00
rewards   strict 0.67
metrics   leaky_pass 0.67  ·  mutation_count 2.00  ·  sampled_calls 2.33  ·
          turns 3.33
usage     2.2K/10.6K tokens (0 cached, 10.0K reasoning)
time      boot 0.0s  ·  setup 5s  ·  agent 33s (model 32s + harness 0.9s)  ·
          finalize 0.0s  ·  scoring 0.0s
[success ] task idx=None agent=agent · cffdef76 · subproces… reward=1.00 · 45s
[success ] task idx=None agent=agent · 14962068 · subproces… reward=0.00 · 21s
[success ] task idx=None agent=agent · a40932b0 · subproces… reward=1.00 · 45s
```

Ten model calls, 8,363 prompt and 10,558 completion tokens (9,984 of them reasoning), about
half a cent. **`reward 0.67` is the model's score, not a fault in the run**: all three
episodes completed (`err 0.00`, every rollout `agent_completed`), and one of the three ended
without the model calling a single tool, which scores 0 under `strict` as it should. Two of
three at `depth:d3` is a measurement of `gpt-5-nano`, and what a level is worth is the
calibration card's subject, not this page's: see [Reading a card](reading-a-card.md).

Paths are elided above; nothing else is. That run predates the turn limit described below,
which is why its limits line reads "no turn cap"; a run today shows the 32-call cap there.

**If the run goes quiet, it has not hung on the model.** At 0.3.1 a run's env server is a
child process, and if it dies during startup -- a config it refuses, a missing dependency --
the parent keeps waiting: no top-level error, no non-zero exit, and `traces.jsonl` stays 0
bytes. Measured 2026-09-22: ~15 minutes to a manual interrupt, with nothing printed. A run
that has produced no trace after a minute or two is worth interrupting; the reason is in the
run's own `logs/attempt_1/eval.log`, under the env server's traceback. This is verifiers'
behaviour, not this taskset's, and it is reported upstream.

## With the `poisson-tasks` command

You do not have to type that command. `poisson-tasks export --to verifiers` writes one eval config for every arm of your settings file, `eval-<arm>.json`, each the config `poisson-tasks run` uses for that arm, and prints the command that runs it:

<!-- docs-check: run -->
```bash
poisson-tasks init --yes --no-check-key --provider openai --recipe first-look > /dev/null
```
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

Each printed command is `eval` by its absolute path in the environment `poisson-tasks` is installed in, such as `/home/you/.venvs/tasks/bin/eval @ export/eval-depth-d1.json`.

Beside the configs it writes `produced_by.json`: what produces the plan's tasks, the package and verifiers versions, the generator's hash, the plan's hash and its seeds (on your own tools also the own-tools generator's hash and your tool file's contract hash), the same record a run writes before its first request. The configs carry none of it, so verifiers reads them as before.

**`eval` is also a shell builtin.** In bash and zsh the bare word `eval` runs the shell's own `eval`, which takes its arguments for a command and runs that, so `eval poisson-tasks ...` does not reach verifiers at all. That is why the command above is `uv run eval ...`, and why the commands `export` prints name the program by its path.

<!-- docs-check: run -->
```bash
type eval
```
<!-- docs-check: output -->
```
eval is a shell builtin
```

Run that way, `eval` runs the arm but leaves out what `run` adds: the plan and its estimate, the spend cap, the tally of failures that are not the model's, the stop when the account is out of credit, the stop for a streak of failures, and the watchdog. It also exits 0 when every episode errored. For a run with a cap on what it can spend, use `poisson-tasks run`.

For tasks on your own tools, the config names the taskset `poisson-tasks-own` (a second top-level module of the same package, because verifiers finds a taskset by a top-level module) and carries your tool set whole.

## The ten names

The shortest thing that works in Python:

<!-- docs-check: run -->
```python
import dataclasses
from poisson_tasks.knobs import ArmSpec
from poisson_tasks.export import ExportTaskset, ExportTasksetConfig, task_from_bundle

arm = ArmSpec(knob="depth", level=3, control=None, strictness="strict",
              split="eval", generator_version="1")
taskset = ExportTaskset(ExportTasksetConfig(arm=dataclasses.asdict(arm), seeds=[404, 55, 2121]))
for task in taskset.load():
    print(task.key[:12], task.data.seq_start, len(task.data.tools))
```
<!-- docs-check: output -->
```
… 1 16
… 1 16
… 1 16
```

`load()` yields one task per declared seed, in the order you declared them, and nothing in
the module shuffles. A seed that appears twice is refused: two tasks would carry one key.

| name | what it is |
|---|---|
| `ExportTasksetConfig(arm=..., seeds=[...])` | the arm as a mapping, plus the seed list |
| `ExportTaskConfig` | the arm's `strictness` and `arm_id`, derived from the arm |
| `ExportTaskData` | the whole bundle, as the wire carries it |
| `ExportTask` | `key == task_id`; one reward, four metrics; `validate()` checks that the reference solution passes |
| `ExportTaskset` | `INFINITE = False`; one task per declared seed |
| `DomainToolsetConfig`, `DomainToolset` | the task's tool block, served over MCP |
| `task_from_bundle(bundle)` | one `generate(arm, seed)` bundle as one task |
| `bundle_from_data(task.data)` | the bundle back, equal to the one generated |
| `MEASURED_HARNESS` | `"null"` |

`bundle_from_data(task_from_bundle(b).data) == b`, and it stays equal after the data has
crossed the JSON wire a launched tool server hands it over. That round trip is how a
finished trace gives back the task it ran.

## The signals

One reward and four metrics, all scored offline -- none of them takes a `runtime`, so a
stored trace can be rescored with no environment at all.

* **`strict`** (reward, weight 1.0) -- 1.0 exactly when the generator's own verifier gives
  strict `passed` on the episode. The sampled tool calls are ordered by the `seq` in the
  tool message each one got back, not by the order they appear in.
* **`leaky_pass`** (metric) -- the leaky predicate. It is descriptive and is deliberately
  not a reward: it must not be summed into `Trace.reward`.
* **`mutation_count`**, **`sampled_calls`**, **`turns`** (metrics) -- diagnostics. Calls on
  prompt-supplied assistant messages are not counted: a control arm's seeded history is not
  the model's work.

`await ExportTask.validate(None)` (a coroutine, as verifiers defines it) re-checks that the
reference solution passes under *both* strictnesses, and gives `False` for a bundle whose
reference falls short. Generation
already refuses such a bundle; this is where the export says so.

## The harness the numbers were measured under

**The measured harness is `null`.** `MEASURED_HARNESS` is that string, and every number the
pin ledger carries was produced under it. The `null` harness gives the model the task's
prompt and the task's tool block and nothing else.

**Running under another harness is outside the pin ledger.** A harness brings its own tools
and its own system prompt, and both of those are pinned quantities: pin-ledger row N3
([knobs and arms](knobs-and-arms.md)) pins the system prompt byte for byte across the arms of a contrast, and the advertised block is pinned to
the bundle's. A harness that prepends its own system prompt or adds a shell tool has
changed the prompt the arms are supposed to share, so a difference measured across arms is
no longer a difference in the knob. The numbers may still be interesting; they are not
comparable with the pinned ones, and they are not what the ledger says.

**`eval poisson-tasks` runs `null` with no flag.** At 0.3.1 a taskset's default harness is
`bash` unless the taskset's own environment says otherwise, and this one's does: its
environment pins `agent.harness.id` to `null`, `agent.runtime.type` to `subprocess` and
`agent.max_turns` to 32, and nothing else. **A harness named on the command line still wins**
(`--env.agent.harness.id bash`), and a run under it is outside the pin ledger, as above.

**An episode ends after 32 model calls.** verifiers sets no turn limit of its own, so a model
that never stops would keep calling tools until its context filled, costing tokens on every
call, and the run would report the end as a setup failure. At 32 calls the episode stops as
`max_turns` and is scored `turn_limit`: the model's own failure, named as one. The number is
four times the deepest task's minimum (eight calls, at `depth:d8`). Ordinary episodes of both
calibrated models end within 18 calls, and in the arms where Qwen3-8B looped, moving the cap
anywhere from 24 to 50 changes 1 episode in 900, so the cap binds only an episode that does
not stop. It shows in the run's saved config, and `--env.agent.max-turns N` overrides it; a
run with another cap is not comparable with the calibration cards.

**`eval` needs `--no-push` to stay local.** Without it verifiers uploads a finished run to
the Prime Intellect platform, to the private Evaluations tab of the account that
`$PRIME_API_KEY` or `prime login` names. The configs `poisson-tasks export` writes have
`push` off.

## Reading a trace

Each rollout gets a tool server of its own, so two rollouts of one task share no record and
no counter. Two things about the server are worth knowing if you are reading a trace:

* **The advertised block is the bundle's, exactly** -- the names in slot order, the
  descriptions, and the parameter schemas as written, with no `<server>_` prefix on the
  names.
* **A call that fails its own schema still reaches the engine.** It comes back as the
  engine's numbered `bad_args` line and the counter advances, because every call is
  numbered; that keeps a replay of the same calls in step with the live run. A depth
  control's seeded history is numbered too, so its first live line is not numbered 1.

## What this export does not do

* It does not decide a format check on the model's raw text. The reward's verdict is the
  state the ledger ends in; whether the raw text was a readable tool call is the serving
  stack's parser's to say.
* It does not pin the model, the endpoint or the sampling: those are the command line's,
  and the saved config records what was used.
