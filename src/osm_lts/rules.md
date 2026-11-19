# osm-lts rules

This file **is** the classifier. `osm_lts` reads the tables below when it is
imported: the Python classifier (`classify`, `explain`) and the PostgreSQL
`CASE` expression (`osm_lts.sql`) are both generated from them, so they can't
disagree. Edit a table here and both forms change together. Each rule row is
also tied to a member of `osm_lts.Rule`, its stable public name: add, rename
or reorder rules there too, or the package won't import.

The method is Peter Furth's Level of Traffic Stress
(<https://peterfurth.sites.northeastern.edu/level-of-traffic-stress/>), applied
to one OpenStreetMap way at a time from its tags. See the README's "Scope and
limitations" for what a per-way reading leaves out.

<!-- osm-lts:table levels -->
| LTS | Who it suits                                  |
| :-: | --------------------------------------------- |
|  1  | Suitable for children                         |
|  2  | Tolerable for most adults                     |
|  3  | Tolerable for enthused and confident adults   |
|  4  | Tolerable only for strong and fearless riders |

## Rules

Rules are checked **top to bottom; the first one that matches decides**. Order
carries meaning: separation from traffic (the LTS 1 rules) is checked before
speed, so a separated bike track beside a 45 mph road is still LTS 1.

A rule matches when **every** filled-in column matches; an empty cell is
ignored. Within a cell, a comma means "any of". The columns:

- **highway**: the way's `highway=*` value.
- **cycleway**: the bike facility on the way, read from the first of the
  [cycleway keys](#cycleway-keys) that is set.
- **speed (mph)**: the way's speed. This is its `maxspeed`, or a
  [legal default](#legal-default-speeds) its `maxspeed:type` names, or the
  [default for its highway type](#default-speeds).
- **lanes**: the way's `lanes`, or the [default for its highway type](#default-lanes).

A highway that is missing or [out of scope](#out-of-scope-highways) is never
rated, and none of these rules are checked for it.

<!-- osm-lts:table rules -->
| rule                 | LTS | highway                                                                       | cycleway                          | speed (mph) | lanes | description                                          |
| -------------------- | :-: | ----------------------------------------------------------------------------- | --------------------------------- | ----------- | ----- | ---------------------------------------------------- |
| cycleway             |  1  | cycleway                                                                      |                                   |             |       | Dedicated cycleway, separated from motor traffic     |
| path                 |  1  | path                                                                          |                                   |             |       | Path closed to motor traffic                         |
| track                |  1  | track                                                                         |                                   |             |       | Access track with no through motor traffic           |
| living_street        |  1  | living_street                                                                 |                                   |             |       | Living street, designed for very low speeds          |
| separated_bike_track |  1  |                                                                               | track                             |             |       | Physically separated bike track alongside the road   |
| speed_over_35        |  4  |                                                                               |                                   | > 35        |       | Speed over 35 mph                                    |
| arterial             |  4  | primary, primary_link, trunk, trunk_link                                      |                                   |             |       | Primary or trunk arterial                            |
| multilane_over_30    |  4  |                                                                               |                                   | > 30        | >= 3  | 3 or more lanes at over 30 mph                       |
| bike_lane_slow       |  2  |                                                                               | lane, opposite_lane, shared_lane  | <= 25       |       | Bike lane on a street at 25 mph or less              |
| slow_residential     |  2  | residential, unclassified                                                     |                                   | <= 25       |       | Residential or unclassified street at 25 mph or less |
| bike_lane_faster     |  3  |                                                                               | lane, opposite_lane, shared_lane  |             |       | Bike lane on a street over 25 mph                    |
| collector            |  3  | tertiary, tertiary_link, secondary, secondary_link, residential, unclassified |                                   |             |       | Collector or faster local street in mixed traffic    |
| service              |  1  | service                                                                       |                                   |             |       | Service way (alley, driveway, parking aisle)         |
| other_highway        |  3  |                                                                               |                                   |             |       | Other road type, rated as mixed traffic              |

Notes on individual rules:

- **path, track**: rated on the `highway` tag alone. LTS measures *traffic*
  stress, not ride quality, so `surface` and `tracktype` aren't read. A track
  is an agricultural or forestry access way: motor vehicles may use it, but
  there is no through traffic.
- **bike_lane_\***: a painted lane reduces stress only on a slow street. On a
  fast or wide street the LTS 4 rules above win first, because paint doesn't
  make a hostile street calm.
- **other_highway**: the last rule has no conditions, so every in-scope way
  gets a rating.

## Out of scope highways

These are never rated: bikes are prohibited, or the way is for people walking.

<!-- osm-lts:table excluded_highways -->
| highway       |
| ------------- |
| motorway      |
| motorway_link |
| footway       |
| sidewalk      |
| steps         |
| pedestrian    |

## Default speeds

Used when a way has no usable `maxspeed` and no recognised legal default. A
highway type not listed here gets the `*` row.

<!-- osm-lts:table default_speeds -->
| highway        | mph |
| -------------- | --: |
| living_street  |  15 |
| residential    |  25 |
| unclassified   |  25 |
| service        |  25 |
| tertiary       |  30 |
| tertiary_link  |  30 |
| secondary      |  35 |
| secondary_link |  35 |
| primary        |  40 |
| primary_link   |  40 |
| trunk          |  40 |
| trunk_link     |  40 |
| *              |  25 |

## Legal default speeds

When a way has no numeric `maxspeed` but its `maxspeed:type` (or
`source:maxspeed`) names a legal default, that speed is used ahead of the
highway default. A state-qualified zone with no row of its own (`US-CO:urban`)
uses its country's row (`US:urban`). Values are the US statutory defaults
listed on the OpenStreetMap wiki's "Default speed limits" page.

<!-- osm-lts:table legal_default_speeds -->
| zone             | mph |
| ---------------- | --: |
| US:living_street |  10 |
| US:urban         |  25 |
| US:rural         |  55 |

## Default lanes

Used when a way has no usable `lanes` tag. A highway type not listed here gets
the `*` row.

<!-- osm-lts:table default_lanes -->
| highway        | lanes |
| -------------- | ----: |
| residential    |     2 |
| service        |     2 |
| primary        |     4 |
| primary_link   |     4 |
| secondary      |     4 |
| secondary_link |     4 |
| *              |     2 |

## Cycleway keys

The bike facility is read from the first of these keys that is set. A way whose
sides disagree (a lane on the right, a track on the left) gets the first one.

<!-- osm-lts:table cycleway_keys -->
| key            |
| -------------- |
| cycleway       |
| cycleway:right |
| cycleway:left  |
| cycleway:both  |

## Reading numbers from tags

`maxspeed` and `lanes` are free-form text in OpenStreetMap. Only the first run
of digits is read: `"25 mph"` is 25, `"4;3"` is 4 lanes, `"1.5"` is 1. A
`maxspeed` with a metric unit (`km/h`, `kmh`, `kph`) is converted to mph and
rounded (`"50 km/h"` is 31 mph); a bare number is read as mph. A value with no
digits (`"none"`, `"signals"`) counts as missing.
