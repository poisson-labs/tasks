# Knobs, arms and the pin ledger

A knob is a thing you vary on purpose. An arm is one setting of it. The whole point of
the generator is that two arms of one knob differ in the knob and in nothing else, and
the pin ledger is what makes that a measurement rather than a hope.

`poisson-tasks generate` runs the pin ledger over the arms of your plan and says what it found; [python.md](python.md) shows the same check from Python.

## The knobs

Fourteen are named: the two the published cards measured, the seven newer knobs the knob
probe measured, three transport faults added in 0.3.0 and two bad-data knobs added in 0.4.0.
No model has been measured on those five yet. The generator makes tasks for twelve of the
fourteen; `landed` and `lagged` are made on your own tools only, each for a reason given
below.

**`depth`** -- how many chained stage calls the goal is away. Levels `1, 2, 3, 5, 8`. A
depth-*d* task needs *d* calls plus a reply turn, and the chain token makes them
genuinely sequential: no model can skip to the end. Every depth level offers the whole
eight-stage ladder, so below the top level a model can also carry the record past the goal;
a calibration card reads depth on reaching the goal and shows overshoot beside it
([calibration](calibration.md)).

**`distractor`** -- how many of the sixteen tools in the block are irrelevant. Levels
`0, 2, 4, 8, 14`. Every arm needs the same number of calls, so a difference in outcome
across these arms is a difference in *selection*, not in reasoning depth. **Experimental:**
on both calibrated models it does not make tasks harder, so it is not a difficulty setting
for current models ([calibration](calibration.md)). A distractor tool is named for its
ledger class and stage, so choosing the right tool is close to a string match with the
class the prompt names.

The seven newer knobs each vary one thing about a small base task: two chained stage calls
in a sixteen-tool block (shape, which makes four stage calls at every width, varies how
they are arranged, and its base is its one-chain width).

| knob | varies | levels | arm ids | control arm |
|---|---|---|---|---|
| `similarity` | how many digits each lookalike ledger's four-digit number shares, in place, with the target's | `0, 1, 2, 3` | `similarity:s3` | none |
| `faults` | how many calls on the way answer `unavailable` and must be made again | `0, 1, 2, 4` | `faults:f2` | `faults:f0+len(f4)` |
| `history` | how many tokens of earlier tool work sit in the conversation | `0, 300, 600, 1200, 2400` | `history:t600` | none |
| `block` | how many tools are offered | `8, 16, 32, 64` | `block:k32` | `block:k8+len(k64)` |
| `arguments` | how many values each stage call must carry | `2, 4, 6, 8` | `arguments:a6` | `arguments:a2+len(a8)` |
| `shape` | how many records four stage calls advance side by side | `1, 2, 4` | `shape:w2` | `shape:w1+len(w4)` |
| `spread` | how many tool answers the entry code is split across | `1, 2, 4` | `spread:p4` | none |

A level outside a knob's candidates can still be an arm (`history:t12800`); a level the
knob has no task for cannot, and `ArmSpec` refuses it: a similarity level outside
0 to 3, a negative faults, history, timeouts, ratelimits or landed level, a landed level
above 1, a block under 8 or over 258 (the two tools the task needs and every read name the
table can make), an arguments level outside 2 to 8, a shape width other than 1, 2 or 4, a
spread level outside 1 to 4, a baddata level outside 0 to 3, a lagged level other than 0 or 1.

### Three transport faults

The faults knob answers a planned call `unavailable`: nothing changed, and the same call
works when made again. Two requests from the launch asked for the other things a call can
come back with, and 0.3.0 adds them as three knobs beside it, each the faults design with its
own status word and its own sentence in the system prompt. None of the three has been
measured on any model yet, so each is **experimental**, and every place that names one says so
with that reason.

| knob | varies | levels | arm ids | control arm |
|---|---|---|---|---|
| `timeouts` | how many calls on the way time out, nothing having landed, and must be made again | `0, 1, 2, 4` | `timeouts:o2` | `timeouts:o0+len(o4)` |
| `ratelimits` | how many calls on the way answer `rate_limited` with a retry-after, and must be made again | `0, 1, 2, 4` | `ratelimits:r2` | `ratelimits:r0+len(r4)` |
| `landed` | whether the write goes through but answers a timeout, so a blind retry is a duplicate | `0, 1` | `landed:l1` | none |

What the model sees is one line in each case, the engine's own layout with the knob's word
in the status field:

