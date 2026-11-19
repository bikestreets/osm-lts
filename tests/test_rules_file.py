"""Tests for loading ``rules.md``, the classifier's definition."""

from __future__ import annotations

from importlib import resources

import pytest

import osm_lts
from osm_lts import Rule
from osm_lts._rules import (
    DEFINITION,
    RULES_FILE,
    Comparison,
    RulesFileError,
    parse_definition,
)

SHIPPED = resources.files("osm_lts").joinpath(RULES_FILE).read_text("utf-8")


def test_shipped_file_parses_to_the_loaded_definition() -> None:
    assert parse_definition(SHIPPED) == DEFINITION


def test_public_constants_come_from_the_file() -> None:
    assert osm_lts.EXCLUDED_HIGHWAYS == DEFINITION.excluded_highways
    assert osm_lts.DEFAULT_SPEED_MPH_BY_HIGHWAY["residential"] == 25
    assert osm_lts.DEFAULT_SPEED_MPH_FALLBACK == 25
    assert osm_lts.DEFAULT_IMPLICIT_MAXSPEED_MPH["US:urban"] == 25
    assert osm_lts.DEFAULT_LANE_COUNT_BY_HIGHWAY["primary"] == 4
    assert osm_lts.DEFAULT_LANE_COUNT_FALLBACK == 2
    assert osm_lts.CYCLEWAY_TAG_KEYS[0] == "cycleway"


def test_rule_enum_matches_the_table() -> None:
    table = [row.rule for row in DEFINITION.rules]
    assert table == [m.value for m in Rule][2:]
    for row in DEFINITION.rules:
        assert Rule(row.rule).description == row.description


def test_comparison() -> None:
    assert Comparison(">", 35).test(36) and not Comparison(">", 35).test(35)
    assert Comparison("<=", 25).test(25) and not Comparison("<=", 25).test(26)
    assert Comparison(">=", 3).sql("lanes") == "(lanes) >= 3"


def _broken(old: str, new: str) -> str:
    assert old in SHIPPED, old
    return SHIPPED.replace(old, new, 1)


@pytest.mark.parametrize(
    "text, message",
    [
        (_broken("| > 35        |", "| over 35     |"), "isn't a comparison"),
        (
            _broken(
                "| cycleway             |  1  |", "| cycleway             |  5  |"
            ),
            "LTS must be 1-4",
        ),
        (
            _broken("| other_highway        |  3  |                ", "| other_highway        |  3  | road           "),
            "must have no conditions",
        ),
        (_broken("| *              |  25 |", "| tertiary       |  25 |"), "listed twice"),
        (_broken("<!-- osm-lts:table cycleway_keys -->", ""), "missing table 'cycleway_keys'"),
        (
            _broken("| motorway      |\n", "| motorway      | extra |\n"),
            "row has 2 cells",
        ),
        (
            _broken("| *              |  25 |", "| *              |  25 |\n| *              |  35 |"),
            "more than one '\\*' row",
        ),
        (
            _broken("Speed over 35 mph    ", "Speed over 35% mph   "),
            "can't contain '%'",
        ),
        (
            _broken("|  2  | Tolerable for most adults ", "|  1  | Tolerable for most adults "),
            "lists LTS 1 twice",
        ),
    ],
)
def test_malformed_files_are_rejected_with_a_reason(text: str, message: str) -> None:
    with pytest.raises(RulesFileError, match=message):
        parse_definition(text)


def test_crossing_tables_are_validated() -> None:
    with pytest.raises(RulesFileError, match="unsignalized_crossings"):
        parse_definition(
            _broken("|       |             |  4  |\n", "|       | > 1         |  4  |\n")
        )


def test_an_empty_table_is_rejected() -> None:
    text = _broken(
        "| key      |\n| -------- |\n| crossing |\n", "| key      |\n| -------- |\n"
    )
    with pytest.raises(RulesFileError, match="has no rows"):
        parse_definition(text)
