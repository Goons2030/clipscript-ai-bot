"""
ClipScript AI - Database Layer
SQLite persistence for job tracking
"""

import sqlite3
import logging
from datetime import datetime
from contextlib import contextmanager

logger = logging.getLogger(__name__)

DB_PATH = "jobs.db"


@contextmanager
def get_db():
    """Context manager for database connections."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Database error: {e}")
        raise
    finally:
        conn.close()


def init_db():
    """Initialize database and create tables."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Create jobs table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    link TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result TEXT,
                    error TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create index for faster queries
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_user_id ON jobs(user_id)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_request_id ON jobs(request_id)
            ''')
            
            logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise


def create_job(request_id: str, user_id: str, link: str) -> int:
    """Create a new job. Returns job_id."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO jobs (request_id, user_id, link, status)
                VALUES (?, ?, ?, ?)
            ''', (request_id, user_id, link, 'pending'))
            
            job_id = cursor.lastrowid
            logger.info(f"[{request_id}] Created job #{job_id} for user {user_id}")
            return job_id
    except Exception as e:
        logger.error(f"Failed to create job: {e}")
        return None


def update_job_status(request_id: str, status: str) -> bool:
    """Update job status. Returns True if successful."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE jobs
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE request_id = ?
            ''', (status, request_id))
            
            if cursor.rowcount > 0:
                logger.info(f"[{request_id}] Status updated to: {status}")
                return True
            else:
                logger.warning(f"[{request_id}] Job not found")
                return False
    except Exception as e:
        logger.error(f"Failed to update job status: {e}")
        return False


def save_result(request_id: str, result: str) -> bool:
    """Save transcription result. Returns True if successful."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE jobs
                SET status = ?, result = ?, updated_at = CURRENT_TIMESTAMP
                WHERE request_id = ?
            ''', ('completed', result, request_id))
            
            if cursor.rowcount > 0:
                logger.info(f"[{request_id}] Result saved")
                return True
            else:
                logger.warning(f"[{request_id}] Job not found for result save")
                return False
    except Exception as e:
        logger.error(f"Failed to save result: {e}")
        return False


def save_error(request_id: str, error_msg: str) -> bool:
    """Save error message. Returns True if successful."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE jobs
                SET status = ?, error = ?, updated_at = CURRENT_TIMESTAMP
                WHERE request_id = ?
            ''', ('failed', error_msg, request_id))
            
            if cursor.rowcount > 0:
                logger.info(f"[{request_id}] Error saved")
                return True
            else:
                logger.warning(f"[{request_id}] Job not found for error save")
                return False
    except Exception as e:
        logger.error(f"Failed to save error: {e}")
        return False


def get_user_jobs(user_id: str, limit: int = 5) -> list:
    """Get user's recent jobs. Returns list of job dicts."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, request_id, link, status, created_at, updated_at
                FROM jobs
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            ''', (user_id, limit))
            
            rows = cursor.fetchall()
            jobs = [dict(row) for row in rows]
            logger.debug(f"Retrieved {len(jobs)} jobs for user {user_id}")
            return jobs
    except Exception as e:
        logger.error(f"Failed to get user jobs: {e}")
        return []


def get_latest_job(user_id: str) -> dict:
    """Get the most recent job for a user. Returns job dict or None."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, request_id, link, status, result, error, created_at, updated_at
                FROM jobs
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT 1
            ''', (user_id,))
            
            row = cursor.fetchone()
            if row:
                logger.debug(f"Retrieved latest job for user {user_id}")
                return dict(row)
            else:
                logger.debug(f"No jobs found for user {user_id}")
                return None
    except Exception as e:
        logger.error(f"Failed to get latest job: {e}")
        return None


def get_job_by_request_id(request_id: str) -> dict:
    """Get a job by request_id. Returns job dict or None."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, request_id, user_id, link, status, result, error, created_at, updated_at
                FROM jobs
                WHERE request_id = ?
            ''', (request_id,))
            
            row = cursor.fetchone()
            if row:
                return dict(row)
            else:
                return None
    except Exception as e:
        logger.error(f"Failed to get job: {e}")
        return None


def shorten_url(url: str, max_length: int = 40) -> str:
    """Shorten URL for display. Example: 'https://www.tiktok.com/@xxx/video/123...'."""
    if len(url) <= max_length:
        return url
    # Extract the video ID from TikTok URL
    if 'tiktok.com' in url:
        if '/video/' in url:
            video_id = url.split('/video/')[1].split('?')[0]
            return f"TikTok: {video_id[:20]}"
        elif 'vm.tiktok.com' in url or 'vt.tiktok.com' in url:
            return url[:max_length] + "..."
    return url[:max_length] + "..."


def get_status_emoji(status: str) -> str:
    """Get emoji for status display."""
    emojis = {
        'pending': '⏳',
        'processing': '🔄',
        'completed': '✅',
        'failed': '❌'
    }
    return emojis.get(status, '❓')
