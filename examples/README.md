# Examples

Four short programs that use the library, smallest first. They are source to read and copy: they live in the repository and are not installed with the package. Run them from a checkout's root (the [contributing guide](../CONTRIBUTING.md) sets one up). Each takes `--help`, and a mistaken argument gets one line, `error: ...`. They use generator version `"0"`, the label the published cards carry ([docs/python.md](../docs/python.md) says what the label is).

`poisson-tasks` does the first three from the command line: `generate --show` and `verify --self-check` for the first, `generate` for the second, `card --published` for the third. The programs show the same calls in Python.

## `one_task.py` -- one task, and every answer it ships with

```
python examples/one_task.py [SEED]
```

Generates a single depth-3 task and prints the system prompt, the task, the sixteen tools, the goal, the reference solution with the line the domain returns for each call, and then the verdict on the reference solution and on each of the wrong answers the bundle carries. Each wrong answer is named for the outcome it should earn, so the last block reads as a list of `name -> name` pairs, which is the point.

No network, no model, no Prove. Runs in under a second. Start here, then read [docs/the-task.md](../docs/the-task.md).

## `a_contrast.py` -- the arms of a knob, and the pin ledger over them

```
python examples/a_contrast.py
```

Builds four arms of the depth knob and all five of the decoy-tools knob at one seed, runs the pin ledger over each contrast, and prints what it found: which rows were measured off the bundles, which two could not be and why, and the one row that *reports* rather than refuses. Then it builds a deliberately broken contrast -- two arms generated from different seeds -- and prints the three rows that catch it.

No network, no model, no Prove. Then read [docs/knobs-and-arms.md](../docs/knobs-and-arms.md).

## `calibration_card.py` -- a published calibration card, recomputed from its records

```
python examples/calibration_card.py [DIR]
python examples/calibration_card.py --page
```

Reads the 4,200 per-episode records behind the first published card (`calibration/gpt-5-nano-2025-08-07/episodes.jsonl`), rebuilds the machine-readable card from them alone under the provenance its run recorded, checks that it is byte-identical to the committed `artifact.json`, says whether the card is current for the installed generator, and prints the rendered card: the level tables, the control arms, cost, the level-to-level comparisons, the ordering and the provenance.

DIR is one model's folder under `calibration/`: `gpt-5-nano`'s by default, or `calibration/qwen3-8b-b968826d` for `Qwen3-8B`'s. `--page` rebuilds every committed card and prints the one page for all of them, where the models agree and then each card in full, which is what `docs/calibration.md` holds.

No network, no model, no Prove. The records were produced by real model calls; this only does the arithmetic. Read it with [docs/reading-a-card.md](../docs/reading-a-card.md).

## `prove_sweep/run.py` -- the whole scripted path, end to end

```
python examples/prove_sweep/run.py [--store DIR]
```

**Needs Prove installed**: `pip install "poisson-tasks[prove]"` brings `poisson-prove` from PyPI; [docs/prove.md](../docs/prove.md) says more. The other three examples run without it.

Writes a pre-registration, builds a registry module from it under its own hash, writes a Prove sweep spec, and runs three real `poisson-prove sweep` processes -- one per arm -- driven by the reference policy, the one that plays each task correctly. Then it reads the stored episodes back out of the run store and prints their outcomes, and runs a `poisson-prove diff` of the two depth arms.

Every episode comes back `passed`, and the depth arms differ in `t` -- 2 turns at `d1`, 4 at `d3` -- which is the scripted path doing its job: the instrument is exercised with the model taken out, so a later failure is a model's and not the harness's.

It takes a few seconds and writes about 80 KB under `examples/prove_sweep/example-store`, which is git-ignored. Delete that directory to start over.
