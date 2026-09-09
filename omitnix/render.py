"""Rendering the report to JSON, the tool's only generated document.

A Markdown rendering used to sit next to this one. It was removed (2026-09) once a
second tool started reading `.omitnix/index.json` and writing the readable document
itself: two renderers of the same facts drift, and a 3,538-row flat table nobody opened
was evidence that this tool's readable output was not earning its cost to maintain. The
facts it used to spell out in prose -- a field outside an adapter's capabilities, a field
the adapter looked for and found nothing, a file that could not be analyzed at all -- are
unchanged; they live in ``FieldState`` (:mod:`omitnix.model`) and in each file record's
``status``, and are explained for a human reader in the README rather than rendered twice.
"""

from __future__ import annotations

import json
from typing import Any

from .model import Report

__all__ = [
    "to_payload",
    "payload_for_check",
    "render_json",
]


def to_payload(report: Report) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "generated": report.generated.to_json(),
        "coverage": report.coverage.to_json(),
        "files": [record.to_json() for record in report.files],
        "tables": [table.to_json() for table in report.tables],
    }


def payload_for_check(payload: dict[str, Any]) -> dict[str, Any]:
    """The part of the payload ``--check`` compares.

    ``generated`` is excluded on purpose. It holds the commit SHA and the dirty flag,
    which differ on every commit; comparing them would make ``--check`` fail for reasons
    that have nothing to do with the inventory being out of date.
    """
    return {key: value for key, value in payload.items() if key != "generated"}


def render_json(report: Report) -> str:
    return json.dumps(to_payload(report), indent=2, ensure_ascii=False, sort_keys=False) + "\n"
