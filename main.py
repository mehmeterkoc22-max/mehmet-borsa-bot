import os
import asyncio
import logging
import yfinance as yf
import pandas as pd
from datetime import datetime
from flask import Flask
from threading import Thread
from concurrent.futures import ThreadPoolExecutor
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- FLASK ---
app_web = Flask('')
@app_web.route('/')
def home(): return "Bot Aktif!", 200

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app_web.run(host='0.0.0.0', port=port)

# --- AYARLAR ---
MY_CHAT_ID = 1033571271

HISSE_LISTESI = ["THYAO", "GARAN", "ISCTR", "EREGL", "BIMAS", "ASELS", "SASA", "TUPRS", "FROTO", "KCHOL"]

# --- VERİ ÇEKME ---
def get_stock_data(ticker):
    try:
        symbol = f"{ticker}.IS"
        df = yf.download(symbol, period="10d", interval="30m", 
                        progress=False, auto_adjust=True, timeout=15)
        
        if df.empty or len(df) < 30:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df = df.droplevel(0, axis=1)

        close = df['Close']
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = -delta.where(delta < 0, 0).rolling(14).mean()
        df['RSI'] = 100 - (100 / (1 + gain/loss))

        exp1 = close.ewm(span=12, adjust=False).mean()
        exp2 = close.ewm(span=26, adjust=False).mean()
        df['MACD'] = exp1 - exp2
        df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()

        return {
            "kod": ticker,
            "fiyat": float(close.iloc[-1]),
            "rsi": float(df['RSI'].iloc[-1]),
            "rsi_prev": float(df['RSI'].iloc[-2]),
            "macd": float(df['MACD'].iloc[-1]),
            "macd_sig": float(df['Signal'].iloc[-1])
        }
    except Exception as e:
        logging.error(f"{ticker} HATA: {str(e)[:80]}")
        return None

# --- ANA TARAMA (SADECE METİN) ---
async def sinyal_tara(context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=MY_CHAT_ID, text="📡 Tarama başladı...")

    with ThreadPoolExecutor(max_workers=8) as executor:
        loop = asyncio.get_event_loop()
        tasks = [loop.run_in_executor(executor, get_stock_data, kod) for kod in HISSE_LISTESI]
        results = await asyncio.gather(*tasks)

    bulunan = 0
    for s in results:
        if not s: 
            continue

        rsi = s['rsi']
        macd_guc = s['macd'] > s['macd_sig']

        # Koşul çok gevşek
        if rsi < 55 and s['rsi'] > s['rsi_prev']:
            bulunan += 1
            mesaj = (
                f"🚀 **#{s['kod']} - SİNYAL**\n"
                f"💰 Fiyat: **{s['fiyat']:.2f}** TL\n"
                f"📊 RSI: **{rsi:.1f}** (önceki: {s['rsi_prev']:.1f})\n"
                f"📈 MACD: {'🟢' if macd_guc else '🔴'}"
            )
            await context.bot.send_message(chat_id=MY_CHAT_ID, text=mesaj, parse_mode='Markdown')

        else:
            # Tüm hisselerin RSI'ını görmek için
            await context.bot.send_message(
                chat_id=MY_CHAT_ID, 
                text=f"📊 **#{s['kod']}** → RSI: **{rsi:.1f}**"
            )

    await context.bot.send_message(
        chat_id=MY_CHAT_ID, 
        text=f"✅ **Tarama Tamamlandı**\nBulunan sinyal: **{bulunan}**"
    )

# --- KOMUT ---
async def manuel_analiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Tarama başlatılıyor...")
    await sinyal_tara(context)

# --- BAŞLAT ---
if __name__ == '__main__':
    Thread(target=run_web).start()
    
    TOKEN = os.environ.get("TELEGRAM_TOKEN", "7984025004:AAGD1lLv5RGOIAiJ9wbQfaxSS7r6BGLteoA")
    app = ApplicationBuilder().token(TOKEN).build()

    app.job_queue.run_repeating(sinyal_tara, interval=900, first=10)
    app.add_handler(CommandHandler('analiz', manuel_analiz))

    logging.info("Bot başlatıldı...")
    app.run_polling()
