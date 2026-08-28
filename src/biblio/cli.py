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


def _render(value: object, *, summary: str, json_output: bool) -> None:
    if not json_output:
        print(summary)
        return
    payload = asdict(value) if is_dataclass(value) and not isinstance(value, type) else value
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str))


def _quantity(count: int, singular: str, plural: str) -> str:
    return f"{count} {singular if count == 1 else plural}"


def _mutation_summary(
    commit: results.WorkspaceCommitResult | None,
    *,
    dry_run: bool,
    completed: str,
    preview: str,
) -> str:
    if dry_run:
        return f"Dry run: {preview}"
    if commit is None:
        return "No changes committed."
    if commit.outcome is results.CommitOutcome.NOT_COMMITTED:
        summary = "Changes not committed."
    elif commit.outcome is results.CommitOutcome.COMMITTED_UNVERIFIED:
        summary = "Commit outcome unverified; run 'biblio recover --status'."
    else:
        summary = completed
    if commit.cleanup_pending:
        summary += " Workspace cleanup pending; run 'biblio recover'."
    return summary


def _add_summary(result: results.AddResult, *, dry_run: bool) -> str:
    if dry_run and (result.cleanup_diagnostics or result.conflicted_paths):
        return "Dry run: staging cleanup pending; no import preview."
    entries = _quantity(len(result.added_keys), "entry", "entries")
    summary = _mutation_summary(
        result.commit,
        dry_run=dry_run,
        completed=f"Added {entries}.",
        preview=f"would add {entries}.",
    )
    if result.commit is None and not result.changes.changed:
        if dry_run:
            summary = "Dry run: no new entries to add."
        elif result.consumed_paths and not (
            result.retained_paths or result.conflicted_paths or result.cleanup_diagnostics
        ):
            summary = "Staging cleanup completed; no new entries added."
        else:
            summary = "No new entries added."
    if result.conflicted_paths:
        summary += f" Staging conflicts: {len(result.conflicted_paths)}."
    elif result.retained_paths and not dry_run:
        retained = _quantity(len(result.retained_paths), "staging input", "staging inputs")
        summary += f" Retained {retained}."
    elif result.cleanup_diagnostics:
        summary += " Staging cleanup incomplete."
    if (dry_run and result.changes.changed) or (
        result.commit is not None
        and result.commit.outcome is results.CommitOutcome.COMMITTED_VERIFIED
    ):
        summary += "".join(f"\n  {key}" for key in result.added_keys)
    return summary


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
    files = _quantity(len(created), "file", "files")
    _render(
        {"target": str(target.resolve()), "created": created},
        summary=f"Initialized workspace at {target.resolve()} ({files} written).",
        json_output=args.json_output,
    )
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """Validate all three coordinated workspace artifacts."""
    try:
        result = commands.validate(workspace_paths(resolve_config(args)))
    except (ConfigError, OSError, StorageError, ValueError) as error:
        _diagnose(str(error))
        return 1
    summary = (
        "Workspace is valid."
        if result.valid
        else f"Validation failed: {_quantity(len(result.issues), 'issue', 'issues')}."
    )
    _render(result, summary=summary, json_output=args.json_output)
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
    summary = (
        "No audit findings."
        if result.clean
        else f"Audit found {_quantity(len(result.findings), 'finding', 'findings')}."
    )
    _render(result, summary=summary, json_output=args.json_output)
    for finding in result.findings:
        keys = ",".join(finding.canonical_keys)
        fields = ",".join(finding.fields)
        _diagnose(f"{finding.code}:{keys}:{fields}: {finding.message}")
    return 0 if result.clean else 1


