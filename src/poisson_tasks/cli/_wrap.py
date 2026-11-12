"""Lines broken for a terminal, by one rule in both looks and in the guided session.

A line breaks only at a space, and a wrapped line keeps its indent.  No path, URL, command or
quoted value is ever split by a line break: a quoted value (`"…"`, `'…'`, `` `…` ``), a word
with no space in it, a path the caller names (`keep`) and a command that starts with the prog are
each one piece, and a piece longer than the line is left whole for the terminal to fold.  A piece
that is a JSON value or a call (`name(key="value", …)`) longer than the line may also break
between its members, after a comma or an opening bracket, never inside a quoted string, and a
JSON key stays with its value.  A shell assignment written in a sentence (`export NAME=…`) is one
piece too.

Nothing here runs off a terminal: piped output keeps one line per fact, as written.
"""

from __future__ import annotations

import os
import re
from collections.abc import Sequence
from pathlib import Path

VERBS = frozenset({"init", "generate", "run", "card", "verify", "export", "doctor"})
"""The words that may follow the prog in a command written inside a sentence."""

_QUOTES = {'"': '"', "'": "'", "`": "`"}


def known_paths() -> list[str]:
    """The folders a message is most likely to name, in the two forms the command writes them:
    the working folder, absolute and from `~`, and the home folder from `~`.  A path that starts
    with one of them is kept whole even when a folder name in it has a space."""
    found: list[str] = []
    try:
        cwd = os.getcwd()
    except OSError:
        return found
    found.append(cwd)
    home = str(Path.home())
    if cwd == home or cwd.startswith(home + os.sep):
        found.append("~" + cwd[len(home):])
    return [path for path in found if " " in path]


def _quote_end(text: str, start: int) -> int | None:
    """Where the quoted value opening at `start` ends (the index after its closing quote), or
    `None` when `text[start]` does not open one: a quote opens a value at the start of a word or
    after `(`, `[`, `{`, `=` or `:`, and closes before a space, the end or a punctuation mark."""
    mark = text[start]
    if mark not in _QUOTES:
        return None
    if start > 0 and not (text[start - 1].isspace() or text[start - 1] in "([{=:,"):
        return None
    index = start + 1
    while index < len(text):
        char = text[index]
        if char == "\\" and mark == '"':
            index += 2
            continue
        if char == _QUOTES[mark]:
            after = text[index + 1] if index + 1 < len(text) else " "
            if after.isspace() or after in ".,;:)]}!?'\"":
                return index + 1
        if char == "\n":
            return None
        index += 1
    return None


def _command_end(text: str, start: int, prog: str) -> int:
    """Where a command written in a sentence ends: the prog, then each word that is a verb, a
    flag, or the value of the flag before it (a value has a digit, a dot, a slash, a colon or a
    quote in it, or is the only word after the flag)."""
    end = start + len(prog)
    index = end
    previous_flag = False
    while index < len(text) and text[index] == " ":
        word_start = index + 1
        match = re.match(r"\S+", text[word_start:])
        if match is None:
            break
        word = match.group(0).rstrip(".,;:")
        if not word:
            break
        is_part = (word in VERBS or word.startswith("-")
                   or (previous_flag and re.search(r"[\d./:'\"=]", word) is not None))
        if not is_part:
            break
        previous_flag = word.startswith("--") and "=" not in word
        end = word_start + len(word)
        index = end
    return end


def _protected(text: str, keep: Sequence[str], prog: str | None) -> list[tuple[int, int]]:
    """The spans of `text` that are never broken."""
    spans: list[tuple[int, int]] = []
    for path in sorted({*keep, *known_paths()}, key=len, reverse=True):
        if not path:
            continue
        at = text.find(path)
        while at >= 0:
            end = at + len(path)
            while end < len(text) and not text[end].isspace():
                end += 1
            spans.append((at, end))
            at = text.find(path, end)
    if prog:
        at = text.find(prog)
        while at >= 0:
            if at == 0 or text[at - 1] in " (`'\"":
                spans.append((at, _command_end(text, at, prog)))
            at = text.find(prog, at + len(prog))
    for match in re.finditer(r"\bexport [A-Za-z_]\w*=\S*", text):
        spans.append((match.start(), match.end()))
    index = 0
    while index < len(text):
        closed = _quote_end(text, index)
        if closed is not None:
            spans.append((index, closed))
            index = closed
        else:
            index += 1
    return spans


