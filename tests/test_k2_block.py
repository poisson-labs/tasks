"""The similarity knob's tasks: the draws, the lookalike distance, the block, its length and the
prompt, frozen as tests.

The invariants are K2.1 to K2.5 of the knobs plan, from spec §5.  A similarity task is the base
task B (`distractor:r0@k16`, chain depth 2 on a sixteen-tool block holding no stage above the
goal) with twelve of B's reads swapped for lookalikes: the first two stage tools of six other
ledgers.  Every ledger is named by a four-digit number carried in its tools' names and
descriptions, and the prompt names the target ledger by its number.  At level S every lookalike
ledger's number shares exactly S digits in place with the target's.

Shapes decided here
-------------------

**1. A shown stage tool is named `submit_<stage>_<number>`**, the engine's name with the ledger's
class word replaced by its number, as spec §5.1 writes `submit_review_4417`; its description names
the ledger by number and the second stage's names the first stage's shown name (spec §5.4).  Its
parameters are the engine tool's.  The two reads keep their engine names and descriptions and
carry no number.  The descriptions' words are not pinned: what is pinned is that the seven tools
of one stage are identical but for their number, which is spec §5.1's "descriptions identical but
for the number", and which leaves no class word anywhere a lookalike could differ by.

**2. Which reads stay, and where the lookalikes go.**  Spec §3.1 says the block "swaps twelve
reads for lookalikes" from B's and §5.3 that the slot order is fixed across levels; it does not
say which two reads stay or which lookalike takes which slot.  Decided: **the right tools keep
B's slots; the two reads B holds in its first two read slots, in slot order, stay where they are;
every later read slot takes the next lookalike, each lookalike ledger's first stage tool then its
second, the ledgers in their drawn order.**  Why: it is the swap §3.1 describes with no draw of its
own (the spec lists the draws, and which reads stay is not among them), the two reads still vary
with the seed through B's slot order, and the census (`tests/test_k2_fingerprint.py`) can then be
stated exactly.

**3. The prompt is B's with "of the {class} ledger" replaced by "of ledger {number}"**, and its
slots B's with `ledger_class` replaced by `ledger_number` in the same place: spec §5.4's
`ledger-number/v1`, "sentence for sentence", "the five slots stay".  Pinned that exactly, it also
holds the rule `tasks._check_template_words` asserts at import (no word of the template's own
carries a read tool's or a ledger's token): B's template passes it, and the change adds a number.

**4. The draws are read through the verifier's own map.**  Which engine tool a shown name stands
for is `surface.display_map`'s answer, called as the verifier and the tool server call it, with
the bundle's shown names.  How generation asks the map for the shown names is left to the build.

**5. The seeds.**  "Every seed of the card's seed list and the probe's" (K2.4): the card's sixty,
and sixty-three made as spec §9.2 describes the probe's (`tests/k2_support.py`), since the probe's
own derivation is K9's.  Beside them, one test holds the block's length for every four-digit
number in every place a number is shown, which is what "every seed" rests on.

**6. "Through their own PRF domains" is checked by what it protects**: the scenario and B's slot
order are unchanged (`scenario_hash` equal to B's, the right tools in B's slots, and the published
tasks' content, K1.1, in `tests/test_k1_content.py`).  A draw taken from the structure domain's
unused digits would be statistically independent of the scenario and is not observable; it is
named in the mutation table.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from typing import Any

import pytest

from poisson_tasks.tokenizer import count_tokens, reference_encoding
from tests.k2_support import (
    CARD_SEEDS,
    LEVELS,
    LOOKALIKE_LEDGERS,
    SEEDS,
    SHOWN_STAGE,
    SPEC,
    WIDTH,
    base,
    engines,
    ledger_of,
    lookalike_slots,
    names,
    number_of,
    shared,
    sim,
    stage_of,
    target_number,
)


def rendered(bundle: Any) -> str:
    return json.dumps(list(bundle.tools), sort_keys=True, separators=(",", ":"))


def engine_schema(engine: str) -> dict[str, Any]:
    """The engine tool's parameters as every generated block renders them."""
    tool = next(t for t in SPEC.tools if t.name == engine)
    keys = sorted(tool.parameters)
    return {"type": "object",
            "properties": {k: {"type": tool.parameters[k]} for k in keys},
            "required": keys, "additionalProperties": False}


