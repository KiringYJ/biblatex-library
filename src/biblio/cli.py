"""Command-line interface for the biblio CLI."""

import argparse
import json
import logging
import sys
from pathlib import Path

from .add_entries import add_entries_from_staging
from .config import BiblioConfig
from .generate import generate_labels
from .init import init_workspace
from .normalize.accents import normalize_latex_accents
from .normalize.dates import rename_year_to_date_fields
from .normalize.eprint import normalize_eprint_fields
from .normalize.isbn import normalize_isbn_fields
from .normalize.publisher import normalize_publisher_location
from .normalize.url import normalize_trivial_urls
from .sort import sort_alphabetically, sort_by_add_order
from .sync import sync_identifiers_to_library
from .template import generate_staging_templates
from .validate import fix_citekey_labels, validate_citekey_consistency, validate_citekey_labels


def setup_logging(verbosity: int = 0) -> None:
    """Configure logging for the CLI application.

    Args:
        verbosity: Logging verbosity level (0=WARNING, 1=INFO, 2+=DEBUG)
    """
    level = {0: logging.WARNING, 1: logging.INFO}.get(min(verbosity, 1), logging.DEBUG)
    logging.basicConfig(
        level=level,
        format="%(levelname)s %(name)s:%(lineno)d – %(message)s",
    )


def resolve_config(args: argparse.Namespace) -> BiblioConfig:
    """Build resolved config from CLI args, toml discovery, and defaults."""
    config_file: str | None = args.config
    if config_file:
        config = BiblioConfig.from_toml(Path(config_file))
    else:
        config = BiblioConfig.discover()

    # Apply per-path CLI overrides
    bib: str | None = args.bib
    identifiers: str | None = args.identifiers
    add_order: str | None = args.add_order

    if bib or identifiers or add_order:
        config = config.with_overrides(
            bib_path=Path(bib) if bib else None,
            identifier_path=Path(identifiers) if identifiers else None,
            add_order_path=Path(add_order) if add_order else None,
        )

    return config


def cmd_init(args: argparse.Namespace) -> None:
    """Initialize a new biblio workspace."""
    target = Path(args.dir) if args.dir else Path.cwd()
    logger = logging.getLogger(__name__)

    try:
        created = init_workspace(target, force=args.force)
        for path in created:
            logger.info("Created %s", path)
        print(f"Initialized biblio workspace in {target.resolve()}")
    except FileExistsError as e:
        logger.error(str(e))
        sys.exit(1)


def cmd_generate_labels(args: argparse.Namespace) -> None:
    """Generate labels for biblatex entries."""
    config = resolve_config(args)
    default_output = config.root / "bib" / "generated" / "labels.json"
    output_path = Path(args.output) if args.output else default_output

    logger = logging.getLogger(__name__)
    logger.info("Generating labels for biblatex entries")

    try:
        labels = generate_labels(bib_path=config.bib_path, identifier_path=config.identifier_path)

        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(labels, f, indent=2, ensure_ascii=False)

        logger.info(f"✓ Generated {len(labels)} labels")
        logger.info(f"✓ Saved to: {output_path}")

        if args.verbose and labels:
            logger.info("Sample labels:")
            for i, (old_key, new_label) in enumerate(labels.items()):
                if i >= 5:
                    break
                logger.info(f"  {old_key} -> {new_label}")

        sys.exit(0)

    except (FileNotFoundError, ValueError) as e:
        logger.error(f"Label generation error: {e}")
        sys.exit(1)


