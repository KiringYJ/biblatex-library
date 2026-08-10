from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path

import pytest

from biblio.results import CommitOutcome
from biblio.storage import (
    BibliographyCodec,
    LockUnavailableError,
    PlatformLockBackend,
    RecoveryRefusedError,
    StorageError,
    WorkspaceCandidate,
    WorkspaceDigestVector,
    WorkspacePaths,
    WorkspaceRecoveryState,
    WorkspaceResolutionProof,
    WorkspaceTransaction,
    inspect_workspace_recovery,
    read_workspace_snapshot,
    recover_workspace,
    verify_workspace_resolution,
)


def _workspace(tmp_path: Path) -> WorkspacePaths:
    paths = WorkspacePaths(
        bibliography=tmp_path / "library.bib",
        identifiers=tmp_path / "identifier_collection.json",
        add_order=tmp_path / "add_order.json",
    )
    paths.bibliography.write_bytes(b"@article{old, title={Old}}\n")
    paths.identifiers.write_bytes(b'{"old":{"identifiers":{"doi":"10.1/old"}}}\n')
    paths.add_order.write_bytes(b'["old"]\n')
    return paths


def _candidate(paths: WorkspacePaths, *, bibliography: bytes | None = None) -> WorkspaceCandidate:
    return WorkspaceCandidate(
        bibliography=bibliography or b"@article{new, title={New}}\n",
        identifiers=b'{"new":{"identifiers":{"doi":"10.1/new"}}}\n',
        add_order=b'["new"]\n',
    )


def _bytes(paths: WorkspacePaths) -> dict[str, bytes]:
    return {
        "bibliography": paths.bibliography.read_bytes(),
        "identifiers": paths.identifiers.read_bytes(),
        "add_order": paths.add_order.read_bytes(),
    }


def _coordinator(paths: WorkspacePaths) -> Path:
    return paths.bibliography.parent / f".{paths.bibliography.name}.biblio-workspace.json"


def _report(paths: WorkspacePaths) -> Path:
    return paths.bibliography.parent / f".{paths.bibliography.name}.biblio-workspace-resolved.json"


def _snapshot_digests(paths: WorkspacePaths) -> WorkspaceDigestVector:
    snapshot = read_workspace_snapshot(paths)
    return WorkspaceDigestVector(*(item.sha256 for item in snapshot.items()))


def _candidate_digests(candidate: WorkspaceCandidate) -> WorkspaceDigestVector:
    return WorkspaceDigestVector(
        *(hashlib.sha256(candidate.by_name(name)).hexdigest() for name in _WORKSPACE_NAMES)
    )


_WORKSPACE_NAMES = ("bibliography", "identifiers", "add_order")


def _commit_for_proof(
    paths: WorkspacePaths,
) -> tuple[str, WorkspaceDigestVector, WorkspaceDigestVector]:
    original = _snapshot_digests(paths)
    candidate = _candidate(paths)
    candidate_digests = _candidate_digests(candidate)
    with WorkspaceTransaction(paths, "add") as transaction:
        transaction_id = transaction.transaction_id
        assert transaction.transaction_id == transaction_id
        result = transaction.commit(candidate)
    assert result.outcome is CommitOutcome.COMMITTED_VERIFIED
    assert not result.cleanup_pending
    return transaction_id, original, candidate_digests


def test_bibliography_codec_is_value_opaque_and_canonicalizes_bytes() -> None:
    source = (
        b"\xef\xbb\xbf@comment{hello}\r\n"
        b"@article{Key,\r\n DOI = {HTTPS://DOI.ORG/10.X/Y},\n"
        b" title={{A {B}}}\r\n}\r\n\r\n"
    )

    rendered = BibliographyCodec.serialize(BibliographyCodec.parse_bytes(source))

    assert not rendered.startswith(b"\xef\xbb\xbf")
    assert b"\r" not in rendered
    assert rendered.endswith(b"\n") and not rendered.endswith(b"\n\n")
    entry = BibliographyCodec.parse_bytes(rendered).resolve("Key")
    fields = {field.key: field.value for field in entry.fields}
    assert fields["DOI"] == "HTTPS://DOI.ORG/10.X/Y"
    assert fields["title"] == "{A {B}}"


