import os
import asyncio
import logging
from datetime import datetime
from threading import Thread
from concurrent.futures import ThreadPoolExecutor

import yfinance as yf
import pandas as pd

from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler

# ====================== LOGGING ======================
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)

# ====================== FLASK WEB SERVER ======================
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

# ====================== VERİ ÇEKME ======================
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

        fiyat = round(float(close.iloc[-1]), 2)

        # Temel Göstergeler
        ema_200 = close.ewm(span=200, adjust=False).mean().iloc[-1]
        tr = pd.concat([high - low, abs(high - close.shift()), abs(low - close.shift())], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]

        # Agresif Strateji
        stop = round(fiyat - (atr * 1.5), 2)
        risk = fiyat - stop
        hedef = round(fiyat + (risk * 4), 2)
        kar_potansiyeli = round(((hedef - fiyat) / fiyat) * 100, 1)

        # Diğer Koşullar
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
            "bos": bos
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
    mesaj = "🎯 **AGRESİF TREND SİNYALLERİ**\n\n"
    bulundu = False

    for s in valid:
        if s['fiyat'] > s['ema_200'] and s['st_trend'] and (s['hacim'] or s['bos']):
            bulundu = True
            
            ara_uyari = "⚠️ *Not: %5 kârda stopu girişe çek!* " if s['kar'] >= 8 else ""

            mesaj += (
                f"🚀 **#{s['kod']}**\n"
                f"💰 **Giriş:** `{s['fiyat']}`\n"
                f"🎯 **Hedef:** `{s['hedef']}` (+%{s['kar']})\n"
                f"🛑 **Stop:** `{s['stop']}`\n"
                f"⚡ Durum: {'🔥 HACİM PATLAMASI' if s['hacim'] else '📊 Normal'}\n"
                f"{ara_uyari}\n\n"
            )

            if len(mesaj) > 3500:
                await context.bot.send_message(chat_id=MY_CHAT_ID, text=mesaj, parse_mode='Markdown')
                mesaj = "🎯 **AGRESİF TREND SİNYALLERİ (Devam)**\n\n"

    if bulundu:
        await context.bot.send_message(chat_id=MY_CHAT_ID, text=mesaj, parse_mode='Markdown')
    else:
        logging.info("Bu taramada sinyal bulunamadı.")

# ====================== KEEP ALIVE ======================
async def keep_alive(context: ContextTypes.DEFAULT_TYPE):
    try:
        current_time = datetime.now().strftime("%H:%M:%S")
        logging.info(f"🟢 Keep-Alive Ping - {current_time}")
    except Exception as e:
        logging.error(f"Keep-alive hatası: {e}")

# ====================== MANUEL KOMUT ======================
async def manuel_analiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Agresif tarama başlatılıyor...")
    await sinyal_tara(context)

# ====================== ANA BAŞLANGIÇ ======================
if __name__ == '__main__':
    # Web server'ı ayrı thread'de çalıştır
    Thread(target=run_web, daemon=True).start()

    TOKEN = "8027732851:AAFTv0qeU0REVmvjaeCaG8ZkOfmK0ENjiJc"
    
    app = ApplicationBuilder().token(TOKEN).build()

    # Komutlar
    app.add_handler(CommandHandler('analiz', manuel_analiz))

    # Job'lar
    app.job_queue.run_repeating(sinyal_tara, interval=300, first=10)   # 5 dakikada bir
    app.job_queue.run_repeating(keep_alive, interval=240, first=30)    # 4 dakikada bir keep-alive

    logging.info("🤖 Bot başarıyla başlatıldı - Keep Alive aktif!")
    app.run_polling()
