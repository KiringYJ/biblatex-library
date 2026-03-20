"""Tests for BlxConfig: TOML parsing, discovery, overrides, and defaults."""

import tempfile
from pathlib import Path

import pytest

from biblib.config import CONFIG_FILENAME, BlxConfig
from biblib.exceptions import ConfigError


def test_defaults_creates_standard_layout():
    """Default config produces the original repo layout."""
    root = Path("/fake/root")
    config = BlxConfig.defaults(root)

    assert config.bib_path == root.resolve() / "bib" / "library.bib"
    assert config.identifier_path == root.resolve() / "data" / "identifier_collection.json"
    assert config.add_order_path == root.resolve() / "data" / "add_order.json"
    assert config.staging_dir == root.resolve() / "staging"


def test_from_toml_with_defaults():
    """Parsing an empty [paths] table falls back to defaults."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        toml_path = root / CONFIG_FILENAME
        toml_path.write_text("[paths]\n", encoding="utf-8")

        config = BlxConfig.from_toml(toml_path)

        assert config.bib_path == root / "bib" / "library.bib"
        assert config.identifier_path == root / "data" / "identifier_collection.json"


def test_from_toml_custom_paths():
    """Custom paths in blx.toml are resolved relative to config file directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        toml_path = root / CONFIG_FILENAME
        toml_path.write_text(
            '[paths]\nbib = "my/refs.bib"\nidentifiers = "my/ids.json"\n',
            encoding="utf-8",
        )

        config = BlxConfig.from_toml(toml_path)

        assert config.bib_path == (root / "my" / "refs.bib").resolve()
        assert config.identifier_path == (root / "my" / "ids.json").resolve()
        # Unspecified paths keep defaults
        assert config.add_order_path == (root / "data" / "add_order.json").resolve()


def test_from_toml_no_paths_section():
    """A TOML file with no [paths] section uses all defaults."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        toml_path = root / CONFIG_FILENAME
        toml_path.write_text("# empty config\n", encoding="utf-8")

        config = BlxConfig.from_toml(toml_path)

        assert config.bib_path == (root / "bib" / "library.bib").resolve()


def test_from_toml_invalid_paths_type():
    """Non-table [paths] value raises ConfigError."""
    with tempfile.TemporaryDirectory() as tmpdir:
        toml_path = Path(tmpdir) / CONFIG_FILENAME
        toml_path.write_text('paths = "not a table"\n', encoding="utf-8")

        with pytest.raises(ConfigError, match="must be a table"):
            BlxConfig.from_toml(toml_path)


def test_from_toml_invalid_path_value():
    """Non-string path values raise ConfigError."""
    with tempfile.TemporaryDirectory() as tmpdir:
        toml_path = Path(tmpdir) / CONFIG_FILENAME
        toml_path.write_text("[paths]\nbib = 42\n", encoding="utf-8")

        with pytest.raises(ConfigError, match="must be strings"):
            BlxConfig.from_toml(toml_path)


def test_discover_finds_toml_in_cwd():
    """discover() finds blx.toml in the start directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        toml_path = root / CONFIG_FILENAME
        toml_path.write_text('[paths]\nbib = "custom.bib"\n', encoding="utf-8")

        config = BlxConfig.discover(start=root)

        assert config.bib_path == (root / "custom.bib").resolve()


def test_discover_walks_up():
    """discover() walks up parent directories to find blx.toml."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        toml_path = root / CONFIG_FILENAME
        toml_path.write_text('[paths]\nbib = "top.bib"\n', encoding="utf-8")

        child = root / "a" / "b" / "c"
        child.mkdir(parents=True)

        config = BlxConfig.discover(start=child)

        assert config.bib_path == (root / "top.bib").resolve()


def test_discover_falls_back_to_defaults():
    """discover() returns defaults when no blx.toml exists anywhere."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        config = BlxConfig.discover(start=root)

        assert config.bib_path == root / "bib" / "library.bib"
        assert config.root == root


def test_with_overrides():
    """with_overrides replaces only specified paths."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        config = BlxConfig.defaults(root)
        override_bib = root / "other" / "refs.bib"

        new_config = config.with_overrides(bib_path=override_bib)

        assert new_config.bib_path == override_bib.resolve()
        # Others unchanged
        assert new_config.identifier_path == config.identifier_path
        assert new_config.add_order_path == config.add_order_path
        assert new_config.staging_dir == config.staging_dir


def test_with_overrides_none_is_noop():
    """with_overrides with all None returns identical config."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        config = BlxConfig.defaults(root)

        new_config = config.with_overrides()

        assert new_config.bib_path == config.bib_path
        assert new_config.identifier_path == config.identifier_path


def test_schema_path_exists():
    """Bundled schema file should exist on disk."""
    schema = BlxConfig.schema_path()
    assert schema.exists()
    assert schema.name == "identifier_collection.schema.json"
