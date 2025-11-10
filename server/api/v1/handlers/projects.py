"""
Projects CRUD API endpoints.
Tenant-scoped endpoints for managing projects.
"""

import logging
from datetime import datetime
from typing import Optional, List
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field

from server.config.settings import get_settings
from server.integrations.mongodb import MongoDBClient
from server.middleware.auth import AuthenticatedTenant, resolve_tenant
from server.models.project import Project
from server.models.tenant import tenant_manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Projects"])


class CreateProjectRequest(BaseModel):
    """Request model for creating a project"""
    project_name: str = Field(..., description="Display name of the project")
    description: Optional[str] = Field(None, description="Project description")
    # ai_model_id: str = Field(..., description="Associated AI Model ID")


class UpdateProjectRequest(BaseModel):
    """Request model for updating a project"""
    project_name: Optional[str] = None
    description: Optional[str] = None
    ai_model_id: Optional[str] = None
    is_active: Optional[bool] = None


class AssignAIModelRequest(BaseModel):
    """Request model for assigning an AI model to a project"""
    ai_model_id: str = Field(..., description="AI Model ID to assign")


class ProjectResponse(BaseModel):
    """Response model for project operations"""
    success: bool
    data: Optional[Project] = None
    message: Optional[str] = None


@router.post("/tenants/{tenant_id}/projects", response_model=ProjectResponse)
async def create_project(
    tenant_id: str,
    request: CreateProjectRequest,
    auth: AuthenticatedTenant = Depends(resolve_tenant),
):
    """
    Create a new project for a tenant.
    Only the tenant can create projects for themselves.
    """
    try:
        db = await MongoDBClient.get_database()
        projects_collection = db["projects"]
        ai_models_collection = db["ai_models"]
        
        # Verify AI model exists and belongs to this tenant
        # ai_model = await ai_models_collection.find_one({
        #     "model_id": request.ai_model_id,
        #     "tenant_id": tenant_id
        # })
        
        # if not ai_model:
        #     raise HTTPException(
        #         status_code=status.HTTP_404_NOT_FOUND,
        #         detail=f"AI model '{request.ai_model_id}' not found for this tenant",
        #     )
        
        project_id = str(uuid4())
        project = Project(
            project_id=project_id,
            tenant_id=tenant_id,
            project_name=request.project_name,
            description=request.description,
            # ai_model_id=request.ai_model_id,
        )
        
        # Insert into MongoDB
        project_dict = project.dict()
        await projects_collection.insert_one(project_dict)
        
        # Remove MongoDB _id and ai_model_id from response
        project_dict.pop('_id', None)
        project_dict.pop('ai_model_id', None)
        
        logger.info(f"Created project '{project_id}' for tenant '{tenant_id}'")
        
        return ProjectResponse(
            success=True,
            data=project_dict,
            message=f"Project created successfully with ID: {project_id}"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating project: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create project: {str(e)}"
        )


@router.get("/tenants/{tenant_id}/projects")
async def list_projects(
    tenant_id: str,
    active_only: bool = Query(False, description="Filter to active projects only"),
    auth: AuthenticatedTenant = Depends(resolve_tenant),
):
    """
    List all projects for a tenant.
    """
    try:
        db = await MongoDBClient.get_database()
        projects_collection = db["projects"]
        
        query = {"tenant_id": tenant_id}
        if active_only:
            query["is_active"] = True
        
        cursor = projects_collection.find(query)
        projects = []
        
        async for project in cursor:
            # Remove MongoDB's _id field and ai_model_id, then convert to dict
            project_dict = dict(project)
            project_dict.pop('_id', None)
            project_dict.pop('ai_model_id', None)
            projects.append(project_dict)
        
        return {
            "success": True,
            "tenant_id": tenant_id,
            "total_projects": len(projects),
            "projects": projects
        }
        
    except Exception as e:
        logger.error(f"Error listing projects: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list projects: {str(e)}"
        )


@router.get("/tenants/{tenant_id}/projects/{project_id}")
async def get_project(
    tenant_id: str,
    project_id: str,
    auth: AuthenticatedTenant = Depends(resolve_tenant),
):
    """
    Get details of a specific project.
    """
    try:
        db = await MongoDBClient.get_database()
        projects_collection = db["projects"]
        
        project = await projects_collection.find_one({
            "project_id": project_id,
            "tenant_id": tenant_id
        })
        
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{project_id}' not found",
            )
        
        # Convert MongoDB document to dict and remove _id
        project_dict = dict(project)
        project_dict.pop('_id', None)
        project_dict.pop('ai_model_id', None)
        
        return {
            "success": True,
            "data": project_dict
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving project: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve project: {str(e)}"
        )


