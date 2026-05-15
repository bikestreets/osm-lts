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
        ({"highway": "path", "bicycle": "designated"}, LTS.KID_COMFORTABLE),
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


def test_returned_int_is_useable_as_lts_value() -> None:
    """``LTS`` is an ``IntEnum`` so JSON / CSV serialization is trivial."""
    result = classify({"highway": "residential"})
    assert int(result) == 2


def test_returns_lts_enum_not_bare_int() -> None:
    """Caller can pattern-match on the named values."""
    assert isinstance(classify({"highway": "primary"}), LTS)
