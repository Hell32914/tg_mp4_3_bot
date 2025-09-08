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

# Pillow compatibility: older moviepy uses Image.ANTIALIAS which was renamed in Pillow 10
try:
    from PIL import Image
    if not hasattr(Image, 'ANTIALIAS') and hasattr(Image, 'Resampling'):
        Image.ANTIALIAS = Image.Resampling.LANCZOS
except Exception:
    # if PIL not available, moviepy operations will fail later with clear error
    pass

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

# Final square side used for video notes
TARGET_SIDE: Final[int] = 360

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /start command."""
    if update.message:
        await update.message.reply_text(
            "🎵🎥 Send me media files to convert:\n"
            "• .mp3 → Voice message\n"
            "• .mp4 → Round video note (60s max, 20MB max)"
        )

async def diag(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Return diagnostic info: ffmpeg, moviepy, pillow and TARGET_SIDE."""
    info = []
    try:
        import subprocess
        from shutil import which
        ff = which('ffmpeg') is not None
        info.append(f"ffmpeg: {'found' if ff else 'missing'}")
    except Exception:
        info.append('ffmpeg: unknown')

    try:
        import moviepy
        info.append(f"moviepy: {moviepy.__version__}")
    except Exception:
        info.append('moviepy: missing')

    try:
        from PIL import Image
        info.append(f"Pillow: {Image.__version__}")
    except Exception:
        info.append('Pillow: missing')

    info.append(f"TARGET_SIDE: {TARGET_SIDE}")
    if update.message:
        await update.message.reply_text('\n'.join(info))

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
    """Process MP4 file: convert/send as video note (attempts: moviepy pad -> ffmpeg pad+compress -> regular video)."""
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

        # We'll attempt to convert/pad/trim/compress to a video_note; only if all fails we'll send regular video
        from moviepy.editor import VideoFileClip, CompositeVideoClip

        # Inspect video
        try:
            video_clip = VideoFileClip(temp_mp4_path)
            duration = video_clip.duration
            width, height = video_clip.size
            video_clip.close()

            logger.info(f"Video info: duration={duration:.1f}s, size={width}x{height}")

        except Exception as e:
            logger.warning(f"Could not check video properties: {e}")
            await update.message.reply_text("⚠️ Could not analyze video. Sending as regular video.")
            with open(temp_mp4_path, 'rb') as video_file:
                await update.message.reply_video(video_file)
            return

        # Trim if too long (we'll base attempts on max 60s)
        trim_needed = duration > 60

        # If square and short enough, send directly
        aspect_ratio = width / height
        is_square = 0.9 <= aspect_ratio <= 1.1
        if is_square and not trim_needed and os.path.getsize(temp_mp4_path) <= 20 * 1024 * 1024:
            with open(temp_mp4_path, 'rb') as video_file:
                await update.message.reply_video_note(video_file)
            logger.info('Sent original file as video_note')
            return

        # Try moviepy padding/resizing first
        try:
            await update.message.reply_text("⚠️ Video is not square or too large. I'll try to pad/compress and send as a video note.")

            video = VideoFileClip(temp_mp4_path)
            if trim_needed:
                video = video.subclip(0, 60)

            # target square size for video_note (choose 360 for good balance)
            TARGET_SIDE = 360
            max_side = max(video.w, video.h)
            from moviepy.video.VideoClip import ColorClip
            # background
            bg_clip = ColorClip(size=(max_side, max_side), color=(0, 0, 0), duration=video.duration)

            # resize preserving aspect to fit inside square
            from moviepy.video.fx.all import resize as vfx_resize
            # resize original to fit into target square, then pad to TARGET_SIDE and center
            if video.w >= video.h:
                video_resized = video.fx(vfx_resize, width=TARGET_SIDE)
            else:
                video_resized = video.fx(vfx_resize, height=TARGET_SIDE)

            # final composite at TARGET_SIDE
            bg_clip = ColorClip(size=(TARGET_SIDE, TARGET_SIDE), color=(0,0,0), duration=video.duration)
            comp = CompositeVideoClip([bg_clip, video_resized.set_position('center')])
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp_out:
                tmp_out_path = tmp_out.name
            comp.write_videofile(tmp_out_path, codec='libx264', audio_codec='aac', threads=0, verbose=False, logger=None)
            comp.close()
            video.close()
            video_resized.close()
            bg_clip.close()

            if os.path.getsize(tmp_out_path) <= 20 * 1024 * 1024:
                with open(tmp_out_path, 'rb') as vf:
                    await update.message.reply_video_note(vf)
                logger.info('Sent moviepy-padded file as video_note')
                try:
                    os.unlink(tmp_out_path)
                except Exception:
                    pass
                return
            else:
                logger.info('Moviepy padded file too large; will attempt ffmpeg compression')
                # keep tmp_out_path for potential use in compression attempts

        except Exception as e:
            logger.exception(f"Moviepy padding failed: {e}")

        # FFmpeg fallback + iterative compression attempts
        try:
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as temp_ff:
                temp_ff_path = temp_ff.name

            pad_filter = "pad=ceil(max(iw,ih)/2)*2:ceil(max(iw,ih)/2)*2:(ow-iw)/2:(oh-ih)/2:black"
            scale_filter = "scale='min(640,iw)':'min(640,ih)':force_original_aspect_ratio=decrease"
            vf = f"{pad_filter},{scale_filter}"

            import subprocess
            from shutil import which
            if which('ffmpeg') is None:
                logger.warning('ffmpeg not found in PATH for fallback')
                raise FileNotFoundError('ffmpeg not found')

            ffmpeg_cmd = [
                'ffmpeg', '-y', '-i', temp_mp4_path,
                '-t', '60',
                '-vf', vf,
                '-c:v', 'libx264', '-crf', '28', '-preset', 'veryfast',
                '-c:a', 'aac', '-b:a', '96k',
                temp_ff_path
            ]

            proc = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
            if proc.returncode != 0:
                logger.warning(f"ffmpeg fallback failed rc={proc.returncode}; stderr={proc.stderr}")
                raise RuntimeError('ffmpeg failed')

            # If small enough, send
            if os.path.getsize(temp_ff_path) <= 20 * 1024 * 1024:
                with open(temp_ff_path, 'rb') as vf:
                    await update.message.reply_video_note(vf)
                logger.info('Sent ffmpeg-padded file as video_note')
                try:
                    os.unlink(temp_ff_path)
                except Exception:
                    pass
                return

            # Iterative compression attempts
            attempts = [ {'crf':30,'scale':480}, {'crf':32,'scale':360}, {'crf':35,'scale':320} ]
            for a in attempts:
                with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp_try:
                    tmp_try_path = tmp_try.name

                vf_filter = f"{pad_filter},scale={a['scale']}:-2"
                ff_cmd = [
                    'ffmpeg','-y','-i', temp_mp4_path,
                    '-t','60','-vf', vf_filter,
                    '-c:v','libx264','-crf',str(a['crf']),'-preset','veryfast',
                    '-c:a','aac','-b:a','64k', tmp_try_path
                ]
                proc2 = subprocess.run(ff_cmd, capture_output=True, text=True)
                if proc2.returncode != 0:
                    logger.warning(f"ffmpeg compress attempt failed rc={proc2.returncode}; stderr={proc2.stderr}")
                    try:
                        if os.path.exists(tmp_try_path):
                            os.unlink(tmp_try_path)
                    except Exception:
                        pass
                    continue

                if os.path.getsize(tmp_try_path) <= 20 * 1024 * 1024:
                    with open(tmp_try_path, 'rb') as vf2:
                        await update.message.reply_video_note(vf2)
                    logger.info(f"Sent compressed video_note with crf={a['crf']} scale={a['scale']}")
                    try:
                        os.unlink(tmp_try_path)
                    except Exception:
                        pass
                    return
                else:
                    try:
                        os.unlink(tmp_try_path)
                    except Exception:
                        pass

            # All attempts failed: send regular video
            await update.message.reply_text('⚠️ Could not produce a small enough video note. Sending as regular video instead.')
            with open(temp_mp4_path, 'rb') as video_file:
                await update.message.reply_video(video_file)

        except FileNotFoundError:
            await update.message.reply_text('⚠️ ffmpeg not found on server; cannot perform fallback compression. Sending original video.')
            with open(temp_mp4_path, 'rb') as video_file:
                await update.message.reply_video(video_file)
        except Exception as e:
            logger.exception(f"FFmpeg processing failed: {e}")
            await update.message.reply_text('⚠️ Error converting video; sending original file.')
            with open(temp_mp4_path, 'rb') as video_file:
                await update.message.reply_video(video_file)

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
    application.add_handler(CommandHandler("diag", diag))
    # Accept documents, audio, video, voice messages
    application.add_handler(MessageHandler(filters.Document.ALL | filters.AUDIO | filters.VIDEO | filters.VOICE, handle_document))

    logger.info("Bot is running. Press Ctrl+C to stop.")
    application.run_polling()

if __name__ == '__main__':
    main()
