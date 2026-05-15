"""Smoke tests for the ``osm-lts`` CLI."""

from __future__ import annotations

import io
import json

from osm_lts.cli import main


def _run(stdin_text: str, capsys) -> list[dict]:
    # argparse.FileType('r') with default=sys.stdin would normally
    # bind to the real stdin; pytest's capsys swap covers it.
    import sys

    sys.stdin = io.StringIO(stdin_text)
    rc = main(["classify"])
    assert rc == 0
    out = capsys.readouterr().out
    return [json.loads(line) for line in out.splitlines() if line.strip()]


def test_cli_single_object(capsys) -> None:
    rows = _run('{"highway": "residential", "maxspeed": "25 mph"}', capsys)
    assert rows == [
        {"tags": {"highway": "residential", "maxspeed": "25 mph"}, "lts": 2}
    ]


def test_cli_jsonl_input(capsys) -> None:
    payload = '{"highway": "primary"}\n{"highway": "footway"}\n'
    rows = _run(payload, capsys)
    assert rows == [
        {"tags": {"highway": "primary"}, "lts": 4},
        {"tags": {"highway": "footway"}, "lts": None},
    ]


def test_cli_array_input(capsys) -> None:
    payload = '[{"highway": "cycleway"}, {"highway": "residential"}]'
    rows = _run(payload, capsys)
    assert [r["lts"] for r in rows] == [1, 2]
