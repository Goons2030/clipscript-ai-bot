import os
import uuid
import subprocess
import logging
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from flask_cors import CORS
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters
import re

# Load env
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
TRANSCRIPTION_SERVICE = os.getenv("TRANSCRIPTION_SERVICE", "deepgram")

if not BOT_TOKEN:
    raise ValueError("Missing BOT_TOKEN in .env")

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Initialize Telegram app
telegram_app = Application.builder().token(BOT_TOKEN).build()

# Transcription client
if TRANSCRIPTION_SERVICE == "deepgram":
    import requests
    transcription_client = "deepgram"
else:
    from openai import OpenAI
    transcription_client = OpenAI(api_key=OPENAI_API_KEY)

TEMP_DIR = "temp"
os.makedirs(TEMP_DIR, exist_ok=True)

MAX_FILE_SIZE = 25 * 1024 * 1024
MAX_RETRIES = 2


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


def download_video(url: str, output_path: str, retry_count: int = 0) -> bool:
    """Download TikTok video using yt-dlp."""
    try:
        command = [
            "yt-dlp",
            "-f", "best",
            "-o", output_path,
            "--no-warnings",
            url
        ]
        subprocess.run(command, check=True, capture_output=True, timeout=120)
        
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            logger.info(f"Video downloaded: {output_path}")
            return True
        else:
            raise Exception("Downloaded file is empty")
    except subprocess.TimeoutExpired:
        logger.warning(f"Download timeout for {url}")
        if retry_count < MAX_RETRIES:
            return download_video(url, output_path, retry_count + 1)
        raise Exception("Download failed: timeout after retries")
    except Exception as e:
        logger.error(f"Download failed: {str(e)}")
        if retry_count < MAX_RETRIES:
            return download_video(url, output_path, retry_count + 1)
        raise


def extract_audio(video_path: str, audio_path: str) -> bool:
    """Extract audio from video using ffmpeg."""
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
        subprocess.run(command, check=True, capture_output=True, timeout=60)
        
        if os.path.exists(audio_path) and os.path.getsize(audio_path) > 0:
            logger.info(f"Audio extracted: {audio_path}")
            return True
        else:
            raise Exception("Extracted audio is empty")
    except Exception as e:
        logger.error(f"Audio extraction failed: {str(e)}")
        raise


def transcribe_with_deepgram(audio_path: str) -> str:
    """Transcribe using Deepgram API."""
    try:
        if not DEEPGRAM_API_KEY:
            raise Exception("DEEPGRAM_API_KEY not set")

        with open(audio_path, 'rb') as f:
            headers = {
                'Authorization': f'Token {DEEPGRAM_API_KEY}'
            }
            params = {
                'model': 'nova-2',
                'language': 'en'
            }
            response = requests.post(
                'https://api.deepgram.com/v1/listen',
                headers=headers,
                params=params,
                files={'audio': f},
                timeout=60
            )

        if response.status_code != 200:
            raise Exception(f"Deepgram error: {response.status_code}")

        result = response.json()
        transcript = result['results']['channels'][0]['alternatives'][0]['transcript']
        
        logger.info(f"Deepgram transcription successful: {len(transcript)} chars")
        return transcript

    except Exception as e:
        logger.error(f"Deepgram transcription failed: {str(e)}")
        raise


def transcribe_with_whisper(audio_path: str) -> str:
    """Transcribe using OpenAI Whisper API."""
    try:
        if not OPENAI_API_KEY:
            raise Exception("OPENAI_API_KEY not set")

        with open(audio_path, 'rb') as f:
            transcript = transcription_client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                language="en"
            )

        result = transcript.text.strip()
        logger.info(f"Whisper transcription successful: {len(result)} chars")
        return result

    except Exception as e:
        logger.error(f"Whisper transcription failed: {str(e)}")
        raise


def transcribe(audio_path: str) -> str:
    """Main transcription function - routes to correct service."""
    if TRANSCRIPTION_SERVICE == "deepgram":
        return transcribe_with_deepgram(audio_path)
    else:
        return transcribe_with_whisper(audio_path)


def cleanup_files(video_path: str, audio_path: str) -> None:
    """Safe cleanup of temporary files."""
    for path in [video_path, audio_path]:
        try:
            if path and os.path.exists(path):
                os.remove(path)
                logger.info(f"Cleaned up: {path}")
        except Exception as e:
            logger.warning(f"Cleanup failed for {path}: {str(e)}")


def process_transcription(url: str) -> str:
    """Core transcription workflow - used by both Telegram and Web."""
    try:
        if not is_valid_tiktok_url(url):
            raise Exception("Invalid TikTok URL")

        file_id = str(uuid.uuid4())
        video_path = f"{TEMP_DIR}/{file_id}.mp4"
        audio_path = f"{TEMP_DIR}/{file_id}.mp3"

        # Download
        logger.info(f"Downloading: {url}")
        download_video(url, video_path)

        # Extract
        logger.info(f"Extracting audio: {video_path}")
        extract_audio(video_path, audio_path)

        # Transcribe
        logger.info(f"Transcribing: {audio_path}")
        transcript = transcribe(audio_path)

        # Cleanup
        cleanup_files(video_path, audio_path)

        return transcript

    except Exception as e:
        logger.error(f"Transcription failed: {str(e)}")
        cleanup_files(video_path, audio_path)
        raise


# ============================================
# TELEGRAM BOT HANDLERS (Using Telegram library)
# ============================================

