"""
Parsing job models and schemas for MongoDB persistence.
Defines the structure for background parsing jobs.
"""

from enum import Enum
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    """Status of a parsing job."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class WebhookMeta(BaseModel):
    """Webhook delivery metadata."""
    delivered: bool = False
    status: str = "pending"  # pending, success, fail(reason)
    webhook_url: Optional[str] = None
    last_attempt_at: Optional[float] = None
    attempts: int = 0


class BlobFileInfo(BaseModel):
    """Information about a file stored in blob storage."""
    filename: str
    blob_url: str
    size_mb: float
    content_hash: Optional[str] = None


class ParsedReportData(BaseModel):
    """Parsed medical report data from AI model."""
    # Core medical information
    patient_name: Optional[str] = None
    date_of_visit: Optional[str] = None
    diagnosis: Optional[List[str]] = None
    medications: Optional[List[Dict[str, Any]]] = None
    procedures: Optional[List[Dict[str, Any]]] = None
    lab_results: Optional[List[Dict[str, Any]]] = None
    imaging_findings: Optional[List[Dict[str, Any]]] = None
    recommendations: Optional[List[str]] = None
    photo_comparison: Optional[Dict[str, Any]] = None
    confidence_score: Optional[float] = None
    confidence_summary: Optional[str] = None
    
    class Config:
        extra = "allow"  # Allow additional fields


class ParsingJob(BaseModel):
    """MongoDB schema for parsing jobs."""
    # Job identity and scope
    job_id: str = Field(description="Unique job identifier (MongoDB ObjectId as string)")
    tenant_id: str = Field(description="Tenant identifier")
    project_id: str = Field(description="Project identifier")
    report_id: str = Field(description="Report identifier")
    
    # File information
    files: List[BlobFileInfo] = Field(
        default_factory=list,
        description="List of uploaded files with blob URLs"
    )
    total_size_mb: float = Field(description="Total size of all files in MB")
    
    # Job status
    status: JobStatus = Field(
        default=JobStatus.PENDING,
        description="Current job status"
    )
    message: Optional[str] = Field(
        default=None,
        description="Human-readable status message"
    )
    
    # Parsing details (populated after processing)
    files_processed: int = Field(default=0, description="Number of files successfully processed")
    successful_parses: int = Field(default=0, description="Number of successful parses")
    failed_parses: int = Field(default=0, description="Number of failed parses")
    parsing_time_seconds: Optional[float] = Field(
        default=None,
        description="Time taken to parse in seconds"
    )
    parsed_data: Optional[ParsedReportData] = Field(
        default=None,
        description="Consolidated parsed medical data"
    )
    
    # Retry logic
    retry_count: int = Field(default=0, description="Number of retry attempts")
    max_retries: int = Field(default=3, description="Maximum number of retries")
    last_error: Optional[str] = Field(
        default=None,
        description="Last error message if job failed"
    )
    
    # Webhook handling
    webhook_meta: Optional[WebhookMeta] = Field(
        default_factory=WebhookMeta,
        description="Webhook delivery metadata"
    )
    
    # Timestamps
    created_at: float = Field(description="Unix timestamp when job was created")
    started_at: Optional[float] = Field(
        default=None,
        description="Unix timestamp when processing started"
    )
    completed_at: Optional[float] = Field(
        default=None,
        description="Unix timestamp when processing completed"
    )
    
    # AI Model configuration
    model_id: str = Field(description="AI model ID used for parsing")
    model_name: str = Field(description="AI model name (e.g., gemini-2.5-flash)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "job_id": "507f1f77bcf86cd799439011",
                "tenant_id": "tenant-001",
                "project_id": "project-001",
                "report_id": "report-001",
                "files": [
                    {
                        "filename": "medical_report.pdf",
                        "blob_url": "https://storage.example.com/tenant-001/20250113_120000_medical_report.pdf",
                        "size_mb": 2.5
                    }
                ],
                "total_size_mb": 2.5,
                "status": "pending",
                "message": "Parsing queued",
                "files_processed": 0,
                "successful_parses": 0,
                "failed_parses": 0,
                "retry_count": 0,
                "max_retries": 3,
                "webhook_meta": {
                    "delivered": False,
                    "status": "pending",
                    "webhook_url": "https://example.com/webhook"
                },
                "created_at": 1704830400.0,
                "model_id": "model-001",
                "model_name": "gemini-2.5-flash"
            }
        }
