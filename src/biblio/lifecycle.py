"""Pure record-removal and publication-promotion transformations."""

from collections.abc import Sequence
from copy import deepcopy

from bibtexparser.model import Entry, Field

from .bibliography import Bibliography
from .generate import citekey_stem
from .identifier_collection import (
    IdentifierRecord,
    KeyHistory,
    identifier_equality_token,
    identifiers_from_entry,
)
from .identifiers import (
    CanonicalDoi,
    hash_canonical_new_doi,
    is_derived_arxiv_doi,
    legacy_doi_comparison_token,
)
from .results import (
    AddResult,
    AliasDelta,
    ChangeSet,
    FieldDelta,
    OrderDelta,
    PromoteResult,
    RemoveResult,
)
from .workspace import WorkspaceAggregate

_ARXIV_FIELDS = frozenset({"eprint", "eprinttype", "eprintclass"})


def add(bibliography: Bibliography, entries: Sequence[Entry]) -> AddResult:
    """Append a fully validated batch without partially mutating on collision."""
    if not entries:
        return AddResult(added_keys=())

    order_before = bibliography.identity_index.canonical_keys
    candidate_entries = [*bibliography, *entries]
    # Construct the complete namespace before the first append, so a late
    # collision cannot leave a partially changed aggregate.
    from .bibliography import IdentityIndex

    IdentityIndex(candidate_entries)
    for entry in entries:
        bibliography.append(entry)
    bibliography.validate()
    order_after = bibliography.identity_index.canonical_keys
    added_keys = tuple(entry.key for entry in entries)
    return AddResult(
        added_keys=added_keys,
        changes=ChangeSet(
            changed_keys=added_keys,
            order_delta=OrderDelta(before=order_before, after=order_after),
        ),
    )


def _fields_by_name(fields: Sequence[Field], *, owner: str) -> dict[str, Field]:
    indexed: dict[str, Field] = {}
    for field in fields:
        name = field.key.casefold()
        if name in indexed:
            raise ValueError(f"{owner} has duplicate '{name}' fields")
        indexed[name] = field
    return indexed


def _clone_field(field: Field) -> Field:
    return Field(field.key, field.value)


def _merge_fields(current: Entry, published: Entry, canonical_doi: str) -> list[Field]:
    _fields_by_name(current.fields, owner=f"entry '{current.key}'")
    published_by_name = _fields_by_name(published.fields, owner="published payload")

    if "ids" in published_by_name:
        raise ValueError("published payload must not supply ids aliases")
    payload_doi = published_by_name.get("doi")
    if payload_doi is not None and str(payload_doi.value) != canonical_doi:
        raise ValueError("published payload DOI must equal the command-supplied canonical DOI")

    merged = [_clone_field(field) for field in current.fields if field.key.casefold() != "ids"]
    positions = {field.key.casefold(): index for index, field in enumerate(merged)}
    for field in published.fields:
        name = field.key.casefold()
        if name == "ids":
            continue
        replacement = _clone_field(field)
        if name in positions:
            merged[positions[name]] = replacement
        else:
            positions[name] = len(merged)
            merged.append(replacement)

    doi_field = Field("doi", canonical_doi)
    if "doi" in positions:
        merged[positions["doi"]] = doi_field
    else:
        positions["doi"] = len(merged)
        merged.append(doi_field)

    merged_by_name = _fields_by_name(merged, owner="promoted entry")
    if any(name in published_by_name for name in _ARXIV_FIELDS):
        eprint = merged_by_name.get("eprint")
        eprinttype = merged_by_name.get("eprinttype")
        if eprint is None or not str(eprint.value).strip():
            raise ValueError("published arXiv metadata update requires a nonempty eprint")
        if eprinttype is None or str(eprinttype.value).strip().casefold() != "arxiv":
            raise ValueError("published arXiv metadata update requires eprinttype=arxiv")

    return merged


def _entry_arxiv_eprint(entry: Entry) -> str:
    fields = _fields_by_name(entry.fields, owner=f"entry '{entry.key}'")
    eprint = fields.get("eprint")
    eprinttype = fields.get("eprinttype")
    if eprint is None or not str(eprint.value).strip():
        raise ValueError(f"entry '{entry.key}' is not an arXiv record with a nonempty eprint")
    if eprinttype is None or str(eprinttype.value).strip().casefold() != "arxiv":
        raise ValueError(f"entry '{entry.key}' is not an arXiv record with eprinttype=arxiv")
    return str(eprint.value)


