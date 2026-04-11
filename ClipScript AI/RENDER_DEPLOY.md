# ClipScript AI – Render Deployment Guide

## Prerequisites
- GitHub repo with the project pushed
- Render account (https://render.com) – free tier works!
- Telegram Bot Token (@BotFather on Telegram)
- Deepgram API Key (https://console.deepgram.com) – free tier: $200/month

---

## Step 1: Prepare GitHub Repo

Required files:
```
main.py
requirements.txt
.env.example
.gitignore (with: .env, temp/, logs/, *.zip)
render.yaml
```

Add to `.gitignore`:
```
.env
temp/
logs/
*.zip
.venv/
```

Push everything to GitHub.

---

## Step 2: Create Render Worker Service

1. Go to https://dashboard.render.com
2. Click **New +** → **Background Worker**
3. Connect your GitHub repo
4. Configure:
   - **Name**: `clipscript-ai-bot`
   - **Environment**: `Python 3`
   - **Region**: Choose closest to you

---

## Step 3: FFmpeg Setup (CRITICAL)

Render doesn't include FFmpeg. Use `render.yaml` (recommended):

Create `render.yaml` in your repo root:
```yaml
services:
  - type: worker
    name: clipscript-ai-bot
    env: python
    buildCommand: >
      apt-get update &&
      apt-get install -y ffmpeg &&
      pip install -r requirements.txt
    startCommand: python main.py
    envVars:
      - key: BOT_TOKEN
        sync: false
      - key: DEEPGRAM_API_KEY
        sync: false
```

In Render dashboard:
1. Select **Deploy from render.yaml**
2. Click **Create Web Service**

---

## Step 4: Add Environment Variables

In Render dashboard → **Environment**:

```
BOT_TOKEN = your_telegram_bot_token_here
DEEPGRAM_API_KEY = your_deepgram_api_key_here
```

⚠️ **Important**: Do NOT add to render.yaml or git – only in dashboard!

**How to get:**
- **BOT_TOKEN**: Message @BotFather on Telegram → `/newbot` → copy token
- **DEEPGRAM_API_KEY**: Go to https://console.deepgram.com → login → API Keys → copy

---

## Step 5: Deploy & Monitor

1. Click **Deploy**
2. Wait 10–15 minutes for build (first time takes longer)
3. Watch **Logs** tab for status:
   ```
   apt-get: Installing ffmpeg...
   pip install: Installing packages...
   Starting ClipScript AI bot...
   Bot initialized and handlers registered
   Starting polling...
   ```

4. Once you see `Application started`, bot is **LIVE** ✅

---

## Step 6: Test

Send your Telegram bot a TikTok link:
```
https://www.tiktok.com/@username/video/1234567890
https://vm.tiktok.com/abc123xyz
```

Bot should respond in 5–30 seconds with transcript.

---

## Troubleshooting

### `ffmpeg: command not found`
**Cause**: Build didn't install FFmpeg  
**Fix**: 
- Check `render.yaml` is in root
- Check syntax (YAML is strict)
- Delete service and redeploy

### Bot doesn't respond
**Cause**: Token or API key wrong  
**Fix**:
- Verify `BOT_TOKEN` in Environment
- Verify `DEEPGRAM_API_KEY` has credits (https://console.deepgram.com)
- Check Logs tab for errors

### `Deepgram API: 403 Forbidden`
**Cause**: API key expired or wrong  
**Fix**: Generate new key from https://console.deepgram.com

### `TikTok: 403 Forbidden`
**Cause**: TikTok blocking that IP (normal)  
**Fix**: Bot retries with backoff. Wait 5-10 minutes, try again.

### Service keeps restarting
**Cause**: Bot crashing due to error  
**Fix**:
- Check Logs for errors
- Verify all environment variables set
- Verify FFmpeg installed (check logs)

---

## Cost Breakdown

| Service | Free Tier | Cost |
|---------|-----------|------|
| **Render** | 1 worker, 750 hrs/month | Free ✅ |
| **Deepgram** | $200/month free credits | Free ✅ |
| **TikTok download** | Unlimited | Free ✅ |
| **Total** | | **~Free** |

Deepgram at $0.0043/min:
- 100 videos/day = ~$1.30/month ✅
- 1000 videos/day = ~$13/month ✅

---

## Monitoring & Logs

### View Logs in Render
- Go to service page → **Logs** tab
- Scroll to see all activity
- Each request shows:
  ```
  [a1b2c3d4] New request started
  [a1b2c3d4] Starting download...
  [a1b2c3d4] Success: 450 chars transcribed
  [a1b2c3d4] Request completed
  ```

### Download Logs
At bottom of Logs tab: **Download all logs as file**

### Real-time Monitoring
Render only shows Logs tab in dashboard. For real-time:
- Use Render API (advanced)
- Or check logs periodically

---

## Auto-Restart (If Bot Dies)

If bot crashes, it won't auto-restart on free tier. To keep it alive:

Option A: Use a health check service (PingKeep, Uptime Robot - free)
- Set bot URL: `https://your-service.onrender.com` (even though it's a worker)
- Health check every 5 minutes

Option B: Switch to **Web Service** instead of Worker
- Requires Render to serve HTTP (adds complexity)
- Not needed for Telegram polling

For a simple, reliable bot: stick with **Worker** service (recommended).

---

## Next Steps

✅ Deployment complete!  
✅ Bot is live on Render  
✅ Test with TikTok links

**Questions?**
- Check Logs tab in Render
- Verify tokens in Environment
- Verify FFmpeg installed (should see in build logs)(check logs)

---

## Cost Breakdown

| Service | Free Tier | Cost |
|---------|-----------|------|
| **Render** | 1 worker, 750 hrs/month | Free ✅ |
| **Deepgram** | $200/month free credits | Free ✅ |
| **TikTok download** | Unlimited | Free ✅ |
| **Total** | | **~Free** |

Deepgram at $0.0043/min:
- 100 videos/day = ~$1.30/month ✅
- 1000 videos/day = ~$13/month ✅

---

## Monitoring & Logs

### View Logs in Render
- Go to service page → **Logs** tab
- Scroll to see all activity
- Each request shows:
  ```
  [a1b2c3d4] New request started
  [a1b2c3d4] Starting download...
  [a1b2c3d4] Success: 450 chars transcribed
  [a1b2c3d4] Request completed
  ```

### Download Logs
At bottom of Logs tab: **Download all logs as file**

### Real-time Monitoring
Render only shows Logs tab in dashboard. For real-time:
- Use Render API (advanced)
- Or check logs periodically

---

## Auto-Restart (If Bot Dies)

If bot crashes, it won't auto-restart on free tier. To keep it alive:

Option A: Use a health check service (PingKeep, Uptime Robot - free)
- Set bot URL: `https://your-service.onrender.com` (even though it's a worker)
- Health check every 5 minutes

Option B: Switch to **Web Service** instead of Worker
- Requires Render to serve HTTP (adds complexity)
- Not needed for Telegram polling

For a simple, reliable bot: stick with **Worker** service (recommended).

---

## Next Steps

✅ Deployment complete!  
✅ Bot is live on Render  
✅ Test with TikTok links

**Questions?**
- Check Logs tab in Render
- Verify tokens in Environment
- Verify FFmpeg installed (should see in build logs)
- Filter by timestamp
- Common patterns: `ERROR`, `timeout`, `403`

---

## Upgrade: Keep Bot Running 24/7

Render free tier puts services to sleep.

**To keep running:**
1. Upgrade to Paid ($7/month)
2. Or use a free alternative (Railway, Fly.io)

---

That's it. Deploy and test.
