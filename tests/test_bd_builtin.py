"""The `baddata` tasks on the built-in ledger: one request at every level, the answers, the band, the
sequence, what the end state catches and the ledger's row, frozen as tests.

The invariants (the 0.4.0 stale-data spec, BD.2 to BD.5, BD.7 and BD.8).  At every level the request,
block, system prompt, scenario and goal are the same; the level is only what the first answer of one
named read holds.  Level 1 answers another catalogue item's word and the other record; level 2 the
request's item and the other record; level 3 the request's item and the first stage on the second
read; every later answer is true.  A payload is `<item word>/<head>.<hex>`, its fill drawn again until
the line holds N8's band at every number a reference can give it.  The *n*th call of a named read
answers its *n*th entry and the last from then on, counted per exact call.  Reads move no record, so
the end state is what catches an episode that trusted the first answer.

"At the card seeds" is the sixty published seeds on eval and twelve on train.

Shapes decided here
-------------------

**1. The goal stage is looked for outside the ladder and the quoted values.**  The request's own
example lists the whole ladder and quotes ids and items, whose words can be anything, so "no request
names the goal stage" is held on what is left.

**2. "Saying which" is held as the arm (ruled yes, 2026-11-04).**  N36's line is one line, and on the
three plants wrong at one level it names that level's arm id; a changed read is wrong between levels
and is held to one line.

**3. The bad and true payloads share nothing the test reads but what the spec says**: the test parses
item word, head and hex, and compares a named field, never two whole lines that differ in a drawn fill
(the brief's trap).
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from poisson_tasks import knobs
from poisson_tasks.arms import arm_from_id
from poisson_tasks.tasks import generate_contrast, scenario_for
from poisson_tasks.tokenizer import count_tokens
from tests.bd_support import (
    ABOVE_ZERO,
    BUILT_IN_SENTENCE,
    LEVELS,
    SPEC,
    TRUSTED,
    another_page,
    arm,
    bad_read,
    baddata,
    card_seeds,
    changed_reference,
    is_read,
    line_of,
    parts_of,
    payload_of,
    read_pairs,
    replayed,
    stage_calls_on,
    target_and_decoy,
    telling,
    the_two_reads,
    word_of,
)
from tests.k3_support import CARD_SEEDS, answers, base, made, names, right, seq, status, verdict_of
from tests.test_k3_plan import label_of, other_fields

ONE_TASK_MOVES = {"arm_id", "task_id", "pins", "reference_calls", "reference_observations",
                  "negative_controls"}
ITEM = SPEC.parameter_names["item"]
PAGE = SPEC.parameter_names["page"]
RECORD = SPEC.parameter_names["record"]


def request_items(bundle: Any) -> set[str]:
    first, second = the_two_reads(bundle)
    return {first[1][ITEM], second[1][ITEM]}


def contrast_of(*bundles: Any) -> Any:
    return knobs.check_pins({bundle.arm_id: bundle for bundle in bundles})


# --------------------------------------------------------------------------
# one request at every level (BD.2)
# --------------------------------------------------------------------------


def test_every_level_above_0_is_level_0_but_the_reference_and_the_controls() -> None:
    """At the card seeds: `other_fields` is each field the dataclass has, the prompt, the slots, the
    block, the system prompt, the scenario, the goal, the expected final state and the template id
    among those that do not move.  The system prompt is B's and the sentence on a line of its own,
    at every level, level 0 included; the goal is B's."""
    for split, seed in card_seeds():
        zero = baddata(0, seed, split)
        b = base(seed, split)
        assert zero.system_prompt == b.system_prompt + "\n" + BUILT_IN_SENTENCE, (split, seed)
        assert (zero.goal, zero.scenario_hash, zero.expected_final_state) == (
            b.goal, b.scenario_hash, b.expected_final_state)
        for level in ABOVE_ZERO:
            bundle = baddata(level, seed, split)
            assert other_fields(bundle, zero) == ONE_TASK_MOVES, (split, seed, level)
            assert bundle.prompt == zero.prompt and bundle.prompt_slots == zero.prompt_slots
            assert bundle.template_id == zero.template_id and bundle.tools == zero.tools


