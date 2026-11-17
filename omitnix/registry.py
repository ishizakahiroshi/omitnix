"""Adapter discovery.

The core holds no list of languages. It walks ``omitnix.adapters`` at run time and takes
every :class:`Adapter` instance it finds, which is what makes "add a language" mean "add
a file" and nothing else.

Tests (and, later, third-party adapter directories) can extend
``omitnix.adapters.__path__`` and go through this exact code path.
"""

from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass, field
from types import ModuleType

from .adapters.base import Adapter
from .errors import AdapterContractError
from .model import AdapterInfo, Capability

ADAPTER_PACKAGE = "omitnix.adapters"


def _validate(adapter: Adapter, module_name: str) -> None:
    if not isinstance(adapter.name, str) or not adapter.name:
        raise AdapterContractError(f"{module_name}: adapter has no name")
    if not adapter.extensions:
        raise AdapterContractError(f"{module_name}: adapter '{adapter.name}' declares no extension")
    for extension in adapter.extensions:
        if not isinstance(extension, str) or not extension.startswith("."):
            raise AdapterContractError(
                f"{module_name}: adapter '{adapter.name}' declares extension {extension!r}; "
                "extensions must be strings beginning with '.'"
            )
        if extension != extension.lower():
            raise AdapterContractError(
                f"{module_name}: adapter '{adapter.name}' declares extension {extension!r}; "
                "extensions must be lower-case"
            )
    interpreters = adapter.interpreters
    if isinstance(interpreters, str) or not hasattr(interpreters, "__iter__"):
        raise AdapterContractError(
            f"{module_name}: adapter '{adapter.name}' declares interpreters "
            f"{interpreters!r}; interpreters must be an iterable of names"
        )
    for interpreter in interpreters:
        if not isinstance(interpreter, str) or not interpreter:
            raise AdapterContractError(
                f"{module_name}: adapter '{adapter.name}' declares interpreter "
                f"{interpreter!r}; interpreter names must be non-empty strings"
            )
        if interpreter != interpreter.lower():
            raise AdapterContractError(
                f"{module_name}: adapter '{adapter.name}' declares interpreter "
                f"{interpreter!r}; interpreter names must be lower-case"
            )
        if "/" in interpreter or any(char.isspace() for char in interpreter):
            raise AdapterContractError(
                f"{module_name}: adapter '{adapter.name}' declares interpreter "
                f"{interpreter!r}; interpreter names must not contain '/' or whitespace"
            )
    for capability in adapter.capabilities:
        if not isinstance(capability, Capability):
            raise AdapterContractError(
                f"{module_name}: adapter '{adapter.name}' declares {capability!r}, "
                "which is not a Capability"
            )
    if not callable(getattr(adapter, "analyze", None)):
        raise AdapterContractError(f"{module_name}: adapter '{adapter.name}' has no analyze()")


def discover_adapters(package: ModuleType | None = None) -> list[Adapter]:
    """Import every adapter module and return the instances, ordered by name."""
    package = package or importlib.import_module(ADAPTER_PACKAGE)
    found: dict[int, Adapter] = {}
    for info in pkgutil.iter_modules(package.__path__):
        if info.ispkg or info.name.startswith("_"):
            continue
        module = importlib.import_module(f"{package.__name__}.{info.name}")
        for value in vars(module).values():
            if isinstance(value, Adapter) and id(value) not in found:
                _validate(value, module.__name__)
                found[id(value)] = value
    adapters = sorted(found.values(), key=lambda adapter: adapter.name)
    names = [adapter.name for adapter in adapters]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise AdapterContractError(f"more than one adapter is named: {', '.join(duplicates)}")
    return adapters


@dataclass(frozen=True, slots=True)
class AdapterSet:
    """The adapters taking part in a run, plus the routing tables."""

    adapters: tuple[Adapter, ...]
    by_extension: dict[str, Adapter]
    #: Interpreter name -> adapter, for files that carry no extension and so can only
    #: be routed by the interpreter their first line asks for.
    by_interpreter: dict[str, Adapter] = field(default_factory=dict)

    def for_path(self, path: str) -> Adapter | None:
        extension = _extension_of(path)
        return self.by_extension.get(extension) if extension else None

    def for_interpreter(self, interpreter: str) -> Adapter | None:
        """The adapter declaring this interpreter name, or ``None``."""
        return self.by_interpreter.get(interpreter)

    def info(self) -> tuple[AdapterInfo, ...]:
        return tuple(
            AdapterInfo(
                name=adapter.name,
                extensions=tuple(adapter.extensions),
                capabilities=tuple(sorted(adapter.capabilities, key=str)),
            )
            for adapter in self.adapters
        )


