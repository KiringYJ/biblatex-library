"""Workspace configuration for biblib operations."""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class WorkspaceConfig:
    """Configuration for workspace file paths."""

    bib_path: Path
    identifier_path: Path
    add_order_path: Path
    staging_dir: Path

    @classmethod
    def from_workspace(cls, workspace: Path) -> "WorkspaceConfig":
        """Create configuration from workspace root path.

        Args:
            workspace: Path to workspace root directory

        Returns:
            WorkspaceConfig with standard file paths
        """
        return cls(
            bib_path=workspace / "bib" / "library.bib",
            identifier_path=workspace / "data" / "identifier_collection.json",
            add_order_path=workspace / "data" / "add_order.json",
            staging_dir=workspace / "staging",
        )
