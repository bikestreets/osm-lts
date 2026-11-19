"""Furth Level of Traffic Stress classifier.

Reference: peterfurth.sites.northeastern.edu/level-of-traffic-stress/

The classification is a four-tier scale from "kid-comfortable" (1) to
"strong-and-fearless only" (4). The rules live in ``rules.md`` beside
this module (loaded by ``_rules``); :meth:`Classifier.explain` walks
that table top to bottom and the first match wins. Order matters —
separation (a ``cycleway=track``) is checked before any speed/lane rule
can push the way up to LTS 4.

Entry points:

* :func:`classify` — module-level function using the default rules.
  Equivalent to ``Classifier().classify(tags)``.
* :func:`explain` — the same, plus the rule that decided and the inputs
  it read.
* :class:`Classifier` — frozen dataclass with overridable defaults
  (excluded highways, speed/lane fallbacks, cycleway sub-tag order).
  Construct one when you need to model a city or country whose
  posted-speed conventions or in-scope highway set differ from the
  US-centric defaults.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Mapping, Optional, Tuple

from . import _constants as C
from ._rules import DEFINITION as _D


class LTS(IntEnum):
    """Furth's Level of Traffic Stress, 1 (calmest) to 4 (most hostile)."""

    KID_COMFORTABLE = 1
    MOST_ADULTS = 2
    EXPERIENCED_ONLY = 3
    STRONG_AND_FEARLESS = 4

    @property
    def description(self) -> str:
        """Who the level suits, in Furth's terms.

        >>> LTS.MOST_ADULTS.description
        'Tolerable for most adults'
        """
        return _LTS_DESCRIPTIONS[self]


# From the levels table in rules.md.
_LTS_DESCRIPTIONS = {LTS(n): text for n, text in _D.level_descriptions.items()}


class Source(str, Enum):
    """Where a resolved input (speed, lane count) came from."""

    TAGGED = "tagged"
    """Read from the way's own tag (``maxspeed``, ``lanes``)."""
    LEGAL_DEFAULT = "legal_default"
    """A statutory default named by ``maxspeed:type`` / ``source:maxspeed``."""
    HIGHWAY_DEFAULT = "highway_default"
    """The classifier's typical value for the ``highway`` class."""
    FALLBACK = "fallback"
    """The classifier's value for a ``highway`` class it has no default for."""

    # ``str()`` and f-strings give the value on every Python version (3.12
    # changed a str-mixin Enum's ``str()`` to ``'Source.TAGGED'``).
    def __str__(self) -> str:
        return self.value

    def __format__(self, spec: str) -> str:
        return format(self.value, spec)



class Rule(str, Enum):
    """The rule that decided a way's classification, in evaluation order.

    Values are stable identifiers, safe to store or compare. Each
    member's :attr:`description` says what the rule tests.
    """

    NO_HIGHWAY = "no_highway"
    EXCLUDED_HIGHWAY = "excluded_highway"
    CYCLEWAY = "cycleway"
    PATH = "path"
    TRACK = "track"
    LIVING_STREET = "living_street"
    SEPARATED_BIKE_TRACK = "separated_bike_track"
    SPEED_OVER_35 = "speed_over_35"
    ARTERIAL = "arterial"
    MULTILANE_OVER_30 = "multilane_over_30"
    BIKE_LANE_SLOW = "bike_lane_slow"
    SLOW_RESIDENTIAL = "slow_residential"
    BIKE_LANE_FASTER = "bike_lane_faster"
    COLLECTOR = "collector"
    SERVICE = "service"
    OTHER_HIGHWAY = "other_highway"

    # As for :class:`Source`: ``str()`` / f-strings give the stable value.
    def __str__(self) -> str:
        return self.value

    def __format__(self, spec: str) -> str:
        return format(self.value, spec)

    @property
    def description(self) -> str:
        """What the rule tests, in plain language."""
        return _RULE_DESCRIPTIONS[self]


