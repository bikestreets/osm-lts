"""Structural tests for the SQL emitter.

These tests assert that the emitted SQL contains the expected
fragments — they don't require a live PostgreSQL. A separate parity
suite (run by consumers against their own database) is the right
place to verify Python ↔ SQL agreement on real data; for the
package, structural assertions plus the shared-constants design
keep the two forms in lockstep.
"""

from __future__ import annotations

import dataclasses

import pytest

from osm_lts import EXCLUDED_HIGHWAYS, Classifier, classify
from osm_lts.sql import (
    cycleway_kind_expression,
    excluded_highways_in_list,
    lane_count_expression,
    lts_case_expression,
    speed_mph_expression,
)


# ---------------------------------------------------------------------------
# excluded_highways_in_list
# ---------------------------------------------------------------------------


def test_excluded_in_list_contains_default_motorway() -> None:
    assert "'motorway'" in excluded_highways_in_list()


def test_excluded_in_list_is_sorted_for_stable_output() -> None:
    out = excluded_highways_in_list()
    items = [s.strip().strip("'") for s in out.split(",")]
    assert items == sorted(items)


def test_excluded_in_list_picks_up_classifier_override() -> None:
    clf = Classifier(excluded_highways=EXCLUDED_HIGHWAYS | {"track"})
    assert "'track'" in excluded_highways_in_list(clf)


# ---------------------------------------------------------------------------
# speed_mph_expression
# ---------------------------------------------------------------------------


def test_speed_expression_includes_default_residential_branch() -> None:
    out = speed_mph_expression()
    assert "WHEN tags::jsonb->>'highway' = 'residential' THEN 25" in out


def test_speed_expression_else_uses_classifier_fallback() -> None:
    clf = Classifier(speed_mph_fallback=20)
    assert "ELSE 20" in speed_mph_expression(classifier=clf)


def test_speed_expression_strips_units_via_regex() -> None:
    """The COALESCE branch matches the Python ``_coerce_int``."""
    out = speed_mph_expression()
    assert "regexp_replace" in out
    assert "'[^0-9]'" in out


def test_speed_expression_accepts_custom_inputs() -> None:
    out = speed_mph_expression(
        highway_sql="pol.highway", maxspeed_sql="pol.maxspeed_text"
    )
    assert "pol.highway" in out
    assert "pol.maxspeed_text" in out
    assert "tags::jsonb" not in out


# ---------------------------------------------------------------------------
# lane_count_expression
# ---------------------------------------------------------------------------


def test_lane_expression_includes_classifier_default() -> None:
    out = lane_count_expression()
    assert "WHEN tags::jsonb->>'highway' = 'primary' THEN 4" in out


def test_lane_expression_fallback() -> None:
    clf = Classifier(lane_count_fallback=3)
    assert "ELSE 3" in lane_count_expression(classifier=clf)


# ---------------------------------------------------------------------------
# cycleway_kind_expression
# ---------------------------------------------------------------------------


def test_cycleway_expression_default_priority_order() -> None:
    out = cycleway_kind_expression()
    # Default order: cycleway, cycleway:right, cycleway:left, cycleway:both.
    # Find each key's index in the output text and assert the order.
    keys = ["'cycleway'", "'cycleway:right'", "'cycleway:left'", "'cycleway:both'"]
    indices = [out.index(k) for k in keys]
    assert indices == sorted(indices)


def test_cycleway_expression_priority_override() -> None:
    """Reordering classifier.cycleway_tag_keys reorders the COALESCE."""
    clf = Classifier(
        cycleway_tag_keys=("cycleway:both", "cycleway", "cycleway:left")
    )
    out = cycleway_kind_expression(classifier=clf)
    both_idx = out.index("'cycleway:both'")
    plain_idx = out.index("'cycleway'")
    left_idx = out.index("'cycleway:left'")
    assert both_idx < plain_idx < left_idx
    # Removed key shouldn't appear at all.
    assert "'cycleway:right'" not in out


