import os
import asyncio
import logging
import yfinance as yf
import pandas as pd
import numpy as np
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
        
        fiyat = round(float(close.iloc[-1]), 2)

        # 1. EMA 200 (Ana Trend)
        ema_200 = close.ewm(span=200, adjust=False).mean().iloc[-1]
        
        # 2. RSI (14)
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-9))))

        # 3. ATR Hesaplama (Stop Loss için oynaklık ölçümü)
        tr = pd.concat([high - low, abs(high - close.shift()), abs(low - close.shift())], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]

        # 4. Supertrend
        st_lower = ((high + low) / 2) - (3 * tr.rolling(7).mean())
        is_st_up = fiyat > st_lower.iloc[-1]

        # 5. SMC - BoS
        recent_high = high.rolling(20).max().iloc[-2]
        is_bos_up = fiyat > recent_high

        # --- DİNAMİK STRATEJİ HESAPLAMA ---
        # Stop-Loss: ATR'nin 1.5 katı kadar aşağısı
        stop_loss = round(fiyat - (atr * 1.5), 2)
        # Hedef: Riskin 2 katı (Örn: 1 TL risk edip 2 TL kazanmak)
        risk_miktari = fiyat - stop_loss
        hedef_fiyat = round(fiyat + (risk_miktari * 2), 2)
        potansiyel_kar = round(((hedef_fiyat - fiyat) / fiyat) * 100, 1)

        return {
            "kod": ticker,
            "fiyat": fiyat,
            "rsi": round(float(rsi.iloc[-1]), 1),
            "ema_200": round(float(ema_200), 2),
            "st_trend": "🟢 BOĞA" if is_st_up else "🔴 AYI",
            "bos": is_bos_up,
            "stop": stop_loss,
            "hedef": hedef_fiyat,
            "kar_oran": potansiyel_kar
        }
    except Exception as e:
        return None

async def sinyal_tara(context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=MY_CHAT_ID, text="📡 Strateji bazlı tarama başladı...")
    
    with ThreadPoolExecutor(max_workers=30) as executor:
        loop = asyncio.get_event_loop()
        tasks = [loop.run_in_executor(executor, get_stock_data, kod) for kod in HISSE_LISTESI]
        results = await asyncio.gather(*tasks)

    valid = [s for s in results if s]
    mesaj = "📊 **GÜNCEL AL-SAT-STOP SİNYALLERİ**\n\n"
    bulundu = False

    for s in valid:
        # FİLTRE: Yükseliş trendinde olan ve Boğa piyasası onaylı hisseler
        if s['fiyat'] > s['ema_200'] and s['st_trend'] == "🟢 BOĞA":
            bulundu = True
            mesaj += (
                f"💎 **#{s['kod']}**\n"
                f"✅ **Giriş (Al):** `{s['fiyat']}`\n"
                f"🎯 **Hedef (Sat):** `{s['hedef']}` (+%{s['kar_oran']})\n"
                f"🛑 **Stop-Loss:** `{s['stop']}`\n"
                f"📈 Durum: {s['st_trend']} | RSI: {s['rsi']}\n"
                f"{'🔥 BoS KIRILIMI VAR!' if s['bos'] else '—'}\n\n"
            )
            
            if len(mesaj) > 3500:
                await context.bot.send_message(chat_id=MY_CHAT_ID, text=mesaj, parse_mode='Markdown')
                mesaj = ""

    if not bulundu:
        mesaj = "⚠️ Şu an güvenli alım bölgesinde (EMA 200 üstü) hisse bulunamadı."
    
    await context.bot.send_message(chat_id=MY_CHAT_ID, text=mesaj, parse_mode='Markdown')

async def manuel_analiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await sinyal_tara(context)

if __name__ == '__main__':
    Thread(target=run_web).start()
    TOKEN = "8027732851:AAFTv0qeU0REVmvjaeCaG8ZkOfmK0ENjiJc"
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler('analiz', manuel_analiz))
    app.job_queue.run_repeating(sinyal_tara, interval=1800, first=10)
    app.run_polling()
