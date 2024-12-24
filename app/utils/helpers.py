import json
import hashlib
from typing import Dict, Any, Optional
from datetime import datetime

def generate_cache_key(prefix: str, data: str) -> str:
    """Generate a cache key for Redis"""
    return f"{prefix}:{hashlib.md5(data.encode()).hexdigest()}"

def safe_json_loads(data: str, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Safely load JSON data with fallback"""
    try:
        return json.loads(data)
    except (json.JSONDecodeError, TypeError):
        return default or {}

def format_timestamp(dt: datetime) -> str:
    """Format datetime for consistent timestamp representation"""
    return dt.isoformat()

def parse_timestamp(timestamp_str: str) -> datetime:
    """Parse timestamp string to datetime object"""
    try:
        return datetime.fromisoformat(timestamp_str)
    except (ValueError, TypeError):
        return datetime.utcnow()

def calculate_metrics(values: list) -> Dict[str, float]:
    """Calculate basic statistical metrics"""
    if not values:
        return {
            'mean': 0.0,
            'min': 0.0,
            'max': 0.0,
            'count': 0
        }
    
    return {
        'mean': sum(values) / len(values),
        'min': min(values),
        'max': max(values),
        'count': len(values)
    }

def truncate_text(text: str, max_length: int = 100) -> str:
    """Truncate text to specified length with ellipsis"""
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..." 