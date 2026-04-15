# ClipScript AI - Deployment Guide

## 🚀 Quick Start - Local Development

### Prerequisites

- Python 3.9+
- pip or conda
- Git
- Telegram account (for bot testing)
- Deepgram API key (free tier available)

### Step 1: Clone & Setup

```bash
# Clone repository
git clone https://github.com/yourusername/clipscript-ai-bot.git
cd clipscript-ai-bot

# Create virtual environment
python -m venv venv

# Activate venv
# On Windows:
venv\Scripts\activate
# On Mac/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Step 2: Configure Environment

Create `.env` file:

```bash
# Bot
BOT_TOKEN=your_telegram_bot_token_here
TELEGRAM_WEBHOOK_URL=https://your-domain.com/webhook
ENABLE_TELEGRAM_WEBHOOK=false

# API
API_BASE_URL=http://localhost:3000
FLASK_PORT=3000
FLASK_ENV=development

# Database
DATABASE_URL=sqlite:///database.db

# Deepgram
DEEPGRAM_API_KEY=your_deepgram_api_key

# Logging
LOG_LEVEL=INFO
```

**Getting tokens:**
- **Telegram Bot Token**: Message [@BotFather](https://t.me/BotFather) on Telegram, create bot, copy token
- **Deepgram API Key**: Sign up at [console.deepgram.com](https://console.deepgram.com)

### Step 3: Run Services

**Terminal 1 - API Service:**
```bash
cd services/api
python app.py
# Output: "Running on http://localhost:3000"
```

**Terminal 2 - Background Worker:**
```bash
cd services/worker
python worker.py
# Output: "Worker started, polling for jobs..."
```

**Terminal 3 - Telegram Bot:**
```bash
cd services/bot
python telegram_bot.py
# Output: "Starting Telegram polling..."
```

Or run all at once:
```bash
python main.py
```

### Step 4: Test the Bot

1. Open Telegram
2. Search for your bot (from [@BotFather](https://t.me/BotFather) output)
3. Send `/start`
4. Send a TikTok/YouTube/Instagram link
5. Wait for transcription

---

## 🌐 Deployment on Render.com

### Prerequisites

- Render.com account (free tier available)
- GitHub repository with code
- Environment variables configured

### Step 1: Create PostgreSQL Database

1. Go to [render.com](https://render.com)
2. Click "New" → "PostgreSQL"
3. Fill in:
   - **Name**: `clipscript-db`
   - **Region**: Choose closest to you
   - **PostgreSQL Version**: 14+
4. Click "Create Database"
5. Copy connection string (looks like: `postgresql://user:pass@host/db`)

### Step 2: Create API Service

1. Click "New" → "Web Service"
2. Connect your GitHub repository
3. Fill in:
   - **Name**: `clipscript-api`
   - **Region**: Same as database
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `cd services/api && python app.py`
4. Click "Advanced"
5. Add environment variables:
   ```
   DATABASE_URL=<paste_from_step1>
   FLASK_PORT=3000
   FLASK_ENV=production
   DEEPGRAM_API_KEY=<your_key>
   ```
6. Click "Create Web Service"
7. Note the URL (e.g., `https://clipscript-api.onrender.com`)

### Step 3: Create Worker Service

1. Click "New" → "Background Worker"
2. Connect your GitHub repository
3. Fill in:
   - **Name**: `clipscript-worker`
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `cd services/worker && python worker.py`
4. Click "Advanced"
5. Add environment variables:
   ```
   DATABASE_URL=<paste_from_step1>
   API_BASE_URL=https://clipscript-api.onrender.com
   DEEPGRAM_API_KEY=<your_key>
   ```
6. Click "Create Background Worker"

### Step 4: Create Bot Service

1. Click "New" → "Web Service"
2. Connect your GitHub repository
3. Fill in:
   - **Name**: `clipscript-bot`
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `cd services/bot && python telegram_bot.py`
4. Click "Advanced"
5. Add environment variables:
   ```
   BOT_TOKEN=<your_telegram_token>
   API_BASE_URL=https://clipscript-api.onrender.com
   ENABLE_TELEGRAM_WEBHOOK=true
   TELEGRAM_WEBHOOK_URL=https://clipscript-bot.onrender.com/webhook
   ```
6. Click "Create Web Service"

### Step 5: Update Database URL

In all services, change from SQLite to PostgreSQL:

**services/api/database.py:**
```python
# Change from:
# DATABASE_URL = "sqlite:///database.db"

# To (from environment):
DATABASE_URL = os.environ.get("DATABASE_URL")
```

---

## 🔄 Docker Deployment

### Dockerfile for Each Service

**services/api/Dockerfile:**
```dockerfile
FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "-m", "services.api.app"]
```

**services/worker/Dockerfile:**
```dockerfile
FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "-m", "services.worker.worker"]
```

**services/bot/Dockerfile:**
```dockerfile
FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "-m", "services.bot.telegram_bot"]
```