def cmd_template(args: argparse.Namespace) -> int:
    """Generate editable per-entry identifier templates for staged bibliographies."""
    try:
        config = resolve_config(args)
        staging = Path(args.staging_path).resolve() if args.staging_path else config.staging_dir
        result = commands.template(staging, overwrite=args.overwrite)
    except (ConfigError, OSError, StorageError, ValueError) as error:
        _diagnose(str(error))
        return 1
    created = _quantity(len(result.created_paths), "template", "templates")
    skipped = _quantity(len(result.skipped_paths), "existing template", "existing templates")
    summary = f"Created {created}; skipped {skipped}."
    summary += "".join(f"\n  {path}" for path in result.created_paths)
    _render(result, summary=summary, json_output=args.json_output)
    for diagnostic in result.normalization_diagnostics:
        _diagnose(diagnostic)
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    """Normalize, validate, append, and then consume verified staging inputs."""
    try:
        config = resolve_config(args)
        staging = Path(args.staging_path).resolve() if args.staging_path else config.staging_dir
        result = commands.add(workspace_paths(config), staging, dry_run=args.dry_run)
    except (ConfigError, OSError, StorageError, ValueError) as error:
        _diagnose(str(error))
        return 1
    _render(
        result, summary=_add_summary(result, dry_run=args.dry_run), json_output=args.json_output
    )
    _render_commit_diagnostics(result.commit)
    for diagnostic in result.normalization_diagnostics:
        _diagnose(diagnostic)
    for diagnostic in result.cleanup_diagnostics:
        _diagnose(diagnostic)
    if not args.json_output:
        for path in result.conflicted_paths:
            _diagnose(f"Staging conflict: {path}")
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
    entries = _quantity(len(result.changes.changed_keys), "entry", "entries")
    summary = _mutation_summary(
        result.commit,
        dry_run=args.dry_run,
        completed=f"Normalized {entries}.",
        preview=f"would normalize {entries}.",
    )
    _render(result, summary=summary, json_output=args.json_output)
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
    identifiers = _quantity(len(result.additions), "identifier", "identifiers")
    entries = _quantity(
        len({addition.canonical_key for addition in result.additions}), "entry", "entries"
    )
    summary = _mutation_summary(
        result.commit,
        dry_run=args.dry_run,
        completed=f"Added {identifiers} across {entries}.",
        preview=f"would add {identifiers} across {entries}.",
    )
    _render(result, summary=summary, json_output=args.json_output)
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
    summary = _mutation_summary(
        result.commit,
        dry_run=args.dry_run,
        completed=f"Removed {result.canonical_key}.",
        preview=f"would remove {result.canonical_key}.",
    )
    _render(result, summary=summary, json_output=args.json_output)
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
    summary = _mutation_summary(
        result.commit,
        dry_run=args.dry_run,
        completed=f"Promoted {result.old_key} -> {result.new_key}.",
        preview=f"would promote {result.old_key} -> {result.new_key}.",
    )
    _render(result, summary=summary, json_output=args.json_output)
    _render_commit_diagnostics(result.commit)
    return _commit_exit_code(result.commit)


def cmd_recover(args: argparse.Namespace) -> int:
    """Inspect or resolve the coordinated workspace transaction."""
    try:
        result = commands.recover(workspace_paths(resolve_config(args)), dry_run=args.dry_run)
    except (ConfigError, OSError, StorageError, ValueError) as error:
        _diagnose(str(error))
        return 1
    summary = {
        "clean": "No recovery needed.",
        "recovery_required": "Recovery required; run 'biblio recover'.",
        "cleanup_pending": "Workspace cleanup pending; run 'biblio recover'.",
        "invalid": "Recovery state is invalid.",
        "not_committed": "Recovered original workspace; transaction was not committed.",
        "committed_verified": "Recovered committed workspace.",
    }.get(result.resolution, f"Recovery status: {result.resolution}.")
    _render(result, summary=summary, json_output=args.json_output)
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
    parser.add_argument(
        "--json", dest="json_output", action="store_true", help="Print the full result as JSON"
    )
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

    template_parser = subparsers.add_parser(
        "template",
        help="Generate editable identifier templates for staged entries",
        description=(
            "Generate one editable JSON identifier template beside each staged .bib file. "
            "Each entry retains an independently reviewable main_identifier selection."
        ),
    )
    template_parser.add_argument("staging_path", nargs="?", metavar="STAGING")
    template_parser.add_argument("--overwrite", action="store_true")
    template_parser.set_defaults(handler=cmd_template)

    add_parser = subparsers.add_parser(
        "add",
        help="Normalize, validate, append, and consume staged entries",
        description=(
            "Normalize incoming entries, validate the complete workspace candidate, "
            "then append and consume the exact staged inputs."
        ),
    )
    add_parser.add_argument("staging_path", nargs="?", metavar="STAGING")
    add_parser.add_argument("--dry-run", action="store_true")
    add_parser.set_defaults(handler=cmd_add)

    normalize_parser = subparsers.add_parser("normalize", help="Normalize bibliography fields")
    normalize_parser.add_argument(
        "action", nargs="?", default="all", choices=("all", *commands.NORMALIZATION_ACTIONS)
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

    for command_parser in (
        init_parser,
        validate_parser,
        audit_parser,
        template_parser,
        add_parser,
        normalize_parser,
        reconcile_parser,
        remove_parser,
        promote_parser,
        recover_parser,
    ):
        command_parser.add_argument(
            "--json",
            dest="json_output",
            action="store_true",
            default=argparse.SUPPRESS,
            help="Print the full result as JSON",
        )

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
