"""Workspace configuration for biblib operations."""

import logging
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .exceptions import ConfigError

logger = logging.getLogger(__name__)

CONFIG_FILENAME = "blx.toml"

# Default relative paths (matching original repo layout)
_DEFAULT_BIB = "bib/library.bib"
_DEFAULT_IDENTIFIERS = "data/identifier_collection.json"
_DEFAULT_ADD_ORDER = "data/add_order.json"
_DEFAULT_STAGING = "staging"


@dataclass
class BlxConfig:
    """Resolved configuration for all blx operations.

    All paths are absolute after construction.
    """

    root: Path
    bib_path: Path
    identifier_path: Path
    add_order_path: Path
    staging_dir: Path

    @classmethod
    def defaults(cls, root: Path) -> "BlxConfig":
        """Create config with default paths rooted at the given directory."""
        root = root.resolve()
        return cls(
            root=root,
            bib_path=root / "bib" / "library.bib",
            identifier_path=root / "data" / "identifier_collection.json",
            add_order_path=root / "data" / "add_order.json",
            staging_dir=root / "staging",
        )

    @classmethod
    def from_toml(cls, toml_path: Path) -> "BlxConfig":
        """Parse a blx.toml file and resolve paths relative to its directory."""
        toml_path = toml_path.resolve()
        root = toml_path.parent

        with open(toml_path, "rb") as f:
            raw = tomllib.load(f)

        paths_raw = raw.get("paths")
        paths: dict[str, str] = {}

        if paths_raw is not None:
            if not isinstance(paths_raw, dict):
                msg = f"[paths] in {toml_path} must be a table"
                raise ConfigError(msg)
            for key, value in paths_raw.items():
                if not isinstance(key, str) or not isinstance(value, str):
                    msg = f"All [paths] values in {toml_path} must be strings"
                    raise ConfigError(msg)
                paths[key] = value

        def _resolve(key: str, default: str) -> Path:
            value = paths.get(key, default)
            p = Path(value)
            if p.is_absolute():
                return p
            return (root / p).resolve()

        return cls(
            root=root,
            bib_path=_resolve("bib", _DEFAULT_BIB),
            identifier_path=_resolve("identifiers", _DEFAULT_IDENTIFIERS),
            add_order_path=_resolve("add_order", _DEFAULT_ADD_ORDER),
            staging_dir=_resolve("staging", _DEFAULT_STAGING),
        )

    @classmethod
    def discover(cls, start: Path | None = None) -> "BlxConfig":
        """Find blx.toml by walking up from start (default: CWD).

        Falls back to defaults rooted at start if no config file found.
        """
        origin = (start or Path.cwd()).resolve()
        current = origin

        while True:
            candidate = current / CONFIG_FILENAME
            if candidate.is_file():
                logger.debug("Found config: %s", candidate)
                return cls.from_toml(candidate)
            parent = current.parent
            if parent == current:
                break
            current = parent

        logger.debug("No %s found, using defaults rooted at %s", CONFIG_FILENAME, origin)
        return cls.defaults(origin)

    def with_overrides(
        self,
        *,
        bib_path: Path | None = None,
        identifier_path: Path | None = None,
        add_order_path: Path | None = None,
        staging_dir: Path | None = None,
    ) -> "BlxConfig":
        """Return a new config with non-None values overriding the originals."""
        return BlxConfig(
            root=self.root,
            bib_path=bib_path.resolve() if bib_path is not None else self.bib_path,
            identifier_path=(
                identifier_path.resolve() if identifier_path is not None else self.identifier_path
            ),
            add_order_path=(
                add_order_path.resolve() if add_order_path is not None else self.add_order_path
            ),
            staging_dir=staging_dir.resolve() if staging_dir is not None else self.staging_dir,
        )

    @staticmethod
    def schema_path() -> Path:
        """Return path to the bundled identifier_collection schema."""
        return Path(__file__).parent / "schema" / "identifier_collection.schema.json"
