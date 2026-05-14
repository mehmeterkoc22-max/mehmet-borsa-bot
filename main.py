import os
import asyncio
import logging
import sqlite3
from datetime import datetime, date
from threading import Thread
from concurrent.futures import ThreadPoolExecutor

import yfinance as yf
import pandas as pd
import pandas_ta as ta  # ← Yeni ekliyoruz (daha iyi indikatörler için)

from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler("bot.log", encoding="utf-8"), logging.StreamHandler()])

# ====================== FLASK ======================
app_web = Flask(__name__)
@app_web.route('/')
def home(): return "Bot Aktif", 200

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
            macd_hist REAL,
            volume_ratio REAL,
            pattern TEXT
        )
    ''')
    conn.commit()
    conn.close()

# ====================== AYARLAR ======================
MY_CHAT_ID = 1033571271

# Daha geniş liste (istediğin kadar genişletebilirsin)
HISSE_LISTESI = ["THYAO","GARAN","ISCTR","EREGL","BIMAS","ASELS","SASA","TUPRS","FROTO","KCHOL",
                 "TCELL","PETKM","SISE","AKBNK","SAHOL","PGSUS","ARCLK","KOZAL","HEKTS","TOASO",
                 "VESTL","ENKAI","GUBRF","ODAS","VESBE","TKFEN","HALKB","VAKBN","EKGYO","ASTOR",
                 "KONTR","OYAKC","ALARK","SKBNK","YKBNK","BRSAN","TCELL","KRDMD","EGEEN"]

# ====================== GELİŞMİŞ VERİ ÇEKME ======================
def get_stock_data(ticker: str):
    try:
        # 1h verisi + son 60 gün
        df = yf.download(f"{ticker}.IS", period="60d", interval="1h", progress=False, auto_adjust=True)
        if df.empty or len(df) < 100:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df = df.droplevel(0, axis=1)

        df['Close'] = df['Close'].astype(float)
        close = df['Close']
        volume = df['Volume']
        current_price = round(float(close.iloc[-1]), 2)

        # ==================== İNDİKATÖRLER ====================
        # RSI
        rsi = ta.rsi(close, length=14)
        current_rsi = round(float(rsi.iloc[-1]), 1)

        # MACD
        macd = ta.macd(close, fast=12, slow=26, signal=9)
        macd_hist = float(macd['MACDh_12_26_9'].iloc[-1])

        # EMA'lar
        ema9 = ta.ema(close, length=9).iloc[-1]
        ema21 = ta.ema(close, length=21).iloc[-1]
        ema50 = ta.ema(close, length=50).iloc[-1]

        # ATR
        atr = ta.atr(df['High'], df['Low'], close, length=14).iloc[-1]

        # Volume Ratio (son 1 saat hacmi / 20 dönem ortalaması)
        avg_volume = volume.rolling(20).mean().iloc[-1]
        volume_ratio = round(float(volume.iloc[-1] / avg_volume), 2) if avg_volume > 0 else 0

        # Fiyat pozisyonu
        above_ema21 = current_price > ema21
        strong_trend = current_price > ema50 and ema9 > ema21 > ema50

        # ==================== SIKI FİLTRELER (Trade Yapılabilir) ====================
        conditions = (
            current_rsi < 58 and current_rsi > 35 and           # Aşırı alım-satım bölgesi dışında
            macd_hist > 0 and macd_hist > macd_hist.iloc[-2] and # MACD histogram pozitif ve yükseliyor
            above_ema21 and
            volume_ratio > 1.4 and                               # Hacim genişlemesi
            strong_trend                                         # Güçlü trend
        )

        if conditions:
            stop_loss = round(current_price - (atr * 1.8), 2)
            risk = current_price - stop_loss
            target = round(current_price + (risk * 2.8), 2)      # 1:2.8 RR
            kar = round(((target - current_price) / current_price) * 100, 1)

            pattern = "Güçlü Yükseliş Setup" if strong_trend and volume_ratio > 2.0 else "İyi Setup"

            return {
                "kod": ticker,
                "fiyat": current_price,
                "stop": stop_loss,
                "hedef": target,
                "kar": kar,
                "rsi": current_rsi,
                "macd_hist": round(macd_hist, 4),
                "volume_ratio": volume_ratio,
                "pattern": pattern
            }
        return None

    except Exception as e:
        logging.error(f"{ticker} hatası: {e}")
        return None

# ====================== TARAMA ======================
async def sinyal_tara(update: Update = None, context: ContextTypes.DEFAULT_TYPE = None):
    mesaj_baslangic = "🔍 **GÜÇLÜ TRADE SETUP TARAMASI** başlatılıyor...\n"
    if update:
        await update.message.reply_text(mesaj_baslangic)
    else:
        logging.info("Otomatik tarama başladı")

    with ThreadPoolExecutor(max_workers=15) as executor:
        loop = asyncio.get_event_loop()
        tasks = [loop.run_in_executor(executor, get_stock_data, kod) for kod in HISSE_LISTESI]
        results = await asyncio.gather(*tasks)

    signals = [s for s in results if s is not None]

    if not signals:
        if update:
            await update.message.reply_text("❌ Bu taramada güçlü setup bulunamadı.")
        return

    # En iyi sinyalleri volume_ratio'ya göre sırala
    signals.sort(key=lambda x: x['volume_ratio'], reverse=True)

    mesaj = f"🚀 **GÜÇLÜ TRADE SİNYALLERİ** ({len(signals)} adet) - {datetime.now().strftime('%H:%M')}\n\n"

    for s in signals[:8]:  # En fazla 8 tane göster
        mesaj += (
            f"**#{s['kod']}** 🔥\n"
            f"💰 Fiyat: `{s['fiyat']}` TL\n"
            f"🎯 Hedef: `{s['hedef']}` (+%{s['kar']})\n"
            f"🛑 Stop: `{s['stop']}`\n"
            f"📊 RSI: `{s['rsi']}` | Vol Ratio: `{s['volume_ratio']}`\n"
            f"📌 {s['pattern']}\n"
            f"────────────────────\n\n"
        )

    await context.bot.send_message(chat_id=MY_CHAT_ID, text=mesaj, parse_mode='Markdown')

# ====================== BAŞLAT ======================
if __name__ == '__main__':
    init_db()
    Thread(target=run_web, daemon=True).start()

    TOKEN = "8027732851:AAFTv0qeU0REVmvjaeCaG8ZkOfmK0ENjiJc"
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler('analiz', sinyal_tara))
    app.job_queue.run_repeating(sinyal_tara, interval=1800, first=30)  # 30 dakikada bir

    logging.info("✅ Bot başlatıldı - Güçlü Trade Setup Modu")
    app.run_polling(drop_pending_updates=True)