def _extension_of(path: str) -> str:
    name = path.rsplit("/", 1)[-1]
    dot = name.rfind(".")
    if dot <= 0:  # no extension, or a dotfile such as ".gitignore"
        return ""
    return name[dot:].lower()


#: How much of a file the first-line probe reads. A ``#!`` line is short, and reading
#: the whole file to look at its first line would make the probe as expensive as the
#: analysis it decides whether to run.
SHEBANG_PROBE_BYTES = 256


def interpreter_of(head: bytes) -> str | None:
    """The interpreter a file's first line asks for, normalised, or ``None``.

    ``head`` is the first :data:`SHEBANG_PROBE_BYTES` bytes of the file. The caller
    reads them; this function only interprets them, so the parse can be checked
    without a filesystem. Anything that is not a ``#!`` line is no interpreter at
    all -- including a BOM placed before it, which an OS would not execute either --
    as is a first line that is not UTF-8.

    ``#!/usr/bin/env php`` looks past ``env`` and skips option words and
    ``NAME=value`` assignments, because the name that matters is the program env is
    asked to run. Trailing digits and dots are stripped (``php8.2`` -> ``php``,
    ``python3.11`` -> ``python``) so a versioned interpreter still routes to the
    adapter for the language.
    """
    if not head.startswith(b"#!"):
        return None
    line = head.split(b"\n", 1)[0].rstrip(b"\r")
    try:
        words = line[2:].decode("utf-8").split()
    except UnicodeDecodeError:
        return None
    if not words:
        return None

    name = words[0].rsplit("/", 1)[-1].lower()
    if name == "env":
        name = next(
            (
                word.rsplit("/", 1)[-1].lower()
                for word in words[1:]
                if not word.startswith("-") and "=" not in word
            ),
            "",
        )
    return name.rstrip("0123456789.") or None


def build_adapter_set(
    overrides: dict[str, str] | None = None,
    adapters: list[Adapter] | None = None,
) -> AdapterSet:
    """Resolve extension -> adapter and interpreter -> adapter.

    Two adapters claiming the same extension is a defect, not something to resolve by
    import order; the repository can settle it in ``adapters:`` in its configuration.
    Two adapters declaring the same interpreter name is the same defect, except that
    no configuration exists to settle it -- the declaration itself has to be fixed.
    """
    adapters = list(discover_adapters()) if adapters is None else list(adapters)
    by_name = {adapter.name: adapter for adapter in adapters}
    by_extension: dict[str, Adapter] = {}
    claimed: dict[str, list[str]] = {}

    for extension, adapter_name in (overrides or {}).items():
        adapter = by_name.get(adapter_name)
        if adapter is None:
            known = ", ".join(sorted(by_name)) or "(none installed)"
            raise AdapterContractError(
                f"configuration maps '{extension}' to unknown adapter '{adapter_name}'. "
                f"Known adapters: {known}"
            )
        by_extension[extension.lower()] = adapter

    for adapter in adapters:
        for extension in adapter.extensions:
            claimed.setdefault(extension, []).append(adapter.name)

    conflicts = {
        extension: names
        for extension, names in claimed.items()
        if len(names) > 1 and extension not in by_extension
    }
    if conflicts:
        detail = "; ".join(
            f"{extension} claimed by {', '.join(sorted(names))}"
            for extension, names in sorted(conflicts.items())
        )
        raise AdapterContractError(
            f"extension claimed by more than one adapter ({detail}). "
            "Resolve it with 'adapters:' in .omitnix.yaml"
        )

    for extension, names in claimed.items():
        by_extension.setdefault(extension, by_name[names[0]])

    claimed_interpreters: dict[str, list[str]] = {}
    for adapter in adapters:
        for interpreter in adapter.interpreters:
            claimed_interpreters.setdefault(interpreter, []).append(adapter.name)

    interpreter_conflicts = {
        interpreter: names for interpreter, names in claimed_interpreters.items() if len(names) > 1
    }
    if interpreter_conflicts:
        detail = "; ".join(
            f"{interpreter} claimed by {', '.join(sorted(names))}"
            for interpreter, names in sorted(interpreter_conflicts.items())
        )
        raise AdapterContractError(
            f"interpreter claimed by more than one adapter ({detail}). "
            "Resolve it by declaring the name on only one of them"
        )

    by_interpreter = {
        interpreter: by_name[names[0]] for interpreter, names in claimed_interpreters.items()
    }

    return AdapterSet(
        adapters=tuple(adapters),
        by_extension=by_extension,
        by_interpreter=by_interpreter,
    )
