"""Tests for immutable operation-specific result models."""

from dataclasses import FrozenInstanceError

import pytest

from biblio.results import (
    AddResult,
    AliasDelta,
    ChangeSet,
    CommitOutcome,
    FieldDelta,
    NormalizeResult,
    OrderDelta,
    PromoteResult,
    RecoverResult,
    RemoveResult,
    ValidateResult,
    WorkspaceCommitResult,
)


def test_change_set_reports_whether_any_domain_change_exists() -> None:
    empty = ChangeSet()
    changed = ChangeSet(
        changed_keys=("New", "Old"),
        field_deltas=(FieldDelta("New", "doi", None, "10.1000/new"),),
        alias_deltas=(AliasDelta("New", added=("Old",)),),
        order_delta=OrderDelta(before=("Old",), after=("New",)),
    )

    assert not empty.changed
    assert changed.changed


def test_result_models_are_immutable_and_operation_specific() -> None:
    commit = WorkspaceCommitResult(CommitOutcome.COMMITTED_VERIFIED, ())
    validate = ValidateResult(valid=True)
    add = AddResult(
        added_keys=("New",),
        stripped_doi_query_keys=("New",),
        stripped_doi_fragment_keys=("New",),
        commit=commit,
    )
    normalize = NormalizeResult(
        actions=("isbn",), diagnostics=("isbn:invalid:Old:bad",), commit=commit
    )
    remove = RemoveResult(canonical_key="Old", aliases=("Older",), commit=commit)
    promote = PromoteResult(
        old_key="Old",
        new_key="New",
        aliases=("Old", "Older"),
        canonical_doi="10.1000/new",
        commit=commit,
    )
    recover = RecoverResult(resolution="candidate_committed", observed={"bibliography": "new"})

    assert commit.committed
    assert validate.valid
    assert add.added_keys == ("New",)
    assert add.stripped_doi_query_keys == ("New",)
    assert add.stripped_doi_fragment_keys == ("New",)
    assert normalize.actions == ("isbn",)
    assert normalize.diagnostics == ("isbn:invalid:Old:bad",)
    assert remove.canonical_key == "Old"
    assert promote.new_key == "New"
    assert recover.resolution == "candidate_committed"
    assert recover.observed == {"bibliography": "new"}

    with pytest.raises(FrozenInstanceError):
        commit.__setattr__("outcome", CommitOutcome.NOT_COMMITTED)


def test_not_committed_is_not_reported_as_committed() -> None:
    result = WorkspaceCommitResult(
        outcome=CommitOutcome.NOT_COMMITTED,
        artifacts=(),
        diagnostics=("contended",),
    )

    assert not result.committed
