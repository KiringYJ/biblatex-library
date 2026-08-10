"""Configurable tools for maintaining BibLaTeX workspaces."""

import logging

from biblio._version import __version__

__all__ = ["__version__"]

# Install a NullHandler to avoid emitting logs unless the application configures logging
logging.getLogger(__name__).addHandler(logging.NullHandler())
