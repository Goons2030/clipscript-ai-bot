#!/usr/bin/env python3
"""
FFmpeg Auto-Installer for Windows
Downloads and installs FFmpeg to the project directory
"""
import os
import sys
import zipfile
import shutil
from pathlib import Path
import urllib.request

def download_ffmpeg():
    """Download FFmpeg from GitHub releases."""
    print("📥 Downloading FFmpeg...")
    url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
    zip_path = "ffmpeg.zip"
    
    try:
        urllib.request.urlretrieve(url, zip_path)
        print(f"✅ Downloaded: {zip_path}")
        return zip_path
    except Exception as e:
        print(f"❌ Download failed: {e}")
        return None

def extract_ffmpeg(zip_path):
    """Extract FFmpeg from zip file."""
    print("📂 Extracting FFmpeg...")
    extract_dir = "ffmpeg_temp"
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
        print(f"✅ Extracted to: {extract_dir}")
        
        # Find the actual ffmpeg folder
        for item in os.listdir(extract_dir):
            ffmpeg_dir = os.path.join(extract_dir, item)
            if os.path.isdir(ffmpeg_dir) and 'ffmpeg' in item.lower():
                return ffmpeg_dir
        
        # If not found, it might be at root
        if os.path.exists(os.path.join(extract_dir, "bin")):
            return extract_dir
            
    except Exception as e:
        print(f"❌ Extraction failed: {e}")
        return None

def setup_ffmpeg():
    """Download and setup FFmpeg."""
    print("=" * 60)
    print("🚀 FFmpeg Auto-Installer")
    print("=" * 60)
    print()
    
    # Check if ffmpeg is already in PATH
    if shutil.which("ffmpeg"):
        print("✅ FFmpeg already installed and in PATH!")
        print(f"   Location: {shutil.which('ffmpeg')}")
        return True
    
    print("❌ FFmpeg not found in PATH")
    print()
    
    # Download
    zip_path = download_ffmpeg()
    if not zip_path:
        print("\n💡 Alternative: Download manually from:")
        print("   https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip")
        return False
    
    print()
    
    # Extract
    ffmpeg_dir = extract_ffmpeg(zip_path)
    if not ffmpeg_dir:
        print("\n💡 Try extracting the zip manually")
        return False
    
    print()
    
    # Create local ffmpeg directory
    print("📦 Setting up local FFmpeg...")
    local_ffmpeg = Path("ffmpeg")
    
    try:
        if local_ffmpeg.exists():
            shutil.rmtree(local_ffmpeg)
        
        # Move to project folder
        shutil.move(ffmpeg_dir, str(local_ffmpeg))
        print(f"✅ FFmpeg ready at: {local_ffmpeg.absolute()}")
        
        # Cleanup
        if os.path.exists("ffmpeg_temp"):
            shutil.rmtree("ffmpeg_temp")
        if os.path.exists(zip_path):
            os.remove(zip_path)
        
        # Verify
        ffmpeg_exe = local_ffmpeg / "bin" / "ffmpeg.exe"
        if ffmpeg_exe.exists():
            print(f"✅ Verified: {ffmpeg_exe}")
            print()
            print("=" * 60)
            print("✅ FFmpeg installed successfully!")
            print("=" * 60)
            return True
        else:
            print(f"❌ FFmpeg executable not found at {ffmpeg_exe}")
            return False
            
    except Exception as e:
        print(f"❌ Setup failed: {e}")
        return False

if __name__ == '__main__':
    success = setup_ffmpeg()
    sys.exit(0 if success else 1)
