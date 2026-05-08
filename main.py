import os
import asyncio
import logging
import yfinance as yf
import pandas as pd
import numpy as np
from flask import Flask
from threading import Thread
from concurrent.futures import ThreadPoolExecutor
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

app_web = Flask('')
@app_web.route('/')
def home(): return "Bot Aktif!", 200

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app_web.run(host='0.0.0.0', port=port)

# --- AYARLAR ---
MY_CHAT_ID = 1033571271
# TEST İÇİN LİSTEYİ KISALTTIK (Çalıştığını görmek için)
HISSE_LISTESI = ["THYAO", "GARAN", "ISCTR", "EREGL", "BIMAS", "ASELS", "SASA", "TUPRS", "FROTO", "AKBNK"]

def get_stock_data(ticker):
    try:
        symbol = f"{ticker}.IS"
        # 30m yerine 1h deneyelim, daha kararlıdır
        df = yf.download(symbol, period="60d", interval="1h", progress=False, auto_adjust=True)
        
        if df.empty:
            logging.warning(f"{ticker} verisi boş geldi.")
            return None

        # Sütun isimlerini temizle (yfinance MultiIndex hatası için)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # Temel verileri al
        close = df['Close']
        high = df['High']
        low = df['Low']
        
        # EMA 200 için yeterli veri yoksa pas geçme, en azından fiyatı göster
        ema_200 = close.ewm(span=200, adjust=False).mean().iloc[-1] if len(close) >= 200 else 0

        # RSI Hesapla
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / (loss + 1e-9)
        rsi = 100 - (100 / (1 + rs))

        return {
            "kod": ticker,
            "fiyat": round(float(close.iloc[-1]), 2),
            "ema_200": round(float(ema_200), 2),
            "rsi": round(float(rsi.iloc[-1]), 1)
        }
    except Exception as e:
        logging.error(f"{ticker} hatası: {str(e)}")
        return None

async def sinyal_tara(context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=MY_CHAT_ID, text="🔍 Veriler çekiliyor, lütfen bekleyin...")
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        loop = asyncio.get_event_loop()
        tasks = [loop.run_in_executor(executor, get_stock_data, kod) for kod in HISSE_LISTESI]
        results = await asyncio.gather(*tasks)

    valid = [s for s in results if s]
    
    if not valid:
        await context.bot.send_message(chat_id=MY_CHAT_ID, text="⚠️ Hiçbir hisseden veri alınamadı. yfinance hatası olabilir.")
        return

    mesaj = "🧪 **TEST SONUÇLARI**\n\n"
    for s in valid:
        mesaj += f"📊 **#{s['kod']}**\n💰 Fiyat: **{s['fiyat']}**\n📈 RSI: {s['rsi']}\n📏 EMA 200: {s['ema_200']}\n\n"

    await context.bot.send_message(chat_id=MY_CHAT_ID, text=mesaj, parse_mode='Markdown')

async def manuel_analiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await sinyal_tara(context)

if __name__ == '__main__':
    Thread(target=run_web).start()
    TOKEN = "8027732851:AAFTv0qeU0REVmvjaeCaG8ZkOfmK0ENjiJc"
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler('analiz', manuel_analiz))
    logging.info("Bot hazır...")
    app.run_polling()
