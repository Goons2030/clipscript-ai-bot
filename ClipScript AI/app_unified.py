"""
ClipScript AI - Unified Backend
Handles both Telegram bot (webhook) + Web API on ONE Flask service
"""

import os
import uuid
import subprocess
import logging
import asyncio
import io
import sys
import threading
import requests
import re
import time
from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_cors import CORS
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Import database layer
from db import init_db, create_job, update_job_status, save_result, save_error, get_user_jobs, get_latest_job, get_status_emoji, shorten_url

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TRANSCRIPTION_SERVICE = os.getenv("TRANSCRIPTION_SERVICE", "deepgram")

if not BOT_TOKEN:
    raise ValueError("Missing BOT_TOKEN in .env")

# Setup logging (file + console, UTF-8 safe)
log_format = logging.Formatter('[%(asctime)s] %(name)s - %(levelname)s - %(message)s')

# Create logs directory
os.makedirs('logs', exist_ok=True)

# File handler
file_handler = logging.FileHandler('logs/clipscript_unified.log')
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(log_format)

# Console handler with UTF-8 encoding
console_handler = logging.StreamHandler(io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8'))
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(log_format)

# Root logger
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)

logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Initialize Telegram app
telegram_app = Application.builder().token(BOT_TOKEN).build()

# Configuration
TEMP_DIR = "temp"
os.makedirs(TEMP_DIR, exist_ok=True)
MAX_RETRIES = 2

# Request isolation for Telegram
request_semaphore = asyncio.Semaphore(1)


# ============================================
# SHARED UTILITY FUNCTIONS
# ============================================

def is_valid_tiktok_url(url: str) -> bool:
    """Validate TikTok URL format."""
    tiktok_patterns = [
        r'https?://(?:www\.)?tiktok\.com/@[\w.-]+/video/\d+',
        r'https?://(?:vm|vt)\.tiktok\.com/\w+',
        r'https?://(?:www\.)?tiktok\.com/(?:video/\d+|@[\w.-]+)',
    ]
    return any(re.match(pattern, url) for pattern in tiktok_patterns)


def download_video(url: str, output_path: str, request_id: str = "system", retry_count: int = 0) -> bool:
    """Download TikTok video using yt-dlp with anti-blocking measures. Returns bool."""
    try:
        # Rotate user agents to avoid TikTok blocking
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        ]
        user_agent = user_agents[retry_count % len(user_agents)]
        
        command = [
            "yt-dlp",
            "-f", "best",
            "-o", output_path,
            "--no-warnings",
            "--extractor-args", "tiktok:api_hostname=api22-normal-c-hl.tiktokv.com",
            "--user-agent", user_agent,
            "--socket-timeout", "30",
            "--retries", "5",
            "--sleep-requests", "2",
            url
        ]
        
        logger.info(f"[{request_id}] Download attempt {retry_count + 1}")
        result = subprocess.run(command, capture_output=True, timeout=120, text=True)
        
        if result.returncode != 0:
            error_output = result.stderr
            if "HTTP Error 403" in error_output or "blocked" in error_output.lower():
                logger.warning(f"[{request_id}] TikTok blocked request")
                if retry_count < MAX_RETRIES:
                    delay = 30 + (retry_count * 10)
                    time.sleep(delay)
                    return download_video(url, output_path, request_id, retry_count + 1)
            else:
                logger.error(f"[{request_id}] Download failed: {error_output[:100]}")
                if retry_count < MAX_RETRIES:
                    time.sleep(2 ** retry_count)
                    return download_video(url, output_path, request_id, retry_count + 1)
            return False
        
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            logger.info(f"[{request_id}] Video downloaded successfully")
            return True
        else:
            logger.error(f"[{request_id}] Downloaded file is empty")
            return False
            
    except subprocess.TimeoutExpired:
        logger.warning(f"[{request_id}] Download timeout (120s)")
        if retry_count < MAX_RETRIES:
            return download_video(url, output_path, request_id, retry_count + 1)
        return False
    except Exception as e:
        logger.error(f"[{request_id}] Download error: {str(e)[:100]}")
        return False


