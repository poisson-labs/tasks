# Knobs, arms and the pin ledger

A knob is a thing you vary on purpose. An arm is one setting of it. The whole point of
the generator is that two arms of one knob differ in the knob and in nothing else, and
the pin ledger is what makes that a measurement rather than a hope.

`examples/a_contrast.py` prints all of this. Read that beside this page.

## The two knobs

**`depth`** -- how many chained stage calls the goal is away. Levels `1, 2, 3, 5, 8`. A
depth-*d* task needs *d* calls plus a reply turn, and the chain token makes them
genuinely sequential: no model can skip to the end.

**`distractor`** -- how many of the sixteen tools in the block are irrelevant. Levels
`0, 2, 4, 8, 14`. Every arm needs the same number of calls, so a difference in outcome
across these arms is a difference in *selection*, not in reasoning depth.

`levels(knob)` returns the candidate levels. Which of them a study actually sweeps is a
pre-registration decision, not a property of the generator.

## Arms

```python
ArmSpec(knob, level, control, strictness, split, generator_version)
```

`arm_id(spec)` renders it: `depth:d3`, `distractor:r8@k16`, `depth:d1+h8`.

**Control arms.** A control arm answers the obvious objection to each knob.

* A depth arm is longer as well as deeper, so a drop at `d8` could just be length.
  `depth:d1+h8` is the control: a depth-**1** task whose prompt is *seeded* with the
  history a depth-8 episode would have produced. It is as long as `d8` and as deep as
  `d1`. If the model drops at `d8` but not at `d1+h8`, the drop is depth.
* A distractor arm has a different tool block, so a drop at `r14` could just be a longer
  block. `distractor:r0+len(r8)@k16` holds the block's token count where `r8` puts it
  while keeping `r0`'s tools.

`control` holds the level being stood in for, so it must be higher than `level`; an arm
spec that cannot be rendered cannot be built, and the constructor raises.

**A sweep of a knob without its control arm is a pre-registration error**, and
`validate_preregistration` refuses the registration rather than letting the study run.

## Turn budgets

`spec.reference_turns` is the minimum: the calls the arm needs, plus the reply turn.
`spec.max_turns(slack)` adds the slack constant the study chose -- 4 in the pilot.

A registration's **horizon** is the largest `max_turns` over its arms, and it is checked
rather than declared: `validate_preregistration` recomputes it and refuses a document
that states a different number. The horizon is what Proofload uses to cut an episode
short, so a wrong one silently truncates the deepest arm.

## The pin ledger

Thirteen rows. Every row is an equality **across the arms of one contrast**, measured on
the generated bundles. `check_pins({arm_id: bundle, ...})` runs them and returns a
`PinReport`.

| row | holds equal across arms | who |
|---|---|---|
| N1 | the scenario -- every seed-drawn field | both knobs |
| N2 | where the required tools sit in the block | both |
| N3 | the system prompt | both |
| N4 | the tool block itself | `depth` |
| N5 | the block's token count | `distractor` -- **reported**, not refused |
| N6 | the user prompt: its template and its slot token counts | both |
| N7 | the overlap between the prompt's words and the tool names | both |
| N8 | the observation size | checked by the engine's own tests |
| N9 | the seeded history, as a token band over the contrast | `depth` controls |
| N10 | the serving pin: model, revision, vLLM version, sampling | at run time |
| N11 | verifier strictness | at run time |
| N12 | the engine, vocabulary and generator hashes | at run time |
| N13 | realised first-request input tokens, per model | at analysis |

The last four cannot be measured from a bundle -- there is no model, no server and no
trace at generation time -- so `measure_pins` puts each in `unmeasured` with the reason,
rather than leaving it out. Every row is in exactly one of the two, which is what makes
"a row nobody checks" impossible to write.

**A violated row refuses the contrast** before any model runs, except N5, which reports.
The distinction matters and is why the rows carry their own action rather than a
boolean: the block's token count *should* move with the distractor level, so N5 is a
number to record, not a failure.

## One known gap

Six of the 512 record-id words are a substring of some tool name, and four of them
(`city`, `disc`, `grad`, `port`) make N7 refuse a distractor contrast that holds the
`r14` arm -- the one level whose block keeps no read tool at all. Knob `depth` is
unaffected at every level. It is measured, it is in `gap-log.md`, and it closes outright
the day a vocabulary version draws the record-id word lists disjoint from every tool
name.
