# ClipScript AI – Unified Backend Setup Guide

You asked: "Can we use ONE backend for Telegram + Web?"

**Answer: YES. Here's how.**

---

## What You Get

One Flask backend that handles:
- ✅ **Telegram webhook** → `/telegram/webhook`
- ✅ **Web API** → `/api/transcribe`
- ✅ **Health check** → `/health`

Both Telegram and Web use the SAME backend. Simple.

---

## Files

**Replace your current files with:**

| Old File | New File | Purpose |
|----------|----------|---------|
| `main.py` | `app_unified.py` | Single backend (rename to `app.py` when using) |
| `app.py` | Delete | No longer needed |
| `requirements.txt` | Same | No changes needed |
| `.env` | Same | No changes needed |

---

## Step 1: Download the Unified Backend

Download: **app_unified.py**

Rename it to: **app.py**

(Replace your old app.py)

---

## Step 2: Test Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Run the unified backend
python app.py
```

You should see:
```
Starting ClipScript AI Unified Backend...
Telegram webhook set to: http://localhost:5000/telegram/webhook
Unified backend running...
```

---

## Step 3: Test Both Endpoints

### **Test Telegram (via webhook)**

Open Telegram and send a TikTok link to your bot:
```
https://vm.tiktok.com/abc123xyz
```

Should get transcript back ✓

### **Test Web (via HTTP)**

Open browser and test API:
```bash
curl -X POST http://localhost:5000/api/transcribe \
  -H "Content-Type: application/json" \
  -d '{"link": "https://vm.tiktok.com/abc123xyz"}'
```

Should return:
```json
{
  "success": true,
  "transcript": "Your transcript text here",
  "length": 123
}
```

✓ Both work!

---

## Step 4: Deploy to Render

### **Option A: Using render.yaml**

```yaml
services:
  - type: web
    name: clipscript-ai
    env: python
    buildCommand: apt-get update && apt-get install -y ffmpeg && pip install -r requirements.txt
    startCommand: python app.py
    envVars:
      - key: BOT_TOKEN
      - key: OPENAI_API_KEY
      - key: DEEPGRAM_API_KEY
      - key: TRANSCRIPTION_SERVICE
        value: deepgram
```

### **Option B: Manual Render Setup**

1. Go to https://dashboard.render.com
2. Click **New** → **Web Service**
3. Connect GitHub repo
4. Fill in:
   - **Name**: `clipscript-ai`
   - **Environment**: Python 3
   - **Build Command**: `apt-get update && apt-get install -y ffmpeg && pip install -r requirements.txt`
   - **Start Command**: `python app.py`
5. Add environment variables:
   - `BOT_TOKEN`
   - `DEEPGRAM_API_KEY` (or `OPENAI_API_KEY`)
   - `TRANSCRIPTION_SERVICE=deepgram`
6. Click **Create Web Service**

---

## Step 5: Configure Telegram Webhook

The unified backend automatically tells Telegram where to send messages.

When you deploy, the backend gets a URL like:
```
https://clipscript-ai-xxx.onrender.com
```

The code automatically sets webhook to:
```
https://clipscript-ai-xxx.onrender.com/telegram/webhook
```

**How it works:**
```python
# In app_unified.py, on startup:
webhook_url = f"{os.getenv('RENDER_EXTERNAL_URL')}/telegram/webhook"
await telegram_app.bot.set_webhook(url=webhook_url)
```

Telegram receives this and starts sending messages to that URL.

---

## Step 6: Test Live

### **Test Telegram Bot**
Open Telegram → Send TikTok link to your bot → Get transcript ✓

### **Test Web API**
```bash
curl -X POST https://clipscript-ai-xxx.onrender.com/api/transcribe \
  -H "Content-Type: application/json" \
  -d '{"link": "https://vm.tiktok.com/abc123xyz"}'
```

Should work ✓

---

## Architecture Diagram

```
┌────────────────────────────────────────────────┐
│         ONE RENDER WEB SERVICE                 │
│                                                │
│         Python Flask Backend                   │
│            (app_unified.py)                    │
│                                                │
│  ┌──────────────────────────────────────────┐ │
│  │   POST /telegram/webhook                 │ │
│  │   └─ Receives Telegram messages          │ │
│  │   └─ Processes TikTok link               │ │
│  │   └─ Sends transcript back to Telegram   │ │
│  └──────────────────────────────────────────┘ │
│                                                │
│  ┌──────────────────────────────────────────┐ │
│  │   POST /api/transcribe                   │ │
│  │   └─ Receives web API requests           │ │
│  │   └─ Processes TikTok link               │ │
│  │   └─ Returns JSON response               │ │
│  └──────────────────────────────────────────┘ │
│                                                │
│  ┌──────────────────────────────────────────┐ │
│  │   GET /health                            │ │
│  │   └─ Returns status                      │ │
│  └──────────────────────────────────────────┘ │
│                                                │
│  Shared resources:                             │
│    • Deepgram/Whisper API                     │
│    • FFmpeg                                   │
│    • Error handling                           │
└────────────────────────────────────────────────┘
        ↑                          ↑
        │                          │
   Telegram Users             Web Users
   (webhook)                (HTTP API)