def extract_audio(video_path: str, audio_path: str, request_id: str = "system") -> bool:
    """Extract audio from video using FFmpeg. Returns bool."""
    try:
        command = [
            "ffmpeg",
            "-i", video_path,
            "-vn",
            "-acodec", "libmp3lame",
            "-ab", "128k",
            "-ar", "16000",
            "-ac", "1",
            "-y",
            audio_path
        ]
        
        logger.info(f"[{request_id}] Extracting audio")
        result = subprocess.run(command, capture_output=True, timeout=60, text=True)
        
        if result.returncode != 0:
            logger.error(f"[{request_id}] Audio extraction failed: {result.stderr[:100]}")
            return False
        
        if os.path.exists(audio_path) and os.path.getsize(audio_path) > 0:
            logger.info(f"[{request_id}] Audio extracted successfully")
            return True
        else:
            logger.error(f"[{request_id}] Extracted audio is empty")
            return False
            
    except subprocess.TimeoutExpired:
        logger.warning(f"[{request_id}] Audio extraction timeout (60s)")
        return False
    except Exception as e:
        logger.error(f"[{request_id}] Extract audio error: {str(e)[:100]}")
        return False


def transcribe_with_deepgram(audio_path: str, request_id: str = "system") -> str:
    """Transcribe using Deepgram API. Returns string (empty on failure)."""
    try:
        if not DEEPGRAM_API_KEY:
            logger.error(f"[{request_id}] DEEPGRAM_API_KEY not set")
            return ""

        with open(audio_path, 'rb') as f:
            headers = {'Authorization': f'Token {DEEPGRAM_API_KEY}'}
            params = {'model': 'nova-2', 'language': 'en'}
            
            logger.info(f"[{request_id}] Sending to Deepgram")
            response = requests.post(
                'https://api.deepgram.com/v1/listen',
                headers=headers,
                params=params,
                files={'audio': f},
                timeout=60
            )

        if response.status_code != 200:
            logger.error(f"[{request_id}] Deepgram error: {response.status_code}")
            return ""

        result = response.json()
        transcript = result['results']['channels'][0]['alternatives'][0]['transcript']
        logger.info(f"[{request_id}] Transcription successful: {len(transcript)} chars")
        return transcript
        
    except requests.Timeout:
        logger.warning(f"[{request_id}] Deepgram timeout (60s)")
        return ""
    except Exception as e:
        logger.error(f"[{request_id}] Deepgram error: {str(e)[:100]}")
        return ""


def transcribe_with_whisper(audio_path: str, request_id: str = "system") -> str:
    """Transcribe using OpenAI Whisper. Returns string (empty on failure)."""
    try:
        if not OPENAI_API_KEY:
            logger.error(f"[{request_id}] OPENAI_API_KEY not set")
            return ""

        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)

        with open(audio_path, 'rb') as f:
            logger.info(f"[{request_id}] Sending to Whisper")
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                language="en"
            )

        result = transcript.text.strip()
        logger.info(f"[{request_id}] Transcription successful: {len(result)} chars")
        return result

    except Exception as e:
        logger.error(f"[{request_id}] Whisper error: {str(e)[:100]}")
        return ""


def transcribe(audio_path: str, request_id: str = "system") -> str:
    """Route to appropriate transcription service."""
    if TRANSCRIPTION_SERVICE == "deepgram":
        return transcribe_with_deepgram(audio_path, request_id)
    else:
        return transcribe_with_whisper(audio_path, request_id)


def cleanup_files(video_path: str, audio_path: str, request_id: str = "system") -> None:
    """Safely cleanup temporary files."""
    for path in [video_path, audio_path]:
        if not path:
            continue
        try:
            if os.path.exists(path):
                os.remove(path)
                logger.info(f"[{request_id}] Cleaned: {path}")
        except Exception as e:
            logger.warning(f"[{request_id}] Cleanup failed: {str(e)[:80]}")


def cleanup_old_temp_files() -> None:
    """Clean up leftover temp files on startup."""
    try:
        if os.path.exists(TEMP_DIR):
            for fname in os.listdir(TEMP_DIR):
                fpath = os.path.join(TEMP_DIR, fname)
                if os.path.isfile(fpath):
                    try:
                        os.remove(fpath)
                        logger.info(f"Cleaned orphaned: {fpath}")
                    except:
                        pass
    except:
        pass


