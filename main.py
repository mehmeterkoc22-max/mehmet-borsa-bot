import os
import asyncio
import logging
from datetime import datetime
from threading import Thread
from concurrent.futures import ThreadPoolExecutor

import yfinance as yf
import pandas as pd
import numpy as np

from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("bot.log", encoding="utf-8"), logging.StreamHandler()]
)

# ====================== FLASK ======================
app_web = Flask(__name__)

@app_web.route('/')
def home(): 
    return "✅ BIST Trade Bot Aktif", 200

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app_web.run(host='0.0.0.0', port=port, debug=False)

# ====================== AYARLAR ======================
MY_CHAT_ID = 1033571271

# BIST 30 ve BIST 100 Hisselerinin Güncel Listesi (Tekilleştirilmiş)
HISSE_LISTESI = sorted(list(set([
    # BIST 30
    "AKBNK", "ALARK", "ARCLK", "ASELS", "ASTOR", "BIMAS", "BRSAN", "EKGYO", "ENKAI", "EREGL",
    "FROTO", "GARAN", "GUBRF", "HALKB", "HEKTS", "ISCTR", "KCHOL", "KONTR", "KOZAL", "KRDMD",
    "ODAS", "OYAKC", "PETKM", "PGSUS", "SASA", "SISE", "TCELL", "THYAO", "TOASO", "TUPRS",
    "VAKBN", "VESBE", "VESTL", "YKBNK",
    # BIST 100 Ekstra
    "AEFES", "AGROT", "AHGAZ", "AKCNS", "AKFGY", "AKSA", "ALFAS", "ANSGR", "BATAŞ", "BERA",
    "BFREN", "BIENY", "BOBET", "BORAN", "BRYAT", "BUCIM", "CANTE", "CCOLA", "CIMSA", "CWENE",
    "DOAS", "DOHOL", "EUPWR", "ECILC", "EGEEN", "EGENV", "ENJSA", "ERCB", "ECZYT", "GENIL",
    "GESAN", "GIPTA", "GOLTS", "IHAAS", "INVEO", "INVES", "IPEKE", "ISGYO", "ISMEN", "IZMDC",
    "KAYSE", "KCAER", "KMPUR", "KONYA", "KORDS", "KOZAA", "LMKDC", "MAVI", "MGROS", "MIATK",
    "NETAS", "NTHOL", "NTGAZ", "OTKAR", "OYAKC", "PENTA", "QUAGR", "REEDR", "RYSAS", "SAYAS",
    "SDTTR", "SMRTG", "SOKM", "TABGD", "TARKM", "TATEN", "TIRE", "TKFEN", "TMSN", "TSKB",
    "TURSG", "TTKOM", "TTRAK", "TUKAS", "ULKER", "YEOTK", "ZRENG"
])))

# ====================== İNDİKATÖRLER ======================
def calculate_rsi(close, period=14):
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_ema(close, period):
    return close.ewm(span=period, adjust=False).mean()

# ====================== VERİ ANALİZ ======================
def get_stock_data(ticker: str):
    try:
        df = yf.download(f"{ticker}.IS", period="60d", interval="1h",
                        progress=False, auto_adjust=True, timeout=15)
       
        if df.empty or len(df) < 100:
            return None
            
        if isinstance(df.columns, pd.MultiIndex):
            df = df.droplevel(0, axis=1)
            
        close = df['Close']
        volume = df['Volume']
        
        current_price = round(float(close.iloc[-1]), 2)
        rsi = calculate_rsi(close)
        ema9 = calculate_ema(close, 9)
        ema21 = calculate_ema(close, 21)
        ema50 = calculate_ema(close, 50)
        
        current_rsi = round(float(rsi.iloc[-1]), 1)
        avg_vol = volume.rolling(20).mean().iloc[-1]
        volume_ratio = round(float(volume.iloc[-1] / avg_vol), 2) if avg_vol > 0 else 0

        # Orta Seviye Koşullar
        if (30 <= current_rsi <= 62 and 
            current_price > ema21.iloc[-1] and 
            ema21.iloc[-1] > ema50.iloc[-1] and 
            volume_ratio >= 1.25):

            # ATR
            high_low = df['High'] - df['Low']
            high_close = np.abs(df['High'] - close.shift())
            low_close = np.abs(df['Low'] - close.shift())
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            atr = tr.rolling(14).mean().iloc[-1]

            stop_loss = round(current_price - (atr * 1.75), 2)
            risk = current_price - stop_loss
            target = round(current_price + (risk * 2.5), 2)
            kar = round(((target - current_price) / current_price) * 100, 1)

            if volume_ratio > 2.0:
                pattern = "🔥 Güçlü"
            elif volume_ratio > 1.6:
                pattern = "✅ İyi"
            else:
                pattern = "📈 Orta"

            return {
                "kod": ticker,
                "fiyat": current_price,
                "stop": stop_loss,
                "hedef": target,
                "kar": kar,
                "rsi": current_rsi,
                "volume_ratio": volume_ratio,
                "pattern": pattern
            }
        return None
    except Exception as e:
        logging.error(f"{ticker} hatası: {e}")
        return None

# ====================== TARAMA ======================
async def sinyal_tara(update: Update = None, context: ContextTypes.DEFAULT_TYPE = None):
    if update:
        await update.message.reply_text("🔄 BIST 30/100 orta seviye tarama yapılıyor...")
        
    # Genişleyen liste için eşzamanlı iş parçacığı (worker) sayısı 25'e yükseltildi
    with ThreadPoolExecutor(max_workers=25) as executor:
        loop = asyncio.get_event_loop()
        tasks = [loop.run_in_executor(executor, get_stock_data, kod) for kod in HISSE_LISTESI]
        results = await asyncio.gather(*tasks)
    
    signals = [s for s in results if s]
    
    if not signals:
        if update:
            await update.message.reply_text("❌ Bu taramada orta seviyede sinyal bulunamadı.")
        return

    signals.sort(key=lambda x: x.get('volume_ratio', 0), reverse=True)
    
    mesaj = f"📊 **ORTA SEVİYE TRADE TARAMASI** ({len(signals)} adet) - {datetime.now().strftime('%H:%M')}\n\n"
    
    for s in signals[:15]:  # Genişleyen listeden dolayı en iyi 15 sinyal listelenir
        mesaj += (
            f"**#{s['kod']}** {s['pattern']}\n"
            f"💰 Fiyat: `{s['fiyat']}`\n"
            f"🎯 Hedef: `{s['hedef']}` (+%{s['kar']})\n"
            f"🛑 Stop: `{s['stop']}`\n"
            f"📊 RSI: `{s['rsi']}` | Vol: `{s['volume_ratio']}`x\n"
            f"────────────────────\n\n"
        )
    
    await context.bot.send_message(chat_id=MY_CHAT_ID, text=mesaj, parse_mode='Markdown')

# ====================== BAŞLAT ======================
if __name__ == '__main__':
    Thread(target=run_web, daemon=True).start()
    
    TOKEN = "8027732851:AAFTv0qeU0REVmvjaeCaG8ZkOfmK0ENjiJc"
    
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler('analiz', sinyal_tara))
    app.job_queue.run_repeating(sinyal_tara, interval=1800, first=30)
    
    logging.info("✅ Bot başlatıldı - BIST 100 Genişletilmiş Mod")
    print("🤖 Bot çalışıyor... BIST 100 filtresi aktif.")
    
    app.run_polling(drop_pending_updates=True)
