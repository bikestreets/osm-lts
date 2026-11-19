"""Tests for :func:`osm_lts.explain` / :meth:`osm_lts.Classifier.explain`."""

from __future__ import annotations

import pytest

from osm_lts import (
    CYCLEWAY_TAG_KEYS,
    LTS,
    Classifier,
    Explanation,
    Rule,
    Source,
    classify,
    explain,
)
from osm_lts.sql import excluded_highways_in_list, lts_case_expression

# One tag set per rule, in evaluation order.
RULE_CASES = [
    ({"name": "No highway"}, Rule.NO_HIGHWAY, None),
    ({"highway": "footway"}, Rule.EXCLUDED_HIGHWAY, None),
    ({"highway": "cycleway"}, Rule.CYCLEWAY, LTS.KID_COMFORTABLE),
    ({"highway": "path"}, Rule.PATH, LTS.KID_COMFORTABLE),
    ({"highway": "track"}, Rule.TRACK, LTS.KID_COMFORTABLE),
    ({"highway": "living_street"}, Rule.LIVING_STREET, LTS.KID_COMFORTABLE),
    (
        {"highway": "primary", "cycleway:right": "track", "maxspeed": "45 mph"},
        Rule.SEPARATED_BIKE_TRACK,
        LTS.KID_COMFORTABLE,
    ),
    (
        {"highway": "secondary", "maxspeed": "40 mph"},
        Rule.SPEED_OVER_35,
        LTS.STRONG_AND_FEARLESS,
    ),
    (
        {"highway": "trunk", "maxspeed": "25 mph"},
        Rule.ARTERIAL,
        LTS.STRONG_AND_FEARLESS,
    ),
    (
        {"highway": "tertiary", "lanes": "4", "maxspeed": "35 mph"},
        Rule.MULTILANE_OVER_30,
        LTS.STRONG_AND_FEARLESS,
    ),
    (
        {"highway": "tertiary", "cycleway": "lane", "maxspeed": "25 mph"},
        Rule.BIKE_LANE_SLOW,
        LTS.MOST_ADULTS,
    ),
    ({"highway": "residential"}, Rule.SLOW_RESIDENTIAL, LTS.MOST_ADULTS),
    (
        {"highway": "secondary", "cycleway:left": "lane", "maxspeed": "30 mph"},
        Rule.BIKE_LANE_FASTER,
        LTS.EXPERIENCED_ONLY,
    ),
    ({"highway": "tertiary"}, Rule.COLLECTOR, LTS.EXPERIENCED_ONLY),
    ({"highway": "service"}, Rule.SERVICE, LTS.KID_COMFORTABLE),
    ({"highway": "busway"}, Rule.OTHER_HIGHWAY, LTS.EXPERIENCED_ONLY),
]

# Which inputs each RULE_CASES way had read by the time a rule decided it.
# Speed is first tested by speed_over_35, lanes by multilane_over_30 (and
# only when the speed part of that rule passes).
READ = {
    Rule.SPEED_OVER_35: {"speed"},
    Rule.ARTERIAL: {"speed"},
    Rule.MULTILANE_OVER_30: {"speed", "lanes"},
    Rule.BIKE_LANE_SLOW: {"speed"},  # 25 mph: the lanes test isn't reached
    Rule.SLOW_RESIDENTIAL: {"speed"},
    Rule.BIKE_LANE_FASTER: {"speed"},  # 30 mph is not > 30: lanes not reached
    Rule.COLLECTOR: {"speed"},
    Rule.SERVICE: {"speed"},
    Rule.OTHER_HIGHWAY: {"speed"},
}


@pytest.mark.parametrize("tags, rule, lts", RULE_CASES)
def test_each_rule(tags, rule, lts) -> None:
    result = explain(tags)
    assert isinstance(result, Explanation)
    assert (result.rule, result.lts) == (rule, lts)
    assert classify(tags) == lts


def test_every_rule_is_covered_and_described() -> None:
    assert {rule for _, rule, _ in RULE_CASES} == set(Rule)
    for rule in Rule:
        assert rule.description


