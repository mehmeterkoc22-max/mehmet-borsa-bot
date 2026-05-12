import os
import asyncio
import logging
import sqlite3
from datetime import datetime, date
from threading import Thread
from concurrent.futures import ThreadPoolExecutor
import yfinance as yf
import pandas as pd
import pandas_ta as ta
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler

# ====================== LOGGING ======================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

# ====================== FLASK ======================
app_web = Flask('')
@app_web.route('/')
def home(): return "Bot Aktif", 200
@app_web.route('/ping')
def ping(): return "PONG", 200

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app_web.run(host='0.0.0.0', port=port, debug=False)

# ====================== VERİTABANI ======================
def init_db():
    conn = sqlite3.connect('signals.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            date TEXT,
            ticker TEXT,
            price REAL,
            stop REAL,
            target REAL,
            kar REAL,
            rsi REAL,
            patterns TEXT,
            pivot_s1 REAL
        )
    ''')
    conn.commit()
    conn.close()

def save_signal(signal):
    try:
        conn = sqlite3.connect('signals.db')
        cursor = conn.cursor()
        
        today = date.today().isoformat()
        
        # Aynı gün aynı hisse için tekrar kaydetme (spam önleme)
        cursor.execute('''
            SELECT COUNT(*) FROM signals 
            WHERE date = ? AND ticker = ?
        ''', (today, signal['kod']))
        
        if cursor.fetchone()[0] > 0:
            logging.info(f"{signal['kod']} bugün zaten kaydedilmiş.")
            conn.close()
            return False
        
        cursor.execute('''
            INSERT INTO signals 
            (timestamp, date, ticker, price, stop, target, kar, rsi, patterns, pivot_s1)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            today,
            signal['kod'],
            signal['fiyat'],
            signal['stop'],
            signal['hedef'],
            signal['kar'],
            signal['rsi'],
            signal.get('patterns', ''),
            signal.get('pivot_s1')
        ))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logging.error(f"DB kaydetme hatası: {e}")
        return False

# ====================== AYARLAR ======================
MY_CHAT_ID = 1033571271

HISSE_LISTESI = ["THYAO","GARAN","ISCTR","EREGL","BIMAS","ASELS","SASA","TUPRS","FROTO","KCHOL",
                 "TCELL","PETKM","SISE","AKBNK","SAHOL","YKBNK","PGSUS","ARCLK","EKGYO","KOZAL",
                 "ASTOR","KONTR","HEKTS","OYAKC","TOASO","DOAS","GUBRF","VESTL","ENKAI","SOKM",
                 "BRSAN","CIMSA","ALARK","ODAS","VESBE","TKFEN","HALKB","VAKBN","SKBNK","ISMEN",
                 "GWIND","EUPWR","CWENE","YEOTK","SMRTG","REEDR","SDTTR","MOGAN","ALFAS","ARDYZ",
                 "AGROT","BEYAZ","ALVES","ADEL","GESAN","MAVI","LOGO","MPARK","SAYAS","TABGD",
                 "ULKER","ZOREN","BIOEN","BTCIM","CANTE","CCOLA","ECILC","ECZYT","ENJSA","FENER"]

# ====================== PARAMETRELER ======================
RSI_PERIOD = 14
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
ATR_PERIOD = 14
VOLUME_MULTIPLIER = 1.45
BB_PERIOD = 20
BB_STD = 2

# ====================== MUM FORMASYONLARI ve PIVOT (Önceki kodla aynı) ======================
def detect_bullish_patterns(df):
    try:
        o = df['Open']
        c = df['Close']
        h = df['High']
        l = df['Low']
        
        body = c - o
        
        hammer = ((o.where(body > 0, c) - l) > 2 * abs(body)) & ((h - c.where(body > 0, o)) < 0.4 * abs(body))
        engulfing = (c.shift(1) < o.shift(1)) & (c > o) & (c > o.shift(1)) & (o < c.shift(1))
        piercing = (c.shift(1) < o.shift(1)) & (c > o) & (c > (o.shift(1) + c.shift(1))/2) & (o < c.shift(1))
        harami = (c.shift(1) < o.shift(1)) & (c > o) & (c < o.shift(1)) & (o > c.shift(1))
        morning_star = ((c.shift(2) < o.shift(2)) & (abs(body.shift(1)) < 0.3 * abs(c.shift(2)-o.shift(2))) & (c > o) & (c > (o.shift(2) + c.shift(2))/2))
        three_soldiers = (body > 0) & (body.shift(1) > 0) & (body.shift(2) > 0) & (c > c.shift(1)) & (c.shift(1) > c.shift(2))

        patterns = []
        if hammer.iloc[-1]: patterns.append("Hammer")
        if engulfing.iloc[-1]: patterns.append("Engulfing")
        if piercing.iloc[-1]: patterns.append("Piercing")
        if harami.iloc[-1]: patterns.append("Harami")
        if morning_star.iloc[-1]: patterns.append("MorningStar")
        if three_soldiers.iloc[-1]: patterns.append("ThreeSoldiers")
        
        return ", ".join(patterns) if patterns else None
    except:
        return None

def calculate_pivot_points(df):
    try:
        h = df['High'].iloc[-1]
        l = df['Low'].iloc[-1]
        c = df['Close'].iloc[-1]
        pivot = (h + l + c) / 3
        s1 = 2 * pivot - h
        return {"s1": round(s1, 2), "near_support": c <= s1 * 1.015}
    except:
        return None

