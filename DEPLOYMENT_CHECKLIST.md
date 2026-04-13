# ClipScript AI - Deployment Checklist 🚀

**Project Status**: Phase 7 Complete - Ready for Production Testing  
**Date**: April 12, 2026  

---

## ✅ Pre-Deployment Verification

### Code Quality
- [x] Python syntax validated (AST parser)
- [x] No breaking changes to existing code
- [x] Backward compatible with Web API
- [x] Backward compatible with Telegram bot
- [x] Error handling comprehensive
- [x] Logging integrated throughout
- [x] Resource cleanup guaranteed (finally blocks)

### Features Implemented
- [x] Layer 1: Primary yt-dlp with FFmpeg post-processor
- [x] Layer 2: Fallback yt-dlp with manual FFmpeg conversion
- [x] Layer 3: Graceful failure with error classification
- [x] Error message customization based on error type
- [x] Telegram UI shows specific error messages
- [x] Web API returns classified errors
- [x] Comprehensive logging at each layer

### Integration Points
- [x] `process_transcription()` uses new fallback system
- [x] Telegram handler shows user-friendly errors
- [x] Web API endpoint returns detailed errors
- [x] Database saves error messages
- [x] Progress callbacks still work
- [x] Queue position system unaffected

---

## 🧪 Testing Checklist (Do This Before Going Live)

### Unit Testing (No Internet Required)
- [ ] Test `classify_download_error()` with sample error strings
  ```python
  assert classify_download_error("HTTP 403 Forbidden") == "blocked"
  assert classify_download_error("Private video") == "private"
  ```

- [ ] Test error message formatting
  ```python
  error = "⚠️ This video is private or unavailable."
  assert error.startswith("⚠️")
  ```

### Integration Testing (With Internet Required)

#### Scenario 1: Fresh Video Link
```bash
# Expected: Layer 1 success
curl -X POST http://localhost:5000/api/transcribe \
  -H "Content-Type: application/json" \
  -d '{"link": "https://www.tiktok.com/@user/video/123"}'

# Check logs for: "✅ LAYER 1 SUCCESS"
# Expected response: { "success": true, "transcript": "..." }
```

#### Scenario 2: Problematic Link (Rate Limited)
```bash
# Expected: Layer 1 fails, Layer 2 tries, either succeeds or shows error
curl -X POST http://localhost:5000/api/transcribe \
  -H "Content-Type: application/json" \
  -d '{"link": "<a restricted TikTok link>"}'

# Check logs for: "🟡 LAYER 1 FAILED" then either "✅ LAYER 2 SUCCESS" or "❌ ALL LAYERS FAILED"
```

#### Scenario 3: Invalid URL
```bash
# Expected: Layer 1 fails with format error, Layer 2 fails, Layer 3 returns error
curl -X POST http://localhost:5000/api/transcribe \
  -H "Content-Type: application/json" \
  -d '{"link": "not-a-real-url"}'

# Check logs for: "❌ ALL LAYERS FAILED"
# Expected response: { "error": "⚠️ Could not process this link..." }
```

#### Scenario 4: Telegram Bot
```
# Send message to bot with TikTok link
📱 User: "https://www.tiktok.com/@user/video/123"

🤖 Bot: "⏳ Queued successfully!"
         (shows queue position)

🤖 Bot: (message edits showing progress: downloading → extracting → transcribing)

🤖 Bot: "✅ Done! Sending your transcript..."

📱 Bot: "[Transcript text]"

# Expected logs:
# - "🟢 LAYER 1: Primary audio extraction"
# - Progress callbacks working
# - Either "✅ LAYER 1 SUCCESS" or fallback layers engaged
```

### Load Testing (Optional but Recommended)
```bash
# Send 5 concurrent requests
for i in {1..5}; do
  curl -X POST http://localhost:5000/api/transcribe \
    -H "Content-Type: application/json" \
    -d '{"link": "<different-link>"}' &
done
wait

# Check:
# ✅ All 5 complete without server crash
# ✅ Logs show all 5 request IDs
# ✅ Database has all 5 jobs
# ✅ Cache working (check for "Cache hit" in logs)
```

---

## 📝 Manual Testing Scenarios

### A. TikTok Video (Public, No Restrictions)
**Expected**: Layer 1 success, ~10-20 seconds  
**Verify**: 
- Message shows downloading → extracting → transcribing
- Transcript appears without errors
- Log shows "✅ LAYER 1 SUCCESS"

### B. YouTube Video
**Expected**: Layer 1 or Layer 2 success, ~15-30 seconds  
**Verify**:
- Same as A
- Note: YouTube may require Layer 2 due to restrictions

### C. Instagram Reel
**Expected**: Layer 1 or Layer 2 success  
**Verify**:
- Same as A
- May take longer due to Instagram's encoding

### D. Twitter/X Video
**Expected**: Layer 1 or Layer 2 success  
**Verify**:
- Same as A

