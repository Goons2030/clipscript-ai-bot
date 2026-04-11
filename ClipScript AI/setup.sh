#!/bin/bash

# ClipScript AI - Local Setup Script
# Run this once to get the bot ready for local testing

echo "🚀 ClipScript AI Setup"
echo "====================="

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 not found. Install Python 3.9+ first."
    exit 1
fi
echo "✅ Python found: $(python3 --version)"

# Check if venv exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate venv
echo "🔌 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Check FFmpeg
echo "🎬 Checking FFmpeg..."
if ! command -v ffmpeg &> /dev/null; then
    echo "⚠️  FFmpeg not found."
    echo "Install with:"
    echo "  macOS: brew install ffmpeg"
    echo "  Ubuntu: sudo apt-get install ffmpeg"
    echo "  Windows: Download from https://ffmpeg.org/download.html"
else
    echo "✅ FFmpeg found: $(ffmpeg -version | head -1)"
fi

# Check yt-dlp
echo "📥 Checking yt-dlp..."
if ! command -v yt-dlp &> /dev/null; then
    echo "⚠️  yt-dlp not found. Installing..."
    pip install yt-dlp
else
    echo "✅ yt-dlp found"
fi

# Setup .env
if [ ! -f ".env" ]; then
    echo "🔑 Creating .env file..."
    cp .env.example .env
    echo "⚠️  Edit .env with your:"
    echo "   • BOT_TOKEN (from @BotFather)"
    echo "   • OPENAI_API_KEY (from platform.openai.com)"
else
    echo "✅ .env already exists"
fi

# Create temp directory
mkdir -p temp
echo "📂 Created temp directory"

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit .env with your BOT_TOKEN and OPENAI_API_KEY"
echo "2. Run: python main.py"
echo "3. Send a TikTok link to your bot on Telegram"
echo ""
