"""Furth Level of Traffic Stress classifier.

Reference: peterfurth.sites.northeastern.edu/level-of-traffic-stress/

The classification is a four-tier scale from "kid-comfortable" (1) to
"strong-and-fearless only" (4). The branches below evaluate top-to-
bottom; the first match wins. Order matters — separation (a
``cycleway=track``) short-circuits before any speed/lane bump can
push the way up to LTS 4.

Two entry points:

* :func:`classify` — module-level function using the default rules.
  Equivalent to ``Classifier().classify(tags)``.
* :class:`Classifier` — frozen dataclass with overridable defaults
  (excluded highways, speed/lane fallbacks, cycleway sub-tag order).
  Construct one when you need to model a city or country whose
  posted-speed conventions or in-scope highway set differ from the
  US-centric defaults.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
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
# Rule-tier sets live in ``_constants`` so the SQL emitter can read
# the same definitions — adding a new arterial type stays a one-
# place edit. Aliased here for readability of the rule branches.
_BIKE_LANE_KINDS = C._BIKE_LANE_KINDS
_LTS3_HIGHWAYS = C._LTS3_HIGHWAYS
_LTS4_HIGHWAYS = C._LTS4_HIGHWAYS


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


@dataclass(frozen=True)
class Classifier:
    """Configurable Furth LTS classifier.

    All fields default to the public module-level constants, so a
    bare ``Classifier()`` is equivalent to calling :func:`classify`.
    Override fields to model a region whose conventions differ from
    the US-centric defaults: a city with stricter posted-speed
    fallbacks, a country whose ``footway``-tagged ways are commonly
    rideable, etc.

    The dataclass is frozen so an instance is hashable and safe to
    share across threads. To "modify" a classifier, use
    :meth:`dataclasses.replace`.

    Examples:
        Default behavior::

            >>> Classifier()({"highway": "residential"})
            <LTS.MOST_ADULTS: 2>

        Stricter unknown-speed default (treat unknowns as 20 mph)::

            >>> clf = Classifier(speed_mph_fallback=20)
            >>> clf({"highway": "residential"})
            <LTS.MOST_ADULTS: 2>

        Also exclude pedestrian-priority paths from scope::

            >>> from osm_lts import EXCLUDED_HIGHWAYS
            >>> clf = Classifier(
            ...     excluded_highways=EXCLUDED_HIGHWAYS | {"path"}
            ... )
            >>> clf({"highway": "path", "bicycle": "designated"}) is None
            True
    """

    # frozenset is itself immutable, so a shared module-level default
    # is safe — the dataclass machinery doesn't raise on it the way
    # it would on dict/list/set defaults.
    excluded_highways: frozenset = C.EXCLUDED_HIGHWAYS

    # ``Mapping`` defaults need a factory: dict is mutable so Python
    # would otherwise share one dict across every Classifier instance,
    # which would be both surprising and a source of mutation bugs.
    speed_mph_by_highway: Mapping[str, int] = field(
        default_factory=lambda: dict(C.DEFAULT_SPEED_MPH_BY_HIGHWAY)
    )
    speed_mph_fallback: int = C.DEFAULT_SPEED_MPH_FALLBACK

    lane_count_by_highway: Mapping[str, int] = field(
        default_factory=lambda: dict(C.DEFAULT_LANE_COUNT_BY_HIGHWAY)
    )
    lane_count_fallback: int = C.DEFAULT_LANE_COUNT_FALLBACK

    # Tuples are immutable; safe as a direct default.
    cycleway_tag_keys: tuple = C.CYCLEWAY_TAG_KEYS

    def _resolve_speed_mph(self, highway: str, maxspeed: Optional[str]) -> int:
        explicit = _coerce_int(maxspeed)
        if explicit is not None:
            return explicit
        return self.speed_mph_by_highway.get(highway, self.speed_mph_fallback)

    def _resolve_lane_count(self, highway: str, lanes: Optional[str]) -> int:
        explicit = _coerce_int(lanes)
        if explicit is not None:
            return explicit
        return self.lane_count_by_highway.get(highway, self.lane_count_fallback)

    def _resolve_cycleway_kind(
        self, tags: Mapping[str, str]
    ) -> Optional[str]:
        """First non-empty cycleway* value, in :attr:`cycleway_tag_keys` order."""
        for key in self.cycleway_tag_keys:
            value = tags.get(key)
            if value:
                return value
        return None

    def classify(self, tags: Mapping[str, str]) -> Optional[LTS]:
        """Return the Furth LTS classification for an OSM way's tags.

        See :func:`classify` for the full docstring; this method is
        the same logic with this instance's overridable defaults.
        """
        highway = tags.get("highway")
        if not highway or highway in self.excluded_highways:
            return None

        bicycle = tags.get("bicycle")
        cycleway_kind = self._resolve_cycleway_kind(tags)
        speed_mph = self._resolve_speed_mph(highway, tags.get("maxspeed"))
        lane_count = self._resolve_lane_count(highway, tags.get("lanes"))

        # LTS 1 — separated paths, designated bike infrastructure,
        # slow-by-design streets. Short-circuits before any speed/
        # lane bump: a `cycleway=track` on a 40 mph arterial still
        # returns 1 because the rider is physically separated from
        # traffic.
        if highway == "cycleway":
            return LTS.KID_COMFORTABLE
        if highway == "path" and bicycle == "designated":
            return LTS.KID_COMFORTABLE
        if highway == "living_street":
            return LTS.KID_COMFORTABLE
        if cycleway_kind == "track":
            return LTS.KID_COMFORTABLE

        # LTS 4 — high-speed, multi-lane arterial, or trunk/primary
        # by tag class. A painted bike lane on a >35 mph 6-lane road
        # is still LTS 4; paint doesn't reduce stress on a hostile
        # street.
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

        # LTS 3 — moderate-speed mixed traffic, bike lane on a
        # faster street, tertiary collectors, or any residential/
        # unclassified not already absorbed by the LTS 2 branch.
        if cycleway_kind in _BIKE_LANE_KINDS:
            return LTS.EXPERIENCED_ONLY
        if highway in _LTS3_HIGHWAYS:
            return LTS.EXPERIENCED_ONLY

        # Service ways (alleys, driveways, parking aisles) — assume
        # low traffic. Real OSM data tags these heavily, so absent
        # any explicit speed signal we treat them as comfortable.
        if highway == "service":
            return LTS.KID_COMFORTABLE

        return LTS.EXPERIENCED_ONLY

    # Calling a classifier directly is the ergonomic API:
    #     clf = Classifier(...)
    #     clf(tags)
    def __call__(self, tags: Mapping[str, str]) -> Optional[LTS]:
        return self.classify(tags)


# Singleton used by the module-level :func:`classify` shortcut. Frozen
# dataclass + immutable defaults make this safe to share across calls
# and threads.
_DEFAULT_CLASSIFIER = Classifier()


def classify(tags: Mapping[str, str]) -> Optional[LTS]:
    """Return the Furth LTS classification for an OSM way's tags.

    Convenience wrapper around a default-configured
    :class:`Classifier`. For custom defaults or a different in-scope
    highway set, instantiate a :class:`Classifier` directly.

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
    return _DEFAULT_CLASSIFIER.classify(tags)
