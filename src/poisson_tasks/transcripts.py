"""An agent's attempt at a task, read from a file into the turns the verifier judges.

`poisson-tasks verify --transcript FILE` takes one attempt in one of three forms, told apart by
shape and refused when ambiguous (spec §4.5):

- **OpenAI chat messages**: a JSON list of messages with roles, the assistant's carrying
  `tool_calls` and each tool's reply carrying `tool_call_id`.  The sampled calls are ordered as
  the export orders them for a run's records: by the `seq` the tool's answer opens with, a call
  the harness refused kept where it was made; a reply after the last call ends the attempt.
- **One row of a verifiers `traces.jsonl`**: a JSON object with `traces`, read through the wheel's
  own trace type and ordered the same way; its stop condition says whether the turn limit was hit.
- **Tasks' own turns**: a JSON list of `tasks.Turn`'s fields, `content`, `calls` (each
  `[name, arguments]`) and `finish_reason`, taken as written.

`read_transcript` gives the turns and whether the attempt ended with a reply, and whether the
turn limit was hit where the form can say.  `verdict_of` is `tasks.verify` over them with the
direct parser's format.  `tests/test_fd5_verify.py` says what each name does.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Mapping, Sequence
from typing import Any

from poisson_tasks.tasks import FormatSpec, TaskBundle, Turn, Verdict, verify

__all__ = ["Transcript", "read_transcript", "verdict_of"]

OPENAI_FORM = "openai"
TRACES_FORM = "traces"
TURNS_FORM = "turns"

_ROLES = frozenset({"system", "user", "assistant", "tool", "developer"})
_TURN_KEYS = frozenset({"content", "calls", "finish_reason"})
_FORMAT = FormatSpec(name="direct", markers=())

_EXPECTED = (
    "OpenAI chat messages (a JSON list of messages with roles), one row of a verifiers "
    "traces.jsonl (a JSON object with traces), or Tasks' own turns (a JSON list of content, "
    "calls and finish_reason)"
)


@dataclasses.dataclass(frozen=True)
class Transcript:
    """One attempt: the form it was read from, its turns, whether it ended with a reply, and
    whether the turn limit was hit (`None` when the form cannot say)."""

    form: str
    turns: tuple[Turn, ...]
    ended_with_reply: bool
    turn_limit_hit: bool | None


def read_transcript(text: str) -> Transcript:
    """The attempt `text` holds, in one of the three forms.  A text in none of them, or that
    could be read as two, is a `ValueError` of one line naming the form expected."""
    try:
        document = json.loads(text)
    except ValueError as reason:
        raise ValueError(
            f"the transcript is not JSON ({reason}); verify reads {_EXPECTED}"
        ) from None
    if isinstance(document, Mapping):
        if isinstance(document.get("traces"), list):
            return _from_traces_row(document)
        raise ValueError(
            f"the transcript is a JSON object without traces; verify reads {_EXPECTED}"
        )
    if not isinstance(document, list):
        raise ValueError(
            f"the transcript is neither a JSON list nor an object; verify reads {_EXPECTED}"
        )
    if not document:
        raise ValueError(
            "the transcript is an empty list, which could be OpenAI chat messages or Tasks' own "
            f"turns; verify reads {_EXPECTED}"
        )
    if not all(isinstance(item, Mapping) for item in document):
        raise ValueError(
            "the transcript's list holds something that is not a message or a turn; verify "
            f"reads {_EXPECTED}"
        )
    messages = all("role" in item for item in document)
    turns = all(_TURN_KEYS <= set(item) for item in document)
    if messages and turns:
        raise ValueError(
            "the transcript could be read as OpenAI chat messages and as Tasks' own turns; "
            f"verify reads {_EXPECTED}"
        )
    if messages:
        return _from_messages(document)
    if turns:
        return _from_turns(document)
    raise ValueError(f"the transcript's list is in no form verify reads: {_EXPECTED}")


def verdict_of(
    bundle: TaskBundle, transcript: Transcript, *, turn_limit_hit: bool | None = None
) -> Verdict:
    """The task's own verdict on the attempt: `tasks.verify` over the transcript's turns, with
    the direct parser's format.  `turn_limit_hit` says what the form cannot; given, it wins."""
    limit = turn_limit_hit if turn_limit_hit is not None else bool(transcript.turn_limit_hit)
    return verify(bundle, transcript.turns, transcript.ended_with_reply, limit, _FORMAT)


