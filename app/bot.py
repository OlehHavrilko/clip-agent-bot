import asyncio
import logging
from typing import Dict, Any
from uuid import uuid4
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
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
    awaiting_action = State()


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
        scene_data["start_time"] = start_time
        scene_data["end_time"] = end_time

        # Store scene_data in FSM state
        await state.update_data(scene_data=scene_data)

        # Format response
        film = scene_data.get("film", "Неизвестный фильм")
        year = scene_data.get("year", "")
        scene_desc = scene_data.get("scene_description", "Описание недоступно")
        confidence = scene_data.get("confidence", "unknown")

        if year:
            film_info = f"{film} ({year})"
        else:
            film_info = film

        response_text = (
            f"🎬 Нашёл:\n"
            f"Фильм: {film_info}\n"
            f"Сцена: {scene_desc}\n"
            f"Таймкод: {start_time} → {end_time}\n"
            f"Уверенность: {confidence}\n\n"
            f"Что будем делать дальше?"
        )

        # Create inline keyboard
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="⬇️ Скачать клип", callback_data="download_clip"),
                InlineKeyboardButton(text="🔗 Только ссылки", callback_data="send_links"),
            ]
        ])

        await message.answer(response_text, reply_markup=keyboard)
        await state.set_state(SceneStates.awaiting_action)

    except ValueError as e:
        # Agent failed
        await message.answer("❌ Не смог определить сцену. Попробуй описать точнее.")
        await state.set_state(SceneStates.waiting_for_scene)

    except TelegramAPIError as e:
        logger.error(f"Telegram API error: {e}")
        await message.answer("❌ Ошибка при отправке сообщения. Попробуй ещё раз.")
        await state.set_state(SceneStates.waiting_for_scene)

    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        await message.answer("❌ Произошла ошибка. Попробуй ещё раз.")
        await state.set_state(SceneStates.waiting_for_scene)


@dp.callback_query(SceneStates.awaiting_action, F.data == "download_clip")
async def handle_download_clip(callback_query: CallbackQuery, state: FSMContext):
    await callback_query.answer("Начинаю скачивание клипа...")
    await callback_query.message.edit_reply_markup(reply_markup=None)  # Remove buttons

    data = await state.get_data()
    scene_data = data.get("scene_data")

    if not scene_data:
        await callback_query.message.answer("❌ Произошла ошибка: данные сцены не найдены.")
        await state.set_state(SceneStates.waiting_for_scene)
        return

    job_id = uuid4().hex[:8]
    start_time = scene_data["start_time"]
    end_time = scene_data["end_time"]

    try:
        await callback_query.message.answer("📥 Ищу и скачиваю видео...")
        result = await search_and_download(scene_data, job_id)

        if isinstance(result, dict) and result.get("type") == "links":
            await _send_links_message(callback_query.message, result, job_id, state)
            return

        await callback_query.message.answer("✂️ Вырезаю клип...")
        clip_path = await cut_clip(result, start_time, end_time, job_id)

        file_size = get_file_size_mb(clip_path)
        if file_size > 50:
            await callback_query.message.answer(
                "❌ Файл слишком большой для Telegram (>50mb). "
                "Попробуй запросить более короткий отрывок."
            )
            cleanup(job_id)
            await state.set_state(SceneStates.waiting_for_scene)
            return

        video = FSInputFile(clip_path)
        film = scene_data.get("film", "Неизвестный фильм")
        year = scene_data.get("year", "")
        scene_desc = scene_data.get("scene_description", "Описание недоступно")
        film_info = f"{film} ({year})" if year else film
        caption = f"{film_info}\n{scene_desc}"

        try:
            await bot.send_video(
                chat_id=callback_query.message.chat.id,
                video=video,
                caption=caption,
                supports_streaming=True
            )
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.timeout)
            await bot.send_video(
                chat_id=callback_query.message.chat.id,
                video=video,
                caption=caption,
                supports_streaming=True
            )

        cleanup(job_id)
        await state.set_state(SceneStates.waiting_for_scene)
        await callback_query.message.answer("✅ Готово! Можешь описать ещё одну сцену.")

    except RuntimeError as e:
        error_msg = "❌ Ошибка при обработке видео." if "Video not found" not in str(e) else "❌ Не нашёл видео на YouTube. Попробуй другой запрос."
        await callback_query.message.answer(error_msg)
        cleanup(job_id)
        await state.set_state(SceneStates.waiting_for_scene)
    except Exception as e:
        logger.error(f"Unexpected error during download_clip: {e}")
        await callback_query.message.answer("❌ Произошла ошибка при скачивании клипа. Попробуй ещё раз.")
        cleanup(job_id)
        await state.set_state(SceneStates.waiting_for_scene)


@dp.callback_query(SceneStates.awaiting_action, F.data == "send_links")
async def handle_send_links(callback_query: CallbackQuery, state: FSMContext):
    await callback_query.answer("Отправляю ссылки...")
    await callback_query.message.edit_reply_markup(reply_markup=None)  # Remove buttons

    data = await state.get_data()
    scene_data = data.get("scene_data")

    if not scene_data:
        await callback_query.message.answer("❌ Произошла ошибка: данные сцены не найдены.")
        await state.set_state(SceneStates.waiting_for_scene)
        return

    # Generate job ID for cleanup, even if no download happens
    job_id = uuid4().hex[:8]

    # Generate links (similar logic as in search_and_download if it fails)
    search_queries = scene_data.get("search_queries", [])
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

    links_result = {
        "type": "links",
        "urls": urls,
        "message": "Вот ссылки для ручного поиска:"
    }

    await _send_links_message(callback_query.message, links_result, job_id, state)
    await state.set_state(SceneStates.waiting_for_scene)


async def _send_links_message(message: Message, result: Dict[str, Any], job_id: str, state: FSMContext):
    """Helper function to send formatted links message."""
    message_text = result.get("message", "Не смог скачать видео автоматически.")
    data = await state.get_data()
    scene_data = data.get("scene_data", {})
    film = scene_data.get("film", "Неизвестный фильм")
    year = scene_data.get("year", "")
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
    cleanup(job_id)  # Clean up any potential subtitle files
    await state.set_state(SceneStates.waiting_for_scene)


@dp.message(SceneStates.processing)
async def ignore_during_processing(message: Message):
    """Ignore messages while processing."""
    await message.answer("⏳ Сейчас обрабатываю предыдущий запрос. Пожалуйста, подождите.")


@dp.message(SceneStates.awaiting_action)
async def ignore_during_awaiting_action(message: Message):
    """Ignore messages while awaiting action from inline buttons."""
    await message.answer("Пожалуйста, выберите действие на кнопках.")


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
