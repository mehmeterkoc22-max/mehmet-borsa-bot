import os
import time
import pandas as pd
import yfinance as yf
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ================= BIST HİSSELER =================
WATCHLIST = [
    "THYAO.IS", "ASELS.IS", "GARAN.IS", "KCHOL.IS",
    "AKBNK.IS", "BIMAS.IS", "SISE.IS", "EREGL.IS"
]

# ================= RSI =================
def rsi(series, period=14):
    delta = series.diff()

    gain = (delta.where(delta > 0, 0)).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()

    rs = gain / loss
    return 100 - (100 / (1 + rs))

# ================= AI YORUM =================
def ai_comment(rsi_val, change):
    if rsi_val < 30 and change > 0:
        return "AI: Güçlü dip alımı fırsatı olabilir"
    elif rsi_val > 70:
        return "AI: Aşırı alım bölgesi, düzeltme riski yüksek"
    elif change > 2:
        return "AI: Momentum güçlü, trend yukarı"
    elif change < -2:
        return "AI: Satış baskısı artıyor"
    else:
        return "AI: Yatay piyasa, bekleme"

# ================= ANALİZ =================
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
        signal = "🟢 AL"
    elif rsi_val > 70:
        signal = "🔴 SAT"
    else:
        signal = "⚪ BEKLE"

    ai = ai_comment(rsi_val, change)

    return {
        "symbol": symbol,
        "price": last,
        "rsi": rsi_val,
        "change": change,
        "signal": signal,
        "ai": ai
    }

# ================= RAPOR =================
def scan_market():

    text = "📊 PRO BIST AI SCANNER\n\n"

    for s in WATCHLIST:

        data = analyze(s)

        if not data:
            continue

        text += f"{data['symbol']}\n"
        text += f"💰 {data['price']:.2f}\n"
        text += f"📈 %{data['change']:.2f}\n"
        text += f"📊 RSI: {data['rsi']:.2f}\n"
        text += f"🎯 Sinyal: {data['signal']}\n"
        text += f"🤖 {data['ai']}\n\n"

    return text

# ================= TELEGRAM =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 PRO BIST AI BOT AKTİF\n/tara ile analiz"
    )

async def tara(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = scan_market()
    await update.message.reply_text(msg)

# ================= AUTO ALARM LOOP =================
def auto_alert(bot_app):

    last_state = {}

    while True:

        for s in WATCHLIST:

            data = analyze(s)

            if not data:
                continue

            key = s
            signal = data["signal"]

            # sadece değişince mesaj at
            if last_state.get(key) != signal:

                msg = f"""
🚨 BIST ALARM

{data['symbol']}
💰 {data['price']:.2f}
📊 RSI: {data['rsi']:.2f}
🎯 {signal}
🤖 {data['ai']}
"""

                bot_app.bot.send_message(chat_id=os.getenv("CHAT_ID"), text=msg)

                last_state[key] = signal

        time.sleep(300)  # 5 dakika

# ================= MAIN =================
def main():

    TOKEN = os.getenv("TELEGRAM_TOKEN")

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("tara", tara))

    print("PRO BIST AI BOT AKTİF")

    # alarm thread (opsiyonel)
    import threading
    threading.Thread(target=auto_alert, args=(app,), daemon=True).start()

    app.run_polling()

if __name__ == "__main__":
    main()
