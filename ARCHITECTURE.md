# ClipScript AI - Architecture Guide

## 🏗️ System Overview

ClipScript AI Bot is a **distributed, microservices-based video transcription platform** with separate services for API management, Telegram bot, and background job processing.

```
┌─────────────────────────────────────────────────────────────┐
│                    USER INTERFACES                          │
├─────────────────────────────────────────────────────────────┤
│  Telegram Bot         │     Web UI (Flask)                  │
│  (Polling/Webhook)    │     http://localhost:5000           │
└──────────┬────────────┴───────────────────┬──────────────────┘
           │                               │
           └───────────────┬───────────────┘
                          │
                ┌─────────▼─────────┐
                │   API SERVICE     │
                │   (Flask + DB)    │
                │   :3000           │
                └─────────┬─────────┘
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
   ┌────▼──────┐   ┌─────▼────┐    ┌──────▼───┐
   │  Database │   │   Cache  │    │ Job Queue│
   │ (SQLite/  │   │  (Redis) │    │          │
   │ PostgreSQL│   │          │    │          │
   └───────────┘   └──────────┘    └──────────┘
        │
   ┌────▼──────────────────────┐
   │  BACKGROUND WORKER        │
   │  (Multi-threaded)         │
   │  - Download videos        │
   │  - Transcribe (Deepgram)  │
   │  - Save results           │
   └───────────────────────────┘
```

---

## 📦 Folder Structure

```
ClipScript AI bot/
├── services/
│   ├── api/
│   │   ├── app.py                 # Flask API server
│   │   ├── models.py              # Database models
│   │   ├── routes.py              # API endpoints
│   │   ├── database.py            # Database setup
│   │   ├── cache.py               # Redis cache
│   │   └── job_queue.py           # Job management
│   │
│   ├── bot/
│   │   ├── telegram_bot.py        # Telegram bot service
│   │   └── handlers.py            # Message handlers
│   │
│   ├── worker/
│   │   ├── worker.py              # Background job processor
│   │   ├── transcriber.py         # Deepgram integration
│   │   └── downloader.py          # Video downloader
│   │
│   └── shared/
│       ├── config.py              # Configuration (env vars)
│       ├── client.py              # HTTP client for services
│       └── utils.py               # Shared utilities
│
├── main.py                        # Run all services
├── requirements.txt               # Python dependencies
├── .env                           # Environment variables (GITIGNORED)
└── README.md                      # Usage guide
```

---

## 🔄 Service Communication

### Without Shared Asyncio

**Key Principle:** Each service has its own event loop. They communicate via HTTP/REST only.

```
┌─────────────────────┐              ┌────────────────────┐
│  Telegram Bot       │── HTTP POST──>│  API Service       │
│  (asyncio)          │<── JSON────────│  (Flask + DB)      │
│                     │               │                    │
│ - Receives messages │  HTTP GET───> │ - Stores jobs      │
│ - Sends to API      │<──JSON────────│ - Queries status   │
│ - Polls for results │               │ - Updates results  │
└─────────────────────┘               └────────────────────┘
                                              │
                                              │ Job Queue
                                              ▼
                                     ┌────────────────────┐
                                     │  Background Worker │
                                     │  (Threading)       │
                                     │                    │
                                     │ - Pulls jobs       │
                                     │ - Downloads videos │
                                     │ - Transcribes      │
                                     │ - Updates DB       │
                                     └────────────────────┘
```

### API Endpoints (Service-to-Service)

```
POST /api/transcribe
├─ Input: { "link": "url", "user_id": "123" }
└─ Returns: { "job_id": "abc123", "success": true }

GET /api/status/{job_id}
├─ Returns: { 
│    "status": "queued|processing|completed|failed",
│    "result": "transcript text",
│    "error": "error message"
├─ }

GET /health
└─ Returns: { "status": "healthy", "services": {...} }

GET /api/result/{job_id}
└─ Returns: { "transcript": "...", "metadata": {...} }
```

---

## 🚀 Running Each Service

### 1. API Service (Required First)

```bash
cd services/api
python app.py
# Runs on http://localhost:3000
# - Provides REST API
# - Manages database
# - Queues jobs
```

### 2. Background Worker (Concurrent)

```bash
cd services/worker
python worker.py
# - Polls job queue
# - Downloads videos
# - Calls Deepgram
# - Updates job status
```

### 3. Telegram Bot (Concurrent)

```bash
cd services/bot
python telegram_bot.py
# - Polls for messages
# - Sends jobs to API
# - Polls API for results
# - Sends messages to users
```

### Or All At Once

```bash
python main.py  # (from project root)
```

---

## 🔐 Environment Variables

Create `.env` in project root:

