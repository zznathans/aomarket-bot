"""Credit/QL shorthand parsing (format_credits/parse_credits/parse_ql/
parse_range)."""

import re
from collections.abc import Callable

_CREDIT_RE = re.compile(r"^([0-9]+(?:\.[0-9]+)?)\s*([kmb]?)$", re.IGNORECASE)
_QL_RE = re.compile(r"^[0-9]+$")
_RANGE_RE = re.compile(r"^([^-]*)-([^-]*)$")

_MULTIPLIERS = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}


def format_credits(value: float) -> str:
    sign = "-" if value < 0 else ""
    value = abs(value)
    if value >= 1_000_000_000:
        return f"{sign}{round(value / 1_000_000_000, 1)}b"
    if value >= 1_000_000:
        return f"{sign}{round(value / 1_000_000, 1)}m"
    if value >= 1_000:
        return f"{sign}{round(value / 1_000, 1)}k"
    return f"{sign}{value:,.0f}"


def parse_credits(value: str) -> int | None:
    value = value.strip()
    if value == "":
        return None
    match = _CREDIT_RE.match(value)
    if not match:
        return None
    number = float(match.group(1))
    number *= _MULTIPLIERS.get(match.group(2).lower(), 1)
    return round(number)


def parse_ql(value: str) -> int | None:
    value = value.strip()
    if value == "" or not _QL_RE.match(value):
        return None
    return int(value)


def parse_range(spec: str, parser: Callable[[str], int | None]) -> tuple[int | None, int | None] | None:
    """Parses '<min>-<max>' (either side optional). Returns None if malformed:
    an unparseable non-empty side, both sides empty, or min > max."""
    match = _RANGE_RE.match(spec.strip())
    if not match:
        return None
    min_raw, max_raw = match.group(1).strip(), match.group(2).strip()

    min_value = None
    if min_raw != "":
        min_value = parser(min_raw)
        if min_value is None:
            return None

    max_value = None
    if max_raw != "":
        max_value = parser(max_raw)
        if max_value is None:
            return None

    if min_value is None and max_value is None:
        return None
    if min_value is not None and max_value is not None and min_value > max_value:
        return None
    return min_value, max_value
