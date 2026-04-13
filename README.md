# ClipScript AI 🎬→📝

A **production-stable** Telegram bot that transcribes TikTok videos to text using the Deepgram API. Fast, reliable, and handles multiple requests safely.

---

## ✨ Features

- **🚀 Ultra-fast**: Transcribes in 5-30 seconds
- **💪 Fault-tolerant**: Bad links? Bot stays alive & serves next user
- **🔄 Multi-request safe**: Handles multiple users simultaneously
- **📊 Full logging**: Tracks all requests, errors, and performance
- **🛡️ Error isolation**: Graceful error handling with friendly messages
- **🔐 Persistence**: SQLite database for job tracking & history
- **📲 Dashboard**: Telegram commands (`/status`, `/history`, `/help`)

---

## Project Structure

```
ClipScript-AI-bot/
├── backend/              # Python Flask + Telegram backend
│   ├── app_unified.py    # Main app (Flask + Telegram bot)
│   ├── db.py             # SQLite database layer
│   ├── requirements.txt   # Python dependencies
│   ├── jobs.db           # SQLite database file
│   ├── .env              # Credentials (gitignored)
│   ├── .env.example      # Example environment
│   └── verify_stability.py
│
├── frontend/             # Web interface
│   └── index.html        # Web UI
│
├── requirements.txt      # Root-level dependencies (mirrors backend)
├── README.md             # This file
└── render.yaml           # Render deployment config
```

---

## Quick Start

### Prerequisites

- **Python 3.9+** (tested on 3.13)
- **FFmpeg** (for audio extraction)
- **Telegram Bot Token** (from @BotFather)
- **Deepgram API Key** (from https://console.deepgram.com)

### 1. Clone & Setup

```bash
git clone https://github.com/Daniel-pong/ClipScript-AI-bot
cd ClipScript-AI-bot
python -m venv .venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Mac/Linux
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment

```bash
cp backend/.env.example backend/.env
```

Edit `backend/.env`:
```env
BOT_TOKEN=your_telegram_bot_token_here
DEEPGRAM_API_KEY=your_deepgram_api_key_here
```

### 4. Run Locally

**Development Mode** (with Telegram polling):
```bash
cd backend
python app_unified.py
```

App will:
- Start Flask on `http://127.0.0.1:5000` (or PORT env var)
- Start Telegram polling in background
- Create `jobs.db` for persistence
- Create `logs/` for detailed logging

---

## How It Works

```
User sends TikTok link to bot
         ↓
Bot downloads video (yt-dlp with anti-blocking)
         ↓
Extract audio with FFmpeg
         ↓
Transcribe with Deepgram API (<1 second response)
         ↓
Return transcript in Telegram (+ save to database)
```

**Time**: 5–30 seconds depending on video length

---

## Telegram Commands

- `/start` - Welcome + instructions
- `/status` - Show latest job status
- `/history` - Show last 5 transcription jobs
- `/help` - Show usage guide

---

## Deployment

### Option 1: Render (Recommended)

1. Push code to GitHub
2. Create Render Web Service
3. Set Root Directory: `/backend`
4. Set Start Command: `python app_unified.py`
5. Add Environment Variables:
   - `BOT_TOKEN`
   - `DEEPGRAM_API_KEY`
   - `WEBHOOK_URL=https://<your-render-domain>/telegram/webhook`
6. Deploy!

### Option 2: Railway

Similar to Render, set Root Directory to `/backend`.

### Option 3: Local Testing

Already running from "Quick Start" section above.

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `BOT_TOKEN` | ✅ | Telegram bot token from @BotFather |
| `DEEPGRAM_API_KEY` | ✅ | API key from console.deepgram.com |
| `PORT` | ❌ | Server port (default: 5000) |
| `WEBHOOK_URL` | ❌ | Telegram webhook URL (production only) |
| `TRANSCRIPTION_SERVICE` | ❌ | Service choice (default: deepgram) |

---

## Logging

Logs are stored in `backend/logs/clipscript_unified.log`:

```bash
tail -f backend/logs/clipscript_unified.log
```

---

## Troubleshooting

### Bot not responding
- Check `BOT_TOKEN` is correct in `.env`
- Check logs: `backend/logs/clipscript_unified.log`
- Development mode: Uses polling (no webhook needed)
- Production mode: webhook URL must be HTTPS and public

### Transcription failing
- Check `DEEPGRAM_API_KEY` is valid
- Check internet connection
- Check logs for error details

### Port already in use
- Change port: `PORT=8000 python app_unified.py`

### Permission denied (FFmpeg)
- Install FFmpeg: `pip install ffmpeg-python`
- Or: System FFmpeg not in PATH → adjust `FFMPEG_PATH` in `.env`

---

## Testing

Run the verification script:

```bash
cd backend
python verify_stability.py
```

Checks:
- ✅ All dependencies installed
- ✅ Environment variables set
- ✅ Database initialized
- ✅ Flask app loads

---

## Tech Stack

- **Python 3.13** - Runtime
- **Flask 3.0** - Web framework
- **python-telegram-bot 22.7** - Telegram integration
- **SQLite3** - Persistence & job tracking
- **Deepgram SDK 3.2** - Speech-to-text
- **yt-dlp** - TikTok video download
- **FFmpeg** - Audio extraction

---

## Architecture

**Unified Service Pattern:**
- Single Python process runs **both** Flask web server + Telegram bot
- Flask: Serves web UI (`/`), REST API (`/api/transcribe`), health check (`/health`)
- Telegram: Polling (dev) or Webhook (production)
- Database: SQLite with job tracking
- Threading: Concurrent Flask + Telegram without blocking

**Deployment Modes:**
- **Development**: Flask + Telegram polling (no internet required for testing)
- **Production**: Flask + Telegram webhook (requires public HTTPS domain)

---

## Performance

- **Transcription**: 5-30 seconds (depends on video length)
- **Deepgram API fee**: ~$0.0043/minute of audio
- **Database**: SQLite (fast local queries, no external DB needed)
- **Logging**: Async, doesn't block request handling

---

## License

[Your License Here]

---

## Support

For issues, feature requests, or questions:
- 📝 Check logs: `backend/logs/clipscript_unified.log`
- 🐛 Open an issue on GitHub
- 📧 Contact via Telegram bot

---

**Made with ❤️ for TikTok transcription**
