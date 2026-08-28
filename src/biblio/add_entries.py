"""Read and prepare staged ``.bib`` entries without performing I/O writes."""

import hashlib
from collections.abc import Iterable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, replace
from dataclasses import field as dataclass_field
from pathlib import Path

import bibtexparser
from bibtexparser.model import Entry, Field

from .bibliography import Bibliography, IdentityIndex
from .generate import citekey_stem
from .identifier_collection import (
    SUPPORTED_IDENTIFIER_KIND_SET,
    IdentifierRecord,
    identifier_equality_token,
    identifiers_from_entry,
    parse_identifier_collection,
    serialize_identifier_collection,
)
from .identifiers import (
    CanonicalDoi,
    canonicalize_new_doi,
    hash_canonical_new_doi,
    hash_exact_legacy_identifier,
    is_derived_arxiv_doi,
    legacy_doi_comparison_token,
)
from .normalize.inventory import normalize_identifier_inventory
from .normalize.pipeline import ALL, merge_changes, normalize_bibliography
from .results import ChangeSet, NormalizeResult

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


def prepare_entries(
    entries: Sequence[Entry],
    identifier_records: Mapping[str, IdentifierRecord] | None = None,
) -> tuple[Entry, ...]:
    """Assign deterministic canonical keys to already DOI-canonicalized entries."""
    prepared: list[Entry] = []
    for staged in entries:
        entry = deepcopy(staged)
        _field_map(entry)
        if identifier_records is None:
            kind, identifier = select_main_identifier(identifiers_from_entry(entry))
        else:
            record = identifier_records.get(staged.key)
            if record is None:
                raise ValueError(f"entry '{staged.key}' has no identifier selection")
            kind = record.main_identifier
            identifier = record.identifiers[kind]
        entry.key = _citekey(entry, kind, identifier)
        prepared.append(entry)
    return tuple(prepared)


@dataclass(frozen=True, slots=True)
class PreparedStagedFile:
    """Prepared entries and exact source evidence for one staged file."""

    path: Path
    sha256: str
    entries: tuple[Entry, ...]
    identifier_records: tuple[IdentifierRecord, ...]
    template_path: Path | None = None
    template_sha256: str | None = None

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(entry.key for entry in self.entries)


@dataclass(frozen=True, slots=True)
class PreparedStaging:
    """One deterministic staged batch with per-file provenance."""

    files: tuple[PreparedStagedFile, ...]
    stripped_doi_query_keys: tuple[str, ...] = ()
    stripped_doi_fragment_keys: tuple[str, ...] = ()
    normalization_actions: tuple[str, ...] = ()
    normalization_changes: ChangeSet = dataclass_field(default_factory=ChangeSet)
    normalization_diagnostics: tuple[str, ...] = ()

    @property
    def entries(self) -> tuple[Entry, ...]:
        return tuple(entry for file in self.files for entry in file.entries)

    @property
    def identifier_records(self) -> tuple[tuple[str, IdentifierRecord], ...]:
        return tuple(
            (entry.key, record)
            for file in self.files
            for entry, record in zip(file.entries, file.identifier_records, strict=True)
        )


@dataclass(frozen=True, slots=True)
class PreparedIdentifierTemplate:
    """Editable per-entry identifier selections derived from one staged source."""

    data: bytes
    normalization_diagnostics: tuple[str, ...]


def _canonicalized_normalized_entries(
    path: Path, data: bytes
) -> tuple[tuple[Entry, ...], tuple[int, ...], tuple[int, ...], NormalizeResult]:
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

    bibliography = Bibliography(canonicalized, IdentityIndex(canonicalized))
    normalization = normalize_bibliography(bibliography, ALL)
    return (
        tuple(bibliography),
        tuple(query_indexes),
        tuple(fragment_indexes),
        normalization,
    )


def _automatic_identifier_records(
    entries: Sequence[Entry], normalization: NormalizeResult
) -> dict[str, IdentifierRecord]:
    arxiv_preferred = {
        delta.canonical_key
        for delta in normalization.changes.field_deltas
        if delta.field == "doi" and delta.before is not None and delta.after is None
    }
    records: dict[str, IdentifierRecord] = {}
    for entry in entries:
        identifiers = identifiers_from_entry(entry)
        if entry.key in arxiv_preferred and "arxiv" in identifiers:
            main = "arxiv"
        else:
            main, _value = select_main_identifier(identifiers)
        records[entry.key] = IdentifierRecord(main, identifiers)
    return records


def _validate_template_record(entry: Entry, record: IdentifierRecord) -> None:
    if record.key_history:
        raise ValueError(f"staging template entry '{entry.key}' must not contain key_history")
    kinds = {
        *record.identifiers,
        *record.identifier_alternates,
        record.main_identifier,
    }
    unknown = kinds - SUPPORTED_IDENTIFIER_KIND_SET
    if unknown:
        raise ValueError(
            f"staging template entry '{entry.key}' has unsupported identifier kinds: "
            f"{sorted(unknown)}"
        )
    main_value = record.identifiers.get(record.main_identifier)
    if main_value is None or not main_value:
        raise ValueError(
            f"staging template entry '{entry.key}' main_identifier "
            f"'{record.main_identifier}' is absent or empty"
        )
    if record.main_identifier == "doi" and legacy_doi_comparison_token(main_value) != main_value:
        raise ValueError(
            f"staging template entry '{entry.key}' main DOI must use canonical bare text"
        )
    for kind in kinds:
        for value in record.inventory_values(kind):
            if not value or not identifier_equality_token(kind, value):
                raise ValueError(
                    f"staging template entry '{entry.key}' identifier '{kind}' is empty"
                )

    projected = identifiers_from_entry(entry)
    for kind, value in projected.items():
        token = identifier_equality_token(kind, value)
        if not any(
            identifier_equality_token(kind, candidate) == token
            for candidate in record.inventory_values(kind)
        ):
            raise ValueError(
                f"staging template entry '{entry.key}' omits bibliography identifier "
                f"'{kind}' value '{value}'"
            )


