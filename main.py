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

# Render üzerinde grafik hatasını önlemek için arka plan modu
matplotlib.use('Agg')

# Loglama ayarları
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- 1. RENDER UYKU ENGELLEYİCİ (FLASK) ---
app_web = Flask('')
@app_web.route('/')
def home(): return "Bot Aktif!", 200

def run_web(): 
    port = int(os.environ.get("PORT", 8080))
    app_web.run(host='0.0.0.0', port=port)

# --- 2. AYARLAR ---
MY_CHAT_ID = 1033571271
gonderilen_hisseler = {}

# BIST 30 ve BIST 100 Hisseleri
HISSE_LISTESI = [
    "AEFES", "AGHOL", "AKBNK", "AKCNS", "AKFGY", "AKFYE", "AKSA", "AKSEN", "ALARK", "ALBRK",
    "ALFAS", "ALTNY", "ANSGR", "ARCLK", "ASELS", "ASTOR", "BALSU", "BERA", "BIMAS", "BIOEN",
    "BOBET", "BRSAN", "BRYAT", "BSOKE", "BTCIM", "CANTE", "CCOLA", "CIMSA", "CWENE", "DOAS",
    "DOHOL", "ECILC", "ECZYT", "EGEEN", "EKGYO", "ENJSA", "ENKAI", "EREGL", "EUPWR", "FENER",
    "FROTO", "GARAN", "GEDIK", "GENIL", "GESAN", "GIPTA", "GUBRF", "GWIND", "HALKB", "HEKTS",
    "HRKET", "ICBCT", "IMASM", "IPEKE", "ISCTR", "ISGYO", "ISMEN", "IZMDC", "KARKM", "KAYSE",
    "KCHOL", "KLSER", "KOLSN", "KONTR", "KONYA", "KORDS", "KOZAA", "KOZAL", "KRDMD", "KTLEV",
    "LMKDC", "MAVI", "MHRGY", "MOGAN", "ODAS", "OTKAR", "OYAKC", "PASEU", "PEKGY", "PETKM",
    "PGSUS", "PTTGY", "QUAGR", "RALYH", "REEDR", "SAHOL", "SASA", "SAYAS", "SDTTR", "SISE",
    "SKBNK", "SMRTG", "SOKM", "TABGD", "TCELL", "THYAO", "TKFEN", "TOASO", "TSKB", "TUKAS",
    "TUPRS", "TURSG", "ULKER", "VAKBN", "VESBE", "VESTL", "YEOTK", "YKBNK", "YYLGD", "ZOREN"
]

# --- 3. TEKNİK VERİ MOTORU ---
def get_stock_data(ticker):
    try:
        symbol = f"{ticker}.IS"
        # 15 dakikalık veri çekimi (BIST için en kararlı 5 günlük period)
        df = yf.download(symbol, period="5d", interval="15m", progress=False, ignore_tz=True)
        if df is None or df.empty or len(df) < 35: return None
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
    except: return None

# --- 4. ANA TARAMA FONKSİYONU ---
async def sinyal_tara(context: ContextTypes.DEFAULT_TYPE):
    global gonderilen_hisseler
    tr_tz = pytz.timezone('Europe/Istanbul')
    simdi = datetime.now(tr_tz)
    su_an_ts, su_an_str = simdi.timestamp(), simdi.strftime("%H:%M")
    
    # Borsa Saat Kontrolü (Hafta içi 10:15 - 18:05)
    if simdi.weekday() > 4 or not ("10:15" <= su_an_str <= "18:05"):
        logging.info(f"Borsa kapalı ({su_an_str}). Tarama yapılmadı.")
        return

    # 1 saatlik bellek temizliği
    gonderilen_hisseler = {k: v for k, v in gonderilen_hisseler.items() if su_an_ts - v < 3600}
    logging.info(f"--- BIST Tarama Başlatıldı ({su_an_str}) ---")

    # Paralel Veri Çekme
    with ThreadPoolExecutor(max_workers=10) as executor:
        loop = asyncio.get_event_loop()
        tasks = [loop.run_in_executor(executor, get_stock_data, kod) for kod in HISSE_LISTESI if kod not in gonderilen_hisseler]
        results = await asyncio.gather(*tasks)

    bulunan_sinyal = 0
    for s in results:
        if not s: continue
        
        # STRATEJİ: RSI 30 DİPTEN DÖNÜŞ VEYA RSI 35-45 ARASI GÜÇLENME
          if (s['rsi_prev'] < 30 and s['rsi'] >= 30) and s['macd'] > s['macd_sig']:
            gonderilen_hisseler[s['kod']] = su_an_ts
            bulunan_sinyal += 1
            gonderilen_hisseler[s['kod']] = su_an_ts
            bulunan_sinyal += 1
            
            df_plot = s['df'].tail(50)
            atr = (df_plot['High'] - df_plot['Low']).rolling(14).mean().iloc[-1]
            fiyat = s['fiyat']

            buf = io.BytesIO()
            mpf.plot(df_plot, type='candle', style='charles', savefig=buf)
            buf.seek(0)

            keyboard = [[InlineKeyboardButton("📈 TradingView", url=f"https://tradingview.com:{s['kod']}")]]

            mesaj = (
                f"🚀 **#{s['kod']} - DİPTEN DÖNÜŞ**\n\n"
                f"💰 **Fiyat:** {fiyat:,.2f} TL\n"
                f"📊 **RSI:** {s['rsi_prev']:.1f} ➔ {s['rsi']:.1f} 🔥\n"
                f"📈 **MACD:** GÜÇLÜ 🟢\n\n"
                f"🎯 **Hedef:** {fiyat + (atr*2.5):,.2f} TL\n"
                f"🛑 **Stop:** {fiyat - (atr*1.5):,.2f} TL"
            )
            
            await context.bot.send_photo(chat_id=MY_CHAT_ID, photo=buf, caption=mesaj, 
                                        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            await asyncio.sleep(0.3)

    logging.info(f"--- Tarama Bitti. Bulunan: {bulunan_sinyal} ---")

async def manuel_analiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global gonderilen_hisseler
    await update.message.reply_text("⚡ Jet motoru çalıştırıldı, tüm BIST taranıyor...")
    gonderilen_hisseler.clear()
    await sinyal_tara(context)

# --- 5. BAŞLATICI ---
if __name__ == '__main__':
    Thread(target=run_web).start()
    TOKEN = os.environ.get("TELEGRAM_TOKEN", "7984025004:AAGD1lLv5RGOIAiJ9wbQfaxSS7r6BGLteoA")
    app = ApplicationBuilder().token(TOKEN).build()
    
    if app.job_queue:
        app.job_queue.run_repeating(sinyal_tara, interval=300, first=10) # 5 dk bir
    
    app.add_handler(CommandHandler('analiz', manuel_analiz))
    app.run_polling()