def test_no_request_names_the_goal_stage_or_which_record_and_each_names_both_records_and_reads() -> None:
    """Shape 1.  Each record id once and each read's item and page in the request; the entry code
    stated; outside the ladder's line and the quoted values no stage has a name."""
    stages = [str(name) for name in SPEC.stage_names]
    for split, seed in card_seeds():
        bundle = baddata(0, seed, split)
        prompt = bundle.prompt
        assert isinstance(prompt, str)
        target, decoy = target_and_decoy(bundle)
        assert prompt.count(target) == 1 and prompt.count(decoy) == 1, (split, seed)
        for _name, args in the_two_reads(bundle):
            assert args[ITEM] in prompt and args[PAGE] in prompt, (split, seed)
        first, _second = right(bundle)
        assert first[1][SPEC.parameter_names["entry"]] in prompt, (split, seed)
        left = re.sub(r'"[^"]*"', '""', prompt)
        lines = [text for text in left.splitlines() if " then ".join(stages) not in text]
        assert len(lines) == len(left.splitlines()) - 1, prompt
        for stage in stages:
            assert not re.search(rf"\b{stage}\b", "\n".join(lines)), (split, seed, stage)


def test_the_keyed_order_lists_the_target_first_on_a_quarter_to_three_quarters() -> None:
    first = total = 0
    for split, seed in card_seeds():
        bundle = baddata(0, seed, split)
        target, decoy = target_and_decoy(bundle)
        first += int(bundle.prompt.index(target) < bundle.prompt.index(decoy))
        total += 1
    assert total / 4 <= first <= total * 3 / 4, (first, total)


# --------------------------------------------------------------------------
# the answers (BD.3)
# --------------------------------------------------------------------------


def test_every_read_line_is_the_engines_layout_with_the_payloads_three_parts() -> None:
    """At every level and card seed, in the reference's order: `L_obs` bytes, status `ok`, numbered
    from `seq_start`, payload `<item word>/<head>.<hex>`; the reference is the reads and then B's two
    stage calls, 5 turns at level 0 and 6 above it."""
    for split, seed in card_seeds():
        for level in LEVELS:
            bundle = baddata(level, seed, split)
            assert list(bundle.reference_calls[-2:]) == list(right(bundle)), (split, seed, level)
            pairs = read_pairs(bundle)
            assert len(bundle.reference_calls) == len(pairs) + 2
            assert all(is_read(call) for call in bundle.reference_calls[: len(pairs)])
            assert len(pairs) == (2 if level == 0 else 3), (split, seed, level)
            for index, (_call, observation) in enumerate(pairs):
                assert len(observation.encode("ascii")) == SPEC.L_obs, observation
                assert status(observation) == "ok" and seq(observation) == bundle.seq_start + index
                parts_of(observation)
            assert arm_from_id(arm(level)).reference_turns == len(bundle.reference_calls) + 1


def test_level_0_answers_each_read_once_with_its_own_items_word_and_the_truth() -> None:
    for split, seed in card_seeds():
        bundle = baddata(0, seed, split)
        target, decoy = target_and_decoy(bundle)
        (first, first_line), (second, second_line) = read_pairs(bundle)
        assert parts_of(first_line)[:2] == (word_of(first[1][ITEM]), telling(target, decoy))
        assert parts_of(second_line)[:2] == (word_of(second[1][ITEM]), goal_stage(bundle))


def goal_stage(bundle: Any) -> str:
    return str(SPEC.stage_names[bundle.goal[2] - 1])


@pytest.mark.parametrize("level", ABOVE_ZERO)
def test_the_first_answer_holds_the_levels_bad_value_and_the_next_the_truth(level: int) -> None:
    """Level 1: the first read, a catalogue item the request does not name, the other record.
    Level 2: the first read, the request's item, the other record.  Level 3: the second read, the
    request's item, the first stage.  The bad read is made twice in a row; the other read's answer
    is level 0's."""
    for split, seed in card_seeds():
        bundle = baddata(level, seed, split)
        zero = baddata(0, seed, split)
        target, decoy = target_and_decoy(bundle)
        pairs = read_pairs(bundle)
        first_read, second_read = the_two_reads(bundle)
        bad_at = 0 if level < 3 else 1
        bad_call, bad_line = pairs[bad_at]
        again_call, again_line = pairs[bad_at + 1]
        assert bad_call == again_call == (first_read if level < 3 else second_read), (split, seed)
        true_head = telling(target, decoy) if level < 3 else goal_stage(bundle)
        own_word = word_of(bad_call[1][ITEM])
        word, head, _fill = parts_of(bad_line)
        if level == 1:
            words = {word_of(item) for item in SPEC.table["catalogue_items"]}
            assert word in words and word not in {word_of(i) for i in request_items(bundle)}, (
                split, seed, word)
        else:
            assert word == own_word, (split, seed, word)
        assert head == (telling(decoy, target) if level < 3 else str(SPEC.stage_names[0])), (
            split, seed, head)
        assert parts_of(again_line)[:2] == (own_word, true_head), (split, seed)
        other = read_pairs(zero)[1 if level < 3 else 0][1]
        kept = pairs[2 if level < 3 else 0][1]
        assert payload_of(kept) == payload_of(other), (split, seed)


