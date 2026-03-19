import asyncio
import os
import re
import yt_dlp
import httpx
import urllib.parse
from html.parser import HTMLParser
from typing import List, Tuple, Optional
from .config import DOWNLOADS_DIR


async def search_and_download(scene_data: dict, job_id: str):
    """
    Search for the scene and download the video using multiple sources.
    
    Tries each query in scene_data["search_queries"] with various formats.
    Returns path to downloaded file or dict with links if all fail.
    """
    from .subtitles import find_timestamp

    search_queries = scene_data.get("search_queries", [])
    if not search_queries:
        return {
            "type": "links",
            "urls": [],
            "message": "Не смог скачать видео автоматически. Вот ссылки для ручного поиска:"
        }

    video_id = None
    # Try all queries with different formats
    for query in search_queries:
        # Try YouTube with different formats
        youtube_formats = [
            f"ytsearch5:{query}",
            f"ytsearch5:{query} scene HD",
            f"ytsearch5:{query} full scene",
            f"ytsearch5:{query} movie clip"
        ]

        for yt_format in youtube_formats:
            try:
                video_info = await search_youtube(yt_format)
                if video_info:
                    video_id = video_info['id']
                    break
            except Exception:
                continue
        if video_id:
            break

    if video_id:
        # Download subtitles
        subtitle_path = os.path.join(DOWNLOADS_DIR, f"{job_id}_subs.en.srt")
        try:
            ydl_opts = {
                'write_subs': True,
                'write_auto_subs': True,
                'sub_lang': 'en',
                'skip_download': True,
                'outtmpl': os.path.join(DOWNLOADS_DIR, f"{job_id}_subs.%(ext)s"),
                'quiet': True,
                'no_warnings': True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([f"https://youtube.com/watch?v={video_id}"])

            if os.path.exists(subtitle_path):
                keywords = [word for word in scene_data["scene_description"].split() if len(word) > 4]
                timestamps = find_timestamp(subtitle_path, keywords)
                if timestamps:
                    scene_data["start_time"], scene_data["end_time"] = timestamps
                    print(f"Found exact timestamp in subtitles: {timestamps[0]} -> {timestamps[1]}")

        except Exception as e:
            print(f"Subtitle download or parsing failed: {e}")

        video_url = f"https://youtube.com/watch?v={video_id}"
        download_path = await download_video(video_url, job_id)

        if download_path and os.path.exists(download_path):
            return download_path


    # Try with film title and year
    film_title = scene_data.get("film", "")
    year = scene_data.get("year", "")
    if film_title and year:
        title_year_formats = [
            f"ytsearch5:{film_title} {year} {query}",
            f"ytsearch5:{film_title} {year} scene",
            f"ytsearch5:{film_title} {year} movie clip"
        ]

        for yt_format in title_year_formats:
            try:
                video_info = await search_youtube(yt_format)
                if video_info:
                    video_url = f"https://youtube.com/watch?v={video_info['id']}"
                    download_path = await download_video(video_url, job_id)

                    if download_path and os.path.exists(download_path):
                        return download_path
            except Exception:
                continue
        
        # Try with film title and year
        film_title = scene_data.get("film", "")
        year = scene_data.get("year", "")
        if film_title and year:
            title_year_formats = [
                f"ytsearch5:{film_title} {year} {query}",
                f"ytsearch5:{film_title} {year} scene",
                f"ytsearch5:{film_title} {year} movie clip"
            ]
            
            for yt_format in title_year_formats:
                try:
                    video_info = await search_youtube(yt_format)
                    if video_info:
                        video_url = f"https://youtube.com/watch?v={video_info['id']}"
                        download_path = await download_video(video_url, job_id)
                        
                        if download_path and os.path.exists(download_path):
                            return download_path
                except Exception:
                    continue
    
    # If all downloads failed, return links
    scene_description = scene_data.get("scene_description", "")
    film_title = scene_data.get("film", "")
    year = scene_data.get("year", "")
    
    urls = []
    for query in search_queries:
        urls.append(f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}")
        urls.append(f"https://www.youtube.com/results?search_query={urllib.parse.quote(f'{query} scene HD')}")
        urls.append(f"https://www.youtube.com/results?search_query={urllib.parse.quote(f'{film_title} {year} {query}')}")
    
    urls.append(f"https://www.playphrase.me/#/search?q={urllib.parse.quote(scene_description)}")
    urls.append(f"https://clip.cafe/search/?q={urllib.parse.quote(scene_description)}")
    
    return {
        "type": "links",
        "urls": urls,
        "message": "Не смог скачать видео автоматически. Вот ссылки для ручного поиска:"
    }


async def search_youtube(query: str) -> Optional[dict]:
    """
    Search YouTube and return video info for the first result.
    """
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True,
        'skip_download': True,
        'playlist_items': '5',  # Get 5 results to increase chances
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(query, download=False)
            
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
        'format': 'best[height<=720]/best[height<=480]/best',
        'outtmpl': output_template,
        'merge_output_format': 'mp4',
        'no_playlist': True,
        'no_warnings': True,
        'max_filesize': 500 * 1024 * 1024,  # 500MB limit
        'quiet': True,
        'add_headers': [
            'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language: en-US,en;q=0.9'
        ],
        'extractor-retries': 3,
        'fragment-retries': 3,
        'retry-sleep': 3,
        'no-check-certificates': True,
        'geo-bypass': True,
        'age-limit': 18
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
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
                print(f"YT-DLP ERROR: {str(e)}", flush=True)
                return None
    except Exception:
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