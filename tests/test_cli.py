"""Contract tests for the coordinated-workspace CLI adapter."""

import ast
import json
from pathlib import Path

import pytest

from biblio import cli, commands
from biblio.results import (
    AddResult,
    AuditFinding,
    AuditResult,
    CommitOutcome,
    NormalizeResult,
    PromoteResult,
    ReconcileResult,
    RecoverResult,
    RemoveResult,
    ValidateResult,
    WorkspaceCommitResult,
)
from biblio.storage import StorageError, WorkspacePaths


def _write_config(root: Path) -> Path:
    config = root / "biblio.toml"
    config.write_text(
        """\
[paths]
bib = "bib/library.bib"
identifiers = "data/identifier_collection.json"
add_order = "data/add_order.json"
staging = "staging"
""",
        encoding="utf-8",
    )
    return config


def _paths(root: Path) -> WorkspacePaths:
    return WorkspacePaths(
        (root / "bib" / "library.bib").resolve(),
        (root / "data" / "identifier_collection.json").resolve(),
        (root / "data" / "add_order.json").resolve(),
    )


def _commit(
    outcome: CommitOutcome,
    *,
    diagnostics: tuple[str, ...] = (),
    cleanup_pending: bool = False,
) -> WorkspaceCommitResult:
    return WorkspaceCommitResult(
        outcome, (), diagnostics=diagnostics, cleanup_pending=cleanup_pending
    )


def test_cli_module_has_only_allowed_biblio_imports():
    tree = ast.parse(Path(cli.__file__).read_text(encoding="utf-8"))
    imports: set[str] = set()
    storage_names: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom) or not node.level:
            continue
        if node.module is None:
            imports.update(alias.name for alias in node.names)
        else:
            root = node.module.split(".", maxsplit=1)[0]
            imports.add(root)
            if root == "storage":
                storage_names.update(alias.name for alias in node.names)

    assert imports <= {"commands", "config", "results", "storage"}
    assert storage_names == {"StorageError", "WorkspacePaths"}
    assert not imports & {"lifecycle", "normalize", "bibliography", "migrate"}


def test_parser_has_only_current_commands_and_restored_overrides():
    parser = cli.create_parser()
    help_text = parser.format_help()

    for command in (
        "init",
        "validate",
        "audit",
        "add",
        "normalize",
        "reconcile",
        "remove",
        "promote",
        "recover",
    ):
        assert command in help_text
    for retired in ("migrate", "sort", "sync", "template", "generate-labels"):
        assert retired not in help_text
    for option in ("--bib", "--identifiers", "--add-order", "--staging"):
        assert option in help_text


def test_reconcile_help_states_one_way_non_destructive_direction(
    capsys: pytest.CaptureFixture[str],
):
    with pytest.raises(SystemExit) as raised:
        cli.create_parser().parse_args(["reconcile", "--help"])

    help_text = capsys.readouterr().out
    assert raised.value.code == 0
    assert "Append supported identifiers from library.bib" in help_text
    assert "overwrite or delete identifiers" in help_text
    assert "modify" in help_text
    assert "library.bib or add_order.json" in help_text


def test_validate_calls_one_service_with_all_workspace_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    config = _write_config(tmp_path)
    calls: list[WorkspacePaths] = []

    def fake_validate(paths: WorkspacePaths) -> ValidateResult:
        calls.append(paths)
        return ValidateResult(valid=True)

    monkeypatch.setattr(commands, "validate", fake_validate)

    status = cli.run(["--config", str(config), "validate"])

    captured = capsys.readouterr()
    assert status == 0
    assert calls == [_paths(tmp_path)]
    assert json.loads(captured.out)["valid"] is True
    assert captured.err == ""


def test_audit_calls_one_service_and_exits_nonzero_for_findings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    config = _write_config(tmp_path)
    calls: list[WorkspacePaths] = []
    finding = AuditFinding(
        code="multiple-issn",
        canonical_keys=("record",),
        fields=("issn",),
        message="entry has multiple ISSNs",
    )

    def fake_audit(paths: WorkspacePaths) -> AuditResult:
        calls.append(paths)
        return AuditResult(clean=False, findings=(finding,))

    monkeypatch.setattr(commands, "audit", fake_audit)

    status = cli.run(["--config", str(config), "audit"])

    captured = capsys.readouterr()
    assert status == 1
    assert calls == [_paths(tmp_path)]
    assert json.loads(captured.out)["findings"][0]["code"] == "multiple-issn"
    assert "multiple-issn:record:issn: entry has multiple ISSNs" in captured.err


