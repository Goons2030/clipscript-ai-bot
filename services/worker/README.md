# Background Worker Service - ClipScript AI

## Overview

The Background Worker Service:

- Polls API Service for new transcription jobs
- Downloads videos from links
- Extracts audio and transcribes using Deepgram
- Updates API with progress and results
- Handles errors gracefully

## 🏗️ Architecture

```
API Service
     │ (Poll for jobs)
     ↓
Worker Service
     ├─ Check for pending jobs
     ├─ Download video (yt-dlp, instagrapi, etc.)
     ├─ Extract audio (pydub)
     ├─ Send to Deepgram API
     ├─ Update job status
     └─ Return to API when done
```

## 🚀 Running

```bash
cd services/worker
python worker.py

# Output:
# ✅ Worker started
# 🔄 Polling... awaiting jobs
```

## 🔄 Job Processing Flow

```
1. Worker polls API
   GET /api/jobs?status=queued
                     │
2. If jobs found, download video
   youtube-dl, instagrapi, yt-dlp
                     │
3. Extract audio
   pydub or ffmpeg
                     │
4. Send audio to Deepgram
   deepgram-sdk
                     │
5. Receive transcript
   text results
                     │
6. Update job status
   PUT /api/jobs/{job_id}
   → status: "completed"
   → transcript: "..."
                     │
7. Bot polls for result
   GET /api/status/{job_id}
                     │
8. Bot sends to user ✅
```

## 🛠️ Files

- `worker.py` - Main worker loop
- `transcriber.py` - Deepgram integration
- `downloader.py` - Video downloading
- `processor.py` - Audio processing

## ⚙️ Configuration

Via `.env`:
```
API_BASE_URL=http://localhost:3000
DEEPGRAM_API_KEY=<your_deepgram_key>
DATABASE_URL=sqlite:///database.db
WORKER_POLL_INTERVAL=10  # Seconds
WORKER_THREADS=3  # Parallel downloads
```

## 🎥 Video Platforms

### Supported Downloaders

| Platform | Tool | Notes |
|----------|------|-------|
| TikTok | yt-dlp | Works with tokens |
| YouTube | yt-dlp | Full support |
| Instagram | instagrapi | Requires session |
| Twitter/X | yt-dlp | Limited support |
| Generic | yt-dlp | Fallback |

### Adding New Platform

In `downloader.py`:
```python
async def download_platform(url: str) -> str:
    """Download video and return audio path"""
    
    if "newplatform.com" in url:
        # Use platform-specific downloader
        downloader = PlatformDownloader()
        return await downloader.download(url)
    
    # Fallback to yt-dlp
    return await download_with_ytdlp(url)
```

## 🎙️ Transcription

### Using Deepgram

```python
from deepgram import Deepgram

async def transcribe(audio_path: str) -> str:
    """Transcribe audio file"""
    
    deepgram = Deepgram(api_key)
    
    with open(audio_path, 'rb') as audio:
        response = await deepgram.transcription.prerecorded(
            {  'mimetype': 'audio/wav' },
            audio
        )
    
    return response['results']['channels'][0]['alternatives'][0]['transcript']
```

### Language Support

```python
# Transcribe specific language
response = await deepgram.transcription.prerecorded(
    {
        'mimetype': 'audio/wav',
        'language': 'es'  # Spanish
    },
    audio
)
```

Supported: en, es, fr, de, it, pt, nl, tr, pl, hi, ja, ko, zh, ...

## ⏱️ Performance

### Current Configuration

```
WORKER_THREADS=3 (concurrent downloads)
WORKER_POLL_INTERVAL=10 (seconds)
```

### Bottlenecks

1. **Download Speed**: Limited by network & platform rate limits
   - Solution: Increase WORKER_THREADS
   
2. **Transcription Speed**: Limited by Deepgram API (10-20 sec/min audio)
   - Solution: Use faster model (cost)
   
3. **API Polling**: 10-second intervals
   - Solution: Reduce WORKER_POLL_INTERVAL
   - Trade-off: More API calls

