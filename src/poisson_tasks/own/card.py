"""The card on a user's own tools: its first lines, beside a published card, each level against
the first, and the set's own near-duplicates (spec §6.3, §9).

An own-tools card is never pooled with a published card: `beside_published` prints the two
documents whole under the line `DIFFERENT_TASKS`, and refuses a published card of another
model.  On own tools each knob is read against its first level (knobs spec §11.2), every knob
on strict pass@1 (yes/no 29: a user's write has no stage past its goal, so there is no
overshoot and what leaky accepts is collateral); a pair saturated on the same side is excluded,
with no delta.  A knob "made your tasks harder" when a level is called different from the first
under the two-clause rule with a lower rate (yes/no 30).  The near-duplicate census reports the
closest pair of names by edit distance over the longer length and the closest pair of
descriptions by one less the share of words in common, descriptively (yes/no 31).
`tests/test_o2_card.py` pins this.
"""

from __future__ import annotations

import re as _re
from collections.abc import Mapping as _Mapping
from collections.abc import Sequence as _Sequence
from dataclasses import dataclass as _dataclass
from typing import Any as _Any

from poisson_tasks import calibration as _cal
from poisson_tasks.arms import arm_from_id as _arm_from_id
from poisson_tasks.own.generator import GENERATOR_VERSION as _GENERATOR_VERSION
from poisson_tasks.own.generator import KNOBS as _KNOBS

__all__ = [
    "DIFFERENT_TASKS",
    "first_lines",
    "beside_published",
    "AgainstFirst",
    "against_first",
    "bite",
    "near_duplicates",
    "EXCLUDED",
    "PREDICATE",
    "rows_from_artifact",
]

DIFFERENT_TASKS = "different tasks: read each card on its own"
EXCLUDED = "excluded"
PREDICATE = "strict"
_FORMAT_WORDS = {
    "openai": "an OpenAI tools file",
    "mcp": "an MCP tool list",
    "openapi": "an OpenAPI document",
}
_WORD = _re.compile(r"[a-z0-9]+")


@_dataclass(frozen=True)
class AgainstFirst:
    """One level of a knob read against the knob's first level."""

    knob: str
    level: int
    first: int
    predicate: str
    delta: float | None
    low: float | None
    high: float | None
    verdict: str


def first_lines(tools: _Mapping[str, _Any]) -> str:
    """Spec §9's first lines, from the own-tools provenance kind."""
    count = int(tools["tools"])
    words = _FORMAT_WORDS.get(str(tools["source_format"]), "a tool file")
    return (
        f"Measured on your tools ({tools['name']}, {count} tool{'' if count == 1 else 's'} from"
        f" {words}), with responses simulated from your schemas. Your backend was never called."
    )


def _models(artifact: _Any) -> set[str]:
    return {_cal._bare(str(cell["model"])) for cell in artifact.cells}


def beside_published(own: _Any, published: _Any) -> str:
    """The own card and the published card of its model, each on its own."""
    mine, theirs = _models(own), _models(published)
    if mine != theirs:
        raise ValueError(
            "the published card is another model's: this card is "
            + ", ".join(sorted(mine)) + " and the published one " + ", ".join(sorted(theirs))
        )
    return "\n".join([
        "# Your card and the published card",
        "",
        f"## {DIFFERENT_TASKS}",
        "",
        "## Your tools",
        "",
        _cal.render_document(own, claims=True),
        "## The published card",
        "",
        _cal.render_document(published),
    ])


def _spec(arm: str) -> _Any:
    try:
        return _arm_from_id(arm, generator_version=_GENERATOR_VERSION)
    except ValueError:
        return None


