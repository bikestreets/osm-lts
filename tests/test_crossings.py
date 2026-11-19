"""Tests for crossing ratings (:func:`osm_lts.crossing_lts`) and the public
input resolvers."""

from __future__ import annotations

import pytest

from osm_lts import (
    LTS,
    Classifier,
    Source,
    crossing_lts,
    explain,
    is_crossing,
)


# Furth's LTS criteria, Table 6 ("Criteria for Unsignalized Crossings"),
# transcribed cell by cell: {speed band: (up to 3 lanes, 4-5 lanes, 6+ lanes)}.
FURTH_6A = {25: (1, 2, 4), 30: (1, 2, 4), 35: (2, 3, 4), 40: (3, 4, 4)}
FURTH_6B = {25: (1, 1, 2), 30: (1, 2, 3), 35: (2, 3, 4), 40: (3, 4, 4)}


def _band(mph: int) -> int:
    """Furth's speed band: up to 25, 30, 35, 40+; between bands, the next up."""
    return 25 if mph <= 25 else 30 if mph <= 30 else 35 if mph <= 35 else 40


def _width(lanes: int) -> int:
    return 0 if lanes <= 3 else 1 if lanes <= 5 else 2


@pytest.mark.parametrize("refuge, table", [(False, FURTH_6A), (True, FURTH_6B)])
def test_crossing_tables_are_furths_table_6(refuge: bool, table) -> None:
    for lanes in range(0, 11):
        for mph in range(0, 81):
            expected = table[_band(mph)][_width(lanes)]
            assert int(crossing_lts(lanes, mph, refuge=refuge)) == expected, (
                lanes,
                mph,
                refuge,
            )


def test_signalized_is_lts_1() -> None:
    assert crossing_lts(8, 55, signalized=True) == LTS.KID_COMFORTABLE
    assert crossing_lts(8, 55, signalized=True, refuge=True) == LTS.KID_COMFORTABLE


@pytest.mark.parametrize(
    "tags, expected",
    [
        ({"highway": "footway", "footway": "crossing"}, True),
        ({"highway": "cycleway", "cycleway": "crossing"}, True),
        ({"highway": "path", "path": "crossing"}, True),
        ({"highway": "pedestrian", "footway": "crossing"}, True),
        ({"highway": "footway", "footway": "sidewalk"}, False),
        ({"highway": "residential", "footway": "crossing"}, False),
        ({"highway": "footway"}, False),
    ],
)
def test_is_crossing(tags, expected) -> None:
    assert is_crossing(tags) is expected


@pytest.mark.parametrize(
    "tags, expected",
    [
        ({"highway": "cycleway", "crossing": "traffic_signals"}, True),
        ({"highway": "footway", "crossing": "marked"}, True),
        ({"highway": "footway", "crossing": "no"}, False),
        ({"highway": "residential", "crossing": "marked"}, False),
    ],
)
def test_a_crossing_tag_marks_a_crossing_way(tags, expected) -> None:
    assert is_crossing(tags) is expected


@pytest.mark.parametrize(
    "tags",
    [
        {"highway": "residential"},
        {"highway": "residential", "maxspeed": "35", "lanes": "4;3"},
        {"highway": "tertiary", "maxspeed:type": "US-CO:urban"},
        {"highway": "primary", "cycleway:right": "lane"},
        {"highway": "road", "lanes": "two"},
    ],
)
def test_resolvers_agree_with_explain_where_explain_read_them(tags) -> None:
    clf = Classifier()
    e = explain(tags)
    if e.speed_mph is not None:
        assert clf.resolve_speed(tags) == (e.speed_mph, e.speed_source)
    if e.lane_count is not None:
        assert clf.resolve_lanes(tags) == (e.lane_count, e.lane_source)
    assert clf.resolve_cycleway(tags) == (e.cycleway_key, e.cycleway_kind)


def test_resolvers_always_resolve() -> None:
    clf = Classifier()
    # explain never reads lanes for a 25 mph street; the resolver still does.
    assert explain({"highway": "residential"}).lane_count is None
    assert clf.resolve_lanes({"highway": "residential"}) == (2, Source.HIGHWAY_DEFAULT)
    assert clf.resolve_speed({"highway": "residential", "maxspeed": "20 mph"}) == (
        20,
        Source.TAGGED,
    )
    assert clf.resolve_cycleway({"highway": "residential"}) == (None, None)


def test_signal_and_refuge_tags() -> None:
    from osm_lts import has_refuge, is_signalized

    assert is_signalized({"highway": "footway", "crossing": "traffic_signals"})
    assert is_signalized({"crossing:signals": "yes"})
    assert is_signalized({"highway": "traffic_signals"})  # a signal node
    assert not is_signalized({"crossing": "uncontrolled"})
    assert has_refuge({"crossing:island": "yes"})
    assert has_refuge({"traffic_calming": "island"})
    assert has_refuge({"crossing": "island"})  # older tagging, still common
    assert not has_refuge({"crossing:island": "no"})


def test_unresolved_inputs_are_a_clear_error() -> None:
    e = explain({"highway": "residential"})
    with pytest.raises(ValueError, match="resolve_lanes"):
        crossing_lts(e.lane_count, e.speed_mph)


def test_a_refuge_never_makes_a_crossing_worse() -> None:
    for lanes in range(0, 11):
        for mph in range(0, 81):
            assert crossing_lts(lanes, mph, refuge=True) <= crossing_lts(lanes, mph)


def test_more_signal_tags_and_explicit_no() -> None:
    from osm_lts import is_signalized

    assert is_signalized({"crossing_ref": "toucan"})
    assert is_crossing({"highway": "footway", "footway": "crossing", "crossing": "no"}) is False


def test_contraflow_track_is_separated() -> None:
    from osm_lts import Rule

    e = explain({"highway": "tertiary", "maxspeed": "25", "cycleway": "opposite_track"})
    assert (e.rule, int(e.lts)) == (Rule.SEPARATED_BIKE_TRACK, 1)
