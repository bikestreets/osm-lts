"""Load the classifier's definition from ``rules.md``.

``rules.md`` (shipped beside this module) holds every rule and default as a
Markdown table, each preceded by an ``<!-- osm-lts:table NAME -->`` marker.
This module parses those tables, strictly, once at import. ``_constants``,
``_classify`` and ``sql`` all read the result, so the Python classifier and
the SQL emitter evaluate the same ordered rule list.

Standard library only: the package has no dependencies.
"""

from __future__ import annotations

import operator
import re
from dataclasses import dataclass
from importlib import resources
from typing import Callable, Dict, FrozenSet, List, Optional, Tuple

RULES_FILE = "rules.md"

_MARKER_RE = re.compile(r"<!--\s*osm-lts:table\s+(\w+)\s*-->")
_COMPARISON_RE = re.compile(r"^(>=|<=|>|<|=)\s*(\d+)$")

# Comparison operators a rules.md cell may use, with their SQL spelling.
COMPARISONS: Dict[str, Tuple[Callable[[int, int], bool], str]] = {
    ">": (operator.gt, ">"),
    ">=": (operator.ge, ">="),
    "<": (operator.lt, "<"),
    "<=": (operator.le, "<="),
    "=": (operator.eq, "="),
}


class RulesFileError(ValueError):
    """``rules.md`` is malformed. The message says where."""


@dataclass(frozen=True)
class Comparison:
    """``speed (mph)`` / ``lanes`` condition, e.g. ``> 35``."""

    op: str
    value: int

    def test(self, actual: int) -> bool:
        return COMPARISONS[self.op][0](actual, self.value)

    def compiled(self) -> Tuple[Callable[[int, int], bool], int]:
        """``(operator function, value)`` for a tight loop."""
        return COMPARISONS[self.op][0], self.value

    def sql(self, expression: str) -> str:
        return f"({expression}) {COMPARISONS[self.op][1]} {self.value}"

    def __str__(self) -> str:
        return f"{self.op} {self.value}"


@dataclass(frozen=True)
class RuleRow:
    """One row of the rules table: conditions (``None`` = not checked)."""

    rule: str
    lts: int
    highway: Optional[FrozenSet[str]]
    cycleway: Optional[FrozenSet[str]]
    speed_mph: Optional[Comparison]
    lanes: Optional[Comparison]
    description: str


@dataclass(frozen=True)
class Definition:
    level_descriptions: Dict[int, str]
    rules: Tuple[RuleRow, ...]
    excluded_highways: FrozenSet[str]
    speed_mph_by_highway: Dict[str, int]
    speed_mph_fallback: int
    implicit_maxspeed_mph: Dict[str, int]
    lane_count_by_highway: Dict[str, int]
    lane_count_fallback: int
    cycleway_tag_keys: Tuple[str, ...]


def _split_row(line: str) -> List[str]:
    cells = line.strip()
    if not (cells.startswith("|") and cells.endswith("|")):
        raise RulesFileError(f"table row must start and end with '|': {line!r}")
    return [cell.strip() for cell in cells[1:-1].split("|")]


def parse_tables(text: str) -> Dict[str, List[Dict[str, str]]]:
    """``{name: [row dicts]}`` for every marked table in ``text``."""
    tables: Dict[str, List[Dict[str, str]]] = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        marker = _MARKER_RE.search(lines[i])
        i += 1
        if not marker:
            continue
        name = marker.group(1)
        if name in tables:
            raise RulesFileError(f"table {name!r} is defined twice")
        while i < len(lines) and not lines[i].strip():
            i += 1
        if i + 1 >= len(lines):
            raise RulesFileError(f"table {name!r}: marker isn't followed by a table")
        header = _split_row(lines[i])
        separator = _split_row(lines[i + 1])
        if len(separator) != len(header) or not all(
            re.fullmatch(r":?-+:?", cell) for cell in separator
        ):
            raise RulesFileError(f"table {name!r}: second line isn't a separator row")
        i += 2
        rows = []
        while i < len(lines) and lines[i].strip().startswith("|"):
            cells = _split_row(lines[i])
            if len(cells) != len(header):
                raise RulesFileError(
                    f"table {name!r}: row has {len(cells)} cells, header has "
                    f"{len(header)}: {lines[i]!r}"
                )
            rows.append(dict(zip(header, cells)))
            i += 1
        if not rows:
            raise RulesFileError(f"table {name!r} has no rows")
        tables[name] = rows
    return tables


def _require(tables, name: str, columns: Tuple[str, ...]) -> List[Dict[str, str]]:
    if name not in tables:
        raise RulesFileError(f"missing table {name!r}")
    rows = tables[name]
    missing = [c for c in columns if c not in rows[0]]
    if missing:
        raise RulesFileError(f"table {name!r} is missing columns {missing}")
    return rows