async def handle_telegram_message(update: Update, context):
    """Handle incoming Telegram messages."""
    try:
        text = update.message.text.strip()

        if not is_valid_tiktok_url(text):
            await update.message.reply_text(
                "❌ Send a valid TikTok link.\n\n"
                "Examples:\n"
                "• https://www.tiktok.com/@username/video/123456\n"
                "• https://vm.tiktok.com/abc123xyz"
            )
            return

        # Show loading
        status_msg = await update.message.reply_text("⏳ Processing... (downloading video)")

        try:
            # Process
            transcript = process_transcription(text)

            # Split into chunks if too long
            chunks = [transcript[i:i+4000] for i in range(0, len(transcript), 4000)]
            
            # Delete loading message
            await status_msg.delete()
            
            # Send transcript chunks
            for idx, chunk in enumerate(chunks):
                if len(chunks) > 1:
                    await update.message.reply_text(f"**Part {idx + 1}/{len(chunks)}**\n\n{chunk}")
                else:
                    await update.message.reply_text(chunk)

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Processing failed: {error_msg}")
            
            try:
                if "tiktok" in error_msg.lower() or "403" in error_msg:
                    await status_msg.edit_text(
                        "❌ TikTok blocked. Try again in 5 minutes."
                    )
                elif "timeout" in error_msg.lower():
                    await status_msg.edit_text(
                        "❌ Request took too long. Try a shorter video."
                    )
                else:
                    await status_msg.edit_text(f"❌ Error: {error_msg[:100]}")
            except:
                await update.message.reply_text(f"❌ Error: {error_msg[:100]}")

    except Exception as e:
        logger.error(f"Telegram handler error: {str(e)}")


async def handle_telegram_start(update: Update, context):
    """Handle /start command."""
    await update.message.reply_text(
        "👋 Welcome to **ClipScript AI**!\n\n"
        "🎬 I turn TikTok videos into text transcripts.\n\n"
        "📤 Send me any TikTok link and I'll transcribe it.\n\n"
        "⏱️ Processing takes 5–30 seconds."
    )


# Add Telegram handlers
telegram_app.add_handler(CommandHandler("start", handle_telegram_start))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_telegram_message))


# ============================================
# FLASK ROUTES (Web API + Telegram Webhook)
# ============================================

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({
        'status': 'ok',
        'service': 'ClipScript AI Unified Backend'
    })


@app.route('/telegram/webhook', methods=['POST'])
async def telegram_webhook():
    """
    Telegram webhook endpoint.
    Telegram sends updates here when bot receives messages.
    """
    try:
        update_data = request.json
        update = Update.de_json(update_data, telegram_app.bot)
        
        # Process the update through Telegram handlers
        await telegram_app.process_update(update)
        
        return jsonify({'status': 'ok'})
    except Exception as e:
        logger.error(f"Telegram webhook error: {str(e)}")
        return jsonify({'error': str(e)}), 400


@app.route('/api/transcribe', methods=['POST'])
def api_transcribe():
    """
    Web API endpoint.
    Web app sends TikTok links here.
    """
    try:
        data = request.get_json()
        url = data.get('link', '').strip()

        if not url:
            return jsonify({'error': 'No link provided'}), 400

        if not is_valid_tiktok_url(url):
            return jsonify({'error': 'Invalid TikTok URL'}), 400

        # Process
        logger.info(f"Web request: {url}")
        transcript = process_transcription(url)

        return jsonify({
            'success': True,
            'transcript': transcript,
            'length': len(transcript)
        })

    except Exception as e:
        error_msg = str(e)
        logger.error(f"API error: {error_msg}")
        
        if "tiktok" in error_msg.lower() or "403" in error_msg:
            return jsonify({'error': 'TikTok blocked. Try again in 5 minutes.'}), 429
        elif "timeout" in error_msg.lower():
            return jsonify({'error': 'Processing took too long. Try a shorter video.'}), 408
        else:
            return jsonify({'error': error_msg}), 500


@app.route('/api/pricing', methods=['GET'])
def pricing():
    """Get pricing info."""
    services = {
        'deepgram': {
            'cost_per_minute': 0.0043,
            'speed': 'very_fast'
        },
        'whisper': {
            'cost_per_minute': 0.006,
            'speed': 'fast'
        }
    }
    
    return jsonify({
        'current_service': TRANSCRIPTION_SERVICE,
        'services': services
    })


# ============================================
# SETUP TELEGRAM WEBHOOK (On Startup)
# ============================================

def setup_telegram_webhook():
    """Tell Telegram to send updates to our webhook instead of polling."""
    import asyncio
    
    async def set_webhook():
        try:
            # Get your Render URL (or local testing URL)
            webhook_url = os.getenv("WEBHOOK_URL", "http://localhost:5000/telegram/webhook")
            
            # If running on Render, construct URL
            if os.getenv("RENDER_EXTERNAL_URL"):
                webhook_url = f"{os.getenv('RENDER_EXTERNAL_URL')}/telegram/webhook"
            
            await telegram_app.bot.set_webhook(url=webhook_url)
            logger.info(f"Telegram webhook set to: {webhook_url}")
        except Exception as e:
            logger.error(f"Failed to set webhook: {e}")
    
    # Run async function
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(set_webhook())


# ============================================
# ERROR HANDLERS
# ============================================

@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Endpoint not found'}), 404


@app.errorhandler(500)
def server_error(e):
    logger.error(f"Server error: {str(e)}")
    return jsonify({'error': 'Server error'}), 500


# ============================================
# MAIN
# ============================================

if __name__ == '__main__':
    logger.info("Starting ClipScript AI Unified Backend...")
    
    # Set up Telegram webhook
    setup_telegram_webhook()
    
    logger.info("Unified backend running. Handling both Telegram + Web requests...")
    
    # Run Flask app
    app.run(host='0.0.0.0', port=5000, debug=False)
