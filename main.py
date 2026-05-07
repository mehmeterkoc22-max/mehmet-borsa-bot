import os
import pandas as pd
import yfinance as yf
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ================= BIST HİSSELERİ =================
BIST_STOCKS = [
    "THYAO.IS",
    "ASELS.IS",
    "GARAN.IS",
    "KCHOL.IS",
    "AKBNK.IS",
    "BIMAS.IS",
    "SISE.IS",
    "EREGL.IS",
    "YKBNK.IS",
    "TUPRS.IS"
]

# ================= RSI =================
def rsi(data, period=14):
    delta = data.diff()

    gain = (delta.where(delta > 0, 0)).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()

    rs = gain / loss
    return 100 - (100 / (1 + rs))

# ================= ANALYZE =================
def analyze(symbol):

    df = yf.download(symbol, period="3mo", interval="1d", progress=False)

    if df.empty:
        return None

    close = df["Close"]

    rsi_val = rsi(close).iloc[-1]

    last = close.iloc[-1]
    prev = close.iloc[-2]

    change = ((last - prev) / prev) * 100

    if rsi_val < 30:
        signal = "🟢 AL (Aşırı Satım)"
    elif rsi_val > 70:
        signal = "🔴 SAT (Aşırı Alım)"
    elif change > 1:
        signal = "🟡 MOMENTUM AL"
    else:
        signal = "⚪ BEKLE"

    return {
        "symbol": symbol,
        "price": last,
        "rsi": rsi_val,
        "change": change,
        "signal": signal
    }

# ================= RAPOR =================
def build_report():

    text = "📊 BIST PRO TARAMA\n\n"

    for stock in BIST_STOCKS:

        data = analyze(stock)

        if not data:
            continue

        text += f"{stock}\n"
        text += f"💰 {data['price']:.2f}\n"
        text += f"📈 Günlük: %{data['change']:.2f}\n"
        text += f"📊 RSI: {data['rsi']:.2f}\n"
        text += f"🎯 Sinyal: {data['signal']}\n\n"

    return text

# ================= TELEGRAM =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 BIST Bot Aktif!\n/tara ile tarama yap")

async def tara(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = build_report()
    await update.message.reply_text(msg)

def main():

    TOKEN = os.getenv("TELEGRAM_TOKEN")

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("tara", tara))

    print("BIST BOT AKTİF")

    app.run_polling()

if __name__ == "__main__":
    main()
