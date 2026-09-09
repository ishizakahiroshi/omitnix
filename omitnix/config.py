"""Configuration.

Nothing repository-specific belongs in the code: which paths to walk, which function
names count as authentication or authorization, and where the schema snapshot lives are
all read from ``.omitnix.yaml`` at the root of the repository being scanned.

Unknown keys are an error rather than a warning. A typo in a key that silently does
nothing is exactly how an exclusion quietly stops applying.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .errors import ConfigError
from .model import GATE_REQUIRED_CAPABILITIES, Capability

CONFIG_FILENAMES = (".omitnix.yaml", ".omitnix.yml")

#: Excluded unless the repository opts back in. Third-party trees dwarf first-party code
#: (measured: 8,021 PHP files in one repository, 7,739 of them under vendor/).
DEFAULT_EXCLUDE: tuple[str, ...] = (
    "**/.git/**",
    "**/vendor/**",
    "**/node_modules/**",
    "**/dist/**",
)

DEFAULT_INCLUDE: tuple[str, ...] = ("**/*",)
DEFAULT_OUTPUT_DIR = ".omitnix"

_KNOWN_KEYS = frozenset(
    {
        "include",
        "exclude",
        "exclude_defaults",
        "adapters",
        "authentication_functions",
        "authorization_functions",
        "schema_snapshot",
        "output_dir",
        "gate_exemptions",
        "fail_on_unknown",
    }
)

_EXEMPTION_KEYS = frozenset({"paths", "skip", "reason"})


@dataclass(frozen=True, slots=True)
class GateExemption:
    """Permission for named paths to lack a check the gate would otherwise require.

    The reason is a required field, not documentation. An exemption nobody can justify
    in writing is the mechanism by which a gate quietly stops meaning anything, so the
    configuration has no way to express one: an entry without a reason is a
    :class:`~omitnix.errors.ConfigError`, and the reason is printed every time the
    exemption is used.
    """

    paths: tuple[str, ...]
    skip: tuple[Capability, ...]
    reason: str


@dataclass(frozen=True, slots=True)
class Config:
    root: Path
    include: tuple[str, ...] = DEFAULT_INCLUDE
    exclude: tuple[str, ...] = DEFAULT_EXCLUDE
    #: Extension -> adapter name. Only needed when an extension is ambiguous or when a
    #: repository uses a non-standard extension for a known language.
    adapters: dict[str, str] = field(default_factory=dict)
    authentication_functions: tuple[str, ...] = ()
    authorization_functions: tuple[str, ...] = ()
    schema_snapshot: str | None = None
    output_dir: str = DEFAULT_OUTPUT_DIR
    gate_exemptions: tuple[GateExemption, ...] = ()
    #: Whether a file that could not be analyzed makes the run fail.
    #:
    #: Off by default, and that default is the correction of a mistake. The rule used to
    #: be unconditional, on the reasoning that a gap nobody is forced to look at is a gap
    #: that gets ignored. What it actually produced was homework: a repository could only
    #: go green by writing, into its configuration, a sentence about why each unreadable
    #: thing was out of scope. Measured on one real repository, thirty-six of its
    #: fifty-two exclusion entries existed for no other reason -- "png files are not
    #: program source" is not a decision anybody made, it is paperwork the tool demanded.
    #:
    #: Worse, some of those gaps are not the repository's to close. A grammar that cannot
    #: read valid source of a language its adapter claims is this tool's defect, and
    #: failing the run over it leaves the repository a choice between editing correct code
    #: and writing a false reason. Neither is a thing to ask of somebody.
    #:
    #: What makes a gap impossible to ignore is that the generated documents say so, in
    #: the coverage line and by name. That is a property of the report and always holds.
    #: Failing the run is a *policy* on top of it, and it only makes sense where the
    #: person reading the failure has an action available -- which is why the new-file
    #: gate, where the author is right there and can fix it, stays strict either way.
    fail_on_unknown: bool = False
    source_path: Path | None = None
    #: False when the repository said ``exclude_defaults: false``, i.e. it wants to be
    #: walked with exactly the exclusions it wrote. Recorded rather than inferred from
    #: ``exclude`` because a caller that layers further defaults on top (a workspace run)
    #: has to be able to tell "did not say" from "said no".
    exclude_defaults_kept: bool = True

    @property
    def json_path(self) -> Path:
        return self.root / self.output_dir / "index.json"


def _as_str_tuple(value: Any, key: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str) or not isinstance(value, list):
        raise ConfigError(f"'{key}' must be a list of strings")
    for item in value:
        if not isinstance(item, str):
            raise ConfigError(f"'{key}' must be a list of strings, found {type(item).__name__}")
    return tuple(value)


def _parse_gate_exemptions(raw: Any, config_path: Path) -> tuple[GateExemption, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ConfigError(f"{config_path}: 'gate_exemptions' must be a list of entries")

    allowed = {str(capability) for capability in GATE_REQUIRED_CAPABILITIES}
    exemptions: list[GateExemption] = []
    for position, entry in enumerate(raw, start=1):
        where = f"{config_path}: gate_exemptions[{position}]"
        if not isinstance(entry, dict):
            raise ConfigError(f"{where} must be a mapping with 'paths', 'skip' and 'reason'")
        unknown = sorted(set(entry) - _EXEMPTION_KEYS)
        if unknown:
            raise ConfigError(
                f"{where}: unknown key(s): {', '.join(unknown)}. "
                f"Known keys: {', '.join(sorted(_EXEMPTION_KEYS))}"
            )

        paths_raw = entry.get("paths")
        paths = (paths_raw,) if isinstance(paths_raw, str) else _as_str_tuple(paths_raw, "paths")
        if not paths:
            raise ConfigError(f"{where}: 'paths' must name at least one path or glob")

        skip_raw = entry.get("skip")
        skip_names = (skip_raw,) if isinstance(skip_raw, str) else _as_str_tuple(skip_raw, "skip")
        if not skip_names:
            raise ConfigError(f"{where}: 'skip' must name at least one check")
        unsupported = sorted(set(skip_names) - allowed)
        if unsupported:
            raise ConfigError(
                f"{where}: cannot skip {', '.join(unsupported)}. "
                f"The gate only requires: {', '.join(sorted(allowed))}"
            )

        reason = entry.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            raise ConfigError(
                f"{where}: 'reason' is required and must say why these paths are allowed "
                "to skip the check. An exemption without a stated reason is not accepted."
            )

        exemptions.append(
            GateExemption(
                paths=paths,
                skip=tuple(Capability(name) for name in skip_names),
                reason=reason.strip(),
            )
        )
    return tuple(exemptions)


def find_config_file(root: Path) -> Path | None:
    for name in CONFIG_FILENAMES:
        candidate = root / name
        if candidate.is_file():
            return candidate
    return None


def load_config(root: Path, config_path: Path | None = None) -> Config:
    """Load the configuration for ``root``.

    A repository without a configuration file is valid and gets the defaults: the whole
    tree minus the default exclusions. That matters because the tool has to run across
    many repositories without one being placed in each of them first.
    """
    root = root.resolve()
    if config_path is None:
        config_path = find_config_file(root)
    elif not config_path.is_file():
        raise ConfigError(f"configuration file not found: {config_path}")

    if config_path is None:
        return Config(root=root)

    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"{config_path}: invalid YAML: {exc}") from exc
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ConfigError(f"{config_path}: top level must be a mapping")

    unknown = sorted(set(raw) - _KNOWN_KEYS)
    if unknown:
        known = ", ".join(sorted(_KNOWN_KEYS))
        raise ConfigError(
            f"{config_path}: unknown key(s): {', '.join(unknown)}. Known keys: {known}"
        )

    include = _as_str_tuple(raw.get("include"), "include") or DEFAULT_INCLUDE
    user_exclude = _as_str_tuple(raw.get("exclude"), "exclude")
    keep_defaults = raw.get("exclude_defaults", True)
    if not isinstance(keep_defaults, bool):
        raise ConfigError(f"{config_path}: 'exclude_defaults' must be true or false")
    exclude = (DEFAULT_EXCLUDE + user_exclude) if keep_defaults else user_exclude

    adapters_raw = raw.get("adapters") or {}
    if not isinstance(adapters_raw, dict):
        raise ConfigError(
            f"{config_path}: 'adapters' must be a mapping of extension to adapter name"
        )
    adapters: dict[str, str] = {}
    for extension, adapter_name in adapters_raw.items():
        if not isinstance(extension, str) or not isinstance(adapter_name, str):
            raise ConfigError(f"{config_path}: 'adapters' must map strings to strings")
        if not extension.startswith("."):
            raise ConfigError(f"{config_path}: adapter key '{extension}' must start with '.'")
        adapters[extension.lower()] = adapter_name

    schema_snapshot = raw.get("schema_snapshot")
    if schema_snapshot is not None and not isinstance(schema_snapshot, str):
        raise ConfigError(f"{config_path}: 'schema_snapshot' must be a string path")

    output_dir = raw.get("output_dir", DEFAULT_OUTPUT_DIR)
    if not isinstance(output_dir, str) or not output_dir:
        raise ConfigError(f"{config_path}: 'output_dir' must be a non-empty string")

    fail_on_unknown = raw.get("fail_on_unknown", False)
    if not isinstance(fail_on_unknown, bool):
        raise ConfigError(f"{config_path}: 'fail_on_unknown' must be true or false")

    return Config(
        root=root,
        include=include,
        exclude=exclude,
        adapters=adapters,
        authentication_functions=_as_str_tuple(
            raw.get("authentication_functions"), "authentication_functions"
        ),
        authorization_functions=_as_str_tuple(
            raw.get("authorization_functions"), "authorization_functions"
        ),
        schema_snapshot=schema_snapshot,
        output_dir=output_dir,
        gate_exemptions=_parse_gate_exemptions(raw.get("gate_exemptions"), config_path),
        fail_on_unknown=fail_on_unknown,
        source_path=config_path,
        exclude_defaults_kept=keep_defaults,
    )
