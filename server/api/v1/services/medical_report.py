"""
Medical Report Service
Business logic layer for medical report operations
Follows service layer pattern with dependency injection
"""

import logging
import uuid
from typing import Dict, Any, Optional, List
from datetime import datetime
from fastapi import UploadFile

from server.integrations.gemini import GeminiParser
from server.integrations.azure import AzureBlobStorage
from server.common.validators import MedicalDataValidator
from server.common.utils import generate_report_id, sanitize_filename
from server.config.settings import get_settings
from server.api.v1.models.common import (
    MedicalReportParseResponse,
    MedicalReportListResponse,
    MedicalReportDeleteResponse,
    ValidationResult,
)

logger = logging.getLogger(__name__)


class MedicalReportService:
    """Service for medical report operations"""

    def __init__(self):
        """Initialize service with dependencies"""
        self.settings = get_settings()
        self.blob_storage = AzureBlobStorage(
            connection_string=self.settings.azure_connection_string,
            container_name=self.settings.azure_container_name,
        )
        self.gemini_parser = GeminiParser(
            api_key=self.settings.gemini_api_key,
            model=self.settings.gemini_model,
        )
        self.validator = MedicalDataValidator()

    async def parse_and_save_report(
        self, file: UploadFile
    ) -> MedicalReportParseResponse:
        """
        Parse medical report PDF and save to storage

        Args:
            file: Uploaded PDF file

        Returns:
            MedicalReportParseResponse with parsed data

        Raises:
            ValidationError: If file validation fails
            ParsingError: If parsing fails
            StorageError: If storage operation fails
        """
        try:
            logger.info("=" * 60)
            logger.info("🏥 Starting Medical Report Parsing")
            
            # Validate file
            logger.info("Step 1: Validating file...")
            self._validate_file(file)
            logger.info(f"✅ File validated: {file.filename}")

            # Generate report ID
            report_id = generate_report_id()
            logger.info(f"Step 2: Generated report ID: {report_id}")

            # Read file content
            logger.info("Step 3: Reading file content...")
            content = await file.read()
            logger.info(f"✅ File read: {len(content)} bytes")

            # Parse document with Gemini using native PDF support
            logger.info("Step 4: Parsing PDF with Gemini (native PDF processing)...")
            logger.info("🎉 Using Gemini's native PDF parsing - No text extraction needed!")
            
            parsed_data = self.gemini_parser.parse_pdf(
                pdf_bytes=content,
                filename=file.filename
            )

            logger.info(f"Gemini parse result type: {type(parsed_data)}")
            logger.info(f"Gemini parse result: {parsed_data}")

            if not parsed_data:
                logger.error("❌ Gemini returned None or empty data")
                raise Exception("Failed to parse medical report: Gemini returned no data")
            
            if not isinstance(parsed_data, dict):
                logger.error(f"❌ Gemini returned invalid type: {type(parsed_data)}")
                raise Exception(f"Failed to parse medical report: Invalid data type {type(parsed_data)}")
            
            logger.info(f"✅ Parsed data keys: {list(parsed_data.keys())}")

            # Validate parsed data
            logger.info("Step 5: Validating parsed data...")
            is_valid, errors, warnings, calculated = self.validator.validate_all(
                parsed_data
            )
            logger.info(f"✅ Validation complete - Valid: {is_valid}, Errors: {len(errors)}, Warnings: {len(warnings)}")

            # Determine confidence
            logger.info("Step 6: Calculating confidence score...")
            if not errors and len(warnings) <= 2:
                confidence_score = 0.95
            elif len(errors) <= 2:
                confidence_score = 0.80
            else:
                confidence_score = 0.60
            logger.info(f"✅ Confidence score: {confidence_score}")

            # Save to Azure Blob Storage
            logger.info("Step 7: Saving to Azure Blob Storage...")
            blob_name = self.blob_storage.save(
                report_data=parsed_data,
                original_filename=file.filename,
                report_id=report_id,
            )

            logger.info(f"✅ Report saved: {report_id} -> {blob_name}")

            # Build response
            logger.info("Step 8: Building response...")
            response = MedicalReportParseResponse(
                id=report_id,
                file_name=file.filename,
                status="success" if is_valid else "success_with_warnings",
                parsed_data=parsed_data,
                metadata={
                    "validation": {
                        "is_valid": is_valid,
                        "errors": errors,
                        "warnings": warnings,
                        "calculated_fields": calculated,
                    },
                    "blob_name": blob_name,
                },
                confidence_score=confidence_score,
            )
            
            logger.info("✅ Response built successfully")
            logger.info("=" * 60)

            return response

        except Exception as e:
            logger.error("=" * 60)
            logger.error(f"❌ ERROR in parse_and_save_report:")
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"Error message: {str(e)}")
            logger.exception("Full traceback:")
            logger.error("=" * 60)
            raise

    async def get_all_reports(
        self,
        limit: int = 10,
        offset: int = 0,
        patient_name: Optional[str] = None,
        report_date: Optional[str] = None,
    ) -> MedicalReportListResponse:
        """
        Retrieve all reports with optional filtering

        Args:
            limit: Maximum number of reports
            offset: Number to skip
            patient_name: Filter by patient name
            report_date: Filter by date

        Returns:
            MedicalReportListResponse with paginated results
        """
        try:
            logger.info(
                f"Listing reports: limit={limit}, offset={offset}, "
                f"patient_name={patient_name}, report_date={report_date}"
            )

            # Get all reports from storage
            all_reports = self.blob_storage.list_all()

            # Apply filters
            if patient_name or report_date:
                filtered_reports = self.blob_storage.search(
                    patient_name=patient_name, report_date=report_date
                )
            else:
                filtered_reports = all_reports

            # Apply pagination
            total = len(filtered_reports)
            paginated = filtered_reports[offset : offset + limit]

            # Convert to response models
            reports = [
                MedicalReportParseResponse(
                    id=report.get("reportId", "unknown"),
                    file_name=report.get("fileName", "unknown"),
                    status="success",
                    parsed_data=report,
                    created_at=datetime.fromisoformat(
                        report.get("uploadedAt", datetime.utcnow().isoformat())
                    ),
                )
                for report in paginated
            ]

            return MedicalReportListResponse(
                reports=reports, total=total, limit=limit, offset=offset
            )

        except Exception as e:
            logger.error(f"Error listing reports: {str(e)}")
            raise

    async def get_report_by_id(self, report_id: str) -> Optional[MedicalReportParseResponse]:
        """
        Retrieve specific report by ID

        Args:
            report_id: Unique report identifier

        Returns:
            MedicalReportParseResponse or None

        Raises:
            NotFoundError: If report not found
        """
        try:
            logger.info(f"Retrieving report: {report_id}")

            report_data = self.blob_storage.get(report_id)

            if not report_data:
                logger.warning(f"Report not found: {report_id}")
                return None

            response = MedicalReportParseResponse(
                id=report_data.get("reportId", report_id),
                file_name=report_data.get("fileName", "unknown"),
                status="success",
                parsed_data=report_data,
                created_at=datetime.fromisoformat(
                    report_data.get("uploadedAt", datetime.utcnow().isoformat())
                ),
            )

            return response

        except Exception as e:
            logger.error(f"Error retrieving report: {str(e)}")
            raise

    async def delete_report(self, report_id: str) -> MedicalReportDeleteResponse:
        """
        Delete report by ID

        Args:
            report_id: Unique report identifier

        Returns:
            MedicalReportDeleteResponse with deletion status

        Raises:
            NotFoundError: If report not found
        """
        try:
            logger.info(f"Deleting report: {report_id}")

            deleted = self.blob_storage.delete(report_id)

            if not deleted:
                logger.warning(f"Report not found for deletion: {report_id}")
                return None

            logger.info(f"Report deleted: {report_id}")

            return MedicalReportDeleteResponse(
                id=report_id, status="deleted", timestamp=datetime.utcnow()
            )

        except Exception as e:
            logger.error(f"Error deleting report: {str(e)}")
            raise

    def _validate_file(self, file: UploadFile) -> None:
        """
        Validate uploaded file

        Args:
            file: File to validate

        Raises:
            ValidationError: If file invalid
        """
        from server.core.exceptions import ValidationError

        if not file.filename:
            raise ValidationError("File name is required")

        # Check file extension
        if not any(file.filename.lower().endswith(ext) for ext in self.settings.allowed_extensions):
            raise ValidationError(
                f"Invalid file type. Allowed types: {', '.join(self.settings.allowed_extensions)}"
            )

        # TODO: Check file size when reading
