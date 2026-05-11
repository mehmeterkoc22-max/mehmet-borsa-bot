import time
import random

# ====================== VERİ ÇEKME ======================
def get_stock_data(ticker, retry=2):
    for attempt in range(retry + 1):
        try:
            symbol = f"{ticker}.IS"
            # Period biraz kısaltıldı
            df = yf.download(symbol, period="12d", interval="1h", 
                           progress=False, auto_adjust=True, timeout=10)
            
            if df.empty or len(df) < 50:
                return None
                
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            close = df['Close']
            high = df['High']
            low = df['Low']
            volume = df['Volume']

            fiyat = round(float(close.iloc[-1]), 2)

            # Pivot
            df_daily = df.resample('1D').agg({'High': 'max', 'Low': 'min', 'Close': 'last'}).dropna()
            if len(df_daily) < 2:
                return None

            prev = df_daily.iloc[-2]
            pp = (prev['High'] + prev['Low'] + prev['Close']) / 3
            r1 = 2 * pp - prev['Low']
            s1 = 2 * pp - prev['High']
            r2 = pp + (prev['High'] - prev['Low'])
            s2 = pp - (prev['High'] - prev['Low'])
            r3 = pp + 2 * (prev['High'] - prev['Low'])
            s3 = pp - 2 * (prev['High'] - prev['Low'])

            # RSI + Hidden Bullish (basit)
            rsi = calculate_rsi(close, 14)
            current_rsi = round(rsi.iloc[-1], 1) if not rsi.empty else None

            hidden_bullish_div = False
            # ... (hidden bullish kodun aynı kalabilir)

            # Diğer hesaplamalar (ATR, stop, hedef vs.)
            ema_200 = close.ewm(span=200, adjust=False).mean().iloc[-1]
            tr = pd.concat([high - low, abs(high - close.shift()), abs(low - close.shift())], axis=1).max(axis=1)
            atr = tr.rolling(14).mean().iloc[-1]

            stop = round(fiyat - (atr * 1.5), 2)
            risk = max(fiyat - stop, 0.01)
            hedef = round(fiyat + (risk * 4), 2)
            kar_potansiyeli = round(((hedef - fiyat) / fiyat) * 100, 1)

            avg_vol = volume.rolling(20).mean().iloc[-1]
            hacim_ok = volume.iloc[-1] > (avg_vol * 1.5)
            st_up = fiyat > (((high + low) / 2) - (3 * tr.rolling(7).mean())).iloc[-1]
            bos = fiyat > high.rolling(20).max().iloc[-2]

            # Rate limit koruması
            time.sleep(random.uniform(0.4, 0.8))   # ← ÖNEMLİ

            return {
                "kod": ticker, "fiyat": fiyat, "stop": stop, "hedef": hedef,
                "kar": kar_potansiyeli, "hacim": hacim_ok, "st_trend": st_up,
                "ema_200": ema_200, "bos": bos,
                "pivot": round(pp, 2), "r1": round(r1, 2), "r2": round(r2, 2), "r3": round(r3, 2),
                "s1": round(s1, 2), "s2": round(s2, 2), "s3": round(s3, 2),
                "pivot_yukari": fiyat > pp,
                "hidden_bullish_div": hidden_bullish_div,
                "rsi": current_rsi
            }

        except Exception as e:
            if "Rate limited" in str(e) or "Too Many Requests" in str(e):
                wait = (attempt + 1) * 8
                logging.warning(f"{ticker} rate limit → {wait} saniye bekleniyor...")
                time.sleep(wait)
            else:
                logging.error(f"{ticker} hata: {e}")
                time.sleep(2)
                
    return None
