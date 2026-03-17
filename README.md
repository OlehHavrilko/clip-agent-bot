# ClipAgent - Telegram Movie Scene Bot

A production-ready Telegram bot that accepts natural language descriptions of movie scenes, finds them on YouTube, cuts the clip, and sends it back to the user.

## Features

- **Natural Language Processing**: Uses Google Gemini API to understand scene descriptions in any language
- **YouTube Integration**: Automatically searches and downloads videos using yt-dlp
- **Smart Video Cutting**: Uses ffmpeg to extract precise clips with configurable buffers
- **Telegram Bot Interface**: Full aiogram 3 implementation with FSM state management
- **Production Ready**: Docker containerization with Render.com deployment
- **Error Handling**: Comprehensive error handling and cleanup on failures

## Project Structure

```
clip-agent-bot/
├── Dockerfile
├── render.yaml
├── requirements.txt
├── .env.example
├── app/
│   ├── main.py          # FastAPI app + aiogram startup
│   ├── bot.py           # aiogram handlers with FSM
│   ├── agent.py         # Gemini AI logic
│   ├── searcher.py      # yt-dlp video search and download
│   ├── cutter.py        # ffmpeg video cutting
│   ├── config.py        # Environment configuration
│   └── utils.py         # Helper functions
└── downloads/           # Temporary storage (auto-created)
```

## Requirements

- Python 3.11
- Google Gemini API key
- Telegram Bot Token
- Docker (for deployment)

## Installation

1. Clone the repository:
```bash
git clone <your-repo-url>
cd clip-agent-bot
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your actual keys
```

## Configuration

Create a `.env` file with the following variables:

```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
GEMINI_API_KEY=your_gemini_api_key_here
# Optional:
MAX_CLIP_DURATION=300  # Maximum clip duration in seconds (5 minutes)
DOWNLOADS_DIR=downloads  # Temporary storage directory
```

## Usage

### Local Development

1. Set up your environment variables in `.env`
2. Run the application:
```bash
python -m app.main
```

3. Start the bot in Telegram and use commands:
   - `/start` - Begin interaction
   - `/cancel` - Cancel current operation

### Example Conversation

```
User: сцена из матрицы где нео выбирает таблетку
Bot: ⏳ Анализирую сцену...
Bot: 🎬 Нашёл:
     Фильм: The Matrix (1999)
     Сцена: Morpheus offers Neo red and blue pill choice
     Таймкод: 00:28:00 → 00:31:30
     Уверенность: high
     Начинаю поиск и скачивание...
Bot: ✂️ Вырезаю клип...
Bot: [video file]
Bot: ✅ Готово! Можешь описать ещё одну сцену.
```

## Deployment

### Using Render.com

1. Push your project to GitHub
2. Go to [render.com](https://render.com) → New → Web Service → Connect repo
3. Runtime: Docker
4. Add environment variables:
   - `TELEGRAM_BOT_TOKEN`
   - `GEMINI_API_KEY`
5. Deploy

### Preventing Free Tier Sleep

To prevent the free tier from sleeping:

1. Register on [UptimeRobot](https://uptimerobot.com)
2. Add monitor: GET `https://your-render-url.onrender.com/health`
3. Set interval to 5 minutes

## API Endpoints

- `GET /` - Root endpoint (status check)
- `GET /health` - Health check endpoint (for uptime monitoring)

## Technical Details

### Architecture

- **Backend**: FastAPI with async support
- **Bot Framework**: aiogram 3 with FSM
- **AI Processing**: Google Gemini API (gemini-2.0-flash)
- **Video Processing**: ffmpeg with optimized settings
- **Download Manager**: yt-dlp with quality constraints

### Key Features

- **Async Processing**: All operations are non-blocking
- **State Management**: FSM prevents concurrent operations
- **File Management**: Automatic cleanup of temporary files
- **Error Recovery**: Graceful handling of failures with cleanup
- **Size Validation**: 50MB limit enforcement for Telegram compatibility

### Timestamp Handling

- Adds 30-second buffer to timestamps by default
- Widens timestamp range by 2 minutes each side for low confidence
- Validates duration against maximum clip duration

### Video Quality Settings

- Maximum resolution: 720p
- Format: MP4 with H.264 video and AAC audio
- CRF: 28 (good quality/size balance)
- Fast preset for quick processing

## Troubleshooting

### Common Issues

1. **Gemini API Errors**: Check your API key and quota
2. **YouTube Download Failures**: May be due to geo-blocking or video restrictions
3. **FFmpeg Errors**: Ensure ffmpeg is properly installed
4. **Telegram Flood Limits**: Bot includes automatic retry logic

### Logs

Check application logs for detailed error information:
```bash
# For Docker containers
docker logs <container_id>

# For Render.com
Check the service logs in your Render dashboard
```

## Development

### Adding New Features

1. Follow the existing modular structure
2. Add new functionality to appropriate modules
3. Update error handling and cleanup
4. Test thoroughly with various inputs

### Testing

The application includes comprehensive error handling. To test:

1. Use different scene descriptions
2. Test with various languages
3. Verify file size limits
4. Check cleanup functionality

## Security

- Environment variables for all sensitive data
- Input validation and sanitization
- Proper file cleanup to prevent disk space issues
- Rate limiting protection against Telegram flood limits

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is open source and available under the [MIT License](LICENSE).

## Support

For issues and questions:
1. Check the troubleshooting section
2. Review the logs
3. Open an issue on GitHub