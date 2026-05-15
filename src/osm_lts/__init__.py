"""osm-lts — classify OpenStreetMap ways by Level of Traffic Stress.

Implements the Furth methodology
(peterfurth.sites.northeastern.edu/level-of-traffic-stress/) as a pure
Python function operating on OSM tag dicts. No PostGIS, no Django, no
network I/O — just OSM tags in, LTS 1-4 (or ``None``) out.
"""

from ._classify import LTS, Classifier, classify
from ._constants import (
    CYCLEWAY_TAG_KEYS,
    DEFAULT_LANE_COUNT_BY_HIGHWAY,
    DEFAULT_LANE_COUNT_FALLBACK,
    DEFAULT_SPEED_MPH_BY_HIGHWAY,
    DEFAULT_SPEED_MPH_FALLBACK,
    EXCLUDED_HIGHWAYS,
)

__version__ = "0.4.0"

__all__ = [
    "LTS",
    "Classifier",
    "classify",
    "EXCLUDED_HIGHWAYS",
    "DEFAULT_SPEED_MPH_BY_HIGHWAY",
    "DEFAULT_SPEED_MPH_FALLBACK",
    "DEFAULT_LANE_COUNT_BY_HIGHWAY",
    "DEFAULT_LANE_COUNT_FALLBACK",
    "CYCLEWAY_TAG_KEYS",
    "__version__",
]
