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
import shutil
from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_cors import CORS
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Import database layer
from db import init_db, create_job, update_job_status, save_result, save_error, get_user_jobs, get_latest_job, get_status_emoji, shorten_url, get_job_by_link, get_queue_position, get_pending_count, get_avg_processing_time

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TRANSCRIPTION_SERVICE = os.getenv("TRANSCRIPTION_SERVICE", "deepgram")

if not BOT_TOKEN:
    raise ValueError("Missing BOT_TOKEN in .env")

def clean_ascii(text: str) -> str:
    """
    Remove non-ASCII characters that break Windows logging.
    Replace Unicode symbols with ASCII equivalents.
    """
    if not text:
        return text
    
    # Replace common Unicode symbols with ASCII equivalents
    replacements = {
        '→': '->',
        '✓': 'OK',
        '✗': 'ERROR',
        '…': '...',
        '•': '*',
        '—': '-',
        '–': '-',
        ''': "'",
        ''': "'",
        '"': '"',
        '"': '"',
        '█': '#',
        '▲': '^',
        '▼': 'v',
    }
    
    for symbol, replacement in replacements.items():
        text = text.replace(symbol, replacement)
    
    # Remove any remaining non-ASCII characters
    text = ''.join(char if ord(char) < 128 else '?' for char in text)
    
    return text

class AsciiLoggingFilter(logging.Filter):
    """Logging filter that ensures all messages are ASCII-safe."""
    
    def filter(self, record):
        """Apply clean_ascii to log message before logging."""
        try:
            record.msg = clean_ascii(str(record.msg))
            # Also clean arguments if they exist
            if record.args:
                if isinstance(record.args, dict):
                    record.args = {k: clean_ascii(str(v)) for k, v in record.args.items()}
                elif isinstance(record.args, tuple):
                    record.args = tuple(clean_ascii(str(arg)) for arg in record.args)
        except Exception:
            pass  # If cleaning fails, let the original message through
        return True

# Setup logging (file + console, UTF-8 safe)
log_format = logging.Formatter('[%(asctime)s] %(name)s - %(levelname)s - %(message)s')

# Create logs directory
os.makedirs('logs', exist_ok=True)

# File handler with UTF-8 encoding
file_handler = logging.FileHandler('logs/clipscript_unified.log', encoding='utf-8')
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(log_format)
file_handler.addFilter(AsciiLoggingFilter())  # Ensure ASCII-safe logging

# Console handler with safe encoding for Windows
try:
    # Reconfigure stdout to replace problematic characters
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except:
    pass
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(log_format)
console_handler.addFilter(AsciiLoggingFilter())  # Ensure ASCII-safe logging

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

# Request isolation for Telegram - increased to 2 for better concurrency
request_semaphore = asyncio.Semaphore(2)

# ============================================
# PRODUCTION HARDENING: IN-MEMORY CACHE + LOCKS
# ============================================

# Thread-safe in-memory cache for recently processed links
# Maps normalized_link -> (result, timestamp)
# Reduces DB calls and prevents duplicate simultaneous processing
_link_cache = {}
_link_cache_lock = threading.Lock()
CACHE_MAX_SIZE = 50  # Keep last 50 links in memory

# ============================================
# DUPLICATE PROCESSING PREVENTION
# ============================================
# Global set of links currently being processed
# Prevents multiple simultaneous requests for the same link
_processing_links = set()
_processing_lock = threading.Lock()

# ============================================
# SMART JOB QUEUE SYSTEM
# ============================================
# Tracks all active jobs and their states
# Maps normalized_link -> {
#   'request_id': str,
#   'status': 'processing'|'completed'|'failed',
#   'result': str,
#   'error': str,
#   'created_at': timestamp,
#   'completed_at': timestamp
# }
_job_queue = {}
_job_queue_lock = threading.Lock()

# Tracks users waiting for job results
# Maps normalized_link -> [
#   {'type': 'telegram', 'user_id': str, 'chat_id': str, 'update': Update},
#   {'type': 'api', 'request_id': str}
# ]
_waiting_users = {}
_waiting_users_lock = threading.Lock()


def register_waiting_user(normalized_link: str, user_info: dict):
    """Register a user waiting for job result."""
    try:
        with _waiting_users_lock:
            if normalized_link not in _waiting_users:
                _waiting_users[normalized_link] = []
            _waiting_users[normalized_link].append(user_info)
            logger.debug(f"User registered for {normalized_link[:40]}: {user_info['type']}")
    except Exception as e:
        logger.warning(f"Failed to register waiting user: {e}")


def get_waiting_users(normalized_link: str) -> list:
    """Get all users waiting for a job result."""
    try:
        with _waiting_users_lock:
            return _waiting_users.get(normalized_link, []).copy()
    except Exception as e:
        logger.warning(f"Failed to get waiting users: {e}")
        return []


def clear_waiting_users(normalized_link: str):
    """Clear waiting users after notifying them."""
    try:
        with _waiting_users_lock:
            if normalized_link in _waiting_users:
                del _waiting_users[normalized_link]
                logger.debug(f"Cleared waiting users for {normalized_link[:40]}")
    except Exception as e:
        logger.warning(f"Failed to clear waiting users: {e}")


def get_job_status(normalized_link: str) -> dict:
    """Get current job status from queue."""
    try:
        with _job_queue_lock:
            return _job_queue.get(normalized_link, {}).copy()
    except Exception as e:
        logger.warning(f"Failed to get job status: {e}")
        return {}


def create_job_entry(normalized_link: str, request_id: str):
    """Create a new job entry in the queue."""
    try:
        with _job_queue_lock:
            _job_queue[normalized_link] = {
                'request_id': request_id,
                'status': 'processing',
                'result': None,
                'error': None,
                'created_at': time.time(),
                'completed_at': None
            }
            logger.debug(f"Created job queue entry for {normalized_link[:40]}")
    except Exception as e:
        logger.warning(f"Failed to create job entry: {e}")


def complete_job(normalized_link: str, result: str = None, error: str = None):
    """Mark job as completed and notify waiting users."""
    try:
        with _job_queue_lock:
            if normalized_link in _job_queue:
                _job_queue[normalized_link]['status'] = 'completed' if result else 'failed'
                _job_queue[normalized_link]['result'] = result
                _job_queue[normalized_link]['error'] = error
                _job_queue[normalized_link]['completed_at'] = time.time()
                logger.info(f"Job completed: {normalized_link[:40]}, status: {'completed' if result else 'failed'}")
    except Exception as e:
        logger.warning(f"Failed to complete job: {e}")


def cache_get(link: str) -> str:
    """Get result from in-memory cache if available."""
    try:
        with _link_cache_lock:
            if link in _link_cache:
                result, cached_at = _link_cache[link]
                age = time.time() - cached_at
                logger.debug(f"Cache hit for {link[:40]}, age: {age:.1f}s")
                return result
            return None
    except Exception as e:
        logger.warning(f"Cache get error: {e}")
        return None


