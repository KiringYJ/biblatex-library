"""Tests for ISBN field normalization."""

from __future__ import annotations

from pathlib import Path

import bibtexparser

from biblio.normalize.isbn import (
    calculate_isbn13_check_digit,
    convert_isbn10_to_isbn13,
    extract_isbn_digits,
    is_valid_isbn10,
    is_valid_isbn13,
    normalize_isbn_field,
    normalize_isbn_fields,
)


def _write_bib(tmp_path: Path, content: str) -> Path:
    bib_path = tmp_path / "library.bib"
    bib_path.write_text(content, encoding="utf-8")
    return bib_path


class TestExtractIsbnDigits:
    """Tests for _extract_isbn_digits helper."""

    def test_digits_only(self) -> None:
        assert extract_isbn_digits("0387979263") == "0387979263"

    def test_with_hyphens(self) -> None:
        assert extract_isbn_digits("0-387-97926-3") == "0387979263"

    def test_with_spaces(self) -> None:
        assert extract_isbn_digits("0 387 97926 3") == "0387979263"

    def test_with_x_check_digit(self) -> None:
        assert extract_isbn_digits("0-387-97430-X") == "038797430X"

    def test_lowercase_x(self) -> None:
        assert extract_isbn_digits("0-387-97430-x") == "038797430X"

    def test_isbn13(self) -> None:
        assert extract_isbn_digits("978-0-8218-5193-7") == "9780821851937"


class TestIsbnValidation:
    """Tests for ISBN validation functions."""

    def test_valid_isbn10(self) -> None:
        # Known valid ISBN-10s
        assert is_valid_isbn10("0387979263") is True
        assert is_valid_isbn10("0387961623") is True
        assert is_valid_isbn10("038797430X") is True  # X check digit

    def test_invalid_isbn10_wrong_length(self) -> None:
        assert is_valid_isbn10("123456789") is False
        assert is_valid_isbn10("12345678901") is False

    def test_invalid_isbn10_wrong_checksum(self) -> None:
        assert is_valid_isbn10("0387979264") is False

    def test_valid_isbn13(self) -> None:
        # Known valid ISBN-13s
        assert is_valid_isbn13("9780821851937") is True
        assert is_valid_isbn13("9780387944265") is True

    def test_invalid_isbn13_wrong_length(self) -> None:
        assert is_valid_isbn13("978082185193") is False
        assert is_valid_isbn13("97808218519377") is False

    def test_invalid_isbn13_wrong_checksum(self) -> None:
        assert is_valid_isbn13("9780821851938") is False


class TestIsbn13CheckDigit:
    """Tests for ISBN-13 check digit calculation."""

    def test_check_digit_calculation(self) -> None:
        # 978-0-8218-5193-7: check digit is 7
        assert calculate_isbn13_check_digit("978082185193") == "7"

        # 978-0-387-94426-5: check digit is 5
        assert calculate_isbn13_check_digit("978038794426") == "5"


class TestConvertIsbn10ToIsbn13:
    """Tests for ISBN-10 to ISBN-13 conversion."""

    def test_convert_without_hyphens(self) -> None:
        result = convert_isbn10_to_isbn13("0387979263")
        assert result is not None
        # Should have 13 digits
        digits = extract_isbn_digits(result)
        assert len(digits) == 13
        assert is_valid_isbn13(digits)

    def test_convert_with_hyphens_preserves_structure(self) -> None:
        result = convert_isbn10_to_isbn13("0-387-97926-3")
        assert result is not None
        assert result.startswith("978-")
        digits = extract_isbn_digits(result)
        assert len(digits) == 13
        assert is_valid_isbn13(digits)

    def test_convert_with_x_check_digit(self) -> None:
        result = convert_isbn10_to_isbn13("0-387-97430-X")
        assert result is not None
        digits = extract_isbn_digits(result)
        assert len(digits) == 13
        assert is_valid_isbn13(digits)

    def test_invalid_isbn10_returns_none(self) -> None:
        result = convert_isbn10_to_isbn13("1234567890")
        assert result is None


class TestNormalizeIsbnField:
    """Tests for normalize_isbn_field function."""

    def test_single_isbn10(self) -> None:
        normalized, conversions = normalize_isbn_field("0-387-97926-3")
        assert len(conversions) == 1
        assert "978-" in normalized

    def test_single_isbn13_unchanged(self) -> None:
        normalized, conversions = normalize_isbn_field("978-0-8218-5193-7")
        assert len(conversions) == 0
        assert normalized == "978-0-8218-5193-7"

    def test_multiple_isbns_mixed(self) -> None:
        # One ISBN-10, one ISBN-13
        normalized, conversions = normalize_isbn_field("0-8218-1045-6, 978-0-8218-1045-3")
        assert len(conversions) == 1  # Only the ISBN-10 should be converted
        # Since both resolve to the same ISBN-13, result should be deduplicated
        assert normalized.count("978-0-8218-1045-3") == 1

    def test_deduplication_isbn10_matches_existing_isbn13(self) -> None:
        # ISBN-10 converts to same value as the existing ISBN-13
        normalized, conversions = normalize_isbn_field("0-8218-1045-6, 978-0-8218-1045-3")
        assert "deduplicated" in conversions[0] or "978-0-8218-1045-3" in conversions[0]
        # Only one ISBN in the result
        assert "," not in normalized

    def test_empty_string(self) -> None:
        normalized, conversions = normalize_isbn_field("")
        assert normalized == ""
        assert len(conversions) == 0


