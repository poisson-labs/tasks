"""Recompute a published calibration card from its per-episode records, and check it.

    python examples/calibration_card.py [DIR]
    python examples/calibration_card.py --page > docs/calibration.md

DIR is one model's folder under `calibration/`, and defaults to the first,
`calibration/gpt-5-nano-2025-08-07`; the other is `calibration/qwen3-8b-b968826d`.  A folder
holds the per-episode records the card was computed from (`episodes.jsonl`), the
machine-readable card (`artifact.json`) and, for a run that tallied instrument failures as they
happened, that tally (`tallies.json`).  This rebuilds the artifact from the records alone,
under the provenance block the run recorded, checks that it is byte-identical to the committed
one, says whether the card is current for the installed generator, and prints the rendered card.

`--page` instead rebuilds every committed card and prints the one page for all of them,
`docs/calibration.md`: where the models' difficulty orderings agree, then each card in full.

No model, no network, no Proofload.  Every published number is a function of the records and
the provenance, so nothing here needs the run to be repeated.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import tempfile
from typing import TYPE_CHECKING, Any, NoReturn

if TYPE_CHECKING:
    from poisson_tasks import calibration as cal

ROOT = pathlib.Path(__file__).resolve().parent.parent
CARDS = ROOT / "calibration"
CARD_FILES = ("artifact.json", "episodes.jsonl")


class Parser(argparse.ArgumentParser):
    """A command-line mistake is one line on stderr, and exit 2."""

    def error(self, message: str) -> NoReturn:
        self.exit(2, f"error: {message}\n")


def arguments() -> argparse.Namespace:
    parser = Parser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    which = parser.add_mutually_exclusive_group()
    which.add_argument("dir", metavar="DIR", nargs="?", type=pathlib.Path,
                       default=None,
                       help=f"one model's card folder (default: {shown(committed_cards()[0])})")
    which.add_argument("--page", action="store_true",
                       help="rebuild every committed card and print the one page for all of them")
    return parser.parse_args()


def shown(path: pathlib.Path) -> str:
    """A path as the user would type it from here: relative when it is under the current
    folder, in full otherwise."""
    try:
        return str(path.resolve().relative_to(pathlib.Path.cwd()))
    except ValueError:
        return str(path)


def committed_cards() -> list[pathlib.Path]:
    return sorted(f for f in CARDS.iterdir() if all((f / name).is_file() for name in CARD_FILES))


def rebuild(cal: Any, folder: pathlib.Path) -> tuple[cal.Artifact, int]:
    """A committed card rebuilt from its records under its recorded provenance, and how many
    records it has."""
    stored = json.loads((folder / "artifact.json").read_bytes())
    records = cal.read_records(folder / "episodes.jsonl")
    cells: dict[tuple[str, str], list[cal.EpisodeRecord]] = {}
    for record in records:
        cells.setdefault((record.arm_id, record.model), []).append(record)
    # The instrument failures tallied as they happened, per arm; a run with none has none.
    tallies_path = folder / "tallies.json"
    tallies = json.loads(tallies_path.read_text()) if tallies_path.exists() else {}
    built = cal.build_artifact(
        cells, cal.Provenance(**stored["provenance"]),
        tally={key: tallies.get(key[0], {}) for key in cells},
    )
    return built, len(records)


def main() -> None:
    args = arguments()
    if not args.page:
        folder = args.dir or committed_cards()[0]
        missing = [name for name in CARD_FILES if not (folder / name).is_file()]
        if missing:
            cards = " and ".join(shown(card) for card in committed_cards())
            sys.exit(f"error: {folder} is not a card folder (it has no "
                     f"{' and no '.join(missing)}); the committed cards are {cards}")

    # Imported here, after the command line is read: --help and a mistaken argument answer at
    # once, before the generator loads (loading it needs the tokenizer file).
    from poisson_tasks import calibration as cal
    from poisson_tasks.tasks import generate

    if args.page:
        sys.stdout.write(
            cal.render_combined_document([rebuild(cal, f)[0] for f in committed_cards()]))
        return

    committed = (folder / "artifact.json").read_bytes()
    provenance = cal.Provenance(**json.loads(committed)["provenance"])
    artifact, count = rebuild(cal, folder)
    cells = {(cell["arm_id"], cell["model"]) for cell in artifact.cells}

    with tempfile.TemporaryDirectory() as scratch:
        rebuilt = cal.write_artifact(artifact, pathlib.Path(scratch) / "artifact.json").read_bytes()

    print(cal.render_document(artifact))
    print(f"{count} records, {len(cells)} cells")
    if rebuilt != committed:
        sys.exit("the rebuilt artifact differs from the committed artifact.json")
    print("the rebuilt artifact is byte-identical to the committed artifact.json")
    # The installed generator's hash, read off a generated task (it is `tasks.py`'s own bytes).
    current = generate(cal.arm_specs()[0], cal.seed_list()[0]).generator_hash
    print("the card is current for this generator" if provenance.generator_hash == current
          else f"the card is STALE: it was measured at generator {provenance.generator_hash}, "
               f"and the installed generator is {current}")


if __name__ == "__main__":
    main()
