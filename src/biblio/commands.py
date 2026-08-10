"""Thin application services for coordinated bibliography workspaces."""

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from bibtexparser.model import Entry

from . import lifecycle
from .add_entries import (
    discover_staged_bib_files,
    doi_fields,
    parse_staged_entries,
    prepare_staged_sources,
    replace_doi,
    select_main_identifier,
)
from .identifier_collection import (
    IdentifierRecord,
    identifiers_from_entry,
    parse_add_order,
    parse_identifier_collection,
    serialize_add_order,
    serialize_identifier_collection,
)
from .identifiers import canonicalize_new_doi
from .normalize.pipeline import normalize_bibliography
from .reconcile import reconcile_identifier_inventory
from .results import (
    AddResult,
    CommitOutcome,
    NormalizeResult,
    PromoteResult,
    ReconcileResult,
    RecoverResult,
    RemoveResult,
    ValidateResult,
)
from .storage import (
    BibliographyCodec,
    LockBackend,
    StorageError,
    WorkspaceCandidate,
    WorkspaceDigestVector,
    WorkspacePaths,
    WorkspaceRecoveryState,
    WorkspaceSnapshot,
    WorkspaceTransaction,
    inspect_workspace_recovery,
    read_workspace_snapshot,
    recover_workspace,
    verify_workspace_resolution,
)
from .validate import validate_bibliography
from .workspace import WorkspaceAggregate

FaultHook = Callable[[str], None]
_RECEIPT_NAME = ".biblio-add-cleanup.json"
_GENERATED_KEY = re.compile(r"^[a-z]+-(?:[0-9]{4}|unknown)-[0-9a-f]{8}$")


def _noop_fault_hook(_phase: str) -> None:
    return None


def _aggregate(snapshot: WorkspaceSnapshot) -> WorkspaceAggregate:
    return WorkspaceAggregate(
        BibliographyCodec.parse_bytes(snapshot.bibliography.data),
        parse_identifier_collection(snapshot.identifiers.data),
        parse_add_order(snapshot.add_order.data),
    )


def _issues(aggregate: WorkspaceAggregate) -> tuple[str, ...]:
    bibliography = validate_bibliography(aggregate.bibliography)
    return (*bibliography.issues, *aggregate.validation_issues())


def _require_valid(aggregate: WorkspaceAggregate) -> None:
    issues = _issues(aggregate)
    if issues:
        raise ValueError("; ".join(dict.fromkeys(issues)))


def _candidate(
    aggregate: WorkspaceAggregate,
    *,
    bibliography: bytes | None = None,
    identifiers: bytes | None = None,
    add_order: bytes | None = None,
) -> WorkspaceCandidate:
    return WorkspaceCandidate(
        bibliography
        if bibliography is not None
        else BibliographyCodec.serialize(aggregate.bibliography),
        identifiers
        if identifiers is not None
        else serialize_identifier_collection(aggregate.identifiers),
        add_order if add_order is not None else serialize_add_order(aggregate.add_order),
    )


def validate(paths: WorkspacePaths) -> ValidateResult:
    """Validate one stable, side-effect-free read of all workspace artifacts."""
    issues: list[str] = []
    try:
        snapshot = read_workspace_snapshot(paths)
        issues.extend(_issues(_aggregate(snapshot)))
    except (StorageError, ValueError, OSError) as error:
        issues.append(str(error))
    recovery = inspect_workspace_recovery(paths)
    if recovery.state is not WorkspaceRecoveryState.CLEAN:
        issues.append(f"workspace recovery state is {recovery.state.value}")
        issues.extend(recovery.diagnostics)
    return ValidateResult(valid=not issues, issues=tuple(dict.fromkeys(issues)))


def _selected_staging(staging: Path) -> tuple[Path, Path | None]:
    if staging.is_dir():
        return staging.resolve(), None
    if staging.suffix.casefold() != ".bib":
        raise ValueError(f"explicit staging file must have a .bib suffix: {staging}")
    return staging.parent.resolve(), staging.resolve()


def _normalized_path(path: Path) -> str:
    return os.path.normcase(str(path.resolve()))


