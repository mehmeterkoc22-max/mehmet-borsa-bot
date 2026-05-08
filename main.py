import os
import io
import asyncio
import logging
import yfinance as yf
import pandas as pd
import mplfinance as mpf
import pytz
import matplotlib
from datetime import datetime
from flask import Flask
from threading import Thread
from concurrent.futures import ThreadPoolExecutor
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler

matplotlib.use('Agg')

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
gonderilen_hisseler = {}

# Test için az hisse (istediğin zaman hepsini aç)
HISSE_LISTESI = ["THYAO", "GARAN", "ISCTR", "EREGL", "BIMAS", "AKBNK", "SAHOL", "ASELS", 
                 "TUPRS", "SASA", "FROTO", "KCHOL", "TCELL", "PETKM", "SISE"]

# --- VERİ ÇEKME ---
def get_stock_data(ticker):
    try:
        symbol = f"{ticker}.IS"
        df = yf.download(symbol, period="5d", interval="15m", 
                        progress=False, auto_adjust=True, timeout=10)
        
        if df.empty or len(df) < 40:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df = df.droplevel(0, axis=1)

        close = df['Close']
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = -delta.where(delta < 0, 0).rolling(14).mean()
        df['RSI'] = 100 - (100 / (1 + gain/loss))

        exp1 = close.ewm(span=12, adjust=False).mean()
        exp2 = close.ewm(span=26, adjust=False).mean()
        df['MACD'] = exp1 - exp2
        df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()

        return {
            "kod": ticker,
            "fiyat": float(close.iloc[-1]),
            "rsi": float(df['RSI'].iloc[-1]),
            "rsi_prev": float(df['RSI'].iloc[-2]),
            "macd": float(df['MACD'].iloc[-1]),
            "macd_sig": float(df['Signal'].iloc[-1]),
            "df": df
        }
    except Exception as e:
        logging.error(f"{ticker} HATA: {e}")
        return None

# --- ANA TARAMA ---
async def sinyal_tara(context: ContextTypes.DEFAULT_TYPE):
    global gonderilen_hisseler
    logging.info("🔍 Tarama başladı...")

    await context.bot.send_message(chat_id=MY_CHAT_ID, text="📡 Veriler çekiliyor, lütfen bekleyin...")

    with ThreadPoolExecutor(max_workers=10) as executor:
        loop = asyncio.get_event_loop()
        tasks = [loop.run_in_executor(executor, get_stock_data, kod) for kod in HISSE_LISTESI]
        results = await asyncio.gather(*tasks)

    bulunan = 0
    sinyal_listesi = []

    for s in results:
        if not s: 
            continue

        rsi = s['rsi']
        macd_cross = s['macd'] > s['macd_sig']

        # Genişletilmiş test koşulu
        if (rsi < 48 and s['rsi_prev'] < rsi) or (rsi < 40) or (macd_cross and rsi < 52):
            bulunan += 1
            gonderilen_hisseler[s['kod']] = datetime.now().timestamp()

            buf = io.BytesIO()
            mpf.plot(s['df'].tail(50), type='candle', style='charles', savefig=buf, figsize=(10,6))
            buf.seek(0)

            mesaj = (
                f"🚀 **#{s['kod']} - SİNYAL**\n"
                f"💰 Fiyat: **{s['fiyat']:.2f}** TL\n"
                f"📊 RSI: **{rsi:.1f}** (önceki: {s['rsi_prev']:.1f})\n"
                f"📈 MACD: {'🟢' if macd_cross else '🔴'}"
            )

            keyboard = [[InlineKeyboardButton("📈 TradingView", 
                        url=f"https://www.tradingview.com/symbols/BIST-{s['kod']}/")]]

            await context.bot.send_photo(chat_id=MY_CHAT_ID, photo=buf, caption=mesaj,
                                       reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            await asyncio.sleep(0.6)

        else:
            # Sadece log için
            logging.info(f"{s['kod']:6} RSI: {rsi:.1f} | MACD Cross: {macd_cross}")

    await context.bot.send_message(
        chat_id=MY_CHAT_ID, 
        text=f"✅ **Tarama Tamamlandı**\n\nBulunan sinyal: **{bulunan}**\nToplam taranan: {len([r for r in results if r])}"
    )

# --- KOMUT ---
async def manuel_analiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⚡ Tarama başlatılıyor...")
    gonderilen_hisseler.clear()
    await sinyal_tara(context)

# --- BAŞLAT ---
if __name__ == '__main__':
    Thread(target=run_web).start()
    
    TOKEN = os.environ.get("TELEGRAM_TOKEN", "7984025004:AAGD1lLv5RGOIAiJ9wbQfaxSS7r6BGLteoA")
    app = ApplicationBuilder().token(TOKEN).build()

    app.job_queue.run_repeating(sinyal_tara, interval=600, first=10)
    app.add_handler(CommandHandler('analiz', manuel_analiz))

    logging.info("Bot başlatıldı...")
    app.run_polling()