```env
# Bot
BOT_TOKEN=<telegram_bot_token>
TELEGRAM_WEBHOOK_URL=https://your-domain.com/webhook
ENABLE_TELEGRAM_WEBHOOK=false

# API
API_BASE_URL=http://localhost:3000
FLASK_PORT=3000
FLASK_ENV=development

# Database
DB_PATH=./database.db
DATABASE_URL=sqlite:///database.db
# OR PostgreSQL:
# DATABASE_URL=postgresql://user:pass@localhost/dbname

# Cache (Redis - optional)
REDIS_URL=redis://localhost:6379

# Deepgram
DEEPGRAM_API_KEY=<your_key>

# Other
LOG_LEVEL=INFO
```

---

## 💾 Database Schema

### Jobs Table
```sql
CREATE TABLE jobs (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    link TEXT NOT NULL,
    status TEXT DEFAULT 'queued',  -- queued, downloading, processing, completed, failed
    transcript TEXT,
    error TEXT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

### Metadata Table
```sql
CREATE TABLE metadata (
    id INTEGER PRIMARY KEY,
    job_id TEXT NOT NULL,
    platform TEXT,  -- tiktok, youtube, instagram, twitter
    title TEXT,
    author TEXT,
    duration INT,
    FOREIGN KEY(job_id) REFERENCES jobs(id)
);
```

---

## ⚠️ Critical Design Decisions

### 1. **No Shared Asyncio**
Each service has its own event loop:
- **Telegram Bot**: `asyncio.run()`
- **API Service**: Flask (synchronous with thread pool)
- **Background Worker**: Threading for I/O operations
- **Service Communication**: HTTP REST (JSON)

**Reason:** Prevents asyncio conflicts, simplifies deployment, easier debugging.

### 2. **API-First Architecture**
- Bot doesn't store jobs internally
- Worker doesn't handle HTTP requests
- All state managed by API service + database

**Reason:** Single source of truth, easier recovery, better scalability.

### 3. **Job Queue**
- Simple in-memory or database queue
- Worker polls API for jobs
- Updates status via API calls

**Reason:** Decouples services, enables multiple workers, survives restarts.

### 4. **No Direct Bot-to-Worker Communication**
Bot and Worker don't know about each other:
- Bot → API Service →  Job Queue  
- Worker ← API Service ← Job Queue

**Reason:** Services are independent, can restart without affecting others.

---

## 🛠️ Adding New Features

### Add a New Endpoint

1. **API** (`services/api/routes.py`):
   ```python
   @app.route('/api/new-feature', methods=['POST'])
   def new_feature():
       data = request.json
       # Process
       return jsonify({"success": True})
   ```

2. **Bot** (`services/bot/telegram_bot.py`):
   ```python
   result = api_client.post('/api/new-feature', {...})
   ```

3. **Worker** (calls existing API endpoints):
   No changes needed if using existing endpoints.

### Add a New Processing Step

1. **Worker** (`services/worker/worker.py`):
   ```python
   def process_job(job):
       # Add new step
       # Update status via API
       api_client.put(f'/api/jobs/{job_id}', {...})
   ```

2. **API** (if needed) - add endpoint to update job.

---

## 📊 Monitoring & Debugging

### Health Checks
```bash
curl http://localhost:3000/health
```

### View Job Status
```bash
curl http://localhost:3000/api/status/{job_id}
```

### View Logs
- **API**: `services/api/app.py` logs
- **Worker**: `services/worker/worker.py` logs
- **Bot**: `services/bot/telegram_bot.py` logs

---

## 🚀 Production Deployment

### Render.com
See `RENDER_DEPLOY.md` for specific instructions.

### General Steps
1. Set environment variables
2. Start API service
3. Start worker(s)
4. Start bot service
5. Monitor health endpoints

### Scaling
- **Multiple Workers**: Spin up multiple worker processes
- **Load Balancing**: Use reverse proxy for API service
- **Database Replication**: Use PostgreSQL for durability
- **Redis Cache**: Optional for performance

---

## 🐛 Troubleshooting

### "API unavailable"
- Check `API_BASE_URL` in `.env`
- Verify API service is running
- Check network connectivity

### "Telegram messages not received"
- Verify `BOT_TOKEN` is correct
- Check Telegram bot [@BotFather](https://t.me/BotFather) settings
- View logs for errors

### "Jobs stuck in queue"
- Verify worker is running
- Check worker logs for errors
- Verify Deepgram API key is valid

### "Transcription poor quality"
- Check video is accessible
- Verify Deepgram language model selected
- Check video audio quality

---

## 📝 Version Control

**.gitignore** should include:
```
.env
*.pyc
__pycache__/
.DS_Store
database.db
.sqlite
venv/
*.log
```

---

## 🔄 Maintenance

### Database Cleanup
```python
# In services/api/routes.py
@app.route('/api/clean', methods=['POST'])
def cleanup():
    # Delete old jobs
    pass
```

### Backup Database
```bash
cp database.db database.db.backup
```

### Update Dependencies
```bash
pip install --upgrade -r requirements.txt
```

---

## 📞 Support

For issues:
1. Check logs in each service
2. Verify `.env` configuration
3. Test API endpoints manually
4. Review database state

