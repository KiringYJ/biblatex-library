"""Value-opaque codecs and fail-closed three-file workspace transactions."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import stat
import tempfile
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from types import TracebackType
from typing import Any, Protocol, Self

import bibtexparser
from bibtexparser import Library

from biblio.bibliography import Bibliography, IdentityIndex
from biblio.results import (
    ArtifactCommitEvidence,
    CommitOutcome,
    WorkspaceCommitResult,
)


class StorageError(RuntimeError):
    """Base exception for storage boundary failures."""


class LockUnavailableError(StorageError):
    """Another cooperating process owns the bibliography lock."""


class IndeterminateLockError(StorageError):
    """The platform cannot provide authoritative locking semantics."""


class RecoveryRequiredError(StorageError):
    """A prior transaction must be explicitly recovered before mutation."""


class RecoveryRefusedError(StorageError):
    """Recovery evidence is invalid, unstable, or insufficient."""


class StaleTargetError(StorageError):
    """The target changed externally after the locked snapshot was captured."""


class LockBackend(Protocol):
    """Nonblocking advisory lock held on an open persistent sidecar."""

    def acquire(self, path: Path) -> LockHandle:
        """Acquire *path* or raise a classified lock exception."""


class LockHandle(Protocol):
    """One acquired OS lock."""

    def close(self) -> None:
        """Release the lock and close its descriptor."""


class _DescriptorLock:
    def __init__(self, descriptor: int, unlock: Callable[[int], None]) -> None:
        self._descriptor = descriptor
        self._unlock = unlock
        self._closed = False

    def close(self) -> None:
        if self._closed:
            return
        try:
            self._unlock(self._descriptor)
        finally:
            os.close(self._descriptor)
            self._closed = True


class PlatformLockBackend:
    """Standard-library POSIX ``flock`` or Windows reserved-byte locking."""

    def acquire(self, path: Path) -> LockHandle:
        _reject_unsupported_lock_location(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            if os.name == "posix":
                return self._acquire_posix(descriptor)
            if os.name == "nt":
                return self._acquire_windows(descriptor)
            raise IndeterminateLockError(f"unsupported lock platform: {os.name}")
        except BaseException:
            os.close(descriptor)
            raise

    @staticmethod
    def _acquire_posix(descriptor: int) -> LockHandle:
        import errno
        import fcntl

        try:
            fcntl_api = vars(fcntl)
            flock = fcntl_api["flock"]
            flock(descriptor, fcntl_api["LOCK_EX"] | fcntl_api["LOCK_NB"])
        except OSError as error:
            if error.errno in {errno.EACCES, errno.EAGAIN}:
                raise LockUnavailableError("bibliography lock is already held") from error
            raise IndeterminateLockError(f"unable to establish POSIX lock: {error}") from error

        def unlock(fd: int) -> None:
            fcntl_api["flock"](fd, fcntl_api["LOCK_UN"])

        return _DescriptorLock(descriptor, unlock)

    @staticmethod
    def _acquire_windows(descriptor: int) -> LockHandle:
        import msvcrt

        msvcrt_api = vars(msvcrt)
        if os.fstat(descriptor).st_size < 1:
            os.write(descriptor, b"\0")
            os.fsync(descriptor)
        os.lseek(descriptor, 0, os.SEEK_SET)
        try:
            msvcrt_api["locking"](descriptor, msvcrt_api["LK_NBLCK"], 1)
        except OSError as error:
            if getattr(error, "winerror", None) in {32, 33, 36} or error.errno in {13, 36}:
                raise LockUnavailableError("bibliography lock is already held") from error
            raise IndeterminateLockError(f"unable to establish Windows lock: {error}") from error

        def unlock(fd: int) -> None:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt_api["locking"](fd, msvcrt_api["LK_UNLCK"], 1)

        return _DescriptorLock(descriptor, unlock)


def _reject_unsupported_lock_location(path: Path) -> None:
    if os.name != "nt":
        return
    absolute = Path(os.path.abspath(path))
    anchor = absolute.anchor
    if anchor.startswith("\\\\"):
        raise IndeterminateLockError("Windows UNC/network lock paths are unsupported")
    drive_type = _windows_drive_type(anchor)
    if drive_type == 4:
        raise IndeterminateLockError("Windows mapped network lock paths are unsupported")
    if drive_type in {0, 1}:
        raise IndeterminateLockError("Windows lock-path drive semantics are indeterminate")


def _windows_drive_type(root: str) -> int:
    import ctypes

    kernel32 = vars(ctypes)["windll"].kernel32
    get_drive_type = kernel32.GetDriveTypeW
    get_drive_type.argtypes = [ctypes.c_wchar_p]
    get_drive_type.restype = ctypes.c_uint
    return int(get_drive_type(root))


class BibliographyCodec:
    """Parse and deterministically serialize a value-opaque bibliography."""

    @staticmethod
    def parse_bytes(data: bytes) -> Bibliography:
        if data.startswith(b"\xef\xbb\xbf"):
            data = data[3:]
        try:
            source = data.decode("utf-8")
        except UnicodeDecodeError as error:
            raise StorageError("bibliography is not valid UTF-8") from error
        library = vars(bibtexparser)["parse_string"](source)
        if library.failed_blocks:
            raise StorageError(
                "bibliography contains parser failures: "
                + "; ".join(type(block).__name__ for block in library.failed_blocks)
            )
        entries = list(library.entries)
        return Bibliography(library.blocks, IdentityIndex(entries))

    @staticmethod
    def serialize(bibliography: Bibliography) -> bytes:
        bibliography.validate()
        rendered = bibtexparser.write_string(Library(list(bibliography.blocks)))
        normalized = rendered.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n") + "\n"
        return normalized.encode("utf-8")


@dataclass(frozen=True, slots=True)
class SupportedMetadata:
    """Portable metadata this writer can preserve and verify."""

    mode: int | None
    readonly: bool | None


FaultHook = Callable[[str], None]


def _noop_fault_hook(_phase: str) -> None:
    return


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _capture_metadata(path: Path, existed: bool) -> SupportedMetadata:
    if not existed:
        return SupportedMetadata(None, None)
    mode = stat.S_IMODE(path.stat().st_mode)
    readonly = not bool(mode & stat.S_IWUSR) if os.name == "nt" else None
    return SupportedMetadata(mode, readonly)


def _apply_metadata(path: Path, metadata: SupportedMetadata) -> None:
    if metadata.mode is not None:
        os.chmod(path, metadata.mode)


def _remove_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except PermissionError:
        if os.name != "nt":
            raise
        os.chmod(path, stat.S_IWRITE)
        path.unlink(missing_ok=True)


def _verify_metadata(path: Path, metadata: SupportedMetadata) -> None:
    if metadata.mode is None:
        return
    observed_mode = stat.S_IMODE(path.stat().st_mode)
    if os.name == "posix" and observed_mode != metadata.mode:
        raise StorageError(
            f"mode changed during replacement: expected {metadata.mode:o}, got {observed_mode:o}"
        )
    if os.name == "nt" and metadata.readonly != (not bool(observed_mode & stat.S_IWUSR)):
        raise StorageError("readonly state changed during replacement")


def _json_bytes(record: Mapping[str, Any]) -> bytes:
    return (json.dumps(record, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode()


def _fsync_directory(path: Path) -> None:
    if os.name != "posix":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_write(path: Path, data: bytes, fault_hook: FaultHook, phase: str) -> None:
    candidate_path: Path | None = None
    try:
        descriptor, raw_path = tempfile.mkstemp(prefix=f".{path.name}.candidate-", dir=path.parent)
        candidate_path = Path(raw_path)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            fault_hook(f"{phase}:before_file_fsync")
            os.fsync(stream.fileno())
        if candidate_path.read_bytes() != data:
            raise StorageError(f"{phase} candidate verification failed")
        fault_hook(f"{phase}:before_replace")
        os.replace(candidate_path, path)
        candidate_path = None
        fault_hook(f"{phase}:before_directory_fsync")
        _fsync_directory(path.parent)
        if path.read_bytes() != data:
            raise StorageError(f"{phase} installed verification failed")
    finally:
        if candidate_path is not None:
            candidate_path.unlink(missing_ok=True)


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RecoveryRequiredError(f"unreadable recovery evidence at {path}: {error}") from error
    if not isinstance(value, dict):
        raise RecoveryRequiredError(f"recovery evidence at {path} is not an object")
    return value


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and value == value.lower()
        and all(character in "0123456789abcdef" for character in value)
    )


def _durability_level() -> str:
    if os.name == "posix":
        return "namespace_atomic_directory_fsync"
    if os.name == "nt":
        return "namespace_atomic_best_effort_durability"
    return "indeterminate"


def _diagnostics(messages: tuple[str, ...]) -> list[dict[str, str]]:
    return [{"code": message.split(":", 1)[0].lower(), "message": message} for message in messages]


# Raw three-artifact workspace storage. Domain parsing and cross-artifact semantic
# validation intentionally live above this boundary.

_WORKSPACE_FORMAT = "biblio-workspace-transaction"
_WORKSPACE_REPORT_FORMAT = "biblio-workspace-resolution"
_WORKSPACE_STATES = {
    "prepared",
    "installing",
    "recovery_required",
    "resolving_rollback",
    "resolving_forward",
    "cleanup_pending",
    "idle",
}
_WORKSPACE_NAMES = ("bibliography", "identifiers", "add_order")
_WORKSPACE_INSTALL_ORDER = ("identifiers", "add_order", "bibliography")


class UnstableWorkspaceError(StorageError):
    """A side-effect-free vector read observed concurrent change."""


@dataclass(frozen=True, slots=True)
class WorkspacePaths:
    """The three explicit files forming one workspace integrity set."""

    bibliography: Path
    identifiers: Path
    add_order: Path


@dataclass(frozen=True, slots=True)
class WorkspaceFileSnapshot:
    """Raw bytes and metadata for one required workspace artifact."""

    name: str
    path: Path
    data: bytes
    sha256: str
    metadata: SupportedMetadata


@dataclass(frozen=True, slots=True)
class WorkspaceSnapshot:
    """One stable raw vector snapshot."""

    bibliography: WorkspaceFileSnapshot
    identifiers: WorkspaceFileSnapshot
    add_order: WorkspaceFileSnapshot

    def items(self) -> tuple[WorkspaceFileSnapshot, ...]:
        """Return artifacts in canonical name order."""
        return (self.bibliography, self.identifiers, self.add_order)

    def by_name(self, name: str) -> WorkspaceFileSnapshot:
        """Return one named artifact."""
        return getattr(self, name)


@dataclass(frozen=True, slots=True)
class WorkspaceCandidate:
    """Caller-validated raw candidate bytes for all three artifacts."""

    bibliography: bytes
    identifiers: bytes
    add_order: bytes

    def by_name(self, name: str) -> bytes:
        """Return one named candidate."""
        return getattr(self, name)


@dataclass(frozen=True, slots=True)
class WorkspaceDigestVector:
    """Exact SHA-256 vector for the three workspace artifacts."""

    bibliography: str
    identifiers: str
    add_order: str

    def by_name(self, name: str) -> str:
        """Return one named digest."""
        return getattr(self, name)


@dataclass(frozen=True, slots=True)
class WorkspaceResolutionProof:
    """Validated durable evidence for one verified workspace transaction."""

    transaction_id: str
    operation: str
    outcome: CommitOutcome
    original: WorkspaceDigestVector
    candidate: WorkspaceDigestVector
    observed: WorkspaceDigestVector
    operation_evidence_sha256: str | None = None


class WorkspaceRecoveryState(StrEnum):
    """Read-only coordinator classification."""

    CLEAN = "clean"
    REQUIRED = "recovery_required"
    CLEANUP_PENDING = "cleanup_pending"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class WorkspaceRecoveryStatus:
    """Read-only workspace coordinator status."""

    state: WorkspaceRecoveryState
    coordinator: Mapping[str, Any] | None = None
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class WorkspaceRecoveryResult:
    """Explicit workspace recovery result."""

    resolution: str
    observed: Mapping[str, str]
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _WorkspaceLayout:
    paths: WorkspacePaths
    locks: Mapping[str, Path]
    coordinator: Path
    report: Path
    candidates: Mapping[str, Path]
    shadows: Mapping[str, Path]


def _workspace_path_map(paths: WorkspacePaths) -> dict[str, Path]:
    for path in (paths.bibliography, paths.identifiers, paths.add_order):
        _reject_unsupported_lock_location(path)
    return {
        "bibliography": paths.bibliography.resolve(),
        "identifiers": paths.identifiers.resolve(),
        "add_order": paths.add_order.resolve(),
    }


def _workspace_normalized(path: Path) -> str:
    return os.path.normcase(str(path.resolve()))


def _workspace_layout(paths: WorkspacePaths, nonce: str) -> _WorkspaceLayout:
    resolved = _workspace_path_map(paths)
    locks = {name: path.parent / f".{path.name}.biblio.lock" for name, path in resolved.items()}
    bibliography = resolved["bibliography"]
    coordinator = bibliography.parent / f".{bibliography.name}.biblio-workspace.json"
    report = bibliography.parent / f".{bibliography.name}.biblio-workspace-resolved.json"
    candidates = {
        name: path.parent / f".{path.name}.biblio-workspace-{nonce}.candidate"
        for name, path in resolved.items()
    }
    shadows = {
        name: path.parent / f".{path.name}.biblio-workspace-{nonce}.original"
        for name, path in resolved.items()
    }
    all_paths = [*resolved.values(), *locks.values(), coordinator, report]
    all_paths.extend(candidates.values())
    all_paths.extend(shadows.values())
    normalized = [_workspace_normalized(path) for path in all_paths]
    if len(normalized) != len(set(normalized)):
        raise StorageError("workspace target or reserved internal paths collide")
    for path in all_paths:
        _reject_unsupported_lock_location(path)
    return _WorkspaceLayout(
        WorkspacePaths(**resolved), locks, coordinator, report, candidates, shadows
    )


def _read_required_file(name: str, path: Path) -> WorkspaceFileSnapshot:
    try:
        data = path.read_bytes()
    except FileNotFoundError as error:
        raise StorageError(f"required workspace artifact does not exist: {path}") from error
    return WorkspaceFileSnapshot(
        name=name,
        path=path,
        data=data,
        sha256=_sha256(data),
        metadata=_capture_metadata(path, True),
    )


def read_workspace_snapshot(paths: WorkspacePaths, *, attempts: int = 2) -> WorkspaceSnapshot:
    """Optimistically double-read a stable raw vector without creating files."""
    if attempts < 1:
        raise ValueError("attempts must be positive")
    resolved = _workspace_path_map(paths)
    if len({_workspace_normalized(path) for path in resolved.values()}) != 3:
        raise StorageError("workspace target paths must be distinct")
    for _attempt in range(attempts):
        first = {name: _read_required_file(name, path) for name, path in resolved.items()}
        second_data = {name: path.read_bytes() for name, path in resolved.items()}
        if all(_sha256(second_data[name]) == first[name].sha256 for name in _WORKSPACE_NAMES):
            return WorkspaceSnapshot(**first)
    raise UnstableWorkspaceError("workspace vector changed during side-effect-free read")


def _workspace_lock_order(layout: _WorkspaceLayout) -> list[Path]:
    return sorted(layout.locks.values(), key=_workspace_normalized)


def _acquire_workspace_locks(layout: _WorkspaceLayout, backend: LockBackend) -> list[LockHandle]:
    acquired: list[LockHandle] = []
    try:
        for path in _workspace_lock_order(layout):
            acquired.append(backend.acquire(path))
        return acquired
    except BaseException:
        for handle in reversed(acquired):
            handle.close()
        raise


def _close_workspace_locks(handles: list[LockHandle]) -> None:
    for handle in reversed(handles):
        handle.close()


def _write_workspace_artifact(path: Path, data: bytes, metadata: SupportedMetadata) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        _apply_metadata(path, metadata)
        if path.read_bytes() != data:
            raise StorageError(f"staged workspace artifact verification failed: {path}")
        _verify_metadata(path, metadata)
        _fsync_directory(path.parent)
    except BaseException:
        _remove_file(path)
        raise


def _workspace_json(path: Path) -> dict[str, Any] | None:
    return _read_json(path)


def _validate_workspace_marker(record: Mapping[str, Any], layout: _WorkspaceLayout) -> None:
    if (
        record.get("format") != _WORKSPACE_FORMAT
        or type(record.get("version")) is not int
        or record.get("version") != 1
        or record.get("state") not in _WORKSPACE_STATES
        or not isinstance(record.get("txid"), str)
        or not record["txid"]
    ):
        raise RecoveryRefusedError("invalid workspace coordinator header")
    paths = record.get("paths")
    if not isinstance(paths, dict):
        raise RecoveryRefusedError("workspace coordinator paths are invalid")
    expected_paths = {name: str(path) for name, path in _workspace_path_map(layout.paths).items()}
    if paths != expected_paths:
        raise RecoveryRefusedError("workspace coordinator paths differ from caller paths")
    artifacts = record.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != set(_WORKSPACE_NAMES):
        raise RecoveryRefusedError("workspace coordinator artifact vector is invalid")
    commit_artifact = record.get("commit_artifact")
    if commit_artifact not in _WORKSPACE_NAMES:
        raise RecoveryRefusedError("workspace coordinator commit artifact is invalid")
    dirty_artifacts: list[str] = []
    for name in _WORKSPACE_NAMES:
        item = artifacts[name]
        if not isinstance(item, dict):
            raise RecoveryRefusedError("workspace coordinator artifact evidence is invalid")
        if not _is_sha256(item.get("original_sha256")) or not _is_sha256(
            item.get("candidate_sha256")
        ):
            raise RecoveryRefusedError("workspace coordinator digest is invalid")
        observed = item.get("observed_sha256")
        if observed is not None and not _is_sha256(observed):
            raise RecoveryRefusedError("workspace coordinator observed digest is invalid")
        if not isinstance(item.get("dirty"), bool):
            raise RecoveryRefusedError("workspace coordinator dirty flag is invalid")
        digest_dirty = item["original_sha256"] != item["candidate_sha256"]
        if item["dirty"] != digest_dirty:
            raise RecoveryRefusedError("workspace coordinator dirty flag disagrees with digests")
        if digest_dirty:
            dirty_artifacts.append(name)
        if not isinstance(item.get("replaced"), bool):
            raise RecoveryRefusedError("workspace coordinator replaced flag is invalid")
        if item.get("mode") is not None and type(item["mode"]) is not int:
            raise RecoveryRefusedError("workspace coordinator mode is invalid")
        if item.get("readonly") is not None and not isinstance(item["readonly"], bool):
            raise RecoveryRefusedError("workspace coordinator readonly flag is invalid")
        for field, expected in (
            ("candidate_path", layout.candidates[name]),
            ("shadow_path", layout.shadows[name]),
        ):
            value = item.get(field)
            if item["dirty"]:
                if value != str(expected):
                    raise RecoveryRefusedError("workspace staged path is hostile or inconsistent")
            elif value is not None:
                raise RecoveryRefusedError("clean workspace artifact unexpectedly has staged path")
    expected_commit_artifact = next(
        (name for name in reversed(_WORKSPACE_INSTALL_ORDER) if name in dirty_artifacts),
        None,
    )
    if commit_artifact != expected_commit_artifact:
        raise RecoveryRefusedError(
            "workspace coordinator commit artifact is not the last dirty artifact"
        )
    allowlist = record.get("cleanup_allowlist")
    if not isinstance(allowlist, list) or any(not isinstance(item, str) for item in allowlist):
        raise RecoveryRefusedError("workspace cleanup allowlist is invalid")
    allowed = {str(path) for path in (*layout.candidates.values(), *layout.shadows.values())}
    if not set(allowlist).issubset(allowed):
        raise RecoveryRefusedError("workspace cleanup allowlist contains a hostile path")
    report_path = record.get("resolution_report_path")
    report_digest = record.get("resolution_report_sha256")
    content_outcome = record.get("content_outcome")
    if "operation_evidence_sha256" not in record:
        raise RecoveryRefusedError("workspace operation evidence field is missing")
    operation_evidence = record["operation_evidence_sha256"]
    if operation_evidence is not None and not _is_sha256(operation_evidence):
        raise RecoveryRefusedError("workspace operation evidence digest is invalid")
    resolved_state = record["state"] in {"cleanup_pending", "idle"}
    if resolved_state:
        if (
            report_path != str(layout.report)
            or not _is_sha256(report_digest)
            or content_outcome
            not in {CommitOutcome.NOT_COMMITTED.value, CommitOutcome.COMMITTED_VERIFIED.value}
        ):
            raise RecoveryRefusedError("workspace resolution evidence is invalid")
    elif report_path is not None or report_digest is not None or content_outcome is not None:
        raise RecoveryRefusedError("unresolved workspace has premature resolution evidence")


def inspect_workspace_recovery(paths: WorkspacePaths) -> WorkspaceRecoveryStatus:
    """Inspect the coordinator without creating locks or clearing evidence."""
    nonce = "inspection-placeholder"
    try:
        layout = _workspace_layout(paths, nonce)
        record = _workspace_json(layout.coordinator)
        if record is None:
            return WorkspaceRecoveryStatus(WorkspaceRecoveryState.CLEAN)
        marker_nonce = record.get("txid")
        if not isinstance(marker_nonce, str) or not marker_nonce:
            raise RecoveryRefusedError("workspace coordinator txid is invalid")
        layout = _workspace_layout(paths, marker_nonce)
        _validate_workspace_marker(record, layout)
    except (StorageError, RecoveryRequiredError, RecoveryRefusedError) as error:
        return WorkspaceRecoveryStatus(WorkspaceRecoveryState.INVALID, diagnostics=(str(error),))
    state = record["state"]
    if state == "idle":
        return WorkspaceRecoveryStatus(WorkspaceRecoveryState.CLEAN, record)
    if state == "cleanup_pending":
        return WorkspaceRecoveryStatus(WorkspaceRecoveryState.CLEANUP_PENDING, record)
    return WorkspaceRecoveryStatus(WorkspaceRecoveryState.REQUIRED, record)


def _workspace_observed(layout: _WorkspaceLayout) -> dict[str, str]:
    return {
        name: _sha256(path.read_bytes()) for name, path in _workspace_path_map(layout.paths).items()
    }


def _digest_vector(values: Mapping[str, str]) -> WorkspaceDigestVector:
    return WorkspaceDigestVector(*(values[name] for name in _WORKSPACE_NAMES))


def _validate_digest_vector(vector: WorkspaceDigestVector, description: str) -> None:
    if any(not _is_sha256(vector.by_name(name)) for name in _WORKSPACE_NAMES):
        raise RecoveryRefusedError(f"{description} workspace digest vector is invalid")


def _marker_digest_vector(marker: Mapping[str, Any], digest_name: str) -> WorkspaceDigestVector:
    return _digest_vector(
        {name: marker["artifacts"][name][digest_name] for name in _WORKSPACE_NAMES}
    )


def _workspace_metadata(marker: Mapping[str, Any], name: str) -> SupportedMetadata:
    item = marker["artifacts"][name]
    return SupportedMetadata(mode=item["mode"], readonly=item["readonly"])


def _prove_workspace_vector(
    layout: _WorkspaceLayout, marker: Mapping[str, Any], desired: str
) -> dict[str, str]:
    """Freshly prove the complete desired digest and metadata vector."""
    paths = _workspace_path_map(layout.paths)
    observed: dict[str, str] = {}
    for name in _WORKSPACE_NAMES:
        item = marker["artifacts"][name]
        digest = _sha256(paths[name].read_bytes())
        if digest not in {item["original_sha256"], item["candidate_sha256"]}:
            raise RecoveryRefusedError(f"workspace artifact has a third digest: {name}")
        if digest != item[f"{desired}_sha256"]:
            raise RecoveryRefusedError(f"workspace artifact is not in the desired vector: {name}")
        _verify_metadata(paths[name], _workspace_metadata(marker, name))
        observed[name] = digest
    return observed


def _workspace_marker_bytes(record: Mapping[str, Any]) -> bytes:
    return _json_bytes(record)


def _write_workspace_marker(
    layout: _WorkspaceLayout,
    record: Mapping[str, Any],
    fault_hook: FaultHook,
    phase: str,
) -> None:
    _atomic_write(layout.coordinator, _workspace_marker_bytes(record), fault_hook, phase)


def _workspace_evidence(
    layout: _WorkspaceLayout,
    marker: Mapping[str, Any],
    observed: Mapping[str, str | None],
    replaced: set[str],
) -> tuple[ArtifactCommitEvidence, ...]:
    paths = _workspace_path_map(layout.paths)
    return tuple(
        ArtifactCommitEvidence(
            name=name,
            path=str(paths[name]),
            original_sha256=marker["artifacts"][name]["original_sha256"],
            candidate_sha256=marker["artifacts"][name]["candidate_sha256"],
            observed_sha256=observed.get(name),
            dirty=marker["artifacts"][name]["dirty"],
            replaced=name in replaced,
        )
        for name in _WORKSPACE_NAMES
    )


def _workspace_replaced(marker: Mapping[str, Any]) -> set[str]:
    return {name for name in _WORKSPACE_NAMES if marker["artifacts"][name].get("replaced") is True}


def _validate_workspace_source(
    layout: _WorkspaceLayout, marker: Mapping[str, Any], name: str, desired: str
) -> Path:
    item = marker["artifacts"][name]
    field = "candidate_path" if desired == "candidate" else "shadow_path"
    digest_field = "candidate_sha256" if desired == "candidate" else "original_sha256"
    path = Path(item[field])
    expected = layout.candidates[name] if desired == "candidate" else layout.shadows[name]
    if _workspace_normalized(path) != _workspace_normalized(expected):
        raise RecoveryRefusedError("workspace recovery source path is hostile")
    try:
        data = path.read_bytes()
    except FileNotFoundError as error:
        raise RecoveryRefusedError(f"workspace recovery source is missing: {path}") from error
    if _sha256(data) != item[digest_field]:
        raise RecoveryRefusedError(f"workspace recovery source digest changed: {path}")
    return path


def _repair_workspace_vector(
    layout: _WorkspaceLayout,
    marker: dict[str, Any],
    desired: str,
    fault_hook: FaultHook,
) -> tuple[dict[str, str], set[str]]:
    observed = _workspace_observed(layout)
    replaced = _workspace_replaced(marker)
    for name in _WORKSPACE_NAMES:
        item = marker["artifacts"][name]
        if observed[name] not in {item["original_sha256"], item["candidate_sha256"]}:
            raise RecoveryRefusedError(f"workspace artifact has a third digest: {name}")
        _verify_metadata(_workspace_path_map(layout.paths)[name], _workspace_metadata(marker, name))
        if item["dirty"] and observed[name] == item["candidate_sha256"]:
            replaced.add(name)
            item["replaced"] = True
    order = (
        _WORKSPACE_INSTALL_ORDER
        if desired == "candidate"
        else tuple(reversed(_WORKSPACE_INSTALL_ORDER))
    )
    paths = _workspace_path_map(layout.paths)
    for name in order:
        item = marker["artifacts"][name]
        wanted = item[f"{desired}_sha256"]
        if observed[name] == wanted:
            continue
        source = _validate_workspace_source(layout, marker, name, desired)
        fault_hook(f"workspace:before_replace:{name}:{desired}")
        os.replace(source, paths[name])
        replaced.add(name)
        item["replaced"] = True
        fault_hook(f"workspace:after_replace:{name}:{desired}")
        _fsync_directory(paths[name].parent)
        observed[name] = _sha256(paths[name].read_bytes())
        if observed[name] != wanted:
            raise StorageError(f"workspace replacement verification failed: {name}")
        _verify_metadata(paths[name], _workspace_metadata(marker, name))
        marker["artifacts"][name]["observed_sha256"] = observed[name]
        _write_workspace_marker(layout, marker, fault_hook, "workspace_progress")
    return observed, replaced


def _read_workspace_resolution_report(
    layout: _WorkspaceLayout, marker: Mapping[str, Any]
) -> tuple[CommitOutcome, str, dict[str, str]]:
    report_path = Path(marker["resolution_report_path"])
    report_digest = marker["resolution_report_sha256"]
    try:
        report_bytes = report_path.read_bytes()
        report = json.loads(report_bytes.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RecoveryRefusedError("workspace resolution report is unreadable") from error
    if (
        _workspace_normalized(report_path) != _workspace_normalized(layout.report)
        or not _is_sha256(report_digest)
        or _sha256(report_bytes) != report_digest
        or not isinstance(report, dict)
        or report.get("format") != _WORKSPACE_REPORT_FORMAT
        or type(report.get("version")) is not int
        or report.get("version") != 1
        or report.get("txid") != marker["txid"]
        or report.get("paths") != marker["paths"]
        or report.get("commit_artifact") != marker["commit_artifact"]
        or "operation_evidence_sha256" not in report
        or report.get("operation_evidence_sha256") != marker["operation_evidence_sha256"]
        or not isinstance(report.get("resolved_at"), str)
        or not report["resolved_at"]
    ):
        raise RecoveryRefusedError("workspace resolution report is invalid")
    try:
        outcome = CommitOutcome(report.get("outcome"))
    except (TypeError, ValueError) as error:
        raise RecoveryRefusedError("workspace resolution report outcome is invalid") from error
    if outcome not in {CommitOutcome.NOT_COMMITTED, CommitOutcome.COMMITTED_VERIFIED}:
        raise RecoveryRefusedError("workspace resolution report outcome is invalid")
    desired = "candidate" if outcome is CommitOutcome.COMMITTED_VERIFIED else "original"
    observed = report.get("observed")
    expected = {name: marker["artifacts"][name][f"{desired}_sha256"] for name in _WORKSPACE_NAMES}
    if (
        not isinstance(observed, dict)
        or set(observed) != set(_WORKSPACE_NAMES)
        or any(not _is_sha256(value) for value in observed.values())
        or observed != expected
        or marker["content_outcome"] != outcome.value
    ):
        raise RecoveryRefusedError("workspace resolution report vector is invalid")
    return outcome, desired, expected


def verify_workspace_resolution(
    paths: WorkspacePaths,
    *,
    transaction_id: str,
    operation: str,
    original: WorkspaceDigestVector,
    candidate: WorkspaceDigestVector,
    operation_evidence_sha256: str | None = None,
) -> WorkspaceResolutionProof:
    """Read-only proof that one exact transaction durably committed its candidate vector."""
    if not transaction_id or not operation:
        raise RecoveryRefusedError("workspace resolution identity is invalid")
    _validate_digest_vector(original, "original")
    _validate_digest_vector(candidate, "candidate")
    if operation_evidence_sha256 is not None and not _is_sha256(operation_evidence_sha256):
        raise RecoveryRefusedError("workspace operation evidence digest is invalid")
    layout = _workspace_layout(paths, transaction_id)
    try:
        coordinator_before = layout.coordinator.read_bytes()
    except FileNotFoundError as error:
        raise RecoveryRefusedError("workspace coordinator is missing") from error
    marker = _workspace_json(layout.coordinator)
    if marker is None:
        raise RecoveryRefusedError("workspace coordinator is missing")
    _validate_workspace_marker(marker, layout)
    if (
        marker["state"] != "idle"
        or marker["txid"] != transaction_id
        or marker.get("operation") != operation
        or marker["content_outcome"] != CommitOutcome.COMMITTED_VERIFIED.value
        or marker["operation_evidence_sha256"] != operation_evidence_sha256
    ):
        raise RecoveryRefusedError("workspace resolution identity or outcome does not match")
    if (
        _marker_digest_vector(marker, "original_sha256") != original
        or _marker_digest_vector(marker, "candidate_sha256") != candidate
    ):
        raise RecoveryRefusedError("workspace resolution digest vectors do not match")
    try:
        report_before = layout.report.read_bytes()
    except FileNotFoundError as error:
        raise RecoveryRefusedError("workspace resolution report is missing") from error
    outcome, desired, report_observed = _read_workspace_resolution_report(layout, marker)
    if outcome is not CommitOutcome.COMMITTED_VERIFIED or desired != "candidate":
        raise RecoveryRefusedError("workspace resolution is not a verified commit")
    observed = _prove_workspace_vector(layout, marker, desired)
    if _digest_vector(report_observed) != candidate or _digest_vector(observed) != candidate:
        raise RecoveryRefusedError("workspace resolution current vector does not match")
    try:
        coordinator_after = layout.coordinator.read_bytes()
        report_after = layout.report.read_bytes()
    except FileNotFoundError as error:
        raise RecoveryRefusedError("workspace resolution evidence disappeared") from error
    if coordinator_after != coordinator_before or report_after != report_before:
        raise UnstableWorkspaceError("workspace resolution evidence changed while reading")
    observed_vector = _digest_vector(_prove_workspace_vector(layout, marker, desired))
    if observed_vector != candidate:
        raise RecoveryRefusedError("workspace resolution current vector changed")
    return WorkspaceResolutionProof(
        transaction_id,
        operation,
        outcome,
        original,
        candidate,
        observed_vector,
        operation_evidence_sha256,
    )


def _workspace_resolution_report(
    layout: _WorkspaceLayout,
    marker: Mapping[str, Any],
    outcome: CommitOutcome,
    observed: Mapping[str, str],
) -> bytes:
    return _json_bytes(
        {
            "format": _WORKSPACE_REPORT_FORMAT,
            "version": 1,
            "txid": marker["txid"],
            "paths": marker["paths"],
            "commit_artifact": marker["commit_artifact"],
            "operation_evidence_sha256": marker["operation_evidence_sha256"],
            "outcome": outcome.value,
            "observed": dict(observed),
            "resolved_at": _utc_now(),
        }
    )


def _complete_workspace_resolution(
    layout: _WorkspaceLayout,
    marker: dict[str, Any],
    outcome: CommitOutcome,
    observed: dict[str, str],
    replaced: set[str],
    fault_hook: FaultHook,
) -> WorkspaceCommitResult:
    desired = "candidate" if outcome is CommitOutcome.COMMITTED_VERIFIED else "original"
    observed = _prove_workspace_vector(layout, marker, desired)
    for name, digest in observed.items():
        marker["artifacts"][name]["observed_sha256"] = digest
    report_bytes = _workspace_resolution_report(layout, marker, outcome, observed)
    _atomic_write(layout.report, report_bytes, fault_hook, "workspace_resolution")
    observed = _prove_workspace_vector(layout, marker, desired)
    marker["resolution_report_path"] = str(layout.report)
    marker["resolution_report_sha256"] = _sha256(report_bytes)
    marker["content_outcome"] = outcome.value
    marker["state"] = "cleanup_pending"
    marker["cleanup_allowlist"] = [
        value
        for name in _WORKSPACE_NAMES
        for value in (
            marker["artifacts"][name]["candidate_path"],
            marker["artifacts"][name]["shadow_path"],
        )
        if value is not None
    ]
    _write_workspace_marker(layout, marker, fault_hook, "workspace_cleanup_pending")
    try:
        _cleanup_workspace_artifacts(layout, marker, fault_hook)
        observed = _prove_workspace_vector(layout, marker, desired)
        marker["state"] = "idle"
        marker["cleanup_allowlist"] = []
        _write_workspace_marker(layout, marker, fault_hook, "workspace_idle")
        observed = _prove_workspace_vector(layout, marker, desired)
    except Exception as error:
        observed = _prove_workspace_vector(layout, marker, desired)
        return WorkspaceCommitResult(
            outcome,
            _workspace_evidence(layout, marker, observed, replaced),
            diagnostics=(f"workspace_cleanup_pending: {error}",),
            cleanup_pending=True,
        )
    return WorkspaceCommitResult(outcome, _workspace_evidence(layout, marker, observed, replaced))


def _cleanup_workspace_artifacts(
    layout: _WorkspaceLayout, marker: Mapping[str, Any], fault_hook: FaultHook
) -> None:
    allowed = {str(path): path for path in (*layout.candidates.values(), *layout.shadows.values())}
    for raw_path in marker["cleanup_allowlist"]:
        path = allowed.get(raw_path)
        if path is None:
            raise RecoveryRefusedError("workspace cleanup path is not allowlisted")
        fault_hook(f"workspace:before_cleanup:{path.name}")
        _remove_file(path)
        _fsync_directory(path.parent)


class WorkspaceTransaction:
    """Exclusive raw three-file logical transaction."""

    def __init__(
        self,
        paths: WorkspacePaths,
        operation: str,
        *,
        lock_backend: LockBackend | None = None,
        fault_hook: FaultHook = _noop_fault_hook,
    ) -> None:
        self.paths = paths
        self.operation = operation
        self._nonce = uuid.uuid4().hex
        self._layout = _workspace_layout(paths, self._nonce)
        for path in _workspace_path_map(self._layout.paths).values():
            if not path.is_file():
                raise StorageError(f"required workspace artifact does not exist: {path}")
        self._backend = lock_backend or PlatformLockBackend()
        self._fault_hook = fault_hook
        self._locks: list[LockHandle] = []
        self._snapshot: WorkspaceSnapshot | None = None
        self._commit_attempted = False

    @property
    def snapshot(self) -> WorkspaceSnapshot:
        if self._snapshot is None:
            raise StorageError("workspace transaction is not open")
        return self._snapshot

    @property
    def transaction_id(self) -> str:
        """Return the stable identifier written into this transaction's evidence."""
        return self._nonce

    def __enter__(self) -> Self:
        self._locks = _acquire_workspace_locks(self._layout, self._backend)
        try:
            status = inspect_workspace_recovery(self._layout.paths)
            if status.state is not WorkspaceRecoveryState.CLEAN:
                raise RecoveryRequiredError("unresolved workspace coordinator exists")
            self._snapshot = read_workspace_snapshot(self._layout.paths, attempts=1)
            return self
        except BaseException:
            self.close()
            raise

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_value: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        _close_workspace_locks(self._locks)
        self._locks = []

    def commit(
        self,
        candidate: WorkspaceCandidate,
        *,
        operation_evidence_sha256: str | None = None,
    ) -> WorkspaceCommitResult:
        """Commit one caller-validated raw vector."""
        if self._commit_attempted:
            raise StorageError("a workspace transaction permits one commit attempt")
        self._commit_attempted = True
        if operation_evidence_sha256 is not None and not _is_sha256(operation_evidence_sha256):
            raise StorageError("workspace operation evidence digest is invalid")
        snapshot = self.snapshot
        candidate_data = {name: candidate.by_name(name) for name in _WORKSPACE_NAMES}
        dirty = {
            name: candidate_data[name] != snapshot.by_name(name).data for name in _WORKSPACE_NAMES
        }
        observed = {item.name: item.sha256 for item in snapshot.items()}
        if not any(dirty.values()):
            self._prove_workspace_original()
            paths = _workspace_path_map(self._layout.paths)
            return WorkspaceCommitResult(
                CommitOutcome.NOT_COMMITTED,
                tuple(
                    ArtifactCommitEvidence(
                        name=item.name,
                        path=str(paths[item.name]),
                        original_sha256=item.sha256,
                        candidate_sha256=item.sha256,
                        observed_sha256=item.sha256,
                        dirty=False,
                        replaced=False,
                    )
                    for item in snapshot.items()
                ),
                diagnostics=("no_change",),
            )
        marker = self._marker(candidate_data, dirty, operation_evidence_sha256)
        staged: list[Path] = []
        try:
            for item in snapshot.items():
                if not dirty[item.name]:
                    continue
                candidate_path = self._layout.candidates[item.name]
                shadow_path = self._layout.shadows[item.name]
                _write_workspace_artifact(candidate_path, candidate_data[item.name], item.metadata)
                staged.append(candidate_path)
                _write_workspace_artifact(shadow_path, item.data, item.metadata)
                staged.append(shadow_path)
        except BaseException:
            for path in staged:
                _remove_file(path)
            self._prove_workspace_original()
            raise

        try:
            marker["state"] = "prepared"
            _write_workspace_marker(self._layout, marker, self._fault_hook, "workspace_prepared")
            self._prove_workspace_original()
            marker["state"] = "installing"
            _write_workspace_marker(self._layout, marker, self._fault_hook, "workspace_installing")
            observed, replaced = _repair_workspace_vector(
                self._layout, marker, "candidate", self._fault_hook
            )
            return _complete_workspace_resolution(
                self._layout,
                marker,
                CommitOutcome.COMMITTED_VERIFIED,
                observed,
                replaced,
                self._fault_hook,
            )
        except BaseException as error:
            result = self._classify_and_resolve(marker, error)
            if not isinstance(error, Exception):
                raise
            return result

    def _marker(
        self,
        candidate_data: Mapping[str, bytes],
        dirty: Mapping[str, bool],
        operation_evidence_sha256: str | None,
    ) -> dict[str, Any]:
        path_map = _workspace_path_map(self._layout.paths)
        commit_artifact = next(name for name in reversed(_WORKSPACE_INSTALL_ORDER) if dirty[name])
        return {
            "format": _WORKSPACE_FORMAT,
            "version": 1,
            "txid": self._nonce,
            "state": "prepared",
            "operation": self.operation,
            "operation_evidence_sha256": operation_evidence_sha256,
            "commit_artifact": commit_artifact,
            "paths": {name: str(path) for name, path in path_map.items()},
            "platform": platform.system().lower(),
            "durability": _durability_level(),
            "replacement_order": list(_WORKSPACE_INSTALL_ORDER),
            "artifacts": {
                item.name: {
                    "original_sha256": item.sha256,
                    "candidate_sha256": _sha256(candidate_data[item.name]),
                    "observed_sha256": item.sha256,
                    "dirty": dirty[item.name],
                    "replaced": False,
                    "candidate_path": (
                        str(self._layout.candidates[item.name]) if dirty[item.name] else None
                    ),
                    "shadow_path": (
                        str(self._layout.shadows[item.name]) if dirty[item.name] else None
                    ),
                    "mode": item.metadata.mode,
                    "readonly": item.metadata.readonly,
                }
                for item in self.snapshot.items()
            },
            "resolution_report_path": None,
            "resolution_report_sha256": None,
            "cleanup_allowlist": [],
            "content_outcome": None,
            "created_at": _utc_now(),
            "diagnostics": [],
        }

    def _prove_workspace_original(self) -> None:
        observed = _workspace_observed(self._layout)
        expected = {item.name: item.sha256 for item in self.snapshot.items()}
        if observed != expected:
            raise StaleTargetError("workspace vector changed after snapshot")

    def _classify_and_resolve(
        self, marker: dict[str, Any], error: BaseException
    ) -> WorkspaceCommitResult:
        observed_before = _workspace_observed(self._layout)
        original = {item.name: item.sha256 for item in self.snapshot.items()}
        if not self._layout.coordinator.exists() and observed_before == original:
            cleanup_diagnostics: list[str] = []
            for path in (*self._layout.candidates.values(), *self._layout.shadows.values()):
                try:
                    _remove_file(path)
                except Exception as cleanup_error:
                    cleanup_diagnostics.append(str(cleanup_error))
            return WorkspaceCommitResult(
                CommitOutcome.NOT_COMMITTED,
                _workspace_evidence(
                    self._layout, marker, observed_before, _workspace_replaced(marker)
                ),
                diagnostics=(f"{type(error).__name__}: {error}", *cleanup_diagnostics),
            )
        try:
            observed = observed_before
            commit_name = marker["commit_artifact"]
            commit_item = marker["artifacts"][commit_name]
            if observed[commit_name] == commit_item["original_sha256"]:
                desired = "original"
                outcome = CommitOutcome.NOT_COMMITTED
                marker["state"] = "resolving_rollback"
            elif observed[commit_name] == commit_item["candidate_sha256"]:
                desired = "candidate"
                outcome = CommitOutcome.COMMITTED_VERIFIED
                marker["state"] = "resolving_forward"
            else:
                raise RecoveryRefusedError("workspace logical commit digest is unknown")
            _write_workspace_marker(
                self._layout, marker, self._fault_hook, f"workspace_{marker['state']}"
            )
            observed, replaced = _repair_workspace_vector(
                self._layout, marker, desired, self._fault_hook
            )
            return _complete_workspace_resolution(
                self._layout, marker, outcome, observed, replaced, self._fault_hook
            )
        except BaseException as recovery_error:
            marker["state"] = "recovery_required"
            marker["diagnostics"] = _diagnostics(
                (f"{type(error).__name__}: {error}", f"recovery: {recovery_error}")
            )
            try:
                _write_workspace_marker(
                    self._layout, marker, self._fault_hook, "workspace_recovery_required"
                )
            except BaseException as marker_error:
                if not isinstance(marker_error, Exception):
                    raise
            observed_values: dict[str, str | None]
            try:
                observed_values = {
                    name: digest for name, digest in _workspace_observed(self._layout).items()
                }
            except Exception:
                observed_values = {name: None for name in _WORKSPACE_NAMES}
            result = WorkspaceCommitResult(
                CommitOutcome.COMMITTED_UNVERIFIED,
                _workspace_evidence(
                    self._layout, marker, observed_values, _workspace_replaced(marker)
                ),
                diagnostics=(f"{type(error).__name__}: {error}", f"recovery: {recovery_error}"),
            )
            if not isinstance(recovery_error, Exception):
                raise recovery_error
            return result