# --------------------------------------------------------------------------
# K2.1 the draws
# --------------------------------------------------------------------------


def test_the_draws_come_from_the_seed_and_split_and_are_the_same_at_every_level() -> None:
    """Across the four levels of one seed: the scenario, the target ledger and its number, the
    engine tool behind every slot (so the six lookalike ledgers and the slot order) are one;
    and the scenario is B's.  Across splits the draws differ, so they are taken from the split
    as well as the seed."""
    for seed in SEEDS:
        made = [sim(level, seed) for level in LEVELS]
        b = base(seed)
        assert {m.scenario_hash for m in made} == {b.scenario_hash}, seed
        assert len({engines(m) for m in made}) == 1, seed
        assert len({target_number(m) for m in made}) == 1, seed
        assert {m.goal for m in made} == {b.goal}, seed
    eval_draws = [(target_number(sim(3, s)), engines(sim(3, s))) for s in CARD_SEEDS[:30]]
    train_draws = [(target_number(sim(3, s, "train")), engines(sim(3, s, "train")))
                   for s in CARD_SEEDS[:30]]
    assert [d[0] for d in eval_draws] != [d[0] for d in train_draws]
    assert [d[1] for d in eval_draws] != [d[1] for d in train_draws]


def test_a_task_is_the_same_in_another_process_and_under_another_hash_seed() -> None:
    """G1 for the new draws: nothing in them reads the process, the clock or Python's hash."""
    seed = CARD_SEEDS[7]
    here = {level: sim(level, seed).task_id for level in LEVELS}
    code = ("import json; from poisson_tasks.arms import arm_from_id; "
            "from poisson_tasks.tasks import generate; "
            f"print(json.dumps({{l: generate(arm_from_id(f'similarity:s{{l}}'), {seed}).task_id "
            f"for l in {LEVELS!r}}}))")
    for hash_seed in ("0", "4242"):
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                             check=True, env={"PYTHONHASHSEED": hash_seed, "PATH": ""})
        assert {int(k): v for k, v in json.loads(out.stdout).items()} == here


@pytest.fixture(scope="module")
def spread_sample() -> dict[str, Any]:
    """Three hundred and twenty-three eval seeds at s0, s1 and s3: the draws' spread."""
    seeds = SEEDS + tuple(range(200))
    out: dict[str, Any] = {"targets": [], "kept": {1: Counter(), 3: Counter()},
                           "digits": Counter(), "lookalike": Counter(), "eligible": Counter()}
    for seed in seeds:
        for level in (0, 1, 3):
            bundle = sim(level, seed)
            target = target_number(bundle)
            numbers = lookalike_numbers(bundle)
            if level == 0:
                out["targets"].append(target)
                for number in numbers:
                    for place, digit in enumerate(number):
                        out["digits"][(place, digit)] += 1
                ledgers = {ledger_of(engines(bundle)[s]) for s in lookalike_slots(bundle)}
                for cls in SPEC.qualifiers:
                    if cls != bundle.goal[0]:
                        out["eligible"][cls] += 1
                        out["lookalike"][cls] += cls in ledgers
            else:
                for number in numbers:
                    for place in range(WIDTH):
                        if (number[place] == target[place]) == (level == 1):
                            out["kept"][level][place] += 1
    return out


def lookalike_numbers(bundle: Any) -> list[str]:
    """Each lookalike ledger's number, once per ledger, in slot order."""
    out: list[str] = []
    for slot in lookalike_slots(bundle):
        number = number_of(names(bundle)[slot])
        assert number is not None
        if number not in out:
            out.append(number)
    return out


