import asyncio
import os
import re
import yt_dlp
import httpx
import urllib.parse
from html.parser import HTMLParser
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


class ClipCafeParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.mp4_url = None
        self.in_video_tag = False

    def handle_starttag(self, tag, attrs):
        if tag == 'video':
            self.in_video_tag = True
            for attr in attrs:
                if attr[0] == 'src' and attr[1].endswith('.mp4'):
                    self.mp4_url = attr[1]
        elif tag == 'source' and self.in_video_tag:
            for attr in attrs:
                if attr[0] == 'src' and attr[1].endswith('.mp4'):
                    self.mp4_url = attr[1]
        elif tag == 'a':
            for attr in attrs:
                if attr[0] == 'href' and attr[1].endswith('.mp4'):
                    self.mp4_url = attr[1]
                elif attr[0] == 'data-video' and attr[1].endswith('.mp4'):
                    self.mp4_url = attr[1]

    def handle_endtag(self, tag):
        if tag == 'video':
            self.in_video_tag = False


async def search_clipcafe(query: str, job_id: str) -> str | None:
    """
    Search clip.cafe for the query and download the first video found.
    """
    try:
        # Build search URL
        search_url = f"https://clip.cafe/search/?q={urllib.parse.quote(query)}"
        
        # Make HTTP request
        async with httpx.AsyncClient() as client:
            response = await client.get(search_url)
            if response.status_code != 200:
                return None
                
            # Parse HTML for .mp4 URLs
            parser = ClipCafeParser()
            parser.feed(response.text)
            
            if parser.mp4_url:
                # Download the video
                video_url = parser.mp4_url
                if not video_url.startswith('http'):
                    video_url = f"https://clip.cafe{video_url}"
                
                return await download_video(video_url, job_id)
                
    except Exception as e:
        print(f"clip.cafe search failed for query '{query}': {str(e)}")
        
    return None


async def search_playphrase(query: str, job_id: str) -> str | None:
    """
    Search playphrase.me API for the query and download the first video found.
    """
    try:
        api_url = f"https://www.playphrase.me/api/v1/phrases/search?q={urllib.parse.quote(query)}&limit=5"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(api_url)
            if response.status_code != 200:
                return None
                
            data = response.json()
            if data and 'phrases' in data and len(data['phrases']) > 0:
                video_url = data['phrases'][0]['video']
                return await download_video(video_url, job_id)
                
    except Exception as e:
        print(f"playphrase.me search failed for query '{query}': {str(e)}")
        
    return None


async def search_and_download(scene_data: dict, job_id: str) -> str:
    """
    Search for the scene and download the video using multiple sources.
    
    Tries clip.cafe first, then playphrase.me, then YouTube.
    Returns path to downloaded file or raises RuntimeError if all fail.
    """
    search_queries = scene_data.get("search_queries", [])
    if not search_queries:
        raise RuntimeError("No search queries provided")
    
    for query in search_queries:
        try:
            # Try clip.cafe first
            print(f"Trying clip.cafe for query: {query}")
            result = await search_clipcafe(query, job_id)
            if result:
                print(f"Successfully downloaded from clip.cafe")
                return result
                
            # Try playphrase.me second
            print(f"Trying playphrase.me for query: {query}")
            result = await search_playphrase(query, job_id)
            if result:
                print(f"Successfully downloaded from playphrase.me")
                return result
                
            # Fallback to YouTube
            print(f"Trying YouTube for query: {query}")
            video_info = await search_youtube(query)
            if video_info:
                video_url = f"https://youtube.com/watch?v={video_info['id']}"
                download_path = await download_video(video_url, job_id)
                
                if download_path and os.path.exists(download_path):
                    print(f"Successfully downloaded from YouTube")
                    return download_path
                    
        except Exception as e:
            print(f"Failed to download with query '{query}': {str(e)}")
            continue
    
    raise RuntimeError("Video not found from any source")
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