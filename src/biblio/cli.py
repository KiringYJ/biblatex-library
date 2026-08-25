"""Thin command-line adapter for coordinated biblio workspaces."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Never

from . import commands, results
from .config import BiblioConfig, ConfigError
from .storage import StorageError, WorkspacePaths

_NORMALIZATION_ACTIONS = (
    "all",
    "year-to-date",
    "publisher-location",
    "eprint-fields",
    "journal-fields",
    "book-pagination",
    "name-spacing",
    "latex-accents",
    "isbn",
    "trivial-url",
)


def setup_logging(verbosity: int = 0) -> None:
    """Configure CLI diagnostics."""
    if verbosity == 0:
        level = logging.WARNING
    elif verbosity == 1:
        level = logging.INFO
    else:
        level = logging.DEBUG
    logging.basicConfig(level=level, format="%(levelname)s %(name)s:%(lineno)d – %(message)s")


def resolve_config(args: argparse.Namespace) -> BiblioConfig:
    """Discover configuration and apply explicit path overrides."""
    config_name: str | None = args.config
    config = (
        BiblioConfig.from_toml(Path(config_name))
        if config_name is not None
        else BiblioConfig.discover()
    )
    bib_name: str | None = args.bib
    identifier_name: str | None = args.identifiers
    add_order_name: str | None = args.add_order
    staging_name: str | None = args.staging
    return config.with_overrides(
        bib_path=Path(bib_name) if bib_name is not None else None,
        identifier_path=Path(identifier_name) if identifier_name is not None else None,
        add_order_path=Path(add_order_name) if add_order_name is not None else None,
        staging_dir=Path(staging_name) if staging_name is not None else None,
    )


def workspace_paths(config: BiblioConfig) -> WorkspacePaths:
    """Adapt resolved config to the application-service workspace boundary."""
    return WorkspacePaths(config.bib_path, config.identifier_path, config.add_order_path)


def _render(value: object) -> None:
    payload = asdict(value) if is_dataclass(value) and not isinstance(value, type) else value
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str))


def _diagnose(message: str) -> None:
    print(message, file=sys.stderr)


def _commit_exit_code(commit: results.WorkspaceCommitResult | None) -> int:
    if commit is None:
        return 0
    if commit.cleanup_pending:
        return 2
    if commit.outcome is results.CommitOutcome.COMMITTED_VERIFIED:
        return 0
    if commit.outcome is results.CommitOutcome.COMMITTED_UNVERIFIED:
        return 2
    return 1


def _render_commit_diagnostics(commit: results.WorkspaceCommitResult | None) -> None:
    if commit is None:
        return
    for diagnostic in commit.diagnostics:
        _diagnose(diagnostic)
    for artifact in commit.artifacts:
        for diagnostic in artifact.diagnostics:
            _diagnose(f"{artifact.name}: {diagnostic}")


def cmd_init(args: argparse.Namespace) -> int:
    """Initialize a consumer workspace."""
    from .init import init_workspace

    target = Path(args.directory) if args.directory is not None else Path.cwd()
    try:
        created = init_workspace(target, force=args.force)
    except (OSError, ValueError) as error:
        _diagnose(str(error))
        return 1
    _render({"target": str(target.resolve()), "created": created})
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """Validate all three coordinated workspace artifacts."""
    try:
        result = commands.validate(workspace_paths(resolve_config(args)))
    except (ConfigError, OSError, StorageError, ValueError) as error:
        _diagnose(str(error))
        return 1
    _render(result)
    for issue in result.issues:
        _diagnose(issue)
    return 0 if result.valid else 1


def cmd_audit(args: argparse.Namespace) -> int:
    """Audit deterministic bibliography conventions without external lookup."""
    try:
        result = commands.audit(workspace_paths(resolve_config(args)))
    except (ConfigError, OSError, StorageError, ValueError) as error:
        _diagnose(str(error))
        return 1
    _render(result)
    for finding in result.findings:
        keys = ",".join(finding.canonical_keys)
        fields = ",".join(finding.fields)
        _diagnose(f"{finding.code}:{keys}:{fields}: {finding.message}")
    return 0 if result.clean else 1


def cmd_add(args: argparse.Namespace) -> int:
    """Append and then consume verified staging inputs."""
    try:
        config = resolve_config(args)
        staging = Path(args.staging_path).resolve() if args.staging_path else config.staging_dir
        result = commands.add(workspace_paths(config), staging, dry_run=args.dry_run)
    except (ConfigError, OSError, StorageError, ValueError) as error:
        _diagnose(str(error))
        return 1
    _render(result)
    _render_commit_diagnostics(result.commit)
    for diagnostic in result.cleanup_diagnostics:
        _diagnose(diagnostic)
    commit_status = _commit_exit_code(result.commit)
    if commit_status != 0:
        return commit_status
    if result.conflicted_paths:
        return 1
    if result.cleanup_diagnostics or (result.commit is not None and result.retained_paths):
        return 2
    return 0


def cmd_normalize(args: argparse.Namespace) -> int:
    """Normalize bibliography presentation through one workspace service."""
    try:
        result = commands.normalize(
            workspace_paths(resolve_config(args)), args.action, dry_run=args.dry_run
        )
    except (ConfigError, OSError, StorageError, ValueError) as error:
        _diagnose(str(error))
        return 1
    _render(result)
    _render_commit_diagnostics(result.commit)
    for diagnostic in result.diagnostics:
        _diagnose(diagnostic)
    return _commit_exit_code(result.commit)


def cmd_reconcile(args: argparse.Namespace) -> int:
    """Append missing BibLaTeX identifiers to the exact JSON inventory."""
    try:
        result = commands.reconcile(workspace_paths(resolve_config(args)), dry_run=args.dry_run)
    except (ConfigError, OSError, StorageError, ValueError) as error:
        _diagnose(str(error))
        return 1
    _render(result)
    _render_commit_diagnostics(result.commit)
    return _commit_exit_code(result.commit)


def cmd_remove(args: argparse.Namespace) -> int:
    """Hard-delete one record from the coordinated workspace."""
    try:
        result = commands.remove(
            workspace_paths(resolve_config(args)), args.identity, dry_run=args.dry_run
        )
    except (ConfigError, OSError, StorageError, ValueError) as error:
        _diagnose(str(error))
        return 1
    _render(result)
    _render_commit_diagnostics(result.commit)
    return _commit_exit_code(result.commit)


def cmd_promote(args: argparse.Namespace) -> int:
    """Promote an arXiv record across all workspace artifacts."""
    try:
        result = commands.promote(
            workspace_paths(resolve_config(args)),
            args.identity,
            Path(args.published),
            dry_run=args.dry_run,
        )
    except (ConfigError, OSError, StorageError, ValueError) as error:
        _diagnose(str(error))
        return 1
    _render(result)
    _render_commit_diagnostics(result.commit)
    return _commit_exit_code(result.commit)


def cmd_recover(args: argparse.Namespace) -> int:
    """Inspect or resolve the coordinated workspace transaction."""
    try:
        result = commands.recover(workspace_paths(resolve_config(args)), dry_run=args.dry_run)
    except (ConfigError, OSError, StorageError, ValueError) as error:
        _diagnose(str(error))
        return 1
    _render(result)
    for diagnostic in result.diagnostics:
        _diagnose(diagnostic)
    if args.dry_run:
        if result.resolution == "invalid":
            return 2
        if result.resolution != "clean":
            return 1
    return 0


def create_parser() -> argparse.ArgumentParser:
    """Build the public command-line parser."""
    parser = argparse.ArgumentParser(
        prog="biblio",
        description="Maintain one coordinated BibLaTeX workspace.",
    )
    parser.add_argument("-v", "--verbose", action="count", default=0)
    parser.add_argument("--config", help="Explicit biblio.toml path")
    parser.add_argument("--bib", help="Override the bibliography path")
    parser.add_argument("--identifiers", help="Override the identifier collection path")
    parser.add_argument("--add-order", dest="add_order", help="Override the add-order path")
    parser.add_argument("--staging", help="Override the staging directory")

    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Initialize a consumer workspace")
    init_parser.add_argument("directory", nargs="?")
    init_parser.add_argument("--force", action="store_true")
    init_parser.set_defaults(handler=cmd_init)

    validate_parser = subparsers.add_parser("validate", help="Validate the workspace")
    validate_parser.set_defaults(handler=cmd_validate)

    audit_parser = subparsers.add_parser(
        "audit", help="Audit deterministic bibliography conventions"
    )
    audit_parser.set_defaults(handler=cmd_audit)

    add_parser = subparsers.add_parser("add", help="Append and consume staged entries")
    add_parser.add_argument("staging_path", nargs="?", metavar="STAGING")
    add_parser.add_argument("--dry-run", action="store_true")
    add_parser.set_defaults(handler=cmd_add)

    normalize_parser = subparsers.add_parser("normalize", help="Normalize bibliography fields")
    normalize_parser.add_argument(
        "action", nargs="?", default="all", choices=_NORMALIZATION_ACTIONS
    )
    normalize_parser.add_argument("--dry-run", action="store_true")
    normalize_parser.set_defaults(handler=cmd_normalize)

    reconcile_parser = subparsers.add_parser(
        "reconcile",
        help="Append missing .bib identifiers to the exact JSON inventory",
        description=(
            "Append supported identifiers from library.bib to the JSON inventory; "
            "never overwrite or delete identifiers, change main/hash provenance, "
            "or modify library.bib or add_order.json."
        ),
    )
    reconcile_parser.add_argument("--dry-run", action="store_true")
    reconcile_parser.set_defaults(handler=cmd_reconcile)

    remove_parser = subparsers.add_parser("remove", help="Hard-delete one record")
    remove_parser.add_argument("identity", metavar="KEY")
    remove_parser.add_argument("--dry-run", action="store_true")
    remove_parser.set_defaults(handler=cmd_remove)

    promote_parser = subparsers.add_parser("promote", help="Promote an arXiv record")
    promote_parser.add_argument("identity", metavar="KEY")
    promote_parser.add_argument("published", metavar="PUBLISHED.bib")
    promote_parser.add_argument("--dry-run", action="store_true")
    promote_parser.set_defaults(handler=cmd_promote)

    recover_parser = subparsers.add_parser("recover", help="Inspect or recover the workspace")
    status_group = recover_parser.add_mutually_exclusive_group()
    status_group.add_argument("--dry-run", action="store_true", help="Inspect without recovery")
    status_group.add_argument("--status", action="store_true", help="Alias for --dry-run")
    recover_parser.set_defaults(handler=cmd_recover)

    return parser


def run(argv: list[str] | None = None) -> int:
    """Parse ``argv`` and return an exit status."""
    args = create_parser().parse_args(argv)
    if args.command == "recover" and args.status:
        args.dry_run = True
    setup_logging(args.verbose)
    return int(args.handler(args))


def main(argv: list[str] | None = None) -> Never:
    """CLI process boundary."""
    raise SystemExit(run(argv))


if __name__ == "__main__":
    main()
