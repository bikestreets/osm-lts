"""osm-lts — classify OpenStreetMap ways by Level of Traffic Stress.

Implements the Furth methodology
(peterfurth.sites.northeastern.edu/level-of-traffic-stress/) as a pure
Python function operating on OSM tag dicts. No PostGIS, no Django, no
network I/O — just OSM tags in, LTS 1-4 (or ``None``) out.
"""

from ._classify import LTS, Classifier, classify, parse_maxspeed_mph
from ._constants import (
    CYCLEWAY_TAG_KEYS,
    DEFAULT_IMPLICIT_MAXSPEED_MPH,
    DEFAULT_LANE_COUNT_BY_HIGHWAY,
    DEFAULT_LANE_COUNT_FALLBACK,
    DEFAULT_SPEED_MPH_BY_HIGHWAY,
    DEFAULT_SPEED_MPH_FALLBACK,
    EXCLUDED_HIGHWAYS,
)

__version__ = "0.5.0"

__all__ = [
    "LTS",
    "Classifier",
    "classify",
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
