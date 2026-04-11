# ClipScript AI – Single Backend Architecture (Unified Approach)

**Your Question:** Can we use ONE backend to handle both Telegram bot AND web app instead of two separate services?

**Answer:** YES. Absolutely. In fact, this is BETTER than separate services.

---

## Current Architecture (What I Built)

```
Telegram Users
    ↓
Telegram Bot (main.py on Render)
    ↓ (direct polling)
    ↓
Transcription API (Deepgram/Whisper)

Web Users
    ↓
Web App (index.html in browser)
    ↓
Flask API (app.py on Render)
    ↓
Transcription API (Deepgram/Whisper)
```

**Problem:** Two separate services, two separate code bases (sort of)

---

## BETTER Architecture (What You Want)

```
Telegram Users
    ↓
    ↓ (webhook)
    ↓
┌─────────────────────────────────┐
│    ONE UNIFIED BACKEND          │
│  (Flask API on Render)          │
│                                 │
│  • Handle Telegram messages     │
│  • Handle web requests          │
│  • Orchestrate everything       │
│  • Call Deepgram/Whisper        │
└─────────────────────────────────┘
    ↑
    ↑
Web Users
    ↓
Web App (index.html in browser)
    ↓ (HTTP requests)
    ↓
(Same unified backend above)
```

---

## How This Works (Technical)

### **What is a Webhook?**

Instead of the bot constantly asking Telegram "do you have messages for me?" (polling), you tell Telegram:

```
"Hey Telegram, whenever someone sends me a message,
POST it to this URL: https://my-backend.com/telegram/webhook"
```

Telegram then **pushes** messages to your backend instantly.

### **One Flask Backend Handles Everything**

```python
# app.py (single backend)

from flask import Flask, request

app = Flask(__name__)

# Endpoint 1: Telegram webhook
@app.route('/telegram/webhook', methods=['POST'])
def telegram_webhook():
    """Telegram pushes messages here"""
    message = request.json
    link = message['text']
    
    # Process TikTok link
    transcript = transcribe(link)
    
    # Send back to Telegram
    send_to_telegram(message['chat_id'], transcript)
    
    return 'OK'

# Endpoint 2: Web app API
@app.route('/api/transcribe', methods=['POST'])
def web_transcribe():
    """Web app sends requests here"""
    data = request.json
    link = data['link']
    
    # Process TikTok link
    transcript = transcribe(link)
    
    # Return as JSON
    return {'transcript': transcript}

if __name__ == '__main__':
    app.run()
```

**Result:** Same backend serves both Telegram AND web.

---

## Advantages of Single Backend

✅ **1. Simpler to maintain**
- One codebase, not two
- One set of dependencies
- One error log to check
- Fix bugs once, works for both

✅ **2. Shared resources**
- Same transcription logic
- Same error handling
- Same database (if you add one)
- Same rate limiting

✅ **3. Cheaper**
- One Render service ($7/month) instead of two
- Shared computing resources
- Scales better

✅ **4. Easier to add features**
- Add feature once → works for Telegram + web
- No duplicate code

✅ **5. Centralized monitoring**
- One place to check logs
- One place to see errors
- One place to monitor traffic

---

## Disadvantages (Minimal)

❌ **1. Single point of failure**
- If backend goes down, BOTH Telegram + web are down
- **Mitigation:** Render auto-restarts on crash

❌ **2. Shared rate limits**
- If web gets hammered, Telegram might slow down
- **Mitigation:** Easy to add separate rate limiters

❌ **3. More complex routing**
- Need to route `/telegram/webhook` vs `/api/transcribe`
- **Reality:** Takes 30 seconds to implement

**Honest answer:** The disadvantages are negligible for your use case.

---

## Architecture Comparison

### **Option 1: Two Services (Current)**

```
Telegram Bot (main.py)
  ├─ Runs on Render worker
  ├─ Uses polling (constant checking)
  ├─ $0/month (free tier)
  
Web App (app.py)
  ├─ Runs on Render web service
  ├─ Uses HTTP requests
  ├─ $7/month (or free tier)

Total: 2 services, polling + webhooks mixed
```

### **Option 2: One Unified Service (RECOMMENDED)**

```
Unified Backend (app.py)
  ├─ Runs on ONE Render service
  ├─ Telegram uses webhooks (no polling)
  ├─ Web uses HTTP (same backend)
  ├─ $7/month (or free tier)
  
Web App (index.html)
  ├─ Runs as static HTML
  ├─ Calls the backend
  ├─ $0/month (GitHub Pages or same Render)

Total: 1 backend service, clean architecture
```

