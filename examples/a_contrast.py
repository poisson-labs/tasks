"""Build the arms of one knob and run the pin ledger over them.

    python examples/a_contrast.py

A knob is only worth sweeping if the arms it produces differ in the one thing it names
and in nothing else. The pin ledger is what says so: every row is an equality *across*
the arms of a contrast, measured on the generated bundles, and a row that fails refuses
the contrast before any model runs.

No model, no network, no Proofload.
"""

from __future__ import annotations

import argparse
from typing import NoReturn

SEED = 404
GEN = "0"  # the generator version the published cards were measured at


class Parser(argparse.ArgumentParser):
    """A command-line mistake is one line on stderr, and exit 2."""

    def error(self, message: str) -> NoReturn:
        self.exit(2, f"error: {message}\n")


def main() -> None:
    # It takes no arguments; this gives it --help and refuses anything else.
    Parser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()

    # Imported here, after the command line is read: --help and a mistaken argument answer at
    # once, before the generator loads (loading it needs the tokenizer file).
    from poisson_tasks.knobs import ArmSpec, arm_id, check_pins, levels, pin_ledger
    from poisson_tasks.tasks import generate

    def spec(knob: str, level: int, control: int | None = None) -> ArmSpec:
        return ArmSpec(knob, level, control, "strict", "eval", GEN)

    def show(knob: str, arms: list[ArmSpec]) -> None:
        bundles = {arm_id(a): generate(a, SEED) for a in arms}
        report = check_pins(bundles)

        print(f"\n=== {knob}: {', '.join(bundles)} at seed {SEED} ===")
        print(f"  refused: {report.refused}")
        for row_id, detail in report.violations:
            print(f"  VIOLATION {row_id}: {detail}")
        for row_id, detail in report.reported:
            print(f"  reported  {row_id}: {detail}")

        rows = {row.row_id: row for row in pin_ledger(knob)}
        one = report.records[next(iter(bundles))]
        print(f"  rows measured from a bundle: {', '.join(sorted(one.values))}")
        for row_id, why in sorted(one.unmeasured.items()):
            print(f"  {row_id} is not measurable here -- {rows[row_id].stage}:")
            print(f"      {why[:96]}...")

    print(f"depth levels      {levels('depth')}")
    print(f"distractor levels {levels('distractor')}")

    # The depth knob: how many chained stage calls the task needs. Its control arm is a
    # low-depth arm whose prompt is *seeded* with the history a high arm would have
    # produced, so the episode is as long as the high arm's without being as deep.
    show("depth", [spec("depth", 1), spec("depth", 3), spec("depth", 8),
                   spec("depth", 1, control=8)])

    # The distractor knob: how many irrelevant tools sit in the block. Every arm needs
    # the same number of calls, so a difference in outcome is a difference in selection.
    show("distractor", [spec("distractor", lvl) for lvl in levels("distractor")])

    # What a refusal looks like. N1 holds the scenario equal across a contrast's arms,
    # so two arms generated from *different* seeds are not a contrast at all.
    print("\n=== what a refused contrast looks like: two arms, two seeds ===")
    a, b = spec("depth", 1), spec("depth", 3)
    mixed = {arm_id(a): generate(a, SEED), arm_id(b): generate(b, SEED + 1)}
    report = check_pins(mixed)
    print(f"  refused: {report.refused}")
    for row_id, detail in report.violations:
        print(f"  VIOLATION {row_id}: {detail}")


if __name__ == "__main__":
    main()
