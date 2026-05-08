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
gonderilen_hisseler = {}

# BIST Tüm Hisseler (Ana + Yıldız Pazar)
HISSE_LISTESI = [
    "AEFES","AGHOL","AKBNK","AKCNS","AKFGY","AKFYE","AKSA","AKSEN","ALARK","ALBRK","ALFAS","ALTNY",
    "ANSGR","ARCLK","ASELS","ASTOR","BALSU","BERA","BIMAS","BIOEN","BOBET","BRSAN","BRYAT","BSOKE",
    "BTCIM","CANTE","CCOLA","CIMSA","CWENE","DOAS","DOHOL","ECILC","ECZYT","EGEEN","EKGYO","ENJSA",
    "ENKAI","EREGL","EUPWR","FENER","FROTO","GARAN","GEDIK","GENIL","GESAN","GIPTA","GUBRF","GWIND",
    "HALKB","HEKTS","HRKET","ICBCT","IMASM","IPEKE","ISCTR","ISGYO","ISMEN","IZMDC","KARKM","KAYSE",
    "KCHOL","KLSER","KOLSN","KONTR","KONYA","KORDS","KOZAA","KOZAL","KRDMD","KTLEV","LMKDC","MAVI",
    "MHRGY","MOGAN","ODAS","OTKAR","OYAKC","PASEU","PEKGY","PETKM","PGSUS","PTTGY","QUAGR","RALYH",
    "REEDR","SAHOL","SASA","SAYAS","SDTTR","SISE","SKBNK","SMRTG","SOKM","TABGD","TCELL","THYAO",
    "TKFEN","TOASO","TSKB","TUKAS","TUPRS","TURSG","ULKER","VAKBN","VESBE","VESTL","YEOTK","YKBNK",
    "YYLGD","ZOREN","ADESE","AFYON","AGYO","AKSGY","ALGYO","ALKA","ALKAR","ALMAD","ANHYT","APX",
    "ARTGR","ASUZU","ATAGY","ATEKS","AYEN","AYGAZ","BAGFS","BAYRK","BEGYO","BIZIM","BJKAS","BNTAS",
    "BOLUC","BRMEN","BRSAN","BURCE","BURVA","CELHA","CEMAS","CEMTS","CEO","CUS","DARDL","DENCM",
    "DERIM","DESA","DGATE","DGGYO","DGNMO","DIRIT","DITAS","DMSAS","DURDO","EDIP","EGEPO","EGPRO",
    "EGSER","EMKEL","EMNIS","ENKAI","ERBOS","ERCB","EREGL","ERSU","ESCOM","ESEN","ETI","EUKYO",
    "EUYO","FNSYO","FORMT","FROTO","FZLGY","GARAN","GENTS","GESAN","GLYHO","GSDHO","GUBRF","GUNER",
    "GWIND","HATEK","HAYAT","HEKTS","HLGYO","HURGZ","HZNDR","ICBCT","IDGYO","IEYHO","IHEVA","IHLAS",
    "IHLGM","IHGZT","INGYO","INTEM","ISBTR","ISCTR","ISGYO","ISMEN","IZENR","IZMDC","JANTS","KAPLM",
    "KARTN","KATMR","KENT","KERVT","KIMSA","KRDMA","KRDMB","KRDMD","KRGYO","KRONT","KRSAN","KUTPO",
    "LKMNH","LOGO","MAALT","MAVI","MEGAP","MGROS","MIPAZ","MNMAN","MNDTR","MPARK","MRDIN","MRSHL",
    "MTRKS","MUTLU","NATHK","NETAS","NIBAS","NIGDE","NKGYO","NTEK","NTTUR","NUGYO","ODAS","OFSYM",
    "ONCSM","ORMA","OSMEN","OYA","OZKGY","OZRDN","PAGYO","PARKM","PEGYO","PEKGY","PETKM","PINSU",
    "PKART","PKENT","PNSUT","POLHO","PRKAB","PRKCG","PRKIN","PSDTC","PTOFS","QNBFB","QNBFL","RHEAG",
    "RHGYO","RYSAS","SAFKR","SANEL","SANFM","SANKO","SAY","SEKFK","SELEC","SENTE","SERSN","SKBNK",
    "SKTAS","SMART","SNGYO","SNKRN","SOKM","SONME","SRVGY","STARK","STN","SUWEN","TAVHL","TBORG",
    "TCELL","TEZOL","THYAO","TIRE","TKFEN","TM","TMSN","TOASO","TRCAS","TRKCM","TSKB","TTKOM",
    "TTRAK","TUKAS","TUPRS","TURGG","TURSG","ULAS","ULKER","ULUSE","UNYEC","USAK","UTPYA","VAKBN",
    "VAKFN","VAKKO","VERUS","VESBE","VESTL","VKING","YAPRK","YATAS","YAYLA","YKGYO","YKBNK","YUNSA",
    "YYLGD","ZOREN"
]

