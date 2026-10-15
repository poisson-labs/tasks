# The Proofload route (optional)

Proofload is one of the two routes a generated task can be run down, beside verifiers. It is an **optional route, not a dependency**, and **Proofload is not publicly available yet**, so there is no extra for it and no index to install it from. It comes from a checkout installed into the same environment. Nothing in the README's first run, in `poisson-tasks` or in the verifiers export needs it.

`poisson_tasks.adapter` is the only module that needs Proofload. Without Proofload installed, `import poisson_tasks` and every module under it work as they do with it, and importing the adapter raises a `ModuleNotFoundError` that says where Proofload comes from. The tests that need Proofload are skipped without it, and say so.

## Install it beside Tasks

With a Proofload checkout at `../proofload` and a checkout of this repository:

<!-- docs-check: skip reason="needs a checkout of Proofload, which is not public" -->
```bash
.venv/bin/pip install -e ../proofload
.venv/bin/pip install -e ".[dev]"
export PATH="$PWD/.venv/bin:$PATH"
```

The `PATH` line is required: the adapter and its tests shell out to `proofload`.

## The scripted path, end to end

<!-- docs-check: skip reason="needs Proofload installed" -->
```bash
.venv/bin/python examples/proofload_sweep/run.py
```

The example writes a pre-registration, builds a registry module from it under its own hash, writes a Proofload sweep spec, and runs three real `proofload sweep` processes, one per arm, driven by the reference policy: the one that plays each task correctly. It then reads the stored episodes back and prints their outcomes, and runs a `proofload diff` of the two depth arms. Every episode comes back `passed`, and the depth arms differ in turns: 2 at `d1`, 4 at `d3`. That is the point of the scripted path: the instrument is exercised with the model taken out, so a later failure is a model's and not the instrument's.

It takes a few seconds and writes about 80 KB under `examples/proofload_sweep/example-store`, which git ignores. Delete that folder to start over. [The example](https://github.com/poisson-labs/tasks/blob/main/examples/proofload_sweep/run.py) is source to read; [python.md](python.md) lists the others.
