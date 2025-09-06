"""Biblatex library tools package."""

import logging

# Install a NullHandler to avoid emitting logs unless the application configures logging
logging.getLogger(__name__).addHandler(logging.NullHandler())
