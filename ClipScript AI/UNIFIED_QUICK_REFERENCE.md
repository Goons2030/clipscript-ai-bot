# Unified Backend – Quick Reference

**ONE service. Both Telegram + Web. Simple.**

---

## Current State (Before)

| Component | Technology | Deployment |
|-----------|-----------|-----------|
| Telegram Bot | `main.py` | Render Worker |
| Web API | `app.py` | Render Web Service |
| Web UI | `index.html` | Browser |
| Total | 2 separate services | 2 Render deployments |

---

## New State (After)

| Component | Technology | Deployment |
|-----------|-----------|-----------|
| Unified Backend | `app_unified.py` | **One Render Web Service** |
| Telegram Bot Handler | Built-in | Same service |
| Web API Handler | Built-in | Same service |
| Web UI | `index.html` | Browser |
| Total | **1 unified service** | **1 Render deployment** |

---

## Setup Steps (3 minutes)

### 1. Verify `app_unified.py` exists
Located at: `ClipScript AI/app_unified.py` ✓

### 2. Test locally
```bash
python app_unified.py
```

Both should work:
- Telegram: Send TikTok link to bot → Transcript arrives
- Web: Open `http://localhost:5000` in browser → Paste link → Transcript appears

### 3. Deploy to Render
```bash
git add .
git commit -m "Unified backend"
git push
```

Create new Render service:
- **Type:** Web Service
- **Command:** `python app_unified.py`
- **Environment Variables:**
  - `BOT_TOKEN`
  - `DEEPGRAM_API_KEY`
  - `TRANSCRIPTION_SERVICE=deepgram`

### Done! ✅

---

## How It Works (Technical)

### Telegram Flow
```
User sends message to @yourbot on Telegram
    ↓
Telegram sends to: https://your-service.onrender.com/telegram/webhook
    ↓
Flask backend processes message
    ↓
Returns transcript to Telegram chat
```

### Web Flow
```
User opens: https://your-service.onrender.com
    ↓
Pastes TikTok link in web form
    ↓
JavaScript calls: POST /api/transcribe
    ↓
Flask backend processes request
    ↓
Returns JSON with transcript
    ↓
Web page displays result
```

### Both Share Same Code
```
process_transcription()
  ├─ download_video()
  ├─ extract_audio()
  ├─ transcribe()   [Deepgram or Whisper]
  ├─ cleanup_files()
  └─ error handling
```

---

## Files to Keep & Delete

### Keep (Unified)
- ✅ `app_unified.py` - Unified backend
- ✅ `index.html` - Web UI
- ✅ `requirements.txt` - Dependencies
- ✅ `render.yaml` - Deployment config

### Delete (Old)
- ❌ `main.py` - Old Telegram bot
- ❌ `ClipScript AI web/app.py` - Old web API
- ❌ `start_bot.py` - Helper script
- ❌ `run.py` - Helper script

### Documentation (Keep)
- ✅ `README.md`
- ✅ `UNIFIED_DEPLOYMENT.md` - New guide
- ✅ All others

---

## Endpoints

| Endpoint | Method | For | Input |
|----------|--------|-----|-------|
| `/telegram/webhook` | POST | Telegram | (Auto from Telegram) |
| `/api/transcribe` | POST | Web app | `{"link": "..."}` |
| `/api/pricing` | GET | Info | None |
| `/health` | GET | Status | None |

---

## Benefits

✅ **Simpler** - One code file instead of two  
✅ **Cheaper** - One Render service ($7/month) instead of two  
✅ **Faster** - Single deployment, both users get updates together  
✅ **Easier to maintain** - Fix bugs once, works everywhere  
✅ **Better resource management** - Shared processing pool  

---

## Costs

| Before | After |
|--------|-------|
| Telegram (Worker) + Web (Service) | One Web Service |
| ~$7/month (Web) + Free (Worker) | $7/month or Free tier |
| Manage 2 services | Manage 1 service |

---

## Testing Checklist

```bash
# 1. Local test
python app_unified.py    # Should start without errors

# 2. Test Telegram (from Telegram app)
Send TikTok link        # Should respond with transcript

# 3. Test Web API
curl -X POST http://localhost:5000/api/transcribe \
  -H "Content-Type: application/json" \
  -d '{"link": "https://vm.tiktok.com/abc123xyz"}'
                         # Should return JSON with transcript

# 4. Test Health
curl http://localhost:5000/health
                         # Should return {"status": "ok", ...}
```

---

## Common Issues

### Issue: "Webhook URL not set"
**Solution:** Code automatically detects Render URL. Or set `WEBHOOK_URL` env var.

### Issue: "Bot not responding on Telegram"
**Solution:** Check Render logs. Verify `BOT_TOKEN` is correct in environment.

### Issue: "Web API returns 404"
**Solution:** Make sure `index.html` is in same folder or update API endpoint.

### Issue: "Deepgram returns error"
**Solution:** Verify `DEEPGRAM_API_KEY` is set and has credits.

---

## Rename Convention

When moving to unified approach:

```
Old:                          New:
main.py         →             app_unified.py
                              (or rename to app.py when deploying)

app.py          →             DELETE (replaced by app_unified.py)

index.html      →             (stays same, just update API call)
                              (already uses relative /api/transcribe)
```

---

## Deployment Command (One-liner)

```bash
# After making changes locally
git add . && git commit -m "Unified backend" && git push

# Then deploy on Render dashboard (existing service)
# or create new service with: python app_unified.py
```

---

## Next: Monitor and Scale

Once deployed:

1. **Monitor** - Check Render logs for errors
2. **Test** - Send 5-10 test messages
3. **Share** - Give bot/web link to users
4. **Optimize** - Monitor usage, adjust if needed

---

**That's it!** You now have a single, unified backend serving both Telegram and web. Simple, reliable, easy to maintain. 🚀
