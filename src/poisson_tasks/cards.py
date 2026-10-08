"""The published cards: the calibration cards that ship with the package, by name.

A published card is named by its model's short name (`gpt-5-nano`, `qwen3-8b`), never by the
folder its records are kept in.  `recompute` rebuilds a card from its own records under the
provenance it recorded and says whether that gives the committed artifact byte for byte, and
whether the card is current for this install.  `tests/test_fd4_published.py` says what each name
does.

**Where the cards are.**  Inside the package, `poisson_tasks/cards/<folder>/`, once the packaging
module ships them there; until then the checkout's `calibration/` folder beside the package's
source, which is where the estimate reads them too.  An install with neither has no published
card: `published()` is empty, and nothing that reads the cards refuses on its account.

**A card's folder** holds `episodes.jsonl` (its records), `artifact.json` (the committed
artifact) and, when the run kept one, `tallies.json`: the instrument tally per arm id, which the
rebuild needs because a resume re-ran what failed and the records alone under-count.
"""

from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path

from poisson_tasks import calibration
from poisson_tasks.calibration import Artifact

__all__ = ["PublishedCard", "Recomputed", "TALLIES_FILE", "published", "recompute"]

TALLIES_FILE = "tallies.json"
"""A card folder's instrument tally, per arm id, when its run kept one."""

_DATED = re.compile(r"-\d{4}-\d{2}-\d{2}$")
"""A dated snapshot's suffix (`gpt-5-nano-2025-08-07`), which the short name drops."""


@dataclasses.dataclass(frozen=True)
class PublishedCard:
    """A published card: its short name and the folder that holds its records and artifact."""

    name: str
    folder: Path


@dataclasses.dataclass(frozen=True)
class Recomputed:
    """A published card recomputed: whether the rebuilt artifact is the committed one byte for
    byte, whether the card is current for this install, how many records it was rebuilt from,
    and the rebuilt artifact."""

    identical: bool
    current: bool
    records: int
    artifact: Artifact


def _root() -> Path:
    """Where the published cards are read from: inside the package once they ship there, and
    until then the checkout's `calibration/` folder beside the package's source."""
    package = Path(__file__).resolve().parent
    shipped = package / "cards"
    if shipped.is_dir():
        return shipped
    return package.parents[1] / "calibration"


def _short(model: str) -> str:
    """A model's short name: its id without a revision, an organisation prefix or a dated
    snapshot's suffix, in lower case.  `gpt-5-nano-2025-08-07` is `gpt-5-nano`; `Qwen/Qwen3-8B`
    is `qwen3-8b`."""
    name = model.split("@", 1)[0].rsplit("/", 1)[-1].lower()
    return _DATED.sub("", name) or name


def published(root: Path | None = None) -> tuple[PublishedCard, ...]:
    """Every published card, by its model's short name, from `root` or where the cards are
    read from by default.  Two cards whose models share a short name are refused in one line,
    since a name must say which card it is."""
    base = Path(root) if root is not None else _root()
    out: list[PublishedCard] = []
    for artifact in sorted(base.glob("*/artifact.json")):
        stored = json.loads(artifact.read_text(encoding="utf-8"))
        out.append(PublishedCard(name=_short(str(stored["provenance"]["models"][0]["id"])),
                                 folder=artifact.parent))
    names = [card.name for card in out]
    for name in sorted(set(names)):
        if names.count(name) > 1:
            folders = ", ".join(card.folder.name for card in out if card.name == name)
            raise ValueError(f"two published cards share the name {name!r}: {folders}")
    return tuple(out)


def recompute(card: PublishedCard) -> Recomputed:
    """`card` rebuilt from its records, under the provenance its `artifact.json` recorded and
    with its tally, and compared byte for byte with that file as `write_artifact` writes one.
    `current` reads the recorded generator hash against the package's.  A card whose files no
    longer give the same artifact is not identical; a cell its records now refuse (over a gate,
    or two models in one) is the rebuild's own `ValueError`."""
    folder = Path(card.folder)
    committed = (folder / "artifact.json").read_text(encoding="utf-8")
    stored = json.loads(committed)
    records = calibration.read_records(folder / calibration.RECORDS_FILE)
    cells: dict[tuple[str, str], list[calibration.EpisodeRecord]] = {}
    for record in records:
        cells.setdefault((record.arm_id, record.model), []).append(record)
    tallies_path = folder / TALLIES_FILE
    tallies = json.loads(tallies_path.read_text(encoding="utf-8")) if tallies_path.exists() else {}
    artifact = calibration.build_artifact(
        cells, calibration.Provenance(**stored["provenance"]),
        tally={key: dict(tallies.get(key[0], {})) for key in cells},
    )
    return Recomputed(
        identical=calibration._artifact_text(artifact) == committed,
        current=stored["provenance"]["generator_hash"] == calibration._package_generator_hash(),
        records=len(records),
        artifact=artifact,
    )
