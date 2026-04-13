# 🔧 API Integration Testing Guide

**Purpose**: Verify that the Flask backend returns JSON for all endpoints and the frontend correctly detects the API environment

---

## ✅ Quick Testing Checklist

### Local Testing (http://127.0.0.1:5000)

```bash
# 1. Test the health endpoint
curl http://127.0.0.1:5000/health

# Expected response (JSON):
{
    "status": "ok",
    "service": "ClipScript AI Unified Backend",
    "transcription_service": "deepgram"
}
```

```bash
# 2. Test the new test endpoint
curl http://127.0.0.1:5000/test

# Expected response (JSON):
{
    "status": "ok",
    "message": "API is working correctly",
    "timestamp": 1712973154.6234,
    "environment": "development"
}
```

```bash
# 3. Test the API transcribe endpoint with OPTIONS (CORS preflight)
curl -X OPTIONS http://127.0.0.1:5000/api/transcribe

# Expected response (JSON):
{"status":"ok"}
```

---

## 🌐 Testing via Browser

### Step 1: Local Development
1. Navigate to `http://127.0.0.1:5000` in your browser
2. Open **Developer Console** (F12 → Console tab)
3. Look for these logs:
   - `🚀 API BASE: http://127.0.0.1:5000` ✅
   - `🌐 Hostname: 127.0.0.1` ✅

4. Paste a TikTok link and click "Transcribe"
5. Check console for logs:
   - `📡 Calling: http://127.0.0.1:5000/api/transcribe` ✅
   - `📦 Raw Response: {...}` ✅

### Step 2: Production (Vercel Frontend)
1. Navigate to your Vercel frontend URL
2. Open **Developer Console** (F12 → Console tab)
3. Look for these logs:
   - `🚀 API BASE: https://clipscript-ai-bot-production.up.railway.app` ✅
   - `🌐 Hostname: your-vercel-domain.vercel.app` ✅

4. Paste a TikTok link and click "Transcribe"
5. Check console for logs:
   - `📡 Calling: https://clipscript-ai-bot-production.up.railway.app/api/transcribe` ✅
   - `📦 Raw Response: {...}` ✅

---

## 🐛 Debugging JSON Errors

### If you see: "Unexpected token 'T', 'The page c...' is not valid JSON"

This means the backend returned HTML instead of JSON. 

**Steps to debug:**
1. Open **Developer Console** (F12)
2. In the Console, look for:
   ```
   ❌ JSON Parse Error
   📄 Raw response was: <!DOCTYPE html>...
   ```

3. This shows the backend is returning HTML (usually an error page)

**Common causes:**
- ❌ Route returning `send_from_directory()` instead of `jsonify()`
- ❌ The `/api/transcribe` endpoint hitting the Flask error handler
- ❌ CORS headers missing

**Solution:**
- Check that the backend route returns `jsonify()` not HTML
- Verify CORS is enabled: `CORS(app)` should be in backend imports
- Check logs: `backend/logs/clipscript_unified.log`

---

## 📡 Testing Transcribe Endpoint

### Test 1: Valid Request (Local)

```bash
curl -X POST http://127.0.0.1:5000/api/transcribe \
  -H "Content-Type: application/json" \
  -d '{"link":"https://www.tiktok.com/@username/video/123456789"}'
```

**Expected response**:
```json
{
    "success": true,
    "transcript": "Your transcribed text here...",
    "length": 142,
    "cache_hit": false
}
```

### Test 2: Invalid Request (No Link)

```bash
curl -X POST http://127.0.0.1:5000/api/transcribe \
  -H "Content-Type: application/json" \
  -d '{}'
```

**Expected response**:
```json
{
    "success": false,
    "error": "No links provided"
}
```
**Status Code**: `400`

### Test 3: Invalid Link Format

```bash
curl -X POST http://127.0.0.1:5000/api/transcribe \
  -H "Content-Type: application/json" \
  -d '{"link":"not-a-tiktok-url"}'
```

**Expected response**:
```json
{
    "success": false,
    "error": "No valid video links found"
}
```
**Status Code**: `400`

---

## 🔍 API Response Format Guide

