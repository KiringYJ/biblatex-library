"""Tests for the label generation module."""

import json
import tempfile
from pathlib import Path

from biblib.generate import (
    create_hash,
    extract_lastname,
    extract_year,
    generate_labels,
    load_identifier_collection,
    parse_bib_entries,
)


def test_extract_lastname():
    """Test lastname extraction from various author formats."""
    # Standard "Lastname, Firstname" format
    assert extract_lastname("Bredon, Glen E.") == "bredon"

    # "Firstname Lastname" format
    assert extract_lastname("Glen E. Bredon") == "bredon"

    # Multiple authors - take first
    assert extract_lastname("Bredon, Glen E. and Smith, John") == "bredon"

    # Organizational author with braces
    assert extract_lastname("{The LMFDB Collaboration}", "LMFDB Collaboration") == "lmfdb"

    # Organizational author without sortname
    assert extract_lastname("{LMFDB Collaboration}") == "lmfdb"

    # Unicode normalization
    assert extract_lastname("Müller, Hans") == "muller"

    # Empty/invalid input
    assert extract_lastname("") == "unknown"
    assert extract_lastname("   ") == "unknown"


def test_extract_year():
    """Test year extraction from date/year fields."""
    # Standard year
    assert extract_year("1993") == "1993"

    # Date format
    assert extract_year("1993-05-15") == "1993"

    # Date range
    assert extract_year("1993/1994") == "1993"

    # Complex date with other text
    assert extract_year("circa 1993") == "1993"

    # 20xx year
    assert extract_year("2023") == "2023"

    # Invalid years
    assert extract_year("1800") == "unknown"  # Too old
    assert extract_year("3000") == "unknown"  # Too new
    assert extract_year("abc") == "unknown"  # No year
    assert extract_year("") == "unknown"  # Empty


def test_create_hash():
    """Test hash creation."""
    # Known DOI hash
    doi = "10.1007/978-1-4757-6848-0"
    expected_hash = "7908a921"
    assert create_hash(doi) == expected_hash

    # Hash should be 8 characters
    assert len(create_hash("test")) == 8

    # Same input should give same hash
    assert create_hash("test") == create_hash("test")

    # Different inputs should give different hashes
    assert create_hash("test1") != create_hash("test2")


def test_parse_bib_entries():
    """Test parsing bibtex entries."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".bib", delete=False) as f:
        f.write("""
@book{bredon-1993-test,
  author = {Bredon, Glen E.},
  title = {Test Title},
  year = {1993},
  sortname = {Bredon},
}

@article{smith-2020-test,
  author = {Smith, John},
  title = {Test Article},
  date = {2020-05-15},
}

@online{lmfdb-2016-test,
  author = {{The LMFDB Collaboration}},
  sortname = {{LMFDB Collaboration}},
  title = {Test Database},
  year = {2016},
}
""")
        bib_path = Path(f.name)

    try:
        entries = parse_bib_entries(bib_path)

        # Should have 3 entries
        assert len(entries) == 3

        # Check Bredon entry
        bredon = entries["bredon-1993-test"]
        assert bredon["author"] == "Bredon, Glen E."
        assert bredon["year"] == "1993"
        assert bredon["sortname"] == "Bredon"

        # Check Smith entry (date field)
        smith = entries["smith-2020-test"]
        assert smith["author"] == "Smith, John"
        assert smith["year"] == "2020-05-15"

        # Check LMFDB entry (organizational author)
        lmfdb = entries["lmfdb-2016-test"]
        assert lmfdb["author"] == "{The LMFDB Collaboration}"
        assert lmfdb["sortname"] == "{LMFDB Collaboration}"

    finally:
        bib_path.unlink()


def test_load_identifier_collection():
    """Test loading identifier collection."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(
            {
                "test-key-1": {"main_identifier": "doi", "identifiers": {"doi": "10.1000/test1"}},
                "test-key-2": {"main_identifier": "isbn", "identifiers": {"isbn": "1234567890"}},
            },
            f,
        )
        identifier_path = Path(f.name)

    try:
        collection = load_identifier_collection(identifier_path)

        assert len(collection) == 2
        assert "test-key-1" in collection
        assert collection["test-key-1"]["main_identifier"] == "doi"
        assert collection["test-key-1"]["identifiers"]["doi"] == "10.1000/test1"

    finally:
        identifier_path.unlink()


def test_generate_labels_integration():
    """Test full label generation integration."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create test .bib file
        bib_path = temp_path / "test.bib"
        bib_path.write_text("""
@book{original-key-1,
  author = {Bredon, Glen E.},
  title = {Test Book},
  year = {1993},
}

@article{original-key-2,
  author = {Smith, John},
  title = {Test Article},
  date = {2020},
}
""")

        # Create test identifier collection
        identifier_path = temp_path / "identifiers.json"
        identifier_path.write_text(
            json.dumps(
                {
                    "original-key-1": {
                        "main_identifier": "doi",
                        "identifiers": {"doi": "10.1007/978-1-4757-6848-0"},
                    },
                    "original-key-2": {
                        "main_identifier": "isbn",
                        "identifiers": {"isbn": "1234567890"},
                    },
                }
            )
        )

        # Generate labels
        labels = generate_labels(bib_path, identifier_path)

        # Should have 2 labels
        assert len(labels) == 2

        # Check label format
        bredon_label = labels["original-key-1"]
        assert bredon_label.startswith("bredon-1993-")
        assert len(bredon_label.split("-")) == 3  # lastname-year-hash

        smith_label = labels["original-key-2"]
        assert smith_label.startswith("smith-2020-")
        assert len(smith_label.split("-")) == 3


def test_generate_labels_fallbacks():
    """Test label generation with fallback scenarios."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create test .bib file with edge cases
        bib_path = temp_path / "test.bib"
        bib_path.write_text("""
@book{test-key-1,
  editor = {Editor, Main},
  title = {Test Book},
  year = {1993},
}

@article{test-key-2,
  author = {Unknown Author},
  title = {Test Article},
}
""")

        # Create identifier collection without entries
        identifier_path = temp_path / "identifiers.json"
        identifier_path.write_text("{}")

        # Generate labels
        labels = generate_labels(bib_path, identifier_path)

        # Should have 2 labels
        assert len(labels) == 2

        # First entry should use editor as fallback
        label1 = labels["test-key-1"]
        assert label1.startswith("editor-1993-")

        # Second entry should handle missing year and use entry key for hash
        label2 = labels["test-key-2"]
        assert label2.startswith("author-unknown-")
