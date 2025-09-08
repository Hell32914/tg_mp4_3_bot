#!/usr/bin/env python3
"""
Simple test script to check if bot code works
"""

import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

try:
    from config import BOT_TOKEN
    print(f"✅ Config loaded successfully. Token: {BOT_TOKEN[:10]}...")

    from moviepy.editor import VideoFileClip
    print("✅ MoviePy imported successfully")

    print("✅ All imports successful!")
    print("Bot should work correctly.")

except ImportError as e:
    print(f"❌ Import error: {e}")
except Exception as e:
    print(f"❌ Error: {e}")
