# ClipScript AI 🎬→📝

A **production-stable** Telegram bot that transcribes TikTok videos to text using Deepgram API. Fast, reliable, and handles multiple requests safely.

---

## ✨ Features

- **🚀 Ultra-fast**: Transcribes in 5-30 seconds (Deepgram <1s response)
- **💪 Fault-tolerant**: Bad TikTok link? Bot stays alive & serves next user
- **🔄 Multi-request safe**: Handles multiple users simultaneously without crashing
- **📊 Full logging**: Tracks all requests, errors, and performance metrics
- **🛡️ Error isolation**: Download fails? FFmpeg error? API timeout? User gets friendly message
- **🧹 Auto-cleanup**: Removes temp files automatically, prevents disk buildup

---

## How It Works

```
User sends TikTok link
       ↓
Bot downloads video (yt-dlp with anti-blocking)
       ↓
Extract audio (FFmpeg)
       ↓
Transcribe (Deepgram API - $0.0043/min)
       ↓
Return text in Telegram
```

**Time**: 5–30 seconds depending on video length

---

## Quick Start

### Prerequisites

- **Python 3.9+** (tested on 3.13)
- **FFmpeg** (for audio extraction)
- **Telegram Bot Token** (@BotFather on Telegram)
- **Deepgram API Key** (https://console.deepgram.com)

### 1. Clone & Setup

```bash
cd "ClipScript AI"
python -m venv .venv
.venv\Scripts\activate  # Windows
# or: source .venv/bin/activate  # macOS/Linux

pip install -r requirements.txt
```

### 2. Install FFmpeg

**Windows (WinGet):**
```bash
winget install Gyan.FFmpeg
# Then set in .env: FFMPEG_PATH=C:\path\to\ffmpeg.exe
```

**macOS:**
```bash
brew install ffmpeg
```

**Linux:**
```bash
sudo apt install ffmpeg
```

### 3. Configure `.env`

```bash
BOT_TOKEN=your_telegram_bot_token
DEEPGRAM_API_KEY=your_deepgram_api_key
FFMPEG_PATH=/path/to/ffmpeg  # Optional: only if not in PATH
```

**Get these:**
- **BOT_TOKEN**: Message @BotFather → `/newbot` → copy token
- **DEEPGRAM_API_KEY**: https://console.deepgram.com → create free account → API keys

### 4. Run

```bash
python app_unified.py
```

Expected output:
```
======================================================================
Starting ClipScript AI - Unified Backend
Transcription Service: deepgram
Flask server started in background
======================================================================
Application started
```

### 5. Test

Send a TikTok link to your bot in Telegram. For example:
```
https://www.tiktok.com/@username/video/1234567890
https://vm.tiktok.com/abc123xyz
```

Bot responds with transcript in seconds.

---

## Deployment

### Local Deployment

```bash
# Keep running
python app_unified.py

# To stop: Ctrl+C or
taskkill /F /IM python.exe
```

### Render Deployment (Free)

See [RENDER_DEPLOY.md](RENDER_DEPLOY.md) for step-by-step guide.

---

## Current Performance & Reliability

| Metric | Status |
|--------|--------|
| Multi-request safety | ✅ Semaphore-locked (1 req at a time) |
| Error isolation | ✅ All errors caught, bot stays alive |
| Temp file cleanup | ✅ Auto-cleanup, prevents disk buildup |
| Logging | ✅ File + console, all errors tracked |
| FFmpeg detection | ✅ 3-tier: env → local → system PATH |
| TikTok blocking | ✅ User-agent rotation + exponential backoff |
| Deepgram API | ✅ Timeout: 60s, file limit: 25MB |

---

## Architecture

### Request Handling

```python
# Each request is isolated with asyncio.Semaphore
async with request_semaphore:  # Max 1 concurrent request
    download_video(url)
    extract_audio(video)
    transcribe(audio)
    send_result()
    cleanup()  # Always runs, even on error
```

### Error Handling Strategy

- **Download fails?** → Return False, bot sends user-friendly error, stays live
- **FFmpeg error?** → Caught, logged, user notified
- **API timeout?** → 60s timeout prevents hanging
- **Multiple instances?** → 409 Conflict detected, logged, handled gracefully
- **Unhandled exception?** → Logged with full traceback, request completes safely

### Logging

All activity logged to `logs/clipscript_bot.log`:
```
[request_id] New request started
[request_id] Starting download...
[request_id] Download success
[request_id] Audio extraction...
[request_id] Transcription success: 450 chars
[request_id] Request completed
```

View logs in real-time:
```bash
python view_logs.py
# or
tail -f logs/clipscript_bot.log
```

---

## Troubleshooting

### "409 Conflict" Error

Multiple bot instances running. Fix:
```bash
taskkill /F /IM python.exe
python main.py
```

### "FFmpeg not found"

FFmpeg not in PATH. Fix:
1. Download FFmpeg from https://ffmpeg.org/download.html
2. Add to `.env`:
   ```
   FFMPEG_PATH=C:\path\to\ffmpeg.exe
   ```

### Bot doesn't respond to TikTok links

- Check `.env` has valid `BOT_TOKEN` and `DEEPGRAM_API_KEY`
- Verify Deepgram account has active credits
- Check logs: `python view_logs.py`

### TikTok download fails repeatedly

TikTok is rate-limiting. Bot will:
- Retry with user-agent rotation
- Wait 30-50 seconds between attempts
- Inform user after 3 failed attempts

---

## Dependencies

```
python-telegram-bot==22.7    # Telegram API
yt-dlp==2026.3.17           # TikTok download (auto-updates)
requests>=2.32.2             # HTTP calls
python-dotenv==1.0.0         # .env file parsing
FFmpeg 8.1+                  # Audio extraction (system)
Deepgram API                 # Transcription
```

---

## License & Contributing

MIT License - feel free to modify and deploy!

**Quick summary:**
1. Push repo to GitHub (with render.yaml)
2. Go to https://dashboard.render.com
3. New → Web Service
4. Connect repo
5. Add BOT_TOKEN and OPENAI_API_KEY as environment variables
6. Deploy

---

## Project Structure

```
clipscript-ai/
├── main.py              # Main bot code
├── requirements.txt     # Python dependencies
├── .env.example         # Environment variables template
├── render.yaml          # Render deployment config
├── setup.sh             # Local setup automation
├── RENDER_DEPLOY.md     # Detailed deployment guide
├── README.md            # This file
└── temp/                # Temporary files (gitignored)
```

---

## How It Works

### Flow

```
TikTok Link
    ↓
validate URL
    ↓
download video (yt-dlp)
    ↓
extract audio (FFmpeg)
    ↓
transcribe (OpenAI Whisper)
    ↓
send result to Telegram
    ↓
cleanup temp files
```

### Key Features

- ✅ URL validation (catches invalid links early)
- ✅ Retry logic (handles TikTok blocking)
- ✅ Error messages (user-friendly, not scary)
- ✅ Logging (all actions tracked)
- ✅ File cleanup (no junk left behind)
- ✅ Chunk splitting (handles long transcripts)
- ✅ Status updates (shows progress)

---

## Costs

### OpenAI Whisper API
~$0.006 per minute of audio

**Examples:**
- 100 videos/month × 1 min avg = $18/month
- 500 videos/month × 1.5 min avg = $45/month

### Hosting (Render)
- Free tier: Works, but service sleeps after 15 min inactivity
- Paid ($7/month): Always on

---

## Troubleshooting

### "ffmpeg: command not found"
Install FFmpeg for your OS (see Setup section above)

### "OpenAI API key invalid"
Check key hasn't expired → regenerate at https://platform.openai.com/account/api-keys

### "TikTok blocked the request"
Normal. TikTok sometimes blocks yt-dlp. Bot retries automatically.
If persistent: wait 5 min and try again

### "Request took too long"
Video too long or slow network. Bot will timeout after 2 min.

### "Telegram bot not responding"
- Verify BOT_TOKEN is correct (check @BotFather)
- Make sure main.py is running (check console)
- Check internet connection

### Long transcripts are cut off
Telegram has 4096 character limit. Bot automatically splits into chunks.

---

## Advanced: Customization

### Add language support
In `main.py`, line ~167, change:
```python
language="en"  # Change to "es", "fr", "zh", etc.
```

### Increase timeout
In `main.py`, line ~92 and ~109:
```python
timeout=120  # Change to 180 for slower networks
```

### Add user rate limiting
In `main.py`, add to `handle_message()`:
```python
user_id = update.message.from_user.id
if user_id in rate_limit and time.time() - rate_limit[user_id] < 60:
    await update.message.reply_text("Please wait 60 seconds")
    return
rate_limit[user_id] = time.time()
```

---

## Next Steps (Post-MVP)

- [ ] Add summary button ("Summarize this")
- [ ] Add user credits system
- [ ] Add database to track history
- [ ] Monetize with tiered plans
- [ ] Add Instagram Reels support
- [ ] Add YouTube Shorts support
- [ ] Create admin dashboard

---

## License

MIT (free to use, modify, deploy)

---

## Support

Issues? Questions?

1. Check Troubleshooting section
2. Check bot logs (if local: console; if Render: dashboard)
3. Open GitHub issue

---

Made with ❤️ for content creators and researchers