def test_platform_lock_backend_contends_and_releases(tmp_path: Path) -> None:
    lock_path = tmp_path / ".workspace.lock"
    backend = PlatformLockBackend()
    first = backend.acquire(lock_path)
    try:
        with pytest.raises(LockUnavailableError):
            backend.acquire(lock_path)
    finally:
        first.close()

    released = backend.acquire(lock_path)
    released.close()


def test_verified_workspace_resolution_proof_is_side_effect_free(tmp_path: Path) -> None:
    paths = _workspace(tmp_path)
    transaction_id, original, candidate = _commit_for_proof(paths)
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir()}

    proof = verify_workspace_resolution(
        paths,
        transaction_id=transaction_id,
        operation="add",
        original=original,
        candidate=candidate,
    )

    assert proof == WorkspaceResolutionProof(
        transaction_id,
        "add",
        CommitOutcome.COMMITTED_VERIFIED,
        original,
        candidate,
        candidate,
    )
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == before


def test_operation_evidence_digest_is_durable_and_exact(tmp_path: Path) -> None:
    paths = _workspace(tmp_path)
    original = _snapshot_digests(paths)
    candidate_bytes = _candidate(paths)
    candidate = _candidate_digests(candidate_bytes)
    evidence_digest = "a" * 64
    with WorkspaceTransaction(paths, "add") as transaction:
        transaction_id = transaction.transaction_id
        result = transaction.commit(candidate_bytes, operation_evidence_sha256=evidence_digest)

    assert result.outcome is CommitOutcome.COMMITTED_VERIFIED
    proof = verify_workspace_resolution(
        paths,
        transaction_id=transaction_id,
        operation="add",
        original=original,
        candidate=candidate,
        operation_evidence_sha256=evidence_digest,
    )
    assert proof.operation_evidence_sha256 == evidence_digest
    assert (
        json.loads(_coordinator(paths).read_text(encoding="utf-8"))["operation_evidence_sha256"]
        == evidence_digest
    )
    assert (
        json.loads(_report(paths).read_text(encoding="utf-8"))["operation_evidence_sha256"]
        == evidence_digest
    )

    with pytest.raises(RecoveryRefusedError, match="identity or outcome"):
        verify_workspace_resolution(
            paths,
            transaction_id=transaction_id,
            operation="add",
            original=original,
            candidate=candidate,
            operation_evidence_sha256="b" * 64,
        )

    report_path = _report(paths)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["operation_evidence_sha256"] = "b" * 64
    report_bytes = (
        json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    ).encode()
    report_path.write_bytes(report_bytes)
    coordinator_path = _coordinator(paths)
    coordinator = json.loads(coordinator_path.read_text(encoding="utf-8"))
    coordinator["resolution_report_sha256"] = hashlib.sha256(report_bytes).hexdigest()
    coordinator_path.write_text(
        json.dumps(coordinator, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(RecoveryRefusedError, match="resolution report"):
        verify_workspace_resolution(
            paths,
            transaction_id=transaction_id,
            operation="add",
            original=original,
            candidate=candidate,
            operation_evidence_sha256=evidence_digest,
        )


def test_invalid_operation_evidence_digest_creates_no_transaction_marker(
    tmp_path: Path,
) -> None:
    paths = _workspace(tmp_path)
    with WorkspaceTransaction(paths, "add") as transaction:
        with pytest.raises(StorageError, match="operation evidence"):
            transaction.commit(_candidate(paths), operation_evidence_sha256="invalid")

    assert not _coordinator(paths).exists()


@pytest.mark.parametrize("mismatch", ["transaction_id", "operation", "original", "candidate"])
def test_verified_workspace_resolution_rejects_identity_or_vector_mismatch(
    tmp_path: Path, mismatch: str
) -> None:
    paths = _workspace(tmp_path)
    transaction_id, original, candidate = _commit_for_proof(paths)
    bad_vector = WorkspaceDigestVector("0" * 64, "0" * 64, "0" * 64)

    with pytest.raises(RecoveryRefusedError):
        verify_workspace_resolution(
            paths,
            transaction_id="wrong" if mismatch == "transaction_id" else transaction_id,
            operation="wrong" if mismatch == "operation" else "add",
            original=bad_vector if mismatch == "original" else original,
            candidate=bad_vector if mismatch == "candidate" else candidate,
        )


def test_verified_workspace_resolution_requires_idle_state(tmp_path: Path) -> None:
    paths = _workspace(tmp_path)
    original = _snapshot_digests(paths)
    candidate = _candidate(paths)

    def fail(phase: str) -> None:
        if phase.startswith("workspace:before_cleanup:"):
            raise OSError("injected cleanup failure")

    with WorkspaceTransaction(paths, "add", fault_hook=fail) as transaction:
        transaction_id = transaction.transaction_id
        result = transaction.commit(candidate)

    assert result.cleanup_pending
    with pytest.raises(RecoveryRefusedError, match="identity or outcome"):
        verify_workspace_resolution(
            paths,
            transaction_id=transaction_id,
            operation="add",
            original=original,
            candidate=_candidate_digests(candidate),
        )


@pytest.mark.parametrize("damage", ["missing", "tampered"])
def test_verified_workspace_resolution_requires_valid_report(tmp_path: Path, damage: str) -> None:
    paths = _workspace(tmp_path)
    transaction_id, original, candidate = _commit_for_proof(paths)
    if damage == "missing":
        _report(paths).unlink()
    else:
        _report(paths).write_bytes(b"{}\n")

    with pytest.raises(RecoveryRefusedError, match="resolution report"):
        verify_workspace_resolution(
            paths,
            transaction_id=transaction_id,
            operation="add",
            original=original,
            candidate=candidate,
        )


def test_verified_workspace_resolution_rejects_current_digest_drift(tmp_path: Path) -> None:
    paths = _workspace(tmp_path)
    transaction_id, original, candidate = _commit_for_proof(paths)
    paths.identifiers.write_bytes(b"third-party\n")

    with pytest.raises(RecoveryRefusedError, match="third digest"):
        verify_workspace_resolution(
            paths,
            transaction_id=transaction_id,
            operation="add",
            original=original,
            candidate=candidate,
        )


def test_verified_workspace_resolution_rejects_current_metadata_drift(tmp_path: Path) -> None:
    paths = _workspace(tmp_path)
    transaction_id, original, candidate = _commit_for_proof(paths)
    original_mode = stat.S_IMODE(paths.identifiers.stat().st_mode)
    os.chmod(paths.identifiers, original_mode ^ stat.S_IWUSR)
    try:
        with pytest.raises(StorageError, match="changed during replacement"):
            verify_workspace_resolution(
                paths,
                transaction_id=transaction_id,
                operation="add",
                original=original,
                candidate=candidate,
            )
    finally:
        os.chmod(paths.identifiers, original_mode)


def test_workspace_commit_replaces_complete_vector_and_keeps_locks(tmp_path: Path) -> None:
    paths = _workspace(tmp_path)
    candidate = _candidate(paths)

    with WorkspaceTransaction(paths, "test") as transaction:
        result = transaction.commit(candidate)
        assert all(
            (path.parent / f".{path.name}.biblio.lock").exists()
            for path in (paths.bibliography, paths.identifiers, paths.add_order)
        )

    assert result.outcome is CommitOutcome.COMMITTED_VERIFIED
    assert not result.cleanup_pending
    assert _bytes(paths) == {
        "bibliography": candidate.bibliography,
        "identifiers": candidate.identifiers,
        "add_order": candidate.add_order,
    }
    assert json.loads(_coordinator(paths).read_text())["state"] == "idle"
    assert {item.name for item in result.artifacts} == {
        "bibliography",
        "identifiers",
        "add_order",
    }


def test_workspace_noop_proves_vector_without_coordinator(tmp_path: Path) -> None:
    paths = _workspace(tmp_path)
    snapshot = read_workspace_snapshot(paths)
    candidate = WorkspaceCandidate(*(item.data for item in snapshot.items()))

    with WorkspaceTransaction(paths, "test") as transaction:
        result = transaction.commit(candidate)

    assert result.outcome is CommitOutcome.NOT_COMMITTED
    assert not _coordinator(paths).exists()


def test_identifier_only_commit_uses_identifier_as_logical_commit_artifact(
    tmp_path: Path,
) -> None:
    paths = _workspace(tmp_path)
    candidate = WorkspaceCandidate(
        paths.bibliography.read_bytes(), b"{}\n", paths.add_order.read_bytes()
    )

    with WorkspaceTransaction(paths, "test") as transaction:
        result = transaction.commit(candidate)

    assert result.outcome is CommitOutcome.COMMITTED_VERIFIED
    assert _bytes(paths)["identifiers"] == b"{}\n"
    coordinator = json.loads(_coordinator(paths).read_text(encoding="utf-8"))
    report = json.loads(_report(paths).read_text(encoding="utf-8"))
    assert coordinator["commit_artifact"] == "identifiers"
    assert report["commit_artifact"] == "identifiers"


def test_identifier_only_failure_before_commit_point_rolls_back(tmp_path: Path) -> None:
    paths = _workspace(tmp_path)
    original = paths.identifiers.read_bytes()

    def fail(phase: str) -> None:
        if phase == "workspace:before_replace:identifiers:candidate":
            raise OSError("injected")

    candidate = WorkspaceCandidate(
        paths.bibliography.read_bytes(), b"{}\n", paths.add_order.read_bytes()
    )
    with WorkspaceTransaction(paths, "test", fault_hook=fail) as transaction:
        result = transaction.commit(candidate)

    assert result.outcome is CommitOutcome.NOT_COMMITTED
    assert paths.identifiers.read_bytes() == original


def test_identifier_only_recovery_classifies_crossed_commit_point(tmp_path: Path) -> None:
    paths = _workspace(tmp_path)
    candidate = WorkspaceCandidate(
        paths.bibliography.read_bytes(), b"{}\n", paths.add_order.read_bytes()
    )

    def fail(phase: str) -> None:
        if phase == "workspace_resolution:before_file_fsync":
            raise OSError("injected")

    with WorkspaceTransaction(paths, "test", fault_hook=fail) as transaction:
        result = transaction.commit(candidate)

    assert result.outcome is CommitOutcome.COMMITTED_UNVERIFIED
    assert inspect_workspace_recovery(paths).state is WorkspaceRecoveryState.REQUIRED
    recovered = recover_workspace(paths)
    assert recovered.resolution == CommitOutcome.COMMITTED_VERIFIED.value
    assert paths.identifiers.read_bytes() == b"{}\n"


def test_side_effect_free_workspace_read_creates_nothing(tmp_path: Path) -> None:
    paths = _workspace(tmp_path)
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir()}

    snapshot = read_workspace_snapshot(paths)

    assert snapshot.bibliography.data == paths.bibliography.read_bytes()
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == before


def test_all_workspace_targets_are_required_before_locks(tmp_path: Path) -> None:
    paths = _workspace(tmp_path)
    paths.add_order.unlink()

    with pytest.raises(StorageError, match="does not exist"):
        WorkspaceTransaction(paths, "test")

    assert not list(tmp_path.glob(".*.biblio.lock"))


def test_reserved_path_collision_preserves_all_bytes_and_creates_nothing(tmp_path: Path) -> None:
    bibliography = tmp_path / "library.bib"
    bibliography.write_bytes(b"")
    collision = tmp_path / ".library.bib.biblio.lock"
    collision.write_bytes(b"{}\n")
    add_order = tmp_path / "add_order.json"
    add_order.write_bytes(b"[]\n")
    paths = WorkspacePaths(bibliography, collision, add_order)
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir()}

    with pytest.raises(StorageError, match="collide"):
        WorkspaceTransaction(paths, "test")

    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == before


