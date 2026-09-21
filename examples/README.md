# Examples

Three, smallest first. Run them from the repository root with the virtual environment
the [README](../README.md) sets up.

## `one_task.py` -- one task, and every answer it ships with

```
python examples/one_task.py [SEED]
```

Generates a single depth-3 task and prints the system prompt, the task, the sixteen
tools, the goal, the reference solution with the line the domain returns for each call,
and then the verdict on the reference solution and on each of the wrong answers the
bundle carries. Each wrong answer is named for the outcome it should earn, so the last
block reads as a list of `name -> name` pairs, which is the point.

No network, no model, no Proofload. Runs in under a second.

Start here, then read [docs/the-task.md](../docs/the-task.md).

## `a_contrast.py` -- the arms of a knob, and the pin ledger over them

```
python examples/a_contrast.py
```

Builds four arms of the depth knob and all five of the distractor knob at one seed, runs
the pin ledger over each contrast, and prints what it found: which rows were measured off
the bundles, which two could not be and why, and the one row that *reports* rather than
refuses. Then it builds a deliberately broken contrast -- two arms generated from
different seeds -- and prints the three rows that catch it.

No network, no model, no Proofload.

Then read [docs/knobs-and-arms.md](../docs/knobs-and-arms.md).

## `proofload_sweep/run.py` -- the whole scripted path, end to end

```
python examples/proofload_sweep/run.py [--store DIR]
```

**Needs the optional `proofload` extra**, and Proofload is not yet publicly available;
see the README's install section. The other two examples run without it.

Writes a pre-registration, builds a registry module from it under its own hash, writes a
Proofload sweep spec, and runs three real `proofload sweep` processes -- one per arm --
driven by the reference policy, the one that plays each task correctly. Then it reads the
stored episodes back out of the run store and prints their outcomes, and runs a
`proofload diff` of the two depth arms.

Every episode comes back `passed`, and the depth arms differ in `t` -- 2 turns at `d1`, 4
at `d3` -- which is the scripted path doing its job: the instrument is exercised with the
model taken out, so a later failure is a model's and not the harness's.

It takes a few seconds and writes about 80 KB under `examples/proofload_sweep/example-store`,
which is git-ignored. Delete that directory to start over.
