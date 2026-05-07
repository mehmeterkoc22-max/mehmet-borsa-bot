import os
import logging
from flask import Flask
from threading import Thread
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes
)

# ================= LOG =================
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# ================= FLASK =================
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot aktif ✅"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# ================= TELEGRAM =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 Bot çalışıyor")

async def tara(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Tarama sistemi aktif")

def run_bot():

    TOKEN = os.environ.get("TELEGRAM_TOKEN")

    if not TOKEN:
        logging.error("TOKEN bulunamadı")
        return

    telegram_app = Application.builder().token(TOKEN).build()

    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CommandHandler("tara", tara))

    logging.info("Bot başlatılıyor...")

    telegram_app.run_polling()

# ================= MAIN =================
if __name__ == "__main__":

    web_thread = Thread(target=run_web)
    web_thread.start()

    run_bot()
