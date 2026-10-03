"""Error types shared by every module. MCP tool handlers surface the message to the caller."""


class AdlcError(Exception):
    """Base error."""


class AuthError(AdlcError):
    """The caller could not be authenticated."""


class PermissionDenied(AdlcError):
    """An authenticated caller attempted something its identity does not permit."""


class ValidationError(AdlcError):
    """Input violates the schema or a platform rule."""


class NotFound(AdlcError):
    """A referenced record does not exist."""