def cache_set(link: str, result: str):
    """Store result in in-memory cache."""
    try:
        with _link_cache_lock:
            _link_cache[link] = (result, time.time())
            
            # Evict oldest entry if cache is too large
            if len(_link_cache) > CACHE_MAX_SIZE:
                oldest_key = min(_link_cache.keys(), key=lambda k: _link_cache[k][1])
                del _link_cache[oldest_key]
                logger.debug(f"Cache evicted: {oldest_key[:40]}, size: {len(_link_cache)}")
            
            logger.debug(f"Cache stored: {link[:40]}, size: {len(_link_cache)}/{CACHE_MAX_SIZE}")
    except Exception as e:
        logger.warning(f"Cache set error: {e}")


def get_estimated_wait_time(position: int) -> int:
    """
    Calculate estimated wait time in seconds based on queue position.
    Uses average processing time from completed jobs.
    """
    try:
        avg_time = get_avg_processing_time()
        # Position 1 = no wait (next to be processed)
        # Position 2 = avg_time seconds wait
        estimated = (position - 1) * avg_time
        return int(max(0, estimated))
    except Exception as e:
        logger.warning(f"Failed to calculate wait time: {e}")
        return position * 10  # Safe default: position * 10 seconds


# ============================================
# SHARED UTILITY FUNCTIONS
# ============================================

def get_valid_video_domains() -> list:
    """Get list of supported video platforms."""
    return [
        'tiktok.com',
        'vm.tiktok.com',
        'vt.tiktok.com',
        'youtube.com',
        'youtu.be',
        'instagram.com',
        'twitter.com',
        'x.com'
    ]


def extract_links(text: str) -> list:
    """Extract ALL URLs from text. Returns list of URLs."""
    try:
        # Regex to match URLs
        url_pattern = r'https?://[^\s]+'
        links = re.findall(url_pattern, text)
        logger.debug(f"Extracted {len(links)} links from text")
        return links
    except Exception as e:
        logger.warning(f"Failed to extract links: {e}")
        return []


def get_valid_links(links: list) -> list:
    """Filter links to only valid video platforms. Returns list of valid URLs."""
    valid_domains = get_valid_video_domains()
    valid_links = []
    
    try:
        for link in links:
            # Check if any valid domain is in the link
            if any(domain in link for domain in valid_domains):
                valid_links.append(link)
                logger.debug(f"Valid link found: {link[:60]}")
            else:
                logger.debug(f"Skipped non-video link: {link[:60]}")
        
        logger.info(f"Filtered {len(links)} links → {len(valid_links)} valid")
        return valid_links
    except Exception as e:
        logger.warning(f"Failed to filter links: {e}")
        return []


def resolve_url(url: str) -> str:
    """Resolve short URLs to final destination. Returns final URL."""
    try:
        logger.debug(f"Resolving URL: {url[:60]}")
        
        # Use requests to follow redirects
        response = requests.get(url, allow_redirects=True, timeout=10)
        final_url = response.url
        
        logger.debug(f"Resolved to: {final_url[:60]}")
        return final_url
    except Exception as e:
        logger.warning(f"Failed to resolve URL: {e}, returning original")
        return url


def is_valid_tiktok_url(url: str) -> bool:
    """Validate TikTok URL format."""
    tiktok_patterns = [
        r'https?://(?:www\.)?tiktok\.com/@[\w.-]+/video/\d+',
        r'https?://(?:vm|vt)\.tiktok\.com/\w+',
        r'https?://(?:www\.)?tiktok\.com/(?:video/\d+|@[\w.-]+)',
    ]
    return any(re.match(pattern, url) for pattern in tiktok_patterns)


# ============================================
# PRODUCTION RESILIENCE: 3-LAYER FALLBACK SYSTEM
# ============================================

def classify_download_error(error_output: str, error_type: str = "") -> str:
    """
    Classify download errors to provide better user feedback.
    Returns error type: 'private', 'blocked', 'rate_limited', 'timeout', 'format', 'unknown'
    """
    error_lower = (error_output + error_type).lower()
    
    # Private/restricted video
    if any(x in error_lower for x in ['private', 'unavailable', 'removed', 'deleted']):
        return 'private'
    
    # Region blocked or geo-restricted
    if any(x in error_lower for x in ['403', 'forbidden', 'region', 'geo', 'blocked']):
        return 'blocked'
    
    # Rate limited
    if any(x in error_lower for x in ['429', 'rate limit', 'too many requests', 'throttle']):
        return 'rate_limited'
    
    # Timeout
    if any(x in error_lower for x in ['timeout', 'timed out', 'connection timeout']):
        return 'timeout'
    
    # Format extraction error
    if any(x in error_lower for x in ['no video format', 'not found', 'extract', 'format']):
        return 'format'
    
    return 'unknown'


def _has_ffmpeg() -> bool:
    """Check if ffmpeg is available in system PATH."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            timeout=5,
            text=True
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _convert_to_mp3(input_file: str, output_file: str) -> bool:
    """
    Convert audio file to MP3 using ffmpeg.
    Returns True if successful, False if ffmpeg unavailable or conversion failed.
    
    CRITICAL: Cleans up input file in finally block to prevent accumulation
    of intermediate files that causes next request failure.
    """
    if not _has_ffmpeg():
        logger.warning("FFmpeg not found - skipping post-processing")
        return False
    
    try:
        ffmpeg_cmd = [
            "ffmpeg",
            "-i", input_file,
            "-vn",
            "-acodec", "libmp3lame",
            "-ab", "192k",
            "-ar", "16000",
            "-ac", "1",
            "-y",
            output_file
        ]
        
        result = subprocess.run(
            ffmpeg_cmd,
            capture_output=True,
            timeout=60,
            text=True
        )
        
        if result.returncode == 0:
            return True
        else:
            logger.warning(f"FFmpeg conversion failed: {result.stderr[:100]}")
            return False
    except subprocess.TimeoutExpired:
        logger.warning("FFmpeg conversion timeout")
        return False
    except Exception as e:
        logger.warning(f"FFmpeg conversion error: {str(e)}")
        return False
    finally:
        # CRITICAL: Clean up input file to prevent accumulation
        # This ensures intermediate temp_layer files don't persist
        # and cause "second request fails" issues
        try:
            if os.path.exists(input_file):
                time.sleep(0.05)  # Windows file handle release
                os.remove(input_file)
                logger.debug(f"Cleanup: Removed intermediate file")
        except:
            pass


def download_audio_with_fallback(url: str, output_path: str) -> bool:
    """
    Download audio with 3-layer fallback system.
    
    LAYER 1: yt-dlp + bestaudio/best format + desktop UA + FFmpeg if available
    LAYER 2: yt-dlp + worstaudio/best format + mobile UA + no FFmpeg
    LAYER 3: yt-dlp + best format + generic UA + minimal options
    
    Args:
        url: Video URL to download
        output_path: Full path where audio.mp3 should be written
    
    Returns:
        True if successful, False if all layers fail
    
    CRITICAL: Proper cleanup and synchronization ensures next request
    doesn't encounter file handle conflicts from previous yt-dlp processes.
    """
    # SAFETY: Ensure no concurrent processes from previous request
    time.sleep(0.1)  # Windows file handle release delay
    
    # Remove existing output if present
    if os.path.exists(output_path):
        try:
            os.remove(output_path)
            time.sleep(0.05)  # Force file handle release
        except:
            pass
    
    # Setup temp folder for intermediate files (same folder as output)
    temp_folder = os.path.dirname(output_path)
    
    # Check for cookies
    cookies_file = 'cookies.txt'
    has_cookies = os.path.isfile(cookies_file)
    
    # Check ffmpeg availability
    has_ffmpeg = _has_ffmpeg()
    
    # User agents for different layers
    user_agents = {
        'layer1': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        'layer2': "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148",
        'layer3': "Mozilla/5.0 (Linux; Android 11; SM-G191B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
    }
    
    last_error = ""
    
    # ========================================
    # LAYER 1: PRIMARY (best format + desktop UA + FFmpeg)
    # ========================================
    try:
        logger.info("[DOWNLOAD] LAYER 1 (Primary - bestaudio/best + desktop UA + FFmpeg)")
        
        # Use yt-dlp to extract audio directly to MP3 if ffmpeg available
        if has_ffmpeg:
            yt_dlp_args = [
                "yt-dlp",
                "-f", "bestaudio/best",
                "-x",
                "--audio-format", "mp3",
                "--audio-quality", "192",
                "-o", output_path,
                "--no-warnings",
                "--quiet",
                "--socket-timeout", "30",
                "--retries", "3",
                "--fragment-retries", "3",
                "--sleep-requests", "1",
                "--user-agent", user_agents['layer1'],
                "--extractor-args", "tiktok:api_hostname=api16-normal-useast5.us.tiktokv.com",
                url
            ]
        else:
            # Download without extraction, will convert manually
            temp_file = os.path.join(temp_folder, "temp_layer1.%(ext)s")
            yt_dlp_args = [
                "yt-dlp",
                "-f", "bestaudio/best",
                "-o", temp_file,
                "--no-warnings",
                "--quiet",
                "--socket-timeout", "30",
                "--retries", "3",
                "--fragment-retries", "3",
                "--user-agent", user_agents['layer1'],
                "--extractor-args", "tiktok:api_hostname=api16-normal-useast5.us.tiktokv.com",
                url
            ]
        
        if has_cookies:
            yt_dlp_args.insert(1, "--cookies")
            yt_dlp_args.insert(2, cookies_file)
        
        result = subprocess.run(
            yt_dlp_args,
            capture_output=True,
            timeout=120,
            text=True
        )
        last_error = result.stderr
        
        # CRITICAL: Subprocess cleanup - ensure process handles released
        time.sleep(0.1)  # Windows subprocess cleanup
        
        if result.returncode == 0:
            # If ffmpeg extraction succeeded
            if has_ffmpeg and os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
                file_size = os.path.getsize(output_path)
                logger.info(f"[DOWNLOAD] LAYER 1 OK ({file_size} bytes, desktop + ffmpeg)")
                return True
            
            # If no ffmpeg, look for downloaded file and convert
            if not has_ffmpeg:
                # SAFETY: File system flush
                time.sleep(0.1)
                for file in os.listdir(temp_folder):
                    if file.startswith("temp_layer1") and file.endswith(('.m4a', '.aac', '.opus', '.webm')):
                        temp_audio = os.path.join(temp_folder, file)
                        if _convert_to_mp3(temp_audio, output_path):
                            # _convert_to_mp3 cleanup removes temp_audio in finally block
                            if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
                                file_size = os.path.getsize(output_path)
                                logger.info(f"[DOWNLOAD] LAYER 1 OK ({file_size} bytes, desktop + manual convert)")
                                return True
        
        logger.warning(f"[DOWNLOAD] LAYER 1 FAILED: {last_error[:100]}")
    
    except subprocess.TimeoutExpired:
        logger.warning("[DOWNLOAD] LAYER 1 TIMEOUT: 120s exceeded")
    except Exception as e:
        logger.warning(f"[DOWNLOAD] LAYER 1 EXCEPTION: {str(e)[:100]}")
    
    # ========================================
    # LAYER 2: FALLBACK (worstaudio + mobile UA + no FFmpeg)
    # ========================================
    try:
        logger.info("[DOWNLOAD] LAYER 2 (Fallback - worstaudio + mobile UA)")
        
        temp_file = os.path.join(temp_folder, "temp_layer2.%(ext)s")
        yt_dlp_args = [
            "yt-dlp",
            "-f", "worstaudio/best",
            "-o", temp_file,
            "--no-warnings",
            "--quiet",
            "--socket-timeout", "30",
            "--retries", "2",
            "--fragment-retries", "2",
            "--sleep-requests", "1",
            "--user-agent", user_agents['layer2'],
            "--extractor-args", "tiktok:api_hostname=api22.tiktok.com",
            url
        ]
        
        if has_cookies:
            yt_dlp_args.insert(1, "--cookies")
            yt_dlp_args.insert(2, cookies_file)
        
        result = subprocess.run(
            yt_dlp_args,
            capture_output=True,
            timeout=120,
            text=True
        )
        last_error = result.stderr
        
        # CRITICAL: Subprocess cleanup
        time.sleep(0.1)  # Windows subprocess cleanup
        
        if result.returncode == 0:
            # Try to convert downloaded file
            time.sleep(0.1)  # SAFETY: File system flush
            for file in os.listdir(temp_folder):
                if file.startswith("temp_layer2") and file.endswith(('.m4a', '.aac', '.opus', '.webm', '.mp4')):
                    temp_audio = os.path.join(temp_folder, file)
                    if _convert_to_mp3(temp_audio, output_path):
                        # _convert_to_mp3 cleanup removes temp_audio in finally block
                        if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
                            file_size = os.path.getsize(output_path)
                            logger.info(f"[DOWNLOAD] LAYER 2 OK ({file_size} bytes, mobile UA)")
                            return True
        
        logger.warning(f"[DOWNLOAD] LAYER 2 FAILED: {last_error[:100]}")
    
    except subprocess.TimeoutExpired:
        logger.warning("[DOWNLOAD] LAYER 2 TIMEOUT: 120s exceeded")
    except Exception as e:
        logger.warning(f"[DOWNLOAD] LAYER 2 EXCEPTION: {str(e)[:100]}")
    
    # ========================================
    # LAYER 3: FINAL FALLBACK (best + generic UA + minimal)
    # ========================================
    try:
        logger.info("[DOWNLOAD] LAYER 3 (Final fallback - best format + minimal options)")
        
        temp_file = os.path.join(temp_folder, "temp_layer3.%(ext)s")
        yt_dlp_args = [
            "yt-dlp",
            "-f", "best",
            "-o", temp_file,
            "--no-warnings",
            "--quiet",
            "--socket-timeout", "30",
            "--retries", "1",
            "--user-agent", user_agents['layer3'],
            url
        ]
        
        if has_cookies:
            yt_dlp_args.insert(1, "--cookies")
            yt_dlp_args.insert(2, cookies_file)
        
        result = subprocess.run(
            yt_dlp_args,
            capture_output=True,
            timeout=120,
            text=True
        )
        last_error = result.stderr
        
        # CRITICAL: Subprocess cleanup
        time.sleep(0.1)  # Windows subprocess cleanup
        
        if result.returncode == 0:
            # Try to convert downloaded file
            time.sleep(0.1)  # SAFETY: File system flush
            for file in os.listdir(temp_folder):
                if file.startswith("temp_layer3") and file.endswith(('.m4a', '.aac', '.opus', '.webm', '.mp4', '.mkv')):
                    temp_audio = os.path.join(temp_folder, file)
                    if _convert_to_mp3(temp_audio, output_path):
                        # _convert_to_mp3 cleanup removes temp_audio in finally block
                        if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
                            file_size = os.path.getsize(output_path)
                            logger.info(f"[DOWNLOAD] LAYER 3 OK ({file_size} bytes, minimal options)")
                            return True
        
        logger.warning(f"[DOWNLOAD] LAYER 3 FAILED: {last_error[:100]}")
    
    except subprocess.TimeoutExpired:
        logger.warning("[DOWNLOAD] LAYER 3 TIMEOUT: 120s exceeded")
    except Exception as e:
        logger.warning(f"[DOWNLOAD] LAYER 3 EXCEPTION: {str(e)[:100]}")
    
    # ========================================
    # ALL LAYERS FAILED
    # ========================================
    logger.error("[DOWNLOAD] FAIL ALL LAYERS - Download unsuccessful")
    logger.debug(f"[DOWNLOAD] Last error: {last_error[:200]}")
    
    # Classify error
    error_type = classify_download_error(last_error)
    logger.info(f"[DOWNLOAD] Error classified as: {error_type}")
    
    return False


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
            "-f", "bestaudio/best",  # Prioritize audio for transcription
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


def get_temp_folder(request_id: str) -> str:
    """
    Get isolated temp folder path for a request_id.
    Ensures each job has its own folder to prevent conflicts.
    Example: temp/a1b2c3d4/
    
    SAFETY: Pre-cleans any stale files from failed previous requests
    with same ID to prevent file handle conflicts.
    """
    folder = os.path.join(TEMP_DIR, request_id)
    
    # If folder exists from previous run, clean stale temp files first
    # This prevents file handle conflicts on Windows from leftover processes
    if os.path.exists(folder):
        try:
            for file in os.listdir(folder):
                if file.startswith('temp_'):
                    fpath = os.path.join(folder, file)
                    try:
                        time.sleep(0.05)  # Windows file handle release
                        if os.path.isfile(fpath):
                            os.remove(fpath)
                            logger.debug(f"[{request_id}] Cleaned stale: {file}")
                    except:
                        pass
        except:
            pass
    
    os.makedirs(folder, exist_ok=True)
    return folder


def cleanup_files(video_path: str, audio_path: str, request_id: str = "system") -> None:
    """Safely cleanup ALL temporary files from request.
    
    CRITICAL: Aggressively removes intermediate layer files to prevent
    accumulation and file handle exhaustion on next request. This is
    essential for multi-request stability.
    """
    # Remove specified files
    for path in [video_path, audio_path]:
        if not path:
            continue
        try:
            if os.path.exists(path):
                os.remove(path)
                logger.info(f"[{request_id}] Cleaned: {path}")
        except Exception as e:
            logger.warning(f"[{request_id}] Cleanup failed: {str(e)[:80]}")
    
    # CRITICAL: Aggressively clean all intermediate layer files
    # This prevents accumulation of temp_layer*.* files that consume handles
    try:
        temp_folder = os.path.join(TEMP_DIR, request_id)
        if os.path.exists(temp_folder):
            for file in os.listdir(temp_folder):
                # target: temp_layer1.*, temp_layer2.*, temp_layer3.*
                # and any remaining media files
                if file.startswith('temp_') or file.endswith(('.mp4', '.m4a', '.webm', '.opus', '.aac')):
                    fpath = os.path.join(temp_folder, file)
                    try:
                        time.sleep(0.05)  # Windows file handle release
                        if os.path.isfile(fpath):
                            os.remove(fpath)
                            logger.debug(f"[{request_id}] Cleaned layer file: {file}")
                    except Exception as fe:
                        logger.debug(f"[{request_id}] Could not remove {file}: {fe}")
    except Exception as e:
        logger.debug(f"[{request_id}] Aggressive cleanup error: {e}")
    
    # Finally, try to remove isolated temp folder if now empty
    try:
        temp_folder = os.path.join(TEMP_DIR, request_id)
        if os.path.exists(temp_folder):
            time.sleep(0.1)  # Wait for any lingering processes
            if not os.listdir(temp_folder):  # Only if empty
                os.rmdir(temp_folder)
                logger.debug(f"[{request_id}] Cleaned temp folder")
            else:
                logger.debug(f"[{request_id}] Temp folder not empty, leaving for cleanup")
    except Exception as e:
        logger.debug(f"[{request_id}] Could not remove temp folder: {e}")


def cleanup_old_temp_files() -> None:
    """Clean up leftover temp files and folders on startup."""
    try:
        if os.path.exists(TEMP_DIR):
            # Remove old request-id folders (older than 1 hour)
            import shutil
            from pathlib import Path
            current_time = time.time()
            
            for folder in os.listdir(TEMP_DIR):
                fpath = os.path.join(TEMP_DIR, folder)
                if os.path.isdir(fpath):
                    try:
                        # Get folder modification time
                        mod_time = os.path.getmtime(fpath)
                        age = current_time - mod_time
                        
                        # Remove if older than 1 hour
                        if age > 3600:
                            shutil.rmtree(fpath)
                            logger.info(f"Cleaned old temp folder: {folder}")
                    except:
                        pass
                elif os.path.isfile(fpath):
                    # Remove orphaned files
                    try:
                        os.remove(fpath)
                        logger.info(f"Cleaned orphaned: {fpath}")
                    except:
                        pass
    except:
        pass


def process_transcription(url: str, request_id: str = "system", progress_callback=None) -> str:
    """
    Core transcription workflow - shared by both Telegram and Web.
    progress_callback: async function(stage_name) called at each processing stage
    Uses isolated temp folder per request_id to prevent conflicts.
    Integrated with 3-layer fallback system for robust audio extraction.
    
    CRITICAL: Handles duplicates via wait+poll, NOT exceptions
    """
    try:
        if not is_valid_tiktok_url(url):
            logger.warning(f"[{request_id}] Invalid TikTok URL")
            raise Exception("Invalid TikTok URL")
        
        # DUPLICATE PROCESSING PREVENTION - NEW FLOW
        # Step 1: Check memory cache FIRST (fastest)
        cached_result = cache_get(url)
        if cached_result:
            logger.info(f"[{request_id}] Memory cache hit - returning instantly")
            return cached_result
        
        # Step 2: Check if already processing (duplicate detection)
        # If yes, WAIT for result without raising exception
        with _processing_lock:
            if url in _processing_links:
                logger.info(f"[{request_id}] Duplicate detected - waiting for result")
                # Don't add to processing_links, just wait for the first request
                # Release lock before waiting
        
        # If duplicate was detected, wait for result without raising exception
        if url in _processing_links:
            logger.info(f"[{request_id}] Waiting for duplicate processing to complete")
            for wait_attempt in range(60):  # Wait up to 60 seconds
                time.sleep(1)
                
                # Check cache for result
                cached_result = cache_get(url)
                if cached_result:
                    logger.info(f"[{request_id}] Duplicate resolved - got result after {wait_attempt+1}s")
                    return cached_result
            
            # Timeout waiting for duplicate
            logger.error(f"[{request_id}] Timeout waiting for duplicate result (60s)")
            raise Exception("Processing timeout - link is taking too long on another request")
        
        # Step 3: Mark as processing (only if not a duplicate)
        with _processing_lock:
            _processing_links.add(url)
            logger.debug(f"[{request_id}] Added link to processing set. Active: {len(_processing_links)}")

        # PRODUCTION HARDENING: Use isolated temp folder per request_id
        temp_folder = get_temp_folder(request_id)
        audio_path = os.path.join(temp_folder, "audio.mp3")

        try:
            # Step 1: Download with 3-layer fallback system
            logger.info(f"[{request_id}] Starting download with fallback protection")
            
            # SAFETY: Only invoke progress_callback in async context
            if progress_callback:
                try:
                    asyncio.create_task(progress_callback("downloading"))
                except RuntimeError:
                    logger.debug(f"[{request_id}] No event loop for callback, continuing")
            
            # Use new robust fallback system - returns bool
            success = download_audio_with_fallback(url, audio_path)
            
            if not success:
                raise Exception("Could not process this link. It may be private, restricted, unsupported, or temporarily unavailable. Try another video.")

            # Step 2: Transcribe
            logger.info(f"[{request_id}] Starting transcription")
            
            # SAFETY: Only invoke progress_callback in async context
            if progress_callback:
                try:
                    asyncio.create_task(progress_callback("transcribing"))
                except RuntimeError:
                    logger.debug(f"[{request_id}] No event loop for callback, continuing")
            
            transcript = transcribe(audio_path, request_id)
            
            if not transcript:
                raise Exception("Transcription failed or returned empty")

            # Cache result before returning
            cache_set(url, transcript)
            logger.info(f"[{request_id}] Cached result - {len(transcript)} chars")
            
            logger.info(f"[{request_id}] Processing complete - {len(transcript)} chars")
            return transcript

        finally:
            # DUPLICATE PROCESSING PREVENTION: Remove from active processing set
            try:
                with _processing_lock:
                    _processing_links.discard(url)
                    logger.debug(f"[{request_id}] Removed link from processing set. Active: {len(_processing_links)}")
            except:
                pass
            
            # CRITICAL: Always cleanup
            cleanup_files(audio_path, "", request_id)
            
            # Also explicitly remove temp folder contents
            try:
                temp_folder = os.path.join(TEMP_DIR, request_id)
                if os.path.exists(temp_folder):
                    for file in os.listdir(temp_folder):
                        try:
                            fpath = os.path.join(temp_folder, file)
                            if os.path.isfile(fpath):
                                time.sleep(0.05)
                                os.remove(fpath)
                        except:
                            pass
                    # Try to remove folder once empty
                    try:
                        time.sleep(0.1)
                        if not os.listdir(temp_folder):
                            os.rmdir(temp_folder)
                    except:
                        pass
            except:
                pass

    except Exception as e:
        error_msg = str(e)
        logger.error(f"[{request_id}] Processing failed - {error_msg}")
        raise


# ============================================
# TELEGRAM BOT HANDLERS
# ============================================

async def handle_telegram_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming Telegram messages - now supports multiple links with job reuse."""
    async with request_semaphore:
        user_id = str(update.message.from_user.id)
        
        try:
            text = update.message.text.strip()
            logger.info(f"[MSG] Processing message from user {user_id}")
            
            # FEATURE 1: Smart link extraction
            all_links = extract_links(text)
            logger.debug(f"[MSG] Extracted {len(all_links)} links from message")
            
            if not all_links:
                await update.message.reply_text(
                    "ERROR: No links found.\n\n"
                    "Please send a message with a valid video link:\n\n"
                    "Supported platforms:\n"
                    "- TikTok (tiktok.com, vm.tiktok.com)\n"
                    "- YouTube (youtube.com, youtu.be)\n"
                    "- Instagram\n"
                    "- Twitter/X\n\n"
                    "Use /help for more commands."
                )
                return
            
            # FEATURE 2: Filter valid video links
            valid_links = get_valid_links(all_links)
            logger.debug(f"[MSG] Found {len(valid_links)} valid video links")
            
            if not valid_links:
                await update.message.reply_text(
                    "ERROR: No valid video links found.\n\n"
                    "I support: TikTok, YouTube, Instagram, Twitter/X\n"
                    "Use /help for examples."
                )
                return
            
            # FEATURE 2: Enforce max 3 links per message
            if len(valid_links) > 3:
                await update.message.reply_text(
                    f"WARNING: You sent {len(valid_links)} links, but max is 3 per message.\n"
                    f"I'll process the first 3."
                )
                valid_links = valid_links[:3]
            
            # Process each link sequentially
            processed_count = 0
            for idx, link in enumerate(valid_links, 1):
                try:
                    request_id = str(uuid.uuid4())[:8]
                    logger.info(f"[{request_id}] Processing link {idx}/{len(valid_links)}: {link[:50]}")
                    
                    # FEATURE 3: Normalize URL (resolve redirects)
                    normalized_link = resolve_url(link)
                    logger.info(f"[{request_id}] Normalized to: {normalized_link[:60]}")
                    
                    # SMART JOB QUEUE: Check if job is already being processed or completed
                    job_status = get_job_status(normalized_link)
                    
                    # PRODUCTION HARDENING: Check in-memory cache first (reduces DB calls)
                    cached_result = cache_get(normalized_link)
                    if cached_result:
                        logger.info(f"[{request_id}] FAST Memory cache hit - returning instantly")
                        transcript = cached_result
                        
                        await update.message.reply_text(
                            "FAST Already processed! Returning from memory.\n\n"
                            "Processing time: <1 second"
                        )
                    # SMART QUEUE: If job is already completed in queue, return result
                    elif job_status.get('status') == 'completed':
                        logger.info(f"[{request_id}] FAST Job queue hit - job already completed")
                        transcript = job_status['result']
                        cache_set(normalized_link, transcript)  # Refresh memory cache
                        
                        await update.message.reply_text(
                            "FAST Already processed! Returning completed result.\n\n"
                            "Processing time: <1 second (from queue)"
                        )
                    # SMART QUEUE: If job is currently processing, register as waiting user
                    elif job_status.get('status') == 'processing':
                        logger.info(f"[{request_id}] Smart queue: Job already processing - registering as waiting user")
                        
                        # Register this user to be notified when job completes
                        register_waiting_user(normalized_link, {
                            'type': 'telegram',
                            'user_id': user_id,
                            'chat_id': update.message.chat_id,
                            'message_id': update.message.message_id
                        })
                        
                        await update.message.reply_text(
                            "INFO Someone else is already processing this link.\n"
                            "You'll be notified when their processing completes.\n"
                            "No duplicate processing needed!"
                        )
                        continue
                    # FEATURE 4: Job reuse - check if already processed (DB fallback)
                    elif (existing_job := get_job_by_link(normalized_link)) and existing_job.get('result'):
                        logger.info(f"[{request_id}] FAST Database cache hit - returning saved result")
                        transcript = existing_job['result']
                        
                        # Store in memory cache and job queue for future requests
                        cache_set(normalized_link, transcript)
                        create_job_entry(normalized_link, existing_job['id'] or request_id)
                        complete_job(normalized_link, result=transcript)
                        
                        await update.message.reply_text(
                            "FAST Already processed! Returning saved result.\n\n"
                            f"Processed: {existing_job['created_at'][:10]}"
                        )
                    else:
                        # New processing required
                        logger.info(f"[{request_id}] Cache miss - processing new link")
                        
                        # Create job queue entry to track this processing
                        create_job_entry(normalized_link, request_id)
                        
                        # Create job in database with NORMALIZED link for caching
                        try:
                            create_job(request_id, user_id, normalized_link)
                            logger.debug(f"[{request_id}] Saved normalized link to database: {normalized_link[:60]}")
                        except Exception as e:
                            logger.warning(f"[{request_id}] Database operation failed: {e}")
                        
                        # FEATURE 5: Show queue position + estimated wait time
                        try:
                            position = get_queue_position(request_id)
                            if position and position > 0:
                                logger.info(f"[{request_id}] QUEUE Position: {position}")
                                
                                # Calculate estimated wait time
                                wait_time = get_estimated_wait_time(position)
                                wait_str = f"{wait_time}s" if wait_time < 60 else f"{wait_time // 60}m {wait_time % 60}s"
                                
                                # Initial queue message with position and estimate
                                status_msg = await update.message.reply_text(
                                    f"WAITING Queued successfully!\n"
                                    f"POSITION {position}\n"
                                    f"ESTIMATED {wait_str}\n"
                                    f"You'll be notified when processing starts."
                                )
                            else:
                                status_msg = await update.message.reply_text(
                                    f"WAITING Queued successfully!\n"
                                    f"Processing will start shortly."
                                )
                        except Exception as e:
                            logger.warning(f"[{request_id}] Failed to show queue position: {e}")
                            status_msg = await update.message.reply_text(
                                f"WAITING Queued successfully!\n"
                                f"Processing will start shortly."
                            )
                        
                        # Update job status to processing
                        try:
                            update_job_status(request_id, "processing")
                        except Exception as e:
                            logger.warning(f"[{request_id}] Failed to update status: {e}")
                        
                        # FEATURE 6: Message editing for progress updates
                        async def update_progress(stage: str):
                            """Update Telegram message with current processing stage."""
                            try:
                                stage_messages = {
                                    "downloading": "DOWNLOADING video...",
                                    "extracting": "EXTRACTING audio...",
                                    "transcribing": "TRANSCRIBING audio...",
                                    "completed": "DONE Processing complete!"
                                }
                                
                                message_text = stage_messages.get(stage, f"PROCESSING: {stage}...")
                                logger.info(f"[{request_id}] {message_text}")
                                
                                # Try to edit the message
                                try:
                                    await status_msg.edit_text(message_text)
                                except Exception as edit_e:
                                    # If edit fails, send new message
                                    logger.debug(f"[{request_id}] Message edit failed, sending new message: {edit_e}")
                                    try:
                                        await update.message.reply_text(message_text)
                                    except:
                                        pass
                            except Exception as e:
                                logger.warning(f"[{request_id}] Failed to update progress: {e}")
                        
                        try:
                            # Process transcription with progress callback
                            # Note: Duplicates are handled transparently within process_transcription
                            transcript = process_transcription(
                                normalized_link, 
                                request_id,
                                progress_callback=update_progress
                            )
                            
                            # Save result to database
                            try:
                                save_result(request_id, transcript)
                                logger.info(f"[{request_id}] Result saved to database")
                                
                                # PRODUCTION HARDENING: Cache in memory for instant future lookups
                                cache_set(normalized_link, transcript)
                                
                                # SMART JOB QUEUE: Mark job as completed and notify waiting users
                                complete_job(normalized_link, result=transcript)
                                
                                # Notify all waiting users
                                waiting_users = get_waiting_users(normalized_link)
                                if waiting_users:
                                    logger.info(f"[{request_id}] Notifying {len(waiting_users)} waiting users")
                                    for user in waiting_users:
                                        try:
                                            if user['type'] == 'telegram':
                                                chat_id = user['chat_id']
                                                await context.bot.send_message(
                                                    chat_id=chat_id,
                                                    text="INFO The link you were waiting for is now ready!\n"
                                                         "Your result is being prepared..."
                                                )
                                                logger.debug(f"[{request_id}] Notified user {user['user_id']}")
                                        except Exception as notify_e:
                                            logger.warning(f"[{request_id}] Notification failed: {notify_e}")
                                    
                                    # Clear waiting users after notifying
                                    clear_waiting_users(normalized_link)
                            except Exception as e:
                                logger.warning(f"[{request_id}] Failed to save result: {e}")
                            
                            # Edit final message to show completion
                            try:
                                await status_msg.edit_text("DONE! Sending your transcript...")
                            except:
                                try:
                                    await update.message.reply_text("DONE! Sending transcript...")
                                except:
                                    pass
                        
                        except Exception as e:
                            error_msg = str(e)
                            logger.error(f"[{request_id}] Processing failed - {error_msg}")
                            
                            # Save error to database
                            try:
                                save_error(request_id, error_msg)
                                logger.info(f"[{request_id}] Error saved to database")
                            except Exception as db_e:
                                logger.warning(f"[{request_id}] Failed to save error: {db_e}")
                            
                            # SMART JOB QUEUE: Mark job as failed and notify waiting users
                            complete_job(normalized_link, error=error_msg)
                            logger.info(f"[{request_id}] Job marked as failed")
                            
                            # Notify all waiting users about the failure
                            waiting_users = get_waiting_users(normalized_link)
                            if waiting_users:
                                logger.info(f"[{request_id}] Notifying {len(waiting_users)} of failure")
                                for user in waiting_users:
                                    try:
                                        if user['type'] == 'telegram':
                                            chat_id = user['chat_id']
                                            await context.bot.send_message(
                                                chat_id=chat_id,
                                                text=f"ERROR The link failed to process.\n"
                                                     f"Reason: {error_msg[:100]}"
                                            )
                                            logger.debug(f"[{request_id}] Notified fail - user {user['user_id']}")
                                    except Exception as notify_e:
                                        logger.warning(f"[{request_id}] Failed to notify: {notify_e}")
                                    
                                    # Clear waiting users after notifying
                                    clear_waiting_users(normalized_link)
                                
                                # Show specific error message from fallback system
                                # (includes helpful hints about private videos, rate limits, etc)
                                error_display = error_msg
                                if "Invalid TikTok URL" in error_msg:
                                    error_display = "ERROR Invalid video link. Please check the URL."
                                
                                # Update message with error
                                try:
                                    await status_msg.edit_text(error_display)
                                except:
                                    try:
                                        await update.message.reply_text(error_display)
                                    except:
                                        pass
                                
                                continue
                    
                    # Send transcript (split if too long)
                    chunks = [transcript[i:i+4000] for i in range(0, len(transcript), 4000)]
                    for chunk_idx, chunk in enumerate(chunks):
                        if len(valid_links) > 1:
                            header = f"VIDEO Link {idx}/{len(valid_links)}"
                        else:
                            header = "TRANSCRIPT"
                        
                        if len(chunks) > 1:
                            header += f" (Part {chunk_idx + 1}/{len(chunks)})"
                        
                        await update.message.reply_text(f"{header}\n\n{chunk}")
                    
                    processed_count += 1
                    logger.info(f"[{request_id}] OK Link {idx} completed")
                
                except Exception as link_error:
                    logger.error(f"[LINK {idx}] Failed to process: {str(link_error)}", exc_info=True)
                    try:
                        await update.message.reply_text(f"ERROR Failed to process link {idx}. Try another video.")
                    except:
                        pass
            
            logger.info(f"[MSG] Completed: {processed_count}/{len(valid_links)} links")

        except Exception as e:
            logger.error(f"[TELEGRAM] Handler error: {str(e)}", exc_info=True)
            try:
                await update.message.reply_text(f"ERROR {str(e)[:80]}")
            except:
                pass