# The rules table in rules.md drives classification; these members are its
# stable public names. The table and the enum must list the same rules in
# the same order (after the two out-of-scope outcomes, which aren't rows).
_OUT_OF_SCOPE_DESCRIPTIONS = {
    Rule.NO_HIGHWAY: "No highway tag; out of scope",
    Rule.EXCLUDED_HIGHWAY: "Highway type outside the classifier's scope",
}
_TABLE_RULES = [member for member in Rule if member not in _OUT_OF_SCOPE_DESCRIPTIONS]
if [r.rule for r in _D.rules] != [member.value for member in _TABLE_RULES]:
    raise ImportError(
        "rules.md's rules table and osm_lts.Rule disagree: "
        f"{[r.rule for r in _D.rules]} vs {[m.value for m in _TABLE_RULES]}"
    )
# The rules table, unpacked once for the hot loop in ``Classifier._walk``:
# (Rule, LTS, highways, cycleway kinds, (op, n) speed test, (op, n) lanes test).
_ROWS = tuple(
    (
        Rule(row.rule),
        LTS(row.lts),
        row.highway,
        row.cycleway,
        None if row.speed_mph is None else row.speed_mph.compiled(),
        None if row.lanes is None else row.lanes.compiled(),
    )
    for row in _D.rules
)
# Every cycleway value a rule tests: the bike facilities the rules know.
FACILITY_KINDS = frozenset(
    kind for row in _D.rules if row.cycleway is not None for kind in row.cycleway
)
_RULE_DESCRIPTIONS = {
    **_OUT_OF_SCOPE_DESCRIPTIONS,
    **{Rule(row.rule): row.description for row in _D.rules},
}


@dataclass(frozen=True)
class Explanation:
    """A classification and the reason for it. See :meth:`Classifier.explain`."""

    lts: Optional[LTS]
    """LTS 1-4, or ``None`` when the way is out of scope."""
    rule: Rule
    """The rule that decided :attr:`lts`."""
    highway: Optional[str]
    speed_mph: Optional[int] = None
    """Resolved speed, or ``None`` if no rule read it before one decided."""
    speed_source: Optional[Source] = None
    lane_count: Optional[int] = None
    """Resolved lane count, or ``None`` if no rule read it before one decided."""
    lane_source: Optional[Source] = None
    cycleway_key: Optional[str] = None
    """The ``cycleway*`` key the facility was read from, if any. Reported
    for every in-scope way, whichever rule decided."""
    cycleway_kind: Optional[str] = None
    """That key's value (``lane``, ``track``, ...), if any."""


_LEADING_DIGITS_RE = re.compile(r"\d+")
# Detect a metric unit in a free-form maxspeed string ("50 km/h",
# "50 kmh", "50 kph"). Anything else — bare numbers, "25 mph" — is read
# as mph. The SQL emitter mirrors this with a ``~* 'km/?h|kmh|kph'`` test.
_KMH_RE = re.compile(r"km/?h|kmh|kph", re.IGNORECASE)
_KMH_TO_MPH = 0.621371
# Normalize a country-qualified ``maxspeed:type`` zone to its country
# generic: "US-CO:urban" -> "US:urban". Leaves an already-generic
# "US:urban" (no state segment) unchanged. Mirrored in SQL by
# ``regexp_replace(<type>, '^([A-Za-z]+)-[A-Za-z]+(:.+)$', '\1\2')``.
_MAXSPEED_TYPE_RE = re.compile(r"^([A-Za-z]+)-[A-Za-z]+(:.+)$")


def _coerce_int(value: Optional[str]) -> Optional[int]:
    """Read the first integer out of a free-form OSM tag value, else ``None``.

    OSM ``maxspeed`` and ``lanes`` are free-form strings: ``"25 mph"``,
    ``"50 km/h"``, ``"4"``, ``"4;3"``, ``"1.5"``. We consume the *first
    run of digits* and stop — so ``"25 mph"`` → ``25``, ``"1.5"`` → ``1``,
    ``"4;3"`` → ``4``. Anything with no digits returns ``None`` and the
    caller falls back to a highway-typical default.

    Earlier this stripped *all* non-digits and concatenated what was
    left, which turned ``"1.5"`` into ``15`` and ``"4;3"`` into ``43``
    — an order-of-magnitude error that, via the ``lanes >= 3`` LTS-4
    rule, flipped narrow calm streets into the high-stress bucket. The
    SQL emitter mirrors this with ``substring(<tag> from '[0-9]+')``.
    """
    if value is None:
        return None
    match = _LEADING_DIGITS_RE.search(str(value))
    return int(match.group()) if match else None