def test_the_telling_words_tell_the_records_apart_where_they_share_a_first_word() -> None:
    """The 222-in-57,144 case: every seed up to where twelve such tasks are found on the eval split,
    whose heads then run to the words that differ, at every level that shows them."""
    found = 0
    seed = 0
    while found < 12:
        seed += 1
        scenario_records = {record for _ledger, record in scenario_for(seed, "eval").records}
        if len({word_of(record) for record in scenario_records}) > 1:
            continue
        found += 1
        bundle = baddata(0, seed)
        target, decoy = target_and_decoy(bundle)
        true_head = parts_of(read_pairs(bundle)[0][1])[1]
        assert true_head == telling(target, decoy), seed
        assert true_head.count("-") >= 1, (seed, true_head)
        bad_head = parts_of(read_pairs(baddata(2, seed))[0][1])[1]
        assert bad_head == telling(decoy, target) and bad_head != true_head, seed


# --------------------------------------------------------------------------
# the band (BD.4)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("split", ["eval", "train"])
def test_every_read_line_holds_the_band_at_every_number_over_a_thousand_seeds(split: str) -> None:
    """`generate_contrast` of the four levels never refuses, and each read payload at every level
    holds N8's band at each number from 1 to 5 a reference can give it.  The same head reads the same
    at every level: the true payloads are level 0's, so a redraw is not the level's."""
    low, high = SPEC.table["token_band"]
    arms = tuple(arm_from_id(arm(level), split=split) for level in LEVELS)
    for seed in range(1000):
        contrast = generate_contrast(arms, seed)
        zero = contrast[arm(0)]
        zero_payloads = {call[0]: payload_of(line) for call, line in read_pairs(zero)}
        for level in LEVELS:
            pairs = read_pairs(contrast[arm(level)])
            for _call, observation in pairs:
                for number in range(1, 6):
                    tokens = count_tokens(line_of(number, "ok", payload_of(observation)))
                    assert low <= tokens <= high, (split, seed, level, number, observation)
            last = {call[0]: payload_of(line) for call, line in pairs}
            assert last == zero_payloads, (split, seed, level)


# --------------------------------------------------------------------------
# the sequence (BD.5)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("level", LEVELS)
def test_the_nth_call_answers_the_nth_entry_and_the_last_from_then_on(level: int) -> None:
    """Through `apply_planned` at six card seeds: the bad read four times, then the other read; at
    level 0 the first read four times.  The counter advances on every call."""
    for seed in CARD_SEEDS[:6]:
        bundle = baddata(level, seed)
        first, second = the_two_reads(bundle)
        called = bad_read(bundle) if level else first
        other = second if called == first else first
        lines = replayed(bundle, [called] * 4 + [other])
        said = [payload_of(line) for line in lines]
        reference = [payload_of(line) for call, line in read_pairs(bundle) if call == called]
        assert said[:4] == (reference + [reference[-1]] * 4)[:4], (level, seed, said)
        assert len(set(said[:4])) == (2 if level else 1), (level, seed, said)
        assert said[4] == next(payload_of(line) for call, line in read_pairs(bundle)
                               if call == other)
        assert [seq(line) for line in lines] == list(range(bundle.seq_start, bundle.seq_start + 5))
        assert all(status(line) == "ok" for line in lines)


@pytest.mark.parametrize("level", ABOVE_ZERO)
def test_the_count_is_per_exact_call_so_another_call_neither_takes_nor_gets_the_bad_answer(
    level: int,
) -> None:
    """Another page, a key more, and another read tool with the same arguments each reach the engine
    and leave the named read's first answer its first; a call whose keys come in another order is
    the same call."""
    for seed in CARD_SEEDS[:6]:
        bundle = baddata(level, seed)
        name, args = bad_read(bundle)
        reference = [payload_of(line) for call, line in read_pairs(bundle) if call == (name, args)]
        outside = next(tool for tool in names(bundle)
                       if tool in SPEC.read_tools and tool not in {c[0] for c in the_two_reads(bundle)})
        others = [another_page((name, args)), (name, {**args, "extra": "x"}), (outside, args)]
        lines = replayed(bundle, [*others, (name, args), (name, args)])
        assert [payload_of(line) for line in lines[-2:]] == reference, (level, seed, lines)
        assert all(payload_of(line) not in reference for line in lines[:3]), (level, seed, lines)
        turned = dict(reversed(list(args.items())))
        same = replayed(bundle, [(name, turned), (name, args)])
        assert [payload_of(line) for line in same] == reference, (level, seed, same)


