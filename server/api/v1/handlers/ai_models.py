"""
AI Models CRUD API endpoints.
Admin endpoints for managing AI models per tenant.
"""

import logging
import secrets
from datetime import datetime
from typing import Optional, List
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException, Query, status
from pydantic import BaseModel, Field

from server.config.settings import get_settings
from server.integrations.mongodb import MongoDBClient
from server.models.project import AIModel
from server.models.tenant import tenant_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/ai-models", tags=["AI Models Management"])

settings = get_settings()
ADMIN_API_KEY = settings.admin_api_key


class CreateAIModelRequest(BaseModel):
    """Request model for creating an AI model"""
    model_name: str = Field(..., description="Display name of the AI model")
    cost_per_page: float = Field(..., gt=0, description="Cost per page in USD")
    description: Optional[str] = Field(None, description="Model description")
    provider: str = Field(default="gemini", description="AI provider")


class UpdateAIModelRequest(BaseModel):
    """Request model for updating an AI model"""
    model_name: Optional[str] = None
    cost_per_page: Optional[float] = Field(None, gt=0)
    description: Optional[str] = None
    status: Optional[str] = Field(None, pattern="^(active|deprecated|archived)$")


class AIModelResponse(BaseModel):
    """Response model for AI model operations"""
    success: bool
    data: Optional[AIModel] = None
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


@router.post("/tenants/{tenant_id}", response_model=AIModelResponse)
async def create_ai_model(
    tenant_id: str,
    request: CreateAIModelRequest,
    admin_key: str = Header(None, alias="X-Admin-Key")
):
    """
    Create a new AI model for a tenant.
    
    **Admin only** - Requires X-Admin-Key header
    """
    verify_admin_key(admin_key)
    
    tenant = tenant_manager.get_tenant(tenant_id)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant '{tenant_id}' not found",
        )
    
    try:
        db = await MongoDBClient.get_database()
        ai_models_collection = db["ai_models"]
        
        model_id = str(uuid4())
        ai_model = AIModel(
            model_id=model_id,
            tenant_id=tenant_id,
            model_name=request.model_name,
            cost_per_page=request.cost_per_page,
            description=request.description,
            provider=request.provider,
        )
        
        # Insert into MongoDB
        model_dict = ai_model.dict()
        await ai_models_collection.insert_one(model_dict)
        
        # Remove MongoDB _id from response
        model_dict.pop('_id', None)
        
        logger.info(f"Created AI model '{model_id}' for tenant '{tenant_id}'")
        
        return AIModelResponse(
            success=True,
            data=model_dict,
            message=f"AI model created successfully with ID: {model_id}"
        )
        
    except Exception as e:
        logger.error(f"Error creating AI model: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create AI model: {str(e)}"
        )


@router.get("/tenants/{tenant_id}")
async def list_ai_models(
    tenant_id: str,
    status_filter: Optional[str] = Query(None, description="Filter by status: active, deprecated, archived"),
    admin_key: str = Header(None, alias="X-Admin-Key")
):
    """
    List all AI models for a tenant.
    
    **Admin only** - Requires X-Admin-Key header
    """
    verify_admin_key(admin_key)
    
    tenant = tenant_manager.get_tenant(tenant_id)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant '{tenant_id}' not found",
        )
    
    try:
        db = await MongoDBClient.get_database()
        ai_models_collection = db["ai_models"]
        
        query = {"tenant_id": tenant_id}
        if status_filter:
            query["status"] = status_filter
        
        cursor = ai_models_collection.find(query)
        models = []
        
        async for model in cursor:
            # Remove MongoDB's _id field and convert to dict
            model_dict = dict(model)
            model_dict.pop('_id', None)
            models.append(model_dict)
        
        return {
            "success": True,
            "tenant_id": tenant_id,
            "total_models": len(models),
            "models": models
        }
        
    except Exception as e:
        logger.error(f"Error listing AI models: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list AI models: {str(e)}"
        )


@router.get("/tenants/{tenant_id}/{model_id}")
async def get_ai_model(
    tenant_id: str,
    model_id: str,
    admin_key: str = Header(None, alias="X-Admin-Key")
):
    """
    Get details of a specific AI model.
    
    **Admin only** - Requires X-Admin-Key header
    """
    verify_admin_key(admin_key)
    
    try:
        db = await MongoDBClient.get_database()
        ai_models_collection = db["ai_models"]
        
        model = await ai_models_collection.find_one({
            "model_id": model_id,
            "tenant_id": tenant_id
        })
        
        if not model:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"AI model '{model_id}' not found for tenant '{tenant_id}'",
            )
        
        # Convert MongoDB document to dict and remove _id
        model_dict = dict(model)
        model_dict.pop('_id', None)
        
        return {
            "success": True,
            "data": model_dict
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving AI model: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve AI model: {str(e)}"
        )


@router.patch("/tenants/{tenant_id}/{model_id}", response_model=AIModelResponse)
async def update_ai_model(
    tenant_id: str,
    model_id: str,
    request: UpdateAIModelRequest,
    admin_key: str = Header(None, alias="X-Admin-Key")
):
    """
    Update an AI model.
    
    **Admin only** - Requires X-Admin-Key header
    """
    verify_admin_key(admin_key)
    
    try:
        db = await MongoDBClient.get_database()
        ai_models_collection = db["ai_models"]
        
        model = await ai_models_collection.find_one({
            "model_id": model_id,
            "tenant_id": tenant_id
        })
        
        if not model:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"AI model '{model_id}' not found",
            )
        
        # Build update dict
        update_data = {}
        if request.model_name is not None:
            update_data["model_name"] = request.model_name
        if request.cost_per_page is not None:
            update_data["cost_per_page"] = request.cost_per_page
        if request.description is not None:
            update_data["description"] = request.description
        if request.status is not None:
            update_data["status"] = request.status
        
        update_data["updated_at"] = datetime.utcnow()
        
        # Update in MongoDB
        await ai_models_collection.update_one(
            {"model_id": model_id, "tenant_id": tenant_id},
            {"$set": update_data}
        )
        
        # Fetch updated model
        updated_model = await ai_models_collection.find_one({
            "model_id": model_id,
            "tenant_id": tenant_id
        })
        
        # Convert MongoDB document to dict and remove _id
        updated_model_dict = dict(updated_model)
        updated_model_dict.pop('_id', None)
        
        logger.info(f"Updated AI model '{model_id}' for tenant '{tenant_id}'")
        
        return AIModelResponse(
            success=True,
            data=updated_model_dict,
            message=f"AI model '{model_id}' updated successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating AI model: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update AI model: {str(e)}"
        )


@router.delete("/tenants/{tenant_id}/{model_id}")
async def delete_ai_model(
    tenant_id: str,
    model_id: str,
    admin_key: str = Header(None, alias="X-Admin-Key")
):
    """
    Delete an AI model.
    
    **Admin only** - Requires X-Admin-Key header
    
    Warning: Projects associated with this model will no longer have a valid AI model reference.
    """
    verify_admin_key(admin_key)
    
    try:
        db = await MongoDBClient.get_database()
        ai_models_collection = db["ai_models"]
        
        result = await ai_models_collection.delete_one({
            "model_id": model_id,
            "tenant_id": tenant_id
        })
        
        if result.deleted_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"AI model '{model_id}' not found",
            )
        
        logger.warning(f"Deleted AI model '{model_id}' for tenant '{tenant_id}'")
        
        return {
            "success": True,
            "message": f"AI model '{model_id}' deleted successfully",
            "warning": "Any projects using this model will need to be reassigned to a different AI model"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting AI model: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete AI model: {str(e)}"
        )
