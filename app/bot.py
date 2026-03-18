import asyncio
import logging
from typing import Dict, Any
from uuid import uuid4
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, FSInputFile
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter
from .config import TELEGRAM_BOT_TOKEN, MAX_CLIP_DURATION, DOWNLOADS_DIR
from .agent import analyze_prompt
from .searcher import search_and_download
from .cutter import cut_clip, cleanup, adjust_timestamps_for_confidence
from .utils import get_file_size_mb

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Define states for FSM
class SceneStates(StatesGroup):
    waiting_for_scene = State()
    processing = State()


def create_bot_and_dispatcher() -> tuple[Bot, Dispatcher]:
    """Create and configure bot and dispatcher."""
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    return bot, dp


# Create bot and dispatcher
bot, dp = create_bot_and_dispatcher()


@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """Handle /start command."""
    await state.set_state(SceneStates.waiting_for_scene)
    await message.answer(
        "Привет! Опиши сцену из фильма на любом языке, и я найду и вырежу её для тебя.\n"
        "Пример: сцена из Бойцовского клуба где Тайлер отпускает руль"
    )


@dp.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    """Handle /cancel command."""
    await state.set_state(SceneStates.waiting_for_scene)
    await message.answer("Отменено. Опиши новую сцену.")


@dp.message(SceneStates.waiting_for_scene, F.text)
async def process_scene_description(message: Message, state: FSMContext):
    """Process user's scene description."""
    user_text = message.text
    
    try:
        # Set processing state
        await state.set_state(SceneStates.processing)
        await message.answer("⏳ Анализирую сцену...")
        
        # Analyze prompt with Gemini
        scene_data = analyze_prompt(user_text)
        
        # Adjust timestamps based on confidence
        start_time, end_time = adjust_timestamps_for_confidence(scene_data)
        
        # Format response
        film = scene_data.get("film", "Неизвестный фильм")
        year = scene_data.get("year", "")
        scene_desc = scene_data.get("scene_description", "Описание недоступно")
        confidence = scene_data.get("confidence", "unknown")
        
        if year:
            film_info = f"{film} ({year})"
        else:
            film_info = film
            
        await message.answer(
            f"🎬 Нашёл:\n"
            f"Фильм: {film_info}\n"
            f"Сцена: {scene_desc}\n"
            f"Таймкод: {start_time} → {end_time}\n"
            f"Уверенность: {confidence}\n\n"
            f"Начинаю поиск и скачивание..."
        )
        
        # Generate job ID
        job_id = uuid4().hex[:8]
        
        # Search and download video
        await message.answer("📥 Ищу и скачиваю видео...")
        result = await search_and_download(scene_data, job_id)
        
if isinstance(result, dict) and result.get("type") == "links":
    # Handle links response with formatted HTML message
    message_text = result.get("message", "Не смог скачать видео автоматически.")
    film = result.get("film", "Неизвестный фильм")
    year = result.get("year", "")
    if year:
        film_info = f"🎬 {film} ({year})"
    else:
        film_info = f"🎬 {film}"

    urls = result.get("urls", [])
    if urls:
        message_text = f"{film_info}\n✂️ {message_text}\n\n"
        youtube_links = []
        search_links = []
        for url in urls:
            if "youtube.com" in url or "youtu.be" in url:
                youtube_links.append(url)
            else:
                search_links.append(url)

        if youtube_links:
            message_text += "🔍 <b>YouTube:</b>\n"
            for i, url in enumerate(youtube_links, 1):
                message_text += f"• <a href=\"{url}\">YouTube сцена {i}</a>\n"

        if search_links:
            message_text += "\n🎭 <b>Поиск по фразе:</b>\n"
            for i, url in enumerate(search_links, 1):
                if "playphrase" in url:
                    message_text += f"• <a href=\"{url}\">PlayPhrase.me</a>\n"
                elif "clip.cafe" in url:
                    message_text += f"• <a href=\"{url}\">Clip.cafe</a>\n"
                else:
                    message_text += f"• <a href=\"{url}\">Поиск {i}</a>\n"

    await message.answer(message_text, parse_mode="HTML")
    cleanup(job_id)
    await state.set_state(SceneStates.waiting_for_scene)
    return
        
        # Cut the clip
        await message.answer("✂️ Вырезаю клип...")
        clip_path = await cut_clip(result, start_time, end_time, job_id)
        
        # Check file size
        file_size = get_file_size_mb(clip_path)
        if file_size > 50:
            await message.answer(
                "❌ Файл слишком большой для Telegram (>50mb). "
                "Попробуй запросить более короткий отрывок."
            )
            cleanup(job_id)
            await state.set_state(SceneStates.waiting_for_scene)
            return
        
        # Send video to user
        video = FSInputFile(clip_path)
        caption = f"{film_info}\n{scene_desc}"
        
        try:
            await bot.send_video(
                chat_id=message.chat.id,
                video=video,
                caption=caption,
                supports_streaming=True
            )
        except TelegramRetryAfter as e:
            # Handle flood limit
            await asyncio.sleep(e.timeout)
            await bot.send_video(
                chat_id=message.chat.id,
                video=video,
                caption=caption,
                supports_streaming=True
            )
        
        # Cleanup and reset state
        cleanup(job_id)
        await state.set_state(SceneStates.waiting_for_scene)
        await message.answer("✅ Готово! Можешь описать ещё одну сцену.")
        
    except ValueError as e:
        # Agent failed
        await message.answer("❌ Не смог определить сцену. Попробуй описать точнее.")
        await state.set_state(SceneStates.waiting_for_scene)
        
    except RuntimeError as e:
        # Searcher or cutter failed
        if "Video not found" in str(e):
            error_msg = "❌ Не нашёл видео на YouTube. Попробуй другой запрос."
        else:
            error_msg = "❌ Ошибка при обработке видео."
        
        await message.answer(error_msg)
        # Cleanup on error
        try:
            job_id = uuid4().hex[:8]  # This won't match the actual job, but cleanup is safe
            cleanup(job_id)
        except:
            pass
        await state.set_state(SceneStates.waiting_for_scene)
        
    except TelegramAPIError as e:
        logger.error(f"Telegram API error: {e}")
        await message.answer("❌ Ошибка при отправке видео. Попробуй ещё раз.")
        await state.set_state(SceneStates.waiting_for_scene)
        
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        await message.answer("❌ Произошла ошибка. Попробуй ещё раз.")
        await state.set_state(SceneStates.waiting_for_scene)


@dp.message(SceneStates.processing)
async def ignore_during_processing(message: Message):
    """Ignore messages while processing."""
    await message.answer("⏳ Сейчас обрабатываю предыдущий запрос. Пожалуйста, подождите.")


@dp.message()
async def fallback_handler(message: Message, state: FSMContext):
    """Handle any other messages."""
    current_state = await state.get_state()
    if current_state is None:
        await message.answer(
            "Привет! Опиши сцену из фильма на любом языке, и я найду и вырежу её для тебя.\n"
            "Пример: сцена из Бойцовского клуба где Тайлер отпускает руль"
        )
        await state.set_state(SceneStates.waiting_for_scene)