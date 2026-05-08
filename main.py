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

# --- FLASK (Render/Uptime için) ---
app_web = Flask('')
@app_web.route('/')
def home(): return "Bot Aktif!", 200

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app_web.run(host='0.0.0.0', port=port)

# --- AYARLAR ---
MY_CHAT_ID = 1033571271
HISSE_LISTESI = ["THYAO", "GARAN", "ISCTR", "EREGL", "BIMAS", "ASELS", "SASA", "TUPRS", "FROTO", "KCHOL",
                 "TCELL", "PETKM", "SISE", "AKBNK", "HALKB", "SAHOL", "VAKBN", "PGSUS"]

def get_stock_data(ticker):
    try:
        symbol = f"{ticker}.IS"
        # EMA 200 ve sağlıklı analiz için 60 günlük veri çekiyoruz
        df = yf.download(symbol, period="60d", interval="30m", progress=False, auto_adjust=True, timeout=15)
        
        if df.empty or len(df) < 200:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df = df.droplevel(0, axis=1)

        close = df['Close']
        high = df['High']
        low = df['Low']
        volume = df['Volume']

        # 1. EMA 50 & 200
        df['EMA_50'] = close.ewm(span=50, adjust=False).mean()
        df['EMA_200'] = close.ewm(span=200, adjust=False).mean()

        # 2. RSI (14)
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))

        # 3. MACD (12, 26, 9)
        df['EMA_12'] = close.ewm(span=12, adjust=False).mean()
        df['EMA_26'] = close.ewm(span=26, adjust=False).mean()
        df['MACD'] = df['EMA_12'] - df['EMA_26']
        df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()

        # 4. OBV (On-Balance Volume)
        df['OBV'] = (np.sign(close.diff()) * volume).fillna(0).cumsum()

        # 5. Supertrend (ATR 7, Multiplier 3)
        atr_p = 7
        mult = 3
        high_low = high - low
        high_cp = abs(high - close.shift())
        low_cp = abs(low - close.shift())
        tr = pd.concat([high_low, high_cp, low_cp], axis=1).max(axis=1)
        df['ATR'] = tr.rolling(atr_p).mean()
        
        df['ST_Lower'] = ((high + low) / 2) - (mult * df['ATR'])
        is_st_up = close.iloc[-1] > df['ST_Lower'].iloc[-1]

        # 6. Smart Money Concepts (BoS - Market Yapısı Kırılımı)
        # Son 20 mumun zirvesi hacimli kırılırsa BoS kabul edilir
        recent_high = high.rolling(20).max().iloc[-2]
        is_bos_up = close.iloc[-1] > recent_high and volume.iloc[-1] > volume.rolling(10).mean().iloc[-1]

        return {
            "kod": ticker,
            "fiyat": round(float(close.iloc[-1]), 2),
            "ema_50": round(float(df['EMA_50'].iloc[-1]), 2),
            "ema_200": round(float(df['EMA_200'].iloc[-1]), 2),
            "rsi": round(float(df['RSI'].iloc[-1]), 1),
            "macd_ok": bool(df['MACD'].iloc[-1] > df['Signal'].iloc[-1]),
            "st_trend": "🟢 BOĞA" if is_st_up else "🔴 AYI",
            "obv_pozitif": bool(df['OBV'].iloc[-1] > df['OBV'].iloc[-5]),
            "smc_bos": is_bos_up
        }
    except Exception as e:
        logging.error(f"{ticker} hatası: {e}")
        return None

async def sinyal_tara(context: ContextTypes.DEFAULT_TYPE):
    with ThreadPoolExecutor(max_workers=10) as executor:
        loop = asyncio.get_event_loop()
        tasks = [loop.run_in_executor(executor, get_stock_data, kod) for kod in HISSE_LISTESI]
        results = await asyncio.gather(*tasks)

    valid = [s for s in results if s]
    mesaj = "🚀 **SMC & TREND SİNYAL TARAMASI**\n\n"
    sinyal_bulundu = False

    for s in valid:
        # GÜÇLÜ ALIM KOŞULLARI:
        # 1. Fiyat EMA 200 üstünde olacak (Ana trend yukarı)
        # 2. Supertrend Boğa olacak
        # 3. Ya BoS kırılımı olacak ya da RSI aşırı satımdan dönecek
        if s['fiyat'] > s['ema_200'] and s['st_trend'] == "🟢 BOĞA":
            durum = "🔥 GÜÇLÜ AL" if s['smc_bos'] else "✅ TREND YUKARI"
            sinyal_bulundu = True
            mesaj += (
                f"📊 **#{s['kod']}** - {durum}\n"
                f"💰 Fiyat: **{s['fiyat']}**\n"
                f"📏 EMA 50/200: {s['ema_50']}/{s['ema_200']}\n"
                f"⚡ Supertrend: {s['st_trend']}\n"
                f"🌊 OBV: {'Para Girişi Var ✅' if s['obv_pozitif'] else 'Yatay ⚠️'}\n"
                f"📈 RSI/MACD: {s['rsi']} / {'🟢' if s['macd_ok'] else '🔴'}\n"
                f"{'💎 BOS KIRILIMI GELDİ!' if s['smc_bos'] else ''}\n\n"
            )

    if not sinyal_bulundu:
        mesaj += "Şu an kriterlere uygun hisse bulunamadı."

    await context.bot.send_message(chat_id=MY_CHAT_ID, text=mesaj, parse_mode='Markdown')

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Borsa Botu Aktif! 30 dakikada bir tarama yapar. /analiz ile manuel başlatabilirsin.")

async def manuel_analiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Detaylı teknik tarama başlatılıyor...")
    await sinyal_tara(context)

if __name__ == '__main__':
    Thread(target=run_web).start()
    TOKEN = "8027732851:AAFTv0qeU0REVmvjaeCaG8ZkOfmK0ENjiJc" # Buraya kendi tokenını gir
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler('start', start_cmd))
    app.add_handler(CommandHandler('analiz', manuel_analiz))
    
    # Her 30 dakikada bir (1800 saniye) otomatik tarama
    app.job_queue.run_repeating(sinyal_tara, interval=1800, first=10)

    logging.info("Bot çalışıyor...")
    app.run_polling()
