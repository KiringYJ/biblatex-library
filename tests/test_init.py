"""Tests for biblio init workspace scaffolding."""

import tempfile
from pathlib import Path

import pytest

from biblio.config import CONFIG_FILENAME
from biblio.init import init_workspace


def test_init_creates_all_files():
    """init_workspace creates biblio.toml and empty data files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        target = Path(tmpdir)
        created = init_workspace(target)

        assert CONFIG_FILENAME in created
        assert "bib/library.bib" in created
        assert "data/identifier_collection.json" in created
        assert "data/add_order.json" in created

        # Verify files exist
        assert (target / CONFIG_FILENAME).exists()
        assert (target / "bib" / "library.bib").exists()
        assert (target / "data" / "identifier_collection.json").exists()
        assert (target / "data" / "add_order.json").exists()
        assert (target / "staging").is_dir()


def test_init_toml_content():
    """Generated biblio.toml contains [paths] section."""
    with tempfile.TemporaryDirectory() as tmpdir:
        target = Path(tmpdir)
        init_workspace(target)

        content = (target / CONFIG_FILENAME).read_text(encoding="utf-8")
        assert "[paths]" in content
        assert 'bib = "bib/library.bib"' in content


def test_init_empty_data_files():
    """Generated data files contain valid empty structures."""
    with tempfile.TemporaryDirectory() as tmpdir:
        target = Path(tmpdir)
        init_workspace(target)

        ids = (target / "data" / "identifier_collection.json").read_text(encoding="utf-8")
        assert ids.strip() == "{}"
        order = (target / "data" / "add_order.json").read_text(encoding="utf-8")
        assert order.strip() == "[]"


def test_init_refuses_existing_toml():
    """init_workspace raises FileExistsError if biblio.toml already exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        target = Path(tmpdir)
        (target / CONFIG_FILENAME).write_text("existing", encoding="utf-8")

        with pytest.raises(FileExistsError, match="already exists"):
            init_workspace(target)


def test_init_force_overwrites_toml():
    """--force overwrites existing biblio.toml."""
    with tempfile.TemporaryDirectory() as tmpdir:
        target = Path(tmpdir)
        (target / CONFIG_FILENAME).write_text("old content", encoding="utf-8")

        created = init_workspace(target, force=True)

        assert CONFIG_FILENAME in created
        content = (target / CONFIG_FILENAME).read_text(encoding="utf-8")
        assert "[paths]" in content


def test_init_skips_existing_data_files():
    """init_workspace does not overwrite existing data files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        target = Path(tmpdir)
        bib_dir = target / "bib"
        bib_dir.mkdir()
        existing_bib = bib_dir / "library.bib"
        existing_bib.write_text("@book{existing, title={Test}}", encoding="utf-8")

        created = init_workspace(target)

        # bib file should NOT be in created list (skipped)
        assert "bib/library.bib" not in created
        # Original content preserved
        assert "existing" in existing_bib.read_text(encoding="utf-8")


def test_init_creates_directories():
    """init_workspace creates bib/, data/, staging/ directories."""
    with tempfile.TemporaryDirectory() as tmpdir:
        target = Path(tmpdir)
        init_workspace(target)

        assert (target / "bib").is_dir()
        assert (target / "data").is_dir()
        assert (target / "staging").is_dir()