@pytest.mark.parametrize("tags, rule, lts", RULE_CASES)
def test_reports_exactly_the_inputs_that_were_read(tags, rule, lts) -> None:
    result = explain(tags)
    read = READ.get(rule, set())
    assert (result.speed_mph is not None) == ("speed" in read)
    assert (result.speed_source is not None) == ("speed" in read)
    assert (result.lane_count is not None) == ("lanes" in read)
    assert (result.lane_source is not None) == ("lanes" in read)


def test_classify_is_explain_lts_under_overrides() -> None:
    clf = Classifier(speed_mph_fallback=40, lane_count_fallback=3)
    for tags, _, _ in RULE_CASES + [({"highway": "road"}, None, None)]:
        assert clf.classify(tags) == clf.explain(tags).lts


@pytest.mark.parametrize(
    "tags, speed, source",
    [
        ({"highway": "residential", "maxspeed": "20 mph"}, 20, Source.TAGGED),
        ({"highway": "residential", "maxspeed": "50 km/h"}, 31, Source.TAGGED),
        (
            {"highway": "residential", "maxspeed:type": "US-CO:urban"},
            25,
            Source.LEGAL_DEFAULT,
        ),
        ({"highway": "residential"}, 25, Source.HIGHWAY_DEFAULT),
        ({"highway": "road"}, 25, Source.FALLBACK),
    ],
)
def test_speed_source(tags, speed, source) -> None:
    result = explain(tags)
    assert (result.speed_mph, result.speed_source) == (speed, source)


@pytest.mark.parametrize(
    "tags, lanes, source",
    [
        # 35 mph puts each one past the speed half of multilane_over_30,
        # so its lanes are read.
        ({"highway": "tertiary", "maxspeed": "35", "lanes": "4;3"}, 4, Source.TAGGED),
        (
            {"highway": "residential", "maxspeed": "35", "lanes": "two"},
            2,
            Source.HIGHWAY_DEFAULT,
        ),
        ({"highway": "tertiary", "maxspeed": "35"}, 2, Source.FALLBACK),
    ],
)
def test_lane_source(tags, lanes, source) -> None:
    result = explain(tags)
    assert (result.lane_count, result.lane_source) == (lanes, source)


def test_reports_the_cycleway_key_that_won() -> None:
    result = explain(
        {"highway": "tertiary", "cycleway:left": "track", "cycleway": "lane"}
    )
    assert (result.cycleway_key, result.cycleway_kind) == ("cycleway", "lane")
    assert explain({"highway": "tertiary"}).cycleway_key is None


def test_level_descriptions() -> None:
    assert [level.description for level in LTS] == [
        "Suitable for children",
        "Tolerable for most adults",
        "Tolerable for enthused and confident adults",
        "Tolerable only for strong and fearless riders",
    ]


# ---------------------------------------------------------------------------
# A classifier that excludes nothing
# ---------------------------------------------------------------------------


def test_empty_exclusion_set_rates_every_highway() -> None:
    clf = Classifier(excluded_highways=frozenset())
    assert clf.classify({"highway": "footway"}) == LTS.EXPERIENCED_ONLY
    assert clf.explain({"name": "x"}).rule == Rule.NO_HIGHWAY


def test_empty_exclusion_set_emits_valid_sql() -> None:
    sql = lts_case_expression(classifier=Classifier(excluded_highways=frozenset()))
    assert "IN ()" not in sql
    assert "IS NULL OR (tags::jsonb)->>'highway' = '' THEN NULL" in sql


def test_empty_exclusion_set_has_no_in_list() -> None:
    with pytest.raises(ValueError, match="empty"):
        excluded_highways_in_list(Classifier(excluded_highways=frozenset()))


# ---------------------------------------------------------------------------
# Stable text, and inputs Python and SQL must read the same way
# ---------------------------------------------------------------------------


def test_rule_and_source_format_as_their_values() -> None:
    e = explain({"highway": "residential"})
    assert (str(e.rule), f"{e.rule}") == ("slow_residential", "slow_residential")
    assert (str(e.speed_source), f"{e.speed_source}") == (
        "highway_default",
        "highway_default",
    )


