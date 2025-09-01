"""
Utility Helper Functions
"""

import json
import time
import uuid
import logging
from typing import Dict, Any, List
from pathlib import Path

logger = logging.getLogger(__name__)


def generate_id() -> str:
    """Generate unique ID"""
    return str(uuid.uuid4())


def get_current_timestamp() -> int:
    """Get current Unix timestamp"""
    return int(time.time())


def safe_json_parse(data: str, default: Any = None) -> Any:
    """Safely parse JSON string"""
    try:
        return json.loads(data)
    except (json.JSONDecodeError, TypeError):
        logger.warning(f"Failed to parse JSON: {data[:100]}...")
        return default


def format_timestamp(timestamp: int) -> str:
    """Format timestamp to readable string"""
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))


def truncate_text(text: str, max_length: int = 100) -> str:
    """Truncate text to specified length"""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


def get_recommendation_text(recommendation: str) -> str:
    """Convert recommendation to Korean text"""
    recommendations = {
        "adopt": "✅ 채택 권고",
        "hold": "⏸️ 보류 권고",
        "discard": "❌ 폐기 권고",
    }
    return recommendations.get(recommendation, recommendation or "권고 없음")


def create_directory_if_not_exists(path: Path) -> None:
    """Create directory if it doesn't exist"""
    path.mkdir(parents=True, exist_ok=True)


def validate_required_fields(data: Dict[str, Any], required_fields: List[str]) -> bool:
    """Validate that required fields are present"""
    return all(field in data and data[field] is not None for field in required_fields)


def sanitize_filename(filename: str) -> str:
    """Sanitize filename for safe file operations"""
    import re

    # Remove or replace unsafe characters
    sanitized = re.sub(r'[<>:"/\\|?*]', "_", filename)
    # Limit length
    if len(sanitized) > 255:
        sanitized = sanitized[:255]
    return sanitized


def get_file_size_mb(file_path: Path) -> float:
    """Get file size in MB"""
    try:
        return file_path.stat().st_size / (1024 * 1024)
    except FileNotFoundError:
        return 0.0


def log_function_call(func_name: str, **kwargs: Any) -> None:
    """Log function call with parameters"""
    params = ", ".join([f"{k}={v}" for k, v in kwargs.items()])
    logger.debug(f"Function call: {func_name}({params})")


def create_error_response(
    message: str, error_code: str = "UNKNOWN_ERROR"
) -> Dict[str, Any]:
    """Create standardized error response"""
    return {
        "error": True,
        "message": message,
        "error_code": error_code,
        "timestamp": get_current_timestamp(),
    }


def create_success_response(data: Any, message: str = "Success") -> Dict[str, Any]:
    """Create standardized success response"""
    return {
        "error": False,
        "message": message,
        "data": data,
        "timestamp": get_current_timestamp(),
    }