def _identifier_records(
    entries: Sequence[Entry], template_data: bytes | None, normalization: NormalizeResult
) -> dict[str, IdentifierRecord]:
    if template_data is None:
        return _automatic_identifier_records(entries, normalization)
    records = parse_identifier_collection(template_data)
    entry_keys = tuple(entry.key for entry in entries)
    if set(records) != set(entry_keys):
        raise ValueError(
            "staging template keys must exactly match bibliography entry keys: "
            f"template={sorted(records)}, bibliography={sorted(entry_keys)}"
        )
    for entry in entries:
        _validate_template_record(entry, records[entry.key])
    return records


def _rekey_normalization_changes(
    normalization: NormalizeResult,
    normalized: Sequence[Entry],
    prepared: Sequence[Entry],
) -> ChangeSet:
    final_keys = {
        source.key: target.key for source, target in zip(normalized, prepared, strict=True)
    }
    return ChangeSet(
        changed_keys=tuple(
            dict.fromkeys(final_keys[key] for key in normalization.changes.changed_keys)
        ),
        field_deltas=tuple(
            replace(delta, canonical_key=final_keys[delta.canonical_key])
            for delta in normalization.changes.field_deltas
        ),
        alias_deltas=tuple(
            replace(delta, canonical_key=final_keys[delta.canonical_key])
            for delta in normalization.changes.alias_deltas
        ),
    )


def prepare_identifier_template(path: Path, data: bytes) -> PreparedIdentifierTemplate:
    """Derive an editable identifier-selection template from one staged bibliography."""
    normalized, _query_indexes, _fragment_indexes, normalization = (
        _canonicalized_normalized_entries(path, data)
    )
    records = _automatic_identifier_records(normalized, normalization)
    return PreparedIdentifierTemplate(
        serialize_identifier_collection(records),
        normalization.diagnostics,
    )


def prepare_staged_sources(
    sources: Iterable[tuple[Path, bytes]],
    templates: Mapping[Path, tuple[Path, bytes]] | None = None,
) -> PreparedStaging:
    """Normalize, canonicalize, and key exact source bytes for one add transaction."""
    files: list[PreparedStagedFile] = []
    query_keys: list[str] = []
    fragment_keys: list[str] = []
    normalization_actions: tuple[str, ...] = ()
    normalized_keys: list[str] = []
    normalization_field_deltas = []
    normalization_alias_deltas = []
    normalization_diagnostics: list[str] = []
    for path, data in sources:
        normalized, query_indexes, fragment_indexes, normalization = (
            _canonicalized_normalized_entries(path, data)
        )
        template = templates.get(path) if templates is not None else None
        records_by_key = _identifier_records(
            normalized, template[1] if template is not None else None, normalization
        )
        inventory = normalize_identifier_inventory(
            Bibliography(normalized, IdentityIndex(normalized)),
            records_by_key,
            remove_urls=True,
            remove_arxiv_dois=True,
        )
        normalization = replace(
            normalization,
            changes=merge_changes([normalization.changes, inventory.changes]),
            diagnostics=(*normalization.diagnostics, *inventory.diagnostics),
        )
        prepared = prepare_entries(normalized, records_by_key)
        records = tuple(records_by_key[entry.key] for entry in normalized)
        actions = normalization.actions
        changes = _rekey_normalization_changes(normalization, normalized, prepared)
        diagnostics = normalization.diagnostics
        if not normalization_actions:
            normalization_actions = actions
        elif normalization_actions != actions:  # pragma: no cover - one fixed default pipeline
            raise ValueError("staged files used different normalization action sets")
        for key in changes.changed_keys:
            if key not in normalized_keys:
                normalized_keys.append(key)
        normalization_field_deltas.extend(changes.field_deltas)
        normalization_alias_deltas.extend(changes.alias_deltas)
        normalization_diagnostics.extend(diagnostics)
        query_keys.extend(prepared[index].key for index in query_indexes)
        fragment_keys.extend(prepared[index].key for index in fragment_indexes)
        files.append(
            PreparedStagedFile(
                path,
                hashlib.sha256(data).hexdigest(),
                prepared,
                records,
                template_path=template[0] if template is not None else None,
                template_sha256=(
                    hashlib.sha256(template[1]).hexdigest() if template is not None else None
                ),
            )
        )
    return PreparedStaging(
        files=tuple(files),
        stripped_doi_query_keys=tuple(query_keys),
        stripped_doi_fragment_keys=tuple(fragment_keys),
        normalization_actions=normalization_actions,
        normalization_changes=ChangeSet(
            changed_keys=tuple(normalized_keys),
            field_deltas=tuple(normalization_field_deltas),
            alias_deltas=tuple(normalization_alias_deltas),
        ),
        normalization_diagnostics=tuple(normalization_diagnostics),
    )
