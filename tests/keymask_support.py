"""Shared ground for the key mask's tests: made-up keys shaped as providers issue them, the rule
they are held to, and a fixture model that quotes a key back where a provider can.  Frozen with
them.

**The rule** (FD3.16, amended and ruled 2026-10-12).  A key's public prefix, the one every key of
its kind starts with (`sk-proj-`), is not secret; what follows it is the secret part, and a
secret part shorter than four characters is no secret part, so the whole key stands for it.  The
secret part is looked for as written and JSON-escaped, once and twice.
- **Masked** (`masked_runs`): a text that can carry the key, each provider error a trace records,
  the run's first error and every line of `run.log`, holds no run of four or more of its
  characters.
- **Never written** (`key_runs`): no text a run writes or prints, every file in the run folder,
  the result, stdout and stderr, holds a run of twelve or more of its characters, or the whole
  secret part when it is shorter.  Twelve characters of a key are the key's: no text a run makes
  for itself holds one by chance (measured, `evidence/front-door-keymask/`), so a run of twelve
  anywhere is the key leaking, and a shorter run outside the texts above is the run's own.
- **Kept**: every other byte of a trace line is the wheel's own, as the run produced it.

**The keys** are made up; none was ever issued.  `PROJECT_KEY` is shaped as an OpenAI project key
is (`sk-proj-`, 148 characters of `[A-Za-z0-9_-]` with `T3BlbkFJ` in the middle), and its secret
part holds runs of the fixture's own traces, as a real key's does by chance: `fixed-width` (eleven
characters, in every task's system prompt), `product` (the item codes), `000001` (the tool
server's sequence numbers) and `record_id` (a tool's argument).  Its prefix holds `-pro`, which
every item code `user-right-pass-product` holds too.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any

from tests.fixtures.model_server import FixtureModel

MASKED_RUN = 4
KEY_RUN = 12

_HEAD = "Qm7Rx2Vk_fixed-widthL9pZt4Wq-Hn3Bv8product5JcYd1Ks6Gf0000001aUe7MoAb3dGhUi"
_TAIL = "Ex2Nr5record_idTq8Lw3Zy-Va6Pb1Hs9Kd4Jg7Cm0Fu_Xi2Re5Yo8Wn1Qt4Sv7Bk0Dz3Lh6Mx"
PROJECT_SECRET = _HEAD + "T3BlbkFJ" + _TAIL
PROJECT_KEY = "sk-proj-" + PROJECT_SECRET

ANTHROPIC_SECRET = (
    "Wd4Kq8Zr2Tn6Vb0Xy3Mh7Lc1Pf5Gs9Jk2Ue6Ra0Yo4Ni8Bt3Qe7Dw1Hz5Cx9Fv2Sm6Lp0Kg4Jt8-Ab1Cd2Ef"
)
ANTHROPIC_KEY = "sk-ant-api03-" + ANTHROPIC_SECRET + "AA"
LOCAL_KEY = "token-Zq8Wx3sk-Rv7Kp2Lm9"
"""A server's own key (vLLM's `--api-key`): no public prefix at its start, so all of it is
secret, the `sk-` past its start included."""
SHORT_KEY = "sk-Zq9"
"""A secret part shorter than four characters: the whole key stands for it."""
ESCAPED_KEY = 'sk-Zq8"Wx3\\Rv7"Kp2\\Lm9"Tn4\\Yb6"Hd1\\Gf5'
"""Characters JSON escapes, which a header can carry, no more than three characters apart: the
key shows escaped once in a provider's error as verifiers keeps it, and twice in a trace line,
and no run of twelve of it reads the same at two levels of escaping."""

KEYS: dict[str, tuple[str, str]] = {
    "project": (PROJECT_KEY, PROJECT_SECRET),
    "anthropic": (ANTHROPIC_KEY, ANTHROPIC_SECRET + "AA"),
    "local": (LOCAL_KEY, LOCAL_KEY),
    "short": (SHORT_KEY, SHORT_KEY),
    "escaped": (ESCAPED_KEY, ESCAPED_KEY[len("sk-") :]),
}
"""Each made-up key and its secret part, written out rather than computed."""

PREFIXES = {"project": "sk-proj-", "anthropic": "sk-ant-api03-", "escaped": "sk-"}


def forms(secret: str) -> list[str]:
    """The secret part as written and JSON-escaped once and twice."""
    once = json.dumps(secret)[1:-1]
    return list(dict.fromkeys([secret, once, json.dumps(once)[1:-1]]))


def runs_of(text: str, secret: str, length: int) -> list[str]:
    """Every run of `length` characters of the secret part, in any of its forms, that `text`
    holds; a form shorter than `length` counts whole."""
    found: set[str] = set()
    for form in forms(secret):
        size = min(length, len(form))
        found.update(
            form[i : i + size] for i in range(len(form) - size + 1) if form[i : i + size] in text
        )
    return sorted(found)


def masked_runs(text: str, secret: str) -> list[str]:
    """What a text that can carry the key must not hold: runs of four."""
    return runs_of(text, secret, MASKED_RUN)


def key_runs(text: str, secret: str) -> list[str]:
    """What no text a run writes may hold: runs of twelve, or the secret part whole."""
    return runs_of(text, secret, KEY_RUN)


def longest_run(text: str, secret: str) -> int:
    """The longest run of the secret part, as written, that `text` holds."""
    best = 0
    for size in range(1, len(secret) + 1):
        if any(secret[i : i + size] in text for i in range(len(secret) - size + 1)):
            best = size
        else:
            break
    return best


def error_texts(
    row: Mapping[str, Any], names: tuple[str, ...] = ("message", "traceback")
) -> list[str]:
    """Every provider error a trace line records, its message and its traceback (or the parts
    `names` says): the episode's, each trace's and each model call's."""
    errors = list(row.get("errors") or [])
    for trace in row.get("traces") or []:
        errors.extend(trace.get("errors") or [])
        errors.extend(call["error"] for call in trace.get("calls") or [] if call.get("error"))
    return [str(error[name]) for error in errors for name in names if error.get(name) is not None]


