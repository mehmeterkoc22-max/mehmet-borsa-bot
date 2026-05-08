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
HISSE_LISTESI = [
    "THYAO", "GARAN", "ISCTR", "EREGL", "BIMAS", "ASELS", "SASA", "TUPRS", "FROTO", "KCHOL",
    "TCELL", "PETKM", "SISE", "AKBNK", "SAHOL", "YKBNK", "PGSUS", "ARCLK", "EKGYO", "KOZAL",
    "ASTOR", "KONTR", "YEOTK", "SMRTG", "ENJSA", "HEKTS", "OYAKC", "TOASO", "DOAS", "DOHOL",
    "ALARK", "MIATK", "GUBRF", "ZOREN", "BRSAN", "CIMSA", "VESTL", "ENKAI", "BEYAZ", "SOKM",
    "REEDR", "SDTTR", "MIPAZ", "EUPWR", "ALVES", "CWENE", "ADEL", "AGROT", "ALFAS", "ARDYZ"
]

def get_stock_data(ticker):
    try:
        symbol = f"{ticker}.IS"
        df = yf.download(symbol, period="100d", interval="1h", progress=False, auto_adjust=True)
        
        if df.empty or len(df) < 50:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        close = df['Close']
        high = df['High']
        low = df['Low']
        volume = df['Volume']

        # 1. EMA 200
        df['EMA_200'] = close.ewm(span=200, adjust=False).mean()
        
        # 2. RSI
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        df['RSI'] = 100 - (100 / (1 + (gain / (loss + 1e-9))))

        # 3. Supertrend (Basit Versiyon)
        atr = (high - low).rolling(7).mean()
        df['ST_Lower'] = ((high + low) / 2) - (3 * atr)
        is_st_up = close.iloc[-1] > df['ST_Lower'].iloc[-1]

        # 4. MACD
        exp1 = close.ewm(span=12, adjust=False).mean()
        exp2 = close.ewm(span=26, adjust=False).mean()
        macd = exp1 - exp2
        signal = macd.ewm(span=9, adjust=False).mean()

        # 5. SMC - BoS (Market Yapısı Kırılımı)
        recent_high = high.rolling(20).max().iloc[-2]
        is_bos_up = close.iloc[-1] > recent_high

        return {
            "kod": ticker,
            "fiyat": round(float(close.iloc[-1]), 2),
            "rsi": round(float(df['RSI'].iloc[-1]), 1),
            "ema_200": round(float(df['EMA_200'].iloc[-1]), 2),
            "st_trend": "🟢 BOĞA" if is_st_up else "🔴 AYI",
            "macd_ok": bool(macd.iloc[-1] > signal.iloc[-1]),
            "bos": is_bos_up
        }
    except Exception as e:
        return None

async def sinyal_tara(context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=MY_CHAT_ID, text="📡 Profesyonel tarama başladı...")
    
    with ThreadPoolExecutor(max_workers=30) as executor:
        loop = asyncio.get_event_loop()
        tasks = [loop.run_in_executor(executor, get_stock_data, kod) for kod in HISSE_LISTESI]
        results = await asyncio.gather(*tasks)

    valid = [s for s in results if s]
    mesaj = "🚀 **GÜÇLÜ TEKNİK SİNYALLER**\n\n"
    
    for s in valid:
        # ANA STRATEJİ FİLTRESİ:
        # Fiyat EMA 200 üstünde olacak + Supertrend Yeşil olacak + (RSI < 40 veya BoS kırılımı)
        if s['fiyat'] > s['ema_200'] and s['st_trend'] == "🟢 BOĞA":
            if s['rsi'] < 45 or s['bos']:
                mesaj += (
                    f"💎 **#{s['kod']}**\n"
                    f"💰 Fiyat: **{s['fiyat']}**\n"
                    f"📈 Trend: {s['st_trend']} (EMA 200 Üstü)\n"
                    f"📊 RSI: {s['rsi']} | MACD: {'🟢' if s['macd_ok'] else '🔴'}\n"
                    f"{'🔥 YAPI KIRILDI (BoS)!' if s['bos'] else '📉 Tepki Bölgesinde'}\n\n"
                )
                if len(mesaj) > 3500:
                    await context.bot.send_message(chat_id=MY_CHAT_ID, text=mesaj, parse_mode='Markdown')
                    mesaj = ""

    if not mesaj or mesaj == "🚀 **GÜÇLÜ TEKNİK SİNYALLER**\n\n":
        mesaj = "⚠️ Şu an kriterlere tam uyan (EMA 200 üstü ve Boğa) hisse bulunamadı."
    
    await context.bot.send_message(chat_id=MY_CHAT_ID, text=mesaj, parse_mode='Markdown')

async def manuel_analiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await sinyal_tara(context)

if __name__ == '__main__':
    Thread(target=run_web).start()
    TOKEN = "8027732851:AAFTv0qeU0REVmvjaeCaG8ZkOfmK0ENjiJc"
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler('analiz', manuel_analiz))
    app.run_polling()