def cmd_validate(args: argparse.Namespace) -> None:
    """Run validation checks on the biblatex library."""
    config = resolve_config(args)
    logger = logging.getLogger(__name__)

    if args.fix:
        logger.info("Starting validation and fixing citekeys")

        try:
            is_consistent = validate_citekey_consistency(
                bib_path=config.bib_path,
                add_order_path=config.add_order_path,
                identifier_path=config.identifier_path,
            )

            if not is_consistent:
                logger.error("✗ Cannot fix citekeys: consistency issues must be resolved first")
                sys.exit(1)

            fix_successful = fix_citekey_labels(
                bib_path=config.bib_path,
                add_order_path=config.add_order_path,
                identifier_path=config.identifier_path,
            )

            if fix_successful:
                logger.info("✓ All citekey fixes applied successfully")
                sys.exit(0)
            else:
                logger.error("✗ Failed to fix some citekeys")
                sys.exit(1)

        except (FileNotFoundError, ValueError) as e:
            logger.error(f"Fix error: {e}")
            sys.exit(1)
    else:
        logger.info("Starting validation checks")

        try:
            is_consistent = validate_citekey_consistency(
                bib_path=config.bib_path,
                add_order_path=config.add_order_path,
                identifier_path=config.identifier_path,
            )

            labels_valid = validate_citekey_labels(
                bib_path=config.bib_path, identifier_path=config.identifier_path
            )

            all_valid = is_consistent and labels_valid

            if all_valid:
                logger.info("✓ All validation checks passed")
                sys.exit(0)
            else:
                logger.error("✗ Validation checks failed")
                sys.exit(1)

        except (FileNotFoundError, ValueError) as e:
            logger.error(f"Validation error: {e}")
            sys.exit(1)


def cmd_sort(args: argparse.Namespace) -> None:
    """Sort library files."""
    config = resolve_config(args)
    logger = logging.getLogger(__name__)

    try:
        if args.mode == "alphabetical":
            logger.info("Sorting files alphabetically by citekey")
            sort_alphabetically(
                library_path=config.bib_path,
                identifier_path=config.identifier_path,
                add_order_path=config.add_order_path,
            )
        elif args.mode == "add-order":
            logger.info("Sorting files to match add_order.json sequence")
            sort_by_add_order(
                library_path=config.bib_path,
                identifier_path=config.identifier_path,
                add_order_path=config.add_order_path,
            )
        else:
            logger.error(f"Invalid sort mode: {args.mode}")
            sys.exit(1)

        logger.info("✓ Sort operation completed successfully")

    except (FileNotFoundError, ValueError) as e:
        logger.error(f"Sort error: {e}")
        sys.exit(1)


def cmd_sync(args: argparse.Namespace) -> None:
    """Sync identifier fields from identifier collection to library.bib."""
    config = resolve_config(args)
    logger = logging.getLogger(__name__)

    fields_to_sync = None
    if args.fields:
        fields_to_sync = set(field.strip() for field in args.fields.split(","))
        logger.info(f"Syncing specific fields: {', '.join(sorted(fields_to_sync))}")

    try:
        success, changes = sync_identifiers_to_library(
            bib_path=config.bib_path,
            identifier_path=config.identifier_path,
            dry_run=args.dry_run,
            fields_to_sync=fields_to_sync,
        )

        if success:
            if args.dry_run:
                logger.info(f"✓ Dry run completed: {len(changes)} potential changes")
                if changes:
                    logger.info("Changes that would be made:")
                    for change in changes[:10]:
                        logger.info(f"  {change}")
                    if len(changes) > 10:
                        logger.info(f"  ... and {len(changes) - 10} more changes")
            else:
                logger.info(f"✓ Sync completed: {len(changes)} changes applied")
            sys.exit(0)
        else:
            logger.error("✗ Sync failed")
            sys.exit(1)

    except (FileNotFoundError, ValueError) as e:
        logger.error(f"Sync error: {e}")
        sys.exit(1)


def _normalize_year_to_date(config: BiblioConfig, *, dry_run: bool, verbose: bool) -> None:
    logger = logging.getLogger(__name__)
    updated_count, updated_keys = rename_year_to_date_fields(config.bib_path, dry_run=dry_run)

    if dry_run:
        logger.info(
            "Dry run complete: %d entries would be converted from year to date",
            updated_count,
        )
    else:
        logger.info("✓ Converted %d entries from year to date fields", updated_count)

    if verbose and updated_keys:
        preview = ", ".join(updated_keys[:10])
        suffix = "..." if len(updated_keys) > 10 else ""
        logger.info("Affected entries: %s%s", preview, suffix)


