"""Tests for the validation module."""

import json
import tempfile
from pathlib import Path

from biblib.validate import (
    extract_citekeys_from_add_order,
    extract_citekeys_from_bib,
    extract_citekeys_from_identifier_collection,
    validate_citekey_consistency,
    validate_citekey_labels,
)


def test_extract_citekeys_from_bib():
    """Test extracting citekeys from a .bib file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".bib", delete=False) as f:
        f.write("""
@article{key1,
  title = {Test Title 1},
  author = {Test Author},
}

@book{key2,
  title = {Test Title 2},
  author = {Test Author},
}
""")
        bib_path = Path(f.name)

    try:
        citekeys = extract_citekeys_from_bib(bib_path)
        assert citekeys == {"key1", "key2"}
    finally:
        bib_path.unlink()


def test_extract_citekeys_from_add_order():
    """Test extracting citekeys from add_order.json."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(["key1", "key2", "key3"], f)
        order_path = Path(f.name)

    try:
        citekeys = extract_citekeys_from_add_order(order_path)
        assert citekeys == {"key1", "key2", "key3"}
    finally:
        order_path.unlink()


def test_extract_citekeys_from_identifier_collection():
    """Test extracting citekeys from identifier_collection.json."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(
            {
                "key1": {"identifiers": {"doi": "10.1000/test1"}},
                "key2": {"identifiers": {"isbn": "1234567890"}},
            },
            f,
        )
        identifier_path = Path(f.name)

    try:
        citekeys = extract_citekeys_from_identifier_collection(identifier_path)
        assert citekeys == {"key1", "key2"}
    finally:
        identifier_path.unlink()


def test_validate_citekey_consistency_success():
    """Test successful validation when all sources have same citekeys."""
    # Create temporary files
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create .bib file
        bib_path = temp_path / "library.bib"
        bib_path.write_text("""
@article{key1,
  title = {Test Title 1},
}

@book{key2,
  title = {Test Title 2},
}
""")

        # Create add_order.json
        order_path = temp_path / "add_order.json"
        order_path.write_text(json.dumps(["key1", "key2"]))

        # Create identifier_collection.json
        identifier_path = temp_path / "identifier_collection.json"
        identifier_path.write_text(
            json.dumps(
                {
                    "key1": {"identifiers": {"doi": "10.1000/test1"}},
                    "key2": {"identifiers": {"isbn": "1234567890"}},
                }
            )
        )

        # Test validation
        result = validate_citekey_consistency(bib_path, order_path, identifier_path)
        assert result is True


def test_validate_citekey_consistency_failure():
    """Test validation failure when sources have different citekeys."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create .bib file with keys 1,2
        bib_path = temp_path / "library.bib"
        bib_path.write_text("""
@article{key1,
  title = {Test Title 1},
}

@book{key2,
  title = {Test Title 2},
}
""")

        # Create add_order.json with keys 1,3 (missing key2, extra key3)
        order_path = temp_path / "add_order.json"
        order_path.write_text(json.dumps(["key1", "key3"]))

        # Create identifier_collection.json with keys 1,2
        identifier_path = temp_path / "identifier_collection.json"
        identifier_path.write_text(
            json.dumps(
                {
                    "key1": {"identifiers": {"doi": "10.1000/test1"}},
                    "key2": {"identifiers": {"isbn": "1234567890"}},
                }
            )
        )

        # Test validation - should fail
        result = validate_citekey_consistency(bib_path, order_path, identifier_path)
        assert result is False


def test_validate_citekey_labels_matching():
    """Test citekey label validation when keys match generated labels."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create .bib file with entries that will generate matching citekeys
        bib_path = temp_path / "library.bib"
        bib_path.write_text("""
@book{bredon-1993-7908a921,
  author = {Bredon, Glen E.},
  title = {Test Book},
  year = {1993},
}

@article{smith-2020-bca2b41a,
  author = {Smith, John},
  title = {Test Article},
  year = {2020},
}
""")

        # Create identifier collection
        identifier_path = temp_path / "identifier_collection.json"
        identifier_path.write_text(
            json.dumps(
                {
                    "bredon-1993-7908a921": {
                        "main_identifier": "doi",
                        "identifiers": {"doi": "10.1007/978-1-4757-6848-0"},
                    },
                    "smith-2020-bca2b41a": {
                        "main_identifier": "isbn",
                        "identifiers": {"isbn": "1234567890123"},
                    },
                }
            )
        )

        # Test validation - should pass
        result = validate_citekey_labels(bib_path, identifier_path)
        assert result is True


def test_validate_citekey_labels_mismatched():
    """Test citekey label validation when keys don't match generated labels."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create .bib file with entries that have wrong citekeys
        bib_path = temp_path / "library.bib"
        bib_path.write_text("""
@book{wrong-key-1,
  author = {Bredon, Glen E.},
  title = {Test Book},
  year = {1993},
}

@article{bad-key-2,
  author = {Smith, John},
  title = {Test Article},
  year = {2020},
}
""")

        # Create identifier collection
        identifier_path = temp_path / "identifier_collection.json"
        identifier_path.write_text(
            json.dumps(
                {
                    "wrong-key-1": {
                        "main_identifier": "doi",
                        "identifiers": {"doi": "10.1007/978-1-4757-6848-0"},
                    },
                    "bad-key-2": {
                        "main_identifier": "isbn",
                        "identifiers": {"isbn": "1234567890123"},
                    },
                }
            )
        )

        # Test validation - should fail
        result = validate_citekey_labels(bib_path, identifier_path)
        assert result is False
