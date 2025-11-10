# """
# Authentication utilities for enforcing tenant isolation.
# """

# from __future__ import annotations

# import base64
# import hmac
# import json
# import time
# from dataclasses import dataclass, field
# from hashlib import sha256
# from typing import List, Optional, Tuple

# from fastapi import Header, HTTPException, status

# from server.config.settings import get_settings
# from server.core.tenant_context import (
#     reset_current_tenant,
#     set_current_tenant,
# )
# from server.middleware.rate_limit import enforce_rate_limit
# from server.models.tenant import tenant_manager
# from server.utils.usage_tracker import usage_tracker


# @dataclass
# class AuthenticatedTenant:
#     """Represents the authenticated tenant context for a request."""

#     tenant_id: str
#     methods: List[str] = field(default_factory=list)
#     token_id: Optional[str] = None

#     @property
#     def method(self) -> str:
#         """Return a readable summary of the auth mechanisms used."""
#         if not self.methods:
#             return "unknown"
#         ordered_unique = list(dict.fromkeys(self.methods))
#         return "+".join(ordered_unique)


# def _decode_segment(segment: str) -> bytes:
#     """Decode a base64url segment padding as necessary."""
#     padding = "=" * (-len(segment) % 4)
#     return base64.urlsafe_b64decode(segment + padding)


# def _decode_jwt_token(token: str) -> Tuple[str, Optional[str]]:
#     """
#     Decode and validate an HMAC-signed JWT, returning the tenant identifier and token id.
#     """
#     settings = get_settings()

#     if not settings.jwt_secret:
#         raise HTTPException(
#             status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
#             detail="JWT authentication is not configured.",
#         )

#     try:
#         header_segment, payload_segment, signature_segment = token.split(".")
#     except ValueError as exc:
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail="Malformed authentication token.",
#         ) from exc

#     header = json.loads(_decode_segment(header_segment))
#     if header.get("alg") != "HS256":
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail="Unsupported token algorithm.",
#         )

#     signing_input = f"{header_segment}.{payload_segment}".encode("utf-8")
#     expected_signature = hmac.new(
#         settings.jwt_secret.encode("utf-8"),
#         signing_input,
#         sha256,
#     ).digest()
#     received_signature = _decode_segment(signature_segment)

#     if not hmac.compare_digest(received_signature, expected_signature):
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail="Invalid authentication token signature.",
#         )

#     payload = json.loads(_decode_segment(payload_segment))

#     exp = payload.get("exp")
#     if exp is not None and time.time() >= int(exp):
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail="Authentication token has expired.",
#         )

#     aud = payload.get("aud")
#     if settings.jwt_audience and aud != settings.jwt_audience:
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail="Authentication token audience mismatch.",
#         )

#     iss = payload.get("iss")
#     if settings.jwt_issuer and iss != settings.jwt_issuer:
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail="Authentication token issuer mismatch.",
#         )

#     tenant_id = (
#         payload.get("tenant_id")
#         or payload.get("tid")
#         or payload.get("sub")
#     )

#     if not tenant_id:
#         raise HTTPException(
#             status_code=status.HTTP_403_FORBIDDEN,
#             detail="Authentication token missing tenant information.",
#         )

#     return str(tenant_id), payload.get("jti")


# def _resolve_tenant_from_api_key(x_api_key: str) -> str:
#     """Resolve tenant from API key and ensure the tenant is active."""
#     tenant_id = tenant_manager.verify_api_key(x_api_key)
#     if not tenant_id:
#         raise HTTPException(
#             status_code=status.HTTP_403_FORBIDDEN,
#             detail="Invalid or inactive API key.",
#         )
#     return tenant_id


# async def resolve_tenant(
#     tenant_id: str,
#     authorization: Optional[str] = Header(None),
#     x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
#     x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
# ):
#     """
#     Unified dependency that authenticates the request and enforces tenant isolation.

#     Priority:
#         1. Authorization (JWT Bearer) if provided
#         2. X-API-Key header (required if JWT absent)
#         3. X-Tenant-ID header consistency checks
#         4. Path tenant_id
#     """
#     if not authorization and not x_api_key:
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail="Provide either Authorization Bearer token or X-API-Key header.",
#             headers={"WWW-Authenticate": "Bearer"},
#         )