def _normalize_publisher_location(config: BiblioConfig, *, dry_run: bool, verbose: bool) -> None:
    logger = logging.getLogger(__name__)
    report = normalize_publisher_location(config.bib_path, dry_run=dry_run)

    if report.fixed:
        message = (
            "Dry run complete: %d entries would have publisher/location split"
            if dry_run
            else "✓ Split publisher/location for %d entries"
        )
        logger.info(message, len(report.fixed))
        if verbose:
            preview = ", ".join(report.fixed[:10])
            suffix = "..." if len(report.fixed) > 10 else ""
            logger.info("Split entries: %s%s", preview, suffix)

    fixed_set = set(report.fixed)
    remaining = [key for key in report.flagged if key not in fixed_set]
    if remaining:
        preview = ", ".join(remaining[:10])
        suffix = "..." if len(remaining) > 10 else ""
        logger.warning("Entries with publisher but unresolved location: %s%s", preview, suffix)
    elif not report.fixed:
        logger.info("No publisher/location issues found")


def _normalize_eprint_fields(config: BiblioConfig, *, dry_run: bool, verbose: bool) -> None:
    logger = logging.getLogger(__name__)
    report = normalize_eprint_fields(config.bib_path, dry_run=dry_run)

    action_prefix = "Dry run complete" if dry_run else "✓ Applied"
    total_entries = len(
        set(report.renamed_type)
        | set(report.renamed_class)
        | set(report.normalized_type)
        | set(report.changed_entry_type)
    )

    if total_entries:
        logger.info(
            "%s: eprint field normalization touched %d entries",
            action_prefix,
            total_entries,
        )
    else:
        logger.info("%s: no eprint field changes required", action_prefix)

    details = [
        ("Renamed archiveprefix→eprinttype", report.renamed_type),
        ("Renamed primaryclass→eprintclass", report.renamed_class),
        ("Lowercased eprinttype", report.normalized_type),
        ("Changed entry type misc→online", report.changed_entry_type),
    ]

    for label, keys in details:
        if not keys:
            continue
        logger.info("%s for %d entries", label, len(keys))
        if verbose:
            preview = ", ".join(keys[:10])
            suffix = "..." if len(keys) > 10 else ""
            logger.info("  %s%s", preview, suffix)


def _normalize_latex_accents(config: BiblioConfig, *, dry_run: bool, verbose: bool) -> None:
    logger = logging.getLogger(__name__)
    report = normalize_latex_accents(config.bib_path, dry_run=dry_run)

    action_prefix = "Dry run complete" if dry_run else "✓ Applied"
    if report.total_fields:
        logger.info(
            "%s: normalized LaTeX text in %d fields across %d entries",
            action_prefix,
            report.total_fields,
            len(report.converted),
        )
    else:
        logger.info("%s: no LaTeX text changes required", action_prefix)

    if verbose and report.total_fields:
        preview_items = list(report.converted.items())[:5]
        for key, fields in preview_items:
            logger.info("%s: %s", key, ", ".join(fields))
        remaining = len(report.converted) - len(preview_items)
        if remaining > 0:
            logger.info("... and %d more entries", remaining)


def _normalize_isbn(config: BiblioConfig, *, dry_run: bool, verbose: bool) -> None:
    logger = logging.getLogger(__name__)
    report = normalize_isbn_fields(config.bib_path, config.identifier_path, dry_run=dry_run)

    action_prefix = "Dry run complete" if dry_run else "✓ Applied"
    if report.total_converted:
        logger.info(
            "%s: converted %d ISBN-10 values to ISBN-13 across %d entries",
            action_prefix,
            report.total_converted,
            len(report.converted),
        )
    else:
        logger.info("%s: no ISBN conversions required", action_prefix)

    if report.already_isbn13:
        logger.info(
            "%d entries already have valid ISBN-13 values",
            len(report.already_isbn13),
        )

    if report.invalid:
        logger.warning(
            "%d entries have invalid ISBN values that couldn't be converted",
            len(report.invalid),
        )
        if verbose:
            for key, value in list(report.invalid.items())[:5]:
                logger.warning("  %s: %s", key, value)

    if report.identifier_converted:
        logger.info(
            "%s: converted %d isbn13 values in identifier_collection.json",
            action_prefix,
            len(report.identifier_converted),
        )
        if verbose:
            for key, change in list(report.identifier_converted.items())[:5]:
                logger.info("  %s: %s", key, change)
            remaining = len(report.identifier_converted) - 5
            if remaining > 0:
                logger.info("  ... and %d more entries", remaining)

    if verbose and report.converted:
        preview_items = list(report.converted.items())[:5]
        for key, conversions in preview_items:
            logger.info("%s: %s", key, "; ".join(conversions))
        remaining = len(report.converted) - len(preview_items)
        if remaining > 0:
            logger.info("... and %d more entries", remaining)


