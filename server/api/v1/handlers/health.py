"""
Health check handler
"""

from fastapi import APIRouter
from server.api.v1.models.common import HealthCheckResponse
from server.config.settings import get_settings
from datetime import datetime

router = APIRouter()


@router.get("", response_model=HealthCheckResponse)
async def health_check():
    """
    Health check endpoint

    Returns:
        HealthCheckResponse: Service status
    """
    settings = get_settings()
    return HealthCheckResponse(
        status="healthy",
        version=settings.app_version,
        gemini_api_configured=bool(settings.gemini_api_key),
        storage_type="Azure Blob Storage",
        timestamp=datetime.utcnow(),
    )
