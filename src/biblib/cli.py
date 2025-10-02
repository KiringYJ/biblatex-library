"""Command-line interface for biblatex library tools."""

import argparse
import json
import logging
import sys
from pathlib import Path

from .add_entries import add_entries_from_staging
from .generate import generate_labels
from .normalize.accents import normalize_latex_accents
from .normalize.dates import rename_year_to_date_fields
from .normalize.eprint import normalize_eprint_fields
from .normalize.publisher import normalize_publisher_location
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


def cmd_generate_labels(args: argparse.Namespace) -> None:
    """Generate labels for biblatex entries."""
    workspace = Path(args.workspace)

    # Default paths based on standard repository layout
    bib_path = workspace / "bib" / "library.bib"
    identifier_path = workspace / "data" / "identifier_collection.json"
    default_output = workspace / "bib" / "generated" / "labels.json"
    output_path = Path(args.output) if args.output else default_output

    logger = logging.getLogger(__name__)
    logger.info("Generating labels for biblatex entries")

    try:
        # Generate labels
        labels = generate_labels(bib_path=bib_path, identifier_path=identifier_path)

        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Save labels to JSON file
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(labels, f, indent=2, ensure_ascii=False)

        logger.info(f"✓ Generated {len(labels)} labels")
        logger.info(f"✓ Saved to: {output_path}")

        # Optionally show first few labels for verification
        if args.verbose and labels:
            logger.info("Sample labels:")
            for i, (old_key, new_label) in enumerate(labels.items()):
                if i >= 5:  # Show first 5 as examples
                    break
                logger.info(f"  {old_key} -> {new_label}")

        sys.exit(0)

    except (FileNotFoundError, ValueError) as e:
        logger.error(f"Label generation error: {e}")
        sys.exit(1)


