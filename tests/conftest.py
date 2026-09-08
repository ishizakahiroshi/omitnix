"""Shared test helpers.

The adapters used by the tests live in ``tests/fixtures/adapters`` and are picked up by
extending ``omitnix.adapters.__path__`` -- the same discovery code a real adapter goes
through, without shipping test-only adapters in the package.
"""

from __future__ import annotations

import contextlib
import importlib
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
ADAPTER_FIXTURES = FIXTURES / "adapters"
BAD_ADAPTER_FIXTURES = FIXTURES / "bad_adapters"
RIVAL_ADAPTER_FIXTURES = FIXTURES / "rival_adapters"


@contextlib.contextmanager
def adapter_path(*directories: Path) -> Iterator[None]:
    package = importlib.import_module("omitnix.adapters")
    original = list(package.__path__)
    before = set(sys.modules)
    package.__path__[:] = original + [str(directory) for directory in directories]
    importlib.invalidate_caches()
    try:
        yield
    finally:
        package.__path__[:] = original
        for name in set(sys.modules) - before:
            if name.startswith("omitnix.adapters."):
                del sys.modules[name]
        importlib.invalidate_caches()


@pytest.fixture
def with_test_adapters() -> Iterator[None]:
    with adapter_path(ADAPTER_FIXTURES):
        yield


def write_repo(root: Path, files: dict[str, str]) -> Path:
    """Create a synthetic repository. Every name here is fictional on purpose."""
    for rel, content in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return root


ORDERS_FLOW = """summary: List orders for the signed-in customer
authn: require_session
authz: apply_visibility_filter
reads: orders, customers
"""

EXPORT_FLOW = """summary: Export orders as CSV
authn: require_session
authz: apply_visibility_filter
reads: orders
unresolved: dynamic_sql / the table name is built at run time
"""

REINDEX_FLOW = """summary: Nightly reindex
reads: orders
writes: search_index
"""

PLAIN_NOTE = """Release notes for the fictional example service
"""
