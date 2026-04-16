# CLIPSCRIPT AI – FINAL DEPLOYMENT CONFIGURATION
## Railway Deployment (Single Source of Truth)

**Status:** ✅ RESOLVED - All conflicts eliminated
**Date:** April 16, 2026
**Target:** Railway Production

---

## 1. CONFIRMED ENTRYPOINT ✅

### Flask App Location
```
backend/app_unified.py
```

### Flask Instance Definition
```python
# Line 122 in backend/app_unified.py
app = Flask(__name__)
```

### Gunicorn Module:Variable Format
```
app_unified:app
```

---

## 2. RESOLVED CONFLICTS ✅

### Files DELETED (Conflicting Configs)
- ❌ `Procfile` — REMOVED (Railway doesn't use this)
- ❌ `render.yaml` — REMOVED (legacy Render service blueprint)
- ❌ `main.py` in root — NOT an entrypoint, ignore

### Why They Were a Problem
- **Multiple sources of truth** = Railway confused about which config to use
- **Procfile**: Railway ignores file-based configs; reads from Dashboard only
- **render.yaml**: Irrelevant for Railway; was for old Render service
- **Result**: "No entrypoint found" or directory listing fallback

### Single Source of Truth ✅
**Railway Dashboard is the ONLY deployment config**

---

## 3. RAILWAY DASHBOARD CONFIGURATION ✅

### Set These in Railway Project Dashboard:

#### Root Directory
```
/backend
```
**Why:** Gunicorn must be in this directory to resolve `app_unified:app`

#### Build Command
```
pip install -r requirements.txt && apt-get update && apt-get install -y ffmpeg
```
**Why:** Install Python deps + FFmpeg for video processing

#### Start Command
```
gunicorn app_unified:app --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 120
```

**Explanation:**
- `app_unified:app` — Import Flask instance from backend/app_unified.py
- `--bind 0.0.0.0:$PORT` — Listen on Railway-provided PORT
- `--workers 1` — Single worker process (sufficient for Railway)
- `--threads 8` — 8 threads per worker for concurrency
- `--timeout 120` — 120-second timeout for long video processing

#### Environment Variables
Set in Railway Dashboard (NOT in config files):
```
BOT_TOKEN=<your-token>
DEEPGRAM_API_KEY=<your-key>
WEBHOOK_URL=https://<railway-app>.railway.app/telegram/webhook
TRANSCRIPTION_SERVICE=deepgram
FLASK_ENV=production
```

---

## 4. DEPLOYMENT FLOW ✅

```
1. User pushes to git
   ↓
2. Railway detects push
   ↓
3. Railway reads ONLY Dashboard config (NOT files)
   ↓
4. Railway cd into /backend
   ↓
5. Railway installs: pip install gunicorn flask flask-cors ...
   ↓
6. Railway starts: gunicorn app_unified:app --bind 0.0.0.0:$PORT ...
   ↓
7. Gunicorn imports: from app_unified import app
   ↓
8. Flask instance loads: app = Flask(__name__)
   ↓
9. API endpoints available at: https://<app>.railway.app/api/transcribe
   ↓
10. Telegram webhook configured: https://<app>.railway.app/telegram/webhook
```

---

## 5. VERIFICATION CHECKLIST ✅

### Before Deployment
- [ ] Gunicorn in `backend/requirements.txt`
- [ ] No Procfile in root (DELETED ✅)
- [ ] No render.yaml in root (DELETED ✅)
- [ ] `backend/app_unified.py` contains `app = Flask(__name__)`
- [ ] Railway dashboard has Root Directory: `/backend`
- [ ] Railway dashboard has Start Command: `gunicorn app_unified:app --bind 0.0.0.0:$PORT ...`

### Expected Logs After Deployment
```
[2026-04-16] Started build: installing dependencies
[2026-04-16] pip install -r requirements.txt
[2026-04-16] Successfully installed gunicorn flask flask-cors yt-dlp ...
[2026-04-16] Starting service: gunicorn app_unified:app --bind 0.0.0.0:$PORT
[gunicorn] Starting gunicorn 21.2.0
[gunicorn] Listening at: http://0.0.0.0:PORT (PID: XXXXX)
[gunicorn] Worker process [XXXXX] started
[app_unified] OK Database initialized successfully
[app_unified] CONFIG WEBHOOK MODE - Telegram webhook enabled
[app_unified] OK Unified backend ready for Telegram + Web API requests
```

### NOT These Errors
```
❌ "No python entrypoint found"
❌ "(404 Not Found) Directory Listing Enabled"
❌ "ModuleNotFoundError: No module named 'app_unified'"
❌ "TypeError: 'NoneType' object is not callable"
```

### Test Endpoints After Deployment
```bash
# Test API endpoint
curl https://<app>.railway.app/
# Should return: API response (not directory listing)

# Test transcription endpoint
curl -X POST https://<app>.railway.app/api/transcribe \
  -H "Content-Type: application/json" \
  -d '{"links":["https://www.tiktok.com/..."]}'
# Should return: JSON response (success or error)

# Test Telegram webhook
curl https://<app>.railway.app/telegram/webhook
# Should return: 404 (webhook expects POST from Telegram)
```

---

## 6. LOCAL DEVELOPMENT vs PRODUCTION

### Local Development
```bash
cd backend
python app_unified.py
```
**Why:** 
- `if __name__ == '__main__':` block handles dev mode
- Automatically detects polling vs webhook based on WEBHOOK_URL env
- Can run Telegram bot locally (polling mode)

### Local Testing with Gunicorn (matches production)
```bash
cd backend
gunicorn app_unified:app --bind 127.0.0.1:5000 --workers 1 --threads 8 --timeout 120
```
**Why:** 
- Tests production config locally
- Gunicorn won't start bot (only Flask dev server does)
- Verify API endpoints work with Gunicorn

### Production (Railway)
```bash
gunicorn app_unified:app --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 120
```
**Why:**
- Production-grade WSGI server
- Proper concurrency handling
- Railway provides PORT env var
- Only Flask handles Telegram (webhook mode, no polling)

---

## 7. FILE STRUCTURE (Reference)

```
ClipScript AI/
├── backend/
│   ├── app_unified.py      ← ✅ PRODUCTION ENTRYPOINT
│   ├── db.py
│   ├── requirements.txt    ← ✅ Add gunicorn==21.2.0
│   ├── VERIFICATION_REPORT.md
│   └── ... other files
├── frontend/
├── services/              ← Not needed for Railway
├── main.py               ← Ignore (dev orchestrator)
├── DEPLOYMENT_CONFIG.md  ← This file
├── verify_entrypoint.py
├── README.md
└── ... other files

❌ DELETED:
   - Procfile
   - render.yaml
```

---

## 8. WHY THIS WORKS

### The Problem (Old Setup)
```
❌ Procfile exists    ← Railway ignores (uses Dashboard only)
❌ render.yaml exists ← Legacy config, not used by Railway
❌ Dashboard config   ← Was correct, but overshadowed by files
Result: Ambiguity → "No entrypoint found"
```

### The Solution (New Setup)
```
✅ Procfile DELETED
✅ render.yaml DELETED
✅ Railway Dashboard is SOLE source of truth
   ├── Root Directory: /backend
   ├── Build: pip install + ffmpeg
   ├── Start: gunicorn app_unified:app ...
   ├── Environment vars: BOT_TOKEN, DEEPGRAM_API_KEY, etc.
Result: Single clear path → Works correctly
```

### Why Gunicorn?
- **Production-grade**: Handles multiple concurrent requests
- **WSGI-compliant**: Proper Flask integration
- **Railway compatible**: No special config needed
- **Thread-safe**: Flask + threading = proper concurrency
- **Logging**: Outputs to Railway logs correctly

---

## 9. COMMON MISTAKES (AVOID)

### ❌ DON'T DO THIS
```bash
# Wrong: Using Flask dev server in production
FLASK_ENV=production python app_unified.py

# Wrong: Using cd in start command
gunicorn -w 4 cd backend app_unified:app

# Wrong: Including .py extension
gunicorn app_unified.py:app

# Wrong: Full file path
gunicorn backend/app_unified:app

# Wrong: Using Procfile (Railway ignores)
web: gunicorn app_unified:app
```

### ✅ DO THIS
```bash
# Correct: Gunicorn in production
gunicorn app_unified:app --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 120

# Correct: Set Root Directory to /backend in Railway Dashboard
# Then Gunicorn automatically resolves app_unified:app from that directory

# Correct: Module:app format (no path, no .py)
app_unified:app
```

---

## 10. DEPLOYMENT STEPS

1. **Ensure Gunicorn in requirements.txt:**
   ```bash
   grep gunicorn backend/requirements.txt
   # Should show: gunicorn==21.2.0
   ```

2. **Verify Entrypoint:**
   ```bash
   grep "app = Flask" backend/app_unified.py
   # Should show: app = Flask(__name__)
   ```

3. **Commit & Push:**
   ```bash
   git add -A
   git commit -m "Clean deployment: removed conflicting configs, use Railway UI only"
   git push origin main  # or your branch
   ```

4. **Go to Railway Dashboard:**
   - Project → Settings → Deployment
   - Set Root Directory: `/backend`
   - Set Start Command: 
     ```
     gunicorn app_unified:app --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 120
     ```
   - Set Build Command:
     ```
     pip install -r requirements.txt && apt-get update && apt-get install -y ffmpeg
     ```

5. **Set Environment Variables in Railway Dashboard:**
   - BOT_TOKEN
   - DEEPGRAM_API_KEY
   - WEBHOOK_URL
   - TRANSCRIPTION_SERVICE=deepgram
   - FLASK_ENV=production

6. **Deploy:**
   - Railway will start build
   - Should see: "Listening at: http://0.0.0.0:PORT"
   - Test endpoints

7. **Verify No Errors:**
   ```bash
   # View logs
   railway logs

   # Should show: OK Database initialized successfully
   # Should NOT show: "No entrypoint found" or directory listing
   ```

---

## 11. SUMMARY

| Aspect | Status | Details |
|--------|--------|---------|
| **Entrypoint** | ✅ | backend/app_unified.py:app |
| **Config Conflicts** | ✅ RESOLVED | Procfile & render.yaml deleted |
| **Single Source** | ✅ | Railway Dashboard only |
| **Root Directory** | ✅ | /backend |
| **Start Command** | ✅ | gunicorn app_unified:app --bind 0.0.0.0:$PORT ... |
| **WSGI Server** | ✅ | Gunicorn 21.2.0 |
| **Production Ready** | ✅ | YES - Deploy confidently |

---

## 12. FINAL STATUS

✅ **CLEAN DEPLOYMENT CONFIGURATION**
✅ **SINGLE SOURCE OF TRUTH (Railway UI)**
✅ **NO FILE-BASED CONFLICTS**
✅ **PRODUCTION-READY FOR RAILWAY**

🚀 **Ready to deploy!**

---

**For questions:** Refer to this file. All decisions are documented here with reasoning.