def test_the_draws_cover_their_ranges_evenly(spread_sample: dict[str, Any]) -> None:
    """The target's number, the lookalike ledgers, the places kept and the digits changed are
    drawn, not fixed: every first digit 1 to 9 opens some target's number and none opens with 0;
    each other ledger is a lookalike in about six of eleven tasks; at s1 the one place kept, and
    at s3 the one place changed, falls evenly on the four (spec §5.3: "changed places are drawn
    uniformly"); and at s0 every digit a place can change to is drawn there."""
    targets = spread_sample["targets"]
    assert len(set(targets)) > 0.9 * len(targets)
    assert {t[0] for t in targets} == set("123456789")
    for cls, eligible in spread_sample["eligible"].items():
        share = spread_sample["lookalike"][cls] / eligible
        assert 6 / 11 - 0.15 < share < 6 / 11 + 0.15, (cls, share)
    for level in (1, 3):
        counts = spread_sample["kept"][level]
        total = sum(counts.values())
        assert set(counts) == set(range(WIDTH)), counts
        for place in range(WIDTH):
            assert 0.75 * total / WIDTH < counts[place] < 1.25 * total / WIDTH, (level, counts)
    digits = spread_sample["digits"]
    for place in range(WIDTH):
        drawn = {digit for (p, digit), _n in digits.items() if p == place}
        assert drawn == set("0123456789") - ({"0"} if place == 0 else set()), (place, drawn)


# --------------------------------------------------------------------------
# K2.2 distance
# --------------------------------------------------------------------------


def test_every_lookalike_ledger_shares_exactly_the_levels_digits_in_place() -> None:
    """At level S each of the six lookalike ledgers' numbers shares exactly S digits in place
    with the target's, so each changed digit differs from the target's there; the seven numbers
    are distinct; none opens with 0 (N21).  A ledger's two tools carry its one number, and a
    lookalike carries no number but its ledger's."""
    for seed in SEEDS:
        for level in LEVELS:
            bundle = sim(level, seed)
            target = target_number(bundle)
            by_ledger: dict[str, set[str]] = {}
            for slot in lookalike_slots(bundle):
                number = number_of(names(bundle)[slot])
                assert number is not None, (seed, level, names(bundle)[slot])
                by_ledger.setdefault(ledger_of(engines(bundle)[slot]), set()).add(number)
            assert len(by_ledger) == LOOKALIKE_LEDGERS, (seed, level)
            assert all(len(numbers) == 1 for numbers in by_ledger.values()), (seed, by_ledger)
            numbers = [target] + [next(iter(n)) for n in by_ledger.values()]
            assert len(set(numbers)) == LOOKALIKE_LEDGERS + 1, (seed, level, numbers)
            assert all(len(n) == WIDTH and n[0] != "0" for n in numbers), numbers
            assert [shared(n, target) for n in numbers[1:]] == [level] * LOOKALIKE_LEDGERS, (
                seed, level, target, numbers)


# --------------------------------------------------------------------------
# K2.3 the block
# --------------------------------------------------------------------------


def test_the_block_is_bs_with_twelve_reads_swapped_for_lookalikes() -> None:
    """Shape 2: the right tools in B's slots under the target's number; the reads in B's first
    two read slots unchanged; in every later read slot of B, in slot order, the next lookalike,
    each ledger's first stage then its second.  Sixteen tools, twelve lookalikes from six
    ledgers, two reads that carry no number, at every level (N19)."""
    for seed in CARD_SEEDS:
        b = base(seed)
        cls = b.goal[0]
        read_slots = [s for s, n in enumerate(names(b)) if n in SPEC.read_tools]
        for level in LEVELS:
            bundle = sim(level, seed)
            target = target_number(bundle)
            shown, behind = names(bundle), engines(bundle)
            assert len(shown) == len(names(b)) == 16
            for slot, b_name in enumerate(names(b)):
                if b_name in SPEC.stage_tools:
                    assert behind[slot] == b_name, (seed, level, slot)
                    assert SHOWN_STAGE.match(shown[slot]), shown[slot]
                    assert number_of(shown[slot]) == target
            for slot in read_slots[:2]:
                assert bundle.tools[slot] == b.tools[slot], (seed, level, slot)
                assert number_of(json.dumps(bundle.tools[slot])) is None
            later = read_slots[2:]
            assert lookalike_slots(bundle) == later, (seed, level)
            ledgers = [ledger_of(behind[s]) for s in later]
            assert [stage_of(behind[s]) for s in later] == [0, 1] * LOOKALIKE_LEDGERS
            assert ledgers[0::2] == ledgers[1::2], ledgers
            assert len(set(ledgers)) == LOOKALIKE_LEDGERS and cls not in ledgers
            assert bundle.pins.values["N19"] == 12


