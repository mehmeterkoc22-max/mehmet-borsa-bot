import os
import asyncio
import logging
import time
import random
from datetime import datetime
from threading import Thread
from concurrent.futures import ThreadPoolExecutor

import yfinance as yf
import pandas as pd

from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

# ====================== FLASK ======================
app_web = Flask('')

@app_web.route('/')
def home():
    return f"✅ Bot Aktif! - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", 200

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app_web.run(host='0.0.0.0', port=port, debug=False)

# ====================== AYARLAR ======================
MY_CHAT_ID = 1033571271

HISSE_LISTESI = ["THYAO", "GARAN", "ISCTR", "EREGL", "BIMAS", "ASELS", "SASA", "TUPRS", "FROTO", "KCHOL",
    "TCELL", "PETKM", "SISE", "AKBNK", "SAHOL", "YKBNK", "PGSUS", "ARCLK", "EKGYO", "KOZAL",
    "ASTOR", "KONTR", "YEOTK", "SMRTG", "ENJSA", "HEKTS", "OYAKC", "TOASO", "DOAS", "DOHOL",
    "ALARK", "MIATK", "GUBRF", "ZOREN", "BRSAN", "CIMSA", "VESTL", "ENKAI", "BEYAZ", "SOKM",
    "REEDR", "SDTTR", "MIPAZ", "EUPWR", "ALVES", "CWENE", "ADEL", "AGROT", "ALFAS", "ARDYZ"]

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = -delta.where(delta < 0, 0).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

# ====================== VERİ ÇEKME ======================
def get_stock_data(ticker):
    try:
        df = yf.download(f"{ticker}.IS", period="12d", interval="1h", progress=False, auto_adjust=True, timeout=10)
        if df.empty or len(df) < 40:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        close = df['Close']
        high = df['High']
        low = df['Low']
        volume = df['Volume']
        fiyat = round(float(close.iloc[-1]), 2)

        # Pivot
        df_daily = df.resample('1D').agg({'High':'max','Low':'min','Close':'last'}).dropna()
        if len(df_daily) < 2:
            return None
        prev = df_daily.iloc[-2]
        pp = (prev['High'] + prev['Low'] + prev['Close']) / 3
        r1 = 2*pp - prev['Low']
        s1 = 2*pp - prev['High']
        r2 = pp + (prev['High']-prev['Low'])
        s2 = pp - (prev['High']-prev['Low'])
        r3 = pp + 2*(prev['High']-prev['Low'])
        s3 = pp - 2*(prev['High']-prev['Low'])

        rsi = calculate_rsi(close)
        current_rsi = round(rsi.iloc[-1], 1)

        ema_200 = close.ewm(span=200, adjust=False).mean().iloc[-1]
        tr = pd.concat([high-low, abs(high-close.shift()), abs(low-close.shift())], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]

        stop = round(fiyat - (atr * 1.5), 2)
        risk = max(fiyat - stop, 0.01)
        hedef = round(fiyat + (risk * 4), 2)
        kar = round(((hedef - fiyat) / fiyat) * 100, 1)

        avg_vol = volume.rolling(20).mean().iloc[-1]
        hacim_ok = volume.iloc[-1] > (avg_vol * 1.5)
        st_up = fiyat > (((high + low) / 2) - (3 * tr.rolling(7).mean())).iloc[-1]

        time.sleep(random.uniform(0.35, 0.65))

        return {
            "kod": ticker, "fiyat": fiyat, "stop": stop, "hedef": hedef, "kar": kar,
            "hacim": hacim_ok, "st_trend": st_up, "ema_200": ema_200,
            "pivot": round(pp,2), "r1":round(r1,2), "r2":round(r2,2), "r3":round(r3,2),
            "s1":round(s1,2), "s2":round(s2,2), "s3":round(s3,2),
            "pivot_yukari": fiyat > pp, "rsi": current_rsi
        }
    except:
        return None

# ====================== ANA FONKSİYON ======================
async def sinyal_tara(context: ContextTypes.DEFAULT_TYPE, update=None):
    try:
        if update:
            await update.message.reply_text("🔄 Tarama başladı... (30-40 sn sürebilir)")
        else:
            await context.bot.send_message(MY_CHAT_ID, "🔄 Otomatik tarama başladı...")

        with ThreadPoolExecutor(max_workers=10) as executor:
            loop = asyncio.get_event_loop()
            tasks = [loop.run_in_executor(executor, get_stock_data, kod) for kod in HISSE_LISTESI]
            results = await asyncio.gather(*tasks)

        valid = [s for s in results if s]
        sinyal_sayisi = 0
        mesaj = "🎯 **AGRESİF TREND SİNYALLERİ**\n\n"

        for s in valid:
            if s['fiyat'] > s['ema_200'] and s['st_trend'] and s['hacim']:
                sinyal_sayisi += 1
                pivot_durum = "🟢 Üstü" if s['pivot_yukari'] else "🔴 Altı"

                mesaj += (
                    f"🚀 **#{s['kod']}**\n"
                    f"Giriş: `{s['fiyat']}` | Hedef: `{s['hedef']}` (+%{s['kar']})\n"
                    f"Stop: `{s['stop']}` | RSI: `{s['rsi']}`\n"
                    f"📍 Pivot: `{s['pivot']}` {pivot_durum}\n"
                    f"R1:`{s['r1']}` R2:`{s['r2']}` | S1:`{s['s1']}` S2:`{s['s2']}`\n"
                    f"────────────────────\n\n"
                )

                if len(mesaj) > 3800:
                    await context.bot.send_message(MY_CHAT_ID, mesaj, parse_mode='Markdown')
                    mesaj = ""

        if sinyal_sayisi > 0:
            await context.bot.send_message(MY_CHAT_ID, mesaj, parse_mode='Markdown')
        else:
            await context.bot.send_message(MY_CHAT_ID, "🔍 Bu taramada güçlü sinyal bulunamadı.")

    except Exception as e:
        logging.error(f"Genel hata: {e}")
        try:
            await context.bot.send_message(MY_CHAT_ID, f"❌ İşlem sırasında hata: {str(e)[:150]}")
        except:
            pass

# ====================== KOMUT ======================
async def manuel_analiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    asyncio.create_task(sinyal_tara(context, update))   # Async olarak çalıştır

# ====================== BAŞLAT ======================
if __name__ == '__main__':
    Thread(target=run_web, daemon=True).start()

    TOKEN = "8027732851:AAFTv0qeU0REVmvjaeCaG8ZkOfmK0ENjiJc"
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler('analiz', manuel_analiz))

    app.job_queue.run_repeating(sinyal_tara, interval=300, first=30)

    logging.info("🤖 Bot Telefon Uyumlu Versiyon Başlatıldı")
    app.run_polling()
