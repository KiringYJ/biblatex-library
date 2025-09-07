"""Custom exception types for biblib operations."""


class BiblibError(Exception):
    """Base exception for all biblib operations."""


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