def process_transcription(url: str, request_id: str = "system") -> str:
    """Core transcription workflow - shared by both Telegram and Web."""
    try:
        if not is_valid_tiktok_url(url):
            logger.warning(f"[{request_id}] Invalid TikTok URL")
            raise Exception("Invalid TikTok URL")

        file_id = str(uuid.uuid4())
        video_path = f"{TEMP_DIR}/{file_id}.mp4"
        audio_path = f"{TEMP_DIR}/{file_id}.mp3"

        try:
            # Step 1: Download
            logger.info(f"[{request_id}] Starting download")
            if not download_video(url, video_path, request_id):
                raise Exception("Download failed")

            # Step 2: Extract audio
            if not extract_audio(video_path, audio_path, request_id):
                raise Exception("Audio extraction failed")

            # Step 3: Transcribe
            logger.info(f"[{request_id}] Starting transcription")
            transcript = transcribe(audio_path, request_id)
            
            if not transcript:
                raise Exception("Transcription failed or returned empty")

            logger.info(f"[{request_id}] Processing complete: {len(transcript)} chars")
            return transcript

        finally:
            # Always cleanup
            cleanup_files(video_path, audio_path, request_id)

    except Exception as e:
        error_msg = str(e)
        logger.error(f"[{request_id}] Processing failed: {error_msg}")
        raise


# ============================================
# TELEGRAM BOT HANDLERS
# ============================================

async def handle_telegram_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming Telegram messages."""
    async with request_semaphore:
        request_id = str(uuid.uuid4())[:8]
        user_id = str(update.message.from_user.id)
        logger.info(f"[{request_id}] Telegram message from user {user_id}")
        
        try:
            text = update.message.text.strip()

            if not is_valid_tiktok_url(text):
                await update.message.reply_text(
                    "Invalid TikTok URL. Please send a valid link.\n\n"
                    "Examples:\n"
                    "- https://www.tiktok.com/@username/video/123456\n"
                    "- https://vm.tiktok.com/abc123xyz\n\n"
                    "Use /help for more commands."
                )
                return

            # Create job in database
            try:
                create_job(request_id, user_id, text)
                update_job_status(request_id, "processing")
            except Exception as e:
                logger.warning(f"[{request_id}] Database operation failed: {e}")

            status_msg = await update.message.reply_text("Processing (downloading video)")

            try:
                # Process transcription
                transcript = process_transcription(text, request_id)
                
                # Save result to database
                try:
                    save_result(request_id, transcript)
                except Exception as e:
                    logger.warning(f"[{request_id}] Failed to save result: {e}")
                
                # Delete status message
                try:
                    await status_msg.delete()
                except:
                    pass
                
                # Send transcript (split if too long)
                chunks = [transcript[i:i+4000] for i in range(0, len(transcript), 4000)]
                for idx, chunk in enumerate(chunks):
                    if len(chunks) > 1:
                        await update.message.reply_text(f"Part {idx + 1}/{len(chunks)}\n\n{chunk}")
                    else:
                        await update.message.reply_text(chunk)

            except Exception as e:
                error_msg = str(e)
                logger.error(f"[{request_id}] Processing error: {error_msg}")
                
                # Save error to database
                try:
                    save_error(request_id, error_msg)
                except Exception as db_e:
                    logger.warning(f"[{request_id}] Failed to save error: {db_e}")
                
                try:
                    await status_msg.edit_text(f"Error: {error_msg[:80]}")
                except:
                    await update.message.reply_text(f"Error: {error_msg[:80]}")

        except Exception as e:
            logger.error(f"[{request_id}] Telegram handler error: {str(e)}", exc_info=True)


async def handle_telegram_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    user_id = str(update.message.from_user.id)
    await update.message.reply_text(
        "🎬 *ClipScript AI*\n\n"
        "Turn TikTok videos into text transcripts instantly.\n\n"
        "*Commands:*\n"
        "• Send any TikTok link → transcribe\n"
        "/status - Current job status\n"
        "/history - Your last 5 requests\n"
        "/help - Usage guide\n\n"
        "Processing takes 5-30 seconds.",
        parse_mode="Markdown"
    )
    logger.info(f"[START] User {user_id}")


async def handle_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command - show latest job."""
    user_id = str(update.message.from_user.id)
    
    try:
        job = get_latest_job(user_id)
        
        if not job:
            await update.message.reply_text("📋 No previous jobs found.\n\nSend a TikTok link to get started!")
            return
        
        status_emoji = get_status_emoji(job['status'])
        link_short = shorten_url(job['link'])
        
        response = f"{status_emoji} *Status:* {job['status'].upper()}\n"
        response += f"🔗 *Link:* `{link_short}`\n"
        response += f"⏰ *Created:* {job['created_at'][:16]}\n"
        
        if job['status'] == 'completed' and job['result']:
            result_preview = job['result'][:100] + "..." if len(job['result']) > 100 else job['result']
            response += f"\n📝 *Preview:*\n`{result_preview}`"
        elif job['status'] == 'failed' and job['error']:
            response += f"\n❌ *Error:* {job['error'][:80]}"
        
        await update.message.reply_text(response, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Status command error: {e}")
        await update.message.reply_text("Error retrieving status. Please try again.")


async def handle_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /history command - show last 5 jobs."""
    user_id = str(update.message.from_user.id)
    
    try:
        jobs = get_user_jobs(user_id, limit=5)
        
        if not jobs:
            await update.message.reply_text("📋 No history yet.\n\nSend a TikTok link to get started!")
            return
        
        response = "📋 *Your Last 5 Requests:*\n\n"
        for idx, job in enumerate(jobs, 1):
            status_emoji = get_status_emoji(job['status'])
            link_short = shorten_url(job['link'], max_length=30)
            response += f"{idx}. {status_emoji} {link_short}\n"
        
        await update.message.reply_text(response, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"History command error: {e}")
        await update.message.reply_text("Error retrieving history. Please try again.")


async def handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command - show usage guide."""
    help_text = (
        "🎯 *How to Use ClipScript AI*\n\n"
        "*Transcribe:*\n"
        "Simply send me any TikTok link:\n"
        "• https://www.tiktok.com/@username/video/123456\n"
        "• https://vm.tiktok.com/abc123xyz\n"
        "• https://vt.tiktok.com/xyz\n\n"
        "*Commands:*\n"
        "/status - View your current job\n"
        "/history - View last 5 requests\n"
        "/help - Show this help message\n\n"
        "*Speed:*\n"
        "⚡ Most videos: 5-15 seconds\n"
        "⚡ Longer videos: up to 30 seconds\n\n"
        "*API:*\n"
        "Use Deepgram for accurate transcription\n"
        "FFmpeg for audio extraction\n"
        "yt-dlp for video download"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")


# Add Telegram handlers
telegram_app.add_handler(CommandHandler("start", handle_telegram_start))
telegram_app.add_handler(CommandHandler("status", handle_status))
telegram_app.add_handler(CommandHandler("history", handle_history))
telegram_app.add_handler(CommandHandler("help", handle_help))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_telegram_message))


