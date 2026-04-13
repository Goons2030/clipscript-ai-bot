#!/usr/bin/env python3
"""
ClipScript AI - Stability Verification Script
Checks all systems are ready for deployment
"""

import os
import sys
import sqlite3
from dotenv import load_dotenv

def check_stability():
    print("\n" + "="*50)
    print("ClipScript AI - STABILITY CHECK")
    print("="*50 + "\n")
    
    all_good = True
    
    # Check 1: Environment Variables
    print("1. ENVIRONMENT VARIABLES")
    load_dotenv()
    bot_token = os.getenv("BOT_TOKEN")
    deep_key = os.getenv("DEEPGRAM_API_KEY")
    
    if bot_token and len(bot_token) > 30:
        print("   ✓ BOT_TOKEN configured")
    else:
        print("   ✗ BOT_TOKEN missing or invalid")
        all_good = False
        
    if deep_key and len(deep_key) > 20:
        print("   ✓ DEEPGRAM_API_KEY configured")
    else:
        print("   ✗ DEEPGRAM_API_KEY missing or invalid")
        all_good = False
    
    # Check 2: Database
    print("\n2. DATABASE")
    if os.path.exists("jobs.db"):
        try:
            conn = sqlite3.connect("jobs.db")
            cursor = conn.cursor()
            
            # Check tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = cursor.fetchall()
            
            # Check jobs count
            cursor.execute("SELECT COUNT(*) FROM jobs")
            rows = cursor.fetchone()[0]
            
            # Check schema
            cursor.execute("PRAGMA table_info(jobs)")
            columns = len(cursor.fetchall())
            
            conn.close()
            
            print(f"   ✓ Database file: {os.path.getsize('jobs.db')} bytes")
            print(f"   ✓ Tables: {len(tables)} ({', '.join([t[0] for t in tables])})")
            print(f"   ✓ Jobs tracked: {rows}")
            print(f"   ✓ Schema: {columns} columns")
        except Exception as e:
            print(f"   ✗ Database error: {e}")
            all_good = False
    else:
        print("   ✗ Database not found (jobs.db)")
        all_good = False
    
    # Check 3: Dependencies
    print("\n3. DEPENDENCIES")
    required = {
        "flask": "Flask",
        "telegram": "python-telegram-bot",
        "yt_dlp": "yt-dlp",
        "deepgram": "deepgram-sdk",
        "dotenv": "python-dotenv"
    }
    
    missing = []
    for module, name in required.items():
        try:
            __import__(module)
            print(f"   ✓ {name}")
        except ImportError:
            print(f"   ✗ {name}")
            missing.append(name)
            all_good = False
    
    # Check 4: Critical Files
    print("\n4. CRITICAL FILES")
    files = [
        ("app_unified.py", 5000),
        ("db.py", 1000),
        ("requirements.txt", 100),
        ("jobs.db", 1000),
    ]
    
    for filename, min_size in files:
        if os.path.exists(filename):
            size = os.path.getsize(filename)
            if size >= min_size:
                print(f"   ✓ {filename} ({size} bytes)")
            else:
                print(f"   ⚠ {filename} (small: {size} bytes)")
                all_good = False
        else:
            print(f"   ✗ {filename} (missing)")
            all_good = False
    
    # Check 5: Logging
    print("\n5. LOGGING")
    if os.path.exists("logs"):
        log_file = "logs/clipscript_unified.log"
        if os.path.exists(log_file):
            size = os.path.getsize(log_file)
            print(f"   ✓ Log file: {size} bytes")
            
            # Check last entries
            with open(log_file, 'r') as f:
                lines = f.readlines()
                last_line = lines[-1] if lines else ""
                if "INFO" in last_line or "WARNING" in last_line:
                    print(f"   ✓ Last log entry: {last_line[:60]}...")
        else:
            print(f"   ⚠ Log file not yet created (will be on first run)")
    else:
        print(f"   ⚠ Logs directory not found (will be created on first run)")
    
    # Final Result
    print("\n" + "="*50)
    if all_good:
        print("✅ ALL SYSTEMS STABLE - READY FOR DEPLOYMENT")
        print("="*50 + "\n")
        return 0
    else:
        print("⚠️  SOME ISSUES FOUND - SEE ABOVE")
        print("="*50 + "\n")
        return 1

if __name__ == "__main__":
    sys.exit(check_stability())
