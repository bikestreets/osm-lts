"""Furth Level of Traffic Stress classifier.

Reference: peterfurth.sites.northeastern.edu/level-of-traffic-stress/

The classification is a four-tier scale from "kid-comfortable" (1) to
"strong-and-fearless only" (4). The branches below evaluate top-to-
bottom; the first match wins. Order matters — separation (a
``cycleway=track``) short-circuits before any speed/lane bump can
push the way up to LTS 4.
"""

from __future__ import annotations

import re
from enum import IntEnum
from typing import Mapping, Optional

from . import _constants as C


class LTS(IntEnum):
    """Furth's Level of Traffic Stress, 1 (calmest) to 4 (most hostile)."""

    KID_COMFORTABLE = 1
    MOST_ADULTS = 2
    EXPERIENCED_ONLY = 3
    STRONG_AND_FEARLESS = 4


_NON_DIGIT_RE = re.compile(r"[^0-9]")
_BIKE_LANE_KINDS = frozenset({"lane", "opposite_lane", "shared_lane"})
_LTS4_HIGHWAYS = frozenset(
    {"primary", "primary_link", "trunk", "trunk_link"}
)
_LTS3_HIGHWAYS = frozenset(
    {
        "tertiary",
        "tertiary_link",
        "secondary",
        "secondary_link",
        "residential",
        "unclassified",
    }
)


def _coerce_int(value: Optional[str]) -> Optional[int]:
    """Strip non-digits from an OSM tag value and return ``int``, else ``None``.

    OSM ``maxspeed`` and ``lanes`` are free-form strings: ``"25 mph"``,
    ``"50 km/h"``, ``"4"``, ``"4;3"``. We only consume the leading
    digits — anything that doesn't yield digits returns ``None`` and
    the caller falls back to a highway-typical default.
    """
    if value is None:
        return None
    digits = _NON_DIGIT_RE.sub("", str(value))
    return int(digits) if digits else None


def _resolve_speed_mph(highway: str, maxspeed: Optional[str]) -> int:
    explicit = _coerce_int(maxspeed)
    if explicit is not None:
        return explicit
    return C.DEFAULT_SPEED_MPH_BY_HIGHWAY.get(
        highway, C.DEFAULT_SPEED_MPH_FALLBACK
    )


def _resolve_lane_count(highway: str, lanes: Optional[str]) -> int:
    explicit = _coerce_int(lanes)
    if explicit is not None:
        return explicit
    return C.DEFAULT_LANE_COUNT_BY_HIGHWAY.get(
        highway, C.DEFAULT_LANE_COUNT_FALLBACK
    )


def _resolve_cycleway_kind(tags: Mapping[str, str]) -> Optional[str]:
    """First non-empty cycleway* value, in :data:`CYCLEWAY_TAG_KEYS` order."""
    for key in C.CYCLEWAY_TAG_KEYS:
        value = tags.get(key)
        if value:
            return value
    return None


def classify(tags: Mapping[str, str]) -> Optional[LTS]:
    """Return the Furth LTS classification for an OSM way's tags.

    Args:
        tags: Mapping of OSM key to value, e.g. ``{"highway":
            "residential", "maxspeed": "25 mph"}``. Numeric tag values
            (``maxspeed``, ``lanes``) tolerate units — only the
            leading digits are read.

    Returns:
        :class:`LTS` 1-4, or ``None`` for ways outside scope:

        * No ``highway`` tag.
        * ``highway`` in :data:`EXCLUDED_HIGHWAYS` (motorways,
          footways, sidewalks, steps, pedestrian).

    Examples:
        >>> classify({"highway": "cycleway"})
        <LTS.KID_COMFORTABLE: 1>
        >>> classify({"highway": "residential", "maxspeed": "25 mph"})
        <LTS.MOST_ADULTS: 2>
        >>> classify({"highway": "primary"})
        <LTS.STRONG_AND_FEARLESS: 4>
        >>> classify({"highway": "footway"}) is None
        True
    """
    highway = tags.get("highway")
    if not highway or highway in C.EXCLUDED_HIGHWAYS:
        return None

    bicycle = tags.get("bicycle")
    cycleway_kind = _resolve_cycleway_kind(tags)
    speed_mph = _resolve_speed_mph(highway, tags.get("maxspeed"))
    lane_count = _resolve_lane_count(highway, tags.get("lanes"))

    # LTS 1 — separated paths, designated bike infrastructure, slow-
    # by-design streets. Short-circuits before any speed/lane bump:
    # a `cycleway=track` on a 40 mph arterial still returns 1
    # because the rider is physically separated from traffic.
    if highway == "cycleway":
        return LTS.KID_COMFORTABLE
    if highway == "path" and bicycle == "designated":
        return LTS.KID_COMFORTABLE
    if highway == "living_street":
        return LTS.KID_COMFORTABLE
    if cycleway_kind == "track":
        return LTS.KID_COMFORTABLE

    # LTS 4 — high-speed, multi-lane arterial, or trunk/primary by
    # tag class. A painted bike lane on a >35 mph 6-lane road is
    # still LTS 4; paint doesn't reduce stress on a hostile street.
    if speed_mph > 35:
        return LTS.STRONG_AND_FEARLESS
    if highway in _LTS4_HIGHWAYS:
        return LTS.STRONG_AND_FEARLESS
    if lane_count >= 3 and speed_mph > 30:
        return LTS.STRONG_AND_FEARLESS

    # LTS 2 — calm residential or a bike lane on a slow street.
    if cycleway_kind in _BIKE_LANE_KINDS and speed_mph <= 25:
        return LTS.MOST_ADULTS
    if highway in {"residential", "unclassified"} and speed_mph <= 25:
        return LTS.MOST_ADULTS

    # LTS 3 — moderate-speed mixed traffic, bike lane on a faster
    # street, tertiary collectors, or any residential/unclassified
    # not already absorbed by the LTS 2 branch.
    if cycleway_kind in _BIKE_LANE_KINDS:
        return LTS.EXPERIENCED_ONLY
    if highway in _LTS3_HIGHWAYS:
        return LTS.EXPERIENCED_ONLY

    # Service ways (alleys, driveways, parking aisles) — assume low
    # traffic. Real OSM data tags these heavily, so absent any
    # explicit speed signal we treat them as comfortable.
    if highway == "service":
        return LTS.KID_COMFORTABLE

    return LTS.EXPERIENCED_ONLY
