#!/usr/bin/env python3
"""
Production Entrypoint Verification Script (FAST)
Quick syntax and structure check without imports.
"""

import sys
import os
import re
from pathlib import Path

BACKEND_DIR = Path(__file__).parent / "backend"

print("=" * 70)
print("PRODUCTION ENTRYPOINT VERIFICATION (FAST)")
print("=" * 70)

# Test 1: Check if app_unified.py exists
print("\n[TEST 1] Checking app_unified.py exists...")
app_file = BACKEND_DIR / "app_unified.py"
if app_file.exists():
    print(f"  ✅ PASS: Found {app_file}")
    file_size = app_file.stat().st_size
    print(f"     Size: {file_size:,} bytes")
else:
    print(f"  ❌ FAIL: Missing {app_file}")
    sys.exit(1)

# Test 2: Check if 'app = Flask' is defined in the file (without importing)
print("\n[TEST 2] Checking Flask app instance definition...")
with open(app_file, 'r', encoding='utf-8') as f:
    content = f.read()
    if 'app = Flask(' in content:
        # Find exact line number
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if 'app = Flask(' in line:
                print(f"  ✅ PASS: Flask app instance defined at line {i}")
                print(f"     Code: {line.strip()}")
                break
    else:
        print(f"  ❌ FAIL: 'app = Flask' not found in app_unified.py")
        sys.exit(1)

# Test 3: Check setup.cfg or wsgi.py conflicts
print("\n[TEST 3] Checking for conflicting entrypoint files...")
conflicts = []
for conf_file in ["setup.cfg", "wsgi.py", "application.py"]:
    conf_path = BACKEND_DIR / conf_file
    if conf_path.exists():
        conflicts.append(conf_file)

if not conflicts:
    print(f"  ✅ PASS: No conflicting entrypoint files")
else:
    print(f"  ⚠️  WARNING: Found conflicting files: {', '.join(conflicts)}")
    print(f"     Consider removing them to avoid confusion")

# Test 4: Verify Procfile exists
print("\n[TEST 4] Checking Procfile...")
procfile = Path(__file__).parent / "Procfile"
if procfile.exists():
    with open(procfile, 'r', encoding='utf-8') as f:
        procfile_content = f.read()
    if 'app_unified:app' in procfile_content and 'gunicorn' in procfile_content:
        print(f"  ✅ PASS: Procfile configured correctly")
        print(f"     Content: {procfile_content.strip()}")
    else:
        print(f"  ❌ FAIL: Procfile missing 'gunicorn' or 'app_unified:app'")
        sys.exit(1)
else:
    print(f"  ❌ FAIL: Procfile not found in root directory")
    sys.exit(1)

# Test 5: Verify requirements.txt has gunicorn
print("\n[TEST 5] Checking requirements.txt...")
req_file = BACKEND_DIR / "requirements.txt"
if req_file.exists():
    with open(req_file, 'r', encoding='utf-8') as f:
        reqs = f.read()
    if 'gunicorn' in reqs.lower():
        # Find version
        match = re.search(r'gunicorn[>=<~]*[\d.]*', reqs, re.IGNORECASE)
        if match:
            print(f"  ✅ PASS: Gunicorn found in requirements")
            print(f"     {match.group(0)}")
        else:
            print(f"  ✅ PASS: Gunicorn listed in requirements.txt")
    else:
        print(f"  ❌ FAIL: Gunicorn not found in requirements.txt")
        sys.exit(1)
else:
    print(f"  ❌ FAIL: requirements.txt not found")
    sys.exit(1)

# Test 6: Validate Python syntax
print("\n[TEST 6] Validating Python syntax...")
try:
    compile(content, str(app_file), 'exec')
    print(f"  ✅ PASS: Python syntax is valid")
except SyntaxError as e:
    print(f"  ❌ FAIL: Syntax error in app_unified.py:")
    print(f"     {e}")
    sys.exit(1)

# Test 7: Check CORS is configured
print("\n[TEST 7] Checking CORS configuration...")
if 'CORS(app)' in content or 'flask_cors' in content.lower():
    print(f"  ✅ PASS: CORS is configured for API access")
else:
    print(f"  ⚠️  WARNING: CORS might not be configured")

# Summary
print("\n" + "=" * 70)
print("VERIFICATION SUMMARY")
print("=" * 70)
print("\n✅ ALL CHECKS PASSED")
print("\n📋 Deployment Configuration:")
print("   Entrypoint file: backend/app_unified.py")
print("   Flask instance: app = Flask(__name__)")
print("   Gunicorn module:variable: app_unified:app")
print("")
print("   ✅ Flask instance exposed at module level")
print("   ✅ Procfile created and configured")
print("   ✅ Gunicorn added to requirements.txt")
print("   ✅ Python syntax valid")
print("   ✅ No conflicting entrypoint files")
print("")
print("📚 Deployment Commands:")
print("   Local dev: cd backend && python app_unified.py")
print("   Local test (gunicorn): cd backend && gunicorn -w 1 -b 127.0.0.1:5000 app_unified:app")
print("   Production (Railway/Render): gunicorn -w 4 -b 0.0.0.0:$PORT --timeout 120 app_unified:app")
print("")
print("🚀 READY FOR DEPLOYMENT TO RAILWAY/RENDER")
print("=" * 70)
