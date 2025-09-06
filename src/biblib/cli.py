"""Command-line interface for biblatex library tools."""

import argparse
import logging
import sys
from pathlib import Path

from .validate import validate_citekey_consistency


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


def cmd_validate(args: argparse.Namespace) -> None:
    """Run validation checks on the biblatex library."""
    workspace = Path(args.workspace)

    # Default paths based on standard repository layout
    bib_path = workspace / "bib" / "library.bib"
    add_order_path = workspace / "data" / "add_order.json"
    identifier_path = workspace / "data" / "identifier_collection.json"

    logger = logging.getLogger(__name__)
    logger.info("Starting validation checks")

    try:
        # Run citekey consistency validation
        is_consistent = validate_citekey_consistency(
            bib_path=bib_path, add_order_path=add_order_path, identifier_path=identifier_path
        )

        if is_consistent:
            logger.info("✓ All validation checks passed")
            sys.exit(0)
        else:
            logger.error("✗ Validation checks failed")
            sys.exit(1)

    except (FileNotFoundError, ValueError) as e:
        logger.error("Validation error: %s", e)
        sys.exit(1)


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser for the CLI."""
    parser = argparse.ArgumentParser(
        prog="blx",
        description="Tools for a curated biblatex library: validate, sort, convert, enrich.",
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
    validate_parser.set_defaults(func=cmd_validate)

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
