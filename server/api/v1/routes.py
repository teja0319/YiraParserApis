"""
API v1 route definitions
Multi-Tenant Medical Report Parser API
"""

from fastapi import APIRouter

from server.api.v1.handlers import health
from server.api.v1.handlers import medical_reports_multitenant
from server.api.v1.handlers import tenant_management
from server.api.v1.handlers import ai_models
from server.api.v1.handlers import projects
from server.api.v1.handlers import analytics

# Create main router
router = APIRouter()

# Health check
router.include_router(health.router, prefix="/health", tags=["System Health"])

# Multi-tenant medical reports (main feature)
router.include_router(medical_reports_multitenant.router, tags=["Medical Reports"])

# Tenant management (admin)
router.include_router(tenant_management.router, tags=["Tenant Management"])

# AI Models and Projects routes
router.include_router(ai_models.router, tags=["AI Models Management"])
router.include_router(projects.router, tags=["Projects"])

router.include_router(analytics.router, tags=["Analytics"])
