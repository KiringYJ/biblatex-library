"""Tests for ISBN field normalization."""

from __future__ import annotations

import bibtexparser
import pytest

from biblio.bibliography import Bibliography, IdentityIndex
from biblio.normalize.isbn import (
    calculate_isbn13_check_digit,
    convert_isbn10_to_isbn13,
    extract_isbn_digits,
    is_valid_isbn10,
    is_valid_isbn13,
    normalize_isbn_field,
    normalize_isbn_fields,
)


def _bibliography(source: str) -> Bibliography:
    library = bibtexparser.parse_string(source)
    return Bibliography(library.blocks, IdentityIndex(library.entries))


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

    def test_convert_with_hyphens_returns_contiguous_digits(self) -> None:
        result = convert_isbn10_to_isbn13("0-387-97926-3")
        assert result is not None
        assert result == "9780387979267"
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
        assert normalized == "9780387979267"

    def test_single_isbn13_unchanged(self) -> None:
        normalized, conversions = normalize_isbn_field("978-0-8218-5193-7")
        assert len(conversions) == 0
        assert normalized == "978-0-8218-5193-7"

    def test_multiple_isbns_mixed(self) -> None:
        # One ISBN-10, one ISBN-13
        normalized, conversions = normalize_isbn_field("0-8218-1045-6, 978-0-8218-1045-3")
        assert len(conversions) == 1  # Only the ISBN-10 should be converted
        # Since both resolve to the same ISBN-13, result should be deduplicated
        assert normalized == "9780821810453"

    def test_deduplication_isbn10_matches_existing_isbn13(self) -> None:
        # ISBN-10 converts to same value as the existing ISBN-13
        normalized, conversions = normalize_isbn_field("0-8218-1045-6, 978-0-8218-1045-3")
        assert "deduplicated" in conversions[0] or "9780821810453" in conversions[0]
        # Only one ISBN in the result
        assert "," not in normalized

    def test_empty_string(self) -> None:
        normalized, conversions = normalize_isbn_field("")
        assert normalized == ""
        assert len(conversions) == 0


class TestNormalizeIsbnFields:
    """Tests for the pure aggregate transformation."""

    def test_converts_deduplicates_and_classifies_values(self) -> None:
        bibliography = _bibliography(
            "@book{converted, isbn={0-387-97926-3}}\n"
            "@book{existing, isbn={978-0-8218-5193-7}}\n"
            "@book{invalid, isbn={not-an-isbn}}\n"
            "@article{missing, title={No ISBN}}\n"
        )

        report = normalize_isbn_fields(bibliography)

        assert report.total_converted == 1
        assert tuple(report.converted) == ("converted",)
        assert report.already_isbn13 == ("existing",)
        assert report.invalid == {"invalid": "not-an-isbn"}
        assert bibliography.resolve("converted").fields_dict["isbn"].value == "9780387979267"
        assert report.changes.changed_keys == ("converted",)

    def test_reports_noop_for_canonical_values(self) -> None:
        bibliography = _bibliography("@book{existing, isbn={978-0-8218-5193-7}}\n")

        report = normalize_isbn_fields(bibliography)

        assert report.changes.changed is False


@pytest.mark.parametrize(
    "value",
    [
        "ISBN 0-387-97926-3",
        "0-387-97926-3 (hardback)",
        "0-387-97926-3, invalid",
        "0-387-97926-3,",
        ",0-387-97926-3",
        "0-387-97926-3, 9780387979268",
        "0--387-97926-3",
        "０３８７９７９２６３",
        "4006381333931",
        "",
        "  ",
    ],
)
def test_invalid_or_annotated_field_is_preserved_whole(value: str) -> None:
    assert normalize_isbn_field(value) == (value, [])
    bibliography = _bibliography(f"@book{{one,ISBN={{{value}}}}}")
    report = normalize_isbn_fields(bibliography)
    assert report.invalid == {"one": value}
    assert not report.changes.changed
    assert bibliography.resolve("one").fields_dict["ISBN"].value == value


def test_multiple_valid_isbn13_values_are_not_invalid() -> None:
    value = "9780387979267, 9780821851937"
    report = normalize_isbn_fields(_bibliography(f"@book{{one,isbn={{{value}}}}}"))
    assert report.already_isbn13 == ("one",)
    assert not report.invalid
    assert not report.changes.changed


def test_conversion_does_not_reconstruct_registration_groups() -> None:
    assert convert_isbn10_to_isbn13("0 387 97926 3") == "9780387979267"
    assert convert_isbn10_to_isbn13("ISBN 0-387-97926-3") is None
    assert convert_isbn10_to_isbn13("0--387-97926-3") is None


def test_delta_retains_exact_original_spacing() -> None:
    original = " 0-387-97926-3 "
    bibliography = _bibliography(f"@book{{one,isbn={{{original}}}}}")
    report = normalize_isbn_fields(bibliography)
    assert report.changes.field_deltas[0].before == original
    assert report.changes.field_deltas[0].after == "9780387979267"


def test_valid_isbn13_duplicates_are_reported_as_a_change() -> None:
    bibliography = _bibliography("@book{one,isbn={9780387979267, 978-0-387-97926-7}}")
    report = normalize_isbn_fields(bibliography)
    assert report.changes.changed_keys == ("one",)
    assert report.converted["one"][0].startswith("deduplicated:")
    assert not report.invalid
    assert bibliography.resolve("one").fields_dict["isbn"].value == "9780387979267"
