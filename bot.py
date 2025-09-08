"""
Telegram Bot for Media Conversion

This bot converts .mp3 files to voice messages and .mp4 files to video messages.
"""

import logging
import os
import tempfile
from typing import Final

from moviepy.editor import AudioFileClip
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# Import configuration
from config import BOT_TOKEN

# Configure logging to file
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /start command."""
    if update.message:
        await update.message.reply_text(
            "🎵🎥 Send me media files to convert:\n"
            "• .mp3 → Voice message\n"
            "• .mp4 → Round video note (60s max, 20MB max)"
        )

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle document messages (.mp3 and .mp4 files)."""
    if not update.message:
        logger.warning("Received document but no message object")
        return
    # The user may send files in different fields: document, audio, video, voice
    document = update.message.document or update.message.audio or update.message.video or update.message.voice
    if not document:
        logger.warning("No document/audio/video/voice in message")
        await update.message.reply_text("📄 Please send a media file (.mp3 or .mp4).")
        return

    # Try to get a filename or mime type
    file_name = getattr(document, 'file_name', None)
    mime_type = getattr(document, 'mime_type', '') or getattr(document, 'mimetype', '')

    file_name_lower = (file_name or '').lower()
    logger.info(f"Received media: filename={file_name} mime={mime_type}")

    # Decide by extension first, then mime type
    if file_name_lower.endswith('.mp3') or 'audio/mpeg' in mime_type:
        await process_mp3(update, document)
    elif file_name_lower.endswith('.mp4') or 'video/mp4' in mime_type:
        await process_mp4(update, document)
    else:
        logger.info(f"Unsupported file type: {file_name_lower} / {mime_type}")
        await update.message.reply_text("📄 Please send .mp3 or .mp4 files only.")

async def process_mp3(update: Update, document) -> None:
    """Process MP3 file: convert to OGG and send as voice message."""
    if not update.message:
        return

    logger.info("Processing MP3 file...")
    temp_mp3_path = None
    temp_ogg_path = None
    try:
        file = await document.get_file()

        # Download to temporary file
        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as temp_mp3:
            await file.download_to_drive(temp_mp3.name)
            temp_mp3_path = temp_mp3.name

        # Convert to OGG for voice message (Telegram requires OGG Opus)
        with tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as temp_ogg:
            temp_ogg_path = temp_ogg.name

        audio_clip = AudioFileClip(temp_mp3_path)
        # Ensure mono and 48000 sample rate for optimal compatibility
        audio_clip.write_audiofile(temp_ogg_path, codec='libopus', fps=48000, ffmpeg_params=['-ac', '1'], verbose=False, logger=None)

        # Send as voice message
        with open(temp_ogg_path, 'rb') as voice_file:
            await update.message.reply_voice(voice_file)

        logger.info("MP3 processed successfully")

    except Exception as e:
        logger.exception(f"Error processing MP3: {e}")
        await update.message.reply_text("❌ Error processing the MP3 file. Please try again.")
    finally:
        # Clean up temporary files
        try:
            if temp_mp3_path and os.path.exists(temp_mp3_path):
                os.unlink(temp_mp3_path)
        except Exception:
            logger.warning("Failed to remove temp mp3")
        try:
            if temp_ogg_path and os.path.exists(temp_ogg_path):
                os.unlink(temp_ogg_path)
        except Exception:
            logger.warning("Failed to remove temp ogg")

async def process_mp4(update: Update, document) -> None:
    """Process MP4 file: send as video note (round video message)."""
    if not update.message:
        return

    logger.info("Processing MP4 file...")
    temp_mp4_path = None
    try:
        file = await document.get_file()

        # Download to temporary file
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as temp_mp4:
            await file.download_to_drive(temp_mp4.name)
            temp_mp4_path = temp_mp4.name

        # Check file size (video notes have 20MB limit)
        file_size = os.path.getsize(temp_mp4_path)
        if file_size > 20 * 1024 * 1024:  # 20MB
            await update.message.reply_text("❌ Video file is too large. Video notes must be under 20MB.")
            return

        # Check video duration and aspect ratio
        try:
            from moviepy.editor import VideoFileClip
            video_clip = VideoFileClip(temp_mp4_path)
            duration = video_clip.duration
            width, height = video_clip.size
            video_clip.close()

            logger.info(f"Video info: duration={duration:.1f}s, size={width}x{height}")

            if duration > 60:
                await update.message.reply_text("❌ Video is too long. Video notes must be under 60 seconds.")
                return

            # Check if video is square (required for video notes)
            aspect_ratio = width / height
            is_square = 0.9 <= aspect_ratio <= 1.1  # Allow some tolerance

            if not is_square:
                logger.info(f"Video is not square (aspect ratio: {aspect_ratio:.2f}), attempting to pad to square and send as video note")
                await update.message.reply_text("⚠️ Video is not square. I'll try to pad it to square and send as a video note.")

                # Try to pad/resize to square and re-encode to reduce size
                try:
                    with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as temp_padded:
                        temp_padded_path = temp_padded.name

                    from moviepy.editor import VideoFileClip, CompositeVideoClip

                    video = VideoFileClip(temp_mp4_path)
                    # Trim to 60s if needed
                    if video.duration > 60:
                        video = video.subclip(0, 60)

                    # Determine new square size (use max dimension)
                    max_side = max(video.w, video.h)
                    # Create background clip
                    # Create black background and composite the original video centered
                    from moviepy.video.VideoClip import ColorClip
                    from moviepy.video.fx.all import resize as vfx_resize
                    bg_clip = ColorClip(size=(max_side, max_side), color=(0, 0, 0), duration=video.duration)
                    # Resize input video to fit inside square while preserving aspect
                    target_w = video.w if video.w <= max_side else max_side
                    target_h = video.h if video.h <= max_side else max_side
                    # Use clip.resize to ensure it fits within the square
                    video_resized = video.fx(vfx_resize, width=target_w) if video.w >= video.h else video.fx(vfx_resize, height=target_h)
                    # Composite
                    comp = CompositeVideoClip([bg_clip, video_resized.set_position('center')])
                    comp.write_videofile(temp_padded_path, codec='libx264', audio_codec='aac', threads=0, verbose=False, logger=None)
                    comp.close()
                    video.close()
                    video_resized.close()
                    bg_clip.close()

                    # Check padded file size
                    padded_size = os.path.getsize(temp_padded_path)
                    if padded_size <= 20 * 1024 * 1024:
                        with open(temp_padded_path, 'rb') as vf:
                            await update.message.reply_video_note(vf)
                        logger.info('Sent padded video as video_note')
                    else:
                        await update.message.reply_text('⚠️ Padded video is still too large to send as video note. Sending as regular video instead.')
                        with open(temp_padded_path, 'rb') as vf:
                            await update.message.reply_video(vf)

                except Exception as e:
                    logger.exception(f"Failed to pad/convert video: {e}")
                    await update.message.reply_text("⚠️ Could not convert video to square. Sending as regular video.")
                    with open(temp_mp4_path, 'rb') as video_file:
                        await update.message.reply_video(video_file)
                finally:
                    try:
                        if 'temp_padded_path' in locals() and os.path.exists(temp_padded_path):
                            os.unlink(temp_padded_path)
                    except Exception:
                        logger.warning('Failed to remove temp padded file')
            else:
                # Send as video note (round video message)
                with open(temp_mp4_path, 'rb') as video_file:
                    await update.message.reply_video_note(video_file)

        except Exception as e:
            logger.warning(f"Could not check video properties: {e}")
            # Send as regular video if we can't check properties
            await update.message.reply_text("⚠️ Could not analyze video. Sending as regular video.")
            with open(temp_mp4_path, 'rb') as video_file:
                await update.message.reply_video(video_file)

        logger.info("MP4 processed successfully as video note")

    except Exception as e:
        logger.exception(f"Error processing MP4: {e}")
        await update.message.reply_text("❌ Error processing the MP4 file. Please try again.")
    finally:
        try:
            if temp_mp4_path and os.path.exists(temp_mp4_path):
                os.unlink(temp_mp4_path)
        except Exception:
            logger.warning("Failed to remove temp mp4")

def main() -> None:
    """Initialize and run the Telegram bot."""
    logger.info("Starting Telegram Media Converter Bot...")

    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Register handlers
    application.add_handler(CommandHandler("start", start))
    # Accept documents, audio, video, voice messages
    application.add_handler(MessageHandler(filters.Document.ALL | filters.AUDIO | filters.VIDEO | filters.VOICE, handle_document))

    logger.info("Bot is running. Press Ctrl+C to stop.")
    application.run_polling()

if __name__ == '__main__':
    main()
