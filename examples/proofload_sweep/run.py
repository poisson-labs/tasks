"""Run two arms of the depth knob through Proofload, end to end, and read the outcomes.

    python examples/proofload_sweep/run.py [--store DIR]

This is the whole scripted path: a pre-registration file, a registry module built from
it, a Proofload sweep spec, and two real `proofload sweep` runs driven by the reference
policy -- the one that plays each task correctly. Every episode should come back
`passed`, because the policy is the answer the generator shipped with the task. That is
the point of the scripted path: it exercises the plumbing with the model taken out, so a
later failure is a model's and not the instrument's.

It needs Proofload importable and `python -m proofload` runnable. Nothing else, and no
network: the tasks are generated in process and the policy is a function.

Files it writes, under `--store` (default: ./example-store beside this file):

    registration.toml   the pre-registration: knob, arms, slack, horizon, split
    registry.py         `load_registry(...)` plus one module-level callable per arm
    sweep.toml          Proofload's own spec: the cfg axes, held at one value each
    runs/               the store the sweep writes to
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys

from poisson_tasks.knobs import ArmSpec, arm_id
from poisson_tasks.tasks import generate

HERE = pathlib.Path(__file__).resolve().parent

GENERATOR_VERSION = "0"  # the version the published cards were measured at
SLACK = 4  # N16: the turn budget is the turns the arm needs, plus this
SPLIT = "eval"
STRICTNESS = "strict"
REPLICATES = 8
MAX_MDE = "0.99"  # this run is about the plumbing, not about detecting an effect
SALT = "0123456789abcdef"

# Two arms of one knob -- depth 1 and depth 3 -- and depth 1's control arm. Same
# scenario, same tools, same prompt shape; the only difference between d1 and d3 is how
# many chained stage calls the goal is away.
#
# `depth:d1+h3` is the control: a depth-1 task whose prompt is seeded with the history a
# depth-3 episode would have produced, so it is as *long* as d3 without being as *deep*.
# Leaving it out is a pre-registration error, and `validate_preregistration` says so --
# try deleting it from this list and running again.
ARMS = [
    ArmSpec("depth", 1, None, STRICTNESS, SPLIT, GENERATOR_VERSION),
    ArmSpec("depth", 3, None, STRICTNESS, SPLIT, GENERATOR_VERSION),
    ArmSpec("depth", 1, 3, STRICTNESS, SPLIT, GENERATOR_VERSION),
]


def registration_text() -> str:
    """The pre-registration, as TOML.

    `horizon` is N17's declared number: the largest turn budget any arm in this
    registration has. `validate_preregistration` recomputes it and refuses a document
    that states a different one, so it cannot drift from the arms beside it.
    """
    horizon = max(arm.max_turns(SLACK) for arm in ARMS)
    arms = json.dumps([arm_id(a) for a in ARMS])
    return (
        f'knob = "depth"\n'
        f'strictness = "{STRICTNESS}"\n'
        f'split = "{SPLIT}"\n'
        f'generator_version = "{GENERATOR_VERSION}"\n'
        f"slack = {SLACK}\n"
        f"horizon = {horizon}\n"
        f"arms = {arms}\n"
    )


def registry_text(registration: pathlib.Path, digest: str) -> str:
    """A registry module is three lines: load the registration under its hash, then put
    the targets it built into the module's globals, where `--target` can reach them."""
    return (
        "from poisson_tasks.adapter import load_registry\n\n"
        f"REGISTRY = load_registry({str(registration)!r}, sha256={digest!r})\n"
        "globals().update(REGISTRY.targets)\n"
    )


def sweep_text(horizon: int) -> str:
    """Proofload's spec. Every cfg axis is held at one value, because this run is about
    the plumbing and not about a contrast; `t_unit = "turns"` is what the horizon counts.

    `replicates` and `--max-mde` are a real gate: Proofload refuses a design it judges
    underpowered for the effect you say you want to detect, before it runs anything. At 8
    replicates it will only accept a loose `--max-mde`, which is honest for a run whose
    outcome is known in advance."""
    generator_hash = generate(ARMS[0], 0).generator_hash
    return (
        'target_id = "poisson-tasks-example"\n'
        't_unit = "turns"\n'
        f"replicates = {REPLICATES}\n\n"
        f'[axes.slack]\ntype = "continuous"\nvalues = [{SLACK}]\n\n'
        f'[axes.horizon]\ntype = "continuous"\nvalues = [{horizon}]\n\n'
        f'[axes.strictness]\ntype = "categorical"\nvalues = ["{STRICTNESS}"]\n\n'
        f'[axes.generator_hash]\ntype = "categorical"\nvalues = ["{generator_hash}"]\n'
    )


