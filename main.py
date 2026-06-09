import os
import asyncio
import logging
import time
from datetime import datetime
from threading import Thread
from concurrent.futures import ThreadPoolExecutor

import yfinance as yf
import pandas as pd
import numpy as np

from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler

# ====================== LOG ======================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
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
HISSE_LISTESI = ["THYAO","GARAN","ISCTR","EREGL","BIMAS","ASELS","SASA","TUPRS","FROTO","KCHOL",
                 "TCELL","PETKM","SISE","AKBNK","SAHOL","PGSUS","ARCLK","KOZAL","HEKTS","TOASO",
                 "VESTL","ENKAI","GUBRF","ODAS","VESBE","TKFEN","HALKB","VAKBN","EKGYO","ASTOR",
                 "KONTR","OYAKC","ALARK","SKBNK","YKBNK","BRSAN","KRDMD"]

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
        logging.info(f"📥 {ticker} verisi çekiliyor...")
        
        df = None
        for attempt in range(3):
            try:
                df = yf.download(
                    f"{ticker}.IS",
                    period="60d",
                    interval="1h",
                    progress=False,
                    auto_adjust=True,
                    timeout=25,
                    threads=False
                )
                if not df.empty and len(df) >= 80:
                    logging.info(f"✅ {ticker} - Veri alındı ({len(df)} satır)")
                    break
            except Exception as e:
                logging.warning(f"{ticker} - Deneme {attempt+1} başarısız: {e}")
                time.sleep(1.5)
        
        if df is None or df.empty or len(df) < 80:
            logging.warning(f"❌ {ticker} için yeterli veri yok")
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df = df.droplevel(0, axis=1)

        df.columns = [str(col).replace(' ', '') for col in df.columns]

        if 'Close' not in df.columns:
            return None

        close = df['Close']
        volume = df.get('Volume', pd.Series([0]*len(df)))

        current_price = round(float(close.iloc[-1]), 2)
        rsi = calculate_rsi(close)
        ema21 = calculate_ema(close, 21)
        ema50 = calculate_ema(close, 50)

        current_rsi = round(float(rsi.iloc[-1]), 1)
        avg_vol = volume.rolling(20).mean().iloc[-1]
        volume_ratio = round(float(volume.iloc[-1] / avg_vol), 2) if avg_vol > 0 else 0

        if (25 <= current_rsi <= 68 and
            current_price > ema21.iloc[-1] and
            ema21.iloc[-1] > ema50.iloc[-1] and
            volume_ratio >= 1.10):

            high_low = df['High'] - df['Low']
            high_close = np.abs(df['High'] - close.shift())
            low_close = np.abs(df['Low'] - close.shift())
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            atr = tr.rolling(14).mean().iloc[-1]

            stop_loss = round(current_price - (atr * 1.75), 2)
            risk = current_price - stop_loss
            target = round(current_price + (risk * 2.5), 2)
            kar = round(((target - current_price) / current_price) * 100, 1)

            pattern = "🔥 Güçlü" if volume_ratio > 2.0 else "✅ İyi" if volume_ratio > 1.6 else "📈 Orta"

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
        logging.error(f"{ticker} hatası: {e}", exc_info=True)
        return None

# ====================== TARAMA ======================
async def sinyal_tara(update: Update = None, context: ContextTypes.DEFAULT_TYPE = None):
    start_time = datetime.now()
    logging.info("🔄 Tarama başlatıldı")
    
    if update:
        await update.message.reply_text("🔄 BIST orta seviye tarama yapılıyor...")

    with ThreadPoolExecutor(max_workers=12) as executor:
        loop = asyncio.get_event_loop()
        tasks = [loop.run_in_executor(executor, get_stock_data, kod) for kod in HISSE_LISTESI]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    signals = [s for s in results if isinstance(s, dict)]
    duration = (datetime.now() - start_time).seconds

    logging.info(f"Tarama bitti → {len(signals)} sinyal bulundu ({duration}s)")

    if not signals:
        mesaj = f"❌ Bu taramada sinyal bulunamadı. ({duration}s)"
        if update:
            await update.message.reply_text(mesaj)
        elif context:
            await context.bot.send_message(chat_id=MY_CHAT_ID, text=mesaj)
        return

    signals.sort(key=lambda x: x.get('volume_ratio', 0), reverse=True)

    mesaj = f"📊 **ORTA SEVİYE TARAMA** ({len(signals)} sinyal) - {datetime.now().strftime('%H:%M')}\nSüre: {duration}s\n\n"
    
    for s in signals[:12]:
        mesaj += (
            f"**#{s['kod']}** {s['pattern']}\n"
            f"💰 `{s['fiyat']}` → 🎯 `{s['hedef']}` (+%{s['kar']})\n"
            f"🛑 Stop: `{s['stop']}`\n"
            f"📊 RSI: `{s['rsi']}` | Vol: `{s['volume_ratio']}`x\n"
            f"────────────────────\n\n"
        )

    try:
        if update and update.message:
            await update.message.reply_text(mesaj, parse_mode='Markdown')
        elif context:
            await context.bot.send_message(chat_id=MY_CHAT_ID, text=mesaj, parse_mode='Markdown')
    except Exception as e:
        logging.error(f"Mesaj gönderme hatası: {e}")

# ====================== BAŞLAT ======================
if __name__ == '__main__':
    try:
        # Web server thread
        Thread(target=run_web, daemon=True).start()
        logging.info(f"🌐 Flask web server başlatıldı (PORT: {os.environ.get('PORT', 8080)})")

        TOKEN = "8027732851:AAFTv0qeU0REVmvjaeCaG8ZkOfmK0ENjiJc"
        
        app = ApplicationBuilder().token(TOKEN).build()
        app.add_handler(CommandHandler('analiz', sinyal_tara))
        
        # Otomatik tarama
        app.job_queue.run_repeating(sinyal_tara, interval=1800, first=60)
        
        logging.info("🤖 Bot başarıyla başlatıldı - Render Uyumlu")
        print("✅ Bot çalışıyor...")

        app.run_polling(drop_pending_updates=True)

    except Exception as e:
        logging.error("❌ Bot başlatılırken kritik hata:", exc_info=True)
        print(f"Kritik hata: {e}")
        raise
