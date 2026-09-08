"""Include and exclude pattern matching, including when a directory may be skipped.

Pruning a directory is an optimisation, and a wrong one would drop files without saying
so -- the single failure this tool exists to prevent. So the pruning cases are here in
full: a recursive pattern may prune, a pattern covering only direct children may not.
"""

from __future__ import annotations

import pytest

from omitnix.globs import directory_is_pruned, glob_match, normalize


@pytest.mark.parametrize(
    ("pattern", "path", "expected"),
    [
        ("**/*", "api/orders.flow", True),
        ("**/*.flow", "api/orders.flow", True),
        ("**/*.flow", "orders.flow", True),
        ("*.flow", "api/orders.flow", False),
        ("api/*.flow", "api/orders.flow", True),
        ("api/*.flow", "api/nested/orders.flow", False),
        ("api/**/*.flow", "api/nested/deep/orders.flow", True),
        ("**/vendor/**", "vendor/lib/thing.flow", True),
        ("**/vendor/**", "app/vendor/lib/thing.flow", True),
        ("**/vendor/**", "app/vendored/thing.flow", False),
        ("**/node_modules/**", "web/node_modules/pkg/index.flow", True),
        ("report_?.flow", "report_1.flow", True),
        ("report_[0-9].flow", "report_7.flow", True),
        ("report_[!0-9].flow", "report_7.flow", False),
    ],
)
def test_glob_match(pattern: str, path: str, expected: bool) -> None:
    assert glob_match(pattern, path) is expected


def test_normalize_accepts_windows_separators() -> None:
    assert normalize(r".\api\orders.flow") == "api/orders.flow"


def test_directory_is_pruned_only_on_recursive_patterns() -> None:
    exclude = ("**/vendor/**", "**/node_modules/**")
    assert directory_is_pruned(exclude, "vendor")
    assert directory_is_pruned(exclude, "app/vendor")
    assert directory_is_pruned(exclude, "web/node_modules")
    assert not directory_is_pruned(exclude, "app")


def test_directory_is_not_pruned_when_only_direct_children_are_excluded() -> None:
    # 'build/*' excludes direct children only, so the subtree must still be walked --
    # pruning it would drop files silently, which is the one thing this tool forbids.
    assert not directory_is_pruned(("build/*",), "build")