# ---------------------------------------------------------------------------
# the three forms
# ---------------------------------------------------------------------------


def _arguments(value: Any) -> Any:
    """A call's arguments as the verifier takes them: JSON text parsed, lists as tuples."""
    if isinstance(value, str):
        try:
            value = json.loads(value or "{}")
        except ValueError:
            return value
    return _deep(value)


def _deep(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(_deep(item) for item in value)
    return value


def _seq_of(content: Any) -> int | None:
    """The `seq` a tool's answer opens with, or `None` for an answer the harness made itself."""
    if not isinstance(content, str):
        return None
    head = content.split(" ", 1)[0]
    return int(head) if head.isdigit() else None


def _ordered(
    calls: Sequence[tuple[int | None, tuple[str, Any]]], reply: str | None
) -> tuple[tuple[Turn, ...], bool]:
    """One turn per sampled call, ordered by the answers' `seq` (a call with none keeps its
    place), then the reply as a last turn when the attempt ended with one."""
    keys: list[float] = []
    last = -1.0
    for seq, _ in calls:
        key = float(seq) if seq is not None else last + 0.5
        last = max(last, key)
        keys.append(key)
    order = sorted(range(len(calls)), key=lambda index: (keys[index], index))
    turns = [Turn(content="", calls=(calls[index][1],), finish_reason="tool_calls")
             for index in order]
    ended = reply is not None
    if ended:
        turns.append(Turn(content=reply or "", calls=(), finish_reason="stop"))
    return tuple(turns), ended


def _from_messages(messages: Sequence[Mapping[str, Any]]) -> Transcript:
    open_ids: list[str] = []
    calls: list[tuple[str, Any]] = []
    answered: dict[int, Any] = {}
    reply: str | None = None
    for message in messages:
        role = message.get("role")
        if role not in _ROLES:
            raise ValueError(
                f"the transcript's messages carry a role verify does not know, "
                f"{json.dumps(role, ensure_ascii=False)}; the roles are system, user, assistant "
                "and tool"
            )
        if role == "assistant":
            made = message.get("tool_calls") or []
            for call in made:
                function = call.get("function") or {}
                open_ids.append(str(call.get("id", "")))
                calls.append((str(function.get("name", "")), _arguments(function.get("arguments"))))
            reply = None if made else str(message.get("content") or "")
        elif role == "tool":
            wanted = str(message.get("tool_call_id", ""))
            for index, call_id in enumerate(open_ids):
                if call_id == wanted and index not in answered:
                    answered[index] = message.get("content")
                    break
    rows = [(_seq_of(answered.get(index)), call) for index, call in enumerate(calls)]
    turns, ended = _ordered(rows, reply)
    return Transcript(form=OPENAI_FORM, turns=turns, ended_with_reply=ended, turn_limit_hit=None)


def _from_turns(rows: Sequence[Mapping[str, Any]]) -> Transcript:
    turns = []
    for row in rows:
        calls = row.get("calls") or []
        if not isinstance(calls, list) or not all(
            isinstance(call, list) and len(call) == 2 for call in calls
        ):
            raise ValueError(
                "a turn's calls must be a list of [name, arguments] pairs; verify reads "
                f"{_EXPECTED}"
            )
        turns.append(Turn(
            content=str(row.get("content") or ""),
            calls=tuple((str(name), _deep(arguments)) for name, arguments in calls),
            finish_reason=str(row.get("finish_reason") or ""),
        ))
    ended = bool(turns) and not turns[-1].calls
    return Transcript(form=TURNS_FORM, turns=tuple(turns), ended_with_reply=ended,
                      turn_limit_hit=None)


def _from_traces_row(row: Mapping[str, Any]) -> Transcript:
    traces = row["traces"]
    if not traces:
        raise ValueError(
            "the traces.jsonl row records no trace, so there is no attempt to judge"
        )
    import verifiers.v1 as vf
    from pydantic import TypeAdapter

    from poisson_tasks.export import _ordered_turns

    try:
        trace = TypeAdapter(vf.Trace).validate_python(traces[0])
    except ValueError as reason:
        first = str(reason).splitlines()[0]
        raise ValueError(f"the traces.jsonl row's first trace cannot be read ({first})") from None
    turns, ended = _ordered_turns(trace)
    return Transcript(
        form=TRACES_FORM, turns=turns, ended_with_reply=ended,
        turn_limit_hit=trace.stop_condition == "max_turns",
    )
