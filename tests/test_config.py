"""Reading `.omitnix.yaml`, and refusing to read it wrongly.

A configuration file is where a repository states what the tool must not walk. A typo in
a key that silently does nothing is how an exclusion stops applying without anyone
noticing, so unknown keys and wrong types are errors here, not warnings.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from omitnix.config import DEFAULT_EXCLUDE, load_config
from omitnix.errors import ConfigError

from .conftest import write_repo


def test_a_repository_without_configuration_still_runs(tmp_path: Path) -> None:
    config = load_config(tmp_path)
    assert config.include == ("**/*",)
    assert config.exclude == DEFAULT_EXCLUDE
    assert config.source_path is None


def test_user_exclusions_extend_the_defaults(tmp_path: Path) -> None:
    write_repo(tmp_path, {".omitnix.yaml": "exclude:\n  - 'legacy/**'\n"})
    config = load_config(tmp_path)
    assert "legacy/**" in config.exclude
    assert "**/vendor/**" in config.exclude


def test_defaults_can_be_dropped_deliberately(tmp_path: Path) -> None:
    write_repo(
        tmp_path,
        {".omitnix.yaml": "exclude_defaults: false\nexclude:\n  - 'legacy/**'\n"},
    )
    assert load_config(tmp_path).exclude == ("legacy/**",)


def test_unknown_key_is_rejected(tmp_path: Path) -> None:
    write_repo(tmp_path, {".omitnix.yaml": "excludes:\n  - 'legacy/**'\n"})
    with pytest.raises(ConfigError, match="unknown key"):
        load_config(tmp_path)


def test_wrong_type_is_rejected(tmp_path: Path) -> None:
    write_repo(tmp_path, {".omitnix.yaml": "include: '**/*.flow'\n"})
    with pytest.raises(ConfigError, match="must be a list of strings"):
        load_config(tmp_path)


def test_adapter_override_needs_a_dotted_extension(tmp_path: Path) -> None:
    write_repo(tmp_path, {".omitnix.yaml": "adapters:\n  flow: flow\n"})
    with pytest.raises(ConfigError, match="must start with"):
        load_config(tmp_path)


def test_output_paths_follow_the_configured_directory(tmp_path: Path) -> None:
    write_repo(tmp_path, {".omitnix.yaml": "output_dir: docs/inventory\n"})
    config = load_config(tmp_path)
    assert config.json_path == config.root / "docs/inventory" / "index.json"