```

---

## Cost Comparison

### **Old Setup (Two Services)**
```
Telegram bot (main.py on Render worker):  $0–7/month
Web API (app.py on Render web):           $7/month
───────────────────────────────────────────────────
Total:                                    $7–14/month
```

### **New Setup (One Service)**
```
Unified backend (app_unified.py on Render): $0–7/month
───────────────────────────────────────────────────────
Total:                                      $0–7/month
```

**You save: $7/month** = $84/year 💰

---

## Web App (index.html) — No Changes

Your web app stays the same:
```javascript
// index.html still calls the same endpoint
async function transcribe() {
    const response = await fetch('/api/transcribe', {
        method: 'POST',
        body: JSON.stringify({ link })
    });
    const data = await response.json();
    return data.transcript;
}
```

**Works exactly the same**, just uses the unified backend.

---

## Telegram Flow (How Webhooks Work)

### **Step 1: User Sends Message to Bot**
```
User: (sends TikTok link)
  ↓
Telegram servers receive it
```

### **Step 2: Telegram Forwards to Your Backend**
```
Telegram: POST https://your-backend.com/telegram/webhook
Body: {
  "message": {
    "text": "https://vm.tiktok.com/abc123xyz",
    "chat": { "id": 12345 }
  }
}
```

### **Step 3: Your Backend Processes**
```python
@app.route('/telegram/webhook', methods=['POST'])
async def telegram_webhook():
    message = request.json['message']
    link = message['text']
    transcript = process_transcription(link)
    send_back_to_telegram(message['chat']['id'], transcript)
    return 'OK'
```

### **Step 4: Telegram User Gets Response**
```
User receives: (transcript text in Telegram)
```

**All happens in one service. Simple.**

---

## Debugging

### **Check Logs**

On Render:
1. Go to your service
2. Click **Logs** tab
3. Look for errors

Locally:
```bash
python app.py  # See logs in terminal
```

### **Test Webhook URL**

Check if Telegram can reach your webhook:
```bash
curl -X POST https://your-backend.com/telegram/webhook \
  -H "Content-Type: application/json" \
  -d '{"update_id": 1, "message": {"text": "test"}}'
```

Should return: `{"status": "ok"}`

### **Check Environment Variables**

Render service should have:
```
BOT_TOKEN = your_token
DEEPGRAM_API_KEY = your_key
TRANSCRIPTION_SERVICE = deepgram
RENDER_EXTERNAL_URL = https://your-app.onrender.com
```

---

## Switch From Old to New

If you're already running the old setup:

### **Method 1: Clean Migration (Zero Downtime)**
```
Day 1: Deploy new unified backend as new service
Day 2: Update GitHub to use unified backend
Day 3: Delete old services
```

### **Method 2: Quick Switch**
```
1. Stop old services
2. Deploy unified backend
3. Done
```

---

## Maintenance

### **Update Code**
```bash
git push origin main
# Render auto-rebuilds
```

### **Update Telegram Webhook**
If you change the backend URL, it auto-updates on startup:
```python
webhook_url = f"{os.getenv('RENDER_EXTERNAL_URL')}/telegram/webhook"
await telegram_app.bot.set_webhook(url=webhook_url)
```

---

## FAQ

**Q: What if the backend goes down?**
A: Both Telegram and Web go down together. For MVP, acceptable. For scale, add monitoring.

**Q: Can I scale Telegram separately?**
A: Yes. If needed later, split into two services. Easy to do.

**Q: Does webhook vs polling matter?**
A: YES. Webhooks are faster, cheaper, better. You get instant message delivery.

**Q: What about rate limiting?**
A: Easy to add if needed. For now, not necessary.

**Q: Can I add more endpoints later?**
A: Yes. Just add more routes to `app_unified.py`.

---

## Checklist

```
☐ Download app_unified.py
☐ Rename to app.py
☐ Test locally: python app.py
☐ Test Telegram endpoint
☐ Test Web endpoint
☐ Deploy to Render
☐ Update environment variables
☐ Test live Telegram
☐ Test live Web
☐ Delete old services (if migrating)
```

---

## Summary

**What changed:**
- Old: Telegram bot (main.py) + Web API (app.py) = 2 services
- New: Unified backend (app_unified.py) = 1 service

**Benefits:**
- ✅ Simpler
- ✅ Cheaper ($7/month instead of $14)
- ✅ Faster (webhooks instead of polling)
- ✅ Easier to maintain

**Your decision:**
- Keep old setup? Works fine.
- Use unified setup? Better. I recommend this.

---

**To use the unified backend:**

1. Download: **app_unified.py**
2. Rename to: **app.py**
3. Deploy to Render
4. Both Telegram + Web work from same backend

Done. Na so. 🔥