### ✅ Successful Single Link Response
```json
{
    "success": true,
    "transcript": "Full transcript text...",
    "length": 1234,
    "cache_hit": false
}
```

### ✅ Successful Multiple Links Response
```json
{
    "success": true,
    "results": [
        {
            "success": true,
            "link": "https://...",
            "transcript": "...",
            "length": 123,
            "cache_hit": false
        }
    ],
    "total": 1,
    "successful": 1
}
```

### ❌ Error Response
```json
{
    "success": false,
    "error": "Error message here"
}
```

---

## 🌍 Environment-Specific Testing

### Local (http://127.0.0.1:5000)
- Backend: Running locally
- Frontend: Served from backend at `localhost:5000`
- API calls: `http://127.0.0.1:5000/api/transcribe` ✅

### Production (Railway + Vercel)
- Backend: `https://clipscript-ai-bot-production.up.railway.app`
- Frontend: `https://your-domain.vercel.app`
- API calls: `https://clipscript-ai-bot-production.up.railway.app/api/transcribe` ✅

### What the frontend does:
```javascript
if (hostname is localhost/127.0.0.1) {
    use: http://127.0.0.1:5000
} else {
    use: https://clipscript-ai-bot-production.up.railway.app
}
```

---

## ✨ Verifying CORS Headers

```bash
curl -i -X OPTIONS http://127.0.0.1:5000/api/transcribe

# Look for these headers in response:
# Access-Control-Allow-Origin: *
# Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS
# Access-Control-Allow-Headers: Content-Type
```

**If missing**, add to backend:
```python
from flask_cors import CORS
CORS(app)  # Enable CORS for all routes
```

---

## 📊 Checking Backend Logs

```bash
cd backend
tail -f logs/clipscript_unified.log

# Look for entries like:
# [API] Request from 127.0.0.1
# [API] Received data: {'link': '...'}
# [API] Completed: 1/1 links
```

---

## ✅ Final Verification Checklist

- [ ] Test `/health` returns JSON locally
- [ ] Test `/test` returns JSON locally
- [ ] Test `/api/transcribe` with valid TikTok link locally
- [ ] Test `/api/transcribe` with invalid input locally
- [ ] Open frontend in browser (local)
- [ ] Console shows correct API_BASE (`http://127.0.0.1:5000`)
- [ ] Transcription works locally
- [ ] Push to production (Railway + Vercel)
- [ ] Open frontend in Vercel URL
- [ ] Console shows correct API_BASE (`https://clipscript-ai-bot-production.up.railway.app`)
- [ ] Transcription works in production

---

## 🎯 Expected Console Logs (Success Case)

**Local**:
```
🚀 API BASE: http://127.0.0.1:5000
🌐 Hostname: 127.0.0.1
📡 Calling: http://127.0.0.1:5000/api/transcribe
📦 Raw Response: {"success":true,"transcript":"...","length":123,"cache_hit":false}
```

**Production**:
```
🚀 API BASE: https://clipscript-ai-bot-production.up.railway.app
🌐 Hostname: your-app.vercel.app
📡 Calling: https://clipscript-ai-bot-production.up.railway.app/api/transcribe
📦 Raw Response: {"success":true,"transcript":"...","length":123,"cache_hit":false}
```

---

## 🚀 Deployment Checklist

Before deploying to production:

1. **Backend (Railway)**
   - [ ] CORS is enabled: `CORS(app)` in imports
   - [ ] `/test` endpoint returns JSON
   - [ ] `/api/transcribe` returns JSON (not HTML)
   - [ ] Environment variables set: `BOT_TOKEN`, `DEEPGRAM_API_KEY`
   - [ ] Logs directory exists and is writable

2. **Frontend (Vercel)**
   - [ ] `API_BASE` correctly detects localhost vs production
   - [ ] Fetch headers include `'Accept': 'application/json'`
   - [ ] Error handling shows raw response if JSON parsing fails
   - [ ] Console logs show correct API endpoints being called

3. **Testing**
   - [ ] Local: http://127.0.0.1:5000 works fully
   - [ ] Production: Frontend + Backend cross-domain works
   - [ ] CORS preflight (OPTIONS) works
   - [ ] Error cases handled gracefully

---

**Need help?** Check the console logs (F12) → Console tab for detailed error messages!
