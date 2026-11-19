"""SQL generators for the LTS classifier.

Emits a PostgreSQL ``CASE`` expression that returns the same LTS
classification as :func:`osm_lts.classify`, designed to drop directly
into a ``SELECT`` over OSM tag rows. The Python and SQL forms read
the same :class:`osm_lts.Classifier` instance for defaults, so
there is exactly one source of truth for the per-highway speed map,
exclusion set, lane defaults, and cycleway sub-tag priority — change
the constant in one place and both forms move together.

==================
DEFAULT SCHEMA
==================

Defaults target **osm2pgsql slim mode with hstore** — i.e., the
standard PostgreSQL layout produced by::

    osm2pgsql --slim --hstore-all -d <db> region.osm.pbf

In that schema, OSM tags live as ``hstore`` on
``planet_osm_ways.tags`` (and ``planet_osm_line.tags``). The default
``tags_jsonb='tags::jsonb'`` casts hstore to JSON for ``->>``
extraction, matching the pattern used everywhere else in the
osm2pgsql ecosystem.

Other backends — osm2pgsql **flex** output (custom schema), imposm3
(different table layout, no hstore), osmium-derived loaders, or any
hand-rolled OSM ingest — won't match the defaults out of the box.
Every input is overridable via keyword argument; pass the SQL
expression that resolves to the right value for your schema. See
:func:`lts_case_expression` for the full set of overrides.

==================
USAGE
==================

::

    from osm_lts.sql import lts_case_expression

    # Default: reads tags from a column named `tags` (hstore -> jsonb)
    sql = f\"\"\"
        SELECT
            id,
            ({lts_case_expression()}) AS lts
        FROM planet_osm_ways
        WHERE tags ? 'highway'
    \"\"\"

    # Custom alias / pre-extracted highway column:
    sql = lts_case_expression(
        tags_jsonb="pw.tags::jsonb",
        highway_sql="pol.highway",
    )

    # City-specific Classifier overrides flow into the SQL too:
    from osm_lts import Classifier
    clf = Classifier(speed_mph_fallback=20)
    lts_case_expression(classifier=clf)  # ELSE 20 in the speed CASE
"""

from __future__ import annotations

from typing import Optional

from ._rules import DEFINITION as _D
from ._classify import _KMH_TO_MPH, Classifier, _DEFAULT_CLASSIFIER

RULE_ROWS = _D.rules

__all__ = [
    "cycleway_kind_expression",
    "excluded_highways_in_list",
    "lane_count_expression",
    "lts_case_expression",
    "speed_mph_expression",
]


def _quote(value: str) -> str:
    """SQL-quote a literal text value (single-quoted, embedded quotes doubled)."""
    return "'" + value.replace("'", "''") + "'"


def _quote_in(values) -> str:
    """Comma-separated quoted SQL list, sorted for stable output."""
    return ", ".join(_quote(v) for v in sorted(values))


def excluded_highways_in_list(
    classifier: Classifier = _DEFAULT_CLASSIFIER,
) -> str:
    """Comma-separated quoted list of excluded highway tag values.

    Useful for filtering at the source — pre-pruning
    ``planet_osm_ways`` before the LTS CASE runs::

        WHERE tags->>'highway' NOT IN ({excluded_highways_in_list()})

    Raises:
        ValueError: if the classifier excludes nothing. ``IN ()`` isn't
            valid SQL, and no list can stand in for "nothing" in both
            ``IN`` and ``NOT IN`` — skip the filter instead.
    """
    if not classifier.excluded_highways:
        raise ValueError(
            "classifier.excluded_highways is empty; there is nothing to "
            "filter, so omit the IN / NOT IN clause"
        )
    return _quote_in(classifier.excluded_highways)