```text
000003 timeout      00000000000000000000000000000000
000003 rate_limited retry-after=1s000000000000000000
```

A timeout says only that whether the call went through is not known; a rate limit says that
nothing changed and when to make the call again. Tasks has no clock, so the retry-after is a
hint the model reads, and nothing in an episode waits. Each knob adds one sentence to the
system prompt at every level, level 0 included, as faults does: for timeouts (and for
landed), "A call can come back `timeout`: whether it went through is not known."; for
ratelimits, "A call can come back `rate_limited` with a retry-after: nothing changed, and
the same call can be made again after that long." The timeouts sentence is deliberately
silent on whether a retry is safe: that silence is the kind, and whether the drop deepens
between a `503` and a timeout is the question the knob is for.

`landed` has no control arm: one planned pair is 33 reference tokens and the shortest read
pair a control can seed is 51, so no seeded history matches its length within the ledger's
two tokens, and the landed line adds no call to make up the difference. It is not built on
the built-in tasks either: the ledger refuses a repeated stage call (`not_ready`, nothing
moved), so a write that landed and answered a timeout has no duplicate for the end-state
check to catch, and `generate` says so in one line. On your own tools the store accepts a
second write as yours would, a read after a write shows the written record, and `landed` is
offered on any set that has a read tool taking one of the target write's arguments
([own-tools.md](own-tools.md)).

### Reads that say ok and are wrong

Every fault above is loud: a status word says that something went wrong. A comment on the
launch asked for the quiet kind, a read that answers `ok` with a value that is out of date or
wrong, and 0.4.0 adds it as two knobs. No model has been measured on either yet, so each is
**experimental**, and every place that names one says so with that reason.

| knob | varies | levels | arm ids | control arm |
|---|---|---|---|---|
| `baddata` | how little one read's first, wrong answer gives away; the same read made again is right | `0, 1, 2, 3` | `baddata:b2` | none |
| `lagged` | whether the first read after a write still shows the record as it was | `0, 1` | `lagged:g1` | none |

**`baddata`.** The request does not state which record to move or how far. It names both
records of the ledger and two reads: the first read's answer names the record, by the first
words of its id, and the second names the stage to raise it through.

```text
One of two records of the purchase ledger is to advance: "national-listed-wide-limit" or "able-sheet-shopping-question".
Stage ladder: review then sample then measure then monitor then compare then bundle then route then label.
The first read below names the record, by the first words of its id; the second names the stage to raise it through, and no further.
The two reads:
1. the density field of catalogue item "found-open-support-create" on page "5aa129a4931ade7fea000dca209b8d7f"
2. the color field of catalogue item "mark-used-number-event" on page "92998c229eedf4e3f98776a52a309f02"
Each answer's payload is the first word of the catalogue item it answers for, a slash, what it names, a full stop, then filler.
Open with entry code "public"; each later stage needs what the stage before returned.
```

At level 0 both reads answer truthfully. Above it, one of the two answers `ok` and wrong the
first time it is made, and the same read made again is right from then on. The level is what
that first answer holds; the last column is that answer and the next, on the task above:

| level | the first answer | what gives it away | the two answers |
|---|---|---|---|
| 0 | the truth | nothing to give | `found/able.…`, once |
| 1 | the other record, under another catalogue item's word | the answer itself: it is not for the item asked | `user/national.…`, then `found/able.…` |
| 2 | the other record, under the asked item's word | only a second read | `found/national.…`, then `found/able.…` |
| 3 | on the second read, a stage one short of the goal | only a second read, and the two differ by one stage | `mark/review.…`, then `mark/sample.…` |

The request, the tool block, the system prompt and the goal are the same at every level, and
so are the two reads: pin-ledger row N36 holds the reads and what each answers, and row N4
the block. Only the exact call counts toward a read's first answer: the same tool with the
same item and page. A call to that tool with another item or page is another call, and
leaves the named read's first answer still to come. The reference solution makes each read
once at level 0 and the bad read twice above it, so `reference_turns` is 5 at `baddata:b0`
and 6 above it.

**A level is a rung, not a quantity.** The faults knob counts how many calls fail. A count
measures nothing here: a model that does not check fails at one bad answer, and a model that
does passes at any number of them. So the level is how little the bad answer gives away. At
1 the answer itself shows it is for another item; at 2 nothing on it says so; at 3 it also
differs from the truth by a single stage. Nothing promises that a higher level is harder
until a model has been measured on it.

