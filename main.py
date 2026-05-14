import os
import asyncio
import logging
import sqlite3
from datetime import datetime, date
from threading import Thread
from concurrent.futures import ThreadPoolExecutor

import yfinance as yf
import pandas as pd
import pandas_ta as ta

from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler

# ====================== LOGGING ======================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("bot.log", encoding="utf-8"), logging.StreamHandler()]
)

# ====================== FLASK ======================
app_web = Flask(__name__)

@app_web.route('/')
def home():
    return "✅ BIST Trade Bot Aktif", 200

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app_web.run(host='0.0.0.0', port=port, debug=False)

# ====================== VERİTABANI ======================
def init_db():
    conn = sqlite3.connect('signals.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            date TEXT,
            ticker TEXT,
            price REAL,
            stop REAL,
            target REAL,
            kar REAL,
            rsi REAL,
            volume_ratio REAL,
            pattern TEXT
        )
    ''')
    conn.commit()
    conn.close()

# ====================== AYARLAR ======================
MY_CHAT_ID = 1033571271

HISSE_LISTESI = [
    "THYAO","GARAN","ISCTR","EREGL","BIMAS","ASELS","SASA","TUPRS","FROTO","KCHOL",
    "TCELL","PETKM","SISE","AKBNK","SAHOL","PGSUS","ARCLK","KOZAL","HEKTS","TOASO",
    "VESTL","ENKAI","GUBRF","ODAS","VESBE","TKFEN","HALKB","VAKBN","EKGYO","ASTOR",
    "KONTR","OYAKC","ALARK","SKBNK","YKBNK","BRSAN","KRDMD","EGEEN","DOHOL"
]

# ====================== VERİ ÇEKME & ANALİZ ======================
def get_stock_data(ticker: str):
    try:
        df = yf.download(f"{ticker}.IS", period="60d", interval="1h", 
                        progress=False, auto_adjust=True, timeout=15)
        
        if df.empty or len(df) < 120:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df = df.droplevel(0, axis=1)

        close = df['Close']
        high = df['High']
        low = df['Low']
        volume = df['Volume']
        current_price = round(float(close.iloc[-1]), 2)

        # İndikatörler
        rsi = ta.rsi(close, length=14)
        macd = ta.macd(close, fast=12, slow=26, signal=9)
        atr = ta.atr(high, low, close, length=14)
        ema9 = ta.ema(close, length=9)
        ema21 = ta.ema(close, length=21)
        ema50 = ta.ema(close, length=50)

        current_rsi = round(float(rsi.iloc[-1]), 1)
        macd_hist = float(macd['MACDh_12_26_9'].iloc[-1])
        atr_value = float(atr.iloc[-1])

        avg_volume = volume.rolling(20).mean().iloc[-1]
        volume_ratio = round(float(volume.iloc[-1] / avg_volume), 2) if avg_volume > 0 else 0

        # Güçlü Alım Koşulları
        if (current_rsi >= 35 and current_rsi <= 57 and
            macd_hist > 0 and macd_hist > macd['MACDh_12_26_9'].iloc[-2] and
            current_price > ema21.iloc[-1] and
            ema9.iloc[-1] > ema21.iloc[-1] > ema50.iloc[-1] and
            volume_ratio >= 1.45):

            stop_loss = round(current_price - (atr_value * 1.85), 2)
            risk = current_price - stop_loss
            target = round(current_price + (risk * 2.75), 2)
            kar = round(((target - current_price) / current_price) * 100, 1)

            pattern = "🔥 Çok Güçlü" if volume_ratio > 2.2 else "✅ Güçlü Setup"

            return {
                "kod": ticker,
                "fiyat": current_price,
                "stop": stop_loss,
                "hedef": target,
                "kar": kar,
                "rsi": current_rsi,
                "volume_ratio": volume_ratio,
                "pattern": pattern
            }
        return None

    except Exception as e:
        logging.error(f"{ticker} hatası: {e}")
        return None

# ====================== TARAMA ======================
async def sinyal_tara(update: Update = None, context: ContextTypes.DEFAULT_TYPE = None):
    if update:
        await update.message.reply_text("🔄 BIST taranıyor... (Güçlü Setup)")

    with ThreadPoolExecutor(max_workers=15) as executor:
        loop = asyncio.get_event_loop()
        tasks = [loop.run_in_executor(executor, get_stock_data, kod) for kod in HISSE_LISTESI]
        results = await asyncio.gather(*tasks)

    signals = [s for s in results if s]

    if not signals:
        if update:
            await update.message.reply_text("❌ Bu taramada güçlü sinyal bulunamadı.")
        return

    signals.sort(key=lambda x: x['volume_ratio'], reverse=True)

    mesaj = f"🚀 **GÜÇLÜ TRADE SETUP** ({len(signals)} adet) - {datetime.now().strftime('%H:%M')}\n\n"

    for s in signals[:8]:   # En fazla 8 tane göster
        mesaj += (
            f"**#{s['kod']}** {s['pattern']}\n"
            f"💰 Fiyat: `{s['fiyat']}` TL\n"
            f"🎯 Hedef: `{s['hedef']}` (+%{s['kar']})\n"
            f"🛑 Stop: `{s['stop']}`\n"
            f"📊 RSI: `{s['rsi']}` | Vol: `{s['volume_ratio']}`x\n"
            f"────────────────────\n\n"
        )

    await context.bot.send_message(chat_id=MY_CHAT_ID, text=mesaj, parse_mode='Markdown')

# ====================== BAŞLATMA ======================
if __name__ == '__main__':
    init_db()
    Thread(target=run_web, daemon=True).start()

    TOKEN = "8027732851:AAFTv0qeU0REVmvjaeCaG8ZkOfmK0ENjiJc"
    
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler('analiz', sinyal_tara))
    app.job_queue.run_repeating(sinyal_tara, interval=1800, first=20)  # 30 dakikada bir

    logging.info("✅ Bot başarıyla başlatıldı - Güçlü Trade Modu")
    print("🤖 Bot çalışıyor... /analiz komutunu kullanabilirsiniz.")
    
    app.run_polling(drop_pending_updates=True)
