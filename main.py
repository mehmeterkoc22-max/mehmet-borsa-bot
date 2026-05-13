import os
import asyncio
import logging
import sqlite3
from datetime import datetime, date
from threading import Thread
from concurrent.futures import ThreadPoolExecutor
import yfinance as yf
import pandas as pd
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
def home(): return "Bot Aktif", 200

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
        
        cursor.execute('SELECT COUNT(*) FROM signals WHERE date = ? AND ticker = ?', (today, signal['kod']))
        if cursor.fetchone()[0] > 0:
            conn.close()
            return False
       
        cursor.execute('''
            INSERT INTO signals (timestamp, date, ticker, price, stop, target, kar, rsi, patterns, pivot_s1)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            today, signal['kod'], signal['fiyat'], signal['stop'],
            signal['hedef'], signal['kar'], signal['rsi'],
            signal.get('patterns', ''), signal.get('pivot_s1')
        ))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logging.error(f"DB hatası: {e}")
        return False

# ====================== AYARLAR ======================
MY_CHAT_ID = 1033571271

# ====================== TÜM BIST HİSSELERİ (Ana + Yıldız Pazar) ======================
HISSE_LISTESI = [
    "AEFES","AGHOL","AKBNK","AKCNS","AKFGY","AKFYE","AKSA","AKSEN","ALARK","ALBRK","ALFAS","ALTNY","ANSGR","ARCLK",
    "ASELS","ASTOR","BALSU","BERA","BIMAS","BIOEN","BOBET","BRSAN","BRYAT","BSOKE","BTCIM","CANTE","CCOLA","CIMSA",
    "CWENE","DOAS","DOHOL","ECILC","ECZYT","EGEEN","EKGYO","ENJSA","ENKAI","EREGL","EUPWR","FENER","FROTO","GARAN",
    "GEDIK","GENIL","GESAN","GIPTA","GUBRF","GWIND","HALKB","HEKTS","HRKET","ICBCT","IMASM","IPEKE","ISCTR","ISGYO",
    "ISMEN","IZMDC","KARKM","KAYSE","KCHOL","KLSER","KOLSN","KONTR","KONYA","KORDS","KOZAA","KOZAL","KRDMD","KTLEV",
    "LMKDC","MAVI","MHRGY","MOGAN","ODAS","OTKAR","OYAKC","PASEU","PEKGY","PETKM","PGSUS","PTTGY","QUAGR","RALYH",
    "REEDR","SAHOL","SASA","SAYAS","SDTTR","SISE","SKBNK","SMRTG","SOKM","TABGD","TCELL","THYAO","TKFEN","TOASO",
    "TSKB","TUKAS","TUPRS","TURSG","ULKER","VAKBN","VESBE","VESTL","YEOTK","YKBNK","YYLGD","ZOREN",
    # Yıldız Pazar ve Diğer Hisseler
    "ADESE","AFYON","AGYO","AKSGY","ALGYO","ALKA","ALKAR","ALMAD","ANHYT","APX","ARTGR","ASUZU","ATAGY","ATEKS",
    "AYEN","AYGAZ","BAGFS","BAYRK","BEGYO","BIZIM","BJKAS","BNTAS","BOLUC","BRMEN","BURCE","BURVA","CELHA","CEMAS",
    "CEMTS","CEO","CUS","DARDL","DENCM","DERIM","DESA","DGATE","DGGYO","DGNMO","DIRIT","DITAS","DMSAS","DURDO",
    "EDIP","EGEPO","EGPRO","EGSER","EMKEL","EMNIS","ERBOS","ERCB","ERSU","ESCOM","ESEN","ETI","EUKYO","EUYO",
    "FNSYO","FORMT","FZLGY","GENTS","GLYHO","GSDHO","GUNER","HATEK","HAYAT","HLGYO","HURGZ","HZNDR","IDGYO",
    "IEYHO","IHEVA","IHLAS","IHLGM","IHGZT","INGYO","INTEM","ISBTR","IZENR","JANTS","KAPLM","KARTN","KATMR","KENT",
    "KERVT","KIMSA","KRDMA","KRDMB","KRGYO","KRONT","KRSAN","KUTPO","LKMNH","LOGO","MAALT","MEGAP","MGROS","MIPAZ",
    "MNMAN","MNDTR","MPARK","MRDIN","MRSHL","MTRKS","MUTLU","NATHK","NETAS","NIBAS","NIGDE","NKGYO","NTEK","NTTUR",
    "NUGYO","OFSYM","ONCSM","ORMA","OSMEN","OYA","OZKGY","OZRDN","PAGYO","PARKM","PEGYO","PINSU","PKART","PKENT",
    "PNSUT","POLHO","PRKAB","PRKCG","PRKIN","PSDTC","PTOFS","QNBFB","QNBFL","RHEAG","RHGYO","RYSAS","SAFKR","SANEL",
    "SANFM","SANKO","SAY","SEKFK","SELEC","SENTE","SERSN","SKTAS","SMART","SNGYO","SNKRN","SONME","SRVGY","STARK",
    "STN","SUWEN","TAVHL","TBORG","TEZOL","TIRE","TM","TMSN","TRCAS","TRKCM","TTKOM","TTRAK","TURGG","ULAS","ULUSE",
    "UNYEC","USAK","UTPYA","VAKFN","VAKKO","VERUS","VKING","YAPRK","YATAS","YAYLA","YKGYO","YUNSA"
]

# ====================== FONKSİYONLAR ======================
def get_stock_data(ticker: str):
    try:
        df = yf.download(f"{ticker}.IS", period="40d", interval="1h", progress=False, auto_adjust=True, timeout=12)
        if df.empty or len(df) < 80:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df = df.droplevel(0, axis=1)
            
        close = df['Close']
        current_price = round(float(close.iloc[-1]), 2)

        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = -delta.where(delta < 0, 0).rolling(14).mean()
        rsi = 100 - (100 / (1 + gain/loss))
        current_rsi = round(float(rsi.iloc[-1]), 1)

        ema50 = close.ewm(span=50, adjust=False).mean().iloc[-1]
        ema200 = close.ewm(span=200, adjust=False).mean().iloc[-1]

        exp1 = close.ewm(span=12, adjust=False).mean()
        exp2 = close.ewm(span=26, adjust=False).mean()
        macd_line = exp1 - exp2
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        macd_bullish = macd_line.iloc[-1] > signal_line.iloc[-1] and macd_line.iloc[-1] > 0

        tr = pd.concat([(df['High'] - df['Low']), abs(df['High'] - close.shift()), abs(df['Low'] - close.shift())], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]

        volume_power = df['Volume'].iloc[-1] > (df['Volume'].rolling(20).mean().iloc[-1] * 1.45)

        if (current_price > ema50 and ema50 > ema200 and 32 < current_rsi < 48 and macd_bullish and volume_power):
            stop_loss = round(current_price - (atr * 1.8), 2)
            target = round(current_price + (current_price - stop_loss) * 2.8, 2)
            kar = round(((target - current_price) / current_price) * 100, 1)

            return {
                "kod": ticker,
                "fiyat": current_price,
                "stop": stop_loss,
                "hedef": target,
                "kar": kar,
                "rsi": current_rsi,
                "patterns": "Trend + RSI + Volume"
            }
        return None
    except Exception as e:
        logging.error(f"{ticker} hatası: {e}")
        return None

# ====================== TARAMA ======================
async def sinyal_tara(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"🔄 Tüm BIST (Ana + Yıldız Pazar) taranıyor...\nToplam Hisse: **{len(HISSE_LISTESI)}**")

    with ThreadPoolExecutor(max_workers=12) as executor:
        loop = asyncio.get_event_loop()
        tasks = [loop.run_in_executor(executor, get_stock_data, kod) for kod in HISSE_LISTESI]
        results = await asyncio.gather(*tasks)

    signals = [s for s in results if s]
    
    if not signals:
        await update.message.reply_text("🔍 Bu taramada güçlü sinyal bulunamadı.")
        return

    mesaj = f"🚀 **ULTRA SİNYAL** ({len(signals)} adet) - {datetime.now().strftime('%H:%M')}\n\n"
    
    for s in signals:
        mesaj += (
            f"**#{s['kod']}** 🔥\n"
            f"💰 Fiyat: `{s['fiyat']}` TL\n"
            f"🎯 Hedef: `{s['hedef']}` (+%{s['kar']})\n"
            f"🛑 Stop: `{s['stop']}`\n"
            f"📊 RSI: `{s['rsi']}`\n"
            f"────────────────────\n\n"
        )

    await context.bot.send_message(chat_id=MY_CHAT_ID, text=mesaj, parse_mode='Markdown')

# ====================== BAŞLAT ======================
if __name__ == '__main__':
    init_db()
    Thread(target=run_web, daemon=True).start()
   
    TOKEN = "8027732851:AAFTv0qeU0REVmvjaeCaG8ZkOfmK0ENjiJc"
    app = ApplicationBuilder().token(TOKEN).build()
   
    app.add_handler(CommandHandler('analiz', sinyal_tara))
    app.job_queue.run_repeating(sinyal_tara, interval=1800, first=60)
    
    logging.info(f"✅ Bot başlatıldı! Toplam {len(HISSE_LISTESI)} hisse ile çalışıyor.")
    app.run_polling(drop_pending_updates=True)