def test_cycleway_expression_accepts_custom_tags_jsonb() -> None:
    out = cycleway_kind_expression(tags_jsonb="ow.tags::jsonb")
    assert "ow.tags::jsonb" in out
    # Default `tags::jsonb` shouldn't appear if the override took.
    assert " tags::jsonb" not in out  # space-prefixed to dodge `ow.tags::jsonb` match


# ---------------------------------------------------------------------------
# lts_case_expression
# ---------------------------------------------------------------------------


def test_lts_case_starts_with_case_and_ends_with_end() -> None:
    out = lts_case_expression().strip()
    assert out.startswith("CASE")
    assert out.endswith("END")


def test_lts_case_includes_all_four_tiers() -> None:
    out = lts_case_expression()
    # Each LTS tier (1-4) appears as a `THEN N` literal somewhere.
    for n in (1, 2, 3, 4):
        assert f"THEN {n}" in out


def test_lts_case_excluded_branch_returns_null() -> None:
    out = lts_case_expression()
    assert "THEN NULL" in out
    assert "'motorway'" in out  # part of the excluded IN(...)


def test_lts_case_classifier_override_flows_through() -> None:
    clf = Classifier(speed_mph_fallback=20)
    out = lts_case_expression(classifier=clf)
    # The speed sub-expression's ELSE picks up the override.
    assert "ELSE 20" in out


def test_lts_case_per_input_override_takes_precedence() -> None:
    """`highway_sql='pol.highway'` is used everywhere instead of the tags->>'highway' default."""
    out = lts_case_expression(highway_sql="pol.highway")
    assert "pol.highway" in out
    # The default extraction shouldn't appear.
    assert "->>'highway'" not in out


def test_lts_case_default_uses_tags_jsonb_alias() -> None:
    out = lts_case_expression()
    # The default extraction should appear at least once.
    assert "(tags::jsonb)->>'highway'" in out


def test_lts_case_custom_tags_jsonb_propagates() -> None:
    out = lts_case_expression(tags_jsonb="ow.tags::jsonb")
    assert "(ow.tags::jsonb)->>'highway'" in out
    assert "(ow.tags::jsonb)->>'maxspeed'" in out


def test_lts_case_uses_shared_lts4_set() -> None:
    """The LTS 4 IN list comes from the same private constant the Python rules use."""
    from osm_lts._constants import _LTS4_HIGHWAYS

    out = lts_case_expression()
    for hw in _LTS4_HIGHWAYS:
        assert f"'{hw}'" in out


# ---------------------------------------------------------------------------
# Sanity: SQL emitter and Python classifier read the SAME defaults
# ---------------------------------------------------------------------------


def test_classifier_overrides_appear_in_both_forms() -> None:
    """A custom Classifier changes BOTH the Python output and the SQL output.

    Doesn't run the SQL — that needs a live PG. But it confirms the
    override surface is wired through both forms by spot-checking
    that:
      1. The Python classifier returns the new tier.
      2. The SQL expression bakes the new constant in.
    """
    # Bumping every per-highway default to 36 mph means a `tertiary`
    # with no explicit maxspeed flips into LTS 4 (>35 mph).
    bumped = Classifier(
        speed_mph_by_highway={
            **{k: 36 for k in classify.__globals__["C"].DEFAULT_SPEED_MPH_BY_HIGHWAY}
        }
    )
    # Python: the 36 mph default applies → LTS 4.
    assert bumped({"highway": "tertiary"}).value == 4
    # SQL: the WHEN ... = 'tertiary' THEN 36 branch is in the output.
    out = lts_case_expression(classifier=bumped)
    assert "WHEN (tags::jsonb)->>'highway' = 'tertiary' THEN 36" in out


def test_dataclasses_replace_works_for_sql_too() -> None:
    base = Classifier()
    stricter = dataclasses.replace(base, speed_mph_fallback=20)
    out = lts_case_expression(classifier=stricter)
    assert "ELSE 20" in out
