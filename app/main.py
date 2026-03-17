import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from aiogram import Dispatcher
from aiogram.types import BotCommand

from .bot import bot, dp
from .config import TELEGRAM_BOT_TOKEN

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


@app.get("/")
async def root():
    """Root endpoint."""
    return {"status": "ok", "service": "clip-agent-bot"}


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)