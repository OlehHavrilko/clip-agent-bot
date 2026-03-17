import re
import os
from typing import Optional


def slugify(text: str) -> str:
    """
    Convert film title to safe filename.
    Lowercase, spaces→underscores, remove special chars.
    """
    # Convert to lowercase and replace spaces with underscores
    text = text.lower().replace(' ', '_')
    # Remove special characters, keep only alphanumeric and underscores
    text = re.sub(r'[^a-z0-9_]', '', text)
    return text


def get_file_size_mb(path: str) -> float:
    """
    Return file size in megabytes.
    """
    if not os.path.exists(path):
        return 0.0
    size_bytes = os.path.getsize(path)
    return size_bytes / (1024 * 1024)


def validate_duration(start: str, end: str) -> bool:
    """
    Validate that duration does not exceed MAX_CLIP_DURATION.
    Returns True if valid, False if exceeds limit.
    """
    from datetime import datetime
    
    try:
        start_time = datetime.strptime(start, '%H:%M:%S')
        end_time = datetime.strptime(end, '%H:%M:%S')
        
        # Calculate duration in seconds
        duration = (end_time - start_time).total_seconds()
        
        from .config import MAX_CLIP_DURATION
        return duration <= MAX_CLIP_DURATION
        
    except ValueError:
        return False