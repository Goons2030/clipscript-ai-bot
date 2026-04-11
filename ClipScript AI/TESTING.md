# ClipScript AI – Testing Checklist

Before deploying to Render, run through these tests locally.

---

## ✅ Pre-Tests (Setup)

- [ ] Python 3.13+ installed (`python --version`)
- [ ] FFmpeg installed (`ffmpeg -version`) – should show version 8.1+
- [ ] yt-dlp installed (`yt-dlp --version`) – should be 2026.3.17+
- [ ] Virtual environment activated (Windows: `.venv\Scripts\activate` or Linux: `source venv/bin/activate`)
- [ ] Requirements installed (`pip show python-telegram-bot`)
- [ ] .env file created with `BOT_TOKEN` and `DEEPGRAM_API_KEY`
- [ ] temp/ and logs/ directories exist
- [ ] Bot logs appear in `logs/clipscript_bot.log`

---

## ✅ Functional Tests (Local)

Run `python main.py` and send test messages:

### Test 1: Invalid URL
**Send**: `hello world`
**Expected**: "Invalid TikTok URL. Please send a valid link."
**Result**: ✅ / ❌

### Test 2: Valid Short TikTok
**Send**: `https://vm.tiktok.com/abc123xyz` (short link format)
**Expected**: Status message appears: "Downloading...", "Extracting audio...", "Transcribing..."
**Result**: ✅ / ❌

### Test 3: Valid Long TikTok
**Send**: `https://www.tiktok.com/@username/video/1234567890`
**Expected**: Same as Test 2 (both formats work)
**Result**: ✅ / ❌

### Test 4: Transcript Received
After sending valid link, wait 5–30 seconds.
**Expected**: Full transcript text appears in chat
**Result**: ✅ / ❌

### Test 5: Check Request ID in Logs
**Action**: Open `logs/clipscript_bot.log` while test is running
**Expected**: See format: `[abc12def] 2024-01-15 10:30:45 - INFO - Processing TikTok...`
**Result**: ✅ / ❌

### Test 6: Long TikTok (5+ minutes)
Send a longer video
**Expected**: Handles gracefully without timeout (120s limit per download, 60s per transcribe)
**Result**: ✅ / ❌

### Test 7: /start Command
**Send**: `/start`
**Expected**: Welcome message with instructions
**Result**: ✅ / ❌

### Test 8: Network Error Handling
Stop internet, send a TikTok link
**Expected**: "Download failed. Try a different video." (graceful error, no crash)
**Result**: ✅ / ❌

### Test 9: Invalid API Key
Change `DEEPGRAM_API_KEY` in .env to garbage
**Send**: Valid TikTok link
**Expected**: "Transcription failed. Check logs." (graceful error, bot keeps running)
**Result**: ✅ / ❌
(Remember to fix .env after this test!)


---

## ✅ Code Quality Checks

### Logging
Run bot and check if logs appear in `logs/clipscript_bot.log`:
- Request start: `[abc12def] New request started`
- Download: `[abc12def] Starting download...`
- Extract: `[abc12def] Extracting audio...`
- Transcribe: `[abc12def] Transcribing with Deepgram...`
- Success: `[abc12def] Success: 450 characters transcribed`
- Error: `[abc12def] Error occurred: ...`

**Result**: ✅ / ❌

### Cleanup
After each transcript:
1. Check `temp/` directory
2. Should be EMPTY (no leftover .mp4 or .mp3 files)
3. Check `logs/clipscript_bot.log` – should show `[cleanup] Removed: temp/...`

**Result**: ✅ / ❌

### Error Messages (No Crashes)
Test these scenarios - bot should NOT crash:
- Malformed URL → clear error message
- Timeout → graceful message
- API error → graceful message
- Invalid video → graceful message
(Should never see Python tracebacks)

**Result**: ✅ / ❌

### Multi-Request Handling
**Test**: Send 3 TikTok links rapidly (within 5 seconds)
**Expected**: 
- Request 1: `[a1b2c3d4]` starts
- Request 2: `[x9y8z7w6]` waits (queued)
- Request 3: `[p5q4r3s2]` waits (queued)
- Then process sequentially
- All 3 complete successfully

**Result**: ✅ / ❌

---

## ✅ Pre-Deploy Checklist

Before pushing to Render:

- [ ] All functional tests pass
- [ ] Cleanup is working (temp/ empty after each request)
- [ ] Logs are clean (no unhandled exceptions)
- [ ] .env is in .gitignore (not pushed)
- [ ] render.yaml is in repo root with FFmpeg install
- [ ] requirements.txt has correct versions (python-telegram-bot==22.7, yt-dlp==2026.3.17)
- [ ] No hardcoded secrets in main.py
- [ ] `.env.example` has placeholders for users to fill in
- [ ] Multi-request test passes (3+ links sent rapidly)

---

## ✅ Render Deployment Tests

After deploying to Render:

### Test 1: Bot Responds
**Send**: `/start` to bot
**Expected**: Welcome message
**Result**: ✅ / ❌

### Test 2: Real Transcription
**Send**: Valid TikTok link
**Expected**: Transcript (3–30 sec delay on first deployment due to Render startup)
**Result**: ✅ / ❌

### Test 3: Check Render Logs
Go to Render dashboard → Service → Logs
**Expected**: 
- See build output: "Installing ffmpeg...", "Installing packages..."
- See startup: "Bot initialized", "Starting polling..."
- No ERROR lines (INFO and warnings are OK)

**Result**: ✅ / ❌

### Test 4: Test Error Handling
**Send**: Random text
**Expected**: Error message (not crash)
**Result**: ✅ / ❌

### Test 5: Multi-Request (Render)
**Send**: 3 TikTok links within 5 seconds
**Expected**: All process sequentially, all succeed
**Result**: ✅ / ❌

---

## 🐛 If Something Fails

### Bot doesn't respond
1. Check Render logs for "ERROR"
2. Verify BOT_TOKEN in Render Environment
3. Verify service is running (green status, not crashed)
4. Try restarting service

### Transcription fails
1. Check DEEPGRAM_API_KEY in Render Environment
2. Verify key is valid (check at https://console.deepgram.com)
3. Check Render logs for API errors ("403 Forbidden", "invalid key", etc.)
4. Regenerate key if expired

### FFmpeg not found
1. Verify `render.yaml` has FFmpeg install: `apt-get install -y ffmpeg`
2. Check Render build logs (Logs tab, scroll to build section)
3. If missing, delete service and redeploy from scratch

### Download hangs / timeout
1. Video might be 30+ minutes or slow network
2. Check Render logs for timeout errors
3. Increase timeout in code (currently 120s for download, 60s for transcribe)
4. Redeploy

### Service keeps restarting
1. Check Logs tab for errors
2. Common: Missing Deepgram API key
3. Common: FFmpeg not installed
4. Common: Bot token invalid
5. Fix environment variables and redeploy

---

## ✅ All Tests Passed?

**Congrats!** Your ClipScript AI is production-ready.

**Next Steps:**
1. Share bot link with users: `https://t.me/your_bot_name`
2. Monitor performance in Render logs
3. Gather user feedback
4. Iterate and improve
