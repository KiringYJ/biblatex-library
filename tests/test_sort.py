"""Tests for the sort module."""

import json
import tempfile
from collections.abc import Generator
from pathlib import Path

import msgspec
import pytest

from biblib.sort import sort_alphabetically, sort_by_add_order


@pytest.fixture
def temp_library_bib():
    """Create a temporary library.bib file with test entries."""
    content = """@book{zebra-2020-abc123,
  author = {Zebra, Alice},
  title = {Zebras and Their Stripes},
  year = {2020}
}

@book{alpha-2019-def456,
  author = {Alpha, Bob},
  title = {Alpha Particles},
  year = {2019}
}

@book{beta-2021-ghi789,
  author = {Beta, Charlie},
  title = {Beta Testing},
  year = {2021}
}
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".bib", delete=False, encoding="utf-8") as f:
        f.write(content)
        return Path(f.name)


@pytest.fixture
def temp_identifier_collection():
    """Create a temporary identifier_collection.json file."""
    data = {
        "zebra-2020-abc123": {
            "main_identifier": "isbn",
            "identifiers": {"isbn": "978-0-123456-78-9"},
        },
        "alpha-2019-def456": {"main_identifier": "doi", "identifiers": {"doi": "10.1234/alpha"}},
        "beta-2021-ghi789": {
            "main_identifier": "isbn",
            "identifiers": {"isbn": "978-0-987654-32-1"},
        },
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(data, f)
        return Path(f.name)


@pytest.fixture
def temp_add_order():
    """Create a temporary add_order.json file."""
    data = ["zebra-2020-abc123", "alpha-2019-def456", "beta-2021-ghi789"]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(data, f)
        return Path(f.name)


def test_sort_alphabetically(
    temp_library_bib: Path, temp_identifier_collection: Path, temp_add_order: Path
) -> None:
    """Test sorting files alphabetically by citekey."""
    # Sort alphabetically (add_order.json should remain unchanged)
    original_add_order = json.loads(open(temp_add_order, encoding="utf-8").read())

    sort_alphabetically(temp_library_bib, temp_identifier_collection, temp_add_order)

    # Check add_order.json is unchanged
    with open(temp_add_order, encoding="utf-8") as f:
        add_order = json.load(f)
    assert add_order == original_add_order  # Should be unchanged

    # Check identifier_collection.json is sorted alphabetically
    with open(temp_identifier_collection, encoding="utf-8") as f:
        identifier_data = json.load(f)
    expected_order = ["alpha-2019-def456", "beta-2021-ghi789", "zebra-2020-abc123"]
    assert list(identifier_data.keys()) == expected_order

    # Check library.bib entries are sorted alphabetically
    with open(temp_library_bib, encoding="utf-8") as f:
        content = f.read()

    # Verify the order by checking which entry appears first
    alpha_pos = content.find("@book{alpha-2019-def456")
    beta_pos = content.find("@book{beta-2021-ghi789")
    zebra_pos = content.find("@book{zebra-2020-abc123")

    assert alpha_pos < beta_pos < zebra_pos


def test_sort_by_add_order_sequence(
    temp_library_bib: Path, temp_identifier_collection: Path, temp_add_order: Path
) -> None:
    """Test sorting files to match add_order.json sequence."""
    # First, modify add_order to a different sequence
    custom_order = ["beta-2021-ghi789", "zebra-2020-abc123", "alpha-2019-def456"]
    with open(temp_add_order, "w", encoding="utf-8") as f:
        json.dump(custom_order, f)

    # Sort by add_order sequence (add_order.json should remain unchanged)
    sort_by_add_order(temp_library_bib, temp_identifier_collection, temp_add_order)

    # Check add_order.json is unchanged
    with open(temp_add_order, encoding="utf-8") as f:
        add_order = json.load(f)
    assert add_order == custom_order  # Should be unchanged

    # Check identifier_collection.json matches add_order
    with open(temp_identifier_collection, encoding="utf-8") as f:
        identifier_data = json.load(f)
    assert list(identifier_data.keys()) == custom_order

    # Check library.bib entries match the order
    with open(temp_library_bib, encoding="utf-8") as f:
        content = f.read()

    # Verify the order by checking positions
    beta_pos = content.find("@book{beta-2021-ghi789")
    zebra_pos = content.find("@book{zebra-2020-abc123")
    alpha_pos = content.find("@book{alpha-2019-def456")

    assert beta_pos < zebra_pos < alpha_pos


def test_sort_with_missing_citekey(
    temp_library_bib: Path, temp_identifier_collection: Path, temp_add_order: Path
) -> None:
    """Test sorting when a citekey is missing from one of the files."""
    # Remove one entry from add_order.json
    with open(temp_add_order, "w", encoding="utf-8") as f:
        json.dump(["zebra-2020-abc123", "alpha-2019-def456"], f)  # missing beta

    # Sort should handle this gracefully
    sort_by_add_order(temp_library_bib, temp_identifier_collection, temp_add_order)

    # The missing entry should be added at the end
    with open(temp_identifier_collection, encoding="utf-8") as f:
        identifier_data = json.load(f)

    keys = list(identifier_data.keys())
    # First two should match add_order, third should be the missing one
    assert keys[:2] == ["zebra-2020-abc123", "alpha-2019-def456"]
    assert "beta-2021-ghi789" in keys


def test_sort_with_invalid_add_order_format(
    temp_library_bib: Path, temp_identifier_collection: Path, temp_add_order: Path
) -> None:
    """Test that sort functions handle invalid add_order.json format."""
    # Write invalid JSON (dict instead of list)
    with open(temp_add_order, "w", encoding="utf-8") as f:
        json.dump({"invalid": "format"}, f)

    with pytest.raises(msgspec.ValidationError, match="Expected `array`"):
        sort_alphabetically(temp_library_bib, temp_identifier_collection, temp_add_order)


def test_sort_with_invalid_identifier_collection_format(
    temp_library_bib: Path, temp_identifier_collection: Path, temp_add_order: Path
) -> None:
    """Test that sort functions handle invalid identifier_collection.json format."""
    # Write invalid JSON (list instead of dict)
    with open(temp_identifier_collection, "w", encoding="utf-8") as f:
        json.dump(["invalid", "format"], f)

    with pytest.raises(msgspec.ValidationError, match="Expected `object`"):
        sort_by_add_order(temp_library_bib, temp_identifier_collection, temp_add_order)


# Cleanup fixtures
@pytest.fixture(autouse=True)
def cleanup_temp_files(
    temp_library_bib: Path, temp_identifier_collection: Path, temp_add_order: Path
) -> Generator[None, None, None]:
    """Clean up temporary files after each test."""
    yield
    for path in [temp_library_bib, temp_identifier_collection, temp_add_order]:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
