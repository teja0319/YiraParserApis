"""
Utility functions for common operations
"""

import uuid
import json
from typing import Dict, Any
from datetime import datetime


def generate_report_id() -> str:
    """Generate a unique report ID"""
    return str(uuid.uuid4())


def format_timestamp(dt: datetime) -> str:
    """Format datetime to ISO format string"""
    if isinstance(dt, str):
        return dt
    return dt.isoformat() + "Z"


def sanitize_filename(filename: str) -> str:
    """Sanitize filename for safe storage"""
    import re

    # Remove special characters
    filename = re.sub(r"[^\w\s.-]", "", filename)
    # Replace spaces with underscores
    filename = re.sub(r"\s+", "_", filename)
    return filename


def parse_json_safely(json_str: str) -> Dict[str, Any]:
    """Safely parse JSON string with error handling"""
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        return {"error": f"Invalid JSON: {str(e)}", "raw": json_str}


def truncate_string(text: str, max_length: int = 100) -> str:
    """Truncate string to max length with ellipsis"""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


def is_valid_uuid(value: str) -> bool:
    """Check if string is valid UUID"""
    try:
        uuid.UUID(value)
        return True
    except (ValueError, AttributeError):
        return False
