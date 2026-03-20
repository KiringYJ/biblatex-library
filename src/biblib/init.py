"""Initialize a new blx workspace."""

import logging
from pathlib import Path

from .config import CONFIG_FILENAME

logger = logging.getLogger(__name__)

_DEFAULT_TOML = """\
# blx workspace configuration
# All paths are relative to this file's directory.

[paths]
bib = "bib/library.bib"
identifiers = "data/identifier_collection.json"
add_order = "data/add_order.json"
staging = "staging"
"""

_EMPTY_BIB = """\
% biblatex library — managed by blx
% Add entries via `blx add` or edit directly.
"""


def init_workspace(target: Path, *, force: bool = False) -> list[str]:
    """Scaffold a new blx workspace.

    Args:
        target: Directory to initialize
        force: Overwrite existing blx.toml if present

    Returns:
        List of created file paths (relative to target)
    """
    target = target.resolve()
    created: list[str] = []

    toml_path = target / CONFIG_FILENAME
    if toml_path.exists() and not force:
        msg = f"{CONFIG_FILENAME} already exists in {target}. Use --force to overwrite."
        raise FileExistsError(msg)

    # Create directories
    for subdir in ["bib", "data", "staging"]:
        (target / subdir).mkdir(parents=True, exist_ok=True)

    # Write config file
    toml_path.write_text(_DEFAULT_TOML, encoding="utf-8")
    created.append(CONFIG_FILENAME)

    # Write empty data files (only if they don't exist)
    data_files: dict[str, str] = {
        "bib/library.bib": _EMPTY_BIB,
        "data/identifier_collection.json": "{}\n",
        "data/add_order.json": "[]\n",
    }

    for rel_path, content in data_files.items():
        full_path = target / rel_path
        if not full_path.exists():
            full_path.write_text(content, encoding="utf-8")
            created.append(rel_path)
        else:
            logger.info("Skipping existing file: %s", rel_path)

    return created