#     resolved_sources: List[Tuple[str, str]] = []
#     methods: List[str] = []
#     token_id: Optional[str] = None

#     if authorization:
#         scheme, _, token = authorization.partition(" ")
#         if scheme.lower() != "bearer" or not token:
#             raise HTTPException(
#                 status_code=status.HTTP_401_UNAUTHORIZED,
#                 detail="Authorization header must use the Bearer scheme.",
#                 headers={"WWW-Authenticate": "Bearer"},
#             )
#         jwt_tenant_id, token_id = _decode_jwt_token(token.strip())
#         resolved_sources.append(("jwt", jwt_tenant_id))
#         methods.append("jwt")

#     if x_api_key:
#         api_key_tenant = _resolve_tenant_from_api_key(x_api_key)
#         resolved_sources.append(("api_key", api_key_tenant))
#         methods.append("api_key")

#     if x_tenant_id:
#         resolved_sources.append(("header", x_tenant_id))
#         methods.append("tenant_header")

#     resolved_sources.append(("path", tenant_id))

#     canonical_tenant_id = resolved_sources[0][1]
#     for source, resolved_id in resolved_sources[1:]:
#         if canonical_tenant_id != resolved_id:
#             raise HTTPException(
#                 status_code=status.HTTP_403_FORBIDDEN,
#                 detail=f"Tenant mismatch between authentication sources ({source}).",
#             )

#     tenant = tenant_manager.get_tenant(canonical_tenant_id)
#     if not tenant or not tenant.active:
#         raise HTTPException(
#             status_code=status.HTTP_403_FORBIDDEN,
#             detail="Tenant is inactive or does not exist.",
#         )

#     settings = get_settings()
#     if settings.require_tenant_header and not x_tenant_id:
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail="X-Tenant-ID header is required for this environment.",
#         )

#     enforce_rate_limit(canonical_tenant_id)
#     usage_tracker.track_api_call(canonical_tenant_id, "request")

#     token = set_current_tenant(canonical_tenant_id)
#     try:
#         context = AuthenticatedTenant(
#             tenant_id=canonical_tenant_id,
#             methods=methods or ["path"],
#             token_id=token_id,
#         )
#         yield context
#     finally:
#         reset_current_tenant(token)


# def verify_tenant_access(tenant_id_from_url: str, authenticated_tenant_id: str) -> None:
#     """Ensure the requested tenant in the URL matches the authenticated tenant."""
#     if tenant_id_from_url != authenticated_tenant_id:
#         raise HTTPException(
#             status_code=status.HTTP_403_FORBIDDEN,
#             detail="Tenant mismatch between URL and authentication context.",
#         )


# def verify_tenant_header(x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID")) -> str:
#     """
#     Validate the optional X-Tenant-ID header for routes that rely solely on it.
#     """
#     if not x_tenant_id:
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail="X-Tenant-ID header required.",
#         )

#     tenant = tenant_manager.get_tenant(x_tenant_id)
#     if not tenant or not tenant.active:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail="Tenant not found or inactive.",
#         )

#     return x_tenant_id


"""
Authentication utilities for enforcing tenant isolation.
All tenant lookups now use MongoDB asynchronously.
"""

from __future__ import annotations

import base64
import hmac
import json
import time
from dataclasses import dataclass, field
from hashlib import sha256
from typing import List, Optional, Tuple

from fastapi import Header, HTTPException, status

from server.config.settings import get_settings
from server.core.tenant_context import (
    reset_current_tenant,
    set_current_tenant,
)
from server.middleware.rate_limit import enforce_rate_limit
from server.models.tenant import tenant_manager
from server.utils.usage_tracker import usage_tracker


@dataclass
class AuthenticatedTenant:
    """Represents the authenticated tenant context for a request."""

    tenant_id: str
    methods: List[str] = field(default_factory=list)
    token_id: Optional[str] = None

    @property
    def method(self) -> str:
        """Return a readable summary of the auth mechanisms used."""
        if not self.methods:
            return "unknown"
        ordered_unique = list(dict.fromkeys(self.methods))
        return "+".join(ordered_unique)


def _decode_segment(segment: str) -> bytes:
    """Decode a base64url segment padding as necessary."""
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + padding)