def speed_mph_expression(
    highway_sql: str = "tags::jsonb->>'highway'",
    maxspeed_sql: str = "tags::jsonb->>'maxspeed'",
    *,
    maxspeed_type_sql: Optional[str] = None,
    classifier: Classifier = _DEFAULT_CLASSIFIER,
) -> str:
    """Resolve speed_mph from highway + maxspeed (+ maxspeed:type) strings.

    Mirrors :meth:`Classifier._resolve_speed_mph` exactly, in COALESCE
    priority order:

    1. **Explicit numeric ``maxspeed``**, unit-aware. ``substring(<maxspeed>
       from '[0-9]+')`` pulls the first run of digits (``"25 mph"`` →
       ``25``); a metric unit (``~* 'km/?h|kmh|kph'``) is converted with
       ``* 0.621371`` and rounded (``"50 km/h"`` → ``31``). Yields ``NULL``
       when there are no digits, never casting a non-integer to ``::int``.
    2. **Implicit legal default** from ``maxspeed:type`` / ``source:maxspeed``.
       ``regexp_replace`` folds a country-qualified zone to its generic
       (``US-CO:urban`` → ``US:urban``) before matching
       ``classifier.implicit_maxspeed_mph``. Unknown zones → ``NULL``.
    3. **Per-highway default**, else ``classifier.speed_mph_fallback``.

    ``maxspeed_type_sql`` defaults to ``COALESCE(<type>, <source>)`` over
    the standard hstore→jsonb columns; pass your own when those tags are
    materialized elsewhere.
    """
    mt = maxspeed_type_sql or (
        "COALESCE(\n"
        "        NULLIF(tags::jsonb->>'maxspeed:type', ''),\n"
        "        NULLIF(tags::jsonb->>'source:maxspeed', '')\n"
        "    )"
    )
    digits = f"substring({maxspeed_sql} from '[0-9]+')"
    explicit = (
        "CASE\n"
        f"        WHEN {maxspeed_sql} ~* 'km/?h|kmh|kph'\n"
        f"            THEN round({digits}::numeric * {_KMH_TO_MPH})::int\n"
        f"        ELSE {digits}::int\n"
        "    END"
    )
    implicit_branches = "\n".join(
        f"        WHEN {_quote(zone)} THEN {n}"
        for zone, n in classifier.implicit_maxspeed_mph.items()
    )
    implicit = (
        # Trim all surrounding whitespace, as Python's str.strip() does
        # before matching (btrim alone only removes spaces).
        f"CASE regexp_replace(regexp_replace(COALESCE({mt}, ''), "
        "'^\\s+|\\s+$', '', 'g'),\n"
        "             '^([A-Za-z]+)-[A-Za-z]+(:.+)$', '\\1\\2')\n"
        f"{implicit_branches}\n"
        "    END"
    )
    highway_branches = "\n".join(
        f"        WHEN {highway_sql} = {_quote(hw)} THEN {n}"
        for hw, n in classifier.speed_mph_by_highway.items()
    )
    return (
        "COALESCE(\n"
        f"    {explicit},\n"
        f"    {implicit},\n"
        f"    CASE\n"
        f"{highway_branches}\n"
        f"        ELSE {classifier.speed_mph_fallback}\n"
        f"    END\n"
        ")"
    )


def lane_count_expression(
    highway_sql: str = "tags::jsonb->>'highway'",
    lanes_sql: str = "tags::jsonb->>'lanes'",
    *,
    classifier: Classifier = _DEFAULT_CLASSIFIER,
) -> str:
    """Resolve lane_count from highway + lanes string.

    Same shape as :func:`speed_mph_expression`, using the same
    ``substring(<lanes> from '[0-9]+')`` first-digit-run extraction
    before the ``::int`` cast. This matters for two reasons:

    1. **Safety.** OSM ``lanes`` is a free-form string. A raw
       ``{lanes_sql}::int`` raises ``invalid input syntax for type
       integer`` on any non-integer value (e.g. ``"1.5"`` on a narrow
       two-way street, ``"4;3"`` on a multi-way), aborting the whole
       query. ``substring`` extracts ``"1"`` / ``"4"`` instead, and
       yields ``NULL`` (→ highway default) when there are no digits.
    2. **Parity.** This must mirror :meth:`Classifier._resolve_lane_count`,
       which calls ``_coerce_int`` (first run of digits): ``"1.5"`` →
       ``1``, ``"4;3"`` → ``4``. The SQL and Python classifications stay
       in lockstep.
    """
    branches = "\n".join(
        f"            WHEN {highway_sql} = {_quote(hw)} THEN {n}"
        for hw, n in classifier.lane_count_by_highway.items()
    )
    return (
        "COALESCE(\n"
        f"    substring({lanes_sql} from '[0-9]+')::int,\n"
        f"    CASE\n"
        f"{branches}\n"
        f"        ELSE {classifier.lane_count_fallback}\n"
        f"    END\n"
        ")"
    )


def cycleway_kind_expression(
    tags_jsonb: str = "tags::jsonb",
    *,
    classifier: Classifier = _DEFAULT_CLASSIFIER,
) -> str:
    """COALESCE of cycleway/cycleway:right/etc. in the classifier's priority order.

    The priority order comes straight from
    ``classifier.cycleway_tag_keys``; reordering or extending that
    tuple changes which sub-tag wins for a way that carries multiple
    cycleway variants.
    """
    # NULLIF: an empty value doesn't count as set, as in the Python
    # classifier, so a later key can still supply the facility.
    args = ",\n    ".join(
        f"NULLIF(({tags_jsonb})->>{_quote(key)}, '')"
        for key in classifier.cycleway_tag_keys
    )
    return f"COALESCE(\n    {args}\n)"


