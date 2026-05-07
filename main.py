import logging
import yfinance as yf
import pandas as pd
import mplfinance as mpf
import os
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler

# 1. Loglama ayarları
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

# 2. AYARLAR
MY_CHAT_ID = 1033571271
HISSE_LISTESI = [
    "XU100.IS", "XU030.IS", "XBANK.IS", "THYAO", "EREGL", "ASELS", "AKBNK", "SISE", 
    "TUPRS", "GARAN", "SASA", "HEKTS", "KCHOL", "ISCTR", "YKBNK", "BIMAS", "SAHOL", 
    "PETKM", "ARCLK", "TOASO", "FROTO", "TCELL", "HALKB", "VAKBN", "EKGYO", "ENKAI", 
    "KONTR", "ASTOR", "SMRTG", "ALARK", "GUBRF", "ODAS", "A1CAP", "BARMA", "ECOGR", 
    "EGPRO", "GEDIK", "GMTAS", "KRDMB", "LRSHO", "MOGAN", "NTGAZ", "OYYAT", "PAGYO", 
    "VKGYO", "MAVI", "BERA", "AGHOL", "ENJSA", "MPARK", "RALYH", "SOKM", "ADEL", 
    "AFYON", "AKENR", "ALKA", "ANELE", "ARZUM", "AVOD", "BAGFS", "BANVT", "BRYAT", 
    "BURCE", "DESPC", "DGATE", "GEREL", "GLRYH", "IEYHO", "KAREL", "KMPUR", "KONYA", 
    "KORDS", "AKMGY", "BYDNR", "IZINV", "PRZMA", "ENDAE", "ERCB", "PLTUR", "YAPRK"
]

def get_stock_data(ticker):
    try:
        symbol = ticker if ticker.endswith(".IS") or ticker.startswith("^") else f"{ticker}.IS"
        df = yf.download(symbol, period="60d", interval="1h", progress=False, ignore_tz=True)
        
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

async def sinyal_tara(context: ContextTypes.DEFAULT_TYPE):
    print("--- Tarama Başlatıldı ---")
    bulunan_sinyal = 0
    
    for kod in HISSE_LISTESI:
        s = get_stock_data(kod)
        if not s: continue

        # KRİTER: RSI 25'i yukarı kesmiş (DİP DÖNÜŞ) VE MACD Pozitif
        if s['rsi_prev'] < 25 and s['rsi'] >= 25 and s['macd'] > s['macd_sig']:
            bulunan_sinyal += 1
            foto_yolu = f"{s['kod'].replace('^','')}.png"
            data_plot = s['df'].tail(50)
            
            apds = [
                mpf.make_addplot(data_plot['RSI'], panel=1, color='purple', ylabel='RSI'),
                mpf.make_addplot(data_plot['MACD'], panel=2, color='blue', ylabel='MACD'),
                mpf.make_addplot(data_plot['Signal'], panel=2, color='orange')
            ]
            
            mpf.plot(data_plot, type='candle', style='charles', addplot=apds, 
                     volume=True, savefig=foto_yolu, title=f"#{s['kod']} DIP DONUS")

            mesaj = (
                f"🚀 **#{s['kod']} - DİPTEN DÖNÜŞ**\n\n"
                f"💰 **Fiyat:** {s['fiyat']:,.2f}\n"
                f"📉 **RSI:** {s['rsi_prev']:.1f} ➔ {s['rsi']:.1f} 🔥\n"
                f"📈 **MACD:** Pozitif Kesişim 🟢\n\n"
                f"🎯 **Hedef:** {s['fiyat']*1.05:,.2f}\n"
                f"🛑 **Stop:** {s['fiyat']*0.97:,.2f}"
            )
            
            await context.bot.send_photo(chat_id=MY_CHAT_ID, photo=open(foto_yolu, 'rb'), caption=mesaj, parse_mode='Markdown')
            if os.path.exists(foto_yolu): os.remove(foto_yolu)
            await asyncio.sleep(0.5)

    if bulunan_sinyal == 0:
        await context.bot.send_message(chat_id=MY_CHAT_ID, text="🔎 Tarama bitti. Şu an kriterlere uyan bir fırsat bulunamadı.")
    
    print("--- Tarama Tamamlandı ---")

async def manuel_analiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔎 Tarama başlatıldı...")
    await sinyal_tara(context)

if __name__ == '__main__':
    TOKEN = '8027732851:AAFTv0qeU0REVmvjaeCaG8ZkOfmK0ENjiJc'
    app = ApplicationBuilder().token(TOKEN).build()
    
    if app.job_queue:
        app.job_queue.run_repeating(sinyal_tara, interval=3600, first=5)
    
    app.add_handler(CommandHandler('analiz', manuel_analiz))
    app.run_polling()

