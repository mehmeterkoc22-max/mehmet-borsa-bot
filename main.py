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

def piyasa_acik_mi():
    now = datetime.now()
    # Hafta sonu kontrolü (Cumartesi=5, Pazar=6)
    if now.weekday() >= 5:
        return False
    # Saat kontrolü (09:55 - 18:10)
    current_time = now.strftime("%H:%M")
    if "09:55" <= current_time <= "18:10":
        return True
    return False

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

        # 1. EMA 200 (Trend)
        ema_200 = close.ewm(span=200, adjust=False).mean().iloc[-1]
        
        # 2. RSI (14)
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9))))

        # 3. ATR & Stop/Target
        tr = pd.concat([high - low, abs(high - close.shift()), abs(low - close.shift())], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        stop_loss = round(fiyat - (atr * 1.5), 2)
        hedef_fiyat = round(fiyat + ((fiyat - stop_loss) * 2), 2)

        # 4. Hacim Analizi (Anormal Lot Girişi)
        avg_vol = volume.rolling(20).mean().iloc[-1]
        hacim_patlamasi = volume.iloc[-1] > (avg_vol * 1.5)

        # 5. Supertrend & BoS
        st_lower = ((high + low) / 2) - (3 * tr.rolling(7).mean())
        is_st_up = fiyat > st_lower.iloc[-1]
        is_bos_up = fiyat > high.rolling(20).max().iloc[-2]

        return {
            "kod": ticker,
            "fiyat": fiyat,
            "rsi": round(float(rsi.iloc[-1]), 1),
            "ema_200": round(float(ema_200), 2),
            "st_trend": "🟢 BOĞA" if is_st_up else "🔴 AYI",
            "hacim_uyari": hacim_patlamasi,
            "bos": is_bos_up,
            "stop": stop_loss,
            "hedef": hedef_fiyat,
            "kar_oran": round(((hedef_fiyat - fiyat) / fiyat) * 100, 1)
        }
    except: return None

async def sinyal_tara(context: ContextTypes.DEFAULT_TYPE):
    # Piyasa saatleri dışında otomatik çalışmayı engelle (Manuel komutu engellemez)
    if not piyasa_acik_mi() and context.job:
        logging.info("Piyasa kapalı, tarama atlanıyor.")
        return

    with ThreadPoolExecutor(max_workers=30) as executor:
        loop = asyncio.get_event_loop()
        tasks = [loop.run_in_executor(executor, get_stock_data, kod) for kod in HISSE_LISTESI]
        results = await asyncio.gather(*tasks)

    valid = [s for s in results if s]
    mesaj = "📊 **GÜÇLÜ AL-SAT & HACİM SİNYALLERİ**\n\n"
    bulundu = False

    for s in valid:
        # FİLTRE: Trend Yukarı + Boğa + (Hacim veya BoS Kırılımı)
        if s['fiyat'] > s['ema_200'] and s['st_trend'] == "🟢 BOĞA":
            bulundu = True
            hacim_notu = "🔥 **YÜKSEK HACİM / LOT GİRİŞİ!**" if s['hacim_uyari'] else "Normal Hacim"
            mesaj += (
                f"💎 **#{s['kod']}**\n"
                f"✅ **Al:** `{s['fiyat']}` | {hacim_notu}\n"
                f"🎯 **Hedef:** `{s['hedef']}` (+%{s['kar_oran']})\n"
                f"🛑 **Stop:** `{s['stop']}`\n"
                f"📈 Trend: {s['st_trend']} | RSI: {s['rsi']}\n"
                f"{'🚀 YAPI KIRILIMI (BoS)!' if s['bos'] else ''}\n\n"
            )
            if len(mesaj) > 3500:
                await context.bot.send_message(chat_id=MY_CHAT_ID, text=mesaj, parse_mode='Markdown')
                mesaj = ""

    if not bulundu:
        mesaj = "⚠️ Şu an kriterlere uyan hacimli ve trendi güçlü hisse bulunamadı."
    
    await context.bot.send_message(chat_id=MY_CHAT_ID, text=mesaj, parse_mode='Markdown')

async def manuel_analiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Tarama başlatılıyor...")
    await sinyal_tara(context)

if __name__ == '__main__':
    Thread(target=run_web).start()
    TOKEN = "8027732851:AAFTv0qeU0REVmvjaeCaG8ZkOfmK0ENjiJc"
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler('analiz', manuel_analiz))
    app.job_queue.run_repeating(sinyal_tara, interval=1800, first=10)
    app.run_polling()