## 🐛 Debugging

### Test Downloader
```python
from downloader import download_video

# Synchronous wrapper
import asyncio
path = asyncio.run(download_video("https://www.tiktok.com/..."))
print(f"Downloaded to: {path}")
```

### Test Transcriber
```python
from transcriber import transcribe_audio

path = "audio.wav"
transcript = asyncio.run(transcribe_audio(path))
print(f"Transcript: {transcript}")
```

### View Worker Logs
```bash
# Run with verbose output
LOGLEVEL=DEBUG python worker.py
```

## 📊 Monitoring

### Check Worker Status
```bash
curl http://localhost:3000/api/worker-status
```

### View Processing Jobs
```bash
curl http://localhost:3000/api/jobs?status=processing
```

### Worker Health
```bash
# Check if polling
tail -50 worker.log | grep "polling\|processing"
```

## ⚠️ Common Issues

### "API Unavailable"
- Verify `API_BASE_URL` in `.env`
- Check API service is running
- Check network connectivity

### "FFmpeg Not Found"
```bash
# Install ffmpeg
# macOS:
brew install ffmpeg

# Ubuntu:
sudo apt-get install ffmpeg

# Windows:
choco install ffmpeg
```

### "Deepgram Auth Failed"
- Verify `DEEPGRAM_API_KEY` is correct
- Check API key hasn't expired
- View Deepgram console for usage/limits

### "Download Fails"
- **TikTok**: Sometimes requires login tokens
- **Instagram**: May need session cookies
- **YouTube**: Check video is public
- **Generic**: Try with `--no-check-certificates`

### "Memory Issues"
- Reduce `WORKER_THREADS` (fewer parallel downloads)
- Limit audio file size
- Implement file cleanup

## 🔧 Customization

### Change Polling Interval

In `worker.py`:
```python
POLL_INTERVAL = 5  # Check every 5 seconds (faster)
```

### Parallel Processing

In `worker.py`:
```python
WORKER_THREADS = 5  # Process 5 videos simultaneously
```

### Audio Quality

In `transcriber.py`:
```python
# Trade-off: higher quality = slower transcription
options = {
    'mimetype': 'audio/wav',
    'model': 'nova-2-general',  # Best quality
    'language': 'en'
}
```

## 🚀 Production Checklist

- [ ] DEEPGRAM_API_KEY is valid
- [ ] FFmpeg is installed
- [ ] API_BASE_URL points to production
- [ ] Worker restarts on failure
- [ ] Disk space monitoring
- [ ] Logging configured
- [ ] Error alerts setup
- [ ] Database backups scheduled

## 📈 Scaling

### Multiple Workers

```bash
# Start 3 workers in parallel
python worker.py &
python worker.py &
python worker.py &
```

Or with systemd:
```ini
[Service]
ExecStart=/usr/bin/python3 /path/to/worker.py
Restart=always
RestartSec=10
User=clipscript

# Run 3 instances:
# clipscript-worker-1.service
# clipscript-worker-2.service
# clipscript-worker-3.service
```

**Key:** API handles job queue, workers share jobs.

### Distributed Deployment

```
Cloud Job Queue (RabbitMQ / Celery)
         │
    ┌────┼────┐
    │    │    │
Worker  Worker  Worker
 (EC2)  (EC2)  (EC2)
```

See DEPLOYMENT.md for scaling guide.

## 💡 Tips

- Start with 1-2 workers, scale based on load
- Monitor Deepgram API usage (can be expensive)
- Cache downloaded videos if processing multiple copies
- Implement cleanup for old temporary files
- Use connection pooling for database

## 🔒 Security

- Never log full API keys
- Validate URLs before processing
- Limit file sizes to prevent DoS
- Run in containerized environment
- Use VPN for downloading copyrighted content (optional)

---

**See:** [ARCHITECTURE.md](../../ARCHITECTURE.md) | [DEPLOYMENT.md](../../DEPLOYMENT.md)
