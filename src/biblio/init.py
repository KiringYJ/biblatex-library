"""Initialize a biblio consumer workspace."""

import logging
from pathlib import Path

from .config import CONFIG_FILENAME

logger = logging.getLogger(__name__)

_DEFAULT_TOML = """\
# biblio workspace configuration
# All paths are relative to this file's directory.

[paths]
bib = "bib/library.bib"
identifiers = "data/identifier_collection.json"
add_order = "data/add_order.json"
staging = "staging"
"""

_EMPTY_BIB = """\
% biblatex library — managed by biblio
% Add entries via `biblio add` or edit directly.
"""


def init_workspace(target: Path, *, force: bool = False) -> list[str]:
    """Create config, required data files, and the staging directory."""
    resolved_target = target.resolve()
    created: list[str] = []
    toml_path = resolved_target / CONFIG_FILENAME
    if toml_path.exists() and not force:
        raise FileExistsError(
            f"{CONFIG_FILENAME} already exists in {resolved_target}. Use --force to overwrite."
        )

    (resolved_target / "bib").mkdir(parents=True, exist_ok=True)
    (resolved_target / "data").mkdir(parents=True, exist_ok=True)
    (resolved_target / "staging").mkdir(parents=True, exist_ok=True)

    toml_path.write_text(_DEFAULT_TOML, encoding="utf-8", newline="\n")
    created.append(CONFIG_FILENAME)

    data_files = {
        "bib/library.bib": _EMPTY_BIB,
        "data/identifier_collection.json": "{}\n",
        "data/add_order.json": "[]\n",
    }
    for relative_name, content in data_files.items():
        path = resolved_target / relative_name
        if path.exists():
            logger.info("Skipping existing file: %s", relative_name)
            continue
        path.write_text(content, encoding="utf-8", newline="\n")
        created.append(relative_name)

    return created
