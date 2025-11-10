"""
Tenant Management Handler
Admin endpoints for creating, updating, and managing tenants
"""

import logging
import secrets
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, EmailStr

from server.config.settings import get_settings
from server.models.tenant import Tenant, TenantQuota, tenant_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Tenant Management"])

settings = get_settings()
# Admin API key sourced from environment (see Settings.admin_api_key)
ADMIN_API_KEY = settings.admin_api_key


class CreateTenantRequest(BaseModel):
    """Request model for creating a new tenant"""
    name: str
    email: EmailStr
    quota_max_uploads_per_month: int = 100
    quota_max_storage_mb: int = 1000


class UpdateTenantRequest(BaseModel):
    """Request model for updating tenant"""
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    active: Optional[bool] = None
    quota_max_uploads_per_month: Optional[int] = None
    quota_max_storage_mb: Optional[int] = None


class TenantResponse(BaseModel):
    """Response model for tenant operations"""
    success: bool
    tenant: Tenant
    message: Optional[str] = None


def verify_admin_key(x_admin_key: Optional[str] = Header(None)) -> str:
    """Verify admin API key"""
    if not ADMIN_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin access is not configured.",
        )

    if not x_admin_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin API key required. Include X-Admin-Key header.",
        )

    if x_admin_key != ADMIN_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid admin API key",
        )

    return x_admin_key


def generate_tenant_id(name: str) -> str:
    """
    Generate a unique tenant ID from organization name
    
    Args:
        name: Organization name
    
    Returns:
        Unique tenant ID (e.g., "city-general-a1b2")
    """
    # Convert name to slug
    slug = name.lower().replace(" ", "-").replace("_", "-")
    # Remove special characters
    slug = ''.join(c for c in slug if c.isalnum() or c == '-')
    # Add random suffix for uniqueness
    suffix = secrets.token_hex(2)  # 4 character hex
    tenant_id = f"{slug}-{suffix}"
    
    return tenant_id


def generate_api_key(tenant_id: str) -> str:
    """
    Generate a secure API key for tenant
    
    Args:
        tenant_id: Tenant identifier
    
    Returns:
        API key (e.g., "sk_city_general_a1b2_abc123def456")
    """
    # Generate cryptographically secure random token
    token = secrets.token_urlsafe(24)  # 32 characters
    api_key = f"sk_{tenant_id}_{token}"
    return api_key


@router.post("/tenants", response_model=TenantResponse)
async def create_tenant(
    request: CreateTenantRequest,
    admin_key: str = Header(None, alias="X-Admin-Key")
):
    """
    Create a new tenant
    
    **Admin only** - Requires X-Admin-Key header
    
    Args:
        request: Tenant creation details
        admin_key: Admin API key
    
    Returns:
        Created tenant with generated tenant_id and api_key
    """
    verify_admin_key(admin_key)
    
    try:
        # Generate unique tenant ID
        tenant_id = generate_tenant_id(request.name)
        logger.info(f"Generated tenant_id: {tenant_id}")
        
        # Generate API key
        api_key = generate_api_key(tenant_id)
        logger.info(f"Generated API key for tenant: {tenant_id}")
        
        # Create tenant object
        tenant = Tenant(
            tenant_id=tenant_id,
            name=request.name,
            email=request.email,
            api_key=api_key,
            created_at=datetime.utcnow().isoformat(),
            active=True,
            quota=TenantQuota(
                max_uploads_per_month=request.quota_max_uploads_per_month,
                max_storage_mb=request.quota_max_storage_mb
            )
        )
        
        await tenant_manager.add_tenant(tenant)
        
        logger.info(f"Created new tenant: {tenant_id}")
        
        return TenantResponse(
            success=True,
            tenant=tenant,
            message=f"Tenant '{request.name}' created successfully"
        )
        
    except Exception as e:
        logger.error(f"Error creating tenant: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create tenant: {str(e)}"
        )


@router.get("/tenants")
async def list_tenants(
    admin_key: str = Header(None, alias="X-Admin-Key")
):
    """
    List all tenants
    
    **Admin only** - Requires X-Admin-Key header
    """
    verify_admin_key(admin_key)
    
    tenants = await tenant_manager.list_all_tenants()
    
    return {
        "success": True,
        "total_tenants": len(tenants),
        "tenants": [
            {
                "tenant_id": t.tenant_id,
                "name": t.name,
                "email": t.email,
                "active": t.active,
                "created_at": t.created_at,
                "quota": t.quota.dict()
            }
            for t in tenants.values()
        ]
    }