def test_empty_values_count_as_missing() -> None:
    # An empty cycleway doesn't hide a later key's facility...
    tags = {"highway": "tertiary", "cycleway": "", "cycleway:right": "track"}
    assert explain(tags).rule == Rule.SEPARATED_BIKE_TRACK
    # ...an empty highway is unrated...
    assert explain({"highway": ""}).rule == Rule.NO_HIGHWAY
    # ...and an empty maxspeed:type falls through to source:maxspeed.
    tags = {"highway": "residential", "maxspeed:type": "", "source:maxspeed": "US:rural"}
    assert explain(tags).speed_mph == 55


def test_sql_treats_empty_values_as_missing_too() -> None:
    sql = lts_case_expression()
    assert "NULLIF((tags::jsonb)->>'cycleway', '')" in sql
    assert "NULLIF((tags::jsonb)->>'maxspeed:type', '')" in sql
    assert r"regexp_replace(COALESCE(" in sql and r"'^\s+|\s+$', '', 'g'" in sql


def test_private_cycleway_resolver_is_kept_for_earlier_callers() -> None:
    clf = Classifier()
    assert clf._resolve_cycleway_kind({"cycleway:left": "lane"}) == "lane"
    assert clf._resolve_cycleway_kind({"cycleway": ""}) is None


def test_shared_lane_markings_are_mixed_traffic() -> None:
    # Sharrows aren't a bike lane in Furth's method: a 25 mph collector with
    # them is rated as mixed traffic, like one without.
    sharrows = {"highway": "tertiary", "cycleway": "shared_lane", "maxspeed": "25"}
    assert explain(sharrows).rule == Rule.COLLECTOR
    assert explain(sharrows).lts == LTS.EXPERIENCED_ONLY
    # A calm residential street is LTS 2 by its own rule either way.
    calm = {"highway": "residential", "cycleway": "shared_lane", "maxspeed": "25"}
    assert explain(calm).rule == Rule.SLOW_RESIDENTIAL
    # A contraflow lane is a lane.
    contra = {"highway": "tertiary", "cycleway": "opposite_lane", "maxspeed": "25"}
    assert explain(contra).rule == Rule.BIKE_LANE_SLOW


def test_sql_rates_shared_lane_markings_as_mixed_traffic() -> None:
    sql = lts_case_expression()
    branch = sql[sql.index("-- bike_lane_slow"):sql.index("-- slow_residential")]
    assert "'lane'" in branch and "'opposite_lane'" in branch
    assert "shared_lane" not in branch


@pytest.mark.parametrize(
    "tags, key, kind, rule",
    [
        # `no` or sharrows on an earlier key don't hide a later key's lane.
        (
            {"highway": "tertiary", "maxspeed": "25", "cycleway": "no", "cycleway:right": "lane"},
            "cycleway:right",
            "lane",
            Rule.BIKE_LANE_SLOW,
        ),
        (
            {
                "highway": "tertiary",
                "maxspeed": "25",
                "cycleway:right": "shared_lane",
                "cycleway:left": "lane",
            },
            "cycleway:left",
            "lane",
            Rule.BIKE_LANE_SLOW,
        ),
        # With no facility anywhere, the first value set is still reported.
        (
            {"highway": "tertiary", "maxspeed": "25", "cycleway": "no"},
            "cycleway",
            "no",
            Rule.COLLECTOR,
        ),
        # Two facilities: the first key wins, as before.
        (
            {
                "highway": "tertiary",
                "maxspeed": "25",
                "cycleway:right": "lane",
                "cycleway:left": "track",
            },
            "cycleway:right",
            "lane",
            Rule.BIKE_LANE_SLOW,
        ),
    ],
)
def test_the_facility_is_the_first_key_with_one(tags, key, kind, rule) -> None:
    e = explain(tags)
    assert (e.cycleway_key, e.cycleway_kind, e.rule) == (key, kind, rule)
    # The SQL picks the same key: every known-facility term, in key order,
    # before any first-set term.
    from osm_lts.sql import cycleway_kind_expression

    sql = cycleway_kind_expression()
    known = [sql.index(f"CASE WHEN (tags::jsonb)->>'{k}' IN (") for k in CYCLEWAY_TAG_KEYS]
    first = [sql.index(f"NULLIF((tags::jsonb)->>'{k}', '')") for k in CYCLEWAY_TAG_KEYS]
    assert known == sorted(known) and first == sorted(first)
    assert max(known) < min(first)