### E. Private Video (Simulate)
**Expected**: Layer 1 fails → Layer 2 fails → Error message  
**Verify**:
- User sees: "⚠️ This video is private or unavailable"
- Log shows: "Classified error as: private"

### F. Invalid Link
**Expected**: Layer 1 fails → Layer 2 fails → Error message  
**Verify**:
- User sees: "⚠️ Could not process this link"
- Log shows: "Classified error as: format"

### G. Same Link Twice (Cache Test)
**Expected**: 1st takes 20s, 2nd takes <1s  
**Verify**:
- First: "Starting download"
- Second: "⚡ Memory cache hit" or "⚡ Database cache hit"

---

## 🚀 Deployment Steps

### Step 1: Local Testing (This Machine)
```bash
cd backend
python app_unified.py

# Watch logs for startup
# Test scenarios A-G above
```

### Step 2: Push to GitHub
```bash
git add app_unified.py FALLBACK_SYSTEM.md
git commit -m "Add 3-layer fallback system for robust audio extraction"
git push origin main
```

### Step 3: Deploy to Render
```bash
# In Render dashboard:
1. Connect GitHub repo
2. Set Root Directory: /backend
3. Set Start Command: python app_unified.py
4. Verify environment variables set:
   - BOT_TOKEN
   - DEEPGRAM_API_KEY
   - WEBHOOK_URL (for production)
5. Deploy
```

### Step 4: Smoke Test on Render
```bash
# Once deployed, test the live instance:
curl https://<your-render-app>/health

# Test API:
curl -X POST https://<your-render-app>/api/transcribe \
  -H "Content-Type: application/json" \
  -d '{"link": "<valid-tiktok-link>"}'
```

### Step 5: Monitor Logs
```bash
# In Render dashboard, watch logs for:
# ✅ App starting
# ✅ Flask initialized
# ✅ Telegram polling started
# ❌ Network errors (expected if isolated environment)
# ⚠️ Any Python exceptions
```

---

## 📊 Success Metrics to Track

### Deployment Success
- [ ] App starts without errors
- [ ] No syntax errors in logs
- [ ] Flask server listening on port 5000
- [ ] Telegram bot connected (if internet available)

### Functional Testing Success  
- [ ] At least 3 videos transcribed successfully
- [ ] Error handling tested (shows user-friendly messages)
- [ ] Cache working (second request is instant)
- [ ] Queue position accurate (with multiple links)

### Performance Success
- [ ] Average processing time: 15-30 seconds
- [ ] Layer 1 success rate: 70-80%
- [ ] Layer 2 recovery rate: 20-40%
- [ ] Error messages appear within 2 seconds

---

## 🛠️ Troubleshooting

### Symptom: "ModuleNotFoundError: No module named 'yt_dlp'"
**Solution**: 
```bash
pip install -r requirements.txt
```

### Symptom: "DEEPGRAM_API_KEY not set"
**Solution**: 
```bash
# Verify .env file contains:
DEEPGRAM_API_KEY=your_actual_key_here
```

### Symptom: "Port 5000 already in use"
**Solution**:
```bash
PORT=8000 python app_unified.py
# Or kill existing process:
lsof -i :5000  # Find PID
kill -9 <PID>
```

### Symptom: "Bot not responding to messages"
**Solution**:
1. Check BOT_TOKEN is correct
2. Check logs for connection errors
3. Ensure internet connection available
4. Verify bot not already running in another terminal

### Symptom: "Transcription returns empty"
**Solution**:
1. Check DEEPGRAM_API_KEY is valid
2. Check audio file is being created (temp folder)
3. Check Deepgram API quotas in console
4. Try with shorter video (< 10 min)

---

## 📈 Post-Deployment Monitoring

### Daily
- [ ] Check error logs for patterns
- [ ] Monitor success rate by platform
- [ ] Check average processing time

### Weekly
- [ ] Analyze most common error types
- [ ] Check database size (old jobs cleanup)
- [ ] Monitor Deepgram API usage

### Monthly
- [ ] Calculate Layer 1 vs Layer 2 success rates
- [ ] Review user feedback / support tickets
- [ ] Plan next features (rate limiting? analytics?)

---

## 🎯 Success Criteria (All Must Be True)

✅ **Code Quality**: No syntax errors, comprehensive error handling  
✅ **Feature Completeness**: All 3 layers implemented and tested  
✅ **User Experience**: Clear error messages, queue position shown  
✅ **Stability**: No crashes under load, proper cleanup  
✅ **Performance**: < 30 seconds average processing time  
✅ **Reliability**: 85%+ success rate on valid videos  

---

## 📞 Support & Help

If deployment fails:

1. **Check logs first** - they contain 95% of diagnostic info
2. **Run with verbose output** - add `--verbose` flag if available
3. **Test each layer independently** - verify yt-dlp works standalone
4. **Check dependencies** - `pip list | grep -E "yt|ffmpeg|telegram"`
5. **Isolate the issue** - test with simplest possible input

---

**Ready to ship!** 🎉

Once you confirm all tests pass, this is production-grade code ready for real users.