# ============================================
# FLASK ROUTES - WEB API + TELEGRAM WEBHOOK
# ============================================

@app.route('/', methods=['GET'])
def index():
    """Serve the web UI (index.html from web folder)."""
    try:
        # Support both repo-root execution and subdirectory (Railway root-dir) execution
        current_dir = os.path.dirname(__file__)
        repo_root = os.path.dirname(current_dir)
        candidate_folders = [
            os.path.join(repo_root, 'ClipScript AI web'),   # normal repo layout
            os.path.join(current_dir, 'web'),               # optional co-located web folder
            os.path.join(current_dir, '..', 'ClipScript AI web'),
        ]

        for folder in candidate_folders:
            folder = os.path.abspath(folder)
            index_path = os.path.join(folder, 'index.html')
            if os.path.exists(index_path):
                return send_from_directory(folder, 'index.html')

        return jsonify({"status": "Web UI not found"}), 404
    except:
        return jsonify({"status": "Web UI not found"}), 404


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({
        'status': 'ok',
        'service': 'ClipScript AI Unified Backend',
        'transcription_service': TRANSCRIPTION_SERVICE
    })


@app.route('/telegram/webhook', methods=['POST'])
def telegram_webhook():
    """Telegram webhook - receives messages from Telegram."""
    try:
        update_data = request.json
        update = Update.de_json(update_data, telegram_app.bot)
        
        # Process through Telegram handlers (sync wrapper for async)
        asyncio.run(telegram_app.process_update(update))
        
        return jsonify({'status': 'ok'})
    except Exception as e:
        logger.error(f"Telegram webhook error: {str(e)}")
        return jsonify({'error': str(e)}), 400