def test_failure_after_companion_replace_rolls_back_to_original(tmp_path: Path) -> None:
    paths = _workspace(tmp_path)
    original = _bytes(paths)

    def fail(phase: str) -> None:
        if phase == "workspace:after_replace:identifiers:candidate":
            raise OSError("injected")

    with WorkspaceTransaction(paths, "test", fault_hook=fail) as transaction:
        result = transaction.commit(_candidate(paths))

    assert result.outcome is CommitOutcome.NOT_COMMITTED
    assert _bytes(paths) == original
    assert inspect_workspace_recovery(paths).state is WorkspaceRecoveryState.CLEAN


def test_failure_after_bibliography_replace_rolls_forward(tmp_path: Path) -> None:
    paths = _workspace(tmp_path)
    candidate = _candidate(paths)

    def fail(phase: str) -> None:
        if phase == "workspace:after_replace:bibliography:candidate":
            raise OSError("injected")

    with WorkspaceTransaction(paths, "test", fault_hook=fail) as transaction:
        result = transaction.commit(candidate)

    assert result.outcome is CommitOutcome.COMMITTED_VERIFIED
    assert _bytes(paths)["bibliography"] == candidate.bibliography
    assert _bytes(paths)["identifiers"] == candidate.identifiers
    assert all(item.replaced for item in result.artifacts if item.dirty)


