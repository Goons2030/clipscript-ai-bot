# ClipScript AI - Quick Start Guide

## ⚡ 5-Minute Setup

### 1. Get Your Tokens

**Telegram Bot Token:**
1. Open Telegram
2. Message [@BotFather](https://t.me/BotFather)
3. Send `/newbot`
4. Follow steps, copy your token

**Deepgram API Key:**
1. Sign up: [console.deepgram.com](https://console.deepgram.com)
2. Go to "API Keys"
3. Create key, copy it

### 2. Create .env File

In project root (`ClipScript AI bot/`):

```
BOT_TOKEN=<your_telegram_token>
API_BASE_URL=http://localhost:3000
DEEPGRAM_API_KEY=<your_deepgram_key>
DATABASE_URL=sqlite:///database.db
FLASK_PORT=3000
```

### 3. Install & Run

```bash
# One time only
pip install -r requirements.txt

# Start all services
python main.py
```

### 4. Test

1. Open Telegram
2. Find your bot (name from @BotFather)
3. Send `/start`
4. Send: `https://www.tiktok.com/@example/video/123456789`
5. Wait 30 seconds → transcript appears!

---

## 📁 What's Running Where?

```
localhost:3000
│
├─ API Service (manages database & jobs)
├─ Telegram Bot (receives messages)
└─ Worker (transcribes videos)
```

### Check If It's Working

```bash
# In another terminal
curl http://localhost:3000/health

# Should return:
# {"status": "healthy", "services": {...}}
```

---

## 🎯 Common Tasks

### View Job Status

```bash
curl http://localhost:3000/api/status/job_id_here
```

### Stop Everything

Press `Ctrl+C` in the terminal

### View Logs

The terminal shows all logs in real-time.

### Using Only Some Services

**Just API + Worker (no bot):**
```bash
python services/api/app.py &
python services/worker/worker.py
```

**Just API (for testing):**
```bash
python services/api/app.py
```

---

## ⚠️ If Something Breaks

### "API unavailable"
- Verify `API_BASE_URL=http://localhost:3000` in `.env`
- Restart with `python main.py`

### "Bot not responding"
- Verify `BOT_TOKEN` is correct
- Kill any existing Python processes first
- Restart

### "No transcriptions"
- Verify `DEEPGRAM_API_KEY` is correct
- Check worker logs (bottom of terminal)
- Make sure API is running (see "Check If It's Working" above)

### See Full Logs
```bash
# Last 50 lines of errors
tail -50 services/api/app.log
tail -50 services/worker/worker.log
```

---

## 🚀 Next Steps

- **Deploy**: See [DEPLOYMENT.md](DEPLOYMENT.md)
- **Architecture**: See [ARCHITECTURE.md](ARCHITECTURE.md)
- **Testing**: See [TESTING.md](TESTING.md)
- **Advanced**: See [STRATEGY.md](ClipScript%20AI%20web/STRATEGY.md)

---

## 💡 Tips

- Use `python main.py` for development
- Use Docker Compose for isolation
- Use Render.com for free hosting
- Keep `.env` file safe (never commit it!)

**Need help?** Check the logs or see ARCHITECTURE.md for detailed info.
