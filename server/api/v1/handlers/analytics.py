"""
Analytics endpoints for project and tenant level reporting.
Provides comprehensive analytics on usage, costs, and performance.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from server.config.settings import get_settings
from server.integrations.mongodb import MongoDBClient
from server.middleware.auth import AuthenticatedTenant, resolve_tenant
from server.models.tenant import tenant_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["Analytics"])

settings = get_settings()
ADMIN_API_KEY = settings.admin_api_key


def verify_admin_key(x_admin_key: Optional[str] = Header(None)) -> str:
    """Verify admin API key for sensitive analytics operations."""
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


@router.get("/tenants/{tenant_id}/projects/{project_id}/summary")
async def get_project_analytics(
    tenant_id: str,
    project_id: str,
    auth: AuthenticatedTenant = Depends(resolve_tenant),
):
    """
    Get comprehensive analytics for a specific project.
    Includes uploads, costs, parsing performance, and success rates.
    """
    try:
        db = await MongoDBClient.get_database()
        projects_collection = db["projects"]
        analytics_collection = db["analytics"]
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
        
        # Get AI model info
        ai_model = await ai_models_collection.find_one({
            "model_id": project.get("ai_model_id")
        })
        
        # Aggregate analytics for this project
        analytics_pipeline = [
            {"$match": {"project_id": project_id, "tenant_id": tenant_id}},
            {"$group": {
                "_id": None,
                "total_uploads": {"$sum": "$uploads_count"},
                "total_pages": {"$sum": "$total_pages_processed"},
                "total_cost": {"$sum": "$total_cost_usd"},
                "avg_parsing_time": {"$avg": "$average_parsing_time_seconds"},
                "avg_success_rate": {"$avg": "$success_rate"},
                "latest_timestamp": {"$max": "$timestamp"}
            }}
        ]
        
        analytics_result = await analytics_collection.aggregate(analytics_pipeline).to_list(None)
        
        analytics_data = analytics_result[0] if analytics_result else {
            "_id": None,
            "total_uploads": 0,
            "total_pages": 0,
            "total_cost": 0.0,
            "avg_parsing_time": 0.0,
            "avg_success_rate": 100.0,
            "latest_timestamp": None
        }
        
        return {
            "success": True,
            "tenant_id": tenant_id,
            "project_id": project_id,
            "project_name": project.get("project_name"),
            "ai_model": {
                "model_id": ai_model.get("model_id") if ai_model else None,
                "model_name": ai_model.get("model_name") if ai_model else "Unknown",
                "cost_per_page": ai_model.get("cost_per_page", 0.0) if ai_model else 0.0,
            },
            "analytics": {
                "total_uploads": analytics_data.get("total_uploads", 0),
                "total_pages_processed": analytics_data.get("total_pages", 0),
                "total_cost_usd": round(analytics_data.get("total_cost", 0.0), 2),
                "average_parsing_time_seconds": round(analytics_data.get("avg_parsing_time", 0.0), 2),
                "average_success_rate_percent": round(analytics_data.get("avg_success_rate", 100.0), 2),
                "last_activity": analytics_data.get("latest_timestamp")
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving project analytics: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve project analytics: {str(e)}"
        )


@router.get("/tenants/{tenant_id}/summary")
async def get_tenant_analytics(
    tenant_id: str,
    auth: AuthenticatedTenant = Depends(resolve_tenant),
):
    """
    Get comprehensive analytics for entire tenant.
    Aggregates data across all projects.
    """
    try:
        db = await MongoDBClient.get_database()
        projects_collection = db["projects"]
        analytics_collection = db["analytics"]
        
        # Get all projects for tenant
        projects = await projects_collection.find({
            "tenant_id": tenant_id
        }).to_list(None)
        
        active_projects = len([p for p in projects if p.get("is_active", True)])
        
        # Aggregate analytics for entire tenant
        analytics_pipeline = [
            {"$match": {"tenant_id": tenant_id}},
            {"$group": {
                "_id": None,
                "total_uploads": {"$sum": "$uploads_count"},
                "total_pages": {"$sum": "$total_pages_processed"},
                "total_cost": {"$sum": "$total_cost_usd"},
                "avg_parsing_time": {"$avg": "$average_parsing_time_seconds"},
                "avg_success_rate": {"$avg": "$success_rate"},
                "latest_timestamp": {"$max": "$timestamp"}
            }}
        ]
        
        analytics_result = await analytics_collection.aggregate(analytics_pipeline).to_list(None)
        
        analytics_data = analytics_result[0] if analytics_result else {
            "_id": None,
            "total_uploads": 0,
            "total_pages": 0,
            "total_cost": 0.0,
            "avg_parsing_time": 0.0,
            "avg_success_rate": 100.0,
            "latest_timestamp": None
        }
        
        # Breakdown by project
        project_breakdowns = []
        for project in projects:
            project_analytics_pipeline = [
                {"$match": {"project_id": project["project_id"]}},
                {"$group": {
                    "_id": None,
                    "uploads": {"$sum": "$uploads_count"},
                    "pages": {"$sum": "$total_pages_processed"},
                    "cost": {"$sum": "$total_cost_usd"},
                }}
            ]
            
            project_analytics = await analytics_collection.aggregate(project_analytics_pipeline).to_list(None)
            project_data = project_analytics[0] if project_analytics else {"_id": None, "uploads": 0, "pages": 0, "cost": 0.0}
            
            project_breakdowns.append({
                "project_id": project["project_id"],
                "project_name": project.get("project_name"),
                "uploads": project_data.get("uploads", 0),
                "pages_processed": project_data.get("pages", 0),
                "cost_usd": round(project_data.get("cost", 0.0), 2),
            })
        
        return {
            "success": True,
            "tenant_id": tenant_id,
            "summary": {
                "total_projects": len(projects),
                "active_projects": active_projects,
                "total_uploads": analytics_data.get("total_uploads", 0),
                "total_pages_processed": analytics_data.get("total_pages", 0),
                "total_cost_usd": round(analytics_data.get("total_cost", 0.0), 2),
                "average_parsing_time_seconds": round(analytics_data.get("avg_parsing_time", 0.0), 2),
                "average_success_rate_percent": round(analytics_data.get("avg_success_rate", 100.0), 2),
                "last_activity": analytics_data.get("latest_timestamp")
            },
            "project_breakdowns": project_breakdowns
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving tenant analytics: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve tenant analytics: {str(e)}"
        )


@router.get("/admin/tenants/{tenant_id}/detailed")
async def get_admin_tenant_analytics(
    tenant_id: str,
    admin_key: str = Header(None, alias="X-Admin-Key")
):
    """
    Get detailed admin analytics for a tenant including billing breakdown.
    
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
        projects_collection = db["projects"]
        analytics_collection = db["analytics"]
        ai_models_collection = db["ai_models"]
        
        # Get all projects
        projects = await projects_collection.find({
            "tenant_id": tenant_id
        }).to_list(None)
        
        # Aggregate analytics
        analytics_pipeline = [
            {"$match": {"tenant_id": tenant_id}},
            {"$group": {
                "_id": None,
                "total_uploads": {"$sum": "$uploads_count"},
                "total_pages": {"$sum": "$total_pages_processed"},
                "total_cost": {"$sum": "$total_cost_usd"},
            }}
        ]
        
        analytics_result = await analytics_collection.aggregate(analytics_pipeline).to_list(None)
        analytics_data = analytics_result[0] if analytics_result else {
            "total_uploads": 0,
            "total_pages": 0,
            "total_cost": 0.0,
        }
        
        return {
            "success": True,
            "tenant": {
                "tenant_id": tenant.tenant_id,
                "name": tenant.name,
                "email": tenant.email,
                "created_at": tenant.created_at,
                "active": tenant.active,
                "quota": tenant.quota.dict()
            },
            "projects": len(projects),
            "analytics": {
                "total_uploads": analytics_data.get("total_uploads", 0),
                "total_pages_processed": analytics_data.get("total_pages", 0),
                "total_cost_usd": round(analytics_data.get("total_cost", 0.0), 2),
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving admin tenant analytics: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve admin tenant analytics: {str(e)}"
        )