def lts_case_expression(
    *,
    tags_jsonb: str = "tags::jsonb",
    highway_sql: Optional[str] = None,
    maxspeed_sql: Optional[str] = None,
    maxspeed_type_sql: Optional[str] = None,
    lanes_sql: Optional[str] = None,
    cycleway_kind_sql: Optional[str] = None,
    classifier: Classifier = _DEFAULT_CLASSIFIER,
) -> str:
    """Full PostgreSQL CASE expression returning LTS 1-4, or NULL when out of scope.

    NULL means no or empty ``highway``, or one the classifier excludes.
    Generated from the rules table in ``rules.md``; each branch carries a
    comment naming its rule.

    Drops directly into a ``SELECT``::

        SELECT
            id,
            ({lts_case_expression()}) AS lts
        FROM planet_osm_ways

    By default reads tags from a column named ``tags`` (osm2pgsql
    slim-mode hstore, cast to jsonb). Pass ``tags_jsonb`` to change
    the column / alias. If individual tags are materialized as their
    own columns in your schema (e.g. ``planet_osm_line.highway``),
    pass the per-input SQL keyword arguments — they take precedence
    over the automatic ``({tags_jsonb})->>'X'`` extraction.

    Args:
        tags_jsonb: SQL expression that resolves to a ``jsonb`` value
            holding the way's tag map. Default ``tags::jsonb``
            assumes the standard osm2pgsql slim-mode hstore column.
        highway_sql: Override the ``->>'highway'`` extraction. Use
            this when ``highway`` is a separate column.
        maxspeed_sql: Override the ``->>'maxspeed'`` extraction.
        maxspeed_type_sql: Override the implicit-default lookup source.
            Defaults to ``COALESCE(NULLIF(->>'maxspeed:type', ''),
            NULLIF(->>'source:maxspeed', ''))``. A custom expression should
            map an empty value to NULL the same way, or SQL and Python can
            disagree on such ways.
        lanes_sql: Override the ``->>'lanes'`` extraction.
        cycleway_kind_sql: Override the cycleway COALESCE entirely
            — useful when cycleway sub-tags are pre-resolved to a
            single column. Map empty values to NULL (``NULLIF(x, '')``)
            so an empty key doesn't hide a later one, as in Python.
        classifier: :class:`Classifier` instance whose
            speed/lane/exclusion/cycleway-key fields control the
            emitted defaults.

    Returns:
        A multi-line SQL string starting with ``CASE`` and ending
        with ``END``. Safe to interpolate into an f-string; no
        trailing semicolon.
    """
    h = highway_sql or f"({tags_jsonb})->>'highway'"
    m = maxspeed_sql or f"({tags_jsonb})->>'maxspeed'"
    mt = maxspeed_type_sql or (
        f"COALESCE(NULLIF(({tags_jsonb})->>'maxspeed:type', ''), "
        f"NULLIF(({tags_jsonb})->>'source:maxspeed', ''))"
    )
    ln = lanes_sql or f"({tags_jsonb})->>'lanes'"
    cw = cycleway_kind_sql or cycleway_kind_expression(
        tags_jsonb, classifier=classifier
    )
    speed = speed_mph_expression(
        h, m, maxspeed_type_sql=mt, classifier=classifier
    )
    lanes = lane_count_expression(h, ln, classifier=classifier)
    # An empty exclusion set means "rate every highway": only a missing
    # highway is out of scope then (``IN ()`` would be a syntax error).
    # An empty highway is unrated too, as in the Python classifier.
    out_of_scope = f"{h} IS NULL OR {h} = ''"
    if classifier.excluded_highways:
        out_of_scope += f" OR {h} IN ({excluded_highways_in_list(classifier)})"

    return (
        "CASE\n"
        f"    WHEN {out_of_scope} THEN NULL\n"
        + _rule_branches(highway=h, cycleway=cw, speed=speed, lanes=lanes)
        + "\nEND"
    )


def _in_or_equals(expression: str, values) -> str:
    values = sorted(values)
    if len(values) == 1:
        return f"{expression} = {_quote(values[0])}"
    return f"{expression} IN ({_quote_in(values)})"


def _rule_branches(*, highway: str, cycleway: str, speed: str, lanes: str) -> str:
    """One ``WHEN`` per row of the rules table in ``rules.md``, in order.

    The last row has no conditions (checked when rules.md is loaded) and
    becomes the ``ELSE``. Each branch is preceded by a comment naming its
    rule, so the emitted SQL reads like the table it came from.
    """
    branches = []
    for row in RULE_ROWS:
        conditions = []
        if row.highway is not None:
            conditions.append(_in_or_equals(highway, row.highway))
        if row.cycleway is not None:
            conditions.append(_in_or_equals(f"({cycleway})", row.cycleway))
        if row.speed_mph is not None:
            conditions.append(row.speed_mph.sql(speed))
        if row.lanes is not None:
            conditions.append(row.lanes.sql(lanes))
        # rules.md rejects '%' in descriptions, so this comment can't
        # collide with a driver's %s / %(name)s placeholders.
        comment = f"    -- {row.rule}: {row.description}"
        if conditions:
            when = " AND ".join(conditions)
            branches.append(f"{comment}\n    WHEN {when} THEN {row.lts}")
        else:
            branches.append(f"{comment}\n    ELSE {row.lts}")
    return "\n".join(branches)
