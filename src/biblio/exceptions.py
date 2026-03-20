"""Custom exception types for biblio operations."""


class BiblibError(Exception):
    """Base exception for all biblio operations."""


class FileOperationError(BiblibError):
    """Raised when file I/O operations fail."""


class InvalidDataError(BiblibError):
    """Raised when data validation fails."""


class ValidationError(BiblibError):
    """Raised when validation checks fail."""


class ProcessingError(BiblibError):
    """Raised when processing operations fail."""


class BackupError(BiblibError):
    """Raised when backup operations fail."""


class ConfigError(BiblibError):
    """Raised when biblio configuration is invalid."""
