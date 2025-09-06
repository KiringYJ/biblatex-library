"""Tests for the sync module."""

import json
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest

from biblib.sync import (
    load_bibtex_library,
    load_identifier_collection,
    sync_identifiers_to_library,
)


@pytest.fixture
def temp_identifier_collection() -> Generator[Path, None, None]:
    """Create a temporary identifier collection JSON file."""
    data = {
        "test-entry-1": {
            "main_identifier": "doi",
            "identifiers": {
                "doi": "10.1007/978-1-4757-6848-0",
                "isbn13": "978-0387979267",
                "arxiv": "2411.19768",
            },
        },
        "test-entry-2": {
            "main_identifier": "acmdl_doi",
            "identifiers": {"acmdl_doi": "doi:10.5555/197600.197619", "mrnumber": "1234567"},
        },
        "test-entry-3": {
            "main_identifier": "doi",
            "identifiers": {
                "doi": "DOI:10.1090/chel/370",  # Test case normalization
                "url": "//example.com/paper",  # Test URL normalization
            },
        },
        "missing-entry": {"main_identifier": "doi", "identifiers": {"doi": "10.1000/missing"}},
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        temp_path = Path(f.name)

    try:
        yield temp_path
    finally:
        temp_path.unlink()


@pytest.fixture
def temp_library_bib() -> Generator[Path, None, None]:
    """Create a temporary library.bib file with test entries."""
    content = """@book{test-entry-1,
  author = {Test, Author},
  title = {Test Book},
  year = {2020},
  isbn = {0-387-97926-3}
}

@article{test-entry-2,
  author = {Another, Author},
  title = {Test Article},
  year = {2021}
}

@inproceedings{test-entry-3,
  author = {Third, Author},
  title = {Test Proceedings},
  year = {2022},
  doi = {10.1090/chel/370},
  url = {https://example.com/existing}
}
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".bib", delete=False, encoding="utf-8") as f:
        f.write(content)
        temp_path = Path(f.name)

    try:
        yield temp_path
    finally:
        temp_path.unlink()


class TestLoadIdentifierCollection:
    """Tests for load_identifier_collection function."""

    def test_load_valid_collection(self, temp_identifier_collection: Path):
        """Test loading a valid identifier collection."""
        data = load_identifier_collection(temp_identifier_collection)

        assert len(data) == 4
        assert "test-entry-1" in data
        entry_data = data["test-entry-1"]
        assert entry_data["main_identifier"] == "doi"

        # Check identifiers exist - the exact structure will be tested in integration
        assert "identifiers" in entry_data
        assert isinstance(entry_data["identifiers"], dict)

    def test_load_nonexistent_file(self):
        """Test loading a non-existent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="Identifier collection not found"):
            load_identifier_collection(Path("nonexistent.json"))

    def test_load_invalid_json(self):
        """Test loading invalid JSON raises ValueError."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            f.write("invalid json content")
            temp_path = Path(f.name)

        try:
            with pytest.raises(ValueError, match="Invalid JSON"):
                load_identifier_collection(temp_path)
        finally:
            temp_path.unlink()


class TestLoadBibtexLibrary:
    """Tests for load_bibtex_library function."""

    def test_load_valid_library(self, temp_library_bib: Path):
        """Test loading a valid bibtex library."""
        _, entry_map = load_bibtex_library(temp_library_bib)

        assert len(entry_map) == 3
        assert "test-entry-1" in entry_map
        assert "test-entry-2" in entry_map
        assert "test-entry-3" in entry_map

        # Check that we can access entry fields
        entry1 = entry_map["test-entry-1"]
        assert entry1.key == "test-entry-1"
        assert "author" in entry1.fields_dict

    def test_load_nonexistent_file(self):
        """Test loading a non-existent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="Library file not found"):
            load_bibtex_library(Path("nonexistent.bib"))


