import os
import asyncio
import logging
import yfinance as yf
import pandas as pd
from flask import Flask
from threading import Thread
from concurrent.futures import ThreadPoolExecutor
from telegram import Update
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

HISSE_LISTESI = ["THYAO", "GARAN", "ISCTR", "EREGL", "BIMAS", "ASELS", "SASA", "TUPRS", "FROTO", "KCHOL", 
                 "TCELL", "PETKM", "SISE", "AKBNK", "HALKB", "SAHOL"]

def get_stock_data(ticker):
    try:
        symbol = f"{ticker}.IS"
        df = yf.download(symbol, period="15d", interval="30m", progress=False, auto_adjust=True, timeout=15)
        
        if df.empty or len(df) < 30:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df = df.droplevel(0, axis=1)

        close = df['Close'].dropna()

        if len(close) < 30:
            return None

        # Daha sağlam RSI hesaplama
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(window=14, min_periods=1).mean()
        loss = -delta.clip(upper=0).rolling(window=14, min_periods=1).mean()
        
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        current_rsi = float(rsi.iloc[-1])
        
        # 0 veya NaN kontrolü
        if pd.isna(current_rsi) or current_rsi <= 0 or current_rsi > 100:
            current_rsi = 50.0

        return {
            "kod": ticker,
            "fiyat": round(float(close.iloc[-1]), 2),
            "rsi": round(current_rsi, 1)
        }
    except Exception as e:
        logging.error(f"{ticker} Hata: {e}")
        return None

async def sinyal_tara(context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=MY_CHAT_ID, text="📡 BIST taranıyor...")

    with ThreadPoolExecutor(max_workers=8) as executor:
        loop = asyncio.get_event_loop()
        tasks = [loop.run_in_executor(executor, get_stock_data, kod) for kod in HISSE_LISTESI]
        results = await asyncio.gather(*tasks)

    valid = [s for s in results if s]
    valid.sort(key=lambda x: x['rsi'])

    mesaj = "📊 **BIST RSI TARAMASI**\n\n"

    for s in valid:
        if s['rsi'] <= 65:
            mesaj += f"🔥 **#{s['kod']}** → RSI: **{s['rsi']}** | Fiyat: **{s['fiyat']} TL**\n"
        else:
            mesaj += f"📊 #{s['kod']} → RSI: {s['rsi']}\n"

    en_dusuk = valid[0]['rsi'] if valid else 0
    mesaj += f"\n✅ **Tarama Tamamlandı**\n**En düşük RSI: {en_dusuk}**"

    await context.bot.send_message(chat_id=MY_CHAT_ID, text=mesaj, parse_mode='Markdown')

async def manuel_analiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Tarama başlatılıyor...")
    await sinyal_tara(context)

# --- BAŞLAT ---
if __name__ == '__main__':
    Thread(target=run_web).start()
    
    TOKEN = os.environ.get("TELEGRAM_TOKEN", "7984025004:AAGD1lLv5RGOIAiJ9wbQfaxSS7r6BGLteoA")
    app = ApplicationBuilder().token(TOKEN).build()

    app.job_queue.run_repeating(sinyal_tara, interval=1800, first=10)
    app.add_handler(CommandHandler('analiz', manuel_analiz))

    logging.info("Bot başlatıldı...")
    app.run_polling()