**Every bad answer heals on the next read.** One read's first answer is wrong and every later
answer to the same call is right; no read is wrong twice. A value that stayed wrong could be
caught only with a second source and a rule for which of the two to believe, and this
release has neither. So a model that checks reads again, and reading until two answers in a
row agree is right at every level, level 0 included. A read costs nothing in an episode: it
moves no record, so the verdict never counts one against the model.

**What the model is told** is one line of the system prompt, at every level, level 0
included: "A read can come back `ok` with a value that is out of date or wrong." It names
the hazard and not what to do about it.

**What catches it** is the end state, and no new label. A model that trusts the bad answer
advances the other record (levels 1 and 2) or stops a stage short (level 3): `wrong_state`,
which fails strict and leaky. One that advances the other record and then the right one
ends `collateral_mutation`, since the first move cannot be taken back: strict fails it and
leaky accepts it. A card shows what the model did in two columns, *acted on bad data* and
*read again after a bad answer* ([reading-a-card.md](reading-a-card.md)).

**No control arm.** A control arm separates a knob from the length it adds, and here the
length cannot explain a drop. A model that trusts the first answer makes exactly level 0's
calls, with one answer's text different; the one extra read is made only by an episode that
checks, which is the one that passes. Level 0 is already the control, and `ArmSpec` refuses
`baddata:b0+len(b3)` saying so.

**`lagged`** is the same hazard after a write of the model's own. The request is a write,
then a read to check that it took; at level 1 the first read after the write answers as if
the write had not landed, and every later read shows it. A model that believes the read
over the write's own answer writes again, and that is a duplicate. It is made on your own
tools only: the built-in ledger has no read of a record and refuses a repeated stage call, so
there a read that lags a write has nothing to show and a second write nothing to break, and
`generate --arm lagged:g1` refuses in one line that says so. It has no
control arm either, for the same reason. [own-tools.md](own-tools.md) shows the request and
says what a tool set needs for each of the two.

`levels(knob)` returns the candidate levels; which of them a run measures is up to its recipe
or its settings file ([config.md](config.md)). The names on this page that are not
commands (`levels`, `ArmSpec`, `arm_id`, `check_pins`, `measure_pins`, `PinReport`) are in
`poisson_tasks.knobs`.

### What the knob probe measured

The seven newer knobs were each measured once, on `gpt-5-nano` and on `Qwen3-8B`, at their
lowest and highest levels and at the control arm where there is one: 60 tasks, two attempts
each, strict pass@1, and the drop from the base arm to the top arm with a task-clustered 95%
interval. A knob **bites** on a model when the interval excludes zero and the drop is at least
0.15; `faults`, `block` and `arguments` need the same drop from their control arm to the top, and
`shape` counts either direction, as long as its length control differs from the base by less
than 0.15. **Cannot tell** replaces "does not bite" where the base arm passed below 0.15 on that
model, so a drop of 0.15 could not show; a base near 1 can still drop by 0.15, so it is read as
it came out. It also replaces "top easier" where the top arm passed above 0.85. A knob **ships**
when it bites on at least one model and is easier at the top on neither.

`faults`, `history` and `shape` shipped (`arms.SHIPPED_KNOBS`), and the recipes that measure
them are offered. The other four did not ship, and are labelled *Available · retested in v2*:
a later release measures them again, on current models, and until then they work but are not
shown to make tasks harder. Every knob stays in the generator and on the command line, and its
arms work whether or not it shipped. These are two models, measured once. The table, with every
contrast, is `poisson_tasks.arms.knob_status()`. In each cell Δ is the base arm's strict pass@1
minus the top arm's, with its interval; "control" is the control arm's minus the top arm's; for
`shape`, "length control" is the base's minus the length control's.

