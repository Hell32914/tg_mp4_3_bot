# 🎵🎥 Telegram Media Converter Bot

[![Python](https://img.shields.io/badge/Python-3.7+-blue.svg)](https://www.python.org/)
[![Telegram](https://img.shields.io/badge/Telegram-Bot-blue.svg)](https://telegram.org/)

A smart Telegram bot that converts your media files into proper Telegram message formats!

## ✨ Features

- **🎵 MP3 to Voice**: Convert .mp3 files to Telegram voice messages (OGG Opus format)
- **🎥 MP4 to Video Note**: Convert .mp4 files to round video notes (60s max, 20MB max)
- **🔒 Secure**: Uses temporary files and automatic cleanup
- **📝 Logging**: Comprehensive error logging
- **🚀 Easy Setup**: Simple configuration file

## 🚀 Quick Start

### Prerequisites

- Python 3.7 or higher
- Telegram account
- ffmpeg (for audio/video conversion) — install separately and make sure `ffmpeg` is on your PATH. On Windows you can install via Chocolatey (`choco install ffmpeg`) or download and add to PATH.

### Installation

1. **Clone or download** this repository

2. **Create a Telegram Bot**:
   - Message [@BotFather](https://t.me/botfather) on Telegram
   - Use `/newbot` command and follow the instructions
   - Copy your bot token

3. **Configure bot token**:
   - Copy `config.example.py` to `config.py`
   - Open `config.py` file
   - Replace `YOUR_BOT_TOKEN_HERE` with your actual bot token from @BotFather
   - **Important**: `config.py` is in `.gitignore` to keep your token secure

4. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

5. **Run the bot**:
   ```bash
   python bot.py
   ```

## 📖 Usage

1. Start a chat with your bot
2. Send `/start` to see the welcome message
3. Send any `.mp3` file - get a voice message back! 🎤
4. Send any `.mp4` file - get a round video note back! ⭕

## 🛠️ Technical Details

- **MP3 Processing**: Files are converted to OGG format with Opus codec for optimal Telegram compatibility
- **MP4 Processing**: Files are sent as video notes (round videos) with validation:
  - Maximum duration: 60 seconds
  - Maximum size: 20 MB
  - Format: MP4 (Telegram handles conversion automatically)
- **Security**: All temporary files are automatically deleted after processing
- **Error Handling**: Graceful error messages with detailed logging

## 📋 Requirements

- `python-telegram-bot==20.7` - Telegram Bot API wrapper
- `moviepy==1.0.3` - Video/audio processing
- `requests` - HTTP requests
- `ffmpeg` - Audio/video codec (install separately)

## 🔒 Security Note

Your bot token is stored in `config.py` which is automatically excluded from Git commits via `.gitignore`. This prevents accidentally uploading sensitive information to public repositories.

**Never commit `config.py` to version control!**

## 📄 License

This project is open source. Feel free to use and modify.