@router.get("/tenants/{tenant_id}", response_model=TenantResponse)
async def get_tenant(
    tenant_id: str,
    admin_key: str = Header(None, alias="X-Admin-Key")
):
    """
    Get tenant details
    
    **Admin only** - Requires X-Admin-Key header
    """
    verify_admin_key(admin_key)
    
    tenant = await tenant_manager.get_tenant(tenant_id)
    
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant '{tenant_id}' not found"
        )
    
    return TenantResponse(
        success=True,
        tenant=tenant
    )


@router.patch("/tenants/{tenant_id}", response_model=TenantResponse)
async def update_tenant(
    tenant_id: str,
    request: UpdateTenantRequest,
    admin_key: str = Header(None, alias="X-Admin-Key")
):
    """
    Update tenant details
    
    **Admin only** - Requires X-Admin-Key header
    """
    verify_admin_key(admin_key)
    
    tenant = await tenant_manager.get_tenant(tenant_id)
    
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant '{tenant_id}' not found"
        )
    
    try:
        # Update fields if provided
        if request.name is not None:
            tenant.name = request.name
        if request.email is not None:
            tenant.email = request.email
        if request.active is not None:
            tenant.active = request.active
        if request.quota_max_uploads_per_month is not None:
            tenant.quota.max_uploads_per_month = request.quota_max_uploads_per_month
        if request.quota_max_storage_mb is not None:
            tenant.quota.max_storage_mb = request.quota_max_storage_mb
        
        # Save updated tenant to MongoDB
        await tenant_manager.update_tenant(tenant)
        
        logger.info(f"Updated tenant: {tenant_id}")
        
        return TenantResponse(
            success=True,
            tenant=tenant,
            message=f"Tenant '{tenant_id}' updated successfully"
        )
        
    except Exception as e:
        logger.error(f"Error updating tenant: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update tenant: {str(e)}"
        )


@router.delete("/tenants/{tenant_id}")
async def delete_tenant(
    tenant_id: str,
    admin_key: str = Header(None, alias="X-Admin-Key")
):
    """
    Delete a tenant
    
    **Admin only** - Requires X-Admin-Key header
    
    Warning: This will delete the tenant but NOT their data in Azure Blob Storage.
    You must manually clean up Azure storage.
    """
    verify_admin_key(admin_key)
    
    tenant = await tenant_manager.get_tenant(tenant_id)
    
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant '{tenant_id}' not found"
        )
    
    try:
        await tenant_manager.delete_tenant(tenant_id)
        
        logger.warning(f"Deleted tenant: {tenant_id}")
        
        return {
            "success": True,
            "message": f"Tenant '{tenant_id}' deleted successfully",
            "warning": "Azure Blob Storage data NOT deleted. Clean up manually if needed."
        }
        
    except Exception as e:
        logger.error(f"Error deleting tenant: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete tenant: {str(e)}"
        )


@router.post("/tenants/{tenant_id}/regenerate-api-key", response_model=TenantResponse)
async def regenerate_api_key(
    tenant_id: str,
    admin_key: str = Header(None, alias="X-Admin-Key")
):
    """
    Regenerate API key for a tenant
    
    **Admin only** - Requires X-Admin-Key header
    
    Warning: This will invalidate the old API key immediately.
    """
    verify_admin_key(admin_key)
    
    tenant = await tenant_manager.get_tenant(tenant_id)
    
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant '{tenant_id}' not found"
        )
    
    try:
        # Generate new API key
        new_api_key = generate_api_key(tenant_id)
        old_api_key = tenant.api_key
        
        # Update tenant
        tenant.api_key = new_api_key
        await tenant_manager.update_tenant(tenant)
        
        logger.warning(f"Regenerated API key for tenant: {tenant_id}")
        
        return TenantResponse(
            success=True,
            tenant=tenant,
            message=f"API key regenerated. Old key is now invalid."
        )
        
    except Exception as e:
        logger.error(f"Error regenerating API key: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to regenerate API key: {str(e)}"
        )

