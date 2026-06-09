import os
import io
import time
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
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler

# Render ve bulut sunucularda ekran (GUI) olmadığı için çökmesini önleyen kritik ayar
matplotlib.use('Agg')

# Loglama ayarları
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- 1. RENDER UYKU ENGELLEYİCİ (FLASK) & PING ROTASI ---
app_web = Flask('')

@app_web.route('/')
def home(): 
    return "Bot Aktif!", 200

def run_web(): 
    # Render'ın atadığı dinamik portu yakalar, bulamazsa 8080 kullanır
    port = int(os.environ.get("PORT", 8080))
    app_web.run(host='0.0.0.0', port=port)

# --- 2. AYARLAR ---
MY_CHAT_ID = 1033571271
HISSE_LISTESI = [
    "XU100", "XU030", "XBANK", "THYAO", "EREGL", "ASELS", "AKBNK", "SISE", 
    "TUPRS", "GARAN", "SASA", "HEKTS", "KCHOL", "ISCTR", "YKBNK", "BIMAS", "SAHOL", 
    "PETKM", "ARCLK", "TOASO", "FROTO", "TCELL", "HALKB", "VAKBN", "EKGYO", "ENKAI", 
    "KONTR", "ASTOR", "SMRTG", "ALARK", "GUBRF", "ODAS", "A1CAP", "BARMA", "ECOGR", 
    "EGPRO", "GEDIK", "GMTAS", "KRDMB", "LRSHO", "MOGAN", "NTGAZ", "OYYAT", "PAGYO", 
    "VKGYO", "MAVI", "BERA", "AGHOL", "ENJSA", "MPARK", "RALYH", "SOKM", "ADEL", 
    "AFYON", "AKENR", "ALKA", "ANELE", "ARZUM", "AVOD", "BAGFS", "BANVT", "BRYAT", 
    "BURCE", "DESPC", "DGATE", "GEREL", "GLRYH", "IEYHO", "KAREL", "KMPUR", "KONYA", 
    "KORDS", "AKMGY", "BYDNR", "IZINV", "PRZMA", "ENDAE", "ERCB", "PLTUR", "YAPRK"
]

# --- 3. VERİ MOTORU ---
def get_stock_data(ticker):
    try:
        symbol = ticker if ticker.endswith(".IS") or ticker.startswith("^") else f"{ticker}.IS"
        # 15 dakikalık verilerin boş dönmemesi için period maksimum 5 gün (5d) olmalıdır
        df = yf.download(symbol, period="5d", interval="15m", progress=False, ignore_tz=True)
        
        if df is None or df.empty or len(df) < 35: return None
        # yfinance v1.3.0+ sürümündeki MultiIndex sütun hatasını temizleyen satır
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        close = df['Close']
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        df['RSI'] = 100 - (100 / (1 + (gain / loss)))
        
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
        logging.error(f"{ticker} verisi çekilemedi: {e}")
        return None

# --- 4. ANA TARAMA FONKSİYONU ---
async def sinyal_tara(context: ContextTypes.DEFAULT_TYPE):
    logging.info("--- Tarama Başlatıldı ---")
    bulunan_sinyal = 0
    
    for kod in HISSE_LISTESI:
        s = get_stock_data(kod)
        if not s: continue

        # ORİJİNAL KRİTER: RSI 25'i veya esnetilmiş olarak 30'u yukarı kesmiş (DİP DÖNÜŞ) VE MACD Pozitif
        if s['rsi_prev'] < 30 and s['rsi'] >= 30 and s['macd'] > s['macd_sig']:
            bulunan_sinyal += 1
            data_plot = s['df'].tail(50)
            
            apds = [
                mpf.make_addplot(data_plot['RSI'], panel=1, color='purple', ylabel='RSI'),
                mpf.make_addplot(data_plot['MACD'], panel=2, color='blue', ylabel='MACD'),
                mpf.make_addplot(data_plot['Signal'], panel=2, color='orange')
            ]
            
            # Sunucuda dosya yazma izni (permission) hatasını aşmak için bellekte (buffer) çizim yapıyoruz
            buf = io.BytesIO()
            mpf.plot(data_plot, type='candle', style='charles', addplot=apds, 
                     volume=True, savefig=buf, title=f"#{s['kod']} DIP DONUS")
            buf.seek(0)

            mesaj = (
                f"🚀 **#{s['kod']} - DİPTEN DÖNÜŞ**\n\n"
                f"💰 **Fiyat:** {s['fiyat']:,.2f} TL\n"
                f"📉 **RSI:** {s['rsi_prev']:.1f} ➔ {s['rsi']:.1f} 🔥\n"
                f"📊 **MACD:** {s['macd']:.2f} 🟢\n\n"
                f"🎯 **Hedef:** {s['fiyat']*1.05:,.2f} TL\n"
                f"🛑 **Stop:** {s['fiyat']*0.97:,.2f} TL"
            )
            
            await context.bot.send_photo(chat_id=MY_CHAT_ID, photo=buf, caption=mesaj, parse_mode='Markdown')
            await asyncio.sleep(0.5)

    if bulunan_sinyal == 0:
        await context.bot.send_message(chat_id=MY_CHAT_ID, text="🔎 Tarama bitti. Şu an kriterlere uyan bir fırsat bulunamadı.")
    
    logging.info("--- Tarama Tamamlandı ---")

async def manuel_analiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔎 Tarama başlatıldı...")
    await sinyal_tara(context)

# --- 5. ANA BAŞLATICI ---
if __name__ == '__main__':
    # Flask sunucusunu arka planda başlat
    Thread(target=run_web).start()
    
    # Token'ı gizli ortam değişkeninden (Environment Variable) okuyoruz
    TOKEN = os.environ.get("TELEGRAM_TOKEN", "7984025004:AAGD1lLv5RGOIAiJ9wbQfaxSS7r6BGLteoA")
    app = ApplicationBuilder().token(TOKEN).build()
    
    if app.job_queue:
        # 15 dakikalık (900 saniye) periyotlarla otomatik çalışma ayarı
        app.job_queue.run_repeating(sinyal_tara, interval=900, first=5)
    
    app.add_handler(CommandHandler('analiz', manuel_analiz))
    app.run_polling()