class TestSyncIdentifiersToLibrary:
    """Tests for the main sync function."""

    def test_sync_dry_run(self, temp_library_bib: Path, temp_identifier_collection: Path):
        """Test sync in dry-run mode."""
        success, changes = sync_identifiers_to_library(
            temp_library_bib, temp_identifier_collection, dry_run=True
        )

        assert success is True
        assert len(changes) > 0

        # Check that some expected changes are present
        change_texts = "\n".join(changes)
        assert "test-entry-1" in change_texts
        assert "eprint" in change_texts  # arxiv should map to eprint
        assert "isbn" in change_texts  # isbn13 should map to isbn

    def test_sync_actual_changes(self, temp_library_bib: Path, temp_identifier_collection: Path):
        """Test sync with actual changes applied."""
        # First, verify initial state
        _, entry_map_before = load_bibtex_library(temp_library_bib)
        entry1_before = entry_map_before["test-entry-1"]
        assert "eprint" not in entry1_before.fields_dict

        # Run sync
        success, changes = sync_identifiers_to_library(
            temp_library_bib, temp_identifier_collection, dry_run=False
        )

        assert success is True
        assert len(changes) > 0

        # Verify changes were applied
        _, entry_map_after = load_bibtex_library(temp_library_bib)

        # Check that arXiv ID was added as eprint
        entry1_after = entry_map_after["test-entry-1"]
        assert "eprint" in entry1_after.fields_dict
        eprint_value = str(entry1_after.fields_dict["eprint"].value)
        assert eprint_value == "2411.19768"

        # Check that ACM DL DOI was converted to URL
        entry2_after = entry_map_after["test-entry-2"]
        assert "url" in entry2_after.fields_dict
        url_value = str(entry2_after.fields_dict["url"].value)
        assert url_value == "https://dl.acm.org/doi/10.5555/197600.197619"

    def test_sync_specific_fields(self, temp_library_bib: Path, temp_identifier_collection: Path):
        """Test sync with specific field filtering."""
        success, changes = sync_identifiers_to_library(
            temp_library_bib,
            temp_identifier_collection,
            dry_run=True,
            fields_to_sync={"eprint"},  # Only sync eprint fields
        )

        assert success is True

        # Check that only eprint changes are included
        change_texts = "\n".join(changes)
        assert "eprint" in change_texts
        # Should not include isbn or url changes
        for change in changes:
            assert "isbn" not in change
            # url might be in same entry, so check more specifically
            if "url" in change:
                assert "eprint" in change  # Both in same entry

    def test_sync_missing_entry_warning(
        self, temp_library_bib: Path, temp_identifier_collection: Path
    ):
        """Test that missing entries generate warnings but don't fail sync."""
        success, changes = sync_identifiers_to_library(
            temp_library_bib, temp_identifier_collection, dry_run=True
        )

        # Should succeed despite missing entry
        assert success is True

        # Missing entry should not appear in changes
        change_texts = "\n".join(changes)
        assert "missing-entry" not in change_texts

    def test_sync_no_changes_needed(self, temp_library_bib: Path):
        """Test sync when no changes are needed."""
        # Create identifier collection that matches existing data
        matching_data = {
            "test-entry-3": {
                "main_identifier": "doi",
                "identifiers": {
                    "doi": "10.1090/chel/370",  # This already exists in the bib file
                },
            }
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(matching_data, f, indent=2)
            temp_id_path = Path(f.name)

        try:
            success, changes = sync_identifiers_to_library(
                temp_library_bib, temp_id_path, dry_run=True
            )

            assert success is True
            assert len(changes) == 0  # No changes needed
        finally:
            temp_id_path.unlink()

    def test_sync_file_errors(self):
        """Test sync with file access errors."""
        # Test with non-existent files
        with pytest.raises(FileNotFoundError):
            sync_identifiers_to_library(Path("nonexistent.bib"), Path("nonexistent.json"))


class TestIntegrationScenarios:
    """Integration tests for realistic sync scenarios."""

    def test_arxiv_to_eprint_mapping(self):
        """Test complete arXiv ID mapping scenario."""
        # Create test data
        bib_content = """@article{test-arxiv,
  author = {Test, Author},
  title = {Test Paper},
  year = {2024}
}
"""

        identifier_data = {
            "test-arxiv": {"main_identifier": "arxiv", "identifiers": {"arxiv": "2411.19768"}}
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".bib", delete=False, encoding="utf-8"
        ) as f:
            f.write(bib_content)
            bib_path = Path(f.name)

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(identifier_data, f)
            id_path = Path(f.name)

        try:
            success, changes = sync_identifiers_to_library(bib_path, id_path, dry_run=False)

            assert success is True
            assert len(changes) == 1
            assert "eprint" in changes[0]
            assert "2411.19768" in changes[0]

            # Verify the change was applied
            _, entry_map = load_bibtex_library(bib_path)
            entry = entry_map["test-arxiv"]
            assert "eprint" in entry.fields_dict
            eprint_value = str(entry.fields_dict["eprint"].value)
            assert eprint_value == "2411.19768"

        finally:
            bib_path.unlink()
            id_path.unlink()

    def test_acm_dl_doi_to_url_conversion(self):
        """Test ACM DL DOI to URL conversion scenario."""
        bib_content = """@inproceedings{test-acm,
  author = {Test, Author},
  title = {Test Paper},
  year = {2024}
}
"""

        identifier_data = {
            "test-acm": {
                "main_identifier": "acmdl_doi",
                "identifiers": {"acmdl_doi": "doi:10.5555/197600.197619"},
            }
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".bib", delete=False, encoding="utf-8"
        ) as f:
            f.write(bib_content)
            bib_path = Path(f.name)

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(identifier_data, f)
            id_path = Path(f.name)

        try:
            success, changes = sync_identifiers_to_library(bib_path, id_path, dry_run=False)

            assert success is True
            assert len(changes) == 1
            assert "url" in changes[0]
            expected_url = "https://dl.acm.org/doi/10.5555/197600.197619"
            assert expected_url in changes[0]

            # Verify the change was applied
            _, entry_map = load_bibtex_library(bib_path)
            entry = entry_map["test-acm"]
            assert "url" in entry.fields_dict
            url_value = str(entry.fields_dict["url"].value)
            assert url_value == expected_url

        finally:
            bib_path.unlink()
            id_path.unlink()

    def test_doi_normalization(self):
        """Test DOI prefix normalization."""
        bib_content = """@article{test-doi,
  author = {Test, Author},
  title = {Test Paper},
  year = {2024}
}
"""

        identifier_data = {
            "test-doi": {
                "main_identifier": "doi",
                "identifiers": {"doi": "DOI:10.1007/test-normalization"},
            }
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".bib", delete=False, encoding="utf-8"
        ) as f:
            f.write(bib_content)
            bib_path = Path(f.name)

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(identifier_data, f)
            id_path = Path(f.name)

        try:
            success, changes = sync_identifiers_to_library(bib_path, id_path, dry_run=False)

            assert success is True
            assert len(changes) == 1

            # Verify DOI prefix was removed
            _, entry_map = load_bibtex_library(bib_path)
            entry = entry_map["test-doi"]
            assert "doi" in entry.fields_dict
            doi_value = str(entry.fields_dict["doi"].value)
            assert doi_value == "10.1007/test-normalization"
            assert not doi_value.startswith("DOI:")

        finally:
            bib_path.unlink()
            id_path.unlink()

    def test_isbn_field_mapping(self):
        """Test ISBN13 to ISBN field mapping."""
        bib_content = """@book{test-isbn,
  author = {Test, Author},
  title = {Test Book},
  year = {2024}
}
"""

        identifier_data = {
            "test-isbn": {"main_identifier": "isbn13", "identifiers": {"isbn13": "978-0387979267"}}
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".bib", delete=False, encoding="utf-8"
        ) as f:
            f.write(bib_content)
            bib_path = Path(f.name)

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(identifier_data, f)
            id_path = Path(f.name)

        try:
            success, changes = sync_identifiers_to_library(bib_path, id_path, dry_run=False)

            assert success is True
            assert len(changes) == 1
            assert "isbn" in changes[0]  # Should be mapped to isbn field

            # Verify the change was applied to isbn field
            _, entry_map = load_bibtex_library(bib_path)
            entry = entry_map["test-isbn"]
            assert "isbn" in entry.fields_dict
            isbn_value = str(entry.fields_dict["isbn"].value)
            assert isbn_value == "978-0387979267"

        finally:
            bib_path.unlink()
            id_path.unlink()


class TestErrorHandling:
    """Tests for error handling scenarios."""

    def test_invalid_json_content(self):
        """Test handling of malformed JSON."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            f.write('{"invalid": json content}')
            temp_path = Path(f.name)

        try:
            with pytest.raises(ValueError, match="Invalid JSON"):
                load_identifier_collection(temp_path)
        finally:
            temp_path.unlink()

    def test_invalid_bibtex_content(self):
        """Test handling of malformed BibTeX."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".bib", delete=False, encoding="utf-8"
        ) as f:
            f.write("@invalid{bibtex content")
            temp_path = Path(f.name)

        try:
            # bibtexparser v2 handles malformed content gracefully
            # rather than raising an exception, so we test that it
            # can still load the file (even if it has parsing failures)
            _, entry_map = load_bibtex_library(temp_path)
            # The malformed entry won't be in the entry map
            assert len(entry_map) == 0
        finally:
            temp_path.unlink()
