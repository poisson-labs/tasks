"""Checks from 0.3.0 that could be weakened without a test failing (issue #38).

Each of these held in 0.3.0 by the code and by no test: a change that broke it left the suite green.
Each test here passes on the code and fails on the change it is written against; the message of the
commit that added it names that change and the result.  None of the changes is committed.

- **FX38.1** a second write to the same tool with other arguments the schema accepts is not a
  duplicate write.  `duplicate_write` is an accepted write equal to an earlier one, tool and
  arguments both; keyed on the tool alone, any two writes to a tool read as one write made twice.
  0.3.0's `test_a_repeated_write_is_recorded_as_a_duplicate` writes the same tool with other
  arguments first, but with an order id one character too long for the tool's schema, which the
  store refuses (`invalid_arguments`), so the store holds one write and the test holds for the
  tool-keyed change as well (measured: it and every other test of `test_f2_own.py` and
  `test_f2_card_and_experimental.py` pass with `duplicate_write` keyed on the tool alone).
- **FX38.2** after the target write, a read that carries no checkable argument answers as it did
  before the write.  A read is shown the written values only when its checkable arguments are all
  among the write's; one that carries none has nothing to match, and `list_channels` with no
  arguments is that read.  The change it guards against overlays the latest write on it.
- **FX38.3** each experimental dial's note in `init` is the reason in `arms.EXPERIMENTAL_KNOBS`,
  character for character, dial by dial: in the built-in knob menu (`_init.KNOBS`, the notes of
  `distractor`, `timeouts` and `ratelimits`) and in the knob menu of the guided session on your
  own tools (`timeouts`, `ratelimits` and `landed`, each `experimental: <reason>`).  0.3.0's test
  looked for the reason inside the whole text of the menu, and only for two of the dials, so a
  note typed as a different literal that contained the reason, or a third dial's note typed as any
  text at all, passed.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from poisson_tasks.cli import _init
from tests.f2_support import (
    DUPLICATE,
    EXPERIMENTAL_REASONS,
    experimental,
    field,
    loaded,
    own_made,
    own_record,
    stepped,
)
from tests.o1_support import fixture
from tests.o2_support import acme_flows, fixture_sets, mcp_set, read_tool, write_tool
from tests.test_o2_cli import FLOWS, acme_set, invoke, work  # noqa: F401 - the fixture is used by name
from tests.fd5_support import Answers

S12 = {"type": "string", "maxLength": 12}
AB = {"type": "string", "enum": ["a", "b"]}


def items() -> Any:
    """The fewest tools that show it: `set_status` takes an item and a status of two, so a second
    write with the other status is accepted, and `get_item` reads an item back."""
    return mcp_set(
        write_tool("set_status", {"item_id": S12, "status": AB}, ["item_id", "status"]),
        read_tool("get_item", {"item_id": S12}, ["item_id"]), name="items")


def test_fx38_1_a_second_write_to_the_same_tool_with_other_arguments_is_not_a_duplicate(
    tmp_path: Path,
) -> None:
    bundle = own_made(items(), "faults", 0, 7)
    (name, args), *_rest = bundle.reference_calls
    other = {**args, "status": "b" if args["status"] == "a" else "a"}
    assert other != args
    state, _answers = stepped(bundle, [(name, args), (name, other)])
    assert len(vars(state)["writes"]) == 2, "both writes were accepted into the store"
    apart = own_record(tmp_path / "apart", bundle, [(name, args), (name, other)])
    twice = own_record(tmp_path / "twice", bundle, [(name, args), (name, args)])
    assert field(apart, DUPLICATE) is False
    assert field(twice, DUPLICATE) is True, "the control: the same write twice is a duplicate"


ACME = ("acme-openai", "acme-mcp", "acme-openapi-3.0")


@pytest.mark.parametrize("name", ACME)
def test_fx38_2_a_read_with_no_checkable_argument_answers_as_before_the_write(name: str) -> None:
    """On acme, after the target write, `list_channels` with no arguments answers what it answered
    before.  The control is in the same test: `get_order`, which takes the write's `order_id`, shows
    the written id after the write and not before, so the comparison is not between two answers
    that could not differ.  Only the OpenAI file has no output schemas, so only there does an
    overlaid read show the write's arguments beside its own; the other two hold the same rule with
    less to show."""
    bundle = own_made(fixture_sets()[name], "faults", 0, 404)
    target, args = bundle.reference_calls[0]
    listing: tuple[str, dict[str, Any]] = ("list_channels", {})
    look = ("get_order", {"order_id": args["order_id"]})
    _state, (before, _write, after) = stepped(bundle, [listing, (target, args), listing])
    assert loaded(after) == loaded(before)
    _state, (looked_before, _w, looked_after) = stepped(bundle, [look, (target, args), look])
    assert loaded(looked_after) != loaded(looked_before)
    assert loaded(looked_after)["order_id"] == args["order_id"], "the control: the write is shown"


def test_fx38_3_the_shared_reasons_are_the_four_experimental_dials() -> None:
    """The reasons the notes are held to are the mapping's own, and it is the four."""
    assert experimental() == EXPERIMENTAL_REASONS


def test_fx38_3_the_built_in_menus_notes_are_the_reasons_exactly() -> None:
    reasons = experimental()
    menu = {name: (label, note) for name, label, note in _init.KNOBS}
    assert {name for name in menu if name in reasons} == {"distractor", "timeouts", "ratelimits"}
    for name in ("distractor", "timeouts", "ratelimits"):
        label, note = menu[name]
        assert note == reasons[name], (name, note)
        assert f"{name} (experimental)" in label, (name, label)
    label, note = menu["depth"]
    assert note == "" and "(experimental)" not in label, "the control: depth is not experimental"


def knob_menu(text: str) -> dict[str, list[str]]:
    """The options of the guided session's knob menu (plain look), each label with its note lines."""
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if re.fullmatch(r"\d+\. The knob", line))
    options: dict[str, list[str]] = {}
    label = None
    for line in lines[start + 1:]:
        numbered = re.fullmatch(r"   \d+\) (.*)", line)
        if numbered:
            label = numbered.group(1)
            options[label] = []
        elif label is not None and line.startswith("      "):
            options[label].append(line.strip())
        else:
            break
    return options


def test_fx38_3_the_own_tools_menus_notes_are_the_reasons_exactly(
    work: Path, monkeypatch: pytest.MonkeyPatch  # noqa: F811
) -> None:
    from poisson_tasks.own import recipes

    (work / "tools.json").write_bytes(fixture("acme-mcp-tools-list.json"))
    table = recipes.recipes_for(acme_set(), flows=acme_flows())
    custom = str(sum(1 for recipe in table.values() if recipe.offered) + 1)
    ran = invoke(["init", "--no-check-key", *FLOWS], monkeypatch,
                 Answers(["2", "", "", "", "", "tools.json", custom]))
    assert ran.code == 0, ran
    menu = knob_menu(ran.out + ran.err)
    reasons = experimental()
    for name in ("timeouts", "ratelimits", "landed"):
        assert menu.get(f"{name} (experimental)") == [f"experimental: {reasons[name]}"], (name, menu)
    assert not any(label.startswith("depth") and "experimental" in label for label in menu), menu
