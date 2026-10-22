"""Numbers and words as rule L10 writes them, the same in both styles."""

from __future__ import annotations

from collections.abc import Sequence
from math import floor, log10


def rate(value: float) -> str:
    """A rate or a share: three decimals."""
    return f"{value:.3f}"


def interval(low: float, high: float) -> str:
    return f"[{rate(low)}, {rate(high)}]"


def count(value: int | float) -> str:
    """A count: thousands separators."""
    return f"{int(round(value)):,}"


def _significant(value: float, digits: int) -> float:
    return round(value, digits - 1 - floor(log10(abs(value))))


def dollars(value: float) -> str:
    """A measured amount: `$1.00`, or two significant digits below $0.10 (`$0.021`, `$0.0052`),
    the same in every verb."""
    if value <= 0:
        return "$0.00"
    if value >= 0.0995:
        return f"${value:.2f}"
    kept = _significant(value, 2)
    return f"${kept:.{max(2, 1 - floor(log10(kept)))}f}"


def about(value: float) -> str:
    """An estimate: `$2.50`, or one significant digit below $0.10 (`$0.02`)."""
    if value <= 0:
        return "$0.00"
    if value >= 0.0995:
        return f"${_significant(value, 2):.2f}"
    kept = _significant(value, 1)
    return f"${kept:.{max(2, -floor(log10(kept)))}f}"


def duration(seconds: float) -> str:
    """`40 s`, `1 min 40 s`, `1 h 36 min`."""
    whole = int(round(seconds))
    if whole < 60:
        return f"{whole} s"
    if whole < 3600:
        return f"{whole // 60} min {whole % 60} s"
    return f"{whole // 3600} h {whole % 3600 // 60} min"


def words(items: Sequence[object], last: str = "and") -> str:
    """`1, 3 and 8`."""
    texts = [str(item) for item in items]
    if len(texts) <= 1:
        return "".join(texts)
    return ", ".join(texts[:-1]) + f" {last} " + texts[-1]


def plural(number: int, one: str, many: str | None = None) -> str:
    """`1 task`, `10 tasks`."""
    return f"{count(number)} {one if number == 1 else (many or one + 's')}"
