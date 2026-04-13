"""
ClipScript AI - Database Layer
SQLite persistence for job tracking
"""

import sqlite3
import logging
from datetime import datetime
from contextlib import contextmanager
from threading import Lock

logger = logging.getLogger(__name__)

# Thread-safe lock for atomic DB operations
_db_lock = Lock()

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
    """Create a new job atomically. Returns job_id. Thread-safe."""
    try:
        # Use lock to prevent race conditions during job creation
        with _db_lock:
            with get_db() as conn:
                cursor = conn.cursor()
                
                # Check if job already exists (prevent duplicate creation)
                cursor.execute('''
                    SELECT id FROM jobs WHERE request_id = ?
                ''', (request_id,))
                
                if cursor.fetchone():
                    logger.warning(f"[{request_id}] Job already exists, returning existing job")
                    # Get the existing job ID
                    cursor.execute('''
                        SELECT id FROM jobs WHERE request_id = ?
                    ''', (request_id,))
                    return cursor.fetchone()[0]
                
                # Insert new job atomically
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


def get_job_by_link(link: str) -> dict:
    """Get a completed job by link (for job reuse/caching). Returns job dict or None."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, request_id, user_id, link, status, result, error, created_at, updated_at
                FROM jobs
                WHERE link = ?
                AND status = ?
                ORDER BY created_at DESC
                LIMIT 1
            ''', (link, 'completed'))
            
            row = cursor.fetchone()
            if row:
                logger.info(f"Cache hit: Found completed job for link {link[:50]}")
                return dict(row)
            else:
                logger.debug(f"Cache miss: No completed job for link {link[:50]}")
                return None
    except Exception as e:
        logger.error(f"Failed to get job by link: {e}")
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


def get_queue_position(request_id: str) -> int:
    """
    Get queue position for a job.
    Counts all pending jobs created BEFORE this job.
    Returns position (1-indexed, so position 1 means next to be processed).
    """
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Get the created_at timestamp for THIS job
            cursor.execute('''
                SELECT created_at FROM jobs WHERE request_id = ?
            ''', (request_id,))
            
            row = cursor.fetchone()
            if not row:
                logger.warning(f"[{request_id}] Job not found for queue position")
                return None
            
            created_at = row[0]
            
            # Count all PENDING jobs created BEFORE this one
            cursor.execute('''
                SELECT COUNT(*) FROM jobs
                WHERE status = ?
                AND created_at < ?
            ''', ('pending', created_at))
            
            count = cursor.fetchone()[0]
            position = count + 1  # 1-indexed
            
            logger.debug(f"[{request_id}] Queue position: {position} ({count} jobs ahead)")
            return position
            
    except Exception as e:
        logger.error(f"Failed to get queue position: {e}")
        return None


def get_pending_count() -> int:
    """Get number of jobs in pending status. Used for queue display."""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM jobs WHERE status = ?', ('pending',))
            count = cursor.fetchone()[0]
            return count
    except Exception as e:
        logger.error(f"Failed to get pending count: {e}")
        return 0


def get_avg_processing_time() -> float:
    """
    Get average processing time for completed jobs.
    Returns seconds, used for estimated wait time calculation.
    """
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Calculate average time between created_at and updated_at for completed jobs
            cursor.execute('''
                SELECT AVG(
                    (julianday(updated_at) - julianday(created_at)) * 86400
                )
                FROM jobs
                WHERE status = ?
                LIMIT 100
            ''', ('completed',))
            
            result = cursor.fetchone()[0]
            
            # Return average in seconds, minimum 5 seconds, maximum 30 seconds
            if result is None:
                return 10.0  # Default 10 seconds if no completed jobs
            
            avg_time = float(result)
            # Clamp between 5-30 seconds for reasonable estimates
            clamped = max(5.0, min(30.0, avg_time))
            
            logger.debug(f"Average processing time: {clamped:.1f}s from {100} recent jobs")
            return clamped
            
    except Exception as e:
        logger.error(f"Failed to get average processing time: {e}")
        return 10.0  # Safe default