def _is_protected(path: Path, protected: tuple[Path, ...]) -> bool:
    for target in protected:
        if _normalized_path(path) == _normalized_path(target):
            return True
        try:
            if path.exists() and target.exists() and os.path.samefile(path, target):
                return True
        except OSError:
            continue
    return False


def _staging_paths(
    directory: Path, explicit: Path | None, protected: tuple[Path, ...]
) -> tuple[Path, ...]:
    if explicit is not None:
        if not explicit.is_file():
            raise ValueError(f"staging path is not a regular file: {explicit}")
        result = (explicit,)
    else:
        if not directory.is_dir():
            raise ValueError(f"staging path is not a directory: {directory}")
        result = discover_staged_bib_files(directory)
    for path in result:
        if _is_protected(path, protected):
            raise ValueError(f"staging input is a protected workspace artifact: {path}")
        if _normalized_path(path) == _normalized_path(_receipt_path(directory)):
            raise ValueError(f"staging input is the cleanup receipt: {path}")
    return result


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True, slots=True)
class _ReceiptItem:
    name: str
    sha256: str
    keys: tuple[str, ...]
    entries: tuple["_EntryManifest", ...]


@dataclass(frozen=True, slots=True)
class _EntryManifest:
    key: str
    entry_type: str
    fields: tuple[tuple[str, str], ...]
    main_identifier: str
    identifiers: tuple[tuple[str, str], ...]
    identifier_alternates: tuple[tuple[str, tuple[str, ...]], ...] = ()
    key_history: tuple[tuple[str, str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class _CleanupReceipt:
    transaction_id: str
    added_keys: tuple[str, ...]
    original_sha256: WorkspaceDigestVector
    candidate_sha256: WorkspaceDigestVector
    files: tuple[_ReceiptItem, ...]
    pending_files: tuple[str, ...]


def _receipt_path(directory: Path) -> Path:
    return directory / _RECEIPT_NAME


def _entry_manifest(entry: Entry, record: IdentifierRecord) -> _EntryManifest:
    return _EntryManifest(
        entry.key,
        entry.entry_type,
        tuple((field.key, str(field.value)) for field in entry.fields),
        record.main_identifier,
        tuple(record.identifiers.items()),
        tuple((kind, values) for kind, values in record.identifier_alternates.items()),
        tuple((item.key, item.main_identifier, item.identifier) for item in record.key_history),
    )


def _added_entry_manifest(entry: Entry) -> _EntryManifest:
    inventory = identifiers_from_entry(entry)
    main, _value = select_main_identifier(inventory)
    return _entry_manifest(entry, IdentifierRecord(main, inventory))


def _snapshot_vector(snapshot: WorkspaceSnapshot) -> WorkspaceDigestVector:
    return WorkspaceDigestVector(
        snapshot.bibliography.sha256,
        snapshot.identifiers.sha256,
        snapshot.add_order.sha256,
    )


def _candidate_vector(candidate: WorkspaceCandidate) -> WorkspaceDigestVector:
    return WorkspaceDigestVector(
        _digest(candidate.bibliography),
        _digest(candidate.identifiers),
        _digest(candidate.add_order),
    )


def _string_object(raw: object, description: str) -> dict[str, object]:
    if not isinstance(raw, dict):
        raise ValueError(f"staging cleanup receipt {description} is invalid")
    result: dict[str, object] = {}
    for key, value in raw.items():
        if not isinstance(key, str):
            raise ValueError(f"staging cleanup receipt {description} has a non-string key")
        result[key] = value
    return result


def _parse_vector(raw: object, description: str) -> WorkspaceDigestVector:
    vector = _string_object(raw, f"{description} vector")
    if set(vector) != {
        "bibliography",
        "identifiers",
        "add_order",
    }:
        raise ValueError(f"staging cleanup receipt {description} vector is invalid")
    bibliography = vector["bibliography"]
    identifiers = vector["identifiers"]
    add_order = vector["add_order"]
    values = (bibliography, identifiers, add_order)
    if any(
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
        for value in values
    ):
        raise ValueError(f"staging cleanup receipt {description} digest is invalid")
    assert isinstance(bibliography, str)
    assert isinstance(identifiers, str)
    assert isinstance(add_order, str)
    return WorkspaceDigestVector(bibliography, identifiers, add_order)


def _parse_receipt(directory: Path, protected: tuple[Path, ...] = ()) -> _CleanupReceipt | None:
    receipt = _receipt_path(directory)
    if not receipt.exists():
        return None
    try:
        raw = json.loads(receipt.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid staging cleanup receipt: {error}") from error
    expected = {
        "version",
        "transaction_id",
        "added_keys",
        "original_sha256",
        "candidate_sha256",
        "files",
        "pending_files",
    }
    if not isinstance(raw, dict) or set(raw) != expected:
        raise ValueError("staging cleanup receipt has an invalid top-level shape")
    if (
        raw["version"] != 2
        or not isinstance(raw["transaction_id"], str)
        or not isinstance(raw["added_keys"], list)
        or not isinstance(raw["files"], list)
        or not isinstance(raw["pending_files"], list)
    ):
        raise ValueError("unsupported staging cleanup receipt")
    added_keys = tuple(raw["added_keys"])
    transaction_id = raw["transaction_id"]
    if len(transaction_id) != 32 or any(
        character not in "0123456789abcdef" for character in transaction_id
    ):
        raise ValueError("staging cleanup receipt transaction_id is invalid")
    if any(
        not isinstance(key, str) or _GENERATED_KEY.fullmatch(key) is None for key in added_keys
    ) or len(set(added_keys)) != len(added_keys):
        raise ValueError("staging cleanup receipt added_keys are invalid")
    items: list[_ReceiptItem] = []
    names: set[str] = set()
    for item in raw["files"]:
        if not isinstance(item, dict) or set(item) != {"name", "sha256", "keys", "entries"}:
            raise ValueError("staging cleanup receipt file item is invalid")
        name = item["name"]
        digest = item["sha256"]
        raw_keys = item["keys"]
        keys = tuple(raw_keys) if isinstance(raw_keys, list) else ()
        raw_entries = item["entries"]
        normalized_name = os.path.normcase(name) if isinstance(name, str) else ""
        if (
            not isinstance(name, str)
            or Path(name).name != name
            or name == _RECEIPT_NAME
            or Path(name).suffix.casefold() != ".bib"
            or normalized_name in names
            or not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
            or not isinstance(raw_keys, list)
            or not keys
            or any(
                not isinstance(key, str) or _GENERATED_KEY.fullmatch(key) is None for key in keys
            )
            or len(set(keys)) != len(keys)
            or not isinstance(raw_entries, list)
        ):
            raise ValueError("staging cleanup receipt contains a hostile or invalid file item")
        candidate = directory / name
        if candidate.resolve().parent != directory.resolve():
            raise ValueError("staging cleanup receipt path escapes its staging directory")
        if _is_protected(candidate, protected):
            raise ValueError("staging cleanup receipt references a protected workspace artifact")
        entries = tuple(_parse_entry_manifest(value) for value in raw_entries)
        if tuple(entry.key for entry in entries) != keys:
            raise ValueError("staging cleanup receipt entry manifests differ from file keys")
        items.append(_ReceiptItem(name, digest, keys, entries))
        names.add(normalized_name)
    if tuple(key for item in items for key in item.keys) != added_keys:
        raise ValueError("staging cleanup receipt file keys differ from added_keys")
    pending_files = tuple(raw["pending_files"])
    file_names = tuple(item.name for item in items)
    if (
        any(not isinstance(name, str) for name in pending_files)
        or len(set(pending_files)) != len(pending_files)
        or any(name not in file_names for name in pending_files)
    ):
        raise ValueError("staging cleanup receipt pending_files are invalid")
    original = _parse_vector(raw["original_sha256"], "original")
    candidate = _parse_vector(raw["candidate_sha256"], "candidate")
    if original == candidate:
        raise ValueError("staging cleanup receipt vectors must differ")
    return _CleanupReceipt(
        transaction_id,
        added_keys,
        original,
        candidate,
        tuple(items),
        pending_files,
    )


def _fsync_directory(directory: Path) -> None:
    if os.name != "posix":
        return
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _durable_replace(path: Path, data: bytes) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        if temporary.exists():
            temporary.unlink()


def _vector_json(vector: WorkspaceDigestVector) -> dict[str, str]:
    return {
        "bibliography": vector.bibliography,
        "identifiers": vector.identifiers,
        "add_order": vector.add_order,
    }


def _manifest_json(manifest: _EntryManifest) -> dict[str, object]:
    return {
        "key": manifest.key,
        "entry_type": manifest.entry_type,
        "fields": [list(field) for field in manifest.fields],
        "main_identifier": manifest.main_identifier,
        "identifiers": [list(item) for item in manifest.identifiers],
        "identifier_alternates": [
            [kind, list(values)] for kind, values in manifest.identifier_alternates
        ],
        "key_history": [list(item) for item in manifest.key_history],
    }


def _string_pairs(raw: object, description: str) -> tuple[tuple[str, str], ...]:
    if not isinstance(raw, list):
        raise ValueError(f"staging cleanup receipt {description} must be an array")
    pairs: list[tuple[str, str]] = []
    for value in raw:
        if (
            not isinstance(value, list)
            or len(value) != 2
            or not isinstance(value[0], str)
            or not isinstance(value[1], str)
        ):
            raise ValueError(f"staging cleanup receipt {description} item is invalid")
        pairs.append((value[0], value[1]))
    return tuple(pairs)


def _parse_entry_manifest(raw: object) -> _EntryManifest:
    value = _string_object(raw, "entry manifest")
    expected = {
        "key",
        "entry_type",
        "fields",
        "main_identifier",
        "identifiers",
        "identifier_alternates",
        "key_history",
    }
    if set(value) != expected:
        raise ValueError("staging cleanup receipt entry manifest shape is invalid")
    key = value["key"]
    entry_type = value["entry_type"]
    main_identifier = value["main_identifier"]
    if (
        not isinstance(key, str)
        or _GENERATED_KEY.fullmatch(key) is None
        or not isinstance(entry_type, str)
        or not entry_type
        or not isinstance(main_identifier, str)
        or not main_identifier
    ):
        raise ValueError("staging cleanup receipt entry manifest identity is invalid")
    raw_alternates = value["identifier_alternates"]
    if not isinstance(raw_alternates, list):
        raise ValueError("staging cleanup receipt identifier alternates are invalid")
    alternates: list[tuple[str, tuple[str, ...]]] = []
    for item in raw_alternates:
        if (
            not isinstance(item, list)
            or len(item) != 2
            or not isinstance(item[0], str)
            or not isinstance(item[1], list)
            or any(not isinstance(candidate, str) for candidate in item[1])
        ):
            raise ValueError("staging cleanup receipt identifier alternate is invalid")
        kind = item[0]
        candidates = item[1]
        assert isinstance(kind, str)
        assert isinstance(candidates, list)
        exact_candidates: list[str] = []
        for candidate in candidates:
            assert isinstance(candidate, str)
            exact_candidates.append(candidate)
        alternates.append((kind, tuple(exact_candidates)))
    raw_history = value["key_history"]
    if not isinstance(raw_history, list):
        raise ValueError("staging cleanup receipt key history is invalid")
    history: list[tuple[str, str, str]] = []
    for item in raw_history:
        if (
            not isinstance(item, list)
            or len(item) != 3
            or any(not isinstance(candidate, str) for candidate in item)
        ):
            raise ValueError("staging cleanup receipt key history item is invalid")
        history_key, history_kind, history_identifier = item
        assert isinstance(history_key, str)
        assert isinstance(history_kind, str)
        assert isinstance(history_identifier, str)
        history.append((history_key, history_kind, history_identifier))
    return _EntryManifest(
        key,
        entry_type,
        _string_pairs(value["fields"], "entry fields"),
        main_identifier,
        _string_pairs(value["identifiers"], "entry identifiers"),
        tuple(alternates),
        tuple(history),
    )


def _receipt_payload(receipt: _CleanupReceipt, *, include_pending: bool) -> dict[str, object]:
    payload = {
        "version": 2,
        "transaction_id": receipt.transaction_id,
        "added_keys": list(receipt.added_keys),
        "original_sha256": _vector_json(receipt.original_sha256),
        "candidate_sha256": _vector_json(receipt.candidate_sha256),
        "files": [
            {
                "name": item.name,
                "sha256": item.sha256,
                "keys": list(item.keys),
                "entries": [_manifest_json(entry) for entry in item.entries],
            }
            for item in receipt.files
        ],
    }
    if include_pending:
        payload["pending_files"] = list(receipt.pending_files)
    return payload


def _receipt_bytes(receipt: _CleanupReceipt) -> bytes:
    payload = _receipt_payload(receipt, include_pending=True)
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _receipt_evidence_sha256(receipt: _CleanupReceipt) -> str:
    payload = _receipt_payload(receipt, include_pending=False)
    evidence = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    return _digest(evidence)


def _write_receipt(directory: Path, receipt: _CleanupReceipt) -> None:
    _durable_replace(_receipt_path(directory), _receipt_bytes(receipt))
    if _parse_receipt(directory) != receipt:
        raise OSError("staging cleanup receipt verification failed")


def _clear_receipt(directory: Path) -> None:
    receipt = _receipt_path(directory)
    if receipt.exists():
        receipt.unlink()
        _fsync_directory(directory)


@dataclass(frozen=True, slots=True)
class _ReceiptResolution:
    proceed: bool
    added_keys: tuple[str, ...] = ()
    input_paths: tuple[Path, ...] = ()
    consumed_paths: tuple[Path, ...] = ()
    retained_paths: tuple[Path, ...] = ()
    conflicted_paths: tuple[Path, ...] = ()
    diagnostics: tuple[str, ...] = ()


def _prove_receipt_item(
    path: Path,
    item: _ReceiptItem,
    aggregate: WorkspaceAggregate,
) -> str | None:
    committed = tuple(
        _entry_manifest(
            aggregate.bibliography.resolve(manifest.key),
            aggregate.identifiers[manifest.key],
        )
        for manifest in item.entries
    )
    if committed != item.entries:
        return f"committed entry content differs from staging receipt: {path}"
    try:
        data = path.read_bytes()
        prepared = prepare_staged_sources(((path, data),))
        source_manifests = tuple(_added_entry_manifest(entry) for entry in prepared.entries)
    except (OSError, ValueError) as error:
        return f"could not prove staging file '{path}': {error}"
    if (
        _digest(data) != item.sha256
        or prepared.files[0].keys != item.keys
        or source_manifests != item.entries
    ):
        return f"staging source digest, keys, or content changed: {path}"
    return None


def _resolve_receipt(
    directory: Path,
    protected: tuple[Path, ...],
    snapshot: WorkspaceSnapshot,
    paths: WorkspacePaths,
) -> _ReceiptResolution:
    receipt_record = _parse_receipt(directory, protected)
    if receipt_record is None:
        return _ReceiptResolution(proceed=True)
    pending_names = set(receipt_record.pending_files)
    pending_items = tuple(item for item in receipt_record.files if item.name in pending_names)
    input_paths = tuple(directory / item.name for item in pending_items)
    current = _snapshot_vector(snapshot)
    if current == receipt_record.original_sha256:
        try:
            _clear_receipt(directory)
        except OSError as error:
            return _ReceiptResolution(
                False,
                receipt_record.added_keys,
                input_paths,
                retained_paths=input_paths,
                conflicted_paths=(_receipt_path(directory),),
                diagnostics=(f"could not retire uncommitted staging receipt: {error}",),
            )
        return _ReceiptResolution(proceed=True)
    if current != receipt_record.candidate_sha256:
        return _ReceiptResolution(
            False,
            receipt_record.added_keys,
            input_paths,
            retained_paths=input_paths,
            conflicted_paths=(_receipt_path(directory),),
            diagnostics=("staging cleanup receipt does not match the workspace vector",),
        )
    try:
        verify_workspace_resolution(
            paths,
            transaction_id=receipt_record.transaction_id,
            operation="add",
            original=receipt_record.original_sha256,
            candidate=receipt_record.candidate_sha256,
            operation_evidence_sha256=_receipt_evidence_sha256(receipt_record),
        )
    except (OSError, StorageError, ValueError) as error:
        return _ReceiptResolution(
            False,
            receipt_record.added_keys,
            input_paths,
            retained_paths=input_paths,
            conflicted_paths=(_receipt_path(directory),),
            diagnostics=(f"verified add resolution proof failed: {error}",),
        )
    try:
        aggregate = _aggregate(snapshot)
        _require_valid(aggregate)
    except (StorageError, ValueError) as error:
        return _ReceiptResolution(
            False,
            receipt_record.added_keys,
            input_paths,
            retained_paths=input_paths,
            conflicted_paths=(_receipt_path(directory),),
            diagnostics=(f"committed workspace proof failed: {error}",),
        )
    canonical_keys = set(aggregate.bibliography.identity_index.canonical_keys)
    missing_keys = tuple(key for key in receipt_record.added_keys if key not in canonical_keys)
    if missing_keys:
        return _ReceiptResolution(
            False,
            receipt_record.added_keys,
            input_paths,
            retained_paths=input_paths,
            conflicted_paths=(_receipt_path(directory),),
            diagnostics=(f"committed staging keys are missing: {missing_keys}",),
        )
    consumed: list[Path] = []
    retained: list[Path] = []
    conflicted: list[Path] = []
    diagnostics: list[str] = []
    remaining: list[_ReceiptItem] = []
    for item in pending_items:
        path = directory / item.name
        if not path.exists():
            consumed.append(path)
            continue
        issue = _prove_receipt_item(path, item, aggregate)
        if issue is not None:
            retained.append(path)
            conflicted.append(path)
            remaining.append(item)
            diagnostics.append(issue)
    if conflicted:
        return _ReceiptResolution(
            False,
            receipt_record.added_keys,
            input_paths,
            tuple(consumed),
            tuple(retained),
            tuple(conflicted),
            tuple(diagnostics),
        )
    for item in pending_items:
        path = directory / item.name
        if not path.exists():
            continue
        issue = _prove_receipt_item(path, item, aggregate)
        if issue is not None:
            retained.append(path)
            conflicted.append(path)
            remaining.append(item)
            diagnostics.append(f"source drifted before unlink: {issue}")
            continue
        try:
            path.unlink()
            _fsync_directory(directory)
            consumed.append(path)
        except OSError as error:
            retained.append(path)
            remaining.append(item)
            diagnostics.append(f"could not consume staging file '{path}': {error}")
    try:
        if remaining:
            _write_receipt(
                directory,
                replace(
                    receipt_record,
                    pending_files=tuple(item.name for item in remaining),
                ),
            )
        else:
            _clear_receipt(directory)
    except (OSError, ValueError) as error:
        diagnostics.append(f"could not update staging cleanup receipt: {error}")
    return _ReceiptResolution(
        False,
        receipt_record.added_keys,
        input_paths,
        tuple(consumed),
        tuple(retained),
        tuple(conflicted),
        tuple(diagnostics),
    )


def add(
    paths: WorkspacePaths,
    staging: Path,
    *,
    dry_run: bool = False,
    lock_backend: LockBackend | None = None,
    fault_hook: FaultHook = _noop_fault_hook,
) -> AddResult:
    """Append staged entries and consume exact inputs only after verified commit."""
    directory, explicit = _selected_staging(staging)
    protected = (paths.bibliography, paths.identifiers, paths.add_order)
    with WorkspaceTransaction(
        paths, "add", lock_backend=lock_backend, fault_hook=fault_hook
    ) as transaction:
        aggregate = _aggregate(transaction.snapshot)
        _require_valid(aggregate)
        try:
            pending = _parse_receipt(directory, protected)
        except ValueError as error:
            receipt_path = _receipt_path(directory)
            return AddResult(
                (),
                input_paths=(receipt_path,),
                retained_paths=(receipt_path,),
                conflicted_paths=(receipt_path,),
                cleanup_diagnostics=(str(error),),
            )
        pending_paths = (
            tuple(directory / item.name for item in pending.files) if pending is not None else ()
        )
        if dry_run and pending is not None:
            return AddResult(
                pending.added_keys,
                input_paths=pending_paths,
                retained_paths=pending_paths,
                cleanup_diagnostics=("staging cleanup receipt is pending",),
            )
        try:
            resolution = _resolve_receipt(directory, protected, transaction.snapshot, paths)
        except ValueError as error:
            receipt_path = _receipt_path(directory)
            return AddResult(
                (),
                input_paths=(receipt_path,),
                retained_paths=(receipt_path,),
                conflicted_paths=(receipt_path,),
                cleanup_diagnostics=(str(error),),
            )
        if not resolution.proceed:
            return AddResult(
                resolution.added_keys,
                input_paths=resolution.input_paths,
                consumed_paths=resolution.consumed_paths,
                retained_paths=resolution.retained_paths,
                conflicted_paths=resolution.conflicted_paths,
                cleanup_diagnostics=resolution.diagnostics,
            )

        input_paths = _staging_paths(directory, explicit, protected)
        sources = tuple((path, path.read_bytes()) for path in input_paths)
        prepared_batch = prepare_staged_sources(sources)
        prepared = prepared_batch.entries

        domain_result = lifecycle.add(aggregate.bibliography, prepared)
        for entry in prepared:
            inventory = identifiers_from_entry(entry)
            main, _value = select_main_identifier(inventory)
            aggregate.identifiers[entry.key] = IdentifierRecord(main, inventory)
        aggregate.add_order = (*aggregate.add_order, *domain_result.added_keys)
        _require_valid(aggregate)
        candidate = _candidate(aggregate)
        result = replace(
            domain_result,
            stripped_doi_query_keys=prepared_batch.stripped_doi_query_keys,
            stripped_doi_fragment_keys=prepared_batch.stripped_doi_fragment_keys,
            input_paths=input_paths,
            retained_paths=input_paths,
        )
        if dry_run or not result.changes.changed:
            return result
        receipt = _CleanupReceipt(
            transaction.transaction_id,
            result.added_keys,
            _snapshot_vector(transaction.snapshot),
            _candidate_vector(candidate),
            tuple(
                _ReceiptItem(
                    file.path.name,
                    file.sha256,
                    file.keys,
                    tuple(_added_entry_manifest(entry) for entry in file.entries),
                )
                for file in prepared_batch.files
            ),
            tuple(file.path.name for file in prepared_batch.files),
        )
        try:
            _write_receipt(directory, receipt)
        except (OSError, ValueError) as error:
            return replace(
                result,
                cleanup_diagnostics=(f"could not record pending cleanup: {error}",),
            )
        commit = transaction.commit(
            candidate,
            operation_evidence_sha256=_receipt_evidence_sha256(receipt),
        )
        result = replace(result, commit=commit)
        if commit.outcome is CommitOutcome.COMMITTED_UNVERIFIED:
            return replace(
                result,
                cleanup_diagnostics=("workspace commit is unverified; cleanup remains pending",),
            )
        if commit.cleanup_pending:
            return replace(
                result,
                cleanup_diagnostics=("workspace cleanup is pending recovery",),
            )
        try:
            current = read_workspace_snapshot(paths, attempts=1)
            resolution = _resolve_receipt(directory, protected, current, paths)
        except (OSError, StorageError, ValueError) as error:
            receipt_path = _receipt_path(directory)
            return replace(
                result,
                retained_paths=input_paths,
                conflicted_paths=(receipt_path,),
                cleanup_diagnostics=(f"could not resolve pending cleanup: {error}",),
            )
        if commit.outcome is CommitOutcome.NOT_COMMITTED and resolution.proceed:
            return result
        return replace(
            result,
            consumed_paths=resolution.consumed_paths,
            retained_paths=resolution.retained_paths,
            conflicted_paths=resolution.conflicted_paths,
            cleanup_diagnostics=resolution.diagnostics,
        )


def normalize(
    paths: WorkspacePaths,
    action: str,
    *,
    dry_run: bool = False,
    lock_backend: LockBackend | None = None,
    fault_hook: FaultHook = _noop_fault_hook,
) -> NormalizeResult:
    """Normalize only bibliography presentation while preserving ledger bytes."""
    with WorkspaceTransaction(
        paths, f"normalize:{action}", lock_backend=lock_backend, fault_hook=fault_hook
    ) as transaction:
        aggregate = _aggregate(transaction.snapshot)
        _require_valid(aggregate)
        result = normalize_bibliography(aggregate.bibliography, action)
        _require_valid(aggregate)
        if dry_run or not result.changes.changed:
            return result
        commit = transaction.commit(
            _candidate(
                aggregate,
                identifiers=transaction.snapshot.identifiers.data,
                add_order=transaction.snapshot.add_order.data,
            )
        )
        return replace(result, commit=commit)


def reconcile(
    paths: WorkspacePaths,
    *,
    dry_run: bool = False,
    lock_backend: LockBackend | None = None,
    fault_hook: FaultHook = _noop_fault_hook,
) -> ReconcileResult:
    """Monotonically add missing bibliography projections to identifier JSON."""
    with WorkspaceTransaction(
        paths, "reconcile", lock_backend=lock_backend, fault_hook=fault_hook
    ) as transaction:
        aggregate = _aggregate(transaction.snapshot)
        result = reconcile_identifier_inventory(aggregate)
        _require_valid(aggregate)
        if dry_run or not result.changes.changed:
            return result
        candidate = _candidate(
            aggregate,
            bibliography=transaction.snapshot.bibliography.data,
            add_order=transaction.snapshot.add_order.data,
        )
        return replace(result, commit=transaction.commit(candidate))


def remove(
    paths: WorkspacePaths,
    identity: str,
    *,
    dry_run: bool = False,
    lock_backend: LockBackend | None = None,
    fault_hook: FaultHook = _noop_fault_hook,
) -> RemoveResult:
    """Hard-delete one record from all three workspace artifacts."""
    with WorkspaceTransaction(
        paths, "remove", lock_backend=lock_backend, fault_hook=fault_hook
    ) as transaction:
        aggregate = _aggregate(transaction.snapshot)
        _require_valid(aggregate)
        result = lifecycle.remove_from_workspace(aggregate, identity)
        _require_valid(aggregate)
        if dry_run:
            return result
        return replace(result, commit=transaction.commit(_candidate(aggregate)))


def _published_payload(path: Path) -> tuple[Entry, str]:
    entries = parse_staged_entries((path,))
    if len(entries) != 1:
        raise ValueError("publication payload must contain exactly one entry")
    entry = entries[0]
    fields = doi_fields(entry)
    if len(fields) != 1:
        raise ValueError("publication payload must contain exactly one DOI field")
    return entry, str(fields[0].value)


def promote(
    paths: WorkspacePaths,
    identity: str,
    published_path: Path,
    *,
    dry_run: bool = False,
    lock_backend: LockBackend | None = None,
    fault_hook: FaultHook = _noop_fault_hook,
) -> PromoteResult:
    """Promote one arXiv record across all three workspace artifacts."""
    raw_published, raw_doi = _published_payload(published_path)
    canonical = canonicalize_new_doi(raw_doi)
    published = replace_doi(raw_published, canonical)
    with WorkspaceTransaction(
        paths, "promote", lock_backend=lock_backend, fault_hook=fault_hook
    ) as transaction:
        aggregate = _aggregate(transaction.snapshot)
        _require_valid(aggregate)
        result = lifecycle.promote_in_workspace(
            aggregate,
            identity,
            published,
            canonical.value,
            stripped_doi_query=canonical.had_query,
            stripped_doi_fragment=canonical.had_fragment,
        )
        _require_valid(aggregate)
        if dry_run:
            return result
        return replace(result, commit=transaction.commit(_candidate(aggregate)))


def recover(
    paths: WorkspacePaths,
    *,
    dry_run: bool = False,
    lock_backend: LockBackend | None = None,
    fault_hook: FaultHook = _noop_fault_hook,
) -> RecoverResult:
    """Inspect or resolve the workspace coordinator."""
    if dry_run:
        status = inspect_workspace_recovery(paths)
        return RecoverResult(status.state.value, diagnostics=status.diagnostics)
    result = recover_workspace(paths, lock_backend=lock_backend, fault_hook=fault_hook)
    return RecoverResult(
        result.resolution, observed=result.observed, diagnostics=result.diagnostics
    )
