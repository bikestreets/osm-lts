# Changelog

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
