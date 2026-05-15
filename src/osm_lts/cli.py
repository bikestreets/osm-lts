"""Command-line interface for ``osm-lts``.

Reads a JSON object, JSON array, or one JSON object per line from
stdin (or ``--in <file>``) and writes the LTS classification to
stdout (or ``--out <file>``) as JSONL.

Examples::

    echo '{"highway": "residential", "maxspeed": "25 mph"}' \\
        | osm-lts classify
    osm-lts classify --in ways.jsonl --out lts.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import IO, Iterable, Iterator

from . import __version__
from ._classify import classify


def _iter_json_objects(stream: IO[str]) -> Iterator[dict]:
    """Yield one tag dict per JSON object found in ``stream``.

    Accepts either a single JSON value (object or array) or one
    JSON object per line — whichever the file looks like at first
    non-whitespace character.
    """
    text = stream.read().strip()
    if not text:
        return
    if text.startswith("["):
        for obj in json.loads(text):
            yield obj
    elif text.startswith("{") and "\n{" not in text and "}\n{" not in text:
        # Single object, no embedded newlines between objects.
        yield json.loads(text)
    else:
        for line in text.splitlines():
            line = line.strip()
            if line:
                yield json.loads(line)


def _classify_command(args: argparse.Namespace) -> int:
    for tags in _iter_json_objects(args.infile):
        result = classify(tags)
        out_obj = {"tags": tags, "lts": int(result) if result is not None else None}
        args.outfile.write(json.dumps(out_obj))
        args.outfile.write("\n")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="osm-lts",
        description="Classify OSM ways by Furth Level of Traffic Stress.",
    )
    parser.add_argument(
        "--version", action="version", version=f"osm-lts {__version__}"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    classify_parser = sub.add_parser(
        "classify",
        help="Classify one or more OSM tag dicts.",
        description=(
            "Read JSON tag dicts from stdin (or --in) and write a "
            "JSONL stream of {tags, lts} objects to stdout (or --out)."
        ),
    )
    classify_parser.add_argument(
        "--in",
        dest="infile",
        type=argparse.FileType("r"),
        default=sys.stdin,
        help="Input file (default: stdin).",
    )
    classify_parser.add_argument(
        "--out",
        dest="outfile",
        type=argparse.FileType("w"),
        default=sys.stdout,
        help="Output file (default: stdout).",
    )
    classify_parser.set_defaults(func=_classify_command)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
