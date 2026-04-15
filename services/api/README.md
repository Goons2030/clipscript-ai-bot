# API Service - ClipScript AI

## Overview

The API Service is the **central hub** of ClipScript AI. It:

- Manages the database (job storage)
- Provides REST endpoints for Bot & Worker
- Handles job queuing
- Returns transcription results

## 🏗️ Architecture

```
Telegram Bot  ──┐
                ├──> API Service (Flask)
Web UI        ──┤         ├─> SQLite/PostgreSQL
                │         ├─> Redis Cache
Worker        ──┘         └─> Job Queue
```

## 🚀 Running

```bash
cd services/api
python app.py

# Output:
# * Running on http://localhost:3000
```

## 📡 Endpoints

### Health
```bash
GET /health
→ { "status": "healthy", "services": {...} }
```

### Transcription
```bash
POST /api/transcribe
{
  "link": "https://www.tiktok.com/...",
  "user_id": "123456"
}
→ { "job_id": "abc123", "success": true }
```

### Job Status
```bash
GET /api/status/{job_id}
→ {
  "status": "queued|processing|completed|failed",
  "result": "transcript text",
  "error": "error message"
}
```

### Get Result
```bash
GET /api/result/{job_id}
→ {
  "transcript": "...",
  "metadata": {...}
}
```

## 🗂️ Files

- `app.py` - Flask application entry point
- `models.py` - SQLAlchemy database models
- `routes.py` - API endpoints
- `database.py` - Database initialization
- `cache.py` - Redis cache (optional)
- `job_queue.py` - Job management

## ⚙️ Configuration

Via `.env`:
```
API_BASE_URL=http://localhost:3000
FLASK_PORT=3000
FLASK_ENV=development
DATABASE_URL=sqlite:///database.db
# or PostgreSQL:
# DATABASE_URL=postgresql://user:pass@localhost/dbname
```

## 💾 Database

### Tables

**jobs** - Stores transcription jobs
```
id (TEXT) - Job ID
user_id (TEXT) - Telegram user ID
link (TEXT) - Video URL
status (TEXT) - queued/processing/completed/failed
transcript (TEXT) - Results
error (TEXT) - Error message
created_at (TIMESTAMP)
updated_at (TIMESTAMP)
```

**metadata** - Video information
```
id (INTEGER PRIMARY KEY)
job_id (TEXT) - Links to jobs
platform (TEXT) - tiktok/youtube/instagram/twitter
title (TEXT) - Video title
author (TEXT) - Creator
duration (INT) - Seconds
```

## 🔄 Job Lifecycle

```
1. Bot sends POST /api/transcribe
   ↓
2. API creates job (status: "queued")
   ↓
3. Worker polls API for jobs
   ↓
4. Worker downloads video, transcribes
   ↓
5. Worker updates API (status: "processing", then "completed")
   ↓
6. Bot polls /api/status/{job_id}
   ↓
7. Bot receives transcript, sends to user
   ↓
8. Job complete ✅
```

## 🛠️ Development

### Run Tests
```bash
pytest test_api.py -v
```

### Database Reset
```python
# In Python REPL
from app import db
db.drop_all()
db.create_all()
```

### View Logs
```bash
# Detailed logs
FLASK_ENV=development python app.py
```

## 📊 Monitoring

### Check Service Health
```bash
curl http://localhost:3000/health
```

### View Active Jobs
```bash
curl http://localhost:3000/api/jobs
```

### Database Stats
```bash
curl http://localhost:3000/api/stats
```

## 🐛 Troubleshooting

### Port Already in Use
```bash
lsof -i :3000  # Find process
kill -9 <PID>  # Kill it
```

### Database Locked
- Reset: `python app.py --reset-db`
- Or delete `database.db` and restart

### Jobs Stuck in Queue
- Check worker is running
- Verify Deepgram API key is valid
- Check worker logs

## 📚 Code Structure

```python
# Minimal Flask app structure
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
db = SQLAlchemy(app)

@app.route('/health')
def health():
    return {"status": "healthy"}

if __name__ == '__main__':
    db.create_all()
    app.run()
```

## 🔒 Security

- Input validation on all endpoints
- Rate limiting (optional)
- CORS enabled for trusted origins only
- No sensitive data in logs

## 📈 Performance

- Database indexes on job_id, user_id, status
- Redis caching for results  
- Connection pooling (SQLAlchemy)
- ~100 requests/sec capacity

## 🚀 Production

For production:
1. Use PostgreSQL (not SQLite)
2. Set `FLASK_ENV=production`
3. Use gunicorn: `gunicorn app:app`
4. Enable HTTPS/SSL
5. Setup monitoring & backups

---

**See:** [ARCHITECTURE.md](../../ARCHITECTURE.md) | [DEPLOYMENT.md](../../DEPLOYMENT.md)
