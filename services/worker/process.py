"""
Worker Service - Heavy processing engine
Handles yt-dlp downloads, transcription
No Flask, no Telegram, separate event loop
"""
import os
import sys
import asyncio
import logging
import subprocess
import requests
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.config import DEEPGRAM_API_KEY, TRANSCRIPTION_SERVICE
from shared.models import Job, JobStatus, ErrorType

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

TEMP_DIR = "temp"
os.makedirs(TEMP_DIR, exist_ok=True)

def get_error_type(error: str) -> ErrorType:
    """Classify error from yt-dlp"""
    error_lower = error.lower()
    
    if "403" in error or "forbidden" in error_lower:
        return ErrorType.BLOCKED
    elif "429" in error or "rate" in error_lower or "too many" in error_lower:
        return ErrorType.RATE_LIMITED
    elif "private" in error_lower:
        return ErrorType.PRIVATE
    elif "deleted" in error_lower or "not found" in error_lower:
        return ErrorType.DELETED
    elif "unsupported" in error_lower or "type" in error_lower:
        return ErrorType.UNSUPPORTED
    else:
        return ErrorType.UNKNOWN

def download_audio(link: str, job_id: str) -> Optional[str]:
    """
    Download audio from video link using yt-dlp
    Returns path to audio file or None on failure
    """
    logger.info(f"[{job_id}] Starting download: {link[:60]}")
    
    output_file = os.path.join(TEMP_DIR, f"{job_id}.m4a")
    
    # Layer 1: Desktop + best audio
    try:
        cmd = [
            "yt-dlp",
            "-f", "bestaudio/best",
            "-o", output_file,
            "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "--retries", "3",
            "--socket-timeout", "30",
            link
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        
        if result.returncode == 0 and os.path.exists(output_file):
            logger.info(f"[{job_id}] ✅ Layer 1 success")
            return output_file
        
        logger.warning(f"[{job_id}] Layer 1 failed: {result.stderr[:100]}")
    
    except subprocess.TimeoutExpired:
        logger.warning(f"[{job_id}] Layer 1 timeout")
    except Exception as e:
        logger.warning(f"[{job_id}] Layer 1 error: {e}")
    
    # Layer 2: Mobile + fallback format
    try:
        cmd = [
            "yt-dlp",
            "-f", "worstaudio/worst",
            "-o", output_file,
            "--user-agent", "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0) AppleWebKit/605.1.15",
            "--retries", "2",
            "--socket-timeout", "30",
            link
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        
        if result.returncode == 0 and os.path.exists(output_file):
            logger.info(f"[{job_id}] ✅ Layer 2 success")
            return output_file
        
        logger.warning(f"[{job_id}] Layer 2 failed: {result.stderr[:100]}")
    
    except subprocess.TimeoutExpired:
        logger.warning(f"[{job_id}] Layer 2 timeout")
    except Exception as e:
        logger.warning(f"[{job_id}] Layer 2 error: {e}")
    
    # Layer 3: Any format, generic UA
    try:
        cmd = [
            "yt-dlp",
            "-f", "best",
            "-o", output_file,
            "--user-agent", "Mozilla/5.0 (Linux; Android 11) AppleWebKit/537.36",
            "--retries", "1",
            "--socket-timeout", "30",
            link
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        
        if result.returncode == 0 and os.path.exists(output_file):
            logger.info(f"[{job_id}] ✅ Layer 3 success")
            return output_file
        
        logger.error(f"[{job_id}] ❌ All layers failed: {result.stderr[:100]}")
        return None
    
    except subprocess.TimeoutExpired:
        logger.error(f"[{job_id}] Layer 3 timeout")
    except Exception as e:
        logger.error(f"[{job_id}] Layer 3 error: {e}")
    
    return None

def transcribe_audio(audio_path: str, job_id: str) -> Optional[str]:
    """Transcribe audio using Deepgram"""
    logger.info(f"[{job_id}] Starting transcription...")
    
    try:
        with open(audio_path, 'rb') as f:
            response = requests.post(
                "https://api.deepgram.com/v1/listen",
                headers={
                    "Authorization": f"Token {DEEPGRAM_API_KEY}",
                    "Content-Type": "audio/mpeg"
                },
                data=f.read(),
                timeout=120
            )
            
            if response.status_code != 200:
                logger.error(f"[{job_id}] Deepgram error: {response.text}")
                return None
            
            result = response.json()
            transcript = result.get("results", {}).get("channels", [{}])[0].get("alternatives", [{}])[0].get("transcript", "")
            
            if transcript:
                logger.info(f"[{job_id}] ✅ Transcription complete: {len(transcript)} chars")
                return transcript
            else:
                logger.warning(f"[{job_id}] No transcript in response")
                return None
    
    except Exception as e:
        logger.error(f"[{job_id}] Transcription error: {e}")
        return None
    
    finally:
        # Cleanup audio file
        try:
            if os.path.exists(audio_path):
                os.remove(audio_path)
        except:
            pass

async def process_job(job_id: str, link: str, user_id: Optional[str] = None):
    """Main job processing pipeline"""
    logger.info(f"[{job_id}] Processing job...")
    
    # Download audio
    audio_path = download_audio(link, job_id)
    
    if not audio_path:
        logger.error(f"[{job_id}] Download failed - cannot transcribe")
        return {
            "success": False,
            "error": "Could not download audio",
            "error_type": "download_failed"
        }
    
    # Transcribe
    transcript = transcribe_audio(audio_path, job_id)
    
    if not transcript:
        logger.error(f"[{job_id}] Transcription failed")
        return {
            "success": False,
            "error": "Transcription failed",
            "error_type": "transcription_failed"
        }
    
    logger.info(f"[{job_id}] ✅ Job complete")
    return {
        "success": True,
        "job_id": job_id,
        "transcript": transcript
    }

# Simple HTTP server for Flask to call
from flask import Flask, request, jsonify

worker_app = Flask(__name__)

@worker_app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy", "service": "worker"}), 200

@worker_app.route('/process', methods=['POST'])
def process_request():
    """Receive job from API service"""
    try:
        data = request.get_json()
        job_id = data.get('job_id')
        link = data.get('link')
        user_id = data.get('user_id')
        
        logger.info(f"[{job_id}] Received processing request: {link[:60]}")
        
        # Run async processing in background
        # In production, this would use a proper job queue
        asyncio.create_task(process_job(job_id, link, user_id))
        
        return jsonify({
            "success": True,
            "job_id": job_id,
            "message": "Processing started"
        }), 202
    
    except Exception as e:
        logger.error(f"Process request error: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

if __name__ == '__main__':
    logger.info("🚀 Starting Worker Service...")
    logger.info("⚠️  This service handles heavy processing")
    logger.info("⚠️  Do NOT run Telegram or API logic here")
    
    # In development: run simple Flask server
    from threading import Thread
    
    def run_flask():
        worker_app.run(host='0.0.0.0', port=6000, debug=False)
    
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Keep asyncio event loop running in main thread
    try:
        asyncio.run(asyncio.sleep(999999))
    except KeyboardInterrupt:
        logger.info("⏹️  Worker stopped")