def test_final_vector_proof_rejects_third_digest_after_logical_commit(tmp_path: Path) -> None:
    paths = _workspace(tmp_path)

    def corrupt(phase: str) -> None:
        if phase == "workspace:after_replace:bibliography:candidate":
            paths.identifiers.write_bytes(b"third-party\n")

    with WorkspaceTransaction(paths, "test", fault_hook=corrupt) as transaction:
        result = transaction.commit(_candidate(paths))

    assert result.outcome is CommitOutcome.COMMITTED_UNVERIFIED
    assert inspect_workspace_recovery(paths).state is WorkspaceRecoveryState.REQUIRED
    assert paths.identifiers.read_bytes() == b"third-party\n"


def test_final_vector_proof_rejects_metadata_drift(tmp_path: Path) -> None:
    paths = _workspace(tmp_path)
    original_mode = stat.S_IMODE(paths.identifiers.stat().st_mode)
    changed_mode = original_mode ^ stat.S_IWUSR

    def corrupt(phase: str) -> None:
        if phase == "workspace_resolution:before_replace":
            os.chmod(paths.identifiers, changed_mode)

    try:
        with WorkspaceTransaction(paths, "test", fault_hook=corrupt) as transaction:
            result = transaction.commit(_candidate(paths))
    finally:
        os.chmod(paths.identifiers, original_mode)

    assert result.outcome is CommitOutcome.COMMITTED_UNVERIFIED
    assert inspect_workspace_recovery(paths).state is WorkspaceRecoveryState.REQUIRED


