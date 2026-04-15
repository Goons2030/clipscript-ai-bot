"""Shared configuration for all services"""
import os
from dotenv import load_dotenv

load_dotenv()

# Service credentials
BOT_TOKEN = os.getenv("BOT_TOKEN")
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TRANSCRIPTION_SERVICE = os.getenv("TRANSCRIPTION_SERVICE", "deepgram")

# Service URLs (for inter-service communication)
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:5000")
WORKER_BASE_URL = os.getenv("WORKER_BASE_URL", "http://localhost:6000")

# Database
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///clipscript.db")

# Deployment
IS_PRODUCTION = os.getenv("ENVIRONMENT", "development").lower() == "production"
PORT = int(os.getenv("PORT", 5000))

# Feature flags
ENABLE_TELEGRAM_WEBHOOK = os.getenv("WEBHOOK_URL") is not None
TELEGRAM_WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# Validation
if not BOT_TOKEN:
    raise ValueError("Missing BOT_TOKEN in .env")

if not DEEPGRAM_API_KEY:
    raise ValueError("Missing DEEPGRAM_API_KEY in .env")