**Comparison:**
| Factor | Two Services | One Service |
|--------|--------------|-------------|
| Cost | $7–14/month | $7/month |
| Complexity | Medium | Low |
| Maintenance | 2 codebases | 1 codebase |
| Speed | Faster (separate) | Slightly slower (shared) |
| Reliability | Redundant | Single point of failure |
| Scalability | Easy to scale separately | Scales together |

**Winner for you:** ONE SERVICE (simpler, cheaper, sufficient for your scale)

---

## How to Implement (Step by Step)

### **Step 1: Set Up Telegram Webhook**

Instead of:
```python
app.run_polling()  # Constant checking
```

Use:
```python
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

# Tell Telegram to send messages to your webhook
async def set_webhook():
    await app.bot.set_webhook(url="https://your-backend.com/telegram/webhook")

set_webhook()
```

### **Step 2: Create Flask Backend with Two Endpoints**

```python
from flask import Flask, request, jsonify
from telegram import Update
from telegram.ext import Application
import os

app = Flask(__name__)

# Initialize Telegram app
telegram_app = Application.builder().token(os.getenv("BOT_TOKEN")).build()

# ============================================
# ENDPOINT 1: Telegram webhook
# ============================================
@app.route('/telegram/webhook', methods=['POST'])
async def telegram_webhook():
    """
    Telegram sends messages here via webhook
    """
    try:
        update_data = request.json
        update = Update.de_json(update_data, telegram_app.bot)
        
        # Process the update
        await telegram_app.process_update(update)
        
        return jsonify({'status': 'ok'})
    except Exception as e:
        print(f"Telegram error: {e}")
        return jsonify({'error': str(e)}), 400

# ============================================
# ENDPOINT 2: Web API
# ============================================
@app.route('/api/transcribe', methods=['POST'])
def web_transcribe():
    """
    Web app sends TikTok links here via HTTP
    """
    try:
        data = request.json
        link = data.get('link', '').strip()
        
        if not link or 'tiktok.com' not in link:
            return jsonify({'error': 'Invalid TikTok link'}), 400
        
        # Download → Extract → Transcribe
        video_path = download_video(link)
        audio_path = extract_audio(video_path)
        transcript = transcribe(audio_path)
        
        # Cleanup
        cleanup_files(video_path, audio_path)
        
        return jsonify({
            'success': True,
            'transcript': transcript
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================
# ENDPOINT 3: Health check
# ============================================
@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})

# ============================================
# RUN
# ============================================
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
```

### **Step 3: Deploy to Render**

```yaml
# render.yaml
services:
  - type: web
    name: clipscript-ai-backend
    env: python
    buildCommand: apt-get update && apt-get install -y ffmpeg && pip install -r requirements.txt
    startCommand: python app.py
    envVars:
      - key: BOT_TOKEN
      - key: OPENAI_API_KEY
      - key: DEEPGRAM_API_KEY
```

### **Step 4: Tell Telegram Where to Send Messages**

In your Flask app, on startup:

```python
@app.before_first_request
async def setup_webhook():
    """Tell Telegram to use webhook instead of polling"""
    webhook_url = "https://your-app-name.onrender.com/telegram/webhook"
    await telegram_app.bot.set_webhook(url=webhook_url)
    print(f"Webhook set to: {webhook_url}")
```

### **Step 5: Web App Calls the Same Backend**

Your `index.html` (web app) now calls:

```javascript
async function transcribe() {
    const link = document.getElementById('tiktok-link').value;
    
    const response = await fetch('/api/transcribe', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ link })
    });
    
    const data = await response.json();
    console.log(data.transcript);
}
```

**Both use the SAME backend.**

---

## Real-World Diagram