def test_failed_automatic_rollback_is_recoverable_after_restart(tmp_path: Path) -> None:
    paths = _workspace(tmp_path)
    original = _bytes(paths)

    def fail(phase: str) -> None:
        if phase in {
            "workspace:after_replace:identifiers:candidate",
            "workspace:before_replace:identifiers:original",
        }:
            raise OSError("injected")

    with WorkspaceTransaction(paths, "test", fault_hook=fail) as transaction:
        result = transaction.commit(_candidate(paths))

    assert result.outcome is CommitOutcome.COMMITTED_UNVERIFIED
    assert inspect_workspace_recovery(paths).state is WorkspaceRecoveryState.REQUIRED
    recovered = recover_workspace(paths)
    assert recovered.resolution == CommitOutcome.NOT_COMMITTED.value
    assert _bytes(paths) == original
    assert inspect_workspace_recovery(paths).state is WorkspaceRecoveryState.CLEAN


def test_third_digest_stays_blocked(tmp_path: Path) -> None:
    paths = _workspace(tmp_path)

    def corrupt(phase: str) -> None:
        if phase == "workspace:after_replace:identifiers:candidate":
            paths.identifiers.write_bytes(b"third-party\n")
            raise OSError("injected")

    with WorkspaceTransaction(paths, "test", fault_hook=corrupt) as transaction:
        result = transaction.commit(_candidate(paths))

    assert result.outcome is CommitOutcome.COMMITTED_UNVERIFIED
    with pytest.raises(RecoveryRefusedError, match="third digest"):
        recover_workspace(paths)
    assert paths.identifiers.read_bytes() == b"third-party\n"


