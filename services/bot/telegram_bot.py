"""
Telegram Bot Service - Telegram only
Calls API service for processing, no local async state
"""
import os
import sys
import asyncio
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.config import BOT_TOKEN, API_BASE_URL, TELEGRAM_WEBHOOK_URL, ENABLE_TELEGRAM_WEBHOOK
from shared.client import ServiceClient

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize API client
api_client = ServiceClient(API_BASE_URL)

class TelegramBotService:
    """
    Telegram bot service - handles user messages
    Communicates with API service via HTTP
    """
    
    def __init__(self):
        logger.info("🤖 Initializing Telegram Bot Service...")
        self.app = Application.builder().token(BOT_TOKEN).build()
        self.setup_handlers()
    
    def setup_handlers(self):
        """Register command handlers"""
        self.app.add_handler(CommandHandler("start", self.handle_start))
        self.app.add_handler(CommandHandler("help", self.handle_help))
        self.app.add_handler(CommandHandler("status", self.handle_status))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        self.app.add_error_handler(self.handle_error)
    
    async def handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        await update.message.reply_text(
            "👋 Welcome to ClipScript AI!\n\n"
            "Send me a TikTok, YouTube, or Instagram link and I'll transcribe it for you.\n\n"
            "Usage: Just paste a link in a message!"
        )
    
    async def handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        await update.message.reply_text(
            "📝 ClipScript AI - Transcription Bot\n\n"
            "Commands:\n"
            "/start - Welcome message\n"
            "/help - This message\n"
            "/status - Check supported platforms\n\n"
            "Supported platforms:\n"
            "🎵 TikTok\n"
            "▶️ YouTube\n"
            "📷 Instagram\n"
            "🐦 Twitter/X"
        )
    
    async def handle_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        health = api_client.get("/health")
        
        if health:
            await update.message.reply_text(
                "✅ Bot is online and ready!\n\n"
                "Send any video link to get started."
            )
        else:
            await update.message.reply_text(
                "⚠️ Bot is experiencing issues.\n"
                "Please try again in a moment."
            )
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle message with video link"""
        text = update.message.text.strip()
        user_id = str(update.effective_user.id)
        
        # Check if message contains URL
        if not text.startswith(('http://', 'https://')):
            await update.message.reply_text(
                "Please send a valid video link.\n\n"
                "Supported: TikTok, YouTube, Instagram, Twitter/X"
            )
            return
        
        logger.info(f"[{user_id}] Processing link: {text[:60]}")
        
        # Show processing message
        status_msg = await update.message.reply_text("⏳ Queuing your video...")
        
        # Send to API service
        result = api_client.post("/api/transcribe", {
            "link": text,
            "user_id": user_id
        })
        
        if not result or not result.get("success"):
            error = result.get("error", "Unknown error") if result else "API unavailable"
            await status_msg.edit_text(f"❌ Error: {error}")
            logger.error(f"[{user_id}] API error: {error}")
            return
        
        job_id = result.get("job_id")
        
        # Update status message
        await status_msg.edit_text(
            f"✅ Job queued!\n"
            f"Job ID: {job_id}\n"
            f"\n⏳ Processing...\n"
            f"This may take a few minutes."
        )
        
        # Poll for result (simplified - in production use better polling)
        max_polls = 60
        for poll_count in range(max_polls):
            await asyncio.sleep(5)
            
            # Check status
            status_result = api_client.get(f"/api/status/{job_id}")
            
            if not status_result:
                continue
            
            status = status_result.get("status")
            
            if status == "completed":
                transcript = status_result.get("result")
                await status_msg.edit_text(
                    f"✅ Done!\n\n"
                    f"📝 Transcript:\n\n"
                    f"{transcript}"
                )
                logger.info(f"[{user_id}] ✅ Complete: {job_id}")
                return
            
            elif status == "failed":
                error = status_result.get("error", "Unknown error")
                await status_msg.edit_text(f"❌ Failed: {error}")
                logger.error(f"[{user_id}] Failed: {error}")
                return
        
        # Timeout
        await status_msg.edit_text(
            f"⏱️ Processing timeout\n"
            f"Transcript is being generated in the background.\n"
            f"Job ID: {job_id}"
        )
    
    async def handle_error(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle errors gracefully"""
        logger.error(f"Telegram error: {context.error}")
        
        try:
            if update.message:
                await update.message.reply_text(
                    "❌ An error occurred. Please try again."
                )
        except:
            pass
    
    async def run_polling(self):
        """Run bot with polling"""
        logger.info("🔄 Starting Telegram polling...")
        await self.app.run_polling()
    
    async def run_webhook(self):
        """Run bot with webhook"""
        logger.info(f"📡 Starting webhook mode: {TELEGRAM_WEBHOOK_URL}")
        # Webhook setup would go here
        await self.app.run_polling()

async def main():
    """Main entry point"""
    logger.info("="*70)
    logger.info("🚀 ClipScript AI - Telegram Bot Service")
    logger.info("="*70)
    
    bot = TelegramBotService()
    
    try:
        if ENABLE_TELEGRAM_WEBHOOK:
            await bot.run_webhook()
        else:
            await bot.run_polling()
    
    except KeyboardInterrupt:
        logger.info("⏹️  Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise

if __name__ == '__main__':
    logger.info("⚠️  This service: TELEGRAM ONLY")
    logger.info("⚠️  API_BASE_URL must be set in .env")
    logger.info("⚠️  Do NOT run Flask, Asyncio, or processing here")
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutdown")
