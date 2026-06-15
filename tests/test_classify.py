"""Behavior tests for :func:`osm_lts.classify`.

Each parametrize case asserts a specific Furth-rule outcome with the
smallest tag bag that exercises it. Edge cases (missing tags, mph
strings with units, multi-arterial bumps, separation overriding
speed) are kept as named tests so a regression points right at the
rule that broke.
"""

from __future__ import annotations

import pytest

from osm_lts import LTS, classify


@pytest.mark.parametrize(
    "tags, expected",
    [
        # LTS 1 — separated, designated, slow-by-design
        ({"highway": "cycleway"}, LTS.KID_COMFORTABLE),
        ({"highway": "path"}, LTS.KID_COMFORTABLE),
        ({"highway": "path", "bicycle": "designated"}, LTS.KID_COMFORTABLE),
        ({"highway": "path", "bicycle": "yes"}, LTS.KID_COMFORTABLE),
        ({"highway": "living_street"}, LTS.KID_COMFORTABLE),
        (
            {"highway": "residential", "cycleway": "track"},
            LTS.KID_COMFORTABLE,
        ),
        ({"highway": "service"}, LTS.KID_COMFORTABLE),
        # LTS 2 — calm residential or bike lane on slow street
        ({"highway": "residential"}, LTS.MOST_ADULTS),
        ({"highway": "residential", "maxspeed": "25 mph"}, LTS.MOST_ADULTS),
        ({"highway": "unclassified", "maxspeed": "20 mph"}, LTS.MOST_ADULTS),
        (
            {"highway": "tertiary", "maxspeed": "25 mph", "cycleway": "lane"},
            LTS.MOST_ADULTS,
        ),
        # LTS 3 — collectors / fast residential / bike lane on faster street
        (
            {"highway": "residential", "maxspeed": "30 mph"},
            LTS.EXPERIENCED_ONLY,
        ),
        ({"highway": "tertiary"}, LTS.EXPERIENCED_ONLY),
        (
            {"highway": "secondary", "maxspeed": "30 mph"},
            LTS.EXPERIENCED_ONLY,
        ),
        (
            {"highway": "tertiary", "cycleway": "lane"},
            LTS.EXPERIENCED_ONLY,
        ),
        # LTS 4 — high-speed / arterial / multi-lane
        ({"highway": "primary"}, LTS.STRONG_AND_FEARLESS),
        ({"highway": "trunk"}, LTS.STRONG_AND_FEARLESS),
        (
            {"highway": "secondary", "maxspeed": "40 mph"},
            LTS.STRONG_AND_FEARLESS,
        ),
        (
            {
                "highway": "secondary",
                "lanes": "4",
                "maxspeed": "35 mph",
            },
            LTS.STRONG_AND_FEARLESS,
        ),
    ],
)
def test_classify(tags: dict, expected: LTS) -> None:
    assert classify(tags) == expected


@pytest.mark.parametrize(
    "highway",
    [
        "motorway",
        "motorway_link",
        "footway",
        "sidewalk",
        "steps",
        "pedestrian",
    ],
)
def test_excluded_highways_return_none(highway: str) -> None:
    assert classify({"highway": highway}) is None


def test_no_highway_tag_returns_none() -> None:
    assert classify({}) is None
    assert classify({"name": "Anywhere St"}) is None


def test_maxspeed_strips_unit_string() -> None:
    """``maxspeed: '25 mph'`` should be parsed as ``25``, not raise."""
    assert (
        classify({"highway": "residential", "maxspeed": "25 mph"})
        == LTS.MOST_ADULTS
    )