### docker-compose.yml

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:14
    environment:
      POSTGRES_DB: clipscript
      POSTGRES_USER: clipscript
      POSTGRES_PASSWORD: securepassword
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  redis:
    image: redis:7
    ports:
      - "6379:6379"

  api:
    build: ./services/api
    environment:
      - DATABASE_URL=postgresql://clipscript:securepassword@postgres:5432/clipscript
      - REDIS_URL=redis://redis:6379
      - FLASK_PORT=3000
      - DEEPGRAM_API_KEY=${DEEPGRAM_API_KEY}
    ports:
      - "3000:3000"
    depends_on:
      - postgres
      - redis
    restart: unless-stopped

  worker:
    build: ./services/worker
    environment:
      - DATABASE_URL=postgresql://clipscript:securepassword@postgres:5432/clipscript
      - API_BASE_URL=http://api:3000
      - DEEPGRAM_API_KEY=${DEEPGRAM_API_KEY}
    depends_on:
      - postgres
      - api
    restart: unless-stopped

  bot:
    build: ./services/bot
    environment:
      - BOT_TOKEN=${BOT_TOKEN}
      - API_BASE_URL=http://api:3000
      - ENABLE_TELEGRAM_WEBHOOK=false
    depends_on:
      - api
    restart: unless-stopped

volumes:
  postgres_data:
```

### Run Docker Compose

```bash
# Build and start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop all services
docker-compose down
```

---

## ☁️ AWS Deployment

### Architecture

```
┌─────────────────┐
│  API Gateway    │
└────────┬────────┘
         │
   ┌─────┴─────────────┐
   │                   │
┌──▼──┐  ┌──────────┐  ┌──▼────┐
│ EC2 │  │ Database │  │ S3    │
│(API)│  │  (RDS)   │  │Cache  │
└─────┘  └──────────┘  └───────┘
```

### Steps

1. **Create RDS Database**
   - Service: RDS PostgreSQL
   - Instance: db.t3.micro (free tier eligible)
   - Save connection string

2. **Create EC2 Instances**
   - Instance type: t3.micro x3 (API, Worker, Bot)
   - AMI: Ubuntu 22.04
   - Security group: Allow inbound on ports 80, 443, 3000

3. **Deploy Each Service**
   ```bash
   # On each instance
   git clone <your-repo>
   cd clipscript-ai-bot
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   
   # Configure .env with RDS connection
   nano .env
   
   # Start service
   nohup python services/api/app.py &  # On API instance
   nohup python services/worker/worker.py &  # On Worker
   nohup python services/bot/telegram_bot.py &  # On Bot
   ```

4. **Setup API Gateway**
   - Route: `/api/*` → EC2 instance
   - Enable HTTPS

---

## 🔒 Security Best Practices

### Environment Variables
- **Never** commit `.env` to Git
- Use `.gitignore` to exclude it
- In production, use platform secrets (Render, AWS, etc.)

### Database
- Use PostgreSQL in production (not SQLite)
- Enable SSL connections
- Regular backups
- Encrypted passwords

### API
- Enable CORS for specific domains only
- Rate limiting on endpoints
- Input validation
- Error messages don't leak info

### Bot
- Don't log sensitive user data
- Validate all URLs before processing
- Timeout long-running jobs

### Deployment
- Use HTTPS only
- Keep dependencies updated
- Monitor error logs
- Daily backups

---

## 📊 Monitoring

### Health Checks

Create `monitoring.py`:

```python
import requests
from datetime import datetime

def check_health():
    endpoints = {
        "API": "http://localhost:3000/health",
        "Worker": "http://localhost:3000/api/worker-status",
    }
    
    for name, url in endpoints.items():
        try:
            response = requests.get(url, timeout=5)
            status = "✅" if response.status_code == 200 else "❌"
            print(f"{status} {name}: {response.status_code}")
        except Exception as e:
            print(f"❌ {name}: {str(e)}")

if __name__ == "__main__":
    check_health()
```

Run hourly with cron:
```bash
0 * * * * /usr/bin/python3 /path/to/monitoring.py >> /var/log/clipscript-health.log
```

---

## 🐛 Troubleshooting

### "Service failed to start"
1. Check `.env` file exists and has all required fields
2. Verify tokens are valid
3. Check logs: `docker-compose logs <service>`

### "Database connection failed"
1. Verify `DATABASE_URL` is correct
2. Test connection: `psql <DATABASE_URL>`
3. On Render: restart database instance

### "No transcriptions are working"
1. Check Deepgram API key is valid
2. Verify worker service is running
3. Check worker logs for errors
4. Test API manually: `curl http://localhost:3000/health`

### "Bot doesn't respond to messages"
1. Verify `BOT_TOKEN` is correct
2. Check telegram service logs
3. Verify API is accessible from bot service
4. Check Telegram API isn't blocked (some regions)

---

## 📝 Maintenance Schedule

### Daily
- [ ] Check error logs
- [ ] Monitor API response times
- [ ] Verify bot is responding

### Weekly
- [ ] Database backup
- [ ] Clean old jobs from database
- [ ] Review Deepgram usage

### Monthly
- [ ] Update dependencies
- [ ] Security audit
- [ ] Review and optimize costs

---

## 📚 Additional Resources

- [Render.com Documentation](https://render.com/docs)
- [Docker Documentation](https://docs.docker.com)
- [AWS Free Tier](https://aws.amazon.com/free)
- [Telegram Bot API](https://core.telegram.org/bots/api)
- [Deepgram Documentation](https://developers.deepgram.com)