def _coerce_speed_mph(value: Optional[str]) -> Optional[int]:
    """Read an OSM ``maxspeed`` string as whole mph, else ``None``.

    Unit-aware where :func:`_coerce_int` is not: an explicit metric unit
    (``"50 km/h"``, ``"50 kmh"``, ``"50 kph"``) is converted to mph
    (→ ``31``). A bare number or an ``mph`` value is read as mph
    (``"25 mph"`` → ``25``, ``"30"`` → ``30``) — our data is US, where a
    bare ``maxspeed`` is a posted mph value rather than the OSM-spec
    km/h. Anything with no digits (``"none"``, ``"walk"``, ``"signals"``)
    returns ``None`` so the caller falls back to a default.

    Lanes keep using :func:`_coerce_int` — only speeds carry units.
    The SQL emitter mirrors this with a ``~* 'km/?h|kmh|kph'`` test and a
    ``* 0.621371`` conversion before the ``::int`` cast.
    """
    if value is None:
        return None
    s = str(value)
    match = _LEADING_DIGITS_RE.search(s)
    if match is None:
        return None
    mph = int(match.group())
    if _KMH_RE.search(s):
        mph = round(mph * _KMH_TO_MPH)
    return mph


def parse_maxspeed_mph(value: Optional[str]) -> Optional[int]:
    """Parse an OSM ``maxspeed`` tag value to whole mph, or ``None``.

    Public wrapper over the classifier's own ``maxspeed`` parse so ingest
    and preprocessing code can share one implementation instead of
    re-rolling a brittle ``strip("mph")`` parser that silently drops
    metric values. ``"25 mph"`` → ``25``, ``"50 km/h"`` → ``31``, bare
    ``"30"`` → ``30``, ``"none"`` / ``""`` / ``None`` → ``None``.
    """
    return _coerce_speed_mph(value)


