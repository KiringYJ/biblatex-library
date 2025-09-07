"""Type stubs for bibtexparser package."""

from pathlib import Path

from .library import Library
from .model import Entry

def parse_file(file_path: str | Path) -> Library: ...
def write_string(library: Library) -> str: ...

__all__ = ["parse_file", "write_string", "Library", "Entry"]
