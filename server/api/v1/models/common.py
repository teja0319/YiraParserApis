"""
API v1 request/response models following Google API standards
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class HealthCheckResponse(BaseModel):
    """Health check response model"""

    status: str = Field(..., description="Service status")
    version: str = Field(..., description="API version")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    gemini_api_configured: bool = Field(..., description="Whether Gemini API is configured")
    storage_type: str = Field(..., description="Type of storage backend")


class ErrorDetail(BaseModel):
    """Error detail model following Google API standards"""

    code: str = Field(..., description="Error code")
    message: str = Field(..., description="Error message")
    details: Dict[str, Any] = Field(default_factory=dict, description="Additional error details")


class MedicalReportParseRequest(BaseModel):
    """Request model for parsing medical reports"""

    file_name: str = Field(..., description="Original file name")
    content: bytes = Field(..., description="File content (base64 encoded)")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Optional metadata")


class PatientInfo(BaseModel):
    """Patient information model"""

    name: Optional[str] = Field(None, description="Patient name")
    age: Optional[int] = Field(None, description="Patient age")
    gender: Optional[str] = Field(None, description="Patient gender")
    date_of_birth: Optional[str] = Field(None, description="Date of birth")
    contact_number: Optional[str] = Field(None, description="Contact number")


class VitalSigns(BaseModel):
    """Vital signs model"""

    temperature: Optional[float] = Field(None, description="Temperature (°C)")
    blood_pressure: Optional[str] = Field(None, description="Blood pressure (mmHg)")
    heart_rate: Optional[int] = Field(None, description="Heart rate (bpm)")
    respiration_rate: Optional[int] = Field(None, description="Respiration rate (/min)")
    weight: Optional[float] = Field(None, description="Weight (kg)")
    height: Optional[float] = Field(None, description="Height (cm)")
    bmi: Optional[float] = Field(None, description="BMI (kg/m²)")


class LabResult(BaseModel):
    """Single lab test result"""

    test_name: str = Field(..., description="Test name")
    result: str = Field(..., description="Test result")
    unit: Optional[str] = Field(None, description="Unit of measurement")
    reference_range: Optional[str] = Field(None, description="Reference range")
    status: Optional[str] = Field(None, description="Result status (normal, high, low, etc)")


class ImageInfo(BaseModel):
    """Information about an image found in the report"""

    image_number: int = Field(..., description="Sequential image number")
    description: str = Field(..., description="Description of the image content")
    page: Optional[int] = Field(None, description="Page number where image appears")


class PhotoComparison(BaseModel):
    """Photo comparison analysis for human images in the report"""

    images_found: List[ImageInfo] = Field(
        default_factory=list, description="List of human images found in the document"
    )
    comparison_performed: bool = Field(
        False, description="Whether image comparison was performed"
    )
    similarity_percentage: Optional[float] = Field(
        None, 
        ge=0, 
        le=100, 
        description="Similarity percentage between images (0-100)"
    )
    comparison_details: Optional[str] = Field(
        None, description="Detailed explanation of comparison results"
    )
    notes: Optional[str] = Field(
        None, description="Additional observations about the images"
    )


class MedicalReportParseResponse(BaseModel):
    """Response model for parsed medical report"""

    id: str = Field(..., description="Unique report ID")
    file_name: str = Field(..., description="Original file name")
    status: str = Field(..., description="Processing status")
    parsed_data: Dict[str, Any] = Field(
        ..., description="Parsed medical report data"
    )
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Response metadata")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    confidence_score: Optional[float] = Field(
        None, description="Data extraction confidence score (0-1)"
    )


class MedicalReportListResponse(BaseModel):
    """Response model for listing medical reports"""

    reports: List[MedicalReportParseResponse] = Field(..., description="List of reports")
    total: int = Field(..., description="Total number of reports")
    limit: int = Field(..., description="Query limit")
    offset: int = Field(..., description="Query offset")


class MedicalReportDeleteResponse(BaseModel):
    """Response model for delete operation"""

    id: str = Field(..., description="Deleted report ID")
    status: str = Field(..., description="Deletion status")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ValidationResult(BaseModel):
    """Data validation result"""

    is_valid: bool = Field(..., description="Whether data is valid")
    errors: List[str] = Field(default_factory=list, description="Validation errors")
    warnings: List[str] = Field(default_factory=list, description="Validation warnings")
    confidence: str = Field(..., description="Confidence level (HIGH, MEDIUM, LOW)")
