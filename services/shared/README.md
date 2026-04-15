# Shared Services - ClipScript AI

## Overview

The `shared/` folder contains utilities and configuration used by all services:

- Environment configuration (loading `.env`)
- HTTP client for inter-service communication
- Shared utilities and helpers

## 📁 Files

### `config.py` - Configuration Manager

Loads environment variables from `.env` and provides them to all services.

```python
from shared.config import BOT_TOKEN, API_BASE_URL, DEEPGRAM_API_KEY

# Values are automatically loaded from .env
print(f"API: {API_BASE_URL}")
print(f"Bot: {BOT_TOKEN[:20]}...")  # Don't print full token!
```

**Variables loaded:**

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `BOT_TOKEN` | Telegram bot token | None | ✅ |
| `API_BASE_URL` | API service URL | http://localhost:3000 | ✅ |
| `DEEPGRAM_API_KEY` | Deepgram transcription API | None | ✅ |
| `DATABASE_URL` | Database connection | sqlite:///database.db | ❌ |
| `FLASK_PORT` | API port | 3000 | ❌ |
| `FLASK_ENV` | Environment | development | ❌ |
| `LOG_LEVEL` | Logging level | INFO | ❌ |

### `client.py` - Service Client

HTTP client for services to communicate with API.

```python
from shared.client import ServiceClient

client = ServiceClient("http://localhost:3000")

# GET request
status = client.get("/api/status/job_id")

# POST request
result = client.post("/api/transcribe", {
    "link": "https://...",
    "user_id": "123"
})

# PUT request
updated = client.put("/api/jobs/job_id", {"status": "completed"})
```

**Methods:**

- `get(endpoint)` - GET request
- `post(endpoint, data)` - POST request with JSON
- `put(endpoint, data)` - PUT request with JSON
- `delete(endpoint)` - DELETE request

**Error Handling:**

```python
result = client.post("/api/transcribe", {...})

if not result:
    print("API error or network issue")
elif not result.get("success"):
    error = result.get("error")
    print(f"API returned error: {error}")
else:
    job_id = result.get("job_id")
    print(f"Success: {job_id}")
```

### `utils.py` - Shared Utilities

Common functions used across services.

```python
from shared.utils import (
    generate_job_id,
    validate_url,
    format_transcript,
    get_platform
)

# Generate unique job ID
job_id = generate_job_id()
# → "job_1234567890"

# Validate URL format
if validate_url("https://www.tiktok.com/..."):
    print("Valid URL")

# Format transcript (remove extra spaces, etc)
clean = format_transcript(raw_transcript)

# Detect platform from URL
platform = get_platform("https://www.tiktok.com/...")
# → "tiktok"
```

## 🔄 Usage Examples

### In Bot Service

```python
from shared.config import API_BASE_URL
from shared.client import ServiceClient

api_client = ServiceClient(API_BASE_URL)

# Send transcription request
result = api_client.post("/api/transcribe", {
    "link": user_message,
    "user_id": user_id
})

if result and result.get("success"):
    job_id = result["job_id"]
    # Poll for result...
else:
    print("Error:", result.get("error"))
```

### In Worker Service

```python
from shared.config import API_BASE_URL, DEEPGRAM_API_KEY
from shared.client import ServiceClient

api_client = ServiceClient(API_BASE_URL)

# Get pending jobs
jobs = api_client.get("/api/jobs?status=queued")

for job in jobs:
    # Process job...
    
    # Update status
    api_client.put(f"/api/jobs/{job['id']}", {
        "status": "processing"
    })
    
    # After transcription...
    api_client.put(f"/api/jobs/{job['id']}", {
        "status": "completed",
        "transcript": transcript_text
    })
```

### In API Service

```python
# No need to use ServiceClient in API service
# API manages database directly

from flask import request, jsonify
from services.api.models import Job

@app.route('/api/transcribe', methods=['POST'])
def transcribe():
    data = request.json
    
    # Create job
    job = Job(
        user_id=data['user_id'],
        link=data['link'],
        status='queued'
    )
    db.session.add(job)
    db.session.commit()
    
    return jsonify({
        "success": True,
        "job_id": job.id
    })
```

## 🔧 Extending Shared Utilities

### Adding New Config Variable

In `config.py`:
```python
import os
from dotenv import load_dotenv

load_dotenv()

# Existing variables...
NEW_VAR = os.getenv('NEW_VAR', 'default_value')
```

Then in `.env`:
```
NEW_VAR=my_value
```

Usage anywhere:
```python
from shared.config import NEW_VAR
```

### Adding New Client Method

In `client.py`:
```python
class ServiceClient:
    def patch(self, endpoint: str, data: dict = None):
        """PATCH request"""
        try:
            response = requests.patch(
                f"{self.base_url}{endpoint}",
                json=data,
                timeout=10
            )
            return response.json() if response.ok else None
        except Exception as e:
            logger.error(f"PATCH error: {e}")
            return None
```

### Adding New Utility Function

In `utils.py`:
```python
def my_function(param):
    """Do something useful"""
    # Implementation
    return result

# In other services:
from shared.utils import my_function
result = my_function(param)
```

## 📊 Logging

All services use Python's `logging` module with shared configuration.

```python
import logging

logger = logging.getLogger(__name__)

logger.info("Info message")      # Blue, normal info
logger.warning("Warning")        # Yellow, warnings
logger.error("Error occurred")   # Red, errors
logger.debug("Debug info")       # Gray, detailed debug (only with DEBUG level)
```

Configure in `.env`:
```
LOG_LEVEL=INFO  # INFO, DEBUG, WARNING, ERROR
```

## 🔐 Security Notes

**In `config.py`:**
- Never print secret tokens
- Use `os.getenv()` with defaults, never allow empty

```python
# ✅ Good
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN must be set in .env")

# ❌ Bad
BOT_TOKEN = os.getenv('BOT_TOKEN', 'default_token')  # Insecure!
```

**In `client.py`:**
- Never log request bodies (contains API keys)
- Don't expose API errors to clients
- Use timeouts to prevent hanging

**In `utils.py`:**
- Validate all inputs
- Don't store sensitive data in memory longer than needed

## 📚 Related Files

See also:
- [services/api/README.md](../api/README.md) - API documentation
- [services/bot/README.md](../bot/README.md) - Bot documentation
- [services/worker/README.md](../worker/README.md) - Worker documentation

---

**See:** [ARCHITECTURE.md](../../ARCHITECTURE.md)