def test_cleanup_pending_preserves_content_outcome_and_restart_finishes(tmp_path: Path) -> None:
    paths = _workspace(tmp_path)
    candidate = _candidate(paths)

    def fail(phase: str) -> None:
        if phase.startswith("workspace:before_cleanup:"):
            raise OSError("injected cleanup failure")

    with WorkspaceTransaction(paths, "test", fault_hook=fail) as transaction:
        result = transaction.commit(candidate)

    assert result.outcome is CommitOutcome.COMMITTED_VERIFIED
    assert result.cleanup_pending
    assert inspect_workspace_recovery(paths).state is WorkspaceRecoveryState.CLEANUP_PENDING
    recovered = recover_workspace(paths)
    assert recovered.resolution == CommitOutcome.COMMITTED_VERIFIED.value
    assert inspect_workspace_recovery(paths).state is WorkspaceRecoveryState.CLEAN


def test_cleanup_pending_recovery_rejects_target_drift(tmp_path: Path) -> None:
    paths = _workspace(tmp_path)

    def fail(phase: str) -> None:
        if phase.startswith("workspace:before_cleanup:"):
            raise OSError("injected cleanup failure")

    with WorkspaceTransaction(paths, "test", fault_hook=fail) as transaction:
        result = transaction.commit(_candidate(paths))

    assert result.cleanup_pending
    paths.identifiers.write_bytes(b"third-party\n")
    with pytest.raises(RecoveryRefusedError, match="third digest"):
        recover_workspace(paths)
    assert inspect_workspace_recovery(paths).state is WorkspaceRecoveryState.CLEANUP_PENDING
    assert paths.identifiers.read_bytes() == b"third-party\n"