def test_restored_overrides_build_exact_workspace_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    config = _write_config(tmp_path)
    calls: list[WorkspacePaths] = []
    overrides = WorkspacePaths(
        (tmp_path / "other.bib").resolve(),
        (tmp_path / "other-identifiers.json").resolve(),
        (tmp_path / "other-order.json").resolve(),
    )

    def fake_validate(paths: WorkspacePaths) -> ValidateResult:
        calls.append(paths)
        return ValidateResult(valid=True)

    monkeypatch.setattr(commands, "validate", fake_validate)

    status = cli.run(
        [
            "--config",
            str(config),
            "--bib",
            str(overrides.bibliography),
            "--identifiers",
            str(overrides.identifiers),
            "--add-order",
            str(overrides.add_order),
            "validate",
        ]
    )

    assert status == 0
    assert calls == [overrides]


@pytest.mark.parametrize(
    ("argv", "service_name", "result"),
    [
        (["audit"], "audit", AuditResult(clean=True)),
        (["add", "inbox", "--dry-run"], "add", AddResult(())),
        (["normalize", "--dry-run"], "normalize", NormalizeResult(("all",))),
        (["reconcile", "--dry-run"], "reconcile", ReconcileResult()),
        (["remove", "old", "--dry-run"], "remove", RemoveResult("old", ())),
        (
            ["promote", "old", "published.bib", "--dry-run"],
            "promote",
            PromoteResult("old", "new", ("old",), "10.1/example"),
        ),
        (["recover", "--status"], "recover", RecoverResult("clean")),
    ],
)
def test_each_normal_handler_calls_exactly_one_service(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    argv: list[str],
    service_name: str,
    result: object,
):
    config = _write_config(tmp_path)
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def fake_service(*args: object, **kwargs: object) -> object:
        calls.append((args, kwargs))
        return result

    monkeypatch.setattr(commands, service_name, fake_service)

    assert cli.run(["--config", str(config), *argv]) == 0
    assert len(calls) == 1
    assert calls[0][0][0] == _paths(tmp_path)


def test_add_passes_staging_override_and_dry_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    config = _write_config(tmp_path)
    staging = tmp_path / "temporary-source.bib"
    calls: list[tuple[WorkspacePaths, Path, bool]] = []

    def fake_add(paths: WorkspacePaths, source: Path, *, dry_run: bool) -> AddResult:
        calls.append((paths, source, dry_run))
        return AddResult(())

    monkeypatch.setattr(commands, "add", fake_add)

    status = cli.run(["--config", str(config), "add", str(staging), "--dry-run"])

    assert status == 0
    assert calls == [(_paths(tmp_path), staging.resolve(), True)]


def test_normalize_defaults_to_all(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    config = _write_config(tmp_path)
    actions: list[str] = []

    def fake_normalize(_paths: WorkspacePaths, action: str, *, dry_run: bool) -> NormalizeResult:
        assert dry_run is False
        actions.append(action)
        return NormalizeResult((action,))

    monkeypatch.setattr(commands, "normalize", fake_normalize)

    assert cli.run(["--config", str(config), "normalize"]) == 0
    assert actions == ["all"]


def test_reconcile_passes_full_workspace_and_dry_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    config = _write_config(tmp_path)
    calls: list[tuple[WorkspacePaths, bool]] = []

    def fake_reconcile(paths: WorkspacePaths, *, dry_run: bool) -> ReconcileResult:
        calls.append((paths, dry_run))
        return ReconcileResult()

    monkeypatch.setattr(commands, "reconcile", fake_reconcile)

    assert cli.run(["--config", str(config), "reconcile", "--dry-run"]) == 0
    assert calls == [(_paths(tmp_path), True)]


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        (CommitOutcome.COMMITTED_VERIFIED, 0),
        (CommitOutcome.COMMITTED_UNVERIFIED, 2),
        (CommitOutcome.NOT_COMMITTED, 1),
    ],
)
def test_reconcile_uses_workspace_commit_exit_mapping(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    outcome: CommitOutcome,
    expected: int,
):
    config = _write_config(tmp_path)
    monkeypatch.setattr(
        commands,
        "reconcile",
        lambda _paths, *, dry_run: ReconcileResult(commit=_commit(outcome)),
    )

    assert cli.run(["--config", str(config), "reconcile"]) == expected


def test_reconcile_storage_error_is_rendered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    config = _write_config(tmp_path)

    def fail_reconcile(_paths: WorkspacePaths, *, dry_run: bool) -> ReconcileResult:
        assert dry_run is False
        raise StorageError("reconcile workspace unavailable")

    monkeypatch.setattr(commands, "reconcile", fail_reconcile)

    assert cli.run(["--config", str(config), "reconcile"]) == 1
    assert "reconcile workspace unavailable" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        (CommitOutcome.COMMITTED_VERIFIED, 0),
        (CommitOutcome.COMMITTED_UNVERIFIED, 2),
        (CommitOutcome.NOT_COMMITTED, 1),
    ],
)
def test_workspace_commit_outcome_controls_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    outcome: CommitOutcome,
    expected: int,
):
    config = _write_config(tmp_path)
    monkeypatch.setattr(
        commands,
        "normalize",
        lambda _paths, _action, *, dry_run: NormalizeResult(("all",), commit=_commit(outcome)),
    )

    assert cli.run(["--config", str(config), "normalize"]) == expected


