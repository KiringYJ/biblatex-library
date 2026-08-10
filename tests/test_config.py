"""Tests for required workspace path configuration."""

from pathlib import Path

import pytest

from biblio.config import CONFIG_FILENAME, BiblioConfig
from biblio.exceptions import ConfigError


def test_defaults_resolve_all_required_paths(tmp_path: Path):
    config = BiblioConfig.defaults(tmp_path)

    assert config.root == tmp_path.resolve()
    assert config.bib_path == tmp_path.resolve() / "bib" / "library.bib"
    assert config.identifier_path == tmp_path.resolve() / "data" / "identifier_collection.json"
    assert config.add_order_path == tmp_path.resolve() / "data" / "add_order.json"
    assert config.staging_dir == tmp_path.resolve() / "staging"


def test_from_toml_resolves_all_custom_paths(tmp_path: Path):
    config_path = tmp_path / CONFIG_FILENAME
    config_path.write_text(
        """\
[paths]
bib = "references/library.bib"
identifiers = "metadata/identifiers.json"
add_order = "metadata/add_order.json"
staging = "incoming"
""",
        encoding="utf-8",
    )

    config = BiblioConfig.from_toml(config_path)

    assert config.bib_path == (tmp_path / "references" / "library.bib").resolve()
    assert config.identifier_path == (tmp_path / "metadata" / "identifiers.json").resolve()
    assert config.add_order_path == (tmp_path / "metadata" / "add_order.json").resolve()
    assert config.staging_dir == (tmp_path / "incoming").resolve()


def test_from_toml_uses_resolved_defaults_for_missing_values(tmp_path: Path):
    config_path = tmp_path / CONFIG_FILENAME
    config_path.write_text("[paths]\n", encoding="utf-8")

    config = BiblioConfig.from_toml(config_path)

    assert config == BiblioConfig.defaults(tmp_path)


@pytest.mark.parametrize("path_key", ["identifiers", "add_order"])
def test_from_toml_does_not_ignore_restored_path_keys(tmp_path: Path, path_key: str):
    config_path = tmp_path / CONFIG_FILENAME
    config_path.write_text(f'[paths]\n{path_key} = "custom.json"\n', encoding="utf-8")

    config = BiblioConfig.from_toml(config_path)

    configured_path = config.identifier_path if path_key == "identifiers" else config.add_order_path
    assert configured_path == (tmp_path / "custom.json").resolve()


def test_from_toml_rejects_unknown_path_key(tmp_path: Path):
    config_path = tmp_path / CONFIG_FILENAME
    config_path.write_text('[paths]\nfuture = "unknown"\n', encoding="utf-8")

    with pytest.raises(ConfigError, match="Unsupported .* key"):
        BiblioConfig.from_toml(config_path)


def test_from_toml_rejects_invalid_paths_table(tmp_path: Path):
    config_path = tmp_path / CONFIG_FILENAME
    config_path.write_text('paths = "invalid"\n', encoding="utf-8")

    with pytest.raises(ConfigError, match="must be a table"):
        BiblioConfig.from_toml(config_path)


def test_from_toml_rejects_non_string_path(tmp_path: Path):
    config_path = tmp_path / CONFIG_FILENAME
    config_path.write_text("[paths]\nbib = 42\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="must be strings"):
        BiblioConfig.from_toml(config_path)


def test_discover_walks_up(tmp_path: Path):
    config_path = tmp_path / CONFIG_FILENAME
    config_path.write_text('[paths]\nbib = "library.bib"\n', encoding="utf-8")
    child = tmp_path / "one" / "two"
    child.mkdir(parents=True)

    config = BiblioConfig.discover(child)

    assert config.root == tmp_path.resolve()
    assert config.bib_path == (tmp_path / "library.bib").resolve()


def test_discover_falls_back_to_origin_defaults(tmp_path: Path):
    assert BiblioConfig.discover(tmp_path) == BiblioConfig.defaults(tmp_path)


def test_with_overrides_changes_only_supplied_paths(tmp_path: Path):
    config = BiblioConfig.defaults(tmp_path)
    custom_identifiers = tmp_path / "custom-identifiers.json"
    custom_order = tmp_path / "custom-order.json"

    overridden = config.with_overrides(
        identifier_path=custom_identifiers,
        add_order_path=custom_order,
    )

    assert overridden.bib_path == config.bib_path
    assert overridden.identifier_path == custom_identifiers.resolve()
    assert overridden.add_order_path == custom_order.resolve()
    assert overridden.staging_dir == config.staging_dir
