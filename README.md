# osm-lts

[![PyPI version](https://img.shields.io/pypi/v/osm-lts.svg)](https://pypi.org/project/osm-lts/)
[![Python versions](https://img.shields.io/pypi/pyversions/osm-lts.svg)](https://pypi.org/project/osm-lts/)
[![CI](https://github.com/bikestreets/osm-lts/actions/workflows/test.yml/badge.svg)](https://github.com/bikestreets/osm-lts/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/pypi/l/osm-lts.svg)](https://github.com/bikestreets/osm-lts/blob/main/LICENSE)

Classify OpenStreetMap ways by **Level of Traffic Stress (LTS)** using the
[Furth methodology](https://peterfurth.sites.northeastern.edu/level-of-traffic-stress/).

LTS is a 1–4 scale from "kid-comfortable" (1) to "strong-and-fearless only"
(4). It's the standard advocacy and planning input for "where is the bike
network actually rideable for a typical adult" — far more honest than miles
of "bike infrastructure" because it captures whether that infrastructure is
on a calm street or a six-lane arterial.

## Install

```bash
pip install osm-lts
```

Pure Python, no dependencies, Python 3.9+.

## Use

```python
from osm_lts import classify

classify({"highway": "residential", "maxspeed": "25 mph"})
# <LTS.MOST_ADULTS: 2>

classify({"highway": "primary"})
# <LTS.STRONG_AND_FEARLESS: 4>

classify({"highway": "cycleway"})
# <LTS.KID_COMFORTABLE: 1>

classify({"highway": "footway"})
# None — outside scope (not relevant to cyclist stress)
```

The function takes any `Mapping[str, str]` of OSM tags. Numeric tags
(`maxspeed`, `lanes`) tolerate units (`"25 mph"`, `"50 km/h"`, `"4;3"`) —
only the leading digits are read. The result is an `IntEnum`, so
`int(classify(tags))` gives you the bare LTS value for serialization.

### CLI

The package ships with an `osm-lts` command for batch jobs:

```bash
echo '{"highway": "residential", "maxspeed": "25 mph"}' | osm-lts classify
# {"tags": {"highway": "residential", "maxspeed": "25 mph"}, "lts": 2}

osm-lts classify --in ways.jsonl --out lts.jsonl
```

Input is JSON, JSONL, or a single JSON array — auto-detected.

## How it works

The classifier mirrors Furth's published rules:

| Tier  | Description                  | Example triggers                                                |
| :---: | ---------------------------- | --------------------------------------------------------------- |
| LTS 1 | Suitable for children        | `highway=cycleway`, `living_street`, `cycleway=track`           |
| LTS 2 | Most adults will tolerate    | `residential` ≤25 mph, bike lane on a slow street               |
| LTS 3 | Experienced cyclists only    | `tertiary`, fast residential, bike lane on a faster street      |
| LTS 4 | Strong-and-fearless only     | `primary` / `trunk`, `>35 mph`, `≥3 lanes` and `>30 mph`        |

The branches evaluate top-to-bottom and short-circuit on the first match.
Order matters — a `cycleway=track` on a 40 mph arterial returns LTS 1
because separation wins over speed. Highways outside scope (`motorway`,
`footway`, `sidewalk`, `steps`, `pedestrian`) return `None`.

When `maxspeed` or `lanes` are missing, highway-typical defaults fill in:

```python
from osm_lts import (
    DEFAULT_SPEED_MPH_BY_HIGHWAY,
    DEFAULT_LANE_COUNT_BY_HIGHWAY,
    EXCLUDED_HIGHWAYS,
)
```

These are public so callers can read them in their own UIs (e.g. "we
assumed 25 mph because the way was untagged").

### Scope and limitations

The classifier treats each OSM way in isolation — it reads that
way's tags and returns a tier. That's the foundational input to
a network LTS analysis, but it's not the whole methodology:

- **No intersection effects.** A calm residential that crosses a
  hostile arterial is still LTS 2 here; full Furth would penalize
  the unsignalized crossing.
- **No adjacent-way context.** Parking presence, buffer width,
  and sidewalk separation aren't read from neighboring ways. A
  bike lane next to a parking lane is scored the same as one
  without.
- **No network-level analysis.** The output is a per-way score,
  not "low-stress islands" or connectivity. Building a routing
  or coverage tool means doing that analysis on top of the
  per-way scores this library returns.

### SQL form (PostgreSQL / osm2pgsql)

The same rules are also available as a PostgreSQL `CASE` expression
via `osm_lts.sql`. The SQL emitter and the Python classifier share
their constants — change a default in one place and both forms move
together.

```python
from osm_lts.sql import lts_case_expression

sql = f"""
    SELECT
        id,
        ({lts_case_expression()}) AS lts
    FROM planet_osm_ways
    WHERE tags ? 'highway'
"""
```

Defaults assume **osm2pgsql slim mode with `--hstore-all`** —
tags live as `hstore` on `planet_osm_ways.tags` and are cast to
`jsonb` for `->>` extraction. Different schemas (osm2pgsql flex,
imposm3, custom DDL) work via per-input keyword overrides:

```python
lts_case_expression(
    tags_jsonb="pw.tags::jsonb",   # custom alias
    highway_sql="pol.highway",      # pre-extracted column
)
```

`Classifier` overrides flow into the SQL too — a city-specific
tuning produces SQL with the new defaults baked in:

```python
clf = Classifier(speed_mph_fallback=20)
lts_case_expression(classifier=clf)  # emits "ELSE 20" in the speed CASE
```

The submodule also exposes the building blocks individually
(`speed_mph_expression`, `lane_count_expression`,
`cycleway_kind_expression`, `excluded_highways_in_list`) for use in
custom queries.

#### Recipes for different OSM database layouts

**1. osm2pgsql slim + hstore (the default)** — `tags` lives as `hstore`
on `planet_osm_ways.tags`; no extra columns. The defaults work as-is:

```python
from osm_lts.sql import lts_case_expression

sql = f"""
    SELECT id, ({lts_case_expression()}) AS lts
    FROM planet_osm_ways
    WHERE tags ? 'highway'
"""
```

**2. osm2pgsql slim, classifying alongside `planet_osm_line` geometry** —
`planet_osm_line` materializes `highway`, `name`, etc. as columns, but
the full tag bag is back on `planet_osm_ways.tags`. Use the cheap column
where it's available, fall back to the tag bag for everything else:

```python
sql = f"""
    SELECT
        pol.osm_id,
        pol.way AS geom,
        ({lts_case_expression(
            tags_jsonb="pw.tags::jsonb",
            highway_sql="pol.highway",
            maxspeed_sql="(pw.tags::jsonb)->>'maxspeed'",
        )}) AS lts
    FROM planet_osm_line pol
    JOIN planet_osm_ways pw ON pw.id = pol.osm_id
    WHERE pol.highway IS NOT NULL
"""
```

(Pre-filtering on `pol.highway IS NOT NULL` is much faster than
post-filtering on the LTS `NULL` result.)

**3. osm2pgsql flex output with native `jsonb` tags** — flex Lua often
defines a single table with `tags jsonb` (no hstore cast needed). Drop
the `::jsonb` and the rest works:

```python
sql = f"""
    SELECT id, ({lts_case_expression(tags_jsonb="tags")}) AS lts
    FROM osm_ways  -- whatever your flex script named it
"""
```

**4. imposm3** — different schema again. Tags live as `hstore` on
`osm_roads.tags`, but most fields you care about are already broken
out into columns. Use the materialized columns and convert the hstore
to jsonb only for cycleway sub-tags:

```python
sql = f"""
    SELECT
        osm_id,
        geometry,
        ({lts_case_expression(
            tags_jsonb="hstore_to_jsonb(tags)",  # for cycleway COALESCE
            highway_sql="type",                    # imposm3 names it 'type'
            maxspeed_sql="tags->'maxspeed'",       # raw hstore -> text
            bicycle_sql="tags->'bicycle'",
        )}) AS lts
    FROM osm_roads
"""
```

(`tags->'k'` is the hstore text accessor — analogous to JSON `->>`.)

**5. Custom schema with a pre-resolved cycleway column** — if your ETL
already collapsed `cycleway` / `cycleway:right` / `cycleway:left` /
`cycleway:both` down to a single `cycleway_kind` column, skip the
COALESCE entirely:

```python
sql = f"""
    SELECT id, ({lts_case_expression(
        cycleway_kind_sql="cycleway_kind",  # plain column reference
    )}) AS lts
    FROM ways_with_resolved_cycleway
"""
```

**6. Pre-filtering at the source** — for tile servers and other hot
paths, drop excluded highways at the row source so the CASE never sees
them:

```python
from osm_lts.sql import excluded_highways_in_list, lts_case_expression

sql = f"""
    SELECT id, ({lts_case_expression()}) AS lts
    FROM planet_osm_ways
    WHERE tags->'highway' IS NOT NULL
      AND tags->'highway' NOT IN ({excluded_highways_in_list()})
"""
```

### Customizing the rules

Wrap a `Classifier` instance to override any of the defaults. Useful for
modeling a city or country whose posted-speed conventions or in-scope
highway set differ from the US-centric defaults the package ships with.

```python
from osm_lts import Classifier, EXCLUDED_HIGHWAYS

# Stricter unknown-speed default:
strict = Classifier(speed_mph_fallback=20)
strict({"highway": "residential"})  # <LTS.MOST_ADULTS: 2>

# Drop pedestrian-priority paths out of scope entirely:
narrower = Classifier(excluded_highways=EXCLUDED_HIGHWAYS | {"path"})
narrower({"highway": "path", "bicycle": "designated"})  # None

# Per-highway speed overrides:
slower_residential = Classifier(speed_mph_by_highway={"residential": 20})
```

`Classifier` is a frozen dataclass — instances are hashable and
thread-safe to share. Use `dataclasses.replace(clf, ...)` for tweaked
copies.

## Origin

Extracted from the [Bike Streets](https://bikestreets.com/) city-mapping
platform.

## Development

```bash
pip install -e '.[test]'
pytest
```

## License

MIT. See [LICENSE](LICENSE).
