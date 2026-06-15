# Changelog

## 0.5.0 — 2026-06-15

- Feature: `maxspeed` parsing is now **unit-aware**. A metric value
  (`"50 km/h"`, `"50 kmh"`, `"50 kph"`) is converted to mph (`→ 31`)
  instead of being read as the bare number `50` — which previously
  pushed such ways over the `> 35 mph` LTS-4 threshold. Bare numbers and
  `mph` values are still read as mph (US convention). Lanes are
  unaffected (only speeds carry units). The SQL `speed_mph_expression`
  mirrors this with a `~* 'km/?h|kmh|kph'` test and a `* 0.621371`
  conversion before the `::int` cast.
- Feature: when a way carries no numeric `maxspeed` but does reference a
  legal default via `maxspeed:type` / `source:maxspeed` (e.g.
  `US-CO:urban`), that zone is now resolved to its statutory speed
  (`DEFAULT_IMPLICIT_MAXSPEED_MPH`) ahead of the per-highway guess.
  Country-qualified zones fall back to the country generic
  (`US-CO:urban` → `US:urban`). Overridable via the new
  `Classifier(implicit_maxspeed_mph=...)` field; the SQL emitter accepts
  a matching `maxspeed_type_sql` override.
- Feature: new public `parse_maxspeed_mph()` so ingest/preprocessing code
  can share the classifier's unit-aware `maxspeed` parse instead of
  re-rolling a brittle `strip("mph")` parser.

## 0.4.3 — 2026-06-05

- Fix: free-form numeric tags (`maxspeed`, `lanes`) are now parsed as
  their **first run of digits** instead of a strip-and-concatenate of
  every digit. `"1.5"` → `1` (was `15`), `"4;3"` → `4` (was `43`),
  `"30;40"` → `30` (was `3040`). The old behavior was an
  order-of-magnitude error that, via the `lanes >= 3` LTS-4 rule,
  flipped narrow calm streets into the high-stress bucket.
- Fix: the SQL `lane_count_expression` cast `lanes::int` directly,
  which raised `invalid input syntax for type integer` (aborting the
  whole tile query) on any non-integer `lanes` value such as `"1.5"`.
  Both `speed_mph_expression` and `lane_count_expression` now use
  `substring(<tag> from '[0-9]+')::int`, which extracts the leading
  integer and yields `NULL` (→ highway default) when there are none —
  matching the corrected Python `_coerce_int` exactly.

## 0.4.2 — 2026-05-18

- Simplify the `highway=path` rule: any `highway=path` way now
  classifies as LTS 1, with no `bicycle`-tag qualifier. Previously
  the rule accepted only `bicycle in {yes, designated}`; the
  broadening keeps the rule tree short and picks up untagged paved
  paths that the previous form missed. The trade-off is over-claim
  on `highway=path` used for hiking/singletrack — see
  README "Scope and limitations" for the cost.
- Removed `_PATH_BICYCLE_LTS1` and the `bicycle_sql` keyword on
  `lts_case_expression` — both unused after the rule simplifies.

## 0.4.1 — 2026-05-18

- Fix: `highway=path` with `bicycle=yes` now classifies as LTS 1,
  matching the `bicycle=designated` case. Real paved shared-use
  trails (e.g. Denver's Sloan's Lake Trail) are commonly tagged
  with the looser `yes` value rather than the strict `designated`;
  the previous rule sent them to the LTS 3 catch-all. `permissive`
  / `official` / untagged-`bicycle` paths stay at the conservative
  fall-through so under-tagged hiking trails aren't over-claimed.
- The accepted set lives in `_constants._PATH_BICYCLE_LTS1` so the
  Python classifier and the SQL emitter read it from one place.

## 0.4.0 — 2026-05-15

- New `osm_lts.sql` submodule. Emits a PostgreSQL `CASE` expression
  that returns the same LTS classification as
  `osm_lts.classify`, designed to drop directly into a `SELECT` over
  OSM tag rows — useful for tile servers and bulk classification
  passes where running per-row Python is the wrong shape.
- Single source of truth for the constants: the SQL emitter reads
  from the same `Classifier` (and the same `_constants` module) the
  Python classifier uses, so per-highway speed defaults, exclusion
  set, lane defaults, and cycleway sub-tag priority are defined
  once and consumed by both forms.
- Defaults target **osm2pgsql slim mode with hstore** — i.e., the
  layout produced by `osm2pgsql --slim --hstore-all`. Other backends
  (osm2pgsql flex output, imposm3, custom DDL) are supported via
  per-input keyword overrides — every tag extraction is replaceable.
- Classifier overrides flow into the SQL too:
  `Classifier(speed_mph_fallback=20)` produces SQL with `ELSE 20`
  baked into the speed CASE.
- Building-block helpers exposed too — `speed_mph_expression`,
  `lane_count_expression`, `cycleway_kind_expression`,
  `excluded_highways_in_list` — for use in custom queries that
  don't want the full LTS tier.
- 24 new structural tests cover override flow-through and the
  shared-constants property; total 68 passing.

## 0.3.0 — 2026-05-15

Packaging and tooling pass to support external consumers. No
behavior changes to the classifier — the public API is unchanged
from 0.2.0.

- Ship `py.typed` so downstream type checkers (mypy, pyright) pick
  up the package's type hints (PEP 561).
- Metadata: SPDX license expression (`License-Expression: MIT`)
  with explicit `license-files`; added `Source` project URL.
- Single source of truth for the package version: `__version__`
  in `osm_lts/__init__.py`, with `pyproject.toml` deriving from
  it via hatch's regex source.
- CI: GitHub Actions test matrix on Python 3.9–3.13 on every
  push and pull request.
- Docstring examples in `Classifier` now run as part of `pytest`
  via `--doctest-modules`, so they can't silently drift.
- Trusted-Publishing release workflow: pushing a version bump to
  `main` auto-publishes to PyPI via OIDC (no API tokens).

## 0.2.0 — 2026-05-15

- New `Classifier` class — frozen dataclass exposing the previously-
  hardcoded defaults (excluded highways, per-highway speed/lane
  defaults, fallback speed/lane counts, cycleway sub-tag priority)
  as overridable fields. `classify(tags)` is a convenience wrapper
  around the default-configured singleton; `Classifier(...)` is the
  way to model regions whose conventions differ from the US-centric
  defaults.
- Instances are callable: `Classifier()(tags)` works alongside
  `.classify(tags)`.
- Tests pin every override surface (excluded highways add/drop,
  speed fallback flipping the LTS 4 threshold, lane-count fallback
  promoting to LTS 4, cycleway sub-tag priority reordering) plus
  frozen-instance enforcement and per-instance dict isolation.

## 0.1.0 — 2026-05-15

Initial release. Pure-Python Furth Level of Traffic Stress classifier
extracted from the Bike Streets routing platform.

- `osm_lts.classify(tags)` — returns `LTS` 1–4 (or `None` for excluded
  highways) given an OSM tag mapping. Tolerates units in `maxspeed`
  and `lanes`, walks `cycleway` and per-side variants.
- `osm-lts classify` CLI for batch JSON / JSONL / array input.
- Tests pin every Furth rule branch plus edge cases (unit strings,
  cycleway sub-tags, separation overriding speed, multi-lane bumps).
