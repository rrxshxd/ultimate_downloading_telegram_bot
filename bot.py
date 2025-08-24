from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv
import yt_dlp
import os

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello! Send me a link to YouTube, TikTok or Instagram video and I'll download it")

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()

    if not any(x in url for x in ["youtube.com", "youtu.be", "tiktok.com", "instagram.com"]):
        await update.message.reply_text("This doesn't look like a correct link. Please, provide YouTube, TikTok or Instagram link.")
        return

    await update.message.reply_text("Downloading video...")

    try:
        ydl_opts = {
            'format': 'mp4',
            'outtmpl': 'video.%(ext)s',
            'noplaylist': True,
            'merge_output_format': 'mp4'
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

        with open(filename, 'rb') as f:
            await update.message.reply_video(video=f)

        os.remove(filename)

    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))

    print("Bot started")
    app.run_polling()

if __name__ == "__main__":
    main()