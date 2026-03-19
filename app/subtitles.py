
import datetime

def find_timestamp(srt_path: str, keywords: list[str]) -> tuple[str, str] | None:
    """
    Parses an .srt file and searches for lines containing any of the keywords.
    Returns (start_time, end_time) with a 30-second buffer on each side,
    or None if no match is found.
    """
    def parse_time(time_str):
        h, m, s_ms = time_str.split(":")
        s, ms = s_ms.split(',')
        return datetime.timedelta(hours=int(h), minutes=int(m), seconds=int(s), milliseconds=int(ms))

    def format_time(td: datetime.timedelta) -> str:
        total_seconds = int(td.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02}:{minutes:02}:{seconds:02}"

    keywords_lower = [k.lower() for k in keywords]
    buffer = datetime.timedelta(seconds=30)

    with open(srt_path, "r", encoding="utf-8") as f:
        content = f.read()

    blocks = content.strip().split("\n\n")

    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue

        try:
            # Ignore the first line (subtitle number)
            time_str = lines[1]
            text_lines = lines[2:]
        except IndexError:
            continue

        start_time_str, end_time_str = time_str.split(" --> ")
        start_time = parse_time(start_time_str)
        end_time = parse_time(end_time_str)

        full_text = " ".join(text_lines).lower()

        for keyword in keywords_lower:
            if keyword in full_text:
                buffered_start = max(datetime.timedelta(0), start_time - buffer)
                buffered_end = end_time + buffer
                return format_time(buffered_start), format_time(buffered_end)

    return None


import httpx
import logging
from .config import GROQ_API_KEY, DOWNLOADS_DIR

logger = logging.getLogger(__name__)


async def add_subtitles_groq(video_path: str, job_id: str) -> str:
    """
    Transcribes the video using Groq Whisper and burns the subtitles into the video.
    Returns the path to the subtitled video or the original video path if transcription fails.
    """
    srt_path = os.path.join(DOWNLOADS_DIR, f"{job_id}.srt")
    output_path = os.path.join(DOWNLOADS_DIR, f"{job_id}_subtitled.mp4")

    # Step 1 & 2: Transcribe with Groq Whisper and save as .srt
    try:
        async with httpx.AsyncClient() as client:
            with open(video_path, "rb") as f:
                files = {"file": (os.path.basename(video_path), f, "video/mp4")}
                data = {
                    "model": "whisper-large-v3-turbo",
                    "response_format": "srt",
                    "language": "en"
                }
                headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
                response = await client.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    headers=headers,
                    files=files,
                    data=data,
                    timeout=300.0  # 5 minutes timeout for transcription
                )
            response.raise_for_status()

            with open(srt_path, "w", encoding="utf-8") as srt_file:
                srt_file.write(response.text)

    except httpx.HTTPStatusError as e:
        logger.warning(f"Groq transcription failed with HTTP error: {e.response.status_code} - {e.response.text}")
        return video_path
    except httpx.RequestError as e:
        logger.warning(f"Groq transcription failed with request error: {e}")
        return video_path
    except Exception as e:
        logger.warning(f"Groq transcription failed: {e}")
        return video_path

    # Step 3: Burn subtitles into video with ffmpeg
    cmd = [
        "ffmpeg",
        "-i", video_path,
        "-vf", f"subtitles={srt_path}:force_style='FontName=Arial,FontSize=18,PrimaryColour=&HFFFFFF,OutlineColour=&H000000,Outline=2,Alignment=2,MarginV=30'",
        "-c:v", "libx64",
        "-preset", "fast",
        "-crf", "28",
        "-c:a", "copy",
        "-y", output_path
    ]

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown ffmpeg error"
            logger.warning(f"FFmpeg failed burning subtitles: {error_msg}")
            return video_path

        if not os.path.exists(output_path):
            logger.warning("Subtitled video output file was not created")
            return video_path

        return output_path

    except Exception as e:
        logger.warning(f"Failed to burn subtitles into video: {str(e)}")
        return video_path