def test_a_call_the_harness_refuses_takes_none() -> None:
    """Through the tool server at `b2`: arguments that are not a JSON object and a tool the block does
    not show never reach it, so the first call that does answers the bad entry and the next the true
    one, numbered from `seq_start`."""
    for seed in CARD_SEEDS[:3]:
        bundle = baddata(2, seed)
        name, args = bad_read(bundle)
        outside = next(tool for tool in SPEC.stage_tools if tool not in names(bundle))
        calls = [(name, "{"), (name, "[]"), (outside, args), (name, args), (name, args)]
        sent = answers(bundle, calls)
        assert all(line.startswith("error: ") for line in sent[:3]), sent[:3]
        assert [payload_of(line) for line in sent[3:]] == [
            payload_of(line) for call, line in read_pairs(bundle) if call == (name, args)]
        assert [seq(line) for line in sent[3:]] == [bundle.seq_start, bundle.seq_start + 1]


def test_a_spread_arm_answers_each_named_read_as_it_did() -> None:
    """A spread read has one entry: called again it answers the same payload at the next number.
    A guard for spread beside the new sequence: `tests/test_k8b_kept.py`'s digests, read through the
    frozen file, hold the rest."""
    for seed in CARD_SEEDS[:3]:
        bundle = made("spread:p2", seed)
        for call, line in list(read_pairs(bundle))[:2]:
            again = replayed(bundle, [call, call])
            assert [payload_of(text) for text in again] == [payload_of(line), payload_of(line)]
            assert [seq(text) for text in again] == [bundle.seq_start, bundle.seq_start + 1]


# --------------------------------------------------------------------------
# what the end state catches (BD.7)
# --------------------------------------------------------------------------


def the_reads_once(bundle: Any) -> list[tuple[str, Any]]:
    return list(the_two_reads(bundle))


@pytest.mark.parametrize("level", LEVELS)
def test_the_reference_read_until_two_agree_and_one_read_more_all_pass(level: int) -> None:
    """By real `verify` at the card seeds, strict and leaky.  "Read until two in a row agree" is
    played on the answers, and stops within three reads of each read."""
    for split, seed in card_seeds():
        bundle = baddata(level, seed, split)
        stage = list(right(bundle))
        got = verdict_of(bundle, list(bundle.reference_calls))
        assert (got.strict_label, got.leaky_pass) == ("passed", True), (split, seed, got)
        reads = [call for call, _line in read_pairs(bundle)]
        more = verdict_of(bundle, [*reads, reads[0], *stage])
        assert (more.strict_label, more.leaky_pass) == ("passed", True), (split, seed, more)
        calls: list[tuple[str, Any]] = []
        for read in the_two_reads(bundle):
            last = None
            for _within_three in range(3):
                calls.append(read)
                said = payload_of(replayed(bundle, calls)[-1])
                if said == last:
                    break
                last = said
            assert said == last, (split, seed, calls)
        until = verdict_of(bundle, [*calls, *stage])
        assert (until.strict_label, until.leaky_pass) == ("passed", True), (split, seed, until)


@pytest.mark.parametrize("level", ABOVE_ZERO)
def test_trusting_the_first_answer_is_silent_and_wrong_state(level: int) -> None:
    """`wrong_state_trusted` is the reads once each and then what the bad answer asks for: at 1 and 2
    the stage calls on the other record, at 3 the first stage on the target.  Every answer says `ok`,
    so nothing but the end state tells: `wrong_state`, leaky false.  It is absent at level 0."""
    for split, seed in card_seeds():
        bundle = baddata(level, seed, split)
        target, decoy = target_and_decoy(bundle)
        trusted = list(bundle.negative_controls[TRUSTED])
        wanted = [*the_reads_once(bundle),
                  *(stage_calls_on(bundle, decoy) if level < 3 else stage_calls_on(bundle, target)[:1])]
        assert trusted == wanted, (split, seed)
        assert all(status(line) == "ok" for line in replayed(bundle, trusted)), (split, seed)
        got = verdict_of(bundle, trusted)
        assert (got.strict_label, got.leaky_pass) == ("wrong_state", False), (split, seed, got)
        assert TRUSTED not in baddata(0, seed, split).negative_controls


@pytest.mark.parametrize("level", [1, 2])
def test_acting_on_the_bad_record_and_then_the_right_one_is_collateral(level: int) -> None:
    """The bad write cannot be taken back: `collateral_mutation`, leaky true."""
    for split, seed in card_seeds():
        bundle = baddata(level, seed, split)
        target, decoy = target_and_decoy(bundle)
        calls = [*the_reads_once(bundle), *stage_calls_on(bundle, decoy),
                 *stage_calls_on(bundle, target)]
        got = verdict_of(bundle, calls)
        assert (got.strict_label, got.leaky_pass) == ("collateral_mutation", True), (split, seed, got)