def sweep(store: pathlib.Path, spec: pathlib.Path, target: str, modules: pathlib.Path) -> str:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(modules)] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])
    )
    done = subprocess.run(
        [sys.executable, "-m", "proofload", "--store", str(store), "sweep", str(spec),
         "--target", target, "--max-mde", MAX_MDE, "--salt", SALT, "--yes"],
        env=env, capture_output=True, text=True, timeout=600,
    )
    found = re.search(r"^run_id: (\S+)$", done.stdout, re.M)
    if done.returncode != 0 or found is None:
        raise SystemExit(
            f"proofload sweep --target {target} exited {done.returncode}\n"
            f"--- stdout\n{done.stdout}\n--- stderr\n{done.stderr}"
        )
    return found.group(1)


def episodes(store: pathlib.Path, run_id: str) -> list[dict[str, object]]:
    """The stored episodes, read from the store's parquet files.

    `outcome`, `t` and `seed` are Proofload's own columns. `meta` is what the adapter
    wrote beside them -- the arm, the knob and level, the scenario and task ids, the
    pin record, and the calls the policy actually made. Proofload's public verbs do not
    print an episode's `meta`, which is why this reads the files; that is filed as PG-17
    in `gap-log.md`.
    """
    import pyarrow.parquet as pq

    rows: list[dict[str, object]] = []
    for part in sorted((store / run_id / "episodes").glob("part-*.parquet")):
        rows.extend(pq.read_table(part).to_pylist())
    for row in rows:
        row["meta"] = json.loads(str(row["meta"]))
    return sorted(rows, key=lambda r: int(r["replicate_index"]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=pathlib.Path, default=HERE / "example-store")
    args = parser.parse_args()
    out = args.store
    out.mkdir(parents=True, exist_ok=True)

    registration = out / "registration.toml"
    registration.write_text(registration_text())
    digest = hashlib.sha256(registration.read_bytes()).hexdigest()
    print(f"registration {registration}\n  sha256 {digest}")
    print("  " + registration_text().replace("\n", "\n  ").rstrip())

    modules = out / "modules"
    modules.mkdir(exist_ok=True)
    (modules / "registry.py").write_text(registry_text(registration, digest))

    from poisson_tasks.adapter import load_registry

    registry = load_registry(registration, sha256=digest)
    print(f"\nregistry: slack {registry.slack}, horizon {registry.horizon}")
    print(f"  targets: {', '.join(sorted(registry.targets))}")

    spec = out / "sweep.toml"
    spec.write_text(sweep_text(registry.horizon))

    store = out / "runs"
    run_ids: dict[str, str] = {}
    for arm in ARMS:
        # The target name is the policy, then the arm id with every run of
        # non-alphanumeric characters collapsed to one underscore: `--target module:attr`
        # will not take a colon or a plus in an attribute name.
        target = "reference_" + re.sub(r"[^0-9A-Za-z]+", "_", arm_id(arm))
        print(f"\n--- proofload sweep --target registry:{target} ---")
        run_id = sweep(store, spec, f"registry:{target}", modules)
        rows = episodes(store, run_id)
        labels: dict[str, int] = {}
        for row in rows:
            label = str(row["outcome"])
            labels[label] = labels.get(label, 0) + 1
        print(f"  run_id   {run_id}")
        print(f"  episodes {len(rows)}  outcomes {labels}")
        for row in rows[:3]:
            meta = row["meta"]
            print(f"    seed {row['seed']:>10}  t={row['t']}  {row['outcome']:<10} "
                  f"arm {meta['arm_id']}  {meta['sampled_calls']} calls")
        print(f"    ... {len(rows) - 3} more")
        run_ids[arm_id(arm)] = run_id

    # `proofload diff` is how a knob is read: the same seeds under two arms. `--event` is
    # needed here because every episode passed, so there is no failure event for Proofload
    # to infer. The line worth reading is `truncated=0`: N17 is the claim that the
    # declared horizon cuts no arm of this registration short, and this is where it is
    # measured rather than asserted.
    print("\n--- proofload diff: depth:d1 against depth:d3 (head) ---")
    diff = subprocess.run(
        [sys.executable, "-m", "proofload", "--store", str(store), "diff",
         run_ids["depth:d1"], run_ids["depth:d3"], "--event", "passed"],
        capture_output=True, text=True, timeout=300,
    )
    if diff.returncode != 0:
        raise SystemExit(f"proofload diff exited {diff.returncode}\n{diff.stderr}")
    for line in diff.stdout.strip().splitlines()[:4]:
        print(f"  {line}")
    print("  ... (the full report is long; run the command yourself for all of it)")

    print(f"\nthe store is at {store}.")
    print(f"  proofload --store {store} inspect {run_ids['depth:d3']}")


if __name__ == "__main__":
    main()