| knob | shipped | `gpt-5-nano` | `Qwen3-8B` |
|---|---|---|---|
| `similarity` | no | does not bite: Δ −0.050 [−0.150, 0.042] | does not bite: Δ 0.000 [0.000, 0.000] |
| `faults` | yes | does not bite: Δ 0.400 [0.300, 0.500], control 0.142 [0.033, 0.250] | bites: Δ 0.825 [0.742, 0.900], control 0.308 [0.150, 0.458] |
| `history` | yes | bites: Δ 0.683 [0.608, 0.750] | bites: Δ 0.308 [0.217, 0.417] |
| `block` | no | does not bite: Δ −0.067 [−0.142, 0.000], control −0.008 [−0.058, 0.042] | does not bite: Δ 0.000 [0.000, 0.000], control 0.000 [0.000, 0.000] |
| `arguments` | no | does not bite: Δ 0.092 [0.000, 0.183], control 0.000 [−0.108, 0.100] | does not bite: Δ 0.150 [0.067, 0.242], control 0.100 [0.017, 0.183] |
| `shape` | yes | does not bite: Δ −0.300 [−0.425, −0.175], length control 0.158 [0.058, 0.258] | bites: Δ 0.358 [0.233, 0.483], length control 0.000 [−0.033, 0.033]; `shape:w4` harder |
| `spread` | no | top easier: Δ −0.250 [−0.358, −0.142] | cannot tell: base passed 0.008; Δ 0.008 [0.000, 0.033] |

### Three things about how the probe ran

Three things about how the probe ran are disclosed wherever its outcome is published. Each is short; the numbers are the records' own. The probe ran in two phases on each model: phase 1, one attempt at each of three tasks on every one of its eighteen arms, checked that the run worked before the full measurement, phase 2, was spent.

**1. Phase 1's check changed after its first result (gpt-5-nano).** As written before the run, phase 1
stopped the probe if any base-arm episode made no tool call, and gpt-5-nano's first phase 1 stopped
on 1 of 21 (the model asked for the record id in plain text; nothing on our side failed). After
seeing that, on 2026-10-13, the check was changed to the published cards' own rule: stop when more
than 10% of the 21 base episodes make no tool call (3 or more). The recorded phase 1 was read
again once under it, with no episode run again: 1 of 21, so it passed, and the probe went on in
the same folder within the same $4.00 cap. Qwen3-8B's phase 1 passed under the first rule.

**2. A crash at the start, and one arm run again (gpt-5-nano).** The run crashed at its start
on macOS's limit on open files, with its first arm, `similarity:s0`, in flight. The limit was
raised and the run resumed. Episodes in flight at the crash failed on our side, so that arm was
void (instrument rate 0.104; every other arm 0.000) and was run once more, as the
probe's rules, written before it ran, allow once for a cause on our side. The void attempt is kept. In all, gpt-5-nano
cost $1.5981 of the $4.00 cap.

**3. More time for Qwen3-8B.** The Qwen3-8B run on Colab reached its two-hour allowance with 14
of its 18 arms done and stopped cleanly. It was given more time and resumed, the 14 finished arms
kept and the last four run with the same settings; it used 2.56 hours in all.

## Arms

<!-- docs-check: skip reason="shows the names of an arm's six fields, and is not a program" -->
```python
ArmSpec(knob, level, control, strictness, split, generator_version)
```

`arm_id(spec)` renders it: `depth:d3`, `distractor:r8@k16`, `depth:d1+h8`, `faults:f2`.

**Control arms.** A control arm answers the obvious objection to each knob.

* A depth arm is longer as well as deeper, so a drop at `d8` could just be length.
  `depth:d1+h8` is the control: a depth-**1** task whose prompt is *seeded* with the
  history a depth-8 episode would have produced. It is as long as `d8` and as deep as
  `d1`. If the model drops at `d8` but not at `d1+h8`, the drop is depth.
* A distractor arm has a different tool block, so a drop at `r14` could just be a longer
  block. `distractor:r0+len(r8)@k16` holds the block's token count where `r8` puts it
  while keeping `r0`'s tools.

* Faults, block, arguments and shape each lengthen something as the level rises: the
  conversation, the block, or the request. Each has one control format,
  `<arm>+len(<higher arm>)`, which keeps the lower level's task and adds the higher
  level's length. Similarity and spread hold length equal across their levels, and length
  is history's own factor, so those three have no control arm and refuse one. Baddata and
  lagged refuse one too: level 0 is their control, as their section above says.

`control` holds the level being stood in for, so it must be higher than `level`; an arm
spec that cannot be rendered cannot be built, and the constructor raises.

## Turn budgets

