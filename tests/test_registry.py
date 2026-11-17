"""Adapter discovery: adding a language must mean adding a file and nothing else.

The central case writes a module into the package at run time and removes it again,
because the property being checked is the real drop-in path rather than a test-only hook.
An extension claimed by two adapters is an error here, not something settled by import
order.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from omitnix.adapters.base import Adapter
from omitnix.errors import AdapterContractError
from omitnix.registry import build_adapter_set, discover_adapters, interpreter_of

from .conftest import ADAPTER_FIXTURES, BAD_ADAPTER_FIXTURES, RIVAL_ADAPTER_FIXTURES, adapter_path


def test_adapters_are_found_without_a_registry(with_test_adapters: None) -> None:
    names = [adapter.name for adapter in discover_adapters()]
    assert "flow" in names
    assert "note" in names


def test_extension_routing(with_test_adapters: None) -> None:
    adapter_set = build_adapter_set()
    assert adapter_set.for_path("api/orders.flow").name == "flow"
    assert adapter_set.for_path("docs/RELEASE.note").name == "note"
    assert adapter_set.for_path("api/orders.FLOW").name == "flow"
    assert adapter_set.for_path("api/orders.unheardof") is None
    assert adapter_set.for_path("Makefile") is None
    assert adapter_set.for_path(".gitignore") is None


def test_dropping_a_file_into_the_package_is_the_whole_registration(tmp_path: Path) -> None:
    """The completion condition for C2: a second adapter must need no core edit at all.

    This writes a module into omitnix/adapters/ at run time and removes it again, so the
    thing being verified is the real drop-in path, not a test-only hook.
    """
    package = importlib.import_module("omitnix.adapters")
    package_dir = Path(package.__path__[0])
    module_path = package_dir / "zztest_dropin.py"
    module_path.write_text(
        "from omitnix.adapters.base import Adapter, AnalysisResult\n"
        "from omitnix.model import Capability\n"
        "\n"
        "class DropInAdapter(Adapter):\n"
        "    name = 'zztest_dropin'\n"
        "    extensions = ('.dropin',)\n"
        "    capabilities = frozenset({Capability.SUMMARY})\n"
        "\n"
        "    def analyze(self, request):\n"
        "        return AnalysisResult(values={Capability.SUMMARY: 'dropped in'})\n"
        "\n"
        "ADAPTER = DropInAdapter()\n",
        encoding="utf-8",
    )
    importlib.invalidate_caches()
    try:
        adapter_set = build_adapter_set()
        assert adapter_set.for_path("thing.dropin").name == "zztest_dropin"
    finally:
        module_path.unlink(missing_ok=True)
        sys.modules.pop("omitnix.adapters.zztest_dropin", None)
        importlib.invalidate_caches()

    assert build_adapter_set().for_path("thing.dropin") is None


def test_two_adapters_claiming_one_extension_is_an_error() -> None:
    with adapter_path(ADAPTER_FIXTURES, RIVAL_ADAPTER_FIXTURES):
        with pytest.raises(AdapterContractError, match="more than one adapter"):
            build_adapter_set()


def test_configuration_settles_an_ambiguous_extension() -> None:
    with adapter_path(ADAPTER_FIXTURES, RIVAL_ADAPTER_FIXTURES):
        adapter_set = build_adapter_set({".flow": "rival_flow"})
        assert adapter_set.for_path("api/orders.flow").name == "rival_flow"


def test_unknown_adapter_name_in_configuration_is_an_error(with_test_adapters: None) -> None:
    with pytest.raises(AdapterContractError, match="unknown adapter"):
        build_adapter_set({".flow": "nonexistent"})


def test_bad_adapter_fixture_is_discoverable() -> None:
    # The contract violation itself is exercised in test_analyze.py; here we only make
    # sure the fixture is wired the same way as any other adapter.
    with adapter_path(BAD_ADAPTER_FIXTURES):
        assert build_adapter_set().for_path("x.over").name == "overreaching"


@pytest.mark.parametrize(
    ("head", "expected"),
    [
        (b"#!/usr/bin/php\n<?php\n", "php"),
        (b"#!/usr/bin/env php\n<?php\n", "php"),
        (b"#!/usr/bin/env -S php -d x=1\n", "php"),
        (b"#!/usr/bin/env FOO=1 php\n", "php"),
        (b"#!/usr/bin/php8.2\n<?php\n", "php"),
        (b"#!/usr/bin/env python3\n", "python"),
        (b"#!/bin/sh\r\n", "sh"),
        (b"#!\nrest\n", None),
        (b"#!/usr/bin/env\n", None),
        (b"# a comment, not a shebang\n#!/usr/bin/php\n", None),
        (b"\xef\xbb\xbf#!/usr/bin/php\n", None),
        (b"#!/usr/bin/\xffphp\n", None),
        (b"", None),
    ],
)
def test_interpreter_of_the_first_line(head: bytes, expected: str | None) -> None:
    assert interpreter_of(head) == expected


def test_interpreter_routing(with_test_adapters: None) -> None:
    adapter_set = build_adapter_set()
    assert adapter_set.for_interpreter("flowrun").name == "flow"
    assert adapter_set.for_interpreter("perl") is None


def test_two_adapters_declaring_one_interpreter_is_an_error() -> None:
    class _FirstClaim(Adapter):
        name = "first_claim"
        extensions = (".firstclaim",)
        interpreters = ("claimrun",)

    class _SecondClaim(Adapter):
        name = "second_claim"
        extensions = (".secondclaim",)
        interpreters = ("claimrun",)

    with pytest.raises(AdapterContractError, match="interpreter claimed by more than one"):
        build_adapter_set(adapters=[_FirstClaim(), _SecondClaim()])


def test_an_adapter_declaring_a_bad_interpreter_name_is_rejected() -> None:
    """A declaration the lookup can never match is a defect, found at load time."""
    package = importlib.import_module("omitnix.adapters")
    module_path = Path(package.__path__[0]) / "zztest_badinterp.py"
    module_path.write_text(
        "from omitnix.adapters.base import Adapter\n"
        "\n"
        "class BadInterpreterAdapter(Adapter):\n"
        "    name = 'zztest_badinterp'\n"
        "    extensions = ('.badinterp',)\n"
        "    interpreters = ('bad name',)\n"
        "\n"
        "    def analyze(self, request):\n"
        "        raise NotImplementedError\n"
        "\n"
        "ADAPTER = BadInterpreterAdapter()\n",
        encoding="utf-8",
    )
    importlib.invalidate_caches()
    try:
        with pytest.raises(AdapterContractError, match="whitespace"):
            build_adapter_set()
    finally:
        module_path.unlink(missing_ok=True)
        sys.modules.pop("omitnix.adapters.zztest_badinterp", None)
        importlib.invalidate_caches()
