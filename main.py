#!/usr/bin/env python3
"""
ClipScript AI - Master Service Runner
Starts all services: API, Worker, Telegram Bot
"""

import os
import sys
import multiprocessing
import logging
import signal
from pathlib import Path

# Add services to path
BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def check_env():
    """Verify .env file exists and has required fields"""
    from shared.config import (
        BOT_TOKEN, API_BASE_URL, DEEPGRAM_API_KEY, DATABASE_URL, FLASK_PORT
    )
    
    required = {
        "BOT_TOKEN": BOT_TOKEN,
        "API_BASE_URL": API_BASE_URL,
        "DEEPGRAM_API_KEY": DEEPGRAM_API_KEY,
        "DATABASE_URL": DATABASE_URL,
        "FLASK_PORT": FLASK_PORT,
    }
    
    missing = [k for k, v in required.items() if not v]
    
    if missing:
        logger.error(f"❌ Missing environment variables: {', '.join(missing)}")
        logger.error("Create .env file with required fields")
        return False
    
    logger.info("✅ All environment variables configured")
    return True

def run_api():
    """Run API service"""
    logger.info("🚀 Starting API Service...")
    try:
        import sys
        sys.path.insert(0, str(BASE_DIR / 'services' / 'api'))
        from app import app
        
        port = int(os.environ.get('FLASK_PORT', 3000))
        logger.info(f"📡 API Service running on http://localhost:{port}")
        app.run(host='0.0.0.0', port=port, debug=False)
    except Exception as e:
        logger.error(f"❌ API Service failed: {e}")
        raise

def run_worker():
    """Run background worker service"""
    logger.info("🚀 Starting Background Worker...")
    try:
        import sys
        sys.path.insert(0, str(BASE_DIR / 'services' / 'worker'))
        from worker import main as worker_main
        
        worker_main()
    except Exception as e:
        logger.error(f"❌ Worker failed: {e}")
        raise

def run_bot():
    """Run Telegram bot service"""
    logger.info("🚀 Starting Telegram Bot...")
    try:
        import asyncio
        import sys
        sys.path.insert(0, str(BASE_DIR / 'services' / 'bot'))
        from telegram_bot import main as bot_main
        
        asyncio.run(bot_main())
    except Exception as e:
        logger.error(f"❌ Bot failed: {e}")
        raise

def main():
    """Main entry point"""
    logger.info("="*70)
    logger.info("🎬 ClipScript AI - Master Service Runner")
    logger.info("="*70)
    
    # Check environment
    if not check_env():
        sys.exit(1)
    
    # Create processes
    processes = []
    
    try:
        logger.info("\n🔄 Starting all services...")
        logger.info("-"*70)
        
        # Start services in separate processes
        api_process = multiprocessing.Process(target=run_api, name="API")
        api_process.daemon = False
        api_process.start()
        processes.append(("API", api_process))
        
        # Small delay to let API start
        import time
        time.sleep(2)
        
        worker_process = multiprocessing.Process(target=run_worker, name="Worker")
        worker_process.daemon = False
        worker_process.start()
        processes.append(("Worker", worker_process))
        
        bot_process = multiprocessing.Process(target=run_bot, name="Bot")
        bot_process.daemon = False
        bot_process.start()
        processes.append(("Bot", bot_process))
        
        logger.info("-"*70)
        logger.info("\n✅ All services started!")
        logger.info("\n📊 Service Status:")
        logger.info("  API Service:      http://localhost:3000")
        logger.info("  Telegram Bot:     Polling for messages")
        logger.info("  Background Worker: Processing jobs")
        logger.info("\n💡 Tips:")
        logger.info("  - View logs above for each service")
        logger.info("  - Press Ctrl+C to stop all services")
        logger.info("  - Test API: curl http://localhost:3000/health")
        logger.info("  - Check ARCHITECTURE.md for design details")
        logger.info("\n")
        
        # Wait for all processes
        for name, process in processes:
            process.join()
    
    except KeyboardInterrupt:
        logger.info("\n⏹️  Stopping all services...")
        
        # Terminate all processes
        for name, process in processes:
            if process.is_alive():
                logger.info(f"  Stopping {name}...")
                process.terminate()
        
        # Wait briefly for graceful shutdown
        import time
        time.sleep(1)
        
        # Force kill if still alive
        for name, process in processes:
            if process.is_alive():
                logger.info(f"  Force killing {name}...")
                process.kill()
        
        logger.info("✅ All services stopped")
    
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        
        # Cleanup
        for name, process in processes:
            if process.is_alive():
                process.terminate()
        
        sys.exit(1)

if __name__ == '__main__':
    # Print startup info
    print("""
╔══════════════════════════════════════════════════════════════════╗
║                  ClipScript AI - Bot Service                     ║
║              Multi-Service Architecture Runner                   ║
╚══════════════════════════════════════════════════════════════════╝
    """)
    
    # Check if services exist
    api_path = BASE_DIR / 'services' / 'api' / 'app.py'
    worker_path = BASE_DIR / 'services' / 'worker' / 'worker.py'
    bot_path = BASE_DIR / 'services' / 'bot' / 'telegram_bot.py'
    
    missing = []
    if not api_path.exists():
        missing.append(f"API service: {api_path}")
    if not worker_path.exists():
        missing.append(f"Worker service: {worker_path}")
    if not bot_path.exists():
        missing.append(f"Bot service: {bot_path}")
    
    if missing:
        logger.error("❌ Missing service files:")
        for m in missing:
            logger.error(f"  - {m}")
        sys.exit(1)
    
    # Run
    main()
