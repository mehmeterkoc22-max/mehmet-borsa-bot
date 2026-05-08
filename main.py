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

# Render için arka plan modu
matplotlib.use('Agg')

# Loglama
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- 1. RENDER UYKU ENGELLEYİCİ ---
app_web = Flask('')
@app_web.route('/')
def home(): return "Bot Aktif!", 200

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app_web.run(host='0.0.0.0', port=port)

# --- 2. AYARLAR ---
MY_CHAT_ID = 1033571271
gonderilen_hisseler = {}

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

# --- 3. İYİLEŞTİRİLMİŞ TEKNİK VERİ MOTORU ---
def get_stock_data(ticker):
    try:
        symbol = f"{ticker}.IS"
        df = yf.download(
            symbol, 
            period="6d", 
            interval="15m", 
            progress=False, 
            auto_adjust=True,
            repair=True
        )
        
        if df is None or df.empty or len(df) < 50:
            logging.warning(f"{ticker} → Yetersiz veri ({len(df)} satır)")
            return None

        # Sütun düzeltme
        if isinstance(df.columns, pd.MultiIndex):
            df = df.droplevel(0, axis=1)
        df = df[['Open', 'High', 'Low', 'Close', 'Volume']]

        close = df['Close']
        delta = close.diff()

        gain = delta.where(delta > 0, 0).rolling(window=14).mean()
        loss = -delta.where(delta < 0, 0).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))

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
        logging.error(f"{ticker} → Hata: {e}")
        return None

# --- 4. ANA TARAMA FONKSİYONU ---
async def sinyal_tara(context: ContextTypes.DEFAULT_TYPE):
    global gonderilen_hisseler
    tr_tz = pytz.timezone('Europe/Istanbul')
    simdi = datetime.now(tr_tz)
    su_an_ts = simdi.timestamp()
    su_an_str = simdi.strftime("%H:%M")

    # === TEST İÇİN SAAT KONTROLÜ KAPALI ===
    # if simdi.weekday() > 4 or not ("10:15" <= su_an_str <= "18:05"):
    #     logging.info(f"Borsa kapalı ({su_an_str}). Tarama yapılmadı.")
    #     return

    # 1 saatlik bellek temizliği
    gonderilen_hisseler = {k: v for k, v in gonderilen_hisseler.items() if su_an_ts - v < 3600}

    logging.info(f"--- BIST Tarama Başlatıldı ({su_an_str}) | Gönderilen: {len(gonderilen_hisseler)} ---")

    with ThreadPoolExecutor(max_workers=12) as executor:
        loop = asyncio.get_event_loop()
        tasks = [loop.run_in_executor(executor, get_stock_data, kod) 
                for kod in HISSE_LISTESI if kod not in gonderilen_hisseler]
        results = await asyncio.gather(*tasks)

    bulunan_sinyal = 0
    for s in results:
        if not s: 
            continue

        logging.info(f"{s['kod']:6} | Fiyat: {s['fiyat']:.2f} | RSI: {s['rsi']:.1f} | MACD: {s['macd']:.4f}")

        # === GENİŞLETİLMİŞ SİNYAL KOŞULU (Test için daha duyarlı) ===
        if (s['rsi'] <= 45 and s['rsi'] > s['rsi_prev']) and s['macd'] > s['macd_sig']:
            gonderilen_hisseler[s['kod']] = su_an_ts
            bulunan_sinyal += 1

            df_plot = s['df'].tail(50)
            atr = (df_plot['High'] - df_plot['Low']).rolling(14).mean().iloc[-1]
            fiyat = s['fiyat']

            buf = io.BytesIO()
            mpf.plot(df_plot, type='candle', style='charles', savefig=buf, figsize=(10, 6))
            buf.seek(0)

            keyboard = [[InlineKeyboardButton("📈 TradingView", 
                        url=f"https://www.tradingview.com/symbols/BIST-{s['kod']}/")]]

            mesaj = (
                f"🚀 **#{s['kod']} - DİPTEN DÖNÜŞ**\n\n"
                f"💰 **Fiyat:** {fiyat:,.2f} TL\n"
                f"📊 **RSI:** {s['rsi_prev']:.1f} → {s['rsi']:.1f} 🔥\n"
                f"📈 **MACD:** Güçlü 🟢\n\n"
                f"🎯 **Hedef:** {fiyat + (atr*2.5):,.2f} TL\n"
                f"🛑 **Stop:** {fiyat - (atr*1.5):,.2f} TL"
            )

            await context.bot.send_photo(
                chat_id=MY_CHAT_ID, 
                photo=buf, 
                caption=mesaj,
                reply_markup=InlineKeyboardMarkup(keyboard), 
                parse_mode='Markdown'
            )
            await asyncio.sleep(0.4)

    logging.info(f"--- Tarama Tamamlandı. Bulunan sinyal: {bulunan_sinyal} ---")

# --- 5. MANUEL KOMUT ---
async def manuel_analiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⚡ Tüm BIST hisseleri taranıyor, lütfen bekleyin...")
    gonderilen_hisseler.clear()
    await sinyal_tara(context)

# --- 6. BAŞLATICI ---
if __name__ == '__main__':
    Thread(target=run_web).start()
    
    TOKEN = os.environ.get("TELEGRAM_TOKEN", "7984025004:AAGD1lLv5RGOIAiJ9wbQfaxSS7r6BGLteoA")
    app = ApplicationBuilder().token(TOKEN).build()

    if app.job_queue:
        app.job_queue.run_repeating(sinyal_tara, interval=300, first=10)  # 5 dakikada bir

    app.add_handler(CommandHandler('analiz', manuel_analiz))
    app.run_polling()