def _normalize_trivial_url(config: BiblioConfig, *, dry_run: bool, verbose: bool) -> None:
    logger = logging.getLogger(__name__)
    report = normalize_trivial_urls(config.bib_path, dry_run=dry_run)

    action_prefix = "Dry run complete" if dry_run else "✓ Applied"
    if report.removed:
        logger.info(
            "%s: removed %d trivial DOI-derived URL fields",
            action_prefix,
            len(report.removed),
        )
    else:
        logger.info("%s: no trivial URL fields found", action_prefix)

    if verbose and report.removed:
        preview = ", ".join(report.removed[:10])
        suffix = "..." if len(report.removed) > 10 else ""
        logger.info("Removed URL from: %s%s", preview, suffix)


_NORMALIZE_ACTIONS = {
    "year-to-date": _normalize_year_to_date,
    "publisher-location": _normalize_publisher_location,
    "eprint-fields": _normalize_eprint_fields,
    "latex-accents": _normalize_latex_accents,
    "isbn": _normalize_isbn,
    "trivial-url": _normalize_trivial_url,
}


def cmd_normalize(args: argparse.Namespace) -> None:
    """Apply normalization routines to the library."""
    config = resolve_config(args)
    logger = logging.getLogger(__name__)

    actions = [args.action] if args.action else list(_NORMALIZE_ACTIONS)
    run_all = args.action is None

    try:
        for action in actions:
            if run_all:
                logger.info("Running normalization: %s", action)
            handler = _NORMALIZE_ACTIONS[action]
            handler(config, dry_run=args.dry_run, verbose=bool(args.verbose))

        if run_all:
            logger.info("✓ All normalizations completed")
        sys.exit(0)

    except (FileNotFoundError, ValueError) as exc:
        logger.error(f"Normalize error: {exc}")
        sys.exit(1)


def cmd_add(args: argparse.Namespace) -> None:
    """Add new entries from staging files to the main library."""
    config = resolve_config(args)
    logger = logging.getLogger(__name__)

    try:
        success, processed_slugs = add_entries_from_staging(config=config)

        if success:
            if processed_slugs:
                logger.info(f"✓ Successfully added {len(processed_slugs)} new entries")
                logger.info(f"Processed files: {', '.join(processed_slugs)}")
            else:
                logger.info("✓ No new entries to add")
            sys.exit(0)
        else:
            logger.error("✗ Failed to add entries")
            sys.exit(1)

    except (FileNotFoundError, ValueError) as e:
        logger.error(f"Add entries error: {e}")
        sys.exit(1)