def test_stopping_a_stage_short_reading_again_and_finishing_passes() -> None:
    for split, seed in card_seeds():
        bundle = baddata(3, seed, split)
        first, second = right(bundle)
        _record_read, stage_read = the_two_reads(bundle)
        calls = [*the_reads_once(bundle), first, stage_read, second]
        got = verdict_of(bundle, calls)
        assert (got.strict_label, got.leaky_pass) == ("passed", True), (split, seed, got)


@pytest.mark.parametrize("level", LEVELS)
def test_every_negative_control_earns_its_label(level: int) -> None:
    for split, seed in card_seeds():
        bundle = baddata(level, seed, split)
        for key, calls in bundle.negative_controls.items():
            label = label_of(key)
            got = (
                verdict_of(bundle, calls, reply=False, limit=True)
                if label == "turn_limit"
                else verdict_of(bundle, calls)
            )
            assert got.strict_label == label, (level, split, seed, key, got)


# --------------------------------------------------------------------------
# the ledger (BD.8)
# --------------------------------------------------------------------------


def test_n36_is_in_the_ledger_of_thirty_one_rows_and_n4_and_n36_apply_to_baddata() -> None:
    rows = {row.row_id: row for row in knobs.pin_ledger("baddata")}
    assert len(rows) == 31 and "N36" in rows
    assert rows["N36"].applies_to == ("baddata",)
    assert "baddata" in rows["N4"].applies_to
    assert [row.row_id for row in knobs.pin_ledger("baddata")][-1] == "N36"


def test_the_ledger_refuses_nothing_over_the_four_levels_at_the_card_seeds() -> None:
    for split, seed in card_seeds():
        report = contrast_of(*(baddata(level, seed, split) for level in LEVELS))
        assert not report.refused and report.violations == (), (split, seed, report.violations)


def plants(level_two: Any, level_zero: Any) -> dict[str, Any]:
    """Each plant: the bundle that replaces its level's in the contrast."""
    first, second = the_two_reads(level_two)
    pairs = read_pairs(level_two)
    bad, true = payload_of(pairs[0][1]), payload_of(pairs[1][1])
    stage = payload_of(pairs[2][1])
    other_stage = stage.replace(str(SPEC.stage_names[1]), str(SPEC.stage_names[0]))
    moved = another_page(second)
    return {
        "a second bad read": changed_reference(level_two, [first, first, second, second],
                                               [bad, true, other_stage, stage]),
        "a bad answer at level 0": changed_reference(level_zero, [first, first, second],
                                                     [bad, true, stage]),
        "a bad, bad pair": changed_reference(level_two, [first, first, second], [bad, bad, stage]),
        "a changed read at one level": changed_reference(level_two, [first, first, moved],
                                                         [bad, true, stage]),
    }


@pytest.mark.parametrize("plant", ["a second bad read", "a bad answer at level 0", "a bad, bad pair",
                                   "a changed read at one level"])
def test_n36_refuses_each_plant_in_a_line_saying_which(plant: str) -> None:
    """Shape 2, at six card seeds; the contrast without the plant is held refused by nothing above."""
    for seed in CARD_SEEDS[:6]:
        bundles = {level: baddata(level, seed) for level in LEVELS}
        bundles[0 if plant == "a bad answer at level 0" else 2] = plants(bundles[2], bundles[0])[plant]
        report = contrast_of(*bundles.values())
        said = dict(report.violations)
        assert "N36" in said, (plant, seed, report.violations)
        assert "\n" not in said["N36"], said["N36"]
        named = {"a second bad read": "baddata:b2", "a bad answer at level 0": "baddata:b0",
                 "a bad, bad pair": "baddata:b2"}.get(plant)
        if named is not None:
            assert named in said["N36"], (plant, said["N36"])


def test_the_two_reads_are_the_same_at_every_level_each_with_its_own_item() -> None:
    """Each names its own catalogue item, in the block's read tools, and no record."""
    for split, seed in card_seeds():
        zero = baddata(0, seed, split)
        first, second = the_two_reads(zero)
        assert first[1][ITEM] != second[1][ITEM], (split, seed)
        assert first[0] in names(zero) and second[0] in names(zero)
        assert RECORD not in first[1] and RECORD not in second[1]
        for level in ABOVE_ZERO:
            assert the_two_reads(baddata(level, seed, split)) == (first, second), (split, seed, level)
