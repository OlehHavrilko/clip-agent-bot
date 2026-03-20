import asyncio
import logging
import uuid
import os
import urllib.parse
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from aiogram import Dispatcher
from aiogram.types import BotCommand

from .bot import bot, dp
from .config import TELEGRAM_BOT_TOKEN, DOWNLOADS_DIR
from .agent import analyze_prompt, generate_tiktok_caption
from .searcher import search_and_download
from .cutter import cut_clip, crop_vertical, cleanup

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    FastAPI lifespan manager.
    Starts aiogram polling in background task.
    """
    # Setup bot commands
    await setup_bot_commands()
    
    # Start bot polling in background
    asyncio.create_task(dp.start_polling(bot))
    logger.info("Bot started polling")
    
    yield
    
    # Cleanup on shutdown
    await dp.stop_polling()
    await bot.session.close()
    logger.info("Bot stopped polling")


async def setup_bot_commands():
    """Setup bot commands."""
    commands = [
        BotCommand(command="/start", description="Начать работу с ботом"),
        BotCommand(command="/cancel", description="Отменить текущую операцию"),
    ]
    await bot.set_my_commands(commands)


# Create FastAPI app with lifespan
app = FastAPI(
    title="ClipAgent Bot API",
    description="Telegram bot for finding and cutting movie scenes",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory job storage: job_id -> dict with scene_data and file_path
jobs: Dict[str, Dict[str, Any]] = {}


@app.get("/")
async def root():
    """Root endpoint."""
    return {"status": "ok", "service": "clip-agent-bot"}


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.post("/api/search")
async def api_search(body: Dict[str, Any]):
    """
    Search for a movie scene based on user prompt.
    
    Body: {"prompt": "string"}
    Returns scene data with job_id for later operations.
    """
    prompt = body.get("prompt")
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt is required")
    
    try:
        # Analyze prompt to extract scene information
        scene_data = analyze_prompt(prompt)
        
        # Generate job_id
        job_id = uuid.uuid4().hex[:8]
        
        # Store in jobs dictionary
        jobs[job_id] = {
            "scene_data": scene_data,
            "status": "ready"
        }
        
        # Return response with scene data
        return {
            "job_id": job_id,
            "film": scene_data.get("film", ""),
            "year": scene_data.get("year", ""),
            "scene_description": scene_data.get("scene_description", ""),
            "timestamp_start": scene_data.get("timestamp_start", "00:00:00"),
            "timestamp_end": scene_data.get("timestamp_end", "00:01:00"),
            "confidence": scene_data.get("confidence", "medium")
        }
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to analyze prompt: {str(e)}")


@app.post("/api/download")
async def api_download(body: Dict[str, Any]):
    """
    Download and process video clip with SSE progress updates.
    
    Body: {"job_id": "abc123", "mode": "vertical" | "horizontal"}
    Returns StreamingResponse with Server-Sent Events.
    """
    job_id = body.get("job_id")
    mode = body.get("mode", "horizontal")
    
    if not job_id:
        raise HTTPException(status_code=400, detail="job_id is required")
    
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if mode not in ["vertical", "horizontal"]:
        raise HTTPException(status_code=400, detail="mode must be 'vertical' or 'horizontal'")
    
    async def event_generator():
        try:
            scene_data = jobs[job_id]["scene_data"]
            
            # Emit searching status
            yield f"data: {{\"status\": \"searching\", \"message\": \"Ищу видео...\"}}\n\n"
            await asyncio.sleep(0.1)
            
            # Search and download video
            result = await search_and_download(scene_data, job_id)
            
            # Check if result is a dict (links) or a file path
            if isinstance(result, dict) and result.get("type") == "links":
                yield f"data: {{\"status\": \"error\", \"message\": \"Не удалось скачать видео автоматически. Используйте ссылки для ручного поиска.\"}}\n\n"
                return
            
            video_path = result
            
            # Emit downloading status
            yield f"data: {{\"status\": \"downloading\", \"message\": \"Скачиваю...\"}}\n\n"
            await asyncio.sleep(0.1)
            
            # Get timestamps from scene_data
            start_time = scene_data.get("timestamp_start", "00:00:00")
            end_time = scene_data.get("timestamp_end", "00:01:00")
            
            # Emit cutting status
            yield f"data: {{\"status\": \"cutting\", \"message\": \"Вырезаю клип...\"}}\n\n"
            await asyncio.sleep(0.1)
            
            # Cut the clip
            clip_path = await cut_clip(video_path, start_time, end_time, job_id)
            
            # Emit processing status
            yield f"data: {{\"status\": \"processing\", \"message\": \"Обрабатываю...\"}}\n\n"
            await asyncio.sleep(0.1)
            
            # Apply vertical crop if mode is vertical
            if mode == "vertical":
                final_path = await crop_vertical(clip_path, job_id)
            else:
                final_path = clip_path
            
            # Store final file path in jobs
            jobs[job_id]["file_path"] = final_path
            
            # Emit done status with file URL
            yield f"data: {{\"status\": \"done\", \"file_url\": \"/api/file/{job_id}\"}}\n\n"
            
        except Exception as e:
            error_message = str(e).replace('"', '\\"').replace('\n', '\\n')
            yield f"data: {{\"status\": \"error\", \"message\": \"{error_message}\"}}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.get("/api/file/{job_id}")
async def api_file(job_id: str):
    """
    Download the processed video file.
    
    Returns FileResponse with video/mp4 content type.
    """
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    file_path = jobs[job_id].get("file_path")
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(
        path=file_path,
        media_type="video/mp4",
        filename=f"{job_id}_clip.mp4"
    )


@app.get("/api/links/{job_id}")
async def api_links(job_id: str):
    """
    Get search links for manual video finding.
    
    Returns YouTube, PlayPhrase, and ClipCafe search URLs.
    """
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    scene_data = jobs[job_id].get("scene_data", {})
    search_queries = scene_data.get("search_queries", [])
    scene_description = scene_data.get("scene_description", "")
    film_title = scene_data.get("film", "")
    year = scene_data.get("year", "")
    
    youtube_links = []
    for query in search_queries[:2]:  # Limit to first 2 queries
        youtube_links.append(
            f"https://youtube.com/results?search_query={urllib.parse.quote(query)}"
        )
        youtube_links.append(
            f"https://youtube.com/results?search_query={urllib.parse.quote(f'{query} scene HD')}"
        )
    
    return {
        "youtube": youtube_links,
        "playphrase": f"https://playphrase.me/#/search?q={urllib.parse.quote(scene_description)}",
        "clipcafe": f"https://clip.cafe/search/?q={urllib.parse.quote(scene_description)}"
    }


@app.post("/api/caption")
async def api_caption(body: Dict[str, Any]):
    """
    Generate TikTok caption for the scene.
    
    Body: {"job_id": "abc123"}
    Returns caption text with hashtags.
    """
    job_id = body.get("job_id")
    if not job_id:
        raise HTTPException(status_code=400, detail="job_id is required")
    
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    scene_data = jobs[job_id].get("scene_data", {})
    
    try:
        caption = await generate_tiktok_caption(scene_data)
        return {"caption": caption}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate caption: {str(e)}")


@app.delete("/api/job/{job_id}")
async def api_delete_job(job_id: str):
    """
    Delete a job and cleanup associated files.
    
    Returns {"ok": true} on success.
    """
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Cleanup files
    try:
        cleanup(job_id)
    except Exception as e:
        print(f"Cleanup warning for job {job_id}: {e}")
    
    # Remove from jobs dictionary
    del jobs[job_id]
    
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)