# ====================== VERİ ÇEKME ======================
def get_stock_data(ticker: str):
    # ... (Önceki kodla tamamen aynı - yer kaplamasın diye kısalttım)
    # Mum, Pivot, BB, RSI, MACD, EMA, Hacim kontrolleri aynı kalıyor.
    # Sadece return dict'ine patterns ve pivot_s1 ekliyoruz.
    try:
        df = yf.download(f"{ticker}.IS", period="45d", interval="1h", progress=False, auto_adjust=True, timeout=15)
        if df.empty or len(df) < 180:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        close = df['Close']
        current_price = round(float(close.iloc[-1]), 2)

        ema_50 = close.ewm(span=50, adjust=False).mean().iloc[-1]
        ema_200 = close.ewm(span=200, adjust=False).mean().iloc[-1]

        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(RSI_PERIOD).mean()
        loss = -delta.where(delta < 0, 0).rolling(RSI_PERIOD).mean()
        rsi = 100 - (100 / (1 + gain / loss))
        current_rsi = round(float(rsi.iloc[-1]), 1)

        macd = ta.macd(close, fast=MACD_FAST, slow=MACD_SLOW, signal=MACD_SIGNAL)
        macd_line = macd[f'MACD_{MACD_FAST}_{MACD_SLOW}_{MACD_SIGNAL}']
        signal_line = macd[f'MACDs_{MACD_FAST}_{MACD_SLOW}_{MACD_SIGNAL}']
        macd_bullish = macd_line.iloc[-1] > signal_line.iloc[-1] and macd_line.iloc[-1] > 0

        bb = ta.bbands(close, length=BB_PERIOD, std=BB_STD)
        price_near_lower = current_price <= (bb[f'BBL_{BB_PERIOD}_{BB_STD}.0'].iloc[-1] * 1.018)

        atr = ta.atr(df['High'], df['Low'], close, length=ATR_PERIOD).iloc[-1]
        volume_power = df['Volume'].iloc[-1] > (df['Volume'].rolling(20).mean().iloc[-1] * VOLUME_MULTIPLIER)

        patterns = detect_bullish_patterns(df)
        pivot_data = calculate_pivot_points(df)

        if (current_price > ema_50 and ema_50 > ema_200 and
            32 < current_rsi < 48 and macd_bullish and volume_power and
            (price_near_lower or (pivot_data and pivot_data["near_support"])) and patterns):

            stop_loss = round(current_price - (atr * 1.9), 2)
            risk = max(current_price - stop_loss, 0.05)
            target = round(current_price + (risk * 3.0), 2)
            kar_orani = round(((target - current_price) / current_price) * 100, 1)

            return {
                "kod": ticker,
                "fiyat": current_price,
                "stop": stop_loss,
                "hedef": target,
                "kar": kar_orani,
                "rsi": current_rsi,
                "patterns": patterns,
                "pivot_s1": pivot_data["s1"] if pivot_data else None
            }
        return None
    except Exception as e:
        logging.error(f"{ticker} hatası: {e}")
        return None

# ====================== TARAMA ======================
async def sinyal_tara(context: ContextTypes.DEFAULT_TYPE, update=None):
    try:
        start_time = datetime.now()
        if update:
            await update.message.reply_text("🔄 Ultra tarama + DB kaydı başladı...")

        logging.info("=== Yeni Tarama Başladı ===")

        with ThreadPoolExecutor(max_workers=15) as executor:
            loop = asyncio.get_event_loop()
            tasks = [loop.run_in_executor(executor, get_stock_data, kod) for kod in HISSE_LISTESI]
            results = await asyncio.gather(*tasks)

        signals = [s for s in results if s]

        saved_count = 0
        for sig in signals:
            if save_signal(sig):
                saved_count += 1

        if not signals:
            logging.info("Bu taramada sinyal bulunamadı.")
            await context.bot.send_message(MY_CHAT_ID, "🔍 Bu taramada güçlü sinyal bulunamadı.")
            return

        # Telegram Mesajı
        mesaj = f"🚀 **ULTRA KALİTE SİNYALLER** ({len(signals)} adet) - {datetime.now().strftime('%d.%m %H:%M')}\n"
        mesaj += f"📊 {saved_count} yeni kayıt DB'ye eklendi.\n\n"

        for s in signals:
            mesaj += (
                f"**#{s['kod']}** 🔥\n"
                f"💰 `{s['fiyat']}` TL\n"
                f"🎯 Hedef: `{s['hedef']}` (+%{s['kar']})\n"
                f"🛑 Stop: `{s['stop']}`\n"
                f"📊 RSI: `{s['rsi']}` | Pattern: {s['patterns']}\n"
                f"📍 Pivot S1: `{s.get('pivot_s1')}`\n"
                f"────────────────────────\n\n"
            )

        await context.bot.send_message(chat_id=MY_CHAT_ID, text=mesaj, parse_mode='Markdown')
        
        duration = (datetime.now() - start_time).seconds
        logging.info(f"Tarama tamamlandı. {len(signals)} sinyal bulundu, {saved_count} kayıt eklendi. Süre: {duration}sn")

    except Exception as e:
        logging.error(f"Genel tarama hatası: {e}")

# ====================== BAŞLAT ======================
if __name__ == '__main__':
    init_db()  # Veritabanı oluştur
    
    Thread(target=run_web, daemon=True).start()
    
    TOKEN = "8027732851:AAFTv0qeU0REVmvjaeCaG8ZkOfmK0ENjiJc"
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler('analiz', lambda u, c: asyncio.create_task(sinyal_tara(c, u))))
    
    app.job_queue.run_repeating(lambda c: asyncio.create_task(sinyal_tara(c)), interval=1800, first=60)

    logging.info("🚀 Ultra Gelişmiş BİST Bot + SQLite DB Aktif!")
    app.run_polling()
