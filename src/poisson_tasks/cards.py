"""The published cards: the calibration cards that ship with the package, by name.

A published card is named by its model's short name (`gpt-5-nano`, `qwen3-8b`), never by the
folder its records are kept in.  `recompute` rebuilds a card from its own records under the
provenance it recorded and says whether that gives the committed artifact byte for byte, and
whether the card is current for this install.  `tests/test_fd4_published.py` says what each name
does.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

from poisson_tasks.calibration import Artifact

__all__ = ["PublishedCard", "Recomputed", "published", "recompute"]


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


def published() -> tuple[PublishedCard, ...]:
    """Every published card."""
    raise NotImplementedError("FD4: cards.published")


def recompute(card: PublishedCard) -> Recomputed:
    """`card` rebuilt from its records."""
    raise NotImplementedError("FD4: cards.recompute")