def test_cleanup_pending_recovery_validates_resolution_report_contract(
    tmp_path: Path,
) -> None:
    paths = _workspace(tmp_path)

    def fail(phase: str) -> None:
        if phase.startswith("workspace:before_cleanup:"):
            raise OSError("injected cleanup failure")

    with WorkspaceTransaction(paths, "test", fault_hook=fail) as transaction:
        result = transaction.commit(_candidate(paths))

    assert result.cleanup_pending
    coordinator_path = _coordinator(paths)
    coordinator = json.loads(coordinator_path.read_text(encoding="utf-8"))
    report_path = Path(coordinator["resolution_report_path"])
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["observed"]["identifiers"] = coordinator["artifacts"]["identifiers"]["original_sha256"]
    report_bytes = (
        json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    ).encode()
    report_path.write_bytes(report_bytes)
    coordinator["resolution_report_sha256"] = hashlib.sha256(report_bytes).hexdigest()
    coordinator_path.write_text(
        json.dumps(coordinator, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(RecoveryRefusedError, match="resolution report"):
        recover_workspace(paths)
    assert inspect_workspace_recovery(paths).state is WorkspaceRecoveryState.CLEANUP_PENDING


def test_recovery_rejects_tampered_earlier_commit_artifact(tmp_path: Path) -> None:
    paths = _workspace(tmp_path)

    def fail(phase: str) -> None:
        if phase in {
            "workspace:after_replace:identifiers:candidate",
            "workspace:before_replace:identifiers:original",
        }:
            raise OSError("injected")

    with WorkspaceTransaction(paths, "test", fault_hook=fail) as transaction:
        result = transaction.commit(_candidate(paths))

    assert result.outcome is CommitOutcome.COMMITTED_UNVERIFIED
    coordinator_path = _coordinator(paths)
    marker = json.loads(coordinator_path.read_text(encoding="utf-8"))
    assert marker["commit_artifact"] == "bibliography"
    marker["commit_artifact"] = "identifiers"
    coordinator_path.write_text(
        json.dumps(marker, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(RecoveryRefusedError, match="last dirty artifact"):
        recover_workspace(paths)
    assert paths.bibliography.read_bytes() != _candidate(paths).bibliography


def test_prepared_marker_exists_before_first_target_replace(tmp_path: Path) -> None:
    paths = _workspace(tmp_path)
    observed_states: list[str] = []

    def inspect(phase: str) -> None:
        if phase == "workspace:before_replace:identifiers:candidate":
            observed_states.append(json.loads(_coordinator(paths).read_text())["state"])

    with WorkspaceTransaction(paths, "test", fault_hook=inspect) as transaction:
        transaction.commit(_candidate(paths))

    assert observed_states == ["installing"]


def test_prepared_marker_failure_before_install_proves_not_committed(tmp_path: Path) -> None:
    paths = _workspace(tmp_path)
    original = _bytes(paths)

    def fail(phase: str) -> None:
        if phase == "workspace_prepared:before_file_fsync":
            raise OSError("injected")

    with WorkspaceTransaction(paths, "test", fault_hook=fail) as transaction:
        result = transaction.commit(_candidate(paths))

    assert result.outcome is CommitOutcome.NOT_COMMITTED
    assert _bytes(paths) == original
    assert not _coordinator(paths).exists()
    assert not list(tmp_path.glob("*.candidate"))
    assert not list(tmp_path.glob("*.original"))


def test_idle_marker_failure_keeps_verified_outcome_cleanup_pending(tmp_path: Path) -> None:
    paths = _workspace(tmp_path)

    def fail(phase: str) -> None:
        if phase == "workspace_idle:before_file_fsync":
            raise OSError("injected")

    with WorkspaceTransaction(paths, "test", fault_hook=fail) as transaction:
        result = transaction.commit(_candidate(paths))

    assert result.outcome is CommitOutcome.COMMITTED_VERIFIED
    assert result.cleanup_pending
    assert inspect_workspace_recovery(paths).state is WorkspaceRecoveryState.CLEANUP_PENDING
    recovered = recover_workspace(paths)
    assert recovered.resolution == CommitOutcome.COMMITTED_VERIFIED.value
    assert inspect_workspace_recovery(paths).state is WorkspaceRecoveryState.CLEAN


def test_resolution_report_failure_is_committed_unverified(tmp_path: Path) -> None:
    paths = _workspace(tmp_path)

    def fail(phase: str) -> None:
        if phase == "workspace_resolution:before_file_fsync":
            raise OSError("injected")

    with WorkspaceTransaction(paths, "test", fault_hook=fail) as transaction:
        result = transaction.commit(_candidate(paths))

    assert result.outcome is CommitOutcome.COMMITTED_UNVERIFIED
    assert inspect_workspace_recovery(paths).state is WorkspaceRecoveryState.REQUIRED
    recovered = recover_workspace(paths)
    assert recovered.resolution == CommitOutcome.COMMITTED_VERIFIED.value
