"""Command-line interface for biblatex library tools."""

import argparse
import json
import logging
import sys
from pathlib import Path

from .generate import generate_labels
from .sort import sort_alphabetically, sort_by_add_order
from .sync import sync_identifiers_to_library
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

        logger.info("✓ Generated %d labels", len(labels))
        logger.info("✓ Saved to: %s", output_path)

        # Optionally show first few labels for verification
        if args.verbose and labels:
            logger.info("Sample labels:")
            for i, (old_key, new_label) in enumerate(labels.items()):
                if i >= 5:  # Show first 5 as examples
                    break
                logger.info("  %s -> %s", old_key, new_label)

        sys.exit(0)

    except (FileNotFoundError, ValueError) as e:
        logger.error("Label generation error: %s", e)
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
            logger.error("Fix error: %s", e)
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
            logger.error("Validation error: %s", e)
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
            logger.error("Invalid sort mode: %s", args.mode)
            sys.exit(1)

        logger.info("✓ Sort operation completed successfully")

    except (FileNotFoundError, ValueError) as e:
        logger.error("Sort error: %s", e)
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
        logger.info("Syncing specific fields: %s", ", ".join(sorted(fields_to_sync)))

    try:
        success, changes = sync_identifiers_to_library(
            bib_path=bib_path,
            identifier_path=identifier_path,
            dry_run=args.dry_run,
            fields_to_sync=fields_to_sync,
        )

        if success:
            if args.dry_run:
                logger.info("✓ Dry run completed: %d potential changes", len(changes))
                if changes:
                    logger.info("Changes that would be made:")
                    for change in changes[:10]:  # Show first 10 changes
                        logger.info("  %s", change)
                    if len(changes) > 10:
                        logger.info("  ... and %d more changes", len(changes) - 10)
            else:
                logger.info("✓ Sync completed: %d changes applied", len(changes))
            sys.exit(0)
        else:
            logger.error("✗ Sync failed")
            sys.exit(1)

    except (FileNotFoundError, ValueError) as e:
        logger.error("Sync error: %s", e)
        sys.exit(1)


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser for the CLI."""
    parser = argparse.ArgumentParser(
        prog="blx",
        description="Tools for a curated biblatex library: validate, sort, sync, enrich.",
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
        "'add-order' sorts to match add_order.json sequence",
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
