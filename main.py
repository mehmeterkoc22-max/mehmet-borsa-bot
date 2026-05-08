import os
import asyncio
import logging
import yfinance as yf
from flask import Flask
from threading import Thread
from concurrent.futures import ThreadPoolExecutor
from telegram import Update
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

# Daha fazla hisse
HISSE_LISTESI = ["THYAO","GARAN","ISCTR","EREGL","BIMAS","ASELS","SASA","TUPRS","FROTO","KCHOL",
                 "TCELL","PETKM","SISE","AKBNK","HALKB","SAHOL","VAKBN","YKBNK","ARCLK","TOASO"]

def get_stock_data(ticker):
    try:
        symbol = f"{ticker}.IS"
        df = yf.download(symbol, period="10d", interval="30m", 
                        progress=False, auto_adjust=True, timeout=12)
        
        if df.empty or len(df) < 25:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df = df.droplevel(0, axis=1)

        close = df['Close']
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = -delta.where(delta < 0, 0).rolling(14).mean()
        df['RSI'] = 100 - (100 / (1 + gain/loss))

        return {
            "kod": ticker,
            "fiyat": round(float(close.iloc[-1]), 2),
            "rsi": round(float(df['RSI'].iloc[-1]), 1)
        }
    except:
        return None

async def sinyal_tara(context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=MY_CHAT_ID, text="📡 Tarama başladı...")

    with ThreadPoolExecutor(max_workers=10) as executor:
        loop = asyncio.get_event_loop()
        tasks = [loop.run_in_executor(executor, get_stock_data, kod) for kod in HISSE_LISTESI]
        results = await asyncio.gather(*tasks)

    valid = [s for s in results if s]
    valid.sort(key=lambda x: x['rsi'])

    mesaj = "📊 **BIST RSI TARAMASI**\n\n"
    dusuk = 0
    takip = 0

    for s in valid:
        rsi = s['rsi']
        if rsi <= 55:
            dusuk += 1
            mesaj += f"🚀 **#{s['kod']}** → RSI: **{rsi}** | Fiyat: **{s['fiyat']} TL**\n"
        elif rsi <= 68:                       # ← Eşiği yükselttik
            takip += 1
            mesaj += f"🔥 **#{s['kod']}** → RSI: **{rsi}** | Fiyat: **{s['fiyat']} TL**\n"
        else:
            mesaj += f"📊 #{s['kod']} → RSI: {rsi}\n"

    mesaj += f"\n✅ **Tarama Tamamlandı**\n"
    mesaj += f"🚀 RSI ≤ 55 : **{dusuk}** hisse\n"
    mesaj += f"🔥 RSI ≤ 68 : **{takip}** hisse (Takip Listesi)"

    await context.bot.send_message(chat_id=MY_CHAT_ID, text=mesaj, parse_mode='Markdown')

async def manuel_analiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Tarama başlatılıyor...")
    await sinyal_tara(context)

# --- BAŞLAT ---
if __name__ == '__main__':
    Thread(target=run_web).start()
    
    TOKEN = os.environ.get("TELEGRAM_TOKEN", "7984025004:AAGD1lLv5RGOIAiJ9wbQfaxSS7r6BGLteoA")
    app = ApplicationBuilder().token(TOKEN).build()

    app.job_queue.run_repeating(sinyal_tara, interval=900, first=10)
    app.add_handler(CommandHandler('analiz', manuel_analiz))

    logging.info("Bot başlatıldı...")
    app.run_polling()
