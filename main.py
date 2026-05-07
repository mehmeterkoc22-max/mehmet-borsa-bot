import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Bot çalışıyor!")

def main():

    token = os.getenv("TELEGRAM_TOKEN")

    if not token:
        print("TOKEN YOK")
        return

    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("start", start))

    print("BOT BAŞLADI")

    app.run_polling()

if __name__ == "__main__":
    main()