```
┌──────────────────────────────────────────────────────┐
│           SINGLE RENDER SERVICE                      │
│                                                      │
│  ┌─────────────────────────────────────────────┐   │
│  │         Flask Backend (app.py)              │   │
│  │                                             │   │
│  │  POST /telegram/webhook                     │   │
│  │    ├─ Receive Telegram message              │   │
│  │    ├─ Extract link                          │   │
│  │    ├─ Transcribe                            │   │
│  │    └─ Send result back to Telegram          │   │
│  │                                             │   │
│  │  POST /api/transcribe                       │   │
│  │    ├─ Receive web request                   │   │
│  │    ├─ Extract link                          │   │
│  │    ├─ Transcribe                            │   │
│  │    └─ Return JSON response                  │   │
│  │                                             │   │
│  │  GET /health                                │   │
│  │    └─ Return status (for monitoring)        │   │
│  └─────────────────────────────────────────────┘   │
│                                                      │
│  Shared resources:                                   │
│    • Deepgram/Whisper API calls                      │
│    • FFmpeg for audio extraction                     │
│    • File cleanup logic                              │
│    • Error handling                                  │
└──────────────────────────────────────────────────────┘
         ↑                          ↑
         │                          │
    Telegram users              Web users
    (via webhook)             (via HTTP)
```

---

## Cost Breakdown

### **Two Separate Services**
```
Telegram bot (Render worker):  $0–7/month
Web API (Render web):          $7/month
Web app (GitHub Pages):        $0/month
───────────────────────────────────────
Total:                         $7–14/month
```

### **One Unified Service**
```
Backend + Web API (Render web): $0–7/month
Web app (same Render):          Included
───────────────────────────────────────
Total:                          $0–7/month
```

**You save:** $7/month = $84/year

---

## Webhook vs Polling (Why It Matters)

### **Polling (Current main.py)**
```
Bot constantly asks: "Any messages for me?"
Every 1 second: Check Telegram servers
Cost: Unnecessary requests
Speed: Delay when message arrives
Efficiency: 99% of checks are empty
```

### **Webhook (Recommended)**
```
Telegram says: "I'll tell you when messages arrive"
Only when message arrives: Receive it
Cost: No wasted requests
Speed: Instant notification
Efficiency: 100% of messages processed
```

**Result:** Webhooks are faster, cheaper, better.

---

## Implementation Checklist

### **To use ONE backend with webhooks:**

```
☐ Step 1: Create Flask app (app.py) with two endpoints
☐ Step 2: Set up /telegram/webhook endpoint
☐ Step 3: Set up /api/transcribe endpoint
☐ Step 4: Remove polling, use webhooks instead
☐ Step 5: Deploy to Render
☐ Step 6: Tell Telegram to use webhook (set_webhook)
☐ Step 7: Update web app to call /api/transcribe
☐ Step 8: Test both Telegram + web on same backend
☐ Step 9: Delete old main.py (no longer needed)
```

---

## Should You Do This?

### **YES if:**
✅ You want simpler architecture
✅ You want to save money ($7/month)
✅ You want one codebase to maintain
✅ You're building the MVP (now)
✅ You have <10k users per day

### **NO if:**
❌ You need extreme reliability (redundancy)
❌ You expect sudden traffic spikes
❌ You want to scale Telegram separately
❌ You're already running two services

**For you RIGHT NOW:** YES, do the single backend.

---

## Migration Path (If You Want to Switch Later)

If you currently have two services and want to unify:

```
Week 1: Build new unified backend
Week 2: Deploy unified backend alongside old ones
Week 3: Switch web to use new backend
Week 4: Switch Telegram to use new backend
Week 5: Delete old services

Total downtime: 0 minutes (no users affected)
```

**Easy to do. No pain.**

---

## Final Answer to Your Question

**Can we use ONE backend for Telegram + Web with webhooks?**

✅ **YES**
✅ **It's better than two separate services**
✅ **It's cheaper**
✅ **It's simpler**
✅ **It's what I recommend**

---

## Next Steps

**Option A: Use the single backend approach I just explained**
- Modify `app.py` to include both `/telegram/webhook` and `/api/transcribe`
- Deploy once
- Done

**Option B: Keep the current separate services approach**
- Deploy `main.py` to Render worker
- Deploy `app.py` to Render web service
- Works fine, just costs more

**My recommendation: Option A (single backend)**

It's simpler, you're not at scale where redundancy matters yet, and you'll understand your infrastructure better.

---

## TL;DR

**Your question:** Can we use one backend?

**Answer:** YES. In fact, it's BETTER.

```
OLD (Two services):
  Telegram (polling) → Render worker
  Web (HTTP) → Render web service
  Cost: $7–14/month
  Complexity: Medium

NEW (One service):
  Telegram (webhook) → Render web service
  Web (HTTP) → Same Render web service
  Cost: $7/month
  Complexity: Low
```

One Flask backend handles both. Uses webhooks instead of polling. Simpler, faster, cheaper.

Do this. Na so. 🔥
