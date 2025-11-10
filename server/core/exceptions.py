"""
Google API standards compliant exception definitions.
Follows: https://cloud.google.com/apis/design/errors
"""

from enum import Enum
from typing import Optional, Dict, Any


class ErrorCode(str, Enum):
    """Google API standard error codes"""
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    FAILED_PRECONDITION = "FAILED_PRECONDITION"
    OUT_OF_RANGE = "OUT_OF_RANGE"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    NOT_FOUND = "NOT_FOUND"
    ABORTED = "ABORTED"
    ALREADY_EXISTS = "ALREADY_EXISTS"
    CONFLICT = "CONFLICT"
    RESOURCE_EXHAUSTED = "RESOURCE_EXHAUSTED"
    CANCELLED = "CANCELLED"
    DATA_LOSS = "DATA_LOSS"
    UNKNOWN = "UNKNOWN"
    INTERNAL = "INTERNAL"
    UNAVAILABLE = "UNAVAILABLE"
    DEADLINE_EXCEEDED = "DEADLINE_EXCEEDED"


class APIException(Exception):
    """Base application exception following Google API error format"""

    def __init__(
        self,
        error_code: str,
        message: str,
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
    ):
        self.error_code = error_code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        self.request_id = request_id
        super().__init__(message)

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to Google API error format"""
        error_dict = {
            "error": {
                "code": self.error_code,
                "message": self.message,
                "details": self.details,
            }
        }
        if self.request_id:
            error_dict["error"]["requestId"] = self.request_id
        return error_dict


class ValidationError(APIException):
    """Raised when input validation fails"""

    def __init__(
        self,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
    ):
        super().__init__(
            error_code=ErrorCode.INVALID_ARGUMENT,
            message=message,
            status_code=400,
            details=details,
            request_id=request_id,
        )


class NotFoundError(APIException):
    """Raised when resource is not found"""

    def __init__(
        self,
        message: str,
        resource: Optional[str] = None,
        request_id: Optional[str] = None,
    ):
        details = {"resource": resource} if resource else {}
        super().__init__(
            error_code=ErrorCode.NOT_FOUND,
            message=message,
            status_code=404,
            details=details,
            request_id=request_id,
        )


class ConflictError(APIException):
    """Raised when resource conflicts"""

    def __init__(
        self,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
    ):
        super().__init__(
            error_code=ErrorCode.CONFLICT,
            message=message,
            status_code=409,
            details=details,
            request_id=request_id,
        )


class StorageError(APIException):
    """Raised when storage operation fails"""

    def __init__(
        self,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
    ):
        super().__init__(
            error_code=ErrorCode.INTERNAL,
            message=message,
            status_code=500,
            details=details,
            request_id=request_id,
        )


class ParsingError(APIException):
    """Raised when document parsing fails"""

    def __init__(
        self,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
    ):
        super().__init__(
            error_code=ErrorCode.INTERNAL,
            message=message,
            status_code=500,
            details=details,
            request_id=request_id,
        )


class ResourceExhaustedError(APIException):
    """Raised when rate limit or quota exceeded"""

    def __init__(
        self,
        message: str,
        retry_after: Optional[int] = None,
        request_id: Optional[str] = None,
    ):
        details = {"retryAfter": retry_after} if retry_after else {}
        super().__init__(
            error_code=ErrorCode.RESOURCE_EXHAUSTED,
            message=message,
            status_code=429,
            details=details,
            request_id=request_id,
        )


class PermissionDeniedError(APIException):
    """Raised when permission is denied"""

    def __init__(
        self,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
    ):
        super().__init__(
            error_code=ErrorCode.PERMISSION_DENIED,
            message=message,
            status_code=403,
            details=details,
            request_id=request_id,
        )