def get_stock_data(ticker):
    try:
        symbol = f"{ticker}.IS"
        df = yf.download(symbol, period="8d", interval="30m", 
                        progress=False, auto_adjust=True, timeout=10)
        
        if df.empty or len(df) < 35:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df = df.droplevel(0, axis=1)

        close = df['Close']
        high = df['High']
        low = df['Low']

        # RSI
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = -delta.where(delta < 0, 0).rolling(14).mean()
        df['RSI'] = 100 - (100 / (1 + gain/loss))

        # MACD
        exp1 = close.ewm(span=12, adjust=False).mean()
        exp2 = close.ewm(span=26, adjust=False).mean()
        df['MACD'] = exp1 - exp2
        df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()

        # ATR
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]

        return {
            "kod": ticker,
            "fiyat": round(float(close.iloc[-1]), 2),
            "rsi": round(float(df['RSI'].iloc[-1]), 1),
            "macd_guc": df['MACD'].iloc[-1] > df['Signal'].iloc[-1],
            "atr": round(atr, 2)
        }
    except:
        return None

async def sinyal_tara(context: ContextTypes.DEFAULT_TYPE):
    global gonderilen_hisseler
    await context.bot.send_message(chat_id=MY_CHAT_ID, text=f"📡 **Tüm BIST Hisseleri** taranıyor...\nToplam: {len(HISSE_LISTESI)} hisse")

    with ThreadPoolExecutor(max_workers=12) as executor:
        loop = asyncio.get_event_loop()
        tasks = [loop.run_in_executor(executor, get_stock_data, kod) for kod in HISSE_LISTESI]
        results = await asyncio.gather(*tasks)

    bulunan = 0
    for s in results:
        if not s: 
            continue

        rsi = s['rsi']
        if (rsi <= 58 and s['macd_guc']) or (rsi <= 48):
            bulunan += 1

            giris = s['fiyat']
            hedef = round(giris + (s['atr'] * 2.8), 2)
            stop = round(giris - (s['atr'] * 1.6), 2)

            mesaj = (
                f"🚀 **#{s['kod']}** - GÜÇLÜ SİNYAL\n\n"
                f"💰 Giriş: **{giris}** TL\n"
                f"🎯 Hedef: **{hedef}** TL\n"
                f"🛑 Stop Loss: **{stop}** TL\n"
                f"📊 RSI: **{rsi}**\n"
            )

            keyboard = [[InlineKeyboardButton("📈 TradingView", url=f"https://www.tradingview.com/symbols/BIST-{s['kod']}/")]]
            
            await context.bot.send_message(chat_id=MY_CHAT_ID, text=mesaj, 
                                         reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            await asyncio.sleep(0.6)

    await context.bot.send_message(chat_id=MY_CHAT_ID, 
                                 text=f"✅ **Tarama Tamamlandı**\n\nBulunan güçlü sinyal: **{bulunan}**")

async def manuel_analiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Tüm BIST hisseleri (Ana + Yıldız) taranıyor...")
    await sinyal_tara(context)

# --- BAŞLAT ---
if __name__ == '__main__':
    Thread(target=run_web).start()
    
    TOKEN = os.environ.get("TELEGRAM_TOKEN", "7984025004:AAGD1lLv5RGOIAiJ9wbQfaxSS7r6BGLteoA")
    app = ApplicationBuilder().token(TOKEN).build()

    app.job_queue.run_repeating(sinyal_tara, interval=1800, first=10)  # 30 dakikada bir
    app.add_handler(CommandHandler('analiz', manuel_analiz))

    logging.info("Bot başlatıldı - Tüm BIST taraması aktif")
    app.run_polling()
