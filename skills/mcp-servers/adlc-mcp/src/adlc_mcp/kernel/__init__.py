"""Shared kernel: small and stable. Becomes a tiny shared library when a module is extracted.

Must never import from ``adlc_mcp.modules`` (enforced by tests/test_module_boundaries.py).
"""
from .config import Config, KNOWN_MODULES
from .errors import AdlcError, AuthError, NotFound, PermissionDenied, ValidationError
from .identity import Identity, hash_token, issue_credential, resolve_identity, system_identity
from .module import Module, ModuleRegistry

__all__ = [
    "AdlcError", "AuthError", "Config", "Identity", "KNOWN_MODULES", "Module", "ModuleRegistry",
    "NotFound", "PermissionDenied", "ValidationError", "hash_token", "issue_credential",
    "resolve_identity", "system_identity",
]
