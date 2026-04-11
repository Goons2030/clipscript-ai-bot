# ClipScript AI - Logging & Debugging Guide

## 📋 Log Files Location

All bot logs are saved to: **`ClipScript AI/logs/clipscript_bot.log`**

## 🔍 View Logs

### Option 1: Using Python Script (Recommended)
```powershell
cd "ClipScript AI"
python view_logs.py           # Show last 50 entries + statistics
python view_logs.py tail      # Show last 20 entries only
```

### Option 2: View File Directly
```powershell
# Open in default text editor
notepad "logs/clipscript_bot.log"

# Or stream live (PowerShell)
Get-Content "logs/clipscript_bot.log" -Tail 20 -Wait
```

### Option 3: Open in VS Code
```powershell
code "logs/clipscript_bot.log"
```

---

## 📊 Understanding Log Entries

### ✅ Good Signs
```
INFO - Bot running. Waiting for messages...
INFO - HTTP Request: POST https://api.telegram.org/bot.../getUpdates "HTTP/1.1 200 OK"
INFO - Starting download for: https://www.tiktok.com/...
INFO - Video downloaded: temp/....mp4
INFO - Audio extracted: temp/....mp3
INFO - Transcription successful: 234 characters
```

### ⚠️ Warnings/Errors to Watch For

#### FFmpeg Missing
```
ERROR - Audio extraction failed: [WinError 2] The system cannot find the file specified
```
**Fix:** Install FFmpeg (see FFMPEG_SETUP.md)

#### Deepgram API Issue
```
ERROR - Deepgram error: 401
```
**Fix:** Check DEEPGRAM_API_KEY in `.env`

#### TikTok Blocked
```
ERROR - Download failed: 403 Forbidden
```
**Fix:** Try a different link or wait 5 minutes

#### Network Error
```
ERROR - Download failed: timeout after retries
```
**Fix:** Check internet connection

---

## 🔧 Real-Time Debugging

### Run Bot with Live Log View
**Terminal 1 - Run Bot:**
```powershell
cd "ClipScript AI"
python main.py
```

**Terminal 2 - Watch Logs:**
```powershell
cd "ClipScript AI"
python view_logs.py tail    # Updates every time script is run
```

Or keep a PowerShell window open:
```powershell
Get-Content "ClipScript AI/logs/clipscript_bot.log" -Tail 10 -Wait
```

---

## 📈 Log Statistics

Running `python view_logs.py` shows:
```
📈 Statistics:
  ✅ INFO:    45
  ⚠️  WARNING: 2
  ❌ ERROR:   3
```

- **INFO count**: Total successful events
- **WARNING count**: Non-critical issues
- **ERROR count**: Problems that need fixing

---

## 🗑️ Clear Old Logs

```powershell
# Backup current log
Copy-Item "ClipScript AI/logs/clipscript_bot.log" "ClipScript AI/logs/clipscript_bot.backup.log"

# Clear log file (bot will recreate on next run)
Clear-Content "ClipScript AI/logs/clipscript_bot.log"
```

---

## 💡 Best Practices

1. **Check logs after each test** - Use `python view_logs.py`
2. **Look for ERROR entries** - These show what went wrong
3. **Search for specific issues** - Use Ctrl+F to find keywords:
   - "failed" - failed operations
   - "timeout" - network/timeout issues
   - "missing" - missing files/modules
   - "401/403" - API authorization issues
4. **Keep backup logs** - Export important debugging sessions

---

## 🚀 Quick Start

**Step 1: Start the bot**
```powershell
cd "ClipScript AI"
python main.py
```

**Step 2: Send test TikTok link in Telegram**

**Step 3: Check logs**
```powershell
python view_logs.py
```

**Step 4: Debug any errors found**

---

## 📞 Troubleshooting Checklist

| Issue | How to Check Logs | Fix |
|-------|------------------|-----|
| Bot won't start | Look for Python errors | Check imports in logs |
| No messages received | Check for "getUpdates 200 OK" | Verify BOT_TOKEN |
| Download fails | Look for "Download failed" | Check internet/TikTok link |
| FFmpeg error | Search for "system cannot find" | Install FFmpeg |
| Deepgram fails | Look for "401" or "Deepgram error" | Check API key |
| Message edit fails | Look for "Message is not modified" | Code issue (already fixed) |

---

**Questions? Check the logs first!** 🔍
