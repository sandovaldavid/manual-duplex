class ManualDuplexError(RuntimeError):
    """Base error for user-facing manual-duplex failures."""


class ConfigurationError(ManualDuplexError):
    """Raised when printer or profile configuration is incomplete."""


class CommandError(ManualDuplexError):
    """Raised when an external command fails."""
