"""Workspace configuration for the biblio engine."""

import logging
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .exceptions import ConfigError

logger = logging.getLogger(__name__)

CONFIG_FILENAME = "biblio.toml"

_DEFAULT_BIB = "bib/library.bib"
_DEFAULT_IDENTIFIERS = "data/identifier_collection.json"
_DEFAULT_ADD_ORDER = "data/add_order.json"
_DEFAULT_STAGING = "staging"
_PATH_KEYS = frozenset({"bib", "identifiers", "add_order", "staging"})


@dataclass(frozen=True, slots=True)
class BiblioConfig:
    """Resolved paths used by the bibliography engine."""

    root: Path
    bib_path: Path
    identifier_path: Path
    add_order_path: Path
    staging_dir: Path

    @classmethod
    def defaults(cls, root: Path) -> "BiblioConfig":
        """Create the standard layout rooted at ``root``."""
        resolved_root = root.resolve()
        return cls(
            root=resolved_root,
            bib_path=resolved_root / _DEFAULT_BIB,
            identifier_path=resolved_root / _DEFAULT_IDENTIFIERS,
            add_order_path=resolved_root / _DEFAULT_ADD_ORDER,
            staging_dir=resolved_root / _DEFAULT_STAGING,
        )

    @classmethod
    def from_toml(cls, toml_path: Path) -> "BiblioConfig":
        """Load paths from ``biblio.toml`` relative to its directory."""
        resolved_toml = toml_path.resolve()
        root = resolved_toml.parent

        with resolved_toml.open("rb") as stream:
            raw = tomllib.load(stream)

        paths_raw = raw.get("paths")
        paths: dict[str, str] = {}
        if paths_raw is not None:
            if not isinstance(paths_raw, dict):
                raise ConfigError(f"[paths] in {resolved_toml} must be a table")
            for key, value in paths_raw.items():
                if not isinstance(key, str) or not isinstance(value, str):
                    raise ConfigError(f"All [paths] values in {resolved_toml} must be strings")
                if key not in _PATH_KEYS:
                    raise ConfigError(f"Unsupported [paths] key in {resolved_toml}: {key}")
                paths[key] = value

        def resolve_path(key: str, default: str) -> Path:
            path = Path(paths.get(key, default))
            return path.resolve() if path.is_absolute() else (root / path).resolve()

        return cls(
            root=root,
            bib_path=resolve_path("bib", _DEFAULT_BIB),
            identifier_path=resolve_path("identifiers", _DEFAULT_IDENTIFIERS),
            add_order_path=resolve_path("add_order", _DEFAULT_ADD_ORDER),
            staging_dir=resolve_path("staging", _DEFAULT_STAGING),
        )

    @classmethod
    def discover(cls, start: Path | None = None) -> "BiblioConfig":
        """Discover ``biblio.toml`` upward, or use defaults at ``start``."""
        origin = (start or Path.cwd()).resolve()
        current = origin
        while True:
            candidate = current / CONFIG_FILENAME
            if candidate.is_file():
                logger.debug("Found config: %s", candidate)
                return cls.from_toml(candidate)
            if current.parent == current:
                break
            current = current.parent

        logger.debug("No %s found, using defaults rooted at %s", CONFIG_FILENAME, origin)
        return cls.defaults(origin)

    def with_overrides(
        self,
        *,
        bib_path: Path | None = None,
        identifier_path: Path | None = None,
        add_order_path: Path | None = None,
        staging_dir: Path | None = None,
    ) -> "BiblioConfig":
        """Return a copy with explicitly supplied normal-runtime paths."""
        return BiblioConfig(
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