def test_lanes_strips_units_too() -> None:
    """``lanes`` is rare-but-real with weird values like ``'4;3'``."""
    assert (
        classify(
            {
                "highway": "secondary",
                "maxspeed": "35 mph",
                "lanes": "4;3",
            }
        )
        == LTS.STRONG_AND_FEARLESS
    )


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("25 mph", 25),
        ("50 km/h", 50),
        ("4", 4),
        # First run of digits only — NOT a strip-and-concatenate. ``"1.5"``
        # is 1, not 15; ``"4;3"`` is 4, not 43. The old concatenating form
        # turned a 1.5-lane calm street into "15 lanes" and tripped the
        # ``lanes >= 3`` → LTS 4 rule backwards.
        ("1.5", 1),
        ("4;3", 4),
        ("30;40", 30),
        ("none", None),
        ("", None),
        (None, None),
    ],
)
def test_coerce_int_reads_first_digit_run(raw, expected) -> None:
    from osm_lts._classify import _coerce_int

    assert _coerce_int(raw) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("25 mph", 25),
        ("30", 30),  # bare number read as mph (US convention)
        ("50 km/h", 31),  # metric converted: 50 * 0.621371 -> 31
        ("50 kmh", 31),
        ("50 kph", 31),
        ("100 km/h", 62),
        ("none", None),
        ("walk", None),
        ("signals", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_maxspeed_mph_is_unit_aware(raw, expected) -> None:
    from osm_lts import parse_maxspeed_mph

    assert parse_maxspeed_mph(raw) == expected


def test_metric_maxspeed_does_not_trip_lts4() -> None:
    # 50 km/h is 31 mph, under the > 35 mph LTS-4 threshold. Before
    # unit-aware parsing this read as 50 and forced the way to LTS 4.
    assert (
        classify({"highway": "tertiary", "maxspeed": "50 km/h"})
        == LTS.EXPERIENCED_ONLY
    )


@pytest.mark.parametrize(
    "type_tags, expected",
    [
        # No numeric maxspeed; the zone's legal default applies.
        ({"maxspeed:type": "US:rural"}, LTS.STRONG_AND_FEARLESS),  # 55 -> >35
        ({"maxspeed:type": "US:urban"}, LTS.MOST_ADULTS),  # 25 -> <=25
        # Country-qualified zone folds to the generic.
        ({"maxspeed:type": "US-CO:rural"}, LTS.STRONG_AND_FEARLESS),
        # source:maxspeed is consulted too.
        ({"source:maxspeed": "US:rural"}, LTS.STRONG_AND_FEARLESS),
        # A non-zone source:maxspeed misses the table -> highway default (25).
        ({"source:maxspeed": "sign"}, LTS.MOST_ADULTS),
    ],
)
def test_implicit_maxspeed_type(type_tags, expected) -> None:
    tags = {"highway": "residential", **type_tags}
    assert classify(tags) == expected


def test_explicit_maxspeed_beats_implicit_type() -> None:
    # An explicit number always wins over the maxspeed:type zone.
    tags = {
        "highway": "residential",
        "maxspeed": "40 mph",
        "maxspeed:type": "US:urban",
    }
    assert classify(tags) == LTS.STRONG_AND_FEARLESS


def test_implicit_maxspeed_mph_is_overridable() -> None:
    from osm_lts import Classifier

    clf = Classifier(implicit_maxspeed_mph={"US:urban": 40})
    assert clf({"highway": "residential", "maxspeed:type": "US:urban"}) == (
        LTS.STRONG_AND_FEARLESS
    )


def test_cycleway_subkey_priority() -> None:
    """``cycleway:right`` is read when the unprefixed ``cycleway`` is absent."""
    tags = {
        "highway": "tertiary",
        "maxspeed": "25 mph",
        "cycleway:right": "lane",
    }
    assert classify(tags) == LTS.MOST_ADULTS


def test_protected_track_beats_arterial_speed() -> None:
    """A ``cycleway=track`` overrides a 40 mph arterial — separation wins."""
    assert (
        classify({"highway": "primary", "cycleway": "track"})
        == LTS.KID_COMFORTABLE
    )


def test_paved_shared_use_path_is_lts1() -> None:
    """A paved multi-use path is LTS 1 regardless of the ``bicycle``
    value, since ``highway=path`` itself promotes to LTS 1.

    Tag profile from Sloan's Lake Trail in Denver, e.g.
    https://www.openstreetmap.org/way/25671996 — a real-world
    shared-use trail. Before the rule was simplified to "any
    ``highway=path``", this profile fell through to the LTS 3
    catch-all because the original rule required
    ``bicycle=designated``.
    """
    tags = {
        "bicycle": "yes",
        "foot": "yes",
        "highway": "path",
        "segregated": "no",
        "surface": "concrete",
    }
    assert classify(tags) == LTS.KID_COMFORTABLE


def test_returned_int_is_useable_as_lts_value() -> None:
    """``LTS`` is an ``IntEnum`` so JSON / CSV serialization is trivial."""
    result = classify({"highway": "residential"})
    assert int(result) == 2


def test_returns_lts_enum_not_bare_int() -> None:
    """Caller can pattern-match on the named values."""
    assert isinstance(classify({"highway": "primary"}), LTS)
