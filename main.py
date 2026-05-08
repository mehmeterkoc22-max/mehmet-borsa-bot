import os
import asyncio
import logging
import yfinance as yf
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

# Tüm BIST Hisseleri
HISSE_LISTESI = ["THYAO","GARAN","ISCTR","EREGL","BIMAS","ASELS","SASA","TUPRS","FROTO","KCHOL","TCELL","PETKM",
                 "SISE","AKBNK","HALKB","SAHOL","VAKBN","YKBNK","ARCLK","TOASO","PGSUS","EKGYO","ODAS","HEKTS"]  # Test için önce az tuttuk, sonra genişleteceğiz

def get_stock_data(ticker):
    try:
        symbol = f"{ticker}.IS"
        df = yf.download(symbol, period="8d", interval="30m", progress=False, auto_adjust=True, timeout=10)
        
        if df.empty or len(df) < 35:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df = df.droplevel(0, axis=1)

        close = df['Close']
        high = df['High']
        low = df['Low']

        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = -delta.where(delta < 0, 0).rolling(14).mean()
        rsi = 100 - (100 / (1 + gain/loss))

        exp1 = close.ewm(span=12, adjust=False).mean()
        exp2 = close.ewm(span=26, adjust=False).mean()
        macd = exp1 - exp2
        signal = macd.ewm(span=9, adjust=False).mean()

        tr = pd.concat([(high - low), abs(high - close.shift()), abs(low - close.shift())], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]

        return {
            "kod": ticker,
            "fiyat": round(float(close.iloc[-1]), 2),
            "rsi": round(float(rsi.iloc[-1]), 1),
            "macd_guc": macd.iloc[-1] > signal.iloc[-1],
            "atr": round(atr, 2)
        }
    except:
        return None

async def sinyal_tara(context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=MY_CHAT_ID, text="📡 Tüm BIST taranıyor...")

    with ThreadPoolExecutor(max_workers=10) as executor:
        loop = asyncio.get_event_loop()
        tasks = [loop.run_in_executor(executor, get_stock_data, kod) for kod in HISSE_LISTESI]
        results = await asyncio.gather(*tasks)

    valid = [s for s in results if s]
    valid.sort(key=lambda x: x['rsi'])   # En düşük RSI üstte

    bulunan = 0
    mesaj = "🚀 **BIST SİNYAL TARAMASI**\n\n"

    for s in valid:
        rsi = s['rsi']
        
        # Gevşetilmiş koşul
        if rsi <= 62 and s['macd_guc']:
            bulunan += 1
            giris = s['fiyat']
            hedef = round(giris + (s['atr'] * 2.5), 2)
            stop = round(giris - (s['atr'] * 1.5), 2)

            mesaj += (
                f"🚀 **#{s['kod']}** 🔥\n"
                f"💰 Giriş: **{giris}**\n"
                f"🎯 Hedef: **{hedef}**\n"
                f"🛑 Stop: **{stop}**\n"
                f"📊 RSI: **{rsi}**\n\n"
            )

    # En düşük RSI'lı 8 hisseyi de göster
    mesaj += "📉 **EN DÜŞÜK RSI HİSSELER**\n"
    for s in valid[:8]:
        mesaj += f"#{s['kod']} → RSI: **{s['rsi']}**\n"

    mesaj += f"\n✅ **Tarama Tamamlandı**\nBulunan sinyal: **{bulunan}**"

    await context.bot.send_message(chat_id=MY_CHAT_ID, text=mesaj, parse_mode='Markdown')

async def manuel_analiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Tüm BIST taranıyor, lütfen bekleyin...")
    await sinyal_tara(context)

# --- BAŞLAT ---
if __name__ == '__main__':
    Thread(target=run_web).start()
    
    TOKEN = os.environ.get("TELEGRAM_TOKEN", "7984025004:AAGD1lLv5RGOIAiJ9wbQfaxSS7r6BGLteoA")
    app = ApplicationBuilder().token(TOKEN).build()

    app.job_queue.run_repeating(sinyal_tara, interval=1800, first=10)
    app.add_handler(CommandHandler('analiz', manuel_analiz))

    logging.info("Bot başlatıldı...")
    app.run_polling()
