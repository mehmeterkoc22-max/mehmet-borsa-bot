import os
import asyncio
import logging
import yfinance as yf
import pandas as pd
from flask import Flask
from threading import Thread
from concurrent.futures import ThreadPoolExecutor
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- FLASK ---
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
        df = yf.download(symbol, period="15d", interval="30m", progress=False, auto_adjust=True, timeout=15)
        
        if df.empty or len(df) < 50:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df = df.droplevel(0, axis=1)

        close = df['Close']
        high = df['High']
        low = df['Low']

        # ==================== GÖSTERGELER ====================

        # Hareketli Ortalamalar
        df['SMA_20'] = close.rolling(20).mean()
        df['EMA_12'] = close.ewm(span=12, adjust=False).mean()
        df['EMA_26'] = close.ewm(span=26, adjust=False).mean()

        # MACD
        df['MACD'] = df['EMA_12'] - df['EMA_26']
        df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()

        # RSI
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = -delta.where(delta < 0, 0).rolling(14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))

        # Stokastik Osilatör
        lowest_low = low.rolling(14).min()
        highest_high = high.rolling(14).max()
        df['%K'] = 100 * (close - lowest_low) / (highest_high - lowest_low)
        df['%D'] = df['%K'].rolling(3).mean()

        # Bollinger Bantları
        df['BB_Middle'] = close.rolling(20).mean()
        bb_std = close.rolling(20).std()
        df['BB_Upper'] = df['BB_Middle'] + (bb_std * 2)
        df['BB_Lower'] = df['BB_Middle'] - (bb_std * 2)

        return {
            "kod": ticker,
            "fiyat": round(float(close.iloc[-1]), 2),
            "rsi": round(float(df['RSI'].iloc[-1]), 1),
            "macd": float(df['MACD'].iloc[-1]),
            "signal": float(df['Signal'].iloc[-1]),
            "stokastik_k": round(float(df['%K'].iloc[-1]), 1),
            "stokastik_d": round(float(df['%D'].iloc[-1]), 1),
            "bb_upper": round(float(df['BB_Upper'].iloc[-1]), 2),
            "bb_lower": round(float(df['BB_Lower'].iloc[-1]), 2),
            "bb_middle": round(float(df['BB_Middle'].iloc[-1]), 2)
        }
    except Exception as e:
        logging.error(f"{ticker} Hata: {e}")
        return None

async def sinyal_tara(context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=MY_CHAT_ID, text="📡 Tüm göstergeler ile tarama başladı...")

    with ThreadPoolExecutor(max_workers=10) as executor:
        loop = asyncio.get_event_loop()
        tasks = [loop.run_in_executor(executor, get_stock_data, kod) for kod in HISSE_LISTESI]
        results = await asyncio.gather(*tasks)

    valid = [s for s in results if s]
    valid.sort(key=lambda x: x['rsi'])

    mesaj = "📊 **BIST TEKNİK GÖSTERGE TARAMASI**\n\n"

    for s in valid:
        rsi = s['rsi']
        macd_guc = s['macd'] > s['signal']
        stokastik = s['stokastik_k']

        # Güçlü Sinyal Koşulu
        if (rsi <= 35) or (rsi <= 45 and macd_guc and stokastik < 30):
            mesaj += (
                f"🚀 **#{s['kod']}** - GÜÇLÜ ALIM\n"
                f"💰 Fiyat: **{s['fiyat']}** TL\n"
                f"📊 RSI: **{rsi}** (Aşırı Satım)\n"
                f"📈 MACD: {'🟢' if macd_guc else '🔴'}\n"
                f"📉 Stokastik: **{stokastik}**\n"
                f"🔰 Bollinger: {s['bb_lower']} - {s['bb_upper']}\n\n"
            )

    mesaj += f"✅ **Tarama Tamamlandı**\nToplam taranan: **{len(valid)}** hisse"

    await context.bot.send_message(chat_id=MY_CHAT_ID, text=mesaj, parse_mode='Markdown')

async def manuel_analiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Tüm teknik göstergelerle tarama başlatılıyor...")
    await sinyal_tara(context)

# --- BAŞLAT ---
if __name__ == '__main__':
    Thread(target=run_web).start()
    
    TOKEN = os.environ.get("TELEGRAM_TOKEN", "7984025004:AAGD1lLv5RGOIAiJ9wbQfaxSS7r6BGLteoA")
    app = ApplicationBuilder().token(TOKEN).build()

    app.job_queue.run_repeating(sinyal_tara, interval=1800, first=10)
    app.add_handler(CommandHandler('analiz', manuel_analiz))

    logging.info("Bot başlatıldı - Tüm göstergeler aktif")
    app.run_polling()
