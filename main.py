import os
import logging
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes
)

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 Bot aktif")

async def tara(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Tarama çalışıyor")

def main():

    TOKEN = os.getenv("TELEGRAM_TOKEN")

    if not TOKEN:
        print("TOKEN YOK")
        return

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("tara", tara))

    print("BOT BAŞLADI")

    app.run_polling()

if __name__ == "__main__":
    main()