def _decode_jwt_token(token: str) -> Tuple[str, Optional[str]]:
    """
    Decode and validate an HMAC-signed JWT, returning the tenant identifier and token id.
    """
    settings = get_settings()

    if not settings.jwt_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="JWT authentication is not configured.",
        )

    try:
        header_segment, payload_segment, signature_segment = token.split(".")
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed authentication token.",
        ) from exc

    header = json.loads(_decode_segment(header_segment))
    if header.get("alg") != "HS256":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unsupported token algorithm.",
        )

    signing_input = f"{header_segment}.{payload_segment}".encode("utf-8")
    expected_signature = hmac.new(
        settings.jwt_secret.encode("utf-8"),
        signing_input,
        sha256,
    ).digest()
    received_signature = _decode_segment(signature_segment)

    if not hmac.compare_digest(received_signature, expected_signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token signature.",
        )

    payload = json.loads(_decode_segment(payload_segment))

    exp = payload.get("exp")
    if exp is not None and time.time() >= int(exp):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired.",
        )

    aud = payload.get("aud")
    if settings.jwt_audience and aud != settings.jwt_audience:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token audience mismatch.",
        )

    iss = payload.get("iss")
    if settings.jwt_issuer and iss != settings.jwt_issuer:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token issuer mismatch.",
        )

    tenant_id = (
        payload.get("tenant_id")
        or payload.get("tid")
        or payload.get("sub")
    )

    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Authentication token missing tenant information.",
        )

    return str(tenant_id), payload.get("jti")


async def _resolve_tenant_from_api_key(x_api_key: str) -> str:
    """
    Resolve tenant from API key and ensure the tenant is active.
    Now async to query MongoDB
    """
    tenant_id = await tenant_manager.verify_api_key(x_api_key)
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or inactive API key.",
        )
    return tenant_id


async def resolve_tenant(
    tenant_id: str,
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
):
    """
    Unified dependency that authenticates the request and enforces tenant isolation.
    Now fully async for MongoDB operations

    Priority:
        1. Authorization (JWT Bearer) if provided
        2. X-API-Key header (required if JWT absent)
        3. X-Tenant-ID header consistency checks
        4. Path tenant_id
    """
    if not authorization and not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Provide either Authorization Bearer token or X-API-Key header.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    resolved_sources: List[Tuple[str, str]] = []
    methods: List[str] = []
    token_id: Optional[str] = None

    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authorization header must use the Bearer scheme.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        jwt_tenant_id, token_id = _decode_jwt_token(token.strip())
        resolved_sources.append(("jwt", jwt_tenant_id))
        methods.append("jwt")

    if x_api_key:
        api_key_tenant = await _resolve_tenant_from_api_key(x_api_key)
        resolved_sources.append(("api_key", api_key_tenant))
        methods.append("api_key")

    if x_tenant_id:
        resolved_sources.append(("header", x_tenant_id))
        methods.append("tenant_header")

    resolved_sources.append(("path", tenant_id))

    canonical_tenant_id = resolved_sources[0][1]
    for source, resolved_id in resolved_sources[1:]:
        if canonical_tenant_id != resolved_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Tenant mismatch between authentication sources ({source}).",
            )

    tenant = await tenant_manager.get_tenant(canonical_tenant_id)
    if not tenant or not tenant.active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant is inactive or does not exist.",
        )

    settings = get_settings()
    if settings.require_tenant_header and not x_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Tenant-ID header is required for this environment.",
        )

    enforce_rate_limit(canonical_tenant_id)
    usage_tracker.track_api_call(canonical_tenant_id, "request")

    token = set_current_tenant(canonical_tenant_id)
    try:
        context = AuthenticatedTenant(
            tenant_id=canonical_tenant_id,
            methods=methods or ["path"],
            token_id=token_id,
        )
        yield context
    finally:
        reset_current_tenant(token)


def verify_tenant_access(tenant_id_from_url: str, authenticated_tenant_id: str) -> None:
    """Ensure the requested tenant in the URL matches the authenticated tenant."""
    if tenant_id_from_url != authenticated_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant mismatch between URL and authentication context.",
        )


async def verify_tenant_header(x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID")) -> str:
    """
    Validate the optional X-Tenant-ID header for routes that rely solely on it.
    Now async to query MongoDB
    """
    if not x_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Tenant-ID header required.",
        )

    tenant = await tenant_manager.get_tenant(x_tenant_id)
    if not tenant or not tenant.active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found or inactive.",
        )

    return x_tenant_id
