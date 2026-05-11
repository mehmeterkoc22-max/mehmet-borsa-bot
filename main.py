import os
import asyncio
import logging
from datetime import datetime
from threading import Thread
from concurrent.futures import ThreadPoolExecutor

import yfinance as yf
import pandas as pd
import numpy as np

from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler

# ====================== LOGGING ======================
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)

# ====================== FLASK ======================
app_web = Flask('')

@app_web.route('/')
def home():
    return f"✅ Bot Aktif! - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", 200

@app_web.route('/ping')
def ping():
    return "pong", 200

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app_web.run(host='0.0.0.0', port=port, debug=False)

# ====================== AYARLAR ======================
MY_CHAT_ID = 1033571271

HISSE_LISTESI = [
    "THYAO", "GARAN", "ISCTR", "EREGL", "BIMAS", "ASELS", "SASA", "TUPRS", "FROTO", "KCHOL",
    "TCELL", "PETKM", "SISE", "AKBNK", "SAHOL", "YKBNK", "PGSUS", "ARCLK", "EKGYO", "KOZAL",
    "ASTOR", "KONTR", "YEOTK", "SMRTG", "ENJSA", "HEKTS", "OYAKC", "TOASO", "DOAS", "DOHOL",
    "ALARK", "MIATK", "GUBRF", "ZOREN", "BRSAN", "CIMSA", "VESTL", "ENKAI", "BEYAZ", "SOKM",
    "REEDR", "SDTTR", "MIPAZ", "EUPWR", "ALVES", "CWENE", "ADEL", "AGROT", "ALFAS", "ARDYZ"
]

# ====================== RSI HESAPLAMA ======================
def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = -delta.where(delta < 0, 0).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

# ====================== VERİ ÇEKME + PIVOT + HIDDEN BULLISH ======================
def get_stock_data(ticker):
    try:
        symbol = f"{ticker}.IS"
        df = yf.download(symbol, period="15d", interval="1h", progress=False, auto_adjust=True)
        
        if df.empty or len(df) < 60:
            return None
            
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        close = df['Close']
        high = df['High']
        low = df['Low']
        volume = df['Volume']

        fiyat = round(float(close.iloc[-1]), 2)

        # ====================== PIVOT NOKTALARI ======================
        df_daily = df.resample('1D').agg({'High': 'max', 'Low': 'min', 'Close': 'last'}).dropna()
        if len(df_daily) < 2:
            return None

        prev = df_daily.iloc[-2]
        pp = (prev['High'] + prev['Low'] + prev['Close']) / 3
        r1 = 2 * pp - prev['Low']
        s1 = 2 * pp - prev['High']
        r2 = pp + (prev['High'] - prev['Low'])
        s2 = pp - (prev['High'] - prev['Low'])
        r3 = pp + 2 * (prev['High'] - prev['Low'])
        s3 = pp - 2 * (prev['High'] - prev['Low'])

        # ====================== RSI ve HIDDEN BULLISH DIVERGENCE ======================
        rsi = calculate_rsi(close, 14)
        current_rsi = round(rsi.iloc[-1], 1) if not rsi.empty else None

        hidden_bullish_div = False

        # Son 12 mum içinde swing low tespiti (basit yöntem)
        if len(close) > 30 and not rsi.empty:
            for i in range(len(close) - 20, len(close) - 5):
                # Fiyat Higher Low + RSI Lower Low
                if (close.iloc[i] < close.iloc[i-5] and close.iloc[i] < close.iloc[i+5] and  # local low
                    rsi.iloc[i] < rsi.iloc[i-8] and rsi.iloc[i] < rsi.iloc[i+5]):          # RSI daha düşük
                    
                    # Son low ile karşılaştır
                    if (close.iloc[-1] > close.iloc[i] and rsi.iloc[-1] > rsi.iloc[i]):
                        hidden_bullish_div = True
                        break

        # ====================== DİĞER GÖSTERGELER ======================
        ema_200 = close.ewm(span=200, adjust=False).mean().iloc[-1]
        tr = pd.concat([high - low, abs(high - close.shift()), abs(low - close.shift())], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]

        stop = round(fiyat - (atr * 1.5), 2)
        risk = fiyat - stop
        hedef = round(fiyat + (risk * 4), 2)
        kar_potansiyeli = round(((hedef - fiyat) / fiyat) * 100, 1)

        avg_vol = volume.rolling(20).mean().iloc[-1]
        hacim_ok = volume.iloc[-1] > (avg_vol * 1.5)
        st_up = fiyat > (((high + low) / 2) - (3 * tr.rolling(7).mean())).iloc[-1]
        bos = fiyat > high.rolling(20).max().iloc[-2]

        return {
            "kod": ticker,
            "fiyat": fiyat,
            "stop": stop,
            "hedef": hedef,
            "kar": kar_potansiyeli,
            "hacim": hacim_ok,
            "st_trend": st_up,
            "ema_200": ema_200,
            "bos": bos,
            "pivot": round(pp, 2),
            "r1": round(r1, 2),
            "r2": round(r2, 2),
            "r3": round(r3, 2),
            "s1": round(s1, 2),
            "s2": round(s2, 2),
            "s3": round(s3, 2),
            "pivot_yukari": fiyat > pp,
            "hidden_bullish_div": hidden_bullish_div,
            "rsi": current_rsi
        }
    except Exception as e:
        logging.error(f"{ticker} verisi çekilirken hata: {e}")
        return None