def cmd_template(args: argparse.Namespace) -> None:
    """Generate identifier collection templates for staging .bib files."""
    config = resolve_config(args)
    logger = logging.getLogger(__name__)

    try:
        files_processed, generated_files = generate_staging_templates(
            config=config, overwrite=args.overwrite
        )

        if files_processed > 0:
            logger.info(f"✓ Generated {files_processed} identifier templates")
            logger.info(f"Created files: {', '.join(generated_files)}")
        else:
            logger.info("✓ No templates to generate (all .bib files already have .json companions)")

        sys.exit(0)

    except (FileNotFoundError, ValueError) as e:
        logger.error(f"Template generation error: {e}")
        sys.exit(1)


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser for the CLI."""
    parser = argparse.ArgumentParser(
        prog="biblio",
        description="Tools for a curated biblatex library: validate, sort, sync, normalize.",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase verbosity (use -v for INFO, -vv for DEBUG)",
    )

    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to biblio.toml config file (default: auto-discover from CWD upward)",
    )

    parser.add_argument(
        "--bib",
        type=str,
        default=None,
        help="Override path to .bib file",
    )

    parser.add_argument(
        "--identifiers",
        type=str,
        default=None,
        help="Override path to identifier collection JSON file",
    )

    parser.add_argument(
        "--add-order",
        type=str,
        default=None,
        dest="add_order",
        help="Override path to add_order JSON file",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # init subcommand
    init_parser = subparsers.add_parser(
        "init", help="Initialize a new biblio workspace with config and empty data files"
    )
    init_parser.add_argument(
        "dir",
        nargs="?",
        default=None,
        help="Directory to initialize (default: current directory)",
    )
    init_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing biblio.toml",
    )
    init_parser.set_defaults(func=cmd_init)

    # validate subcommand
    validate_parser = subparsers.add_parser(
        "validate", help="Validate library files for consistency and correctness"
    )
    validate_parser.add_argument(
        "--fix",
        action="store_true",
        help="Automatically fix citekeys that don't match generated labels",
    )
    validate_parser.set_defaults(func=cmd_validate)

    # generate-labels subcommand
    generate_parser = subparsers.add_parser(
        "generate-labels", help="Generate labels for biblatex entries"
    )
    generate_parser.add_argument(
        "-o", "--output", type=str, help="Output file path (default: bib/generated/labels.json)"
    )
    generate_parser.set_defaults(func=cmd_generate_labels)

    # sort subcommand
    sort_parser = subparsers.add_parser("sort", help="Sort library files by citekey")
    sort_parser.add_argument(
        "mode",
        nargs="?",
        default="alphabetical",
        choices=["alphabetical", "add-order"],
        help="Sort mode: 'alphabetical' sorts by citekey alphabetically (default), "
        + "'add-order' sorts to match add_order.json sequence",
    )
    sort_parser.set_defaults(func=cmd_sort)

    # sync subcommand
    sync_parser = subparsers.add_parser(
        "sync", help="Sync identifier fields from identifier collection to library.bib"
    )
    sync_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what changes would be made without actually making them",
    )
    sync_parser.add_argument(
        "--fields",
        type=str,
        help="Comma-separated list of fields to sync (default: isbn,doi,url,arxiv,mrnumber,zbl)",
    )
    sync_parser.set_defaults(func=cmd_sync)

    # normalize subcommand
    normalize_parser = subparsers.add_parser(
        "normalize", help="Apply normalization routines to library data"
    )
    normalize_parser.add_argument(
        "action",
        nargs="?",
        default=None,
        choices=[
            "year-to-date",
            "publisher-location",
            "eprint-fields",
            "latex-accents",
            "isbn",
            "trivial-url",
        ],
        help=(
            "Choose normalization action (omit to run all). "
            "'year-to-date' renames entries with year but no date "
            "to use the date field. 'publisher-location' splits combined publisher/location "
            "values and flags missing locations. 'eprint-fields' migrates legacy arXiv fields "
            "and normalizes the eprinttype value. 'latex-accents' converts LaTeX accent "
            "commands into Unicode and normalizes mrreviewer control spaces. 'isbn' converts "
            "ISBN-10 values to ISBN-13 format. 'trivial-url' removes URL fields that are just "
            "doi.org/{doi}."
        ),
    )
    normalize_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without modifying files",
    )
    normalize_parser.set_defaults(func=cmd_normalize)

    # add subcommand
    add_parser = subparsers.add_parser(
        "add", help="Add new entries from staging files to the main library"
    )
    add_parser.set_defaults(func=cmd_add)

    # template subcommand
    template_parser = subparsers.add_parser(
        "template", help="Generate identifier collection templates for staging .bib files"
    )
    template_parser.add_argument(
        "--overwrite",
        action="store_true",
        help=(
            "Overwrite existing .json files "
            "(default: skip files that already have .json companions)"
        ),
    )
    template_parser.set_defaults(func=cmd_template)

    return parser


def main() -> None:
    """Main entry point for the biblio CLI."""
    parser = create_parser()
    args = parser.parse_args()

    # Setup logging based on verbosity
    setup_logging(args.verbose)

    # Handle case where no subcommand is provided
    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)

    # Execute the subcommand
    args.func(args)


if __name__ == "__main__":
    main()
