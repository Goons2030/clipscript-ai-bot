# Telegram Bot Service - ClipScript AI

## Overview

The Telegram Bot Service:

- Receives messages from Telegram users
- Extracts video links
- Sends transcription requests to API Service
- Polls for results
- Returns transcripts to users

## 🏗️ Architecture

```
Telegram User
     │
     ↓ (Message)
Telegram Bot Service
     ├─ Receives message
     ├─ Validates link
     ├─ Sends to API
     ├─ Polls for result
     └─ Sends transcript back
     
All communication: HTTP to API Service
No direct processing, no asyncio conflicts
```

## 🚀 Running

```bash
cd services/bot
python telegram_bot.py

# Output:
# 🤖 Initializing Telegram Bot Service...
# 🔄 Starting Telegram polling...
```

## 📱 Telegram Commands

### /start
Welcome message with instructions

### /help
List of supported platforms and commands

### /status
Check if bot is online and ready

### Send a Link
Any message with a URL:
- TikTok: `https://www.tiktok.com/@user/video/123`
- YouTube: `https://www.youtube.com/watch?v=...`
- Instagram: `https://www.instagram.com/p/...`
- Twitter/X: `https://twitter.com/user/status/123`

## 🔄 Message Flow

```
User sends: >https://www.tiktok.com/...
                     │
                     ↓
     handle_message() in telegram_bot.py
                     │
                     ├─ Validate URL ✓
                     │
                     ├─ Show "⏳ Queuing..." message
                     │
                     ├─ POST /api/transcribe
                     │
                     ├─ Get job_id from API
                     │
                     ├─ Poll /api/status/{job_id} every 5 seconds
                     │
                     @─ When status = "completed"
                     │
                     └─ Send transcript to user ✅
```

## 🛠️ Files

- `telegram_bot.py` - Main bot application
- `handlers.py` - Message & command handlers (optional)

## ⚙️ Configuration

Via `.env`:
```
BOT_TOKEN=<telegram_bot_token>
API_BASE_URL=http://localhost:3000
ENABLE_TELEGRAM_WEBHOOK=false
TELEGRAM_WEBHOOK_URL=https://your-domain.com/webhook
```

## 🔑 Getting a Bot Token

1. Open Telegram, message [@BotFather](https://t.me/BotFather)
2. Send `/newbot`
3. Follow instructions (name, username)
4. Copy token provided
5. Add to `.env` as `BOT_TOKEN`

## 🔄 Polling vs Webhook

### Polling (Simpler)
```
Bot continuously asks Telegram:
"Any new messages?"
"Any new messages?"
"Any new messages?"
```
- **Pros**: Simple, works everywhere
- **Cons**: Slower, more API calls
- **Default**: Used in this bot

### Webhook (Production)
```
Telegram sends messages directly to bot endpoint
```
- **Pros**: Instant, efficient
- **Cons**: Requires HTTPS, static IP
- **Setup**: See DEPLOYMENT.md

## 💬 Handler Examples

### Adding a New Command

In `telegram_bot.py`:
```python
async def handle_custom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /custom command"""
    await update.message.reply_text("Response here")

# In setup_handlers():
self.app.add_handler(CommandHandler("custom", self.handle_custom))
```

### Adding a New Message Type

```python
async def handle_special(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle specific message pattern"""
    # Check message content
    if "special_word" in update.message.text:
        await update.message.reply_text("Special handling")

# In setup_handlers():
self.app.add_handler(MessageHandler(
    filters.TEXT & filters.Regex(r'special_word'),
    self.handle_special
))
```

## ⏱️ Timeout & Polling

**Current behavior:**
- Polls for result every 5 seconds
- Timeouts after 5 minutes (60 polls)
- Shows timeout message if no result

**Customization** (in `handle_message`):
```python
max_polls = 120  # Change to increase timeout
poll_interval = 3  # Seconds between polls
```

## 🐛 Debugging

### Test Bot Manually
```bash
# In Python REPL
from telegram import Update
from telegram.ext import Application

# Check bot can connect
app = Application.builder().token(BOT_TOKEN).build()
bot = app.bot
await bot.send_message(chat_id=<YOUR_ID>, text="Test")
```

### View Logs
```bash
# Run with verbose logging
LOGLEVEL=DEBUG python telegram_bot.py
```

### Common Issues

**"Error: Unauthorized"**
- Bot token is incorrect
- Token was reverted (bad practice)
- Bot was deleted

**"Bot doesn't respond"**
- Check API_BASE_URL is correct
- Verify API service is running
- Check firewall/network access

**"Messages very slow to respond"**
- Increase polling frequency (lower sleep value)
- Check internet connection
- Verify API response time

## 📊 Monitoring

### Health Check
```bash
curl http://localhost:3000/health
```

### View Bot Logs
```bash
# Tail last 100 lines
tail -100 telegram_bot.log
```

### Test API Connection
```python
import requests
response = requests.get("http://localhost:3000/health")
print(response.json())
```

## 🌐 Webhook Mode (Advanced)

For production deployment with faster response times:

**In `.env`:**
```
ENABLE_TELEGRAM_WEBHOOK=true
TELEGRAM_WEBHOOK_URL=https://yourdomain.com/webhook
```

**Requires:**
- HTTPS certificate
- Public domain
- Port 443 or 8443 open
- See DEPLOYMENT.md for setup

## 🚀 Production Checklist

- [ ] Bot token is secure (never in logs)
- [ ] API_BASE_URL points to production API
- [ ] Error messages don't leak system info
- [ ] Timeout handling is graceful
- [ ] User data is not logged
- [ ] Bot grouped calls are rate-limited
- [ ] Consider webhook mode for scale

## 📈 Scaling

**Multiple Bot Instances:**
```
Bot 1 --┐
Bot 2 --|──> API Service (handles all)
Bot 3 --┘
```

All bots can share same token and API endpoint.
API service handles job queue & deduplication.

## 💡 Tips

- Use `/start` to guide new users
- Provide `/help` with clear instructions
- Keep `/status` response brief
- Use emojis for user clarity
- Acknowledge long operations with "⏳"
- Handle errors gracefully with "❌"

## 🔒 Security

- Never commit `.env` with real token
- Don't log user messages
- Validate all links before processing
- Rate limit per user (optional)
- Timeout protection on long operations

---

**See:** [ARCHITECTURE.md](../../ARCHITECTURE.md) | [DEPLOYMENT.md](../../DEPLOYMENT.md)
