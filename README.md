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

Pure Python, no dependencies, Python 3.10+.

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

The whole classifier is defined in one readable file,
[`src/osm_lts/rules.md`](https://github.com/bikestreets/osm-lts/blob/main/src/osm_lts/rules.md): the ordered rules plus the
out-of-scope highways, default speeds and lane counts, legal default speeds,
and the order `cycleway*` keys are read in. Both the Python classifier and the
SQL `CASE` expression are generated from it when the package is imported, so
they always agree. To see what the classifier does, read that file. Defaults
can be edited there freely; a rule row is tied to a member of `osm_lts.Rule`
(its stable public name), so adding, renaming or reordering rules means
changing that enum to match. The package refuses to import if they differ.

The rules are checked top to bottom and the first match wins:

| Tier  | Who it suits                                  | Example triggers                                                       |
| :---: | --------------------------------------------- | ---------------------------------------------------------------------- |
| LTS 1 | Suitable for children                         | `highway=cycleway` / `path` / `track`, `living_street`, `cycleway=track` |
| LTS 2 | Tolerable for most adults                     | `residential` ≤25 mph, bike lane on a slow street                      |
| LTS 3 | Tolerable for enthused and confident adults   | `tertiary`, fast residential, bike lane on a faster street             |
| LTS 4 | Tolerable only for strong and fearless riders | `primary` / `trunk`, `>35 mph`, `≥3 lanes` and `>30 mph`               |

Order matters: a `cycleway=track` on a 40 mph arterial returns LTS 1 because
separation is checked before speed. Highways outside scope (`motorway`,
`footway`, `sidewalk`, `steps`, `pedestrian`) return `None`.

### Why a way got its rating

`explain` returns the rating together with the rule that decided it and the
inputs that rule read, each with where it came from:

```python
from osm_lts import explain

e = explain({"highway": "residential", "lanes": "2"})
e.lts                    # <LTS.MOST_ADULTS: 2>
e.rule.value             # 'slow_residential'
e.rule.description       # 'Residential or unclassified street at 25 mph or less'
e.speed_mph, e.speed_source.value   # (25, 'highway_default')
e.lts.description        # 'Tolerable for most adults'
```

Speed and lane count are reported only if a rule had to read them before
deciding: a `highway=cycleway` is LTS 1 at any speed, so its explanation has no
speed. `speed_source` / `lane_source` is one of `tagged`, `legal_default`
(from `maxspeed:type`), `highway_default` or `fallback`. `Rule` values are
stable identifiers, safe to store. `classify(tags)` is `explain(tags).lts`.

The defaults are also public constants, for showing in your own UI (e.g. "we
assumed 25 mph because the way was untagged"):

```python
from osm_lts import (
    DEFAULT_SPEED_MPH_BY_HIGHWAY,
    DEFAULT_LANE_COUNT_BY_HIGHWAY,
    EXCLUDED_HIGHWAYS,
)
```

### Crossings

Furth's method also rates **crossing** a street, separately from riding along
it. `crossing_lts` rates one crossing from the crossed street's lanes and
speed; a signal makes it LTS 1, and a crossing island (median refuge) uses
Furth's island table. The tables (Furth's LTS criteria, Table 6) are in
`rules.md`.

```python
from osm_lts import Classifier, crossing_lts, has_refuge, is_crossing, is_signalized

street = {"highway": "secondary", "lanes": "4", "maxspeed": "35 mph"}
clf = Classifier()
lanes, _ = clf.resolve_lanes(street)
mph, _ = clf.resolve_speed(street)
crossing_lts(lanes, mph)                # <LTS.EXPERIENCED_ONLY: 3>
crossing_lts(lanes, 25, refuge=True)    # <LTS.KID_COMFORTABLE: 1>

is_crossing({"highway": "footway", "footway": "crossing"})  # True
is_signalized({"crossing": "traffic_signals"})               # True
has_refuge({"crossing:island": "yes"})                        # True
```

Finding which streets a route crosses needs the way network, so it's left to
the caller: check the crossing way and the nodes on it with `is_signalized` /
`has_refuge`, and rate each crossed street. A divided road mapped as two
one-way carriageways is one crossing: pass both carriageways' lanes together,
with `refuge=True` for the median. A way with no `lanes` tag gets its highway
type's default, which counts both directions, so an untagged one-way
carriageway reads wider than it is. Pass `resolve_lanes` / `resolve_speed`
values, not `explain()`'s (which are `None` when no rule read them).
`Classifier.resolve_speed` / `resolve_lanes` / `resolve_cycleway` resolve a
way's inputs exactly as the rules do, for a way the rules didn't need them for
(like a street being crossed).

### Scope and limitations

The classifier treats each OSM way in isolation — it reads that
way's tags and returns a tier. That's the foundational input to
a network LTS analysis, but it's not the whole methodology:

- **No intersection effects in `classify`.** A calm residential that
  crosses a hostile arterial is still LTS 2 here. `crossing_lts` rates
  the crossing itself, but finding a route's crossings is up to the
  caller.
- **No adjacent-way context.** Parking presence, buffer width,
  and sidewalk separation aren't read from neighboring ways. A
  bike lane next to a parking lane is scored the same as one
  without.
- **No surface or ride-quality signal.** `highway=path` and
  `highway=track` promote to LTS 1 on the highway tag alone, so a
  `tracktype=grade5` dirt rut scores the same as a paved trail. LTS
  measures *traffic* stress; a tool that also cares about whether a
  way is rideable should read `surface` / `tracktype` itself. The
  trade-off is over-claim on hiking singletrack tagged `highway=path`
  and on muddy farm tracks.
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

The column must pick the facility as the classifier does: the first key whose
value is `lane`, `opposite_lane` or `track` (the values the rules test), else
the first key set. Collapsing to "the first key set" makes `cycleway=no` +
`cycleway:right=lane` lose its lane and rate differently from Python.

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

# Rate every highway, footways included. The SQL form then treats only a
# missing highway as unrated:
everything = Classifier(excluded_highways=frozenset())
```

The rules themselves (which conditions give which LTS) aren't overridden per
instance: they're Furth's method, defined once in `rules.md`. A `Classifier`
changes the defaults those rules read.

`Classifier` is a frozen dataclass — instances are immutable and
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
