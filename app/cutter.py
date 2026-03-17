import asyncio
import os
import subprocess
from datetime import datetime, timedelta
from typing import Optional
from .config import DOWNLOADS_DIR, MAX_CLIP_DURATION
from .utils import get_file_size_mb, validate_duration


async def cut_clip(input_path: str, start: str, end: str, job_id: str) -> str:
    """
    Cut video clip using ffmpeg with specified start and end timestamps.
    
    Returns path to the cut clip or raises RuntimeError on failure.
    """
    # Validate duration
    if not validate_duration(start, end):
        raise RuntimeError(f"Clip duration exceeds maximum allowed ({MAX_CLIP_DURATION} seconds)")
    
    output_path = os.path.join(DOWNLOADS_DIR, f"{job_id}_clip.mp4")
    
    # Build ffmpeg command
    cmd = [
        'ffmpeg',
        '-i', input_path,
        '-ss', start,
        '-to', end,
        '-c:v', 'libx264',
        '-preset', 'fast',
        '-crf', '28',
        '-c:a', 'aac',
        '-b:a', '128k',
        '-avoid_negative_ts', 'make_zero',
        '-movflags', '+faststart',
        '-y', output_path
    ]
    
    try:
        # Run ffmpeg as subprocess
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown ffmpeg error"
            raise RuntimeError(f"FFmpeg failed: {error_msg}")
        
        if not os.path.exists(output_path):
            raise RuntimeError("Output file was not created")
            
        return output_path
        
    except Exception as e:
        raise RuntimeError(f"Failed to cut clip: {str(e)}")


def cleanup(job_id: str) -> None:
    """
    Delete all files in downloads/ matching {job_id}*.
    """
    try:
        for filename in os.listdir(DOWNLOADS_DIR):
            if filename.startswith(f"{job_id}_"):
                file_path = os.path.join(DOWNLOADS_DIR, filename)
                if os.path.isfile(file_path):
                    os.remove(file_path)
    except Exception as e:
        print(f"Cleanup failed for job {job_id}: {str(e)}")


def format_timestamp(seconds: float) -> str:
    """
    Convert seconds to HH:MM:SS format.
    """
    td = timedelta(seconds=seconds)
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def add_buffer_to_timestamp(timestamp: str, buffer_seconds: int = 30) -> Tuple[str, str]:
    """
    Add buffer to timestamp range.
    Returns (start_with_buffer, end_with_buffer).
    """
    try:
        # Parse input timestamp (assuming it's end time)
        time_obj = datetime.strptime(timestamp, '%H:%M:%S')
        total_seconds = (time_obj.hour * 3600 + time_obj.minute * 60 + time_obj.second)
        
        # Calculate start and end with buffer
        start_seconds = max(0, total_seconds - buffer_seconds)
        end_seconds = total_seconds + buffer_seconds
        
        start_time = format_timestamp(start_seconds)
        end_time = format_timestamp(end_seconds)
        
        return start_time, end_time
        
    except ValueError:
        # If parsing fails, return original with default buffer
        return "00:00:00", "00:01:00"


def adjust_timestamps_for_confidence(scene_data: dict) -> Tuple[str, str]:
    """
    Adjust timestamps based on confidence level.
    """
    start = scene_data.get("timestamp_start", "00:00:00")
    end = scene_data.get("timestamp_end", "00:01:00")
    confidence = scene_data.get("confidence", "medium")
    
    if confidence.lower() == "low":
        # Widen timestamp range by 2 minutes each side
        try:
            start_obj = datetime.strptime(start, '%H:%M:%S')
            end_obj = datetime.strptime(end, '%H:%M:%S')
            
            start_adj = start_obj - timedelta(minutes=2)
            end_adj = end_obj + timedelta(minutes=2)
            
            # Ensure start doesn't go below 0
            if start_adj < datetime(1900, 1, 1):
                start_adj = datetime(1900, 1, 1)
            
            start = start_adj.strftime('%H:%M:%S')
            end = end_adj.strftime('%H:%M:%S')
            
        except ValueError:
            pass  # Use original timestamps if parsing fails
    
    return start, end