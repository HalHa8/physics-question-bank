"""Errors shared by paper validation and HTTP exports."""

class PaperExportValidationError(ValueError):
    """Raised when a paper export request cannot describe a complete paper."""
