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
from dataclasses import dataclass
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
    """The adapters taking part in a run, plus the extension routing table."""

    adapters: tuple[Adapter, ...]
    by_extension: dict[str, Adapter]

    def for_path(self, path: str) -> Adapter | None:
        extension = _extension_of(path)
        return self.by_extension.get(extension) if extension else None

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


def build_adapter_set(
    overrides: dict[str, str] | None = None,
    adapters: list[Adapter] | None = None,
) -> AdapterSet:
    """Resolve extension -> adapter.

    Two adapters claiming the same extension is a defect, not something to resolve by
    import order; the repository can settle it in ``adapters:`` in its configuration.
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

    return AdapterSet(adapters=tuple(adapters), by_extension=by_extension)
