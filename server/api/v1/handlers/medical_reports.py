"""
Medical reports handler
Follows Google API standards for resource operations
"""

from fastapi import APIRouter, UploadFile, File, Query
from typing import Optional, List
import logging

from server.api.v1.models.common import (
    MedicalReportParseResponse,
    MedicalReportListResponse,
    MedicalReportDeleteResponse,
)
from server.api.v1.services.medical_report import MedicalReportService
from server.config.settings import get_settings
from server.core.exceptions import NotFoundError, StorageError

logger = logging.getLogger(__name__)

router = APIRouter()
settings = get_settings()

# Initialize service
service = MedicalReportService()


@router.post("", response_model=MedicalReportParseResponse)
async def parse_medical_report(file: UploadFile = File(...)):
    """
    Parse and store a medical report PDF

    Args:
        file: PDF file to parse

    Returns:
        MedicalReportParseResponse: Parsed report data

    Raises:
        ValidationError: If file format invalid
        StorageError: If storage operation fails
    """
    try:
        logger.info(f"Parsing medical report: {file.filename}")
        result = await service.parse_and_save_report(file)
        return result
    except Exception as e:
        logger.error(f"Error parsing report: {str(e)}")
        raise StorageError(f"Failed to parse medical report: {str(e)}")


@router.get("", response_model=MedicalReportListResponse)
async def list_medical_reports(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    patient_name: Optional[str] = Query(None),
    report_date: Optional[str] = Query(None),
):
    """
    List medical reports with optional filtering

    Args:
        limit: Maximum number of reports to return
        offset: Number of reports to skip
        patient_name: Filter by patient name
        report_date: Filter by report date

    Returns:
        MedicalReportListResponse: List of reports

    Raises:
        StorageError: If retrieval fails
    """
    try:
        logger.info(f"Listing reports (limit={limit}, offset={offset})")
        result = await service.get_all_reports(
            limit=limit,
            offset=offset,
            patient_name=patient_name,
            report_date=report_date,
        )
        return result
    except Exception as e:
        logger.error(f"Error listing reports: {str(e)}")
        raise StorageError(f"Failed to list medical reports: {str(e)}")


@router.get("/{report_id}", response_model=MedicalReportParseResponse)
async def get_medical_report(report_id: str):
    """
    Get a specific medical report by ID

    Args:
        report_id: Unique report identifier

    Returns:
        MedicalReportParseResponse: Report data

    Raises:
        NotFoundError: If report not found
        StorageError: If retrieval fails
    """
    try:
        logger.info(f"Retrieving report: {report_id}")
        result = await service.get_report_by_id(report_id)
        if not result:
            raise NotFoundError(f"Report not found", resource=f"reports/{report_id}")
        return result
    except NotFoundError:
        raise
    except Exception as e:
        logger.error(f"Error retrieving report: {str(e)}")
        raise StorageError(f"Failed to retrieve medical report: {str(e)}")


@router.delete("/{report_id}", response_model=MedicalReportDeleteResponse)
async def delete_medical_report(report_id: str):
    """
    Delete a medical report by ID

    Args:
        report_id: Unique report identifier

    Returns:
        MedicalReportDeleteResponse: Deletion status

    Raises:
        NotFoundError: If report not found
        StorageError: If deletion fails
    """
    try:
        logger.info(f"Deleting report: {report_id}")
        result = await service.delete_report(report_id)
        if not result:
            raise NotFoundError(f"Report not found", resource=f"reports/{report_id}")
        return result
    except NotFoundError:
        raise
    except Exception as e:
        logger.error(f"Error deleting report: {str(e)}")
        raise StorageError(f"Failed to delete medical report: {str(e)}")
