# ClipScript AI - Quick Start Guide

## ✅ Status: Fixed & Running

### What Was Fixed
- **Async Webhook Issue**: The `/telegram/webhook` route was defined as `async def` but Flask routes need to be synchronous. Fixed by wrapping async calls with `asyncio.run()`.
- **Missing Dependencies**: Updated requirements and installed Flask, flask-cors, and deepgram-sdk.

---

## 🚀 How to Run the App

### 1. **Navigate to the app folder** (with quotes for spaces):
```powershell
cd "ClipScript AI"
```

### 2. **Run the unified backend**:
```powershell
python app_unified.py
```

### 3. **You should see**:
```
Starting ClipScript AI - Unified Backend
Transcription Service: deepgram
Unified backend ready for Telegram (webhook) + Web API requests
Running on http://127.0.0.1:5000
```

---

## 📌 Features

### **Telegram Bot**
- Listens for TikTok links in Telegram
- Transcribes video to text using Deepgram API
- Endpoint: `POST /telegram/webhook`

### **Web API**
- Accept TikTok links via HTTP
- Returns transcribed text as JSON
- Endpoint: `POST /api/transcribe`
- Request: `{ "link": "https://www.tiktok.com/..." }`

### **Health Check**
- Endpoint: `GET /health`
- Returns: `{ "status": "ok", "service": "ClipScript AI Unified Backend", "transcription_service": "deepgram" }`

---

## 🔧 Configuration

Environment variables in `.env`:
```
BOT_TOKEN=your_telegram_bot_token
DEEPGRAM_API_KEY=your_deepgram_api_key
FFMPEG_PATH=full/path/to/ffmpeg.exe
TRANSCRIPTION_SERVICE=deepgram  (optional, defaults to deepgram)
WEBHOOK_URL=your_webhook_url    (optional, for Render deployment)
```

---

## 📊 What Happens When You Send a TikTok Link

1. **User sends link** → Telegram or Web API
2. **Validation** → Checks if it's a valid TikTok URL
3. **Download** → yt-dlp downloads the video (with anti-blocking)
4. **Extract Audio** → FFmpeg extracts MP3
5. **Transcribe** → Deepgram API converts to text
6. **Return Result** → Sends transcript back to user/API
7. **Cleanup** → Deletes temporary files

---

## 🐛 Troubleshooting

### **App doesn't start**
- Make sure you're in the `"ClipScript AI"` folder (with quotes)
- Check Python is installed: `python --version`
- Check Flask is installed: `python -m pip list | Select-String flask`

### **Telegram not working**
- Verify `BOT_TOKEN` in `.env` is correct
- For local testing, webhook URL is not needed
- In Telegram, send `/start` then a TikTok link

### **Web API not working**
- Check endpoint: `http://127.0.0.1:5000/api/transcribe`
- Send POST request with JSON: `{ "link": "your_tiktok_url" }`

---

## 📈 Production Deployment

For Render or other hosting, see [UNIFIED_DEPLOYMENT.md](UNIFIED_DEPLOYMENT.md)

---

**Last Updated**: April 10, 2026  
**Status**: ✅ Production Ready