def _int(table: str, value: str) -> int:
    if not re.fullmatch(r"\d+", value):
        raise RulesFileError(f"table {table!r}: {value!r} isn't a whole number")
    return int(value)


def _values(cell: str) -> Optional[FrozenSet[str]]:
    if not cell:
        return None
    values = [v.strip() for v in cell.split(",")]
    if not all(values):
        raise RulesFileError(f"empty value in {cell!r}")
    return frozenset(values)


def _comparison(cell: str) -> Optional[Comparison]:
    if not cell:
        return None
    match = _COMPARISON_RE.match(cell)
    if not match:
        raise RulesFileError(
            f"{cell!r} isn't a comparison like '> 35' or '<= 25' "
            f"(operators: {', '.join(COMPARISONS)})"
        )
    return Comparison(match.group(1), int(match.group(2)))


def _defaults(
    tables, name: str, key: str, value: str, *, fallback_row: bool = True
) -> Tuple[Dict[str, int], Optional[int]]:
    """``{key: value}`` from a two-column table, plus its ``*`` row's value."""
    by_key: Dict[str, int] = {}
    fallback = None
    for row in _require(tables, name, (key, value)):
        number = _int(name, row[value])
        if row[key] == "*" and fallback_row:
            if fallback is not None:
                raise RulesFileError(f"table {name!r} has more than one '*' row")
            fallback = number
        elif row[key] in by_key:
            raise RulesFileError(f"table {name!r}: {row[key]!r} is listed twice")
        else:
            by_key[row[key]] = number
    if fallback is None and fallback_row:
        raise RulesFileError(f"table {name!r} needs a '*' row for everything else")
    return by_key, fallback


def _column(tables, name: str, column: str) -> List[str]:
    values = [row[column] for row in _require(tables, name, (column,))]
    if len(set(values)) != len(values):
        raise RulesFileError(f"table {name!r} lists a value twice")
    return values


def parse_definition(text: str) -> Definition:
    """Parse and validate a whole ``rules.md``."""
    tables = parse_tables(text)

    columns = ("rule", "LTS", "highway", "cycleway", "speed (mph)", "lanes", "description")
    rules = []
    for row in _require(tables, "rules", columns):
        where = f"rules table, rule {row['rule']!r}"
        try:
            lts = _int("rules", row["LTS"])
            if not 1 <= lts <= 4:
                raise RulesFileError(f"LTS must be 1-4, not {lts}")
            if "%" in row["description"]:
                # Descriptions become comments in the emitted SQL, where a
                # '%' would be read as a DB driver placeholder.
                raise RulesFileError("description can't contain '%'")
            rules.append(
                RuleRow(
                    rule=row["rule"],
                    lts=lts,
                    highway=_values(row["highway"]),
                    cycleway=_values(row["cycleway"]),
                    speed_mph=_comparison(row["speed (mph)"]),
                    lanes=_comparison(row["lanes"]),
                    description=row["description"],
                )
            )
        except RulesFileError as error:
            raise RulesFileError(f"{where}: {error}") from None
    names = [rule.rule for rule in rules]
    if len(set(names)) != len(names):
        raise RulesFileError("rules table: a rule name is used twice")
    unconditional = [
        r.rule
        for r in rules
        if not (r.highway or r.cycleway or r.speed_mph or r.lanes)
    ]
    if unconditional != [rules[-1].rule]:
        raise RulesFileError(
            "rules table: exactly one rule, the last, must have no conditions "
            f"(so every in-scope way is rated); found {unconditional or 'none'}"
        )

    speeds, speed_fallback = _defaults(tables, "default_speeds", "highway", "mph")
    lanes, lane_fallback = _defaults(tables, "default_lanes", "highway", "lanes")
    zones, _ = _defaults(
        tables, "legal_default_speeds", "zone", "mph", fallback_row=False
    )
    levels = {}
    for row in _require(tables, "levels", ("LTS", "Who it suits")):
        level = _int("levels", row["LTS"])
        if level in levels:
            raise RulesFileError(f"levels table lists LTS {level} twice")
        levels[level] = row["Who it suits"]
    if sorted(levels) != [1, 2, 3, 4]:
        raise RulesFileError("levels table must describe LTS 1, 2, 3 and 4")

    return Definition(
        level_descriptions=levels,
        rules=tuple(rules),
        excluded_highways=frozenset(_column(tables, "excluded_highways", "highway")),
        speed_mph_by_highway=speeds,
        speed_mph_fallback=speed_fallback,
        implicit_maxspeed_mph=zones,
        lane_count_by_highway=lanes,
        lane_count_fallback=lane_fallback,
        cycleway_tag_keys=tuple(_column(tables, "cycleway_keys", "key")),
    )


def load_definition() -> Definition:
    text = resources.files(__package__).joinpath(RULES_FILE).read_text("utf-8")
    try:
        return parse_definition(text)
    except RulesFileError as error:
        raise RulesFileError(f"{RULES_FILE}: {error}") from None


DEFINITION = load_definition()
