"""Immutable shared change details and operation-specific result models."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Literal


@dataclass(frozen=True, slots=True)
class FieldDelta:
    """One exact field-value change on a canonical entry."""

    canonical_key: str
    field: str
    before: str | None
    after: str | None


@dataclass(frozen=True, slots=True)
class AliasDelta:
    """Direct alias additions and removals for one canonical entry."""

    canonical_key: str
    added: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class OrderDelta:
    """Ordered canonical-key sequences before and after a transformation."""

    before: tuple[str, ...]
    after: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ChangeSet:
    """Small shared description of domain changes, independent of rendering."""

    changed_keys: tuple[str, ...] = ()
    field_deltas: tuple[FieldDelta, ...] = ()
    alias_deltas: tuple[AliasDelta, ...] = ()
    order_delta: OrderDelta | None = None

    @property
    def changed(self) -> bool:
        """Return whether the set contains any recorded change."""
        return bool(
            self.changed_keys
            or self.field_deltas
            or self.alias_deltas
            or self.order_delta is not None
        )


class CommitOutcome(StrEnum):
    """Exhaustive namespace-replacement outcomes."""

    NOT_COMMITTED = "not_committed"
    COMMITTED_VERIFIED = "committed_verified"
    COMMITTED_UNVERIFIED = "committed_unverified"


@dataclass(frozen=True, slots=True)
class ArtifactCommitEvidence:
    """Digest evidence for one artifact in a workspace commit."""

    name: str
    path: str
    original_sha256: str
    candidate_sha256: str
    observed_sha256: str | None
    dirty: bool
    replaced: bool
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class WorkspaceCommitResult:
    """Three-artifact logical commit outcome and per-file evidence."""

    outcome: CommitOutcome
    artifacts: tuple[ArtifactCommitEvidence, ...]
    diagnostics: tuple[str, ...] = ()
    cleanup_pending: bool = False

    @property
    def committed(self) -> bool:
        """Return whether the workspace logical commit artifact may have crossed."""
        return self.outcome is not CommitOutcome.NOT_COMMITTED


@dataclass(frozen=True, slots=True)
class AuditFinding:
    """One deterministic bibliography-compliance observation."""

    code: str
    canonical_keys: tuple[str, ...]
    fields: tuple[str, ...]
    message: str
    values: tuple[str, ...] = ()
    fix_action: str | None = None


@dataclass(frozen=True, slots=True)
class AuditResult:
    """Source-free bibliography audit outcome."""

    clean: bool
    findings: tuple[AuditFinding, ...] = ()


@dataclass(frozen=True, slots=True)
class ValidateResult:
    """Bibliography validation outcome."""

    valid: bool
    issues: tuple[str, ...] = ()
    changes: ChangeSet = field(default_factory=ChangeSet)


@dataclass(frozen=True, slots=True)
class AddResult:
    """Addition outcome."""

    added_keys: tuple[str, ...]
    changes: ChangeSet = field(default_factory=ChangeSet)
    commit: WorkspaceCommitResult | None = None
    stripped_doi_query_keys: tuple[str, ...] = ()
    stripped_doi_fragment_keys: tuple[str, ...] = ()
    input_paths: tuple[Path, ...] = ()
    consumed_paths: tuple[Path, ...] = ()
    retained_paths: tuple[Path, ...] = ()
    conflicted_paths: tuple[Path, ...] = ()
    cleanup_diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class NormalizeResult:
    """One or more normalization-action outcomes."""

    actions: tuple[str, ...]
    changes: ChangeSet = field(default_factory=ChangeSet)
    commit: WorkspaceCommitResult | None = None
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class IdentifierAddition:
    """One exact identifier value added to a record inventory."""

    canonical_key: str
    kind: str
    exact_value: str
    added_as: Literal["primary", "alternate"]


@dataclass(frozen=True, slots=True)
class ReconcileResult:
    """Monotonic identifier additions made by one reconciliation pass."""

    additions: tuple[IdentifierAddition, ...] = ()
    changes: ChangeSet = field(default_factory=ChangeSet)
    commit: WorkspaceCommitResult | None = None


@dataclass(frozen=True, slots=True)
class RemoveResult:
    """Hard-removal outcome for one canonical record and its aliases."""

    canonical_key: str
    aliases: tuple[str, ...]
    changes: ChangeSet = field(default_factory=ChangeSet)
    commit: WorkspaceCommitResult | None = None


@dataclass(frozen=True, slots=True)
class PromoteResult:
    """Publication-promotion outcome."""

    old_key: str
    new_key: str
    aliases: tuple[str, ...]
    canonical_doi: str
    stripped_doi_query: bool = False
    stripped_doi_fragment: bool = False
    changes: ChangeSet = field(default_factory=ChangeSet)
    commit: WorkspaceCommitResult | None = None


@dataclass(frozen=True, slots=True)
class RecoverResult:
    """Durable recovery classification and evidence."""

    resolution: str
    diagnostics: tuple[str, ...] = ()
    observed: Mapping[str, str] = field(default_factory=dict)
