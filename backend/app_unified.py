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

# Setup logging (file + console, UTF-8 safe)
log_format = logging.Formatter('[%(asctime)s] %(name)s - %(levelname)s - %(message)s')

# Create logs directory
os.makedirs('logs', exist_ok=True)

# File handler
file_handler = logging.FileHandler('logs/clipscript_unified.log')
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(log_format)

# Console handler with UTF-8 encoding and error handling for emojis
try:
    # Try UTF-8 encoding for emoji support, replace errors to avoid crashes
    console_handler = logging.StreamHandler(io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace'))
except:
    # Fallback to default if utf-8 fails
    console_handler = logging.StreamHandler()
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


def download_audio_with_fallback(url: str, temp_folder: str, request_id: str = "system") -> str:
    """
    PRODUCTION RESILIENCE: Enhanced 3-layer fallback system for audio extraction.
    
    LAYER 1 (PRIMARY): yt-dlp with FFmpeg post-processor + best format
    LAYER 2 (RETRY): Mobile user-agent + alternative API hostname + worst format fallback
    LAYER 3 (GRACEFUL): Simple download without post-processor + local FFmpeg
    
    Features:
    - Cookie support (checks for cookies.txt)
    - Per-layer user-agent rotation (desktop → mobile → generic)
    - Improved TikTok extractor args with API hostname fallbacks
    - Format fallback strategy (bestaudio/best → worstaudio/worst → best)
    - Enhanced timeout and retry resilience
    - Detailed error tracking for each layer
    
    Returns: path to audio.mp3 if successful
    Raises: Exception with classified error message if all layers fail
    """
    # ========================================
    # SETUP: User agents and cookie file
    # ========================================
    user_agents = {
        'layer1': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        'layer2': "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148",
        'layer3': "Mozilla/5.0 (Linux; Android 11; SM-G191B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
    }
    
    # Check if cookies file exists
    cookies_file = 'cookies.txt'
    has_cookies = os.path.isfile(cookies_file)
    if has_cookies:
        logger.info(f"[{request_id}] 🍪 Using cookies file for authentication")
    
    audio_path = os.path.join(temp_folder, "audio.mp3")
    last_error = ""
    
    # ========================================
    # LAYER 1: PRIMARY ATTEMPT
    # Full yt-dlp with FFmpeg post-processor, best format, desktop UA
    # ========================================
    try:
        logger.info(f"[{request_id}] 🟢 LAYER 1: Primary extraction (best format + FFmpeg post-processor)")
        
        yt_dlp_args = [
            "yt-dlp",
            "-f", "bestaudio/best",  # Prioritize best audio quality
            "-o", os.path.join(temp_folder, "%(id)s.%(ext)s"),
            "--no-warnings",
            "--quiet",
            "--socket-timeout", "30",
            "--retries", "3",
            "--fragment-retries", "3",
            "--sleep-requests", "1",
            "--user-agent", user_agents['layer1'],
            "--extractor-args", "tiktok:api_hostname=api16-normal-useast5.us.tiktokv.com",
            "-x",  # Extract audio
            "--audio-format", "mp3",
            "--audio-quality", "192",
            "--postprocessor-args", "-b:a 192k -ar 16000 -ac 1",
            url
        ]
        
        # Add cookies if available
        if has_cookies:
            yt_dlp_args.insert(2, "--cookies")
            yt_dlp_args.insert(3, cookies_file)
        
        result = subprocess.run(yt_dlp_args, capture_output=True, timeout=120, text=True)
        last_error = result.stderr
        
        if result.returncode == 0:
            # Find and move the extracted mp3 file
            for file in os.listdir(temp_folder):
                if file.endswith('.mp3') and file != 'audio.mp3':
                    extracted = os.path.join(temp_folder, file)
                    shutil.move(extracted, audio_path)
                    if os.path.exists(audio_path) and os.path.getsize(audio_path) > 1000:
                        file_size = os.path.getsize(audio_path)
                        logger.info(f"[{request_id}] ✅ LAYER 1 SUCCESS ({file_size} bytes, desktop UA, cookies={has_cookies})")
                        return audio_path
            
            logger.warning(f"[{request_id}] Layer 1: Completed but no audio file produced")
        else:
            logger.warning(f"[{request_id}] 🟡 LAYER 1 FAILED: {result.stderr[:100]}")
    
    except subprocess.TimeoutExpired:
        logger.warning(f"[{request_id}] 🟡 LAYER 1 TIMEOUT: Exceeded 120 seconds")
    except Exception as e:
        logger.warning(f"[{request_id}] 🟡 LAYER 1 EXCEPTION: {str(e)[:100]}")
    
    # ========================================
    # LAYER 2: FALLBACK WITH MOBILE UA
    # Alternative API hostname + mobile user agent + format fallback
    # ========================================
    try:
        logger.info(f"[{request_id}] 🟡 LAYER 2: Fallback (mobile UA + alternative API + worstaudio format)")
        
        yt_dlp_args = [
            "yt-dlp",
            "-f", "worstaudio/worst",  # Fallback to worst quality but more compatible
            "-o", os.path.join(temp_folder, "%(id)s.%(ext)s"),
            "--no-warnings",
            "--quiet",
            "--socket-timeout", "30",
            "--retries", "2",
            "--fragment-retries", "2",
            "--sleep-requests", "2",
            "--user-agent", user_agents['layer2'],
            "--extractor-args", "tiktok:api_hostname=api22.tiktok.com",
            url
        ]
        
        # Add cookies if available
        if has_cookies:
            yt_dlp_args.insert(2, "--cookies")
            yt_dlp_args.insert(3, cookies_file)
        
        result = subprocess.run(yt_dlp_args, capture_output=True, timeout=120, text=True)
        last_error = result.stderr
        
        if result.returncode == 0:
            # Find downloaded file and convert with FFmpeg
            downloaded_file = None
            for file in os.listdir(temp_folder):
                if (file.endswith(('.m4a', '.aac', '.opus', '.webm', '.mp4', '.mkv')) and 
                    not file.startswith('video') and not file.startswith('audio')):
                    downloaded_file = os.path.join(temp_folder, file)
                    break
            
            if downloaded_file:
                logger.info(f"[{request_id}] Converting with FFmpeg (Layer 2 download)")
                ffmpeg_cmd = [
                    "ffmpeg",
                    "-i", downloaded_file,
                    "-vn",
                    "-acodec", "libmp3lame",
                    "-ab", "192k",
                    "-ar", "16000",
                    "-ac", "1",
                    "-y",
                    audio_path
                ]
                
                ffmpeg_result = subprocess.run(ffmpeg_cmd, capture_output=True, timeout=60, text=True)
                
                if ffmpeg_result.returncode == 0:
                    if os.path.exists(audio_path) and os.path.getsize(audio_path) > 1000:
                        file_size = os.path.getsize(audio_path)
                        logger.info(f"[{request_id}] ✅ LAYER 2 SUCCESS ({file_size} bytes, mobile UA + FFmpeg, cookies={has_cookies})")
                        return audio_path
                else:
                    logger.warning(f"[{request_id}] Layer 2: FFmpeg conversion failed - {ffmpeg_result.stderr[:80]}")
            else:
                logger.warning(f"[{request_id}] Layer 2: No downloadable file found")
        else:
            logger.warning(f"[{request_id}] 🟡 LAYER 2 FAILED: {result.stderr[:100]}")
    
    except subprocess.TimeoutExpired:
        logger.warning(f"[{request_id}] 🟡 LAYER 2 TIMEOUT: Exceeded time limit")
    except Exception as e:
        logger.warning(f"[{request_id}] 🟡 LAYER 2 EXCEPTION: {str(e)[:100]}")
    
    # ========================================
    # LAYER 3: FINAL FALLBACK
    # Simple download (no post-processor) + local FFmpeg, generic UA, best format
    # ========================================
    try:
        logger.info(f"[{request_id}] 🔴 LAYER 3: Final fallback (generic UA + best format)")
        
        yt_dlp_args = [
            "yt-dlp",
            "-f", "best",  # Just get the best available format
            "-o", os.path.join(temp_folder, "%(id)s.%(ext)s"),
            "--no-warnings",
            "--quiet",
            "--socket-timeout", "30",
            "--retries", "1",
            "--fragment-retries", "1",
            "--sleep-requests", "3",
            "--user-agent", user_agents['layer3'],
            url
        ]
        
        # Add cookies if available
        if has_cookies:
            yt_dlp_args.insert(2, "--cookies")
            yt_dlp_args.insert(3, cookies_file)
        
        result = subprocess.run(yt_dlp_args, capture_output=True, timeout=120, text=True)
        last_error = result.stderr
        
        if result.returncode == 0:
            # Find any downloaded file
            downloaded_file = None
            for file in os.listdir(temp_folder):
                if (file.endswith(('.m4a', '.aac', '.opus', '.webm', '.mp4', '.mkv', '.mov', '.m4v')) and 
                    not file.startswith('video') and not file.startswith('audio')):
                    downloaded_file = os.path.join(temp_folder, file)
                    break
            
            if downloaded_file:
                logger.info(f"[{request_id}] Converting with FFmpeg (Layer 3 download)")
                ffmpeg_cmd = [
                    "ffmpeg",
                    "-i", downloaded_file,
                    "-vn",
                    "-acodec", "libmp3lame",
                    "-ab", "192k",
                    "-ar", "16000",
                    "-ac", "1",
                    "-y",
                    audio_path
                ]
                
                ffmpeg_result = subprocess.run(ffmpeg_cmd, capture_output=True, timeout=60, text=True)
                
                if ffmpeg_result.returncode == 0:
                    if os.path.exists(audio_path) and os.path.getsize(audio_path) > 1000:
                        file_size = os.path.getsize(audio_path)
                        logger.info(f"[{request_id}] ✅ LAYER 3 SUCCESS ({file_size} bytes, generic UA + FFmpeg, cookies={has_cookies})")
                        return audio_path
                else:
                    logger.warning(f"[{request_id}] Layer 3: FFmpeg conversion failed - {ffmpeg_result.stderr[:80]}")
            else:
                logger.warning(f"[{request_id}] Layer 3: No downloadable file found")
        else:
            logger.warning(f"[{request_id}] 🟡 LAYER 3 FAILED: {result.stderr[:100]}")
    
    except subprocess.TimeoutExpired:
        logger.warning(f"[{request_id}] 🟡 LAYER 3 TIMEOUT: Exceeded time limit")
    except Exception as e:
        logger.warning(f"[{request_id}] 🟡 LAYER 3 EXCEPTION: {str(e)[:100]}")
    
    # ========================================
    # ALL LAYERS FAILED - GRACEFUL ERROR
    # Classify the error for the user
    # ========================================
    logger.error(f"[{request_id}] ❌ ALL LAYERS EXHAUSTED: Download failed after 3 attempts")
    logger.debug(f"[{request_id}] Last error output: {last_error[:200]}")
    
    # Classify error using last attempt's stderr
    error_type = classify_download_error(last_error)
    
    if error_type == 'private':
        msg = "⚠️ This video is private or unavailable. The creator may have hidden it."
    elif error_type == 'blocked':
        msg = "⚠️ This video is region-blocked or restricted. Try a different video."
    elif error_type == 'rate_limited':
        msg = "⚠️ Rate limited by the platform. Please wait a few minutes and try again."
    elif error_type == 'timeout':
        msg = "⏱️ Connection timeout. The video server is slow. Try again in a moment."
    elif error_type == 'format':
        msg = "⚠️ Video format not supported or couldn't be processed. Try another video."
    else:
        msg = "⚠️ Could not process this link. It may be private, restricted, or unsupported."
    
    logger.info(f"[{request_id}] Classified error: {error_type}")
    
    raise Exception(msg)


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
    """
    folder = os.path.join(TEMP_DIR, request_id)
    os.makedirs(folder, exist_ok=True)
    return folder


def cleanup_files(video_path: str, audio_path: str, request_id: str = "system") -> None:
    """Safely cleanup temporary files and folder."""
    for path in [video_path, audio_path]:
        if not path:
            continue
        try:
            if os.path.exists(path):
                os.remove(path)
                logger.info(f"[{request_id}] Cleaned: {path}")
        except Exception as e:
            logger.warning(f"[{request_id}] Cleanup failed: {str(e)[:80]}")
    
    # Clean up isolated temp folder
    try:
        temp_folder = get_temp_folder(request_id)
        # Only try to remove if empty
        if os.path.exists(temp_folder) and not os.listdir(temp_folder):
            os.rmdir(temp_folder)
            logger.debug(f"[{request_id}] Cleaned temp folder")
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
    """
    try:
        if not is_valid_tiktok_url(url):
            logger.warning(f"[{request_id}] Invalid TikTok URL")
            raise Exception("Invalid TikTok URL")

        # PRODUCTION HARDENING: Use isolated temp folder per request_id
        # Prevents conflicts when multiple jobs run concurrently
        temp_folder = get_temp_folder(request_id)
        audio_path = os.path.join(temp_folder, "audio.mp3")

        try:
            # Step 1: Download with 3-layer fallback system
            logger.info(f"[{request_id}] Starting download with fallback protection")
            if progress_callback:
                asyncio.create_task(progress_callback("downloading"))
            
            # Use new robust fallback system instead of old download_video + extract_audio
            audio_path = download_audio_with_fallback(url, temp_folder, request_id)

            # Step 2: Transcribe
            logger.info(f"[{request_id}] Starting transcription")
            if progress_callback:
                asyncio.create_task(progress_callback("transcribing"))
            
            transcript = transcribe(audio_path, request_id)
            
            if not transcript:
                raise Exception("Transcription failed or returned empty")

            logger.info(f"[{request_id}] Processing complete: {len(transcript)} chars")
            return transcript

        finally:
            # Always cleanup (audio_path is the only file we create now)
            cleanup_files(audio_path, "", request_id)

    except Exception as e:
        error_msg = str(e)
        logger.error(f"[{request_id}] Processing failed: {error_msg}")
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
                    "❌ No links found.\n\n"
                    "Please send a message with a valid video link:\n\n"
                    "Supported platforms:\n"
                    "• TikTok (tiktok.com, vm.tiktok.com)\n"
                    "• YouTube (youtube.com, youtu.be)\n"
                    "• Instagram\n"
                    "• Twitter/X\n\n"
                    "Use /help for more commands."
                )
                return
            
            # FEATURE 2: Filter valid video links
            valid_links = get_valid_links(all_links)
            logger.debug(f"[MSG] Found {len(valid_links)} valid video links")
            
            if not valid_links:
                await update.message.reply_text(
                    "❌ No valid video links found.\n\n"
                    "I support: TikTok, YouTube, Instagram, Twitter/X\n"
                    "Use /help for examples."
                )
                return
            
            # FEATURE 2: Enforce max 3 links per message
            if len(valid_links) > 3:
                await update.message.reply_text(
                    f"⚠️ You sent {len(valid_links)} links, but max is 3 per message.\n"
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
                    
                    # PRODUCTION HARDENING: Check in-memory cache first (reduces DB calls)
                    cached_result = cache_get(normalized_link)
                    if cached_result:
                        logger.info(f"[{request_id}] ⚡ Memory cache hit - returning instantly")
                        transcript = cached_result
                        
                        await update.message.reply_text(
                            "⚡ *Already processed!* Returning from memory.\n\n"
                            "Processing time: <1 second"
                        )
                    # FEATURE 4: Job reuse - check if already processed (DB fallback)
                    elif (existing_job := get_job_by_link(normalized_link)) and existing_job.get('result'):
                        logger.info(f"[{request_id}] ⚡ Database cache hit - returning saved result")
                        transcript = existing_job['result']
                        
                        # Store in memory cache for future requests
                        cache_set(normalized_link, transcript)
                        
                        await update.message.reply_text(
                            "⚡ *Already processed!* Returning saved result.\n\n"
                            f"Processed: {existing_job['created_at'][:10]}"
                        )
                    else:
                        # New processing required
                        logger.info(f"[{request_id}] Cache miss - processing new link")
                        
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
                                logger.info(f"[{request_id}] 📍 Queue position: {position}")
                                
                                # Calculate estimated wait time
                                wait_time = get_estimated_wait_time(position)
                                wait_str = f"{wait_time}s" if wait_time < 60 else f"{wait_time // 60}m {wait_time % 60}s"
                                
                                # Initial queue message with position and estimate
                                status_msg = await update.message.reply_text(
                                    f"⏳ Queued successfully!\n"
                                    f"📍 Position in queue: {position}\n"
                                    f"⏱️ Estimated wait: {wait_str}\n"
                                    f"You'll be notified when processing starts."
                                )
                            else:
                                status_msg = await update.message.reply_text(
                                    f"⏳ Queued successfully!\n"
                                    f"Processing will start shortly."
                                )
                        except Exception as e:
                            logger.warning(f"[{request_id}] Failed to show queue position: {e}")
                            status_msg = await update.message.reply_text(
                                f"⏳ Queued successfully!\n"
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
                                    "downloading": "⬇️ Downloading video...",
                                    "extracting": "🎧 Extracting audio...",
                                    "transcribing": "🧠 Transcribing audio...",
                                    "completed": "✅ Processing complete!"
                                }
                                
                                message_text = stage_messages.get(stage, f"⚙️ Processing: {stage}...")
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
                            transcript = process_transcription(
                                normalized_link, 
                                request_id,
                                progress_callback=update_progress
                            )
                            
                            # Save result to database
                            try:
                                save_result(request_id, transcript)
                                logger.info(f"[{request_id}] ✅ Result saved to database")
                                
                                # PRODUCTION HARDENING: Cache in memory for instant future lookups
                                cache_set(normalized_link, transcript)
                                logger.info(f"[{request_id}] 💾 Result cached in memory")
                            except Exception as e:
                                logger.warning(f"[{request_id}] Failed to save result: {e}")
                            
                            # Edit final message to show completion
                            try:
                                await status_msg.edit_text("✅ Done! Sending your transcript...")
                            except:
                                try:
                                    await update.message.reply_text("✅ Done! Sending transcript...")
                                except:
                                    pass
                        
                        except Exception as e:
                            error_msg = str(e)
                            logger.error(f"[{request_id}] Processing error: {error_msg}")
                            
                            # Save error to database
                            try:
                                save_error(request_id, error_msg)
                                logger.info(f"[{request_id}] ❌ Error saved to database")
                            except Exception as db_e:
                                logger.warning(f"[{request_id}] Failed to save error: {db_e}")
                            
                            # Show specific error message from fallback system
                            # (includes helpful hints about private videos, rate limits, etc)
                            error_display = error_msg
                            if "Invalid TikTok URL" in error_msg:
                                error_display = "❌ Invalid video link. Please check the URL."
                            
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
                            header = f"📹 Link {idx}/{len(valid_links)}"
                        else:
                            header = "📝 Transcript"
                        
                        if len(chunks) > 1:
                            header += f" (Part {chunk_idx + 1}/{len(chunks)})"
                        
                        await update.message.reply_text(f"{header}\n\n{chunk}")
                    
                    processed_count += 1
                    logger.info(f"[{request_id}] ✅ Link {idx} completed")
                
                except Exception as link_error:
                    logger.error(f"[LINK {idx}] Failed to process: {str(link_error)}", exc_info=True)
                    try:
                        await update.message.reply_text(f"❌ Failed to process link {idx}. Try another video.")
                    except:
                        pass
            
            logger.info(f"[MSG] Completed: {processed_count}/{len(valid_links)} links")

        except Exception as e:
            logger.error(f"[TELEGRAM] Handler error: {str(e)}", exc_info=True)
            try:
                await update.message.reply_text(f"❌ Error: {str(e)[:80]}")
            except:
                pass


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
                    logger.info(f"[{request_id}] ⚡ Cache hit - returning saved result")
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
                    
                    # Process transcription
                    transcript = process_transcription(normalized_link, request_id)
                    
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
                
                logger.info(f"[{request_id}] ✅ Processed: {len(transcript)} chars")
            
            except Exception as link_error:
                error_msg = str(link_error)
                logger.error(f"[Link {idx}] Processing failed: {error_msg}")
                
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
# MAIN
# ============================================

if __name__ == '__main__':
    # Ensure all required directories exist
    ensure_directories()
    
    # Get startup configuration
    config = get_startup_config()
    
    logger.info("="*70)
    logger.info(f"🚀 Starting ClipScript AI - Unified Backend")
    logger.info(f"📍 Environment: {config['environment']}")
    logger.info(f"🔧 Transcription Service: {TRANSCRIPTION_SERVICE}")
    logger.info(f"🌐 Server: http://{config['host']}:{config['port']}")
    logger.info(f"🐛 Debug Mode: {config['debug']}")
    logger.info("="*70)
    
    # Initialize database
    try:
        init_db()
        logger.info("✓ Database initialized successfully")
    except Exception as e:
        logger.error(f"✗ Failed to initialize database: {e}")
        logger.warning("⚠️  Continuing without persistence layer")
    
    # Cleanup orphaned files from previous runs
    cleanup_old_temp_files()
    
    # Check if webhook URL is configured
    webhook_url = os.getenv("WEBHOOK_URL") or (
        f"{os.getenv('RENDER_EXTERNAL_URL')}/telegram/webhook" 
        if os.getenv("RENDER_EXTERNAL_URL") else None
    )

    if webhook_url:
        # Production mode: Use webhook
        logger.info("📡 WEBHOOK MODE - Telegram webhook enabled (production)")
        setup_telegram_webhook()
        logger.info("✓ Unified backend ready for Telegram (webhook) + Web API requests")
        logger.info("="*70)
        app.run(
            host=config['host'],
            port=config['port'],
            debug=config['debug'],
            use_reloader=False  # Disable reloader in production
        )
    else:
        # Development mode: Use polling
        logger.info("🔄 POLLING MODE - Telegram polling enabled (development)")
        
        # Start Flask in a background thread
        flask_thread = threading.Thread(
            target=lambda: app.run(
                host=config['host'],
                port=config['port'],
                debug=config['debug'],
                use_reloader=False
            ),
            daemon=True
        )
        flask_thread.start()
        logger.info("✓ Flask server started in background")
        logger.info("✓ Unified backend ready for Telegram (polling) + Web API requests")
        logger.info("="*70)
        
        # Start Telegram polling in main thread
        logger.info("🤖 Starting Telegram bot polling...")
        try:
            asyncio.run(telegram_app.run_polling())
        except KeyboardInterrupt:
            logger.info("⏹️  Telegram polling stopped by user")
            exit(0)