def _generic_maxspeed_type(value: str) -> str:
    """``"US-CO:urban"`` → ``"US:urban"``; already-generic input unchanged."""
    match = _MAXSPEED_TYPE_RE.match(value)
    return f"{match.group(1)}{match.group(2)}" if match else value


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

    # Implicit legal defaults keyed by ``maxspeed:type`` / ``source:maxspeed``
    # zone (e.g. ``US:urban``). Consulted between an explicit numeric
    # ``maxspeed`` and the per-highway guess. dict default needs a factory
    # for the same reason ``speed_mph_by_highway`` does.
    implicit_maxspeed_mph: Mapping[str, int] = field(
        default_factory=lambda: dict(C.DEFAULT_IMPLICIT_MAXSPEED_MPH)
    )

    lane_count_by_highway: Mapping[str, int] = field(
        default_factory=lambda: dict(C.DEFAULT_LANE_COUNT_BY_HIGHWAY)
    )
    lane_count_fallback: int = C.DEFAULT_LANE_COUNT_FALLBACK

    # Tuples are immutable; safe as a direct default.
    cycleway_tag_keys: tuple = C.CYCLEWAY_TAG_KEYS

    def _resolve_implicit_mph(
        self, maxspeed_type: Optional[str]
    ) -> Optional[int]:
        """Legal default for a ``maxspeed:type`` zone, or ``None``.

        Tries the value's country-generic form (``US-CO:urban`` →
        ``US:urban``) against :attr:`implicit_maxspeed_mph`. Non-zone
        ``source:maxspeed`` values (``"sign"``, ``"survey"``) miss the
        table and return ``None``, so the caller falls through to the
        per-highway default.
        """
        if not maxspeed_type:
            return None
        key = _generic_maxspeed_type(maxspeed_type.strip())
        return self.implicit_maxspeed_mph.get(key)

    def _resolve_speed_mph(
        self,
        highway: str,
        maxspeed: Optional[str],
        maxspeed_type: Optional[str] = None,
    ) -> int:
        return self._resolve_speed_with_source(highway, maxspeed, maxspeed_type)[0]

    def _resolve_lane_count(self, highway: str, lanes: Optional[str]) -> int:
        return self._resolve_lanes_with_source(highway, lanes)[0]

    def _resolve_cycleway_kind(
        self, tags: Mapping[str, str]
    ) -> Optional[str]:
        """The value :meth:`resolve_cycleway` reports.

        Kept for callers of earlier releases; :meth:`explain` reports the
        same value as ``cycleway_kind``.
        """
        return self._cycleway(tags)[1]

    def _resolve_speed_with_source(
        self,
        highway: str,
        maxspeed: Optional[str],
        maxspeed_type: Optional[str] = None,
    ) -> tuple[int, Source]:
        """:meth:`_resolve_speed_mph` plus which input it came from."""
        explicit = _coerce_speed_mph(maxspeed)
        if explicit is not None:
            return explicit, Source.TAGGED
        implicit = self._resolve_implicit_mph(maxspeed_type)
        if implicit is not None:
            return implicit, Source.LEGAL_DEFAULT
        if highway in self.speed_mph_by_highway:
            return self.speed_mph_by_highway[highway], Source.HIGHWAY_DEFAULT
        return self.speed_mph_fallback, Source.FALLBACK

    def _resolve_lanes_with_source(
        self, highway: str, lanes: Optional[str]
    ) -> tuple[int, Source]:
        """:meth:`_resolve_lane_count` plus which input it came from."""
        explicit = _coerce_int(lanes)
        if explicit is not None:
            return explicit, Source.TAGGED
        if highway in self.lane_count_by_highway:
            return self.lane_count_by_highway[highway], Source.HIGHWAY_DEFAULT
        return self.lane_count_fallback, Source.FALLBACK

    def resolve_speed(self, tags: Mapping[str, str]) -> Tuple[int, Source]:
        """A way's speed (mph), as the rules read it, and where it came from.

        The tagged ``maxspeed``, else a legal default its ``maxspeed:type`` /
        ``source:maxspeed`` names, else this classifier's default for its
        highway type. Unlike :meth:`explain`, always resolves: for callers
        that need the speed of a way the rules didn't have to read it for
        (e.g. a street being crossed, see :func:`osm_lts.crossing_lts`).

        >>> Classifier().resolve_speed({"highway": "tertiary"})[0]
        30
        """
        return self._resolve_speed_with_source(
            tags.get("highway") or "",
            tags.get("maxspeed"),
            tags.get("maxspeed:type") or tags.get("source:maxspeed"),
        )

    def resolve_lanes(self, tags: Mapping[str, str]) -> Tuple[int, Source]:
        """A way's lane count, as the rules read it, and where it came from.

        >>> Classifier().resolve_lanes({"highway": "primary"})[0]
        4
        """
        return self._resolve_lanes_with_source(
            tags.get("highway") or "", tags.get("lanes")
        )

    def resolve_cycleway(
        self, tags: Mapping[str, str]
    ) -> Tuple[Optional[str], Optional[str]]:
        """``(key, value)`` of the way's bike facility: the first of
        :attr:`cycleway_tag_keys` whose value is a facility the rules test,
        else the first one set, else ``(None, None)``.

        >>> Classifier().resolve_cycleway({"cycleway:right": "lane"})
        ('cycleway:right', 'lane')
        """
        return self._cycleway(tags)

    def explain(self, tags: Mapping[str, str]) -> Explanation:
        """Classify ``tags`` and say why.

        Returns an :class:`Explanation` holding the LTS (``None`` when
        the way is out of scope), the :class:`Rule` that decided it, the
        way's cycleway facility, and the speed and lane count with the
        :class:`Source` each was resolved from. Speed and lane count are
        reported only if some rule read them on the way to the decision:
        a ``highway=cycleway`` is LTS 1 whatever its speed, so no speed
        is reported for it.

        This is the classifier's only rule ladder; :meth:`classify` is
        ``explain(tags).lts``.

        Examples:
            >>> e = Classifier().explain({"highway": "residential"})
            >>> int(e.lts), e.rule.value, e.speed_mph, e.speed_source.value
            (2, 'slow_residential', 25, 'highway_default')
            >>> Classifier().explain({"highway": "cycleway"}).speed_mph is None
            True
        """
        (rule, lts, highway, cycleway_key, cycleway_kind,
         speed, speed_source, lanes, lane_source) = self._walk(tags)
        return Explanation(
            lts=lts,
            rule=rule,
            highway=highway,
            speed_mph=speed,
            speed_source=speed_source,
            lane_count=lanes,
            lane_source=lane_source,
            cycleway_key=cycleway_key,
            cycleway_kind=cycleway_kind,
        )

    def _cycleway(self, tags: Mapping[str, str]) -> tuple:
        """``(key, value)`` of the way's bike facility, else ``(None, None)``.

        The first of :attr:`cycleway_tag_keys` whose value is a facility
        the rules know (:data:`FACILITY_KINDS`: ``cycleway=no`` or
        sharrows on one key don't hide a lane on another); failing that,
        the first key set at all, so its value is still reported.
        """
        first = None
        for key in self.cycleway_tag_keys:
            value = tags.get(key)
            if not value:
                continue
            if value in FACILITY_KINDS:
                return key, value
            if first is None:
                first = (key, value)
        return first or (None, None)

    def _walk(self, tags: Mapping[str, str]) -> tuple:
        """Walk the rules table in rules.md, top to bottom; first match wins.

        The one rule ladder behind :meth:`explain` and :meth:`classify`.
        Returns ``(rule, lts, highway, cycleway_key, cycleway_kind, speed,
        speed_source, lanes, lane_source)``. Plain locals rather than an
        :class:`Explanation`, so :meth:`classify` stays cheap on bulk runs.
        Speed and lanes are resolved the first time a rule tests them, so
        they're ``None`` unless something read them.
        """
        highway = tags.get("highway")
        if not highway:
            return (Rule.NO_HIGHWAY, None, None, None, None, None, None, None, None)
        if highway in self.excluded_highways:
            return (
                Rule.EXCLUDED_HIGHWAY, None, highway, None, None,
                None, None, None, None,
            )
        cycleway_key, cycleway_kind = self._cycleway(tags)
        speed = speed_source = lanes = lane_source = None
        for rule, lts, highways, kinds, speed_test, lane_test in _ROWS:
            if highways is not None and highway not in highways:
                continue
            if kinds is not None and cycleway_kind not in kinds:
                continue
            if speed_test is not None:
                if speed is None:
                    speed, speed_source = self._resolve_speed_with_source(
                        highway,
                        tags.get("maxspeed"),
                        tags.get("maxspeed:type") or tags.get("source:maxspeed"),
                    )
                if not speed_test[0](speed, speed_test[1]):
                    continue
            if lane_test is not None:
                if lanes is None:
                    lanes, lane_source = self._resolve_lanes_with_source(
                        highway, tags.get("lanes")
                    )
                if not lane_test[0](lanes, lane_test[1]):
                    continue
            return (
                rule, lts, highway, cycleway_key, cycleway_kind,
                speed, speed_source, lanes, lane_source,
            )
        # Unreachable: rules.md's last rule has no conditions (checked on load).
        raise AssertionError("no rule matched")

    def classify(self, tags: Mapping[str, str]) -> Optional[LTS]:
        """Return the Furth LTS classification for an OSM way's tags.

        See :func:`classify` for the full docstring; this method is
        the same logic with this instance's overridable defaults. Use
        :meth:`explain` for the rule and inputs behind the result.
        """
        return self._walk(tags)[1]

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
        >>> classify({"highway": "track", "tracktype": "grade2"})
        <LTS.KID_COMFORTABLE: 1>
        >>> classify({"highway": "residential", "maxspeed": "25 mph"})
        <LTS.MOST_ADULTS: 2>
        >>> classify({"highway": "primary"})
        <LTS.STRONG_AND_FEARLESS: 4>
        >>> classify({"highway": "footway"}) is None
        True
    """
    return _DEFAULT_CLASSIFIER.classify(tags)


def explain(tags: Mapping[str, str]) -> Explanation:
    """Classify ``tags`` with the default rules and say why.

    Convenience wrapper around :meth:`Classifier.explain`.

    Examples:
        >>> e = explain({"highway": "tertiary", "cycleway:right": "lane"})
        >>> int(e.lts), e.rule.value, e.cycleway_key, e.cycleway_kind
        (3, 'bike_lane_faster', 'cycleway:right', 'lane')
        >>> explain({"highway": "footway"}).rule.value
        'excluded_highway'
    """
    return _DEFAULT_CLASSIFIER.explain(tags)
