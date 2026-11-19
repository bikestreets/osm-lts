"""osm-lts — classify OpenStreetMap ways by Level of Traffic Stress.

Implements the Furth methodology
(peterfurth.sites.northeastern.edu/level-of-traffic-stress/) as a pure
Python function operating on OSM tag dicts. No PostGIS, no Django, no
network I/O — just OSM tags in, LTS 1-4 (or ``None``) out.
"""

from ._classify import (
    LTS,
    Classifier,
    Explanation,
    Rule,
    Source,
    classify,
    explain,
    parse_maxspeed_mph,
)
from ._crossings import (
    CROSSING_HIGHWAYS,
    CROSSING_KEYS,
    CROSSING_MARKER_KEYS,
    CROSSING_REFUGE_TAGS,
    CROSSING_SIGNAL_TAGS,
    REFUGE_CROSSINGS,
    UNSIGNALIZED_CROSSINGS,
    crossing_lts,
    has_refuge,
    is_crossing,
    is_signalized,
)
from ._rules import Comparison, CrossingRow
from ._constants import (
    CYCLEWAY_TAG_KEYS,
    DEFAULT_IMPLICIT_MAXSPEED_MPH,
    DEFAULT_LANE_COUNT_BY_HIGHWAY,
    DEFAULT_LANE_COUNT_FALLBACK,
    DEFAULT_SPEED_MPH_BY_HIGHWAY,
    DEFAULT_SPEED_MPH_FALLBACK,
    EXCLUDED_HIGHWAYS,
)

__version__ = "0.7.0"

__all__ = [
    "LTS",
    "Classifier",
    "classify",
    "explain",
    "crossing_lts",
    "is_crossing",
    "is_signalized",
    "has_refuge",
    "Comparison",
    "CrossingRow",
    "CROSSING_SIGNAL_TAGS",
    "CROSSING_REFUGE_TAGS",
    "UNSIGNALIZED_CROSSINGS",
    "REFUGE_CROSSINGS",
    "CROSSING_MARKER_KEYS",
    "CROSSING_HIGHWAYS",
    "CROSSING_KEYS",
    "Explanation",
    "Rule",
    "Source",
    "parse_maxspeed_mph",
    "EXCLUDED_HIGHWAYS",
    "DEFAULT_SPEED_MPH_BY_HIGHWAY",
    "DEFAULT_SPEED_MPH_FALLBACK",
    "DEFAULT_IMPLICIT_MAXSPEED_MPH",
    "DEFAULT_LANE_COUNT_BY_HIGHWAY",
    "DEFAULT_LANE_COUNT_FALLBACK",
    "CYCLEWAY_TAG_KEYS",
    "__version__",
]