def without_error_texts(row: Any) -> Any:
    """A trace line's document with every error's message and traceback taken out, so two can be
    compared on everything else."""
    if isinstance(row, dict):
        if (
            "type" in row
            and "message" in row
            and set(row) <= {"type", "message", "status_code", "traceback"}
        ):
            return {key: value for key, value in row.items() if key not in ("message", "traceback")}
        return {key: without_error_texts(value) for key, value in row.items()}
    if isinstance(row, list):
        return [without_error_texts(item) for item in row]
    return row


def strings(value: Any) -> Iterable[str]:
    """Every string in a JSON document, names included."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from strings(item)


REFUSED_MODEL = "keymask-401"
COST = 1e-05
ECHO_MODEL = "keymask-echo"


class KeyQuoting(FixtureModel):
    """The fixture model, and two models of a provider quoting the key back.

    `keymask-401` refuses every call as OpenAI does and quotes the key in every form a provider
    can: masked to its prefix and last four, whole, and the secret part's first three characters
    as a word of their own; and it names a project, whose `proj` the prefix holds.
    `keymask-echo` plays the reference policy and ends with a reply that quotes the key whole, a
    run of twelve of the secret part and a run of eleven, each as `echo` makes them.  Every answer
    it serves reports the call's cost, as OpenRouter's do, in a number the wheel writes
    `0.00001` and Python's `json` writes `1e-05`, so a line written again is told from the
    wheel's."""

    def __init__(self, secret: str) -> None:
        super().__init__()
        self.secret = secret

    def _answer(self, body: Mapping[str, Any], key: str) -> tuple[int, dict[str, Any]]:
        model = str(body.get("model", ""))
        if model == REFUSED_MODEL:
            shown = key[: len(key) - len(self.secret)] + "*" * 20 + key[-4:]
            return 401, {
                "error": {
                    "message": f"Incorrect API key provided: {shown} (sent as {key}; it starts "
                    f"{self.secret[:3]} ). Find your project's keys in its settings.",
                    "type": "invalid_request_error",
                    "param": None,
                    "code": "invalid_api_key",
                }
            }
        status, answer = super()._answer(body, key)
        if status == 200:
            answer["usage"]["cost"] = COST
        if model == ECHO_MODEL and status == 200:
            message = answer["choices"][0]["message"]
            if message.get("content") == "Done.":
                message["content"] = echo(key, self.secret)
        return status, answer


def kept_run(secret: str) -> str:
    """The run of the secret part `keymask-echo`'s reply holds that a run must keep: from its
    nineteenth character, the longest that is under twelve characters as a trace line holds it
    (escaped once), eleven for a key with nothing to escape."""
    size = KEY_RUN - 1
    while len(json.dumps(secret[18 : 18 + size])) - 2 >= KEY_RUN:
        size -= 1
    return secret[18 : 18 + size]


def echo(key: str, secret: str) -> str:
    """`keymask-echo`'s last reply: the key whole and a run of twelve of the secret part, each
    escaped once as JSON (a key a text carries quoted), then `kept_run` as written."""
    once = json.dumps(key)[1:-1]
    return f"Done. {once} | {json.dumps(secret[4:16])[1:-1]} | {kept_run(secret)}"


def echo_masked(key: str, secret: str) -> str:
    """`echo` as a run must write it: the key and the run of twelve masked, the prefix kept,
    `kept_run` kept."""
    prefix = key[: len(key) - len(secret)]
    return f"Done. {prefix}**** | **** | {kept_run(secret)}"
