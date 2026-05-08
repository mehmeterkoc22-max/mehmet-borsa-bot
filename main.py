import os
import io
import asyncio
import logging
import yfinance as yf
import pandas as pd
import mplfinance as mpf
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

HISSE_LISTESI = ["THYAO", "GARAN", "ISCTR", "EREGL", "BIMAS", "ASELS", "SASA", "TUPRS"]

# --- GELİŞTİRİLMİŞ VERİ ÇEKME ---
def get_stock_data(ticker):
    try:
        symbol = f"{ticker}.IS"
        
        # Farklı parametre denemesi
        df = yf.download(
            symbol,
            period="10d",
            interval="30m",
            progress=False,
            auto_adjust=True,
            timeout=15,
            group_by='ticker'
        )
        
        if df is None or df.empty:
            # Alternatif yöntem dene
            df = yf.Ticker(symbol).history(period="10d", interval="30m")
        
        if df is None or df.empty or len(df) < 25:
            logging.warning(f"{ticker} → Veri boş")
            return None

        # Sütun düzeltme
        if isinstance(df.columns, pd.MultiIndex):
            df = df.droplevel(0, axis=1)
            
        if 'Close' not in df.columns:
            return None

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
        logging.error(f"{ticker} → HATA: {str(e)[:80]}")
        return None

# --- TARAMA ---
async def sinyal_tara(context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=MY_CHAT_ID, text="📡 Veriler çekiliyor...")

    with ThreadPoolExecutor(max_workers=6) as executor:
        loop = asyncio.get_event_loop()
        tasks = [loop.run_in_executor(executor, get_stock_data, kod) for kod in HISSE_LISTESI]
        results = await asyncio.gather(*tasks)

    basarili = len([r for r in results if r])
    bulunan = 0

    for s in results:
        if not s:
            continue

        bulunan += 1
        logging.info(f"✅ {s['kod']} | RSI: {s['rsi']:.1f}")

        buf = io.BytesIO()
        mpf.plot(s['df'].tail(40), type='candle', style='charles', savefig=buf, figsize=(10,6))
        buf.seek(0)

        mesaj = (
            f"🚀 **#{s['kod']}**\n"
            f"💰 Fiyat: **{s['fiyat']:.2f}** TL\n"
            f"📊 RSI: **{s['rsi']:.1f}**\n"
            f"📈 MACD: Güçlü"
        )

        keyboard = [[InlineKeyboardButton("📈 TradingView", 
                    url=f"https://www.tradingview.com/symbols/BIST-{s['kod']}/")]]

        await context.bot.send_photo(chat_id=MY_CHAT_ID, photo=buf, caption=mesaj,
                                   reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        await asyncio.sleep(0.8)

    await context.bot.send_message(
        chat_id=MY_CHAT_ID, 
        text=f"✅ **Tarama Tamamlandı**\n\nBaşarılı hisse: **{basarili}**\nSinyal: **{bulunan}**"
    )

# --- KOMUT ---
async def manuel_analiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Tarama başlatılıyor (8 hisse)...")
    await sinyal_tara(context)

# --- BAŞLAT ---
if __name__ == '__main__':
    Thread(target=run_web).start()
    
    TOKEN = os.environ.get("TELEGRAM_TOKEN", "7984025004:AAGD1lLv5RGOIAiJ9wbQfaxSS7r6BGLteoA")
    app = ApplicationBuilder().token(TOKEN).build()

    app.job_queue.run_repeating(sinyal_tara, interval=900, first=5)
    app.add_handler(CommandHandler('analiz', manuel_analiz))

    logging.info("Bot başlatıldı...")
    app.run_polling()
