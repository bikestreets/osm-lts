# Changelog

## 0.1.0 — 2026-05-15

Initial release. Pure-Python Furth Level of Traffic Stress classifier
extracted from the Bike Streets routing platform.

- `osm_lts.classify(tags)` — returns `LTS` 1–4 (or `None` for excluded
  highways) given an OSM tag mapping. Tolerates units in `maxspeed`
  and `lanes`, walks `cycleway` and per-side variants.
- `osm-lts classify` CLI for batch JSON / JSONL / array input.
- Tests pin every Furth rule branch plus edge cases (unit strings,
  cycleway sub-tags, separation overriding speed, multi-lane bumps).
