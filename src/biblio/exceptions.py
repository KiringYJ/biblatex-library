"""Custom exception types for biblio operations."""


class BiblioError(Exception):
    """Base exception for all biblio operations."""


class ConfigError(BiblioError):
    """Raised when biblio configuration is invalid."""