def against_first(
    cells: _Mapping[tuple[str, str], _Sequence[_Any]], provenance: _Any
) -> tuple[AgainstFirst, ...]:
    """Each knob's levels against its first level: the paired delta on strict pass@1, called
    under the two-clause rule, or excluded when both levels are saturated on the same side."""
    rows: list[AgainstFirst] = []
    for model in sorted({model for _, model in cells}):
        by_knob: dict[str, list[tuple[int, str]]] = {}
        for arm, who in cells:
            if who != model:
                continue
            spec = _spec(arm)
            if spec is None or spec.control is not None or spec.knob not in _KNOBS:
                continue
            by_knob.setdefault(spec.knob, []).append((spec.level, arm))
        for knob in _KNOBS:
            levels = sorted(by_knob.get(knob, []))
            if len(levels) < 2:
                continue
            first_level, first_arm = levels[0]
            first = _cal.scored(cells[(first_arm, model)])
            for level, arm in levels[1:]:
                cell = _cal.scored(cells[(arm, model)])
                rate, base = _cal.pass_at_1(cell), _cal.pass_at_1(first)
                high = provenance.saturation_high
                low = provenance.saturation_low
                if (rate >= high and base >= high) or (rate <= low and base <= low):
                    rows.append(AgainstFirst(knob, level, first_level, PREDICATE, None, None,
                                             None, EXCLUDED))
                    continue
                delta = _cal.paired_delta(
                    cell, first, resamples=provenance.bootstrap_resamples,
                    seed=provenance.bootstrap_seed, predicate=PREDICATE,
                )
                rows.append(AgainstFirst(knob, level, first_level, PREDICATE, delta.point,
                                         delta.low, delta.high, _cal.call_pair(delta, provenance)))
    return tuple(rows)


def rows_from_artifact(artifact: _Any) -> tuple[AgainstFirst, ...]:
    """The rows an own-tools artifact's `pairs` hold, as `against_first` gives them."""
    return tuple(
        AgainstFirst(str(pair["knob"]), int(pair["level_a"]), int(pair["level_b"]),
                     str(pair.get("predicate", PREDICATE)), pair["delta"], pair["low"],
                     pair["high"], str(pair["verdict"]))
        for pair in artifact.pairs
    )


def bite(rows: _Sequence[AgainstFirst]) -> dict[str, str]:
    """Per knob, whether it made the tasks harder, in one line."""
    out: dict[str, str] = {}
    for knob in _KNOBS:
        mine = [row for row in rows if row.knob == knob]
        if not mine:
            continue
        harder = [row for row in mine if row.verdict == _cal.DISTINGUISHABLE
                  and row.delta is not None and row.delta < 0]
        if harder:
            levels = ", ".join(str(row.level) for row in harder)
            plural = "" if len(harder) == 1 else "s"
            out[knob] = (
                f"{knob} made your tasks harder for this model: level{plural} {levels} read"
                f" lower than level {mine[0].first} under the two-clause rule."
            )
        else:
            out[knob] = (
                f"{knob} did not show that it made your tasks harder for this model at this"
                " sample size: no level read lower than the first under the two-clause rule."
            )
    return out


def _edit_distance(a: str, b: str) -> int:
    previous = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        current = [i]
        for j, y in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1,
                               previous[j - 1] + (x != y)))
        previous = current
    return previous[-1]


def _words(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


def near_duplicates(toolset: _Any) -> dict[str, _Any]:
    """The set's own closest pairs by name and by description: `(distance, first, second)`,
    the first pair in the file's order on a tie."""
    tools = list(toolset.tools)
    best_name: tuple[float, str, str] | None = None
    best_description: tuple[float, str, str] | None = None
    for i, a in enumerate(tools):
        for b in tools[i + 1:]:
            longer = max(len(a.name), len(b.name))
            name_distance = _edit_distance(a.name, b.name) / longer if longer else 0.0
            if best_name is None or name_distance < best_name[0]:
                best_name = (name_distance, a.name, b.name)
            mine, theirs = _words(a.description), _words(b.description)
            union = mine | theirs
            share = len(mine & theirs) / len(union) if union else 1.0
            description_distance = 1.0 - share
            if best_description is None or description_distance < best_description[0]:
                best_description = (description_distance, a.name, b.name)
    return {"name": best_name, "description": best_description}