def test_the_tools_of_one_stage_are_identical_but_for_their_number() -> None:
    """Spec §5.1: the seven first-stage tools are one tool but for the number, and so are the
    seven second-stage ones.  So no class word, and nothing else a lookalike could differ by,
    is in any of them.  Each description names its own ledger's number; the second stage's names
    its own ledger's first stage by its shown name; parameters are the engine tool's; and no
    shown name or description carries an engine stage tool's name."""
    for seed in CARD_SEEDS[:20]:
        for level in LEVELS:
            bundle = sim(level, seed)
            behind = engines(bundle)
            stage_tools = [(slot, tool) for slot, tool in enumerate(bundle.tools)
                           if behind[slot] in SPEC.stage_tools]
            assert len(stage_tools) == 14
            first_shown = {ledger_of(behind[s]): t["name"] for s, t in stage_tools
                           if stage_of(behind[s]) == 0}
            masked: dict[int, set[str]] = {0: set(), 1: set()}
            for slot, tool in stage_tools:
                number = number_of(tool["name"])
                assert number is not None
                text = json.dumps(tool, sort_keys=True)
                assert number in tool["description"], tool
                assert tool["parameters"] == engine_schema(behind[slot]), tool
                if stage_of(behind[slot]) == 1:
                    assert first_shown[ledger_of(behind[slot])] in tool["description"], tool
                assert not any(engine in text for engine in SPEC.stage_tools), tool
                assert not any(cls in text for cls in SPEC.qualifiers), tool
                masked[stage_of(behind[slot])].add(text.replace(number, "NNNN"))
            assert len(masked[0]) == len(masked[1]) == 1, (seed, level, masked)


# --------------------------------------------------------------------------
# K2.4 length
# --------------------------------------------------------------------------


def test_the_blocks_length_is_equal_across_the_levels_at_every_seed() -> None:
    """N20 at every seed of the card's list and the probe's: the block's reference-token count
    is one number across the four levels."""
    for seed in SEEDS:
        counts = {count_tokens(rendered(sim(level, seed))) for level in LEVELS}
        assert len(counts) == 1, (seed, counts)
        assert {sim(level, seed).pins.values["N20"] for level in LEVELS} == counts


def test_any_ledger_number_shows_at_the_same_length() -> None:
    """What "equal at every seed" rests on (spec §5.3): every four-digit number with a non-zero
    first digit tokenizes to the same count wherever the block shows a number.  The block of one
    task, with one lookalike ledger's number, and then the target's, replaced by each of the
    9,000 in turn, renders to one count."""
    bundle = sim(0, CARD_SEEDS[0])
    text = rendered(bundle)
    target = target_number(bundle)
    lookalike = number_of(names(bundle)[lookalike_slots(bundle)[0]])
    assert lookalike is not None
    encoding = reference_encoding()
    for number in (target, lookalike):
        assert text.count(number) >= 4, (number, text.count(number))
        head, *rest = text.split(number)
        counts = {len(encoding.encode_ordinary(f"{n:04d}".join([head, *rest])))
                  for n in range(1000, 10000)}
        assert len(counts) == 1, (number, sorted(counts)[:5])


# --------------------------------------------------------------------------
# K2.5 the prompt
# --------------------------------------------------------------------------


def test_the_prompt_is_the_chain_template_naming_the_ledger_by_number() -> None:
    """`ledger-number/v1`: B's instruction with the ledger named by number, sentence for
    sentence, and B's slots with the class slot replaced by the number slot in its place; equal
    across the levels.  The system prompt is B's."""
    for seed in SEEDS:
        b = base(seed)
        cls = b.goal[0]
        phrase = f"of the {cls} ledger"
        assert isinstance(b.prompt, str) and b.prompt.count(phrase) == 1
        for level in LEVELS:
            bundle = sim(level, seed)
            number = target_number(bundle)
            assert bundle.template_id == "ledger-number/v1"
            assert bundle.prompt == b.prompt.replace(phrase, f"of ledger {number}"), seed
            assert bundle.prompt_slots == tuple(
                ("ledger_number", number) if key == "ledger_class" else (key, value)
                for key, value in b.prompt_slots)
            assert bundle.system_prompt == b.system_prompt
