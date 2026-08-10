"""Read and prepare staged ``.bib`` entries without performing I/O writes."""

import hashlib
from collections.abc import Iterable, Sequence
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

import bibtexparser
from bibtexparser.model import Entry, Field

from .generate import citekey_stem
from .identifier_collection import identifiers_from_entry
from .identifiers import (
    CanonicalDoi,
    canonicalize_new_doi,
    hash_canonical_new_doi,
    hash_exact_legacy_identifier,
    is_derived_arxiv_doi,
)

MAIN_IDENTIFIER_PRIORITY = (
    "doi",
    "isbn13",
    "mrnumber",
    "arxiv",
    "zbmath",
    "zbl",
    "jfm",
    "oclc",
    "hdl",
    "acmdl_doi",
    "url",
)


def discover_staged_bib_files(staging_dir: Path) -> tuple[Path, ...]:
    """Return staged ``.bib`` files in deterministic filename order."""
    if not staging_dir.exists():
        return ()
    if not staging_dir.is_dir():
        raise ValueError(f"staging path is not a directory: {staging_dir}")
    return tuple(
        sorted(
            path
            for path in staging_dir.iterdir()
            if path.is_file() and path.suffix.lower() == ".bib"
        )
    )


def parse_staged_entries(paths: Iterable[Path]) -> tuple[Entry, ...]:
    """Parse staged files and retain their file and physical entry order."""
    return parse_staged_sources((path, path.read_bytes()) for path in paths)


def parse_staged_sources(sources: Iterable[tuple[Path, bytes]]) -> tuple[Entry, ...]:
    """Parse exact staged bytes and retain file and physical entry order."""
    entries: list[Entry] = []
    for path, data in sources:
        try:
            source = data.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError(f"staged bibliography is not valid UTF-8: {path}") from error
        library = bibtexparser.parse_string(source)
        if library.failed_blocks:
            raise ValueError(
                f"failed to parse {path}: {len(library.failed_blocks)} failed block(s)"
            )
        if not library.entries:
            raise ValueError(f"staged bibliography has no entries: {path}")
        entries.extend(deepcopy(library.entries))
    return tuple(entries)


def doi_fields(entry: Entry) -> tuple[Field, ...]:
    """Return DOI fields without interpreting their values."""
    return tuple(field for field in entry.fields if field.key.casefold() == "doi")


def replace_doi(entry: Entry, canonical_doi: CanonicalDoi) -> Entry:
    """Return a copy with its single DOI field set to canonical bare text."""
    replacement = deepcopy(entry)
    positions = [
        index for index, field in enumerate(replacement.fields) if field.key.casefold() == "doi"
    ]
    if len(positions) != 1:
        raise ValueError(f"entry '{entry.key}' must have exactly one DOI field")
    replacement.fields[positions[0]] = Field("doi", canonical_doi.value)
    return replacement


def _field_map(entry: Entry) -> dict[str, Field]:
    fields: dict[str, Field] = {}
    for field in entry.fields:
        name = field.key.casefold()
        if name in fields:
            raise ValueError(f"entry '{entry.key}' has duplicate '{name}' fields")
        fields[name] = field
    return fields


def select_main_identifier(identifiers: dict[str, str]) -> tuple[str, str]:
    """Select the exact identifier whose value determines the canonical key."""
    doi = identifiers.get("doi")
    arxiv = identifiers.get("arxiv")
    if doi is not None and arxiv is not None and is_derived_arxiv_doi(doi, arxiv):
        return "arxiv", arxiv
    for kind in MAIN_IDENTIFIER_PRIORITY:
        value = identifiers.get(kind)
        if value is None:
            continue
        return kind, value
    raise ValueError("entry has no supported identifier for deterministic citekey generation")


def _field_value(fields: dict[str, Field], name: str) -> str | None:
    field = fields.get(name)
    return str(field.value) if field is not None else None


def _citekey(entry: Entry, kind: str, identifier: str) -> str:
    fields = _field_map(entry)
    lastname, year = citekey_stem(
        shorthand=_field_value(fields, "shorthand"),
        author=_field_value(fields, "author"),
        editor=_field_value(fields, "editor"),
        sortname=_field_value(fields, "sortname"),
        date=_field_value(fields, "date"),
        year=_field_value(fields, "year"),
    )
    suffix = (
        hash_canonical_new_doi(CanonicalDoi(identifier))
        if kind == "doi"
        else hash_exact_legacy_identifier(identifier)
    )
    return f"{lastname}-{year}-{suffix}"


def prepare_entries(entries: Sequence[Entry]) -> tuple[Entry, ...]:
    """Assign deterministic canonical keys to already DOI-canonicalized entries."""
    prepared: list[Entry] = []
    for staged in entries:
        entry = deepcopy(staged)
        _field_map(entry)
        kind, identifier = select_main_identifier(identifiers_from_entry(entry))
        entry.key = _citekey(entry, kind, identifier)
        prepared.append(entry)
    return tuple(prepared)


@dataclass(frozen=True, slots=True)
class PreparedStagedFile:
    """Prepared entries and exact source evidence for one staged file."""

    path: Path
    sha256: str
    entries: tuple[Entry, ...]

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(entry.key for entry in self.entries)


@dataclass(frozen=True, slots=True)
class PreparedStaging:
    """One deterministic staged batch with per-file provenance."""

    files: tuple[PreparedStagedFile, ...]
    stripped_doi_query_keys: tuple[str, ...] = ()
    stripped_doi_fragment_keys: tuple[str, ...] = ()

    @property
    def entries(self) -> tuple[Entry, ...]:
        return tuple(entry for file in self.files for entry in file.entries)


def prepare_staged_sources(sources: Iterable[tuple[Path, bytes]]) -> PreparedStaging:
    """Canonicalize and key exact source bytes using the add-domain pipeline."""
    files: list[PreparedStagedFile] = []
    query_keys: list[str] = []
    fragment_keys: list[str] = []
    for path, data in sources:
        canonicalized: list[Entry] = []
        query_indexes: list[int] = []
        fragment_indexes: list[int] = []
        for entry in parse_staged_sources(((path, data),)):
            fields = doi_fields(entry)
            if len(fields) > 1:
                raise ValueError(f"entry '{entry.key}' has multiple DOI fields")
            if not fields:
                canonicalized.append(deepcopy(entry))
                continue
            canonical = canonicalize_new_doi(str(fields[0].value))
            if canonical.had_query:
                query_indexes.append(len(canonicalized))
            if canonical.had_fragment:
                fragment_indexes.append(len(canonicalized))
            canonicalized.append(replace_doi(entry, canonical))
        prepared = prepare_entries(canonicalized)
        query_keys.extend(prepared[index].key for index in query_indexes)
        fragment_keys.extend(prepared[index].key for index in fragment_indexes)
        files.append(PreparedStagedFile(path, hashlib.sha256(data).hexdigest(), prepared))
    return PreparedStaging(tuple(files), tuple(query_keys), tuple(fragment_keys))
