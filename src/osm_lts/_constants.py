"""Tunable defaults for the LTS classifier, read from ``rules.md``.

The values live in ``rules.md`` beside this module (see ``_rules``); this
module exposes them under their long-standing public names so callers can
inspect them (e.g. to say "we assumed 25 mph because the way was untagged")
and pass edited copies to a :class:`~osm_lts.Classifier`.
"""

from __future__ import annotations

from ._rules import DEFINITION as _D
from ._rules import RulesFileError

# Highways the classifier returns ``None`` for.
EXCLUDED_HIGHWAYS: frozenset[str] = _D.excluded_highways

# Speed (mph) when a way has no usable ``maxspeed`` or legal default.
DEFAULT_SPEED_MPH_BY_HIGHWAY: dict[str, int] = dict(_D.speed_mph_by_highway)
DEFAULT_SPEED_MPH_FALLBACK: int = _D.speed_mph_fallback

# Statutory defaults (mph) named by ``maxspeed:type`` / ``source:maxspeed``.
DEFAULT_IMPLICIT_MAXSPEED_MPH: dict[str, int] = dict(_D.implicit_maxspeed_mph)

# Lane count when ``lanes`` is missing.
DEFAULT_LANE_COUNT_BY_HIGHWAY: dict[str, int] = dict(_D.lane_count_by_highway)
DEFAULT_LANE_COUNT_FALLBACK: int = _D.lane_count_fallback

# ``cycleway*`` keys consulted in priority order.
CYCLEWAY_TAG_KEYS: tuple[str, ...] = _D.cycleway_tag_keys


def _rule_set(rule: str, column: str) -> frozenset:
    row = next((r for r in _D.rules if r.rule == rule), None)
    if row is None:
        raise RulesFileError(
            f"rules.md: rules table has no {rule!r} rule (osm_lts._constants "
            "reads it)"
        )
    return getattr(row, column)


# Kept for callers that read these private sets from earlier releases. The
# rules table is the source; nothing in the package reads these.
_BIKE_LANE_KINDS: frozenset = _rule_set("bike_lane_slow", "cycleway")
_LTS4_HIGHWAYS: frozenset = _rule_set("arterial", "highway")
_LTS3_HIGHWAYS: frozenset = _rule_set("collector", "highway")
