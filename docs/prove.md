# The Prove route (optional)

Prove is one of the two routes a generated task can be run down, beside verifiers. It is an **optional route, not a dependency**: a plain install of Poisson Tasks does not bring it, and nothing in the README's first run, in `poisson-tasks` or in the verifiers export needs it. Prove is public on PyPI as `poisson-prove`, and Poisson Tasks asks for it through an extra, `prove`.

`poisson_tasks.adapter` is the only module that needs Prove. Without Prove installed, `import poisson_tasks` and every module under it work as they do with it, and importing the adapter raises a `ModuleNotFoundError` that names the extra. The tests that need Prove are skipped without it, and say so.

## Install it beside Tasks

<!-- docs-check: skip reason="installs Prove and its scientific stack from PyPI" -->
```bash
pip install "poisson-tasks[prove]"
```

The extra installs `poisson-prove` 0.1.0 or later, with no upper bound. The route is checked from both sides: every release of Tasks is run end to end against the Prove that PyPI serves, and 0.1.0, 0.1.1, 0.1.2 and 0.1.3 each passed; every pull request and release of Prove runs the same check, from the latest release of Tasks, before it ships. The command it adds is `poisson-prove` (`python -m poisson_prove` is the same).

From a checkout of this repository, the extra is installed with the development tools:

<!-- docs-check: skip reason="needs a checkout of this repository and installs from PyPI" -->
```bash
.venv/bin/pip install -e ".[dev,prove]"
```

## The scripted path, end to end

<!-- docs-check: skip reason="needs Prove installed" -->
```bash
.venv/bin/python examples/prove_sweep/run.py
```

The example writes a pre-registration, builds a registry module from it under its own hash, writes a Prove sweep spec, and runs three real `poisson-prove sweep` processes, one per arm, driven by the reference policy: the one that plays each task correctly. It then reads the stored episodes back and prints their outcomes, and runs a `poisson-prove diff` of the two depth arms. Every episode comes back `passed`, and the depth arms differ in turns: 2 at `d1`, 4 at `d3`. The example reads the `diff` from `--json`, where `truncated` is 0, which is the registration's horizon cutting no arm short. That is the point of the scripted path: the instrument is exercised with the model taken out, so a later failure is a model's and not the instrument's.

It takes a few seconds and writes about 80 KB under `examples/prove_sweep/example-store`, which git ignores. Delete that folder to start over. [The example](https://github.com/poisson-labs/tasks/blob/main/examples/prove_sweep/run.py) is source to read; [python.md](python.md) lists the others.

## What a release checks

`scripts/release/prove_e2e.py` is the same route from nothing but two published packages: it takes the wheel built from the tree, makes a fresh environment, installs the wheel with its `prove` extra so that `poisson-prove` comes from PyPI, runs the example and the real `poisson-prove` command on the built-in tasks, reads the episodes back, and then uninstalls Prove and checks that Tasks still imports and that the adapter is refused with the extra's name. Every release runs it ([releasing.md](releasing.md)), and so does the fast lane of the pull request check.

## Registrations, and the horizon

A study run down this route is registered before it runs: which levels of a knob it sweeps is written down in advance, and is not a property of the generator. `poisson_tasks.adapter.validate_preregistration` checks a registration, and takes depth and the decoy-tools dial only. A sweep of a knob without its control arm is refused, rather than letting the study run.

A registration's **horizon** is the largest `max_turns` over its arms (`spec.max_turns(slack)`, [knobs-and-arms.md](knobs-and-arms.md)), and it is checked rather than declared: `validate_preregistration` recomputes it and refuses a document that states a different number. The horizon is what Prove uses to cut an episode short, so a wrong one would silently truncate the deepest arm.
