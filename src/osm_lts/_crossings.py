"""Furth's rating of a street crossing, from the crossing tables in ``rules.md``.

Riding along a calm street and crossing a hostile one are rated separately:
a crossing is LTS 1 at a signal, and otherwise depends on how many lanes are
crossed and how fast traffic is (Mekuria, Furth & Nixon 2012, Table 2,
approximated). Which streets a route crosses, and where, needs the way
network; that's left to the caller, who passes each crossed street's lanes
and speed here (resolved with :meth:`osm_lts.Classifier.resolve_lanes` /
:meth:`~osm_lts.Classifier.resolve_speed` to match the segment rules).
"""

from __future__ import annotations

from typing import Mapping, Optional, Tuple

from ._classify import LTS
from ._rules import DEFINITION as _D
from ._rules import CrossingRow

UNSIGNALIZED_CROSSINGS: Tuple[CrossingRow, ...] = _D.unsignalized_crossings
"""Furth's Table 6a (no crossing island), in order: the first matching row
decides."""

REFUGE_CROSSINGS: Tuple[CrossingRow, ...] = _D.refuge_crossings
"""Furth's Table 6b (with a crossing island), in order."""

CROSSING_HIGHWAYS = _D.crossing_highways
CROSSING_KEYS = _D.crossing_keys
CROSSING_MARKER_KEYS = _D.crossing_marker_keys
CROSSING_SIGNAL_TAGS: Tuple[Tuple[str, str], ...] = _D.crossing_signal_tags
CROSSING_REFUGE_TAGS: Tuple[Tuple[str, str], ...] = _D.crossing_refuge_tags


def is_crossing(tags: Mapping[str, str]) -> bool:
    """Whether a way is a crossing way (e.g. ``highway=footway`` +
    ``footway=crossing``).

    >>> is_crossing({"highway": "footway", "footway": "crossing"})
    True
    >>> is_crossing({"highway": "cycleway", "crossing": "traffic_signals"})
    True
    >>> is_crossing({"highway": "footway", "footway": "sidewalk"})
    False
    """
    if tags.get("highway") not in CROSSING_HIGHWAYS:
        return False
    if any(tags.get(key) == "no" for key in CROSSING_MARKER_KEYS):
        return False  # explicitly not a crossing
    return any(tags.get(key) == "crossing" for key in CROSSING_KEYS) or any(
        tags.get(key) not in (None, "", "no") for key in CROSSING_MARKER_KEYS
    )


def is_signalized(tags: Mapping[str, str]) -> bool:
    """Whether a crossing way's (or a node's) tags mark a signal.

    >>> is_signalized({"crossing": "traffic_signals"})
    True
    """
    return any(tags.get(k) == v for k, v in CROSSING_SIGNAL_TAGS)


def has_refuge(tags: Mapping[str, str]) -> bool:
    """Whether a crossing way's (or a node's) tags mark a median refuge.

    >>> has_refuge({"crossing:island": "yes"})
    True
    """
    return any(tags.get(k) == v for k, v in CROSSING_REFUGE_TAGS)


def crossing_lts(
    lanes: Optional[int],
    speed_mph: Optional[int],
    *,
    refuge: bool = False,
    signalized: bool = False,
) -> LTS:
    """The LTS of crossing a street of ``lanes`` lanes (all crossed, both
    directions) at ``speed_mph``: Furth's Table 6.

    Resolve the inputs with :meth:`~osm_lts.Classifier.resolve_lanes` /
    ``resolve_speed``, not :func:`~osm_lts.explain` (whose fields are
    ``None`` when no rule read them). ``signalized``: LTS 1. ``refuge``: a
    crossing island (median refuge), Table 6b instead of 6a. A divided road
    is one crossing: both carriageways' lanes, with ``refuge=True``.

    >>> int(crossing_lts(2, 25)), int(crossing_lts(4, 35)), int(crossing_lts(6, 25))
    (1, 3, 4)
    >>> int(crossing_lts(4, 25, refuge=True)), int(crossing_lts(6, 25, refuge=True))
    (1, 2)
    >>> int(crossing_lts(6, 45, signalized=True))
    1
    """
    if signalized:
        return LTS.KID_COMFORTABLE
    if lanes is None or speed_mph is None:
        raise ValueError(
            "crossing_lts needs the crossed street's lanes and speed; resolve "
            "them with Classifier.resolve_lanes / resolve_speed"
        )
    table = REFUGE_CROSSINGS if refuge else UNSIGNALIZED_CROSSINGS
    return LTS(next(row.lts for row in table if row.matches(lanes, speed_mph)))
