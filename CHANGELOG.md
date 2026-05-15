# Changelog

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