@pytest.mark.parametrize(
    ("argv", "service_name"),
    [
        (["add"], "add"),
        (["normalize"], "normalize"),
        (["reconcile"], "reconcile"),
        (["remove", "old"], "remove"),
        (["promote", "old", "published.bib"], "promote"),
    ],
)
def test_verified_commit_with_pending_cleanup_is_degraded_for_every_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    service_name: str,
):
    config = _write_config(tmp_path)
    commit = _commit(
        CommitOutcome.COMMITTED_VERIFIED,
        diagnostics=("workspace cleanup pending",),
        cleanup_pending=True,
    )
    if service_name == "add":
        result: object = AddResult(("new",), commit=commit)
    elif service_name == "normalize":
        result = NormalizeResult(("all",), commit=commit)
    elif service_name == "reconcile":
        result = ReconcileResult(commit=commit)
    elif service_name == "remove":
        result = RemoveResult("old", (), commit=commit)
    else:
        result = PromoteResult("old", "new", ("old",), "10.1/example", commit=commit)
    monkeypatch.setattr(commands, service_name, lambda *args, **kwargs: result)

    assert cli.run(["--config", str(config), *argv]) == 2
    assert "workspace cleanup pending" in capsys.readouterr().err


def test_add_verified_content_with_cleanup_failure_exits_two(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    config = _write_config(tmp_path)
    retained = tmp_path / "staging" / "temporary.bib"
    monkeypatch.setattr(
        commands,
        "add",
        lambda _paths, _staging, *, dry_run: AddResult(
            ("new",),
            commit=_commit(CommitOutcome.COMMITTED_VERIFIED),
            retained_paths=(retained,),
            cleanup_diagnostics=("cleanup pending",),
        ),
    )

    status = cli.run(["--config", str(config), "add"])

    assert status == 2
    assert "cleanup pending" in capsys.readouterr().err


def test_add_conflicted_cleanup_receipt_exits_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    config = _write_config(tmp_path)
    conflict = tmp_path / "staging" / "changed.bib"
    monkeypatch.setattr(
        commands,
        "add",
        lambda _paths, _staging, *, dry_run: AddResult(
            (), retained_paths=(conflict,), conflicted_paths=(conflict,)
        ),
    )

    assert cli.run(["--config", str(config), "add"]) == 1


def test_recover_status_inspects_full_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    config = _write_config(tmp_path)
    calls: list[tuple[WorkspacePaths, bool]] = []

    def fake_recover(paths: WorkspacePaths, *, dry_run: bool) -> RecoverResult:
        calls.append((paths, dry_run))
        return RecoverResult("recovery_required")

    monkeypatch.setattr(commands, "recover", fake_recover)

    assert cli.run(["--config", str(config), "recover", "--status"]) == 1
    assert calls == [(_paths(tmp_path), True)]


def test_validate_failure_uses_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    config = _write_config(tmp_path)
    monkeypatch.setattr(
        commands, "validate", lambda _paths: ValidateResult(False, ("ledger mismatch",))
    )

    assert cli.run(["--config", str(config), "validate"]) == 1
    assert "ledger mismatch" in capsys.readouterr().err


def test_storage_error_is_rendered_as_user_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    config = _write_config(tmp_path)

    def fail_storage(_paths: WorkspacePaths) -> ValidateResult:
        raise StorageError("workspace lock unavailable")

    monkeypatch.setattr(commands, "validate", fail_storage)

    assert cli.run(["--config", str(config), "validate"]) == 1
    assert "workspace lock unavailable" in capsys.readouterr().err


def test_unrelated_runtime_error_propagates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    config = _write_config(tmp_path)

    def fail_programmer(_paths: WorkspacePaths) -> ValidateResult:
        raise RuntimeError("programmer defect")

    monkeypatch.setattr(commands, "validate", fail_programmer)

    with pytest.raises(RuntimeError, match="programmer defect"):
        cli.run(["--config", str(config), "validate"])


def test_main_raises_system_exit_at_process_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    config = _write_config(tmp_path)
    monkeypatch.setattr(commands, "validate", lambda _paths: ValidateResult(True))

    with pytest.raises(SystemExit) as raised:
        cli.main(["--config", str(config), "validate"])

    assert raised.value.code == 0
