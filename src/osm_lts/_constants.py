"""Tunable defaults for the LTS classifier.

These mirror the SQL CASE branches in the original Bike Streets
implementation. Surfaced as module-level constants so callers can
inspect them and (in a future minor release) override them via a
``Classifier`` instance.
"""

from __future__ import annotations

# Highways the classifier returns ``None`` for. Bikes are prohibited
# (``motorway``), the way isn't relevant to cyclist stress
# (``footway``, ``sidewalk``, ``steps``), or the way is pedestrian-
# only by convention.
EXCLUDED_HIGHWAYS: frozenset[str] = frozenset(
    {
        "motorway",
        "motorway_link",
        "footway",
        "sidewalk",
        "steps",
        "pedestrian",
    }
)

# Speed defaults in mph when the way has no explicit ``maxspeed`` tag.
# Most US residential streets don't carry a maxspeed; the planning
# default is the posted limit for the highway class.
DEFAULT_SPEED_MPH_BY_HIGHWAY: dict[str, int] = {
    "living_street": 15,
    "residential": 25,
    "unclassified": 25,
    "service": 25,
    "tertiary": 30,
    "tertiary_link": 30,
    "secondary": 35,
    "secondary_link": 35,
    "primary": 40,
    "primary_link": 40,
    "trunk": 40,
    "trunk_link": 40,
}
DEFAULT_SPEED_MPH_FALLBACK: int = 25

# Lane-count defaults when ``lanes`` is missing.
DEFAULT_LANE_COUNT_BY_HIGHWAY: dict[str, int] = {
    "residential": 2,
    "service": 2,
    "primary": 4,
    "primary_link": 4,
    "secondary": 4,
    "secondary_link": 4,
}
DEFAULT_LANE_COUNT_FALLBACK: int = 2

# Rule-tier highway sets — kept as module-level constants (not on
# ``Classifier``) because they're part of Furth's published rule
# tree, not tunable defaults. The Python branches in ``_classify``
# and the SQL emitter in ``sql`` both read from here so adding a
# new arterial type is a one-place edit.
_BIKE_LANE_KINDS: frozenset = frozenset(
    {"lane", "opposite_lane", "shared_lane"}
)
_LTS4_HIGHWAYS: frozenset = frozenset(
    {"primary", "primary_link", "trunk", "trunk_link"}
)
_LTS3_HIGHWAYS: frozenset = frozenset(
    {
        "tertiary",
        "tertiary_link",
        "secondary",
        "secondary_link",
        "residential",
        "unclassified",
    }
)


# OSM cycleway sub-tags consulted in priority order. ``cycleway`` (the
# unprefixed key) wins when present, then per-side variants. A way
# tagged with conflicting sides (e.g. lane right, track left) returns
# the first one set — callers wanting per-direction precision should
# preprocess the tags themselves.
CYCLEWAY_TAG_KEYS: tuple[str, ...] = (
    "cycleway",
    "cycleway:right",
    "cycleway:left",
    "cycleway:both",
)
