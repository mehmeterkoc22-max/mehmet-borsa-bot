import os
import asyncio
import logging
import sqlite3
from datetime import datetime, date
from threading import Thread
from concurrent.futures import ThreadPoolExecutor
import yfinance as yf
import pandas as pd
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("bot.log", encoding="utf-8"), logging.StreamHandler()]
)

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
            patterns TEXT,
            pivot_s1 REAL
        )
    ''')
    conn.commit()
    conn.close()

def save_signal(signal):
    try:
        conn = sqlite3.connect('signals.db')
        cursor = conn.cursor()
        today = date.today().isoformat()
        cursor.execute('SELECT COUNT(*) FROM signals WHERE date = ? AND ticker = ?', (today, signal['kod']))
        if cursor.fetchone()[0] > 0:
            conn.close()
            return False
       
        cursor.execute('''
            INSERT INTO signals (timestamp, date, ticker, price, stop, target, kar, rsi, patterns, pivot_s1)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"), today, signal['kod'],
            signal['fiyat'], signal['stop'], signal['hedef'], signal['kar'],
            signal['rsi'], signal.get('patterns', ''), signal.get('pivot_s1')
        ))
        conn.commit()
        conn.close()
        return True
    except:
        return False

# ====================== AYARLAR ======================
MY_CHAT_ID = 1033571271

# Tüm BIST Hisseleri
HISSE_LISTESI = ["THYAO","GARAN","ISCTR","EREGL","BIMAS","ASELS","SASA","TUPRS","FROTO","KCHOL","TCELL","PETKM",
                 "SISE","AKBNK","SAHOL","PGSUS","ARCLK","KOZAL","HEKTS","TOASO","VESTL","ENKAI","GUBRF","ODAS",
                 "VESBE","TKFEN","HALKB","VAKBN","EKGYO","ASTOR","KONTR","OYAKC"]

# ====================== VERİ ÇEKME (ESNETİLMİŞ) ======================
def get_stock_data(ticker: str):
    try:
        df = yf.download(f"{ticker}.IS", period="40d", interval="1h", progress=False, auto_adjust=True, timeout=12)
        if df.empty or len(df) < 80:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df = df.droplevel(0, axis=1)
            
        close = df['Close']
        current_price = round(float(close.iloc[-1]), 2)

        # RSI
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = -delta.where(delta < 0, 0).rolling(14).mean()
        rsi = 100 - (100 / (1 + gain/loss))
        current_rsi = round(float(rsi.iloc[-1]), 1)

        # EMA
        ema20 = close.ewm(span=20, adjust=False).mean().iloc[-1]
        ema50 = close.ewm(span=50, adjust=False).mean().iloc[-1]

        # MACD
        exp1 = close.ewm(span=12, adjust=False).mean()
        exp2 = close.ewm(span=26, adjust=False).mean()
        macd_line = exp1 - exp2
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        macd_bullish = macd_line.iloc[-1] > signal_line.iloc[-1]

        # ATR
        tr = pd.concat([(df['High'] - df['Low']), abs(df['High'] - close.shift()), abs(df['Low'] - close.shift())], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]

        # ESNETİLMİŞ KOŞULLAR
        if (current_rsi < 52 and                  # RSI 52 altı
            macd_bullish and 
            current_price > ema20):               # Sadece EMA20 üstü yeterli
            
            stop_loss = round(current_price - (atr * 1.7), 2)
            target = round(current_price + (current_price - stop_loss) * 2.8, 2)
            kar = round(((target - current_price) / current_price) * 100, 1)

            return {
                "kod": ticker,
                "fiyat": current_price,
                "stop": stop_loss,
                "hedef": target,
                "kar": kar,
                "rsi": current_rsi,
                "patterns": "Esnetilmiş Sinyal"
            }
        return None
    except Exception as e:
        logging.error(f"{ticker} hatası: {e}")
        return None

# ====================== TARAMA ======================
async def sinyal_tara(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Tüm BIST taranıyor (Esnetilmiş Koşul)...")

    with ThreadPoolExecutor(max_workers=12) as executor:
        loop = asyncio.get_event_loop()
        tasks = [loop.run_in_executor(executor, get_stock_data, kod) for kod in HISSE_LISTESI]
        results = await asyncio.gather(*tasks)

    signals = [s for s in results if s]
    
    if not signals:
        await update.message.reply_text("🔍 Bu taramada sinyal bulunamadı.")
        return

    mesaj = f"🚀 **ESNETİLMİŞ SİNYAL** ({len(signals)} adet) - {datetime.now().strftime('%H:%M')}\n\n"
    
    for s in signals:
        mesaj += (
            f"**#{s['kod']}** 🔥\n"
            f"💰 Fiyat: `{s['fiyat']}` TL\n"
            f"🎯 Hedef: `{s['hedef']}` (+%{s['kar']})\n"
            f"🛑 Stop: `{s['stop']}`\n"
            f"📊 RSI: `{s['rsi']}`\n"
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
    app.job_queue.run_repeating(sinyal_tara, interval=1800, first=30)
    
    logging.info("✅ Bot başlatıldı - Koşullar esnetildi")
    app.run_polling(drop_pending_updates=True)
