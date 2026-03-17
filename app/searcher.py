import asyncio
import os
import re
import yt_dlp
from typing import List, Tuple, Optional
from .config import DOWNLOADS_DIR


async def search_and_download(scene_data: dict, job_id: str) -> str:
    """
    Search YouTube for the scene and download the video.
    
    Tries each query in scene_data["search_queries"] until successful.
    Returns path to downloaded file or raises RuntimeError if all fail.
    """
    search_queries = scene_data.get("search_queries", [])
    if not search_queries:
        raise RuntimeError("No search queries provided")
    
    for query in search_queries:
        try:
            # Search for videos
            video_info = await search_youtube(query)
            if not video_info:
                continue
                
            # Download the first result
            video_url = f"https://youtube.com/watch?v={video_info['id']}"
            download_path = await download_video(video_url, job_id)
            
            if download_path and os.path.exists(download_path):
                return download_path
                
        except Exception as e:
            # Log error and try next query
            print(f"Failed to download with query '{query}': {str(e)}")
            continue
    
    raise RuntimeError("Video not found")


async def search_youtube(query: str) -> Optional[dict]:
    """
    Search YouTube and return video info for the first result.
    """
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True,
        'skip_download': True,
        'playlist_items': '1',
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            search_query = f"ytsearch1:{query}"
            info = ydl.extract_info(search_query, download=False)
            
            if 'entries' in info and info['entries']:
                entry = info['entries'][0]
                return {
                    'id': entry['id'],
                    'title': entry.get('title', ''),
                    'url': entry['url']
                }
                
    except Exception as e:
        print(f"Search failed for query '{query}': {str(e)}")
        
    return None


async def download_video(video_url: str, job_id: str) -> Optional[str]:
    """
    Download YouTube video with specified format and quality settings.
    """
    output_template = os.path.join(DOWNLOADS_DIR, f"{job_id}_raw.%(ext)s")
    
    ydl_opts = {
        'format': 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': output_template,
        'merge_output_format': 'mp4',
        'no_playlist': True,
        'no_warnings': True,
        'max_filesize': 500 * 1024 * 1024,  # 500MB limit
        'quiet': True,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
            
            # Get the actual output path
            if 'filepath' in info:
                return info['filepath']
            else:
                # Fallback: find the downloaded file
                for file in os.listdir(DOWNLOADS_DIR):
                    if file.startswith(f"{job_id}_raw."):
                        return os.path.join(DOWNLOADS_DIR, file)
                        
    except Exception as e:
        print(f"Download failed for {video_url}: {str(e)}")
        
    return None


def get_video_duration(video_path: str) -> float:
    """
    Get video duration in seconds using yt-dlp.
    """
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_path, download=False)
            return info.get('duration', 0)
            
    except Exception:
        return 0.0