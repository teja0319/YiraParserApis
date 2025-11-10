"""
Utilities for working with tenant context during a request lifecycle.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Optional


_tenant_context: ContextVar[Optional[str]] = ContextVar("tenant_context", default=None)


def set_current_tenant(tenant_id: Optional[str]):
    """
    Store the current tenant identifier for the active context.

    Returns:
        The context token that can be used to restore the previous value.
    """
    return _tenant_context.set(tenant_id)


def get_current_tenant() -> Optional[str]:
    """Return the tenant identifier associated with the current context."""
    return _tenant_context.get()


def reset_current_tenant(token) -> None:
    """
    Restore the tenant context to a previous value using the provided token.
    """
    _tenant_context.reset(token)
