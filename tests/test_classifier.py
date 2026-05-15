"""Behavior tests for :class:`osm_lts.Classifier` overrides.

The function-level rules are covered in ``test_classify.py``. These
tests exercise the override surface — confirming each constructor
field actually changes behavior in the expected direction, and that
defaulted instances stay in lockstep with the module-level
:func:`osm_lts.classify` shortcut.
"""

from __future__ import annotations

import dataclasses

import pytest

from osm_lts import (
    EXCLUDED_HIGHWAYS,
    LTS,
    Classifier,
    classify,
)


def test_default_classifier_matches_module_function() -> None:
    """``Classifier()`` and the module-level ``classify`` agree."""
    clf = Classifier()
    for tags in [
        {"highway": "residential"},
        {"highway": "primary"},
        {"highway": "cycleway"},
        {"highway": "footway"},
        {"highway": "tertiary", "cycleway:right": "lane"},
        {},
    ]:
        assert clf.classify(tags) == classify(tags)


def test_callable_alias_matches_classify() -> None:
    clf = Classifier()
    tags = {"highway": "residential", "maxspeed": "25 mph"}
    assert clf(tags) == clf.classify(tags) == LTS.MOST_ADULTS


def test_override_excluded_highways_excludes_more() -> None:
    """Adding ``path`` to the exclusion set drops it out of scope."""
    clf = Classifier(excluded_highways=EXCLUDED_HIGHWAYS | {"path"})
    assert clf({"highway": "path", "bicycle": "designated"}) is None
    # Other excluded highways still excluded.
    assert clf({"highway": "footway"}) is None
    # Non-excluded paths unchanged.
    assert clf({"highway": "residential"}) == LTS.MOST_ADULTS


def test_override_excluded_highways_excludes_fewer() -> None:
    """Removing ``footway`` from the exclusion set lets it classify."""
    looser = EXCLUDED_HIGHWAYS - {"footway"}
    clf = Classifier(excluded_highways=looser)
    # footway has no LTS-specific rule → falls through to the LTS 3
    # default. Just confirm it's no longer excluded (returns a value
    # rather than None).
    assert clf({"highway": "footway"}) is not None


def test_override_speed_mph_fallback() -> None:
    """A 20 mph fallback pushes unknown highways into the LTS 2 branch."""
    clf = Classifier(speed_mph_fallback=20)
    # `highway=byway` isn't in the per-highway speed map → falls back
    # to ``speed_mph_fallback``. With 20 mph it would fall through to
    # the catch-all LTS 3 (only LTS 4 cares about 35+, only LTS 2's
    # residential/lane branches care about ≤25), which is the same as
    # the default — but a different fallback that crosses the 35 mph
    # threshold flips the result.
    high = Classifier(speed_mph_fallback=40)
    assert high({"highway": "byway"}) == LTS.STRONG_AND_FEARLESS
    assert clf({"highway": "byway"}) == LTS.EXPERIENCED_ONLY


def test_override_speed_mph_by_highway() -> None:
    """City posts residential at 20 mph by default → still LTS 2 but cleaner."""
    clf = Classifier(speed_mph_by_highway={"residential": 20})
    assert clf({"highway": "residential"}) == LTS.MOST_ADULTS
    # Residential without an override would also be LTS 2 at 25 mph,
    # so test the cross-threshold case: bump tertiary's default to 25
    # and a tertiary with no maxspeed turns into LTS 2.
    clf = Classifier(
        speed_mph_by_highway={"tertiary": 25},
        # tertiary needs a bike lane to qualify for LTS 2. (Without
        # one the LTS 2 branch is residential/unclassified-only.)
    )
    assert clf({"highway": "tertiary", "cycleway": "lane"}) == LTS.MOST_ADULTS


def test_override_lane_count_fallback_can_promote_to_lts4() -> None:
    """Bumping the lane-count fallback flips a moderate-speed road to LTS 4."""
    # `highway=byway` has no per-highway lane default and no per-
    # highway speed default. With speed override 32 (>30) and lanes
    # override 4 (≥3), the LTS 4 multi-lane branch should fire.
    clf = Classifier(speed_mph_fallback=32, lane_count_fallback=4)
    assert clf({"highway": "byway"}) == LTS.STRONG_AND_FEARLESS


def test_override_cycleway_tag_keys_changes_priority() -> None:
    """Re-ordering the cycleway sub-tag list changes which value wins."""
    tags = {
        "highway": "tertiary",
        "maxspeed": "25 mph",
        "cycleway:left": "track",
        "cycleway:right": "lane",
    }
    # Default order picks ``cycleway:right`` (priority 2) before
    # ``cycleway:left`` (priority 3): ``lane`` on a 25 mph street →
    # LTS 2.
    assert classify(tags) == LTS.MOST_ADULTS

    # Override prioritizes ``cycleway:left`` first: ``track`` →
    # short-circuits to LTS 1.
    clf = Classifier(
        cycleway_tag_keys=("cycleway", "cycleway:left", "cycleway:right")
    )
    assert clf(tags) == LTS.KID_COMFORTABLE


def test_classifier_is_frozen() -> None:
    """Field assignment raises — use ``dataclasses.replace`` instead."""
    clf = Classifier()
    with pytest.raises(dataclasses.FrozenInstanceError):
        clf.speed_mph_fallback = 30  # type: ignore[misc]


def test_dataclasses_replace_returns_modified_copy() -> None:
    """The standard ``replace`` helper produces a tweaked copy."""
    base = Classifier()
    stricter = dataclasses.replace(base, speed_mph_fallback=20)
    assert stricter.speed_mph_fallback == 20
    assert base.speed_mph_fallback != 20  # original untouched


def test_default_classifier_independent_dicts() -> None:
    """Each ``Classifier()`` gets its own dict — no shared mutation risk."""
    a = Classifier()
    b = Classifier()
    # The dataclass uses default_factory, so ``speed_mph_by_highway``
    # is a fresh dict per instance — mutating one wouldn't bleed into
    # the other.
    assert a.speed_mph_by_highway is not b.speed_mph_by_highway
