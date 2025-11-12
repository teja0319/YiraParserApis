"""
Tenant models and MongoDB-based management.
All data stored exclusively in MongoDB, no local files.
"""

import logging
from datetime import datetime
from typing import Dict, Optional, List
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class TenantQuota(BaseModel):
    """Quota limits for tenant"""
    max_uploads_per_month: int = 100
    max_storage_mb: int = 1000


class Tenant(BaseModel):
    """Tenant model representing a hospital/clinic"""
    tenant_id: str
    name: str
    email: str
    api_key: str
    created_at: str
    active: bool = True
    quota: Optional[TenantQuota] = Field(default_factory=TenantQuota)


class TenantManager:
    """Manages tenant data in MongoDB (async operations)"""
    
    def __init__(self):
        """Initialize tenant manager - will connect to MongoDB on first operation"""
        self.db = None
    
    async def _get_db(self):
        """Get MongoDB database connection"""
        if self.db is None:
            from server.integrations.mongodb import MongoDBClient
            self.db = await MongoDBClient.get_database()
        return self.db
    
    def _doc_to_tenant(self, tenant_doc: dict) -> Tenant:
        """Convert MongoDB document to Tenant object, handling missing fields"""
        if not tenant_doc:
            return None
        
        # Remove MongoDB's internal _id field
        tenant_doc.pop("_id", None)
        
        return Tenant(
            tenant_id=tenant_doc.get("tenant_id", tenant_doc.get("_id", "unknown")),
            name=tenant_doc.get("name", "Unknown Tenant"),
            email=tenant_doc.get("email", "noemail@example.com"),
            api_key=tenant_doc.get("api_key", ""),
            created_at=tenant_doc.get("created_at", datetime.utcnow().isoformat()),
            active=tenant_doc.get("active", True),
            quota=TenantQuota(
                max_uploads_per_month=tenant_doc.get("quota", {}).get("max_uploads_per_month", 100),
                max_storage_mb=tenant_doc.get("quota", {}).get("max_storage_mb", 1000)
            ) if tenant_doc.get("quota") else TenantQuota()
        )
    
    async def get_tenant(self, tenant_id: str) -> Optional[Tenant]:
        """Get tenant by ID from MongoDB"""
        db = await self._get_db()
        tenant_doc = await db["tenants"].find_one({"tenant_id": tenant_id})
        
        if tenant_doc:
            return self._doc_to_tenant(tenant_doc)
        return None
    
    async def verify_api_key(self, api_key: str) -> Optional[str]:
        """
        Verify API key and return tenant_id
        Returns None if API key is invalid or tenant is inactive
        Added debug logging to trace API key validation
        """
        db = await self._get_db()
        
        logger.info(f"[v0] Searching for API key in MongoDB. Key: {api_key[:10]}...")
        
        tenant_doc = await db["tenants"].find_one({
            "api_key": api_key,
            "active": True
        })
        
        if tenant_doc:
            tenant_id = tenant_doc.get("tenant_id", tenant_doc.get("_id"))
            logger.info(f"[v0] API key verified successfully. Tenant ID: {tenant_id}")
            return tenant_id
        else:
            logger.warning(f"[v0] API key verification failed. No active tenant found with this key .",api_key)
            inactive_tenant = await db["tenants"].find_one({"api_key": api_key})
            if inactive_tenant:
                logger.warning(f"[v0] API key exists but tenant is INACTIVE: {inactive_tenant.get('tenant_id')}")
        
        return None
    
    async def is_tenant_active(self, tenant_id: str) -> bool:
        """Check if tenant is active"""
        tenant = await self.get_tenant(tenant_id)
        return tenant.active if tenant else False
    
    async def list_all_tenants(self) -> Dict[str, Tenant]:
        """List all tenants (admin function)"""
        db = await self._get_db()
        tenants_dict = {}
        
        async for tenant_doc in db["tenants"].find({}):
            try:
                tenant = self._doc_to_tenant(tenant_doc)
                if tenant:
                    tenants_dict[tenant.tenant_id] = tenant
            except Exception as e:
                logger.warning(f"Failed to convert tenant document: {e}. Skipping: {tenant_doc}")
                continue
        
        return tenants_dict
    
    async def add_tenant(self, tenant: Tenant):
        """
        Add a new tenant to MongoDB
        
        Args:
            tenant: Tenant object to add
        
        Raises:
            ValueError: If tenant_id already exists
        """
        db = await self._get_db()
        
        # Check if tenant already exists
        existing = await db["tenants"].find_one({"tenant_id": tenant.tenant_id})
        if existing:
            raise ValueError(f"Tenant with ID '{tenant.tenant_id}' already exists")
        
        # Insert tenant document
        tenant_doc = tenant.dict()
        result = await db["tenants"].insert_one(tenant_doc)
        logger.info(f"Tenant {tenant.tenant_id} created in MongoDB with _id: {result.inserted_id}")
    
    async def update_tenant(self, tenant: Tenant):
        """
        Update existing tenant in MongoDB
        
        Args:
            tenant: Updated tenant object
        
        Raises:
            ValueError: If tenant doesn't exist
        """
        db = await self._get_db()
        
        # Check if tenant exists
        existing = await db["tenants"].find_one({"tenant_id": tenant.tenant_id})
        if not existing:
            raise ValueError(f"Tenant with ID '{tenant.tenant_id}' not found")
        
        # Update tenant document
        tenant_doc = tenant.dict()
        await db["tenants"].replace_one(
            {"tenant_id": tenant.tenant_id},
            tenant_doc
        )
        logger.info(f"Tenant {tenant.tenant_id} updated in MongoDB")
    
    async def delete_tenant(self, tenant_id: str):
        """
        Delete a tenant from MongoDB
        
        Args:
            tenant_id: ID of tenant to delete
        
        Raises:
            ValueError: If tenant doesn't exist
        """
        db = await self._get_db()
        
        # Check if tenant exists
        existing = await db["tenants"].find_one({"tenant_id": tenant_id})
        if not existing:
            raise ValueError(f"Tenant with ID '{tenant_id}' not found")
        
        result = await db["tenants"].delete_one({"tenant_id": tenant_id})
        logger.info(f"Tenant {tenant_id} deleted from MongoDB. Deleted count: {result.deleted_count}")


tenant_manager = TenantManager()
