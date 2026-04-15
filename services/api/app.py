"""
API Service - REST API only
No Telegram, no processing, no asyncio issues
"""
import os
import sys
import uuid
import logging
from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_cors import CORS

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.config import DEEPGRAM_API_KEY, IS_PRODUCTION, PORT
from shared.models import Job, JobStatus, TranscribeResponse
from shared.client import ServiceClient

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask
app = Flask(__name__)
CORS(app)

# Initialize worker client
WORKER_CLIENT = ServiceClient("http://localhost:6000")

# In-memory job store (would be replaced with proper DB in production)
JOBS = {}

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "service": "api",
        "version": "1.0.0"
    }), 200

@app.route('/test', methods=['GET'])
def test():
    """Test endpoint - verify API is responding"""
    return jsonify({
        "success": True,
        "message": "API is working",
        "timestamp": str(__import__('datetime').datetime.now())
    }), 200

@app.route('/', methods=['GET'])
def index():
    """Serve web frontend"""
    try:
        frontend_paths = [
            os.path.join(os.path.dirname(__file__), '../../frontend'),
            os.path.join(os.path.dirname(__file__), '../../frontend/index.html'),
            'frontend'
        ]
        for path in frontend_paths:
            if os.path.exists(path):
                if os.path.isdir(path):
                    return send_from_directory(path, 'index.html')
                else:
                    return send_from_directory(os.path.dirname(path), 'index.html')
        return "<h1>ClipScript AI - API Service</h1>", 200
    except Exception as e:
        logger.warning(f"Could not serve frontend: {e}")
        return "<h1>ClipScript AI - API Service</h1>", 200

@app.route('/api/transcribe', methods=['POST', 'OPTIONS'])
def transcribe():
    """
    Main transcription endpoint
    Request: { "link": "https://..." }
    Response: { "success": true/false, "job_id": "...", "status": "pending" }
    """
    
    # Handle CORS preflight
    if request.method == 'OPTIONS':
        return '', 204
    
    try:
        data = request.get_json()
        
        if not data or 'link' not in data:
            return jsonify({
                "success": False,
                "error": "Missing 'link' in request"
            }), 400
        
        link = data.get('link', '').strip()
        user_id = data.get('user_id')
        
        # Validate link
        if not link or not link.startswith(('http://', 'https://')):
            return jsonify({
                "success": False,
                "error": "Invalid URL format"
            }), 400
        
        # Create job
        job_id = str(uuid.uuid4())
        job = Job(
            job_id=job_id,
            link=link,
            user_id=user_id,
            status=JobStatus.PENDING
        )
        JOBS[job_id] = job
        
        # Send to worker (async, non-blocking)
        worker_result = WORKER_CLIENT.post('/process', {
            "job_id": job_id,
            "link": link,
            "user_id": user_id
        })
        
        if not worker_result:
            logger.warning(f"Worker unreachable, queued locally: {job_id}")
        
        return jsonify({
            "success": True,
            "job_id": job_id,
            "status": "pending",
            "message": "Job queued for processing"
        }), 202
    
    except Exception as e:
        logger.error(f"Transcribe error: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/status/<job_id>', methods=['GET'])
def get_status(job_id):
    """Get job status"""
    job = JOBS.get(job_id)
    if not job:
        return jsonify({
            "success": False,
            "error": "Job not found"
        }), 404
    
    return jsonify({
        "success": True,
        "status": job.status,
        "result": job.result,
        "error": job.error
    }), 200

@app.route('/api/pricing', methods=['GET'])
def pricing():
    """Return pricing info"""
    return jsonify({
        "currency": "USD",
        "pricing": {
            "free_tier": {
                "transcriptions_per_day": 3,
                "max_length_minutes": 10
            },
            "pro": {
                "price_per_month": 9.99,
                "transcriptions_per_month": 100,
                "max_length_minutes": None
            }
        }
    }), 200

if __name__ == '__main__':
    logger.info("🚀 Starting API Service...")
    logger.info(f"🌐 Listening on port {PORT}")
    logger.info("⚠️  Worker service must be running on port 6000")
    app.run(host='0.0.0.0', port=PORT, debug=not IS_PRODUCTION)