def pieces(text: str, *, keep: Sequence[str] = (), prog: str | None = None) -> list[str]:
    """`text` cut at its spaces into the pieces a line may break between, each piece carrying the
    spaces before it (the first carries none), so that joining them gives `text` back."""
    covered = [False] * len(text)
    for start, end in _protected(text, keep, prog):
        for index in range(start, min(end, len(text))):
            covered[index] = True
    out: list[str] = []
    current = ""
    index = 0
    while index < len(text):
        char = text[index]
        # a space after a JSON key's colon is not a break: a key stays with its value
        if char == " " and not covered[index] and current.strip() and not current.endswith('":'):
            run = index
            while run < len(text) and text[run] == " " and not covered[run]:
                run += 1
            out.append(current)
            current = text[index:run]
            index = run
            continue
        current += char
        index += 1
    if current or not out:
        out.append(current)
    return out


def _members(piece: str) -> list[str]:
    """A JSON value or a call cut after each comma and opening bracket outside a quoted string,
    so it can break between its members; any other piece whole."""
    body = piece.lstrip(" ")
    if not body or not (body[0] in "[{" or re.match(r"[A-Za-z_][\w.]*\(", body)):
        return [piece]
    cuts: list[str] = []
    current = piece[: len(piece) - len(body)]
    quote: str | None = None
    index = 0
    while index < len(body):
        char = body[index]
        current += char
        if quote is not None:
            if char == "\\":
                index += 1
                if index < len(body):
                    current += body[index]
            elif char == quote:
                quote = None
        elif char == '"':
            quote = char
        elif char in ",([{" and index + 1 < len(body) and body[index + 1] not in ")]}":
            cuts.append(current)
            current = ""
            while index + 1 < len(body) and body[index + 1] == " ":
                index += 1
                current += " "
        index += 1
    if current:
        cuts.append(current)
    return cuts


def lines(
    text: str,
    width: int,
    *,
    first: int = 0,
    indent: int = 0,
    keep: Sequence[str] = (),
    prog: str | None = None,
) -> list[str]:
    """`text` as lines for a terminal `width` columns wide: the first line has `first` columns
    already taken (a label, a mark), each later line starts with `indent` spaces, which this
    adds.  Lines of `text` that are already apart stay apart; each is broken by the rule at the
    top of this module."""
    out: list[str] = []
    for paragraph in text.split("\n"):
        if not out:
            out += _paragraph(paragraph, width, first, indent, keep, prog)
            continue
        # a line of the text after the first is a line of the same row: it keeps the indent
        made = _paragraph(paragraph, width, indent, indent, keep, prog)
        out += [(" " * indent + made[0]) if made[0] else ""] + made[1:]
    return out


def _paragraph(text: str, width: int, first: int, indent: int, keep: Sequence[str],
               prog: str | None) -> list[str]:
    """One line of the text, broken: the first line without a prefix (`first` columns are
    taken before it), the others `indent` spaces in."""
    if len(text) <= max(10, width - first):
        return [text]
    result: list[str] = []
    line = ""
    widest = max(10, width - indent)
    for piece in pieces(text, keep=keep, prog=prog):
        for part in _members(piece) if len(piece.strip()) > widest else [piece]:
            room = max(10, width - (first if not result else indent))
            # a part no line can hold starts a line of its own at the indent, for the terminal
            # to fold; as the first piece of the text it stays beside its label
            if line and len(line) + len(part) > room:
                result.append(line)
                line = part.lstrip(" ")
            else:
                line += part
    result.append(line)
    return [result[0]] + [" " * indent + rest for rest in result[1:]]