class TestNormalizeIsbnFields:
    """Tests for normalize_isbn_fields function."""

    def test_converts_isbn10_to_isbn13(self, tmp_path: Path) -> None:
        bib_content = """@book{test-entry,
  title = {Test Book},
  isbn = {0-387-97926-3}
}
"""
        bib_path = _write_bib(tmp_path, bib_content)

        report = normalize_isbn_fields(bib_path)

        assert "test-entry" in report.converted
        assert report.total_converted == 1

        # Verify the file was updated
        library = bibtexparser.parse_file(str(bib_path))
        entry = library.entries[0]
        isbn_value = str(entry.fields_dict["isbn"].value)
        assert "978-" in isbn_value

    def test_preserves_isbn13(self, tmp_path: Path) -> None:
        bib_content = """@book{test-entry,
  title = {Test Book},
  isbn = {978-0-8218-5193-7}
}
"""
        bib_path = _write_bib(tmp_path, bib_content)

        report = normalize_isbn_fields(bib_path)

        assert "test-entry" in report.already_isbn13
        assert report.total_converted == 0

    def test_dry_run_does_not_modify_file(self, tmp_path: Path) -> None:
        bib_content = """@book{test-entry,
  title = {Test Book},
  isbn = {0-387-97926-3}
}
"""
        bib_path = _write_bib(tmp_path, bib_content)
        original_content = bib_path.read_text()

        report = normalize_isbn_fields(bib_path, dry_run=True)

        assert report.total_converted == 1
        assert bib_path.read_text() == original_content

    def test_multiple_entries(self, tmp_path: Path) -> None:
        bib_content = """@book{entry-one,
  title = {Book One},
  isbn = {0-387-97926-3}
}

@book{entry-two,
  title = {Book Two},
  isbn = {978-0-8218-5193-7}
}

@book{entry-three,
  title = {Book Three},
  isbn = {0-387-96162-3}
}
"""
        bib_path = _write_bib(tmp_path, bib_content)

        report = normalize_isbn_fields(bib_path)

        assert len(report.converted) == 2
        assert "entry-one" in report.converted
        assert "entry-three" in report.converted
        assert "entry-two" in report.already_isbn13

    def test_entry_without_isbn(self, tmp_path: Path) -> None:
        bib_content = """@article{test-entry,
  title = {Test Article},
  journal = {Test Journal}
}
"""
        bib_path = _write_bib(tmp_path, bib_content)

        report = normalize_isbn_fields(bib_path)

        assert report.total_converted == 0
        assert len(report.already_isbn13) == 0

    def test_file_not_found(self, tmp_path: Path) -> None:
        import pytest

        nonexistent = tmp_path / "nonexistent.bib"

        with pytest.raises(FileNotFoundError):
            normalize_isbn_fields(nonexistent)


class TestNormalizeIdentifierCollectionIsbns:
    """Tests for ISBN normalization in identifier_collection.json."""

    def _write_identifier(self, tmp_path: Path, data: dict[str, object]) -> Path:
        path = tmp_path / "identifier_collection.json"
        import json

        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return path

    def test_converts_isbn10_in_identifier_collection(self, tmp_path: Path) -> None:
        import json

        bib_content = """@book{test-entry,
  title = {Test Book},
  isbn = {9780821851937}
}
"""
        bib_path = _write_bib(tmp_path, bib_content)
        identifier_data = {
            "test-entry": {
                "main_identifier": "isbn13",
                "identifiers": {"isbn13": "9810202334"},
            }
        }
        id_path = self._write_identifier(tmp_path, identifier_data)

        report = normalize_isbn_fields(bib_path, id_path)

        assert "test-entry" in report.identifier_converted

        # Verify the file was updated
        with open(id_path, encoding="utf-8") as f:
            updated = json.load(f)
        new_isbn = updated["test-entry"]["identifiers"]["isbn13"]
        assert len(new_isbn) == 13
        assert new_isbn.isdigit()

    def test_preserves_valid_isbn13_in_identifier_collection(self, tmp_path: Path) -> None:
        bib_content = """@book{test-entry,
  title = {Test Book},
  isbn = {9780821851937}
}
"""
        bib_path = _write_bib(tmp_path, bib_content)
        identifier_data = {
            "test-entry": {
                "main_identifier": "isbn13",
                "identifiers": {"isbn13": "9780821851937"},
            }
        }
        id_path = self._write_identifier(tmp_path, identifier_data)

        report = normalize_isbn_fields(bib_path, id_path)

        assert len(report.identifier_converted) == 0

    def test_dry_run_does_not_modify_identifier_collection(self, tmp_path: Path) -> None:
        bib_content = """@book{test-entry,
  title = {Test Book},
  isbn = {9780821851937}
}
"""
        bib_path = _write_bib(tmp_path, bib_content)
        identifier_data = {
            "test-entry": {
                "main_identifier": "isbn13",
                "identifiers": {"isbn13": "9810202334"},
            }
        }
        id_path = self._write_identifier(tmp_path, identifier_data)
        original = id_path.read_text(encoding="utf-8")

        report = normalize_isbn_fields(bib_path, id_path, dry_run=True)

        assert "test-entry" in report.identifier_converted
        assert id_path.read_text(encoding="utf-8") == original

    def test_no_identifier_path(self, tmp_path: Path) -> None:
        """When identifier_path is None, only bib file is processed."""
        bib_content = """@book{test-entry,
  title = {Test Book},
  isbn = {9780821851937}
}
"""
        bib_path = _write_bib(tmp_path, bib_content)

        report = normalize_isbn_fields(bib_path, None)

        assert len(report.identifier_converted) == 0
