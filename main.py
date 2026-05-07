import os
import threading
from flask import Flask
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes
)

# ================= WEB =================
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
    await update.message.reply_text("✅ Tarama aktif")

def run_bot():

    TOKEN = os.getenv("TELEGRAM_TOKEN")

    telegram_app = ApplicationBuilder().token(TOKEN).build()

    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CommandHandler("tara", tara))

    print("BOT BAŞLADI")

    telegram_app.run_polling()

# ================= MAIN =================
if __name__ == "__main__":

    threading.Thread(target=run_web).start()

    run_bot()
