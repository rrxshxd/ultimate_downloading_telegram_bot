import os
import asyncio
import logging
import tempfile
import uuid
from urllib.parse import urlparse

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.request import HTTPXRequest
from dotenv import load_dotenv
import yt_dlp

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# --- Logging (VPS-friendly) ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("ultimate-downloading-bot")

# --- Global concurrency limit (prevents VPS overload) ---
DOWNLOAD_SEMAPHORE = asyncio.Semaphore(3)  # tune 2-4 for most VPS setups

# --- Safer domain allowlist ---
ALLOWED_HOSTS = {
    "youtube.com", "www.youtube.com", "youtu.be",
    "tiktok.com", "www.tiktok.com", "vm.tiktok.com", "vt.tiktok.com",
    "instagram.com", "www.instagram.com",
    "x.com", "www.x.com",
    "twitter.com", "www.twitter.com",
    "pinterest.com", "www.pinterest.com", "pin.it", "www.pin.it", "pinimg.com",
}


def     is_allowed_url(url: str) -> bool:
    try:
        host = (urlparse(url.strip()).hostname or "").lower()
        return any(host == d or host.endswith("." + d) for d in ALLOWED_HOSTS)
    except Exception:
        return False


def download_video(url: str, out_dir: str) -> str:
    base = f"video_{uuid.uuid4().hex}"
    outtmpl = os.path.join(out_dir, base + ".%(ext)s")

    ydl_opts = {
        # Reliable selector that tends to yield mp4
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": outtmpl,
        "noplaylist": True,
        "merge_output_format": "mp4",

        # Keep logs clean; flip quiet=False while debugging
        "quiet": True,
        "no_warnings": True,

        # Network timeout
        "socket_timeout": 60,

        # Headers can help on some platforms
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:102.0) "
                "Gecko/20100101 Firefox/102.0"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        },
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)

    # If merge happens, ensure we return the mp4 path
    if not filename.lower().endswith(".mp4"):
        mp4_candidate = os.path.splitext(filename)[0] + ".mp4"
        if os.path.exists(mp4_candidate):
            filename = mp4_candidate

    if not os.path.exists(filename):
        raise FileNotFoundError("Downloaded file not found after download/merge.")

    return filename


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hello! Thanks for using Ultimate Downloading Bot! Please send a link to the video.\n"
        "The current supported platforms are:\n"
        "1) Instagram\n"
        "2) TikTok\n"
        "3) X (former Twitter)\n\n"
        "YouTube support is currently in development."
    )


async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = (update.message.text or "").strip()

    if not is_allowed_url(url):
        await update.message.reply_text(
            "This doesn't look like a correct link. Please provide an Instagram, TikTok, X/Twitter, or YouTube link."
        )
        return

    await update.message.reply_text("Downloading video...")
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action=ChatAction.TYPING
    )

    try:
        # Limit concurrent downloads to protect your VPS
        async with DOWNLOAD_SEMAPHORE:
            # Unique temp folder per request prevents collisions and guarantees cleanup
            with tempfile.TemporaryDirectory(prefix="video_bot_") as tmpdir:
                # yt-dlp is blocking -> offload to a thread
                filename = await asyncio.to_thread(download_video, url, tmpdir)

                await context.bot.send_chat_action(
                    chat_id=update.effective_chat.id, action=ChatAction.UPLOAD_VIDEO
                )
                with open(filename, "rb") as f:
                    await update.message.reply_video(video=f)

    except yt_dlp.utils.DownloadError:
        await update.message.reply_text(
            "Failed to download this video. It may be private/restricted or the platform changed something."
        )
        log.exception("yt-dlp DownloadError for url=%s", url)

    except Exception as e:
        await update.message.reply_text(f"Error: {type(e).__name__}")
        log.exception("Unexpected error for url=%s", url)


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing. Set it in the environment or in your .env file.")

    request = HTTPXRequest(
        connect_timeout=30,
        read_timeout=300,
        write_timeout=300,
        pool_timeout=30,
    )

    app = Application.builder().token(BOT_TOKEN).request(request).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))

    log.info("Bot started")
    app.run_polling(close_loop=False)


if __name__ == "__main__":
    main()
