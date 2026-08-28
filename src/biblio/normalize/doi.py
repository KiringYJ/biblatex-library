"""Remove only DOI fields derived from the entry's explicit arXiv eprint."""

from biblio.bibliography import Bibliography
from biblio.identifiers import is_derived_arxiv_doi, legacy_doi_comparison_token
from biblio.results import ChangeSet, FieldDelta

from .eprint import explicit_arxiv_eprint


def matches_arxiv_doi(doi: str, eprint: str) -> bool:
    """Recognize a matching derived DOI without discarding extra or opaque content."""
    if (
        any(
            not value
            or not value.isascii()
            or any(
                character.isspace()
                or ord(character) < 32
                or ord(character) == 127
                or character in "?#\\{}"
                for character in value
            )
            for value in (doi, eprint)
        )
        or "%" in eprint
    ):
        return False
    try:
        canonical = legacy_doi_comparison_token(doi)
    except ValueError:
        return False
    return canonical.isascii() and is_derived_arxiv_doi(canonical, eprint)


def normalize_arxiv_dois(bibliography: Bibliography) -> ChangeSet:
    """Remove matching derived DOIs, retaining eprints, entry types, and exact keys."""
    changed_keys: list[str] = []
    deltas: list[FieldDelta] = []
    for entry in bibliography:
        eprint = explicit_arxiv_eprint(entry)
        doi = next((field for field in entry.fields if field.key.casefold() == "doi"), None)
        if eprint is None or doi is None or not matches_arxiv_doi(str(doi.value), eprint):
            continue
        entry.fields.remove(doi)
        changed_keys.append(entry.key)
        deltas.append(FieldDelta(entry.key, "doi", str(doi.value), None))
    return ChangeSet(tuple(changed_keys), tuple(deltas))