# ====================== SİNYAL TARAMA ======================
async def sinyal_tara(context: ContextTypes.DEFAULT_TYPE):
    with ThreadPoolExecutor(max_workers=30) as executor:
        loop = asyncio.get_event_loop()
        tasks = [loop.run_in_executor(executor, get_stock_data, kod) for kod in HISSE_LISTESI]
        results = await asyncio.gather(*tasks)

    valid = [s for s in results if s]
    mesaj = "🎯 **AGRESİF TREND SİNYALLERİ (+ Pivot + Hidden Bullish)**\n\n"
    bulundu = False

    for s in valid:
        if (s['fiyat'] > s['ema_200'] and 
            s['st_trend'] and 
            (s['hacim'] or s['bos']) and 
            s['hidden_bullish_div']):                     # ← Hidden Bullish Filtre
            
            bulundu = True
            pivot_durum = "🟢 **Pivot Üstü**" if s['pivot_yukari'] else "🔴 Pivot Altı"
            ara_uyari = "⚠️ *%5 kârda stopu girişe çek!* " if s['kar'] >= 8 else ""

            mesaj += (
                f"🚀 **#{s['kod']}** 🔥 **Hidden Bullish**\n"
                f"💰 **Giriş:** `{s['fiyat']}`\n"
                f"🎯 **Hedef:** `{s['hedef']}` (+%{s['kar']})\n"
                f"🛑 **Stop:** `{s['stop']}`\n"
                f"📍 **Pivot:** `{s['pivot']}` | {pivot_durum}\n"
                f"⚡ Durum: {'🔥 HACİM PATLAMASI' if s['hacim'] else 'Normal'}\n"
                f"📊 RSI: `{s['rsi']}`\n"
                f"{ara_uyari}\n\n"
            )

            if len(mesaj) > 3800:
                await context.bot.send_message(chat_id=MY_CHAT_ID, text=mesaj, parse_mode='Markdown')
                mesaj = "🎯 **AGRESİF TREND SİNYALLERİ (Devam)**\n\n"

    if bulundu:
        await context.bot.send_message(chat_id=MY_CHAT_ID, text=mesaj, parse_mode='Markdown')
    else:
        logging.info("Bu taramada Hidden Bullish sinyali bulunamadı.")

# ====================== KEEP ALIVE ======================
async def keep_alive(context: ContextTypes.DEFAULT_TYPE):
    logging.info(f"🟢 Keep-Alive Ping - {datetime.now().strftime('%H:%M:%S')}")

# ====================== MANUEL KOMUT ======================
async def manuel_analiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Hidden Bullish Divergence taraması başlatılıyor...")
    await sinyal_tara(context)

# ====================== BAŞLAT ======================
if __name__ == '__main__':
    Thread(target=run_web, daemon=True).start()

    TOKEN = "8027732851:AAFTv0qeU0REVmvjaeCaG8ZkOfmK0ENjiJc"
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler('analiz', manuel_analiz))

    app.job_queue.run_repeating(sinyal_tara, interval=300, first=10)
    app.job_queue.run_repeating(keep_alive, interval=240, first=30)

    logging.info("🤖 Bot Hidden Bullish Divergence ile başlatıldı!")
    app.run_polling()
