# ClipScript AI - Unified Backend Deployment

**One Flask service handles BOTH Telegram bot + Web app**

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│      ONE Render Service Running: app_unified.py     │
├─────────────────────────────────────────────────────┤
│                                                     │
│  Telegram Users                  Web Users          │
│       ↓                               ↓             │
│  Telegram Sends Message          Browser Requests   │
│       ↓                               ↓             │
│  POST /telegram/webhook      POST /api/transcribe   │
│       ↓                               ↓             │
│  ┌──────────────────────────────────────────────┐  │
│  │     SHARED CODE                              │  │
│  │  • download_video()                         │  │
│  │  • extract_audio()                          │  │
│  │  • transcribe() [Deepgram or Whisper]       │  │
│  │  • cleanup_files()                          │  │
│  │  • Error handling & logging                 │  │
│  └──────────────────────────────────────────────┘  │
│       ↓                               ↓             │
│  Send back to Telegram          Return JSON        │
│                                                     │
└─────────────────────────────────────────────────────┘
```

---

## Why Unified Approach is Better

✅ **Cheaper** - 1 Render service ($7/month) instead of 2  
✅ **Simpler** - One code file, one deployment  
✅ **Reliable** - Shared error handling & resource cleanup  
✅ **Maintainable** - Fix bugs once, works for both  
✅ **Faster** - Both users and Telegram get responses quicker  

---

## Files

| File | Purpose | Action |
|------|---------|--------|
| `app_unified.py` | Unified backend (handles both) | Keep as-is |
| `index.html` | Web UI for browser | Update (see below) |
| `main.py` | Old Telegram bot | DELETE (replaced by unified backend) |
| `ClipScript AI web/app.py` | Old web backend | DELETE (replaced by unified backend) |
| `requirements.txt` | Dependencies | Keep (same versions) |

---

## Step 1: Update index.html

The web UI needs to point to the unified backend API.

Update the JavaScript in `index.html`:

**Find this section:**
```javascript
const response = await fetch('/api/transcribe', {
```

**Make sure it points to:**
- **Local testing:** `http://localhost:5000/api/transcribe`
- **Deployed:** `https://your-render-url/api/transcribe`

Or make it dynamic:

```javascript
const baseUrl = window.location.origin;  // Works for both local and deployed
const response = await fetch(`${baseUrl}/api/transcribe`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ link: tiktokUrl })
});
```

---

## Step 2: Test Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Run the unified backend
python app_unified.py
```

You should see:
```
==============================================================================
Starting ClipScript AI - Unified Backend
Transcription Service: deepgram
==============================================================================
Unified backend ready for Telegram (webhook) + Web API requests
```

### Test Telegram (Send to bot on Telegram)
```
Send: https://vm.tiktok.com/abc123xyz
Expected: Transcript arrives in chat
```

### Test Web API (in another terminal)
```bash
curl -X POST http://localhost:5000/api/transcribe \
  -H "Content-Type: application/json" \
  -d '{"link": "https://vm.tiktok.com/abc123xyz"}'
```

Expected response:
```json
{
  "success": true,
  "transcript": "Your transcript text...",
  "length": 123
}
```

### Test Health Check
```bash
curl http://localhost:5000/health
```

---

## Step 3: Deploy to Render

### Create render.yaml

```yaml
services:
  - type: web
    name: clipscript-ai
    env: python
    
    buildCommand: >
      apt-get update &&
      apt-get install -y ffmpeg &&
      pip install -r requirements.txt
    
    startCommand: python app_unified.py
    
    runtime: python-3.13
    
    envVars:
      - key: BOT_TOKEN
        sync: false
      - key: DEEPGRAM_API_KEY
        sync: false
      - key: TRANSCRIPTION_SERVICE
        value: deepgram
      - key: WEBHOOK_URL
        scope: runtime
        # Render sets RENDER_EXTERNAL_URL automatically
        # Code will use: https://{RENDER_EXTERNAL_URL}/telegram/webhook
```

### Deploy

1. Commit all changes:
```bash
git add .
git commit -m "Unified backend - ONE service for Telegram + Web"
git push
```

2. Go to https://dashboard.render.com

3. Click **New** → **Web Service**

4. Connect GitHub repo

5. Fill in:
   - **Name**: `clipscript-ai`
   - **Environment**: `Python 3`
   - Use **render.yaml** (if uploading) or fill manually

6. Add environment variables:
   - `BOT_TOKEN` → (from @BotFather)
   - `DEEPGRAM_API_KEY` → (from console.deepgram.com)
   - `TRANSCRIPTION_SERVICE` → `deepgram`

7. Click **Create Web Service**

---

## Step 4: Configure Telegram Webhook

The unified backend automatically sets the webhook when it starts:

1. Gets Render URL from `RENDER_EXTERNAL_URL` environment variable
2. Sets webhook to: `https://your-service.onrender.com/telegram/webhook`
3. Telegram now sends ALL messages to this webhook

**No manual configuration needed** - it's automatic!

---

## Step 5: Verify Everything Works

### Test Telegram Bot
Open Telegram → Send TikTok link to bot → Get transcript ✓

### Test Web App
1. Open browser: `https://your-service.onrender.com`
2. Paste TikTok link
3. Get transcript ✓

### Check Logs
Go to Render dashboard → Service → **Logs** tab:

```
[request_id] Telegram message received
[request_id] Download attempt 1
[request_id] Extracting audio
[request_id] Sending to Deepgram
[request_id] Transcription successful: 450 chars
[request_id] Processing complete
```

---

## File Cleanup

Remove old files from repo (keep only new unified approach):

```bash
# Delete old bot file
rm main.py

# Delete old web API file  
rm ClipScript AI web/app.py

# Keep these
# - index.html (web UI)
# - app_unified.py (unified backend)
# - requirements.txt
# - render.yaml
# - All docs
```

---

## Cost Comparison

### Before (Separate Services)
```
Telegram Bot (Worker on Render)    : Free tier
Web API (Web Service on Render)    : $7/month
Total: ~$7/month
```

### After (Unified)
```
One Web Service on Render          : $7/month (or free tier)
Total: ~$7/month or FREE
```

**Savings: Simpler infrastructure, same cost, 2x less to manage**

---

## Endpoints Summary

| Endpoint | Method | Purpose | Input |
|----------|--------|---------|-------|
| `/telegram/webhook` | POST | Receives Telegram messages | (Telegram sends automatically) |
| `/api/transcribe` | POST | Web app API | `{"link": "https://..."}` |
| `/api/pricing` | GET | Gets pricing info | (none) |
| `/health` | GET | Health check | (none) |

---

## Troubleshooting

### Bot not responding
1. Check Render logs for errors
2. Verify `BOT_TOKEN` in environment
3. Verify webhook URL set correctly (should be in logs)

### Web app returns error
1. Check Render logs
2. Verify `DEEPGRAM_API_KEY` is set and valid
3. Test with `curl` command from Step 2

### "Invalid TikTok URL"
- Make sure link format is correct
- Try both formats:
  - Long: `https://www.tiktok.com/@creator/video/123456`
  - Short: `https://vm.tiktok.com/abc123xyz`

### Processing timeout
- Video might be 30+ minutes long
- Network might be slow
- Try a different video or wait 5 minutes (TikTok rate limit)

---

## What's Different from Separate Services?

### Before (Two Services)
```
main.py (Telegram)          app.py (Web)
    ↓                           ↓
Both on separate Render services
Both had similar code (duplication)
Had to manage 2 deployments
```

### After (Unified)
```
app_unified.py (Both Telegram + Web)
    ↓
One Render deployment
One codebase
One place to manage

Same logic shared:
- Download video
- Extract audio
- Transcribe
- Error handling
```

---

## Next Steps

1. ✅ Update index.html to point to unified API
2. ✅ Test locally with `python app_unified.py`
3. ✅ Deploy to Render
4. ✅ Set environment variables
5. ✅ Test both Telegram + Web
6. ✅ Delete old files (main.py, old app.py)

**Done!** You now have one simple, unified backend serving both Telegram and web. 🚀
