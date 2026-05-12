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
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

# ====================== FLASK ======================
app_web = Flask('')
@app_web.route('/')
def home(): return "Bot Aktif", 200
@app_web.route('/ping')
def ping(): return "PONG", 200

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app_web.run(host='0.0.0.0', port=port, debug=False)

# ====================== AYARLAR ======================
MY_CHAT_ID = 1033571271

# ====================== TÜM BIST HİSSELERİ (Ana + Yıldız Pazar) ======================
HISSE_LISTESI = [
    # Ana Pazar Popüler + Büyük Hisse Senetleri
    "THYAO","GARAN","ISCTR","EREGL","BIMAS","ASELS","SASA","TUPRS","FROTO","KCHOL","TCELL","PETKM",
    "SISE","AKBNK","SAHOL","YKBNK","PGSUS","ARCLK","EKGYO","KOZAL","ASTOR","KONTR","HEKTS","OYAKC",
    "TOASO","DOAS","GUBRF","VESTL","ENKAI","SOKM","BRSAN","CIMSA","ALARK","ODAS","VESBE","TKFEN",
    "HALKB","VAKBN","SKBNK","ISMEN","ISDMR","KRDMD","EREGL","KCHOL","SAHOL","TAVHL","TURSG","MIATK",
    
    # Yıldız Pazar ve Diğer Önemli Hisseler
    "GWIND","EUPWR","CWENE","YEOTK","SMRTG","ENJSA","REEDR","SDTTR","MOGAN","ALFAS","ARDYZ","AGROT",
    "BEYAZ","ALVES","ADEL","GESAN","KONKA","MAVI","LOGO","MPARK","NEURO","OTKAR","SAYAS","TABGD",
    "ULKER","YUNSA","ZOREN","BIOEN","BOBET","BTCIM","CANTE","CCOLA","DOHOL","ECILC","ECZYT","EGEEN",
    "ENKAI","FENER","GEDIK","GENIL","GIPTA","HEKTS","HRKET","IPEKE","IZMDC","KAYSE","KLSER","KOLSN",
    "KORDS","KOZAA","KTLEV","LMKDC","MHRGY","ODAS","PASEU","PEKGY","PTTGY","QUAGR","RALYH","SAYAS",
    "SKBNK","TABGD","TUKAS","TURSG","ULKER","VAKBN","VESBE","VESTL","YYLGD"
]

# ====================== VERİ ÇEKME ======================
def get_stock_data(ticker):
    try:
        df = yf.download(f"{ticker}.IS", period="12d", interval="1h", progress=False, auto_adjust=True, timeout=10)
        if df.empty or len(df) < 60:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        close = df['Close']
        high = df['High']
        low = df['Low']
        volume = df['Volume']

        fiyat = round(float(close.iloc[-1]), 2)

        # Göstergeler
        ema_50 = close.ewm(span=50, adjust=False).mean().iloc[-1]
        ema_200 = close.ewm(span=200, adjust=False).mean().iloc[-1]
        
        # RSI
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = -delta.where(delta < 0, 0).rolling(14).mean()
        rsi = 100 - (100 / (1 + gain/loss))
        current_rsi = round(float(rsi.iloc[-1]), 1)

        # MACD
        exp12 = close.ewm(span=12, adjust=False).mean()
        exp26 = close.ewm(span=26, adjust=False).mean()
        macd = exp12 - exp26
        signal = macd.ewm(span=9, adjust=False).mean()
        macd_guc = macd.iloc[-1] > signal.iloc[-1]

        # ATR
        tr = pd.concat([high - low, abs(high - close.shift()), abs(low - close.shift())], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]

        # Hacim
        avg_vol = volume.rolling(20).mean().iloc[-1]
        hacim_guc = volume.iloc[-1] > (avg_vol * 1.4)

        # ==================== KALİTELİ SİNYAL KOŞULU ====================
        if (fiyat > ema_50 and fiyat > ema_200 and 
            32 < current_rsi < 48 and 
            macd_guc and hacim_guc):

            stop = round(fiyat - (atr * 1.75), 2)
            risk = max(fiyat - stop, 0.01)
            hedef = round(fiyat + (risk * 3), 2)      # 1:3 Risk/Reward
            kar_orani = round(((hedef - fiyat) / fiyat) * 100, 1)

            return {
                "kod": ticker,
                "fiyat": fiyat,
                "stop": stop,
                "hedef": hedef,
                "kar": kar_orani,
                "rsi": current_rsi,
                "hacim_guc": hacim_guc
            }
        return None

    except Exception as e:
        # logging.error(f"{ticker} Hata: {e}")
        return None

# ====================== TARAMA ======================
async def sinyal_tara(context: ContextTypes.DEFAULT_TYPE, update=None):
    try:
        if update:
            await update.message.reply_text(f"🔄 Tüm BIST ({len(HISSE_LISTESI)} hisse) taranıyor...\nBu işlem 40-60 saniye sürebilir.")
        else:
            await context.bot.send_message(MY_CHAT_ID, "🔄 Otomatik tarama başladı...")

        with ThreadPoolExecutor(max_workers=12) as executor:
            loop = asyncio.get_event_loop()
            tasks = [loop.run_in_executor(executor, get_stock_data, kod) for kod in HISSE_LISTESI]
            results = await asyncio.gather(*tasks)

        valid = [s for s in results if s]
        
        if not valid:
            await context.bot.send_message(MY_CHAT_ID, "🔍 Bu taramada yeterince güçlü sinyal bulunamadı.")
            return

        mesaj = "🚀 **TÜM BIST KALİTE SİNYAL TARAMASI**\n\n"
        for s in valid:
            mesaj += (
                f"**#{s['kod']}** 🔥\n"
                f"💰 Giriş: `{s['fiyat']}` TL\n"
                f"🎯 Hedef: `{s['hedef']}` (+%{s['kar']})\n"
                f"🛑 Stop: `{s['stop']}`\n"
                f"📊 RSI: `{s['rsi']}`\n"
                f"📈 Hacim: {'✅ Güçlü' if s['hacim_guc'] else '❌'}\n"
                f"────────────────────────\n\n"
            )

        await context.bot.send_message(chat_id=MY_CHAT_ID, text=mesaj, parse_mode='Markdown')

    except Exception as e:
        logging.error(f"Tarama hatası: {e}")
        await context.bot.send_message(MY_CHAT_ID, "❌ Tarama sırasında hata oluştu.")

async def manuel_analiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    asyncio.create_task(sinyal_tara(context, update))

# ====================== BAŞLAT ======================
if __name__ == '__main__':
    Thread(target=run_web, daemon=True).start()
    
    TOKEN = "8027732851:AAFTv0qeU0REVmvjaeCaG8ZkOfmK0ENjiJc"
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler('analiz', manuel_analiz))
    app.job_queue.run_repeating(sinyal_tara, interval=1800, first=30)  # 30 dakikada bir
    
    logging.info(f"🤖 Bot Güncellendi - Tüm BIST ({len(HISSE_LISTESI)} hisse) Aktif")
    app.run_polling()
