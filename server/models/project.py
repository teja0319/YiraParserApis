"""
Project and AI Model database models.
"""

import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from bson import ObjectId

logger = logging.getLogger(__name__)


class AIModel(BaseModel):
    """AI Model configuration"""
    model_id: str = Field(..., description="Unique model identifier")
    tenant_id: str = Field(..., description="Tenant ID that owns this model")
    model_name: str = Field(..., description="Display name of the AI model")
    cost_per_page: float = Field(..., gt=0, description="Cost per page in USD")
    description: Optional[str] = Field(None, description="Model description")
    provider: str = Field(default="gemini", description="AI provider (gemini, etc)")
    status: str = Field(default="active", description="Model status: active, deprecated, archived")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None,
        }


class Project(BaseModel):
    """Project model representing a hospital/clinic project within a tenant"""
    project_id: str = Field(..., description="Unique project identifier")
    tenant_id: str = Field(..., description="Parent tenant ID")
    project_name: str = Field(..., description="Display name of the project")
    description: Optional[str] = Field(None, description="Project description")
    ai_model_id: Optional[str] = Field(None, description="Associated AI Model ID")
    is_active: bool = Field(default=True, description="Project status")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional project metadata")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None,
        }


class ProjectAnalytics(BaseModel):
    """Project-level analytics"""
    project_id: str = Field(..., description="Project ID")
    tenant_id: str = Field(..., description="Tenant ID")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    uploads_count: int = Field(default=0, description="Number of uploads")
    total_pages_processed: int = Field(default=0, description="Total pages parsed")
    total_cost_usd: float = Field(default=0.0, description="Total cost in USD")
    average_parsing_time_seconds: float = Field(default=0.0, description="Average parsing time")
    success_rate: float = Field(default=100.0, description="Success rate percentage")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None,
        }


class TenantAnalytics(BaseModel):
    """Tenant-level aggregated analytics"""
    tenant_id: str = Field(..., description="Tenant ID")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    total_projects: int = Field(default=0, description="Total number of projects")
    total_uploads: int = Field(default=0, description="Total uploads across all projects")
    total_pages_processed: int = Field(default=0, description="Total pages parsed across all projects")
    total_cost_usd: float = Field(default=0.0, description="Total cost in USD across all projects")
    active_projects: int = Field(default=0, description="Number of active projects")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None,
        }