@app.route('/api/transcribe', methods=['POST'])
def api_transcribe():
    """Web API endpoint - receives requests from web app."""
    request_id = str(uuid.uuid4())[:8]
    logger.info(f"[{request_id}] Web API request")
    
    try:
        data = request.get_json()
        url = data.get('link', '').strip() if data else ''

        if not url:
            logger.warning(f"[{request_id}] No link provided")
            return jsonify({'error': 'No link provided'}), 400

        if not is_valid_tiktok_url(url):
            logger.warning(f"[{request_id}] Invalid URL format")
            return jsonify({'error': 'Invalid TikTok URL'}), 400

        # Process
        transcript = process_transcription(url, request_id)

        logger.info(f"[{request_id}] API response: {len(transcript)} chars")
        return jsonify({
            'success': True,
            'transcript': transcript,
            'length': len(transcript)
        })

    except Exception as e:
        error_msg = str(e)
        logger.error(f"[{request_id}] API error: {error_msg}")
        
        if "tiktok" in error_msg.lower() or "403" in error_msg:
            return jsonify({'error': 'TikTok blocked. Try again in 5 minutes.'}), 429
        elif "timeout" in error_msg.lower():
            return jsonify({'error': 'Processing took too long. Try a shorter video.'}), 408
        else:
            return jsonify({'error': error_msg[:100]}), 500


@app.route('/api/pricing', methods=['GET'])
def pricing():
    """Get pricing information."""
    services = {
        'deepgram': {
            'cost_per_minute': 0.0043,
            'speed': 'very_fast',
            'free_tier': '50k requests/month'
        },
        'whisper': {
            'cost_per_minute': 0.006,
            'speed': 'fast',
            'free_tier': None
        }
    }
    
    return jsonify({
        'current_service': TRANSCRIPTION_SERVICE,
        'services': services
    })


# ============================================
# SETUP & STARTUP
# ============================================

def setup_telegram_webhook():
    """Configure Telegram webhook on startup."""
    import asyncio
    
    async def set_webhook():
        try:
            # Get webhook URL from environment or construct it
            webhook_url = os.getenv("WEBHOOK_URL")
            
            if not webhook_url and os.getenv("RENDER_EXTERNAL_URL"):
                webhook_url = f"{os.getenv('RENDER_EXTERNAL_URL')}/telegram/webhook"
            
            if webhook_url:
                await telegram_app.bot.set_webhook(url=webhook_url)
                logger.info(f"Telegram webhook set to: {webhook_url}")
            else:
                logger.warning("No webhook URL configured (OK for local testing)")
        except Exception as e:
            logger.error(f"Failed to set webhook: {e}")
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(set_webhook())
    except Exception as e:
        logger.error(f"Webhook setup error: {e}")


# ============================================
# MAIN
# ============================================

if __name__ == '__main__':
    logger.info("="*70)
    logger.info("Starting ClipScript AI - Unified Backend")
    logger.info(f"Transcription Service: {TRANSCRIPTION_SERVICE}")
    logger.info("="*70)
    
    # Initialize database
    try:
        init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        logger.warning("Continuing without persistence layer")
    
    # Cleanup orphaned files from previous runs
    cleanup_old_temp_files()
    
    # Check if webhook URL is configured
    webhook_url = os.getenv("WEBHOOK_URL") or (
        f"{os.getenv('RENDER_EXTERNAL_URL')}/telegram/webhook" 
        if os.getenv("RENDER_EXTERNAL_URL") else None
    )
    
    port = int(os.getenv("PORT", 5000))

    if webhook_url:
        # Production mode: Use webhook
        logger.info("PRODUCTION MODE - Using Telegram webhook")
        setup_telegram_webhook()
        logger.info("Unified backend ready for Telegram (webhook) + Web API requests")
        logger.info("="*70)
        app.run(host='0.0.0.0', port=port, debug=False)
    else:
        # Development mode: Use polling
        logger.info("DEVELOPMENT MODE - Using Telegram polling")
        
        # Start Flask in a background thread
        flask_thread = threading.Thread(
            target=lambda: app.run(host='0.0.0.0', port=port, debug=False),
            daemon=True
        )
        flask_thread.start()
        logger.info("Flask server started in background")
        logger.info("Unified backend ready for Telegram (polling) + Web API requests")
        logger.info("="*70)
        
        # Start Telegram polling in main thread
        logger.info("Starting Telegram bot polling...")
        try:
            asyncio.run(telegram_app.run_polling())
        except KeyboardInterrupt:
            logger.info("Telegram polling stopped by user")
            exit(0)