@router.patch("/tenants/{tenant_id}/projects/{project_id}", response_model=ProjectResponse)
async def update_project(
    tenant_id: str,
    project_id: str,
    request: UpdateProjectRequest,
    auth: AuthenticatedTenant = Depends(resolve_tenant),
):
    """
    Update a project.
    """
    try:
        db = await MongoDBClient.get_database()
        projects_collection = db["projects"]
        ai_models_collection = db["ai_models"]
        
        project = await projects_collection.find_one({
            "project_id": project_id,
            "tenant_id": tenant_id
        })
        
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{project_id}' not found",
            )
        
        # Build update dict
        update_data = {}
        if request.project_name is not None:
            update_data["project_name"] = request.project_name
        if request.description is not None:
            update_data["description"] = request.description
        if request.is_active is not None:
            update_data["is_active"] = request.is_active
        
        # Verify AI model if being updated
        if request.ai_model_id is not None:
            ai_model = await ai_models_collection.find_one({
                "model_id": request.ai_model_id,
                "tenant_id": tenant_id
            })
            
            if not ai_model:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"AI model '{request.ai_model_id}' not found",
                )
            
            update_data["ai_model_id"] = request.ai_model_id
        
        update_data["updated_at"] = datetime.utcnow()
        
        # Update in MongoDB
        await projects_collection.update_one(
            {"project_id": project_id, "tenant_id": tenant_id},
            {"$set": update_data}
        )
        
        # Fetch updated project
        updated_project = await projects_collection.find_one({
            "project_id": project_id,
            "tenant_id": tenant_id
        })
        
        # Convert MongoDB document to dict and remove _id and ai_model_id
        updated_project_dict = dict(updated_project)
        updated_project_dict.pop('_id', None)
        updated_project_dict.pop('ai_model_id', None)
        
        logger.info(f"Updated project '{project_id}' for tenant '{tenant_id}'")
        
        return ProjectResponse(
            success=True,
            data=updated_project_dict,
            message=f"Project '{project_id}' updated successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating project: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update project: {str(e)}"
        )


@router.delete("/tenants/{tenant_id}/projects/{project_id}")
async def delete_project(
    tenant_id: str,
    project_id: str,
    auth: AuthenticatedTenant = Depends(resolve_tenant),
):
    """
    Delete a project.
    """
    try:
        db = await MongoDBClient.get_database()
        projects_collection = db["projects"]
        
        result = await projects_collection.delete_one({
            "project_id": project_id,
            "tenant_id": tenant_id
        })
        
        if result.deleted_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{project_id}' not found",
            )
        
        logger.warning(f"Deleted project '{project_id}' for tenant '{tenant_id}'")
        
        return {
            "success": True,
            "message": f"Project '{project_id}' deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting project: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete project: {str(e)}"
        )


@router.post("/tenants/{tenant_id}/projects/{project_id}/assign-model")
async def assign_ai_model(
    tenant_id: str,
    project_id: str,
    request: AssignAIModelRequest,
    auth: AuthenticatedTenant = Depends(resolve_tenant),
):
    """
    Assign or update the AI model for a project.
    """
    try:
        db = await MongoDBClient.get_database()
        projects_collection = db["projects"]
        ai_models_collection = db["ai_models"]
        
        # Verify project exists
        project = await projects_collection.find_one({
            "project_id": project_id,
            "tenant_id": tenant_id
        })
        
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{project_id}' not found",
            )
        
        # Verify AI model exists and belongs to this tenant
        ai_model = await ai_models_collection.find_one({
            "model_id": request.ai_model_id,
            "tenant_id": tenant_id
        })
        
        if not ai_model:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"AI model '{request.ai_model_id}' not found",
            )
        
        # Update project with new AI model
        await projects_collection.update_one(
            {"project_id": project_id, "tenant_id": tenant_id},
            {"$set": {
                "ai_model_id": request.ai_model_id,
                "updated_at": datetime.utcnow()
            }}
        )
        
        logger.info(f"Assigned AI model '{request.ai_model_id}' to project '{project_id}'")
        
        return {
            "success": True,
            "message": f"AI model '{request.ai_model_id}' assigned to project '{project_id}'"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error assigning AI model: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to assign AI model: {str(e)}"
        )