`spec.reference_turns` is the minimum: the calls the arm needs, plus the reply turn.
Depth *d* needs *d* + 1; faults, timeouts and ratelimits level *f* need 3 + *f*, one more
call per planned answer; shape needs 5 at every width and spread 7 at every level; baddata
needs 5 at level 0 (two reads and two stage calls) and 6 above it (the bad read made twice);
lagged needs 3 at level 0 (the write and the read) and 4 at level 1; every other arm needs 3,
landed among them (its one call lands).
`spec.max_turns(slack)` adds a slack you choose. A run of `poisson-tasks` caps every episode
at 32 model calls instead, four times the deepest task's minimum ([verifiers-export.md](verifiers-export.md)
says why).

## The pin ledger

Thirty-one rows: N1 to N13, then N19 to N36 for the newer knobs (the three transport faults of
0.3.0 join the rows the faults knob is held to, and add none; `baddata` adds N36). Every row is held
**across the arms of one contrast**, measured on the generated bundles. `check_pins({arm_id: bundle, ...})` runs them and returns a
`PinReport`.

| row | holds across arms | who |
|---|---|---|
| N1 | the scenario -- every seed-drawn field | every knob |
| N2 | where the required tools sit in the block | every knob |
| N3 | the system prompt; a `distractor` or `block` control may add a filler at its end | every knob |
| N4 | the tool block itself | `depth`, `faults`, `history`, `arguments`, `spread`, `baddata` |
| N5 | the block's token count | `distractor` -- **reported**, not refused |
| N6 | the user prompt: its template and its slot token counts, leaving out the slot that is the knob (the goal stage for `depth`, the stated values for `arguments`, the goal lines for `shape`) | every knob |
| N7 | the overlap between the prompt's words and the tool names | every knob -- **reported**, not refused, for `shape` |
| N8 | the observation size | every knob |
| N9 | the seeded history, as a token band over the contrast | `depth` controls |
| N10 | the serving pin: model, revision, vLLM version, sampling | at run time |
| N11 | verifier strictness | at run time |
| N12 | the engine, vocabulary and generator hashes | at run time |
| N13 | realised first-request input tokens, per model | at analysis |
| N19 | twelve lookalike tools in the block | `similarity` |
| N20 | the block's token count | `similarity` |
| N21 | each of six lookalike ledgers' numbers shares exactly the level's digits, in place, with the target's; none starts with 0 | `similarity` |
| N22 | the two right tools' names, descriptions and parameters | `similarity` |
| N23 | the seeded history's tokens are the level, within two | `history` |
| N24 | every seeded call is a read tool in the block, answered `ok` | `faults`, `history`, `timeouts`, `ratelimits`, `landed` |
| N25 | the planned answers, each in the knob's own word, are the level, split over the right tools, the first taking the odd one; for `landed`, one on the last tool | `faults`, `timeouts`, `ratelimits`, `landed` |
| N26 | the control's seeded tokens match the higher arm's failed calls, within two | `faults`, `timeouts`, `ratelimits` controls |
| N27 | the block holds exactly the level's number of tools | `block` |
| N28 | the right tools sit in the same slots, inside the first eight | `block` |
| N29 | the block's token count -- **reported**; the control's filler matches the higher arm's extra block, within two, or it refuses | `block` |
| N30 | the stage tools' schemas | `arguments` |
| N31 | each stage call carries the level less two extra values, the same on each, each stated in the request and carried by no tool name | `arguments` |
| N32 | the control's request is as long as the higher arm's, within two tokens | `arguments` control |
| N33 | four stage calls and sixteen tools at every width; the block's token count is **reported** | `shape` |
| N34 | the control's request is as long as the widest arm's, within two tokens | `shape` control |
| N35 | the same four reads at every level; as many answer with a part as the level, and the parts join, in order, to the entry code | `spread` |
| N36 | bad data's reads: the same two named reads at every level; at level 0 each answers once; above it exactly one answers twice, and its first answer's head (the payload up to the full stop) is not its second's | `baddata` |

N10 and N13 cannot be measured from a bundle -- there is no server and no trace at
generation time -- so `measure_pins` puts each in `unmeasured` with the reason, rather
than leaving it out. Every other row is measured on every bundle, whatever its knob, and
every row is in exactly one of the two, which is what makes "a row nobody checks"
impossible to write. Which rows a contrast is held to is the "who" column.

**A violated row refuses the contrast** before any model runs. A reported row does not:
N5 only ever reports, N7 reports on a `shape` contrast, and N29 and N33 report the block's
growth beside whatever they refuse. The distinction matters and is why a report lists
`violations` and `reported` apart rather than one boolean: a block's token count *should*
move with the distractor level or the block size, so it is a number to record, not a
failure.
