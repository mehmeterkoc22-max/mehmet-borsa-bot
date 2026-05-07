import os
import logging
import sys
import time
import threading
from flask import Flask
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telegram import Update

# ================= LOG =================
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)]
)

# ================= FLASK =================
app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "Elite Sniper Bot Aktif ✅", 200

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app_web.run(host='0.0.0.0', port=port)

# ================= TELEGRAM =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 Elite Sniper Bot Aktif!"
    )

async def tara(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ Tarama sistemi çalışıyor."
    )

def run_bot():

    TOKEN = os.environ.get("TELEGRAM_TOKEN")

    if not TOKEN:
        logging.error("❌ TELEGRAM_TOKEN bulunamadı")
        return

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("tara", tara))

    logging.info("🚀 Telegram bot başlatıldı")

    app.run_polling(drop_pending_updates=True)

# ================= MAIN =================
if __name__ == '__main__':

    # Flask server
    threading.Thread(target=run_web, daemon=True).start()

    # Telegram bot
    threading.Thread(target=run_bot, daemon=True).start()

    logging.info("✅ Sistem aktif")

    while True:
        time.sleep(30)