def _field_value(fields: dict[str, Field], name: str) -> str | None:
    field = fields.get(name)
    return str(field.value) if field is not None else None


def _canonical_doi_collides(
    bibliography: Bibliography, current: Entry, canonical_doi: str
) -> str | None:
    for entry in bibliography:
        if entry is current:
            continue
        doi_fields = [field for field in entry.fields if field.key.casefold() == "doi"]
        if len(doi_fields) > 1:
            raise ValueError(f"entry '{entry.key}' has duplicate 'doi' fields")
        if doi_fields and legacy_doi_comparison_token(str(doi_fields[0].value)) == canonical_doi:
            return entry.key
    return None


def _field_deltas(current: Entry, replacement: Entry) -> tuple[FieldDelta, ...]:
    before = _fields_by_name(current.fields, owner=f"entry '{current.key}'")
    after = _fields_by_name(replacement.fields, owner=f"entry '{replacement.key}'")
    deltas: list[FieldDelta] = []
    for name in dict.fromkeys([*(field.key.casefold() for field in current.fields), *after]):
        before_value = str(before[name].value) if name in before else None
        after_value = str(after[name].value) if name in after else None
        if before_value != after_value:
            deltas.append(FieldDelta(replacement.key, name, before_value, after_value))
    return tuple(deltas)


def remove(bibliography: Bibliography, identity: str) -> RemoveResult:
    """Remove the canonical record resolved by *identity*, including all aliases."""
    current = bibliography.resolve(identity)
    aliases = bibliography.aliases_for(current.key)
    order_before = bibliography.identity_index.canonical_keys
    bibliography.delete(current.key)
    order_after = bibliography.identity_index.canonical_keys
    return RemoveResult(
        canonical_key=current.key,
        aliases=aliases,
        changes=ChangeSet(
            changed_keys=(current.key,),
            alias_deltas=(AliasDelta(current.key, removed=aliases),) if aliases else (),
            order_delta=OrderDelta(before=order_before, after=order_after),
        ),
    )


def promote(
    bibliography: Bibliography,
    identity: str,
    published: Entry,
    canonical_doi: str,
    *,
    stripped_doi_query: bool = False,
    stripped_doi_fragment: bool = False,
) -> PromoteResult:
    """Promote one arXiv record using one validated published-entry payload."""
    current = bibliography.resolve(identity)
    source_eprint = _entry_arxiv_eprint(current)
    if is_derived_arxiv_doi(canonical_doi, source_eprint):
        raise ValueError("promotion requires a publisher DOI, not the matching derived arXiv DOI")

    collision = _canonical_doi_collides(bibliography, current, canonical_doi)
    if collision is not None:
        raise ValueError(f"canonical DOI '{canonical_doi}' already belongs to '{collision}'")

    merged_fields = _merge_fields(current, published, canonical_doi)
    merged_by_name = _fields_by_name(merged_fields, owner="promoted entry")
    effective_eprint = merged_by_name["eprint"]
    if is_derived_arxiv_doi(canonical_doi, str(effective_eprint.value)):
        raise ValueError("promotion requires a publisher DOI, not the matching derived arXiv DOI")
    aliases = tuple(dict.fromkeys((current.key, *bibliography.aliases_for(current.key))))
    merged_fields.append(Field("ids", ", ".join(aliases)))

    lastname, year = citekey_stem(
        shorthand=_field_value(merged_by_name, "shorthand"),
        author=_field_value(merged_by_name, "author"),
        editor=_field_value(merged_by_name, "editor"),
        sortname=_field_value(merged_by_name, "sortname"),
        date=_field_value(merged_by_name, "date"),
        year=_field_value(merged_by_name, "year"),
    )
    doi_hash = hash_canonical_new_doi(CanonicalDoi(canonical_doi))
    new_key = f"{lastname}-{year}-{doi_hash}"
    replacement = deepcopy(current)
    replacement.entry_type = published.entry_type
    replacement.key = new_key
    replacement.fields = merged_fields

    order_before = bibliography.identity_index.canonical_keys
    bibliography.replace(current.key, replacement)
    order_after = bibliography.identity_index.canonical_keys
    return PromoteResult(
        old_key=current.key,
        new_key=new_key,
        aliases=aliases,
        canonical_doi=canonical_doi,
        stripped_doi_query=stripped_doi_query,
        stripped_doi_fragment=stripped_doi_fragment,
        changes=ChangeSet(
            changed_keys=(current.key, new_key),
            field_deltas=_field_deltas(current, replacement),
            alias_deltas=(AliasDelta(new_key, added=aliases),),
            order_delta=OrderDelta(before=order_before, after=order_after),
        ),
    )


def _commit_workspace_candidate(
    aggregate: WorkspaceAggregate, candidate: WorkspaceAggregate
) -> None:
    candidate.validate()
    aggregate.bibliography = candidate.bibliography
    aggregate.identifiers = candidate.identifiers
    aggregate.add_order = candidate.add_order


def remove_from_workspace(aggregate: WorkspaceAggregate, identity: str) -> RemoveResult:
    """Hard-delete one resolved record from all three in-memory artifacts."""
    aggregate.validate()
    candidate = deepcopy(aggregate)
    canonical_key = candidate.bibliography.resolve(identity).key
    result = remove(candidate.bibliography, identity)
    del candidate.identifiers[canonical_key]
    candidate.add_order = tuple(key for key in candidate.add_order if key != canonical_key)
    _commit_workspace_candidate(aggregate, candidate)
    return result


def _add_inventory_value(record: IdentifierRecord, kind: str, value: str) -> None:
    token = identifier_equality_token(kind, value)
    for current in record.inventory_values(kind):
        if identifier_equality_token(kind, current) == token:
            return

    if kind not in record.identifiers:
        record.identifiers[kind] = value
        return
    record.identifier_alternates[kind] = (
        *record.identifier_alternates.get(kind, ()),
        value,
    )


def _set_publisher_doi(record: IdentifierRecord, canonical_doi: str) -> None:
    canonical_token = identifier_equality_token("doi", canonical_doi)
    retained: list[str] = []
    for value in record.inventory_values("doi"):
        if identifier_equality_token("doi", value) == canonical_token:
            continue
        retained.append(value)

    record.identifiers["doi"] = canonical_doi
    if retained:
        record.identifier_alternates["doi"] = tuple(retained)
    else:
        record.identifier_alternates.pop("doi", None)
    record.main_identifier = "doi"


def _materialized_history(
    canonical_key: str,
    aliases: tuple[str, ...],
    record: IdentifierRecord,
) -> dict[str, KeyHistory]:
    if record.key_history:
        return {item.key: item for item in record.key_history}
    if aliases:
        raise ValueError(f"record '{canonical_key}' aliases require existing key_history")
    identifier = record.identifiers.get(record.main_identifier)
    if identifier is None:
        raise ValueError(
            f"record '{canonical_key}' main identifier '{record.main_identifier}' is absent"
        )
    return {canonical_key: KeyHistory(canonical_key, record.main_identifier, identifier)}


def _rekey_record(
    aggregate: WorkspaceAggregate,
    old_key: str,
    result: PromoteResult,
    canonical_doi: str,
) -> None:
    record = aggregate.identifiers[old_key]
    prior_aliases = aggregate.bibliography.aliases_for(result.new_key)
    history = _materialized_history(old_key, prior_aliases[1:], record)

    _set_publisher_doi(record, canonical_doi)
    projected = identifiers_from_entry(aggregate.bibliography.resolve(result.new_key))
    for kind, value in projected.items():
        _add_inventory_value(record, kind, value)

    try:
        alias_history = tuple(history[alias] for alias in result.aliases)
    except KeyError as error:
        raise ValueError(
            f"record '{old_key}' lacks key_history for alias '{error.args[0]}'"
        ) from error
    record.key_history = (
        *alias_history,
        KeyHistory(result.new_key, "doi", canonical_doi),
    )

    aggregate.identifiers = {
        result.new_key if key == old_key else key: record if key == old_key else current
        for key, current in aggregate.identifiers.items()
    }
    aggregate.add_order = tuple(
        result.new_key if key == old_key else key for key in aggregate.add_order
    )


def promote_in_workspace(
    aggregate: WorkspaceAggregate,
    identity: str,
    published: Entry,
    canonical_doi: str,
    *,
    stripped_doi_query: bool = False,
    stripped_doi_fragment: bool = False,
) -> PromoteResult:
    """Promote one resolved record across all three in-memory artifacts."""
    aggregate.validate()
    candidate = deepcopy(aggregate)
    old_key = candidate.bibliography.resolve(identity).key
    result = promote(
        candidate.bibliography,
        identity,
        published,
        canonical_doi,
        stripped_doi_query=stripped_doi_query,
        stripped_doi_fragment=stripped_doi_fragment,
    )
    _rekey_record(candidate, old_key, result, canonical_doi)
    _commit_workspace_candidate(aggregate, candidate)
    return result