def recover_workspace(
    paths: WorkspacePaths,
    *,
    lock_backend: LockBackend | None = None,
    fault_hook: FaultHook = _noop_fault_hook,
) -> WorkspaceRecoveryResult:
    """Resolve or finish cleanup for the sole workspace coordinator."""
    placeholder = _workspace_layout(paths, "inspection-placeholder")
    backend = lock_backend or PlatformLockBackend()
    initial = _workspace_json(placeholder.coordinator)
    if initial is None:
        layout = placeholder
    else:
        txid = initial.get("txid")
        if not isinstance(txid, str) or not txid:
            raise RecoveryRefusedError("workspace coordinator txid is invalid")
        layout = _workspace_layout(paths, txid)
    locks = _acquire_workspace_locks(layout, backend)
    try:
        marker = _workspace_json(layout.coordinator)
        if initial is None and marker is not None:
            # A writer completed between the optimistic coordinator read and lock
            # acquisition. Release first so its nonce-specific reserved paths can
            # be validated before the retry opens any sidecar.
            _close_workspace_locks(locks)
            locks = []
            return recover_workspace(paths, lock_backend=backend, fault_hook=fault_hook)
        if marker is None:
            return WorkspaceRecoveryResult("clean", _workspace_observed(layout))
        for path in _workspace_path_map(layout.paths).values():
            if not path.is_file():
                raise RecoveryRefusedError(f"required workspace artifact does not exist: {path}")
        _validate_workspace_marker(marker, layout)
        state = marker["state"]
        if state == "idle":
            return WorkspaceRecoveryResult("clean", _workspace_observed(layout))
        if state == "cleanup_pending":
            outcome, desired, report_observed = _read_workspace_resolution_report(layout, marker)
            observed = _prove_workspace_vector(layout, marker, desired)
            if observed != report_observed:
                raise RecoveryRefusedError("workspace resolution report proof changed")
            _cleanup_workspace_artifacts(layout, marker, fault_hook)
            observed = _prove_workspace_vector(layout, marker, desired)
            marker["cleanup_allowlist"] = []
            marker["state"] = "idle"
            _write_workspace_marker(layout, marker, fault_hook, "workspace_idle")
            observed = _prove_workspace_vector(layout, marker, desired)
            return WorkspaceRecoveryResult(outcome.value, observed)
        observed = _workspace_observed(layout)
        commit_name = marker["commit_artifact"]
        commit_item = marker["artifacts"][commit_name]
        if observed[commit_name] == commit_item["original_sha256"]:
            desired = "original"
            outcome = CommitOutcome.NOT_COMMITTED
            marker["state"] = "resolving_rollback"
        elif observed[commit_name] == commit_item["candidate_sha256"]:
            desired = "candidate"
            outcome = CommitOutcome.COMMITTED_VERIFIED
            marker["state"] = "resolving_forward"
        else:
            marker["state"] = "recovery_required"
            _write_workspace_marker(layout, marker, fault_hook, "workspace_recovery_required")
            raise RecoveryRefusedError("workspace logical commit digest is unknown")
        _write_workspace_marker(layout, marker, fault_hook, f"workspace_{marker['state']}")
        observed, replaced = _repair_workspace_vector(layout, marker, desired, fault_hook)
        result = _complete_workspace_resolution(
            layout, marker, outcome, observed, replaced, fault_hook
        )
        return WorkspaceRecoveryResult(
            result.outcome.value,
            {item.name: item.observed_sha256 or "" for item in result.artifacts},
            result.diagnostics,
        )
    finally:
        _close_workspace_locks(locks)
