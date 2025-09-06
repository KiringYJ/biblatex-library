"""Tests for adding new entries from staging files."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from biblib.add_entries import (
    add_entries_from_staging,
    find_staging_pairs,
    process_staging_entry,
)


def test_find_staging_pairs():
    """Test finding matching .bib/.json file pairs in staging."""
    with tempfile.TemporaryDirectory() as tmpdir:
        staging = Path(tmpdir)

        # Create test files
        (staging / "2025-01-15-test1.bib").touch()
        (staging / "2025-01-15-test1.json").touch()
        (staging / "2025-01-15-test2.bib").touch()
        (staging / "2025-01-15-test2.json").touch()  # Add missing .json file
        (staging / "2025-01-15-orphan.bib").touch()  # No matching .json
        (staging / "2025-01-15-orphan2.json").touch()  # No matching .bib
        (staging / "invalid-name.bib").touch()  # Wrong pattern

        pairs = find_staging_pairs(staging)

        assert len(pairs) == 2
        assert (
            "2025-01-15-test1",
            staging / "2025-01-15-test1.bib",
            staging / "2025-01-15-test1.json",
        ) in pairs
        assert (
            "2025-01-15-test2",
            staging / "2025-01-15-test2.bib",
            staging / "2025-01-15-test2.json",
        ) in pairs


def test_process_staging_entry_success():
    """Test successful processing of a staging entry."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)

        # Create test staging files
        bib_content = """@article{temp-key,
    title = {Test Article},
    author = {Smith, John},
    year = {2025}
}"""
        json_content = {"temp-key": {"identifiers": {"doi": "10.1000/test"}}}

        bib_file = workspace / "test.bib"
        json_file = workspace / "test.json"

        bib_file.write_text(bib_content, encoding="utf-8")
        json_file.write_text(json.dumps(json_content, indent=2), encoding="utf-8")

        # Mock existing data files (empty)
        existing_keys: set[str] = set()

        with patch("biblib.add_entries.generate_labels") as mock_gen:
            mock_gen.return_value = {"temp-key": "smith-2025-abc123"}

            result = process_staging_entry(
                slug="test", bib_path=bib_file, json_path=json_file, existing_keys=existing_keys
            )

            assert result is not None
            new_key, entry_data, identifier_data = result
            assert new_key == "smith-2025-abc123"
            assert "smith-2025-abc123" in entry_data
            assert "smith-2025-abc123" in identifier_data


def test_process_staging_entry_duplicate_key():
    """Test handling of duplicate keys."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)

        bib_content = """@article{temp-key,
    title = {Test Article},
    author = {Smith, John},
    year = {2025}
}"""
        json_content = {"temp-key": {"identifiers": {"doi": "10.1000/test"}}}

        bib_file = workspace / "test.bib"
        json_file = workspace / "test.json"

        bib_file.write_text(bib_content, encoding="utf-8")
        json_file.write_text(json.dumps(json_content, indent=2), encoding="utf-8")

        # Mock existing data with duplicate key
        existing_keys = {"smith-2025-abc123"}

        with patch("biblib.add_entries.generate_labels") as mock_gen:
            mock_gen.return_value = {"temp-key": "smith-2025-abc123"}

            result = process_staging_entry(
                slug="test", bib_path=bib_file, json_path=json_file, existing_keys=existing_keys
            )

            assert result is None  # Should skip duplicate


def test_add_entries_from_staging_integration():
    """Test full integration workflow."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        staging = workspace / "staging"
        staging.mkdir()

        # Create data directories
        (workspace / "bib").mkdir()
        (workspace / "data").mkdir()

        # Create test staging files
        bib_content = """@article{temp-key,
    title = {Test Article},
    author = {Smith, John},
    year = {2025}
}"""
        json_content = {"temp-key": {"identifiers": {"doi": "10.1000/test"}}}

        (staging / "2025-01-15-test.bib").write_text(bib_content, encoding="utf-8")
        (staging / "2025-01-15-test.json").write_text(
            json.dumps(json_content, indent=2), encoding="utf-8"
        )

        # Create minimal existing data files
        (workspace / "bib" / "library.bib").write_text("", encoding="utf-8")
        (workspace / "data" / "add_order.json").write_text("[]", encoding="utf-8")
        (workspace / "data" / "identifier_collection.json").write_text("{}", encoding="utf-8")

        with (
            patch("biblib.add_entries.generate_labels") as mock_gen,
            patch("biblib.add_entries.load_existing_keys") as mock_load,
        ):
            mock_gen.return_value = {"temp-key": "smith-2025-abc123"}
            mock_load.return_value = set()

            # Mock the file operations since we're testing logic, not I/O
            with patch("biblib.add_entries.append_to_files") as mock_append:
                mock_append.return_value = True

                success, processed = add_entries_from_staging(workspace)

                assert success is True
                assert len(processed) == 1
                assert processed[0] == "2025-01-15-test"


def test_invalid_staging_files():
    """Test handling of invalid staging files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        staging = workspace / "staging"
        staging.mkdir()

        # Create invalid bib file
        (staging / "2025-01-15-invalid.bib").write_text("invalid bib content", encoding="utf-8")
        (staging / "2025-01-15-invalid.json").write_text("{}", encoding="utf-8")

        pairs = find_staging_pairs(staging)
        assert len(pairs) == 1  # Should find the pair

        # Processing should handle the invalid content gracefully
        with patch("biblib.add_entries.generate_labels") as mock_gen:
            mock_gen.side_effect = ValueError("Invalid bib format")

            result = process_staging_entry(
                slug="invalid",
                bib_path=staging / "2025-01-15-invalid.bib",
                json_path=staging / "2025-01-15-invalid.json",
                existing_keys=set(),
            )

            assert result is None  # Should return None on error