async def handle_telegram_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    user_id = str(update.message.from_user.id)
    await update.message.reply_text(
        "VIDEO ClipScript AI\n\n"
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
            await update.message.reply_text("LIST No previous jobs found.\n\nSend a TikTok link to get started!")
            return
        
        status_emoji = get_status_emoji(job['status'])
        link_short = shorten_url(job['link'])
        
        response = f"{status_emoji} STATUS: {job['status'].upper()}\n"
        response += f"LINK: {link_short}\n"
        response += f"CREATED: {job['created_at'][:16]}\n"
        
        if job['status'] == 'completed' and job['result']:
            result_preview = job['result'][:100] + "..." if len(job['result']) > 100 else job['result']
            response += f"\nTRANSCRIPT:\n{result_preview}"
        elif job['status'] == 'failed' and job['error']:
            response += f"\nERROR: {job['error'][:80]}"
        
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
            await update.message.reply_text("LIST No history yet.\n\nSend a TikTok link to get started!")
            return
        
        response = "LIST Your Last 5 Requests:\n\n"
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
        "GUIDE How to Use ClipScript AI\n\n"
        "TRANSCRIBE:\n"
        "Simply send me any TikTok link:\n"
        "- https://www.tiktok.com/@username/video/123456\n"
        "- https://vm.tiktok.com/abc123xyz\n"
        "- https://vt.tiktok.com/xyz\n\n"
        "COMMANDS:\n"
        "/status - View your current job\n"
        "/history - View last 5 requests\n"
        "/help - Show this help message\n\n"
        "SPEED:\n"
        "FAST Most videos: 5-15 seconds\n"
        "FAST Longer videos: up to 30 seconds\n\n"
        "BACKEND:\n"
        "Uses Deepgram for accurate transcription\n"
        "Uses FFmpeg for audio extraction\n"
        "Uses yt-dlp for video download"
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
    """Serve the web UI (index.html from frontend folder)."""
    try:
        # Support both repo-root execution and subdirectory (Railway root-dir) execution
        current_dir = os.path.dirname(__file__)
        repo_root = os.path.dirname(current_dir)
        candidate_folders = [
            os.path.join(repo_root, 'frontend'),            # new clean structure
            os.path.join(repo_root, 'ClipScript AI web'),   # legacy repo layout
            os.path.join(current_dir, 'web'),               # optional co-located web folder
            os.path.join(current_dir, '..', 'frontend'),    # if backend is subdirectory
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


@app.route('/test', methods=['GET'])
def test():
    """Simple test endpoint to verify API is responding with JSON."""
    logger.info("[TEST] Health check called")
    return jsonify({
        'status': 'ok',
        'message': 'API is working correctly',
        'timestamp': time.time(),
        'environment': 'production' if os.getenv('FLASK_ENV') == 'production' else 'development'
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


@app.route('/api/transcribe', methods=['POST', 'OPTIONS'])
def api_transcribe():
    """Web API endpoint - now supports multiple links with job reuse."""
    # Handle CORS preflight
    if request.method == 'OPTIONS':
        return jsonify({'status': 'ok'}), 200
    
    user_id = request.remote_addr
    logger.info(f"[API] Request from {user_id}")
    
    try:
        data = request.get_json()
        logger.debug(f"[API] Received data: {data}")
        
        if not data:
            logger.warning("[API] No JSON data provided")
            return jsonify({
                'success': False,
                'error': 'No JSON body provided'
            }), 400
        
        # Support both single 'link' and multiple 'links' fields
        link_input = data.get('link', '').strip() if data else ''
        links_input = data.get('links', []) if data else []
        
        # Combine into list
        if link_input:
            links_input = [link_input] + (links_input if isinstance(links_input, list) else [])
        elif not isinstance(links_input, list):
            links_input = []
        
        # Extract and validate links
        all_links = []
        for link_str in links_input:
            all_links.extend(extract_links(link_str))
        
        logger.debug(f"[API] Extracted {len(all_links)} links")
        
        if not all_links:
            logger.warning(f"[API] No links found in request")
            return jsonify({'error': 'No links provided'}), 400
        
        # Filter valid video links
        valid_links = get_valid_links(all_links)
        
        if not valid_links:
            logger.warning(f"[API] No valid video links found")
            return jsonify({'error': 'No valid video links found'}), 400
        
        # Enforce max 3 links
        if len(valid_links) > 3:
            logger.warning(f"[API] Too many links: {len(valid_links)}, limiting to 3")
            valid_links = valid_links[:3]
        
        # Process each link
        results = []
        
        for idx, link in enumerate(valid_links, 1):
            try:
                request_id = str(uuid.uuid4())[:8]
                logger.info(f"[{request_id}] API processing link {idx}/{len(valid_links)}: {link[:50]}")
                
                # Normalize URL
                normalized_link = resolve_url(link)
                logger.info(f"[{request_id}] Normalized to: {normalized_link[:60]}")
                
                # Check job reuse
                existing_job = get_job_by_link(normalized_link)
                
                if existing_job and existing_job.get('result'):
                    logger.info(f"[{request_id}] FAST Cache hit - returning saved result")
                    transcript = existing_job['result']
                    cache_hit = True
                else:
                    logger.info(f"[{request_id}] Cache miss - processing new link")
                    
                    # Create job with NORMALIZED link for caching
                    try:
                        create_job(request_id, user_id, normalized_link)
                        update_job_status(request_id, "processing")
                        logger.debug(f"[{request_id}] Saved normalized link to database: {normalized_link[:60]}")
                    except Exception as e:
                        logger.warning(f"[{request_id}] Database failed: {e}")
                    
                    # Process transcription (handles duplicates transparently)
                    try:
                        transcript = process_transcription(normalized_link, request_id)
                    except Exception as processing_error:
                        raise processing_error
                    
                    # Save result
                    try:
                        save_result(request_id, transcript)
                    except Exception as e:
                        logger.warning(f"[{request_id}] Failed to save result: {e}")
                    
                    cache_hit = False
                
                results.append({
                    'success': True,
                    'link': normalized_link,
                    'transcript': transcript,
                    'length': len(transcript),
                    'cache_hit': cache_hit
                })
                
                logger.info(f"[{request_id}] OK Processed: {len(transcript)} chars")
            
            except Exception as link_error:
                error_msg = str(link_error)
                logger.error(f"[Link {idx}] Processing failed: {error_msg}")
                
                # Only mark job as failed for real processing errors
                # (not for duplicates, which are handled transparently)
                if "DUPLICATE" not in error_msg.upper():
                    try:
                        normalized_link = resolve_url(link)
                        complete_job(normalized_link, error=error_msg)
                        logger.info(f"Job marked as failed")
                    except Exception as q_e:
                        logger.warning(f"Failed to mark job as failed: {q_e}")
                
                results.append({
                    'success': False,
                    'link': link,
                    'error': error_msg[:100]
                })
        
        logger.info(f"[API] Completed: {len([r for r in results if r['success']])}/{len(valid_links)} links")
        
        # Return results
        if len(results) == 1:
            # Single link - return simple format
            result = results[0]
            if result['success']:
                return jsonify({
                    'success': True,
                    'transcript': result['transcript'],
                    'length': result['length'],
                    'cache_hit': result.get('cache_hit', False)
                })
            else:
                error_msg = result['error']
                if "tiktok" in error_msg.lower() or "403" in error_msg:
                    return jsonify({'error': 'TikTok blocked. Try again in 5 minutes.'}), 429
                elif "timeout" in error_msg.lower():
                    return jsonify({'error': 'Processing took too long. Try a shorter video.'}), 408
                else:
                    return jsonify({'error': error_msg}), 500
        else:
            # Multiple links - return array
            return jsonify({
                'success': any(r['success'] for r in results),
                'results': results,
                'total': len(results),
                'successful': len([r for r in results if r['success']])
            })

    except Exception as e:
        error_msg = str(e)
        logger.error(f"[API] Error: {error_msg}", exc_info=True)
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
# ENVIRONMENT & STARTUP UTILITIES
# ============================================

def detect_environment():
    """Detect if running in cloud deployment or local development."""
    cloud_indicators = [
        os.getenv("PORT"),
        os.getenv("RENDER_EXTERNAL_URL"),
        os.getenv("RAILWAY_ENVIRONMENT_NAME"),
        os.getenv("HEROKU_DYNO_TYPE"),
    ]
    return any(cloud_indicators)


def get_startup_config():
    """Get configuration for local vs cloud deployment."""
    is_cloud = detect_environment()
    port = int(os.getenv("PORT", 5000))
    debug = not is_cloud  # Debug mode only in development
    environment = "CLOUD (Production)" if is_cloud else "LOCAL (Development)"
    
    return {
        "environment": environment,
        "is_cloud": is_cloud,
        "port": port,
        "debug": debug,
        "host": "0.0.0.0"
    }


def ensure_directories():
    """Ensure all required directories exist."""
    required_dirs = [
        os.path.join(os.path.dirname(__file__), "logs"),
        os.path.join(os.path.dirname(__file__), TEMP_DIR),
    ]
    for dir_path in required_dirs:
        os.makedirs(dir_path, exist_ok=True)


# ============================================
# STARTUP GUARD - Prevent duplicate bot instances
# ============================================
_TELEGRAM_POLLING_STARTED = False
_STARTUP_LOCK = threading.Lock()

def _is_reloader_process():
    """
    Check if this is a Flask reloader process (NOT the main process).
    Flask's reloader spawns child processes with WERKZEUG_RUN_MAIN env var.
    We should SKIP bot startup in reloader child processes.
    """
    return os.environ.get('WERKZEUG_RUN_MAIN') != 'true'

# ============================================
# MAIN
# ============================================

if __name__ == '__main__':
    # Ensure all required directories exist
    ensure_directories()
    
    # Get startup configuration
    config = get_startup_config()
    
    logger.info("="*70)
    logger.info(f"START ClipScript AI - Unified Backend")
    logger.info(f"CONFIG Environment: {config['environment']}")
    logger.info(f"CONFIG Transcription Service: {TRANSCRIPTION_SERVICE}")
    logger.info(f"CONFIG Server: http://{config['host']}:{config['port']}")
    logger.info(f"CONFIG Debug Mode: {config['debug']}")
    logger.info("="*70)
    
    # Initialize database
    try:
        init_db()
        logger.info("OK Database initialized successfully")
    except Exception as e:
        logger.error(f"FAIL Failed to initialize database: {e}")
        logger.warning("WARNING Continuing without persistence layer")
    
    # Cleanup orphaned files from previous runs
    cleanup_old_temp_files()
    
    # Check if webhook URL is configured
    webhook_url = os.getenv("WEBHOOK_URL") or (
        f"{os.getenv('RENDER_EXTERNAL_URL')}/telegram/webhook" 
        if os.getenv("RENDER_EXTERNAL_URL") else None
    )

    if webhook_url:
        # Production mode: Use webhook
        logger.info("CONFIG WEBHOOK MODE - Telegram webhook enabled (production)")
        setup_telegram_webhook()
        logger.info("OK Unified backend ready for Telegram (webhook) + Web API requests")
        logger.info("="*70)
        app.run(
            host=config['host'],
            port=config['port'],
            debug=False,  # MUST be False in production to prevent reloader
            use_reloader=False  # Disable reloader in production
        )
    else:
        # Development mode: Use polling
        logger.info("CONFIG POLLING MODE - Telegram polling enabled (development)")
        
        # CRITICAL: Prevent Flask reloader from spawning multiple bot instances
        # Flask's reloader creates child processes that we must detect
        is_reloader = _is_reloader_process()
        
        if is_reloader:
            logger.warning("WARNING RELOADER CHILD PROCESS - Skipping bot startup to prevent duplicate instances")
            logger.info("INFO Set FLASK_ENV=production or use_reloader=False to prevent this")
        
        # Start Flask in a background thread
        flask_thread = threading.Thread(
            target=lambda: app.run(
                host=config['host'],
                port=config['port'],
                debug=config['debug'],
                use_reloader=False  # ALWAYS disable reloader to prevent duplicate instances
            ),
            daemon=True
        )
        flask_thread.start()
        logger.info("OK Flask server started in background")
        logger.info("OK Unified backend ready for Telegram (polling) + Web API requests")
        logger.info("="*70)
        
        # GUARD: Only start Telegram polling in main process, NOT in Flask reloader children
        if not is_reloader:
            with _STARTUP_LOCK:
                # Double-check to prevent race conditions
                if not _TELEGRAM_POLLING_STARTED:
                    _TELEGRAM_POLLING_STARTED = True
                    
                    # Start Telegram polling in main thread
                    logger.info("BOT Starting Telegram bot polling...")
                    logger.info("WARNING IMPORTANT: Only ONE bot instance should be running!")
                    logger.info("INFO If you see 'Conflict: terminated by other getUpdates' errors:")
                    logger.info("    1. Check that Flask has use_reloader=False")
                    logger.info("    2. Kill any other bot instance: pkill python")
                    logger.info("    3. Restart the application")
                    
                    try:
                        asyncio.run(telegram_app.run_polling())
                    except KeyboardInterrupt:
                        logger.info("STOP Telegram polling stopped by user")
                        exit(0)
                    except Exception as e:
                        logger.error(f"Fatal polling error: {e}")
                        logger.error(f"If you see 'terminated by other getUpdates request':")
                        logger.error(f"  - Kill conflicting bot: pkill -f 'python.*app_unified'")
                        logger.error(f"  - Wait 10-15 seconds for Telegram side to clear the token")
                        logger.error(f"  - Restart the application")
                        exit(1)
                else:
                    logger.warning("INFO Skipping Telegram polling - already started")
        else:
            logger.info("INFO Flask will continue running in reloader child, Telegram polling skipped")
            # Keep reloader child alive
            try:
                while True:
                    asyncio.run(asyncio.sleep(1))
            except KeyboardInterrupt:
                exit(0)