def cmd_validate(args: argparse.Namespace) -> None:
    """Run validation checks on the biblatex library."""
    workspace = Path(args.workspace)

    # Default paths based on standard repository layout
    bib_path = workspace / "bib" / "library.bib"
    add_order_path = workspace / "data" / "add_order.json"
    identifier_path = workspace / "data" / "identifier_collection.json"

    logger = logging.getLogger(__name__)

    if args.fix:
        logger.info("Starting validation and fixing citekeys")

        try:
            # Run citekey consistency validation first
            is_consistent = validate_citekey_consistency(
                bib_path=bib_path, add_order_path=add_order_path, identifier_path=identifier_path
            )

            if not is_consistent:
                logger.error("✗ Cannot fix citekeys: consistency issues must be resolved first")
                sys.exit(1)

            # Fix citekey labels
            fix_successful = fix_citekey_labels(
                bib_path=bib_path, add_order_path=add_order_path, identifier_path=identifier_path
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
            # Run citekey consistency validation
            is_consistent = validate_citekey_consistency(
                bib_path=bib_path, add_order_path=add_order_path, identifier_path=identifier_path
            )

            # Run citekey label validation (check if existing keys match generated labels)
            labels_valid = validate_citekey_labels(
                bib_path=bib_path, identifier_path=identifier_path
            )

            # Check if all validations passed
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
    workspace = Path(args.workspace)

    # Default paths based on standard repository layout
    bib_path = workspace / "bib" / "library.bib"
    add_order_path = workspace / "data" / "add_order.json"
    identifier_path = workspace / "data" / "identifier_collection.json"

    logger = logging.getLogger(__name__)

    try:
        if args.mode == "alphabetical":
            logger.info("Sorting files alphabetically by citekey")
            sort_alphabetically(
                library_path=bib_path,
                identifier_path=identifier_path,
                add_order_path=add_order_path,
            )
        elif args.mode == "add-order":
            logger.info("Sorting files to match add_order.json sequence")
            sort_by_add_order(
                library_path=bib_path,
                identifier_path=identifier_path,
                add_order_path=add_order_path,
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
    workspace = Path(args.workspace)

    # Default paths based on standard repository layout
    bib_path = workspace / "bib" / "library.bib"
    identifier_path = workspace / "data" / "identifier_collection.json"

    logger = logging.getLogger(__name__)

    # Parse fields to sync if provided
    fields_to_sync = None
    if args.fields:
        fields_to_sync = set(field.strip() for field in args.fields.split(","))
        logger.info(f"Syncing specific fields: {', '.join(sorted(fields_to_sync))}")

    try:
        success, changes = sync_identifiers_to_library(
            bib_path=bib_path,
            identifier_path=identifier_path,
            dry_run=args.dry_run,
            fields_to_sync=fields_to_sync,
        )

        if success:
            if args.dry_run:
                logger.info(f"✓ Dry run completed: {len(changes)} potential changes")
                if changes:
                    logger.info("Changes that would be made:")
                    for change in changes[:10]:  # Show first 10 changes
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


def cmd_normalize(args: argparse.Namespace) -> None:
    """Apply normalization routines to the library."""
    workspace = Path(args.workspace)

    bib_path = workspace / "bib" / "library.bib"

    logger = logging.getLogger(__name__)

    try:
        if args.action == "year-to-date":
            updated_count, updated_keys = rename_year_to_date_fields(bib_path, dry_run=args.dry_run)

            if args.dry_run:
                logger.info(
                    "Dry run complete: %d entries would be converted from year to date",
                    updated_count,
                )
            else:
                logger.info(
                    "✓ Converted %d entries from year to date fields",
                    updated_count,
                )

            if args.verbose and updated_keys:
                preview = ", ".join(updated_keys[:10])
                suffix = "..." if len(updated_keys) > 10 else ""
                logger.info("Affected entries: %s%s", preview, suffix)

            sys.exit(0)

        if args.action == "publisher-location":
            report = normalize_publisher_location(bib_path, dry_run=args.dry_run)

            if report.fixed:
                message = (
                    "Dry run complete: %d entries would have publisher/location split"
                    if args.dry_run
                    else "✓ Split publisher/location for %d entries"
                )
                logger.info(message, len(report.fixed))
                if args.verbose:
                    preview = ", ".join(report.fixed[:10])
                    suffix = "..." if len(report.fixed) > 10 else ""
                    logger.info("Split entries: %s%s", preview, suffix)

            fixed_set = set(report.fixed)
            remaining = [key for key in report.flagged if key not in fixed_set]
            if remaining:
                preview = ", ".join(remaining[:10])
                suffix = "..." if len(remaining) > 10 else ""
                logger.warning(
                    "Entries with publisher but unresolved location: %s%s", preview, suffix
                )
            elif not report.fixed:
                logger.info("No publisher/location issues found")

            sys.exit(0)

        if args.action == "eprint-fields":
            report = normalize_eprint_fields(bib_path, dry_run=args.dry_run)

            action_prefix = "Dry run complete" if args.dry_run else "✓ Applied"
            total_entries = len(
                set(report.renamed_type) | set(report.renamed_class) | set(report.normalized_type)
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
            ]

            for label, keys in details:
                if not keys:
                    continue
                logger.info("%s for %d entries", label, len(keys))
                if args.verbose:
                    preview = ", ".join(keys[:10])
                    suffix = "..." if len(keys) > 10 else ""
                    logger.info("  %s%s", preview, suffix)

            sys.exit(0)

        if args.action == "latex-accents":
            report = normalize_latex_accents(bib_path, dry_run=args.dry_run)

            action_prefix = "Dry run complete" if args.dry_run else "✓ Applied"
            if report.total_fields:
                logger.info(
                    "%s: converted LaTeX accents in %d fields across %d entries",
                    action_prefix,
                    report.total_fields,
                    len(report.converted),
                )
            else:
                logger.info("%s: no LaTeX accent changes required", action_prefix)

            if args.verbose and report.total_fields:
                preview_items = list(report.converted.items())[:5]
                for key, fields in preview_items:
                    logger.info("%s: %s", key, ", ".join(fields))
                remaining = len(report.converted) - len(preview_items)
                if remaining > 0:
                    logger.info("... and %d more entries", remaining)

            sys.exit(0)

        logger.error(f"Unknown normalization action: {args.action}")
        sys.exit(1)

    except (FileNotFoundError, ValueError) as exc:
        logger.error(f"Normalize error: {exc}")
        sys.exit(1)


def cmd_add(args: argparse.Namespace) -> None:
    """Add new entries from staging files to the main library."""
    workspace = Path(args.workspace)
    logger = logging.getLogger(__name__)

    try:
        success, processed_slugs = add_entries_from_staging(workspace=workspace)

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
    workspace = Path(args.workspace)
    logger = logging.getLogger(__name__)

    try:
        files_processed, generated_files = generate_staging_templates(
            workspace=workspace, overwrite=args.overwrite
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
        prog="blx",
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
        "--workspace",
        type=str,
        default=".",
        help="Path to the workspace directory (default: current directory)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

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
        choices=["year-to-date", "publisher-location", "eprint-fields", "latex-accents"],
        help=(
            "Choose normalization action. 'year-to-date' renames entries with year but no date "
            "to use the date field. 'publisher-location' splits combined publisher/location "
            "values and flags missing locations. 'eprint-fields' migrates legacy arXiv fields "
            "and normalizes the eprinttype value. 'latex-accents' converts LaTeX accent "
            "commands into their Unicode equivalents."
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
    """Main entry point for the blx CLI."""
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
