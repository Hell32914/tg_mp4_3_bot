import subprocess
import sys
import os
import time

print("Starting bot launcher...")

# Change to bot directory
os.chdir(r'd:\python_repo\tg_mp4_3_bot')
print(f"Changed directory to: {os.getcwd()}")

# Check if files exist
if os.path.exists('bot.py'):
    print("✅ bot.py exists")
else:
    print("❌ bot.py not found")

if os.path.exists(r'venv\Scripts\python.exe'):
    print("✅ Python venv exists")
else:
    print("❌ Python venv not found")

# Try to run bot in background
try:
    print("Launching bot in background...")
    process = subprocess.Popen([
        r'd:\python_repo\tg_mp4_3_bot\venv\Scripts\python.exe',
        'bot.py'
    ])

    print(f"Bot process started with PID: {process.pid}")
    print("Waiting 5 seconds to check if bot is running...")

    time.sleep(5)

    if process.poll() is None:
        print("✅ Bot is running successfully!")
        print("Check bot.log for detailed logs")
        print("You can now send MP4 files to your bot")
    else:
        print(f"❌ Bot stopped with return code: {process.returncode}")

except Exception as e:
    print(f"❌ Error running bot: {e}")
