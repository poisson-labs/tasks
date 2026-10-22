"""What the similarity knob's test files share: the seeds they read, the base task they compare
with, and how a shown tool is read back.

The test files are `tests/test_k2_*.py`; each says in its own docstring what it pins and what it
decided.  Nothing here asserts anything.
"""

from __future__ import annotations

import hashlib
import re
from functools import lru_cache
from typing import Any

from poisson_tasks import calibration as cal
from poisson_tasks import surface
from poisson_tasks.arms import arm_from_id
from poisson_tasks.engine import EngineSpec
from poisson_tasks.tasks import TaskBundle, generate

SPEC = EngineSpec.load()
LEVELS = (0, 1, 2, 3)
WIDTH = 4
LOOKALIKE_LEDGERS = 6
B_ARM = "distractor:r0@k16"
NUMBER = re.compile(r"(?<!\d)\d{4}(?!\d)")
STAGES = tuple(SPEC.stage_names[:2])
SHOWN_STAGE = re.compile(
    rf"^{re.escape(str(SPEC.table['write_verb']))}_({'|'.join(STAGES)})_(\d{{{WIDTH}}})$"
)

CARD_SEEDS: tuple[int, ...] = cal.seed_list()


def _probe_seeds() -> tuple[int, ...]:
    """The probe's seeds as its design describes them, made the way the cards' are: seed `i` is the
    first four bytes of `sha256("poisson-tasks/knob-probe/seeds/v1:<i>")`, skipping a card seed or a
    repeat; the first three are phase 1's and the next sixty, sorted, the probe's.  The probe's own
    module (`knob_probe`) is where the derivation is fixed; these sixty-three are seeds a test can
    read now."""
    out: list[int] = []
    index = 0
    while len(out) < 63:
        digest = hashlib.sha256(f"poisson-tasks/knob-probe/seeds/v1:{index}".encode()).digest()
        seed = int.from_bytes(digest[:4], "big")
        if seed not in CARD_SEEDS and seed not in out:
            out.append(seed)
        index += 1
    return tuple(out[:3]) + tuple(sorted(out[3:]))


PROBE_SEEDS = _probe_seeds()
SEEDS = CARD_SEEDS + PROBE_SEEDS


def arm(level: int) -> str:
    return f"similarity:s{level}"


@lru_cache(maxsize=4096)
def made(arm_id: str, seed: int, split: str = "eval") -> TaskBundle:
    return generate(arm_from_id(arm_id, split=split), seed)


def sim(level: int, seed: int, split: str = "eval") -> TaskBundle:
    return made(arm(level), seed, split)


def base(seed: int, split: str = "eval") -> TaskBundle:
    """B, the base task the similarity block is made from: `distractor:r0@k16` at the seed."""
    return made(B_ARM, seed, split)


def names(bundle: Any) -> tuple[str, ...]:
    return tuple(str(tool["name"]) for tool in bundle.tools)


def engines(bundle: Any) -> tuple[str, ...]:
    """The engine tool each shown tool stands for, in slot order, as the verifier reads it."""
    shown = surface.display_map(bundle.seed, bundle.split, bundle.arm_id, bundle.goal,
                                names(bundle))
    return tuple(surface.engine_name(shown, name) for name in names(bundle))


def number_of(name: str) -> str | None:
    found = NUMBER.search(name)
    return None if found is None else found.group(0)


def target_number(bundle: Any) -> str:
    """The target ledger's number: the one the first reference call's tool carries."""
    number = number_of(str(bundle.reference_calls[0][0]))
    assert number is not None, bundle.reference_calls[0]
    return number


def ledger_of(engine: str) -> str:
    return str(SPEC.stage_tools[engine][1])


def stage_of(engine: str) -> int:
    return int(SPEC.stage_tools[engine][0])


def lookalike_slots(bundle: Any) -> list[int]:
    """The slots holding a stage tool of a ledger other than the target's."""
    cls = bundle.goal[0]
    return [slot for slot, engine in enumerate(engines(bundle))
            if engine in SPEC.stage_tools and ledger_of(engine) != cls]


def shared(a: str, b: str) -> int:
    return sum(x == y for x, y in zip(a, b, strict=True))
