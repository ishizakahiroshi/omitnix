"""Schema snapshot input.

omitnix never connects to a database. When a repository wants table names it does not
touch in source (to show that nothing was observed to reference them), it points at a
JSON snapshot produced by another tool, such as ``tbls out -t json``.
"""

from __future__ import annotations

import json
from pathlib import Path

from .errors import ConfigError

__all__ = ["load_schema_tables"]


def load_schema_tables(path: Path) -> frozenset[str]:
    """Table names from a snapshot. A configured but unusable snapshot is an error."""
    if not path.is_file():
        raise ConfigError(f"schema_snapshot not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"schema_snapshot could not be read as JSON: {path}: {exc}") from exc

    tables = payload.get("tables") if isinstance(payload, dict) else None
    if not isinstance(tables, list):
        raise ConfigError(
            f"schema_snapshot has no 'tables' array: {path}. "
            "Expected the JSON shape produced by tbls (tbls out -t json)."
        )

    names: set[str] = set()
    for entry in tables:
        if isinstance(entry, dict) and isinstance(entry.get("name"), str):
            names.add(entry["name"])
        elif isinstance(entry, str):
            names.add(entry)
        else:
            raise ConfigError(f"schema_snapshot has a table entry without a name: {path}")
    return frozenset(names)
