import os
import asyncio
import logging
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
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
        if df.empty or len(df) < 50: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

        close, high, low, volume = df['Close'], df['High'], df['Low'], df['Volume']
        fiyat = round(float(close.iloc[-1]), 2)

        # Temel Göstergeler
        ema_200 = close.ewm(span=200, adjust=False).mean().iloc[-1]
        tr = pd.concat([high - low, abs(high - close.shift()), abs(low - close.shift())], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        
        # --- AGRESİF STRATEJİ HESAPLAMA ---
        stop = round(fiyat - (atr * 1.5), 2)
        risk = fiyat - stop
        hedef = round(fiyat + (risk * 4), 2) # 1:4 Risk/Ödül oranı
        kar_potansiyeli = round(((hedef - fiyat) / fiyat) * 100, 1)

        # Diğer Koşullar
        avg_vol = volume.rolling(20).mean().iloc[-1]
        hacim_ok = volume.iloc[-1] > (avg_vol * 1.5)
        st_up = fiyat > (((high + low) / 2) - (3 * tr.rolling(7).mean())).iloc[-1]
        bos = fiyat > high.rolling(20).max().iloc[-2]

        return {
            "kod": ticker, "fiyat": fiyat, "stop": stop, "hedef": hedef,
            "kar": kar_potansiyeli, "hacim": hacim_ok, "st_trend": st_up,
            "ema_200": ema_200, "bos": bos
        }
    except: return None

async def sinyal_tara(context: ContextTypes.DEFAULT_TYPE):
    with ThreadPoolExecutor(max_workers=30) as executor:
        loop = asyncio.get_event_loop()
        tasks = [loop.run_in_executor(executor, get_stock_data, kod) for kod in HISSE_LISTESI]
        results = await asyncio.gather(*tasks)

    valid = [s for s in results if s]
    mesaj = "🎯 **AGRESİF TREND SİNYALLERİ (%10+ Hedef)**\n\n"
    bulundu = False

    for s in valid:
        # FİLTRE: Trend Yukarı + Boğa + (Hacim veya BoS)
        if s['fiyat'] > s['ema_200'] and s['st_trend'] and (s['hacim'] or s['bos']):
            bulundu = True
            
            # Ara Uyarı Notu (Eğer potansiyel kâr yüksekse uyarıyı ekle)
            ara_uyari = ""
            if s['kar'] >= 8:
                ara_uyari = "⚠️ *Not: %5 kârda stopu giriş seviyesine çekmeyi unutma!*"

            mesaj += (
                f"🚀 **#{s['kod']}**\n"
                f"💰 **Giriş:** `{s['fiyat']}`\n"
                f"🎯 **Büyük Hedef:** `{s['hedef']}` (+%{s['kar']})\n"
                f"🛑 **Zarar Kes:** `{s['stop']}`\n"
                f"⚡ Durum: {'🔥 HACİM PATLAMASI' if s['hacim'] else 'Normal Hacim'}\n"
                f"{ara_uyari}\n\n"
            )
            
            if len(mesaj) > 3500:
                await context.bot.send_message(chat_id=MY_CHAT_ID, text=mesaj, parse_mode='Markdown')
                mesaj = ""

    if bulundu:
        await context.bot.send_message(chat_id=MY_CHAT_ID, text=mesaj, parse_mode='Markdown')

async def manuel_analiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Agresif tarama başlatıldı...")
    await sinyal_tara(context)

if __name__ == '__main__':
    Thread(target=run_web).start()
    TOKEN = "8027732851:AAFTv0qeU0REVmvjaeCaG8ZkOfmK0ENjiJc"
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler('analiz', manuel_analiz))
    app.job_queue.run_repeating(sinyal_tara, interval=300, first=10)
    app.run_polling()
