async def sinyal_tara(context: ContextTypes.DEFAULT_TYPE):
    global gonderilen_hisseler
    tr_tz = pytz.timezone('Europe/Istanbul')
    simdi = datetime.now(tr_tz)
    su_an_ts = simdi.timestamp()
    su_an_str = simdi.strftime("%H:%M")
    
    # Otomatik Tarama Saat Kısıtlaması (Hafta içi 10:15 - 18:05)
    if simdi.weekday() > 4 or not ("10:15" <= su_an_str <= "18:05"):
        logging.info(f"Borsa kapalı ({su_an_str}). Otomatik tarama atlandı.")
        return

    # 1 saati dolanları bellekten temizle
    gonderilen_hisseler = {k: v for k, v in gonderilen_hisseler.items() if su_an_ts - v < 3600}

    logging.info(f"--- BIST Tarama Başlatıldı ({su_an_str}) ---")
    
    # Hızlı veri çekme motoru (Multithreading)
    with ThreadPoolExecutor(max_workers=10) as executor:
        loop = asyncio.get_event_loop()
        tasks = [loop.run_in_executor(executor, get_stock_data, kod) for kod in HISSE_LISTESI if kod not in gonderilen_hisseler]
        results = await asyncio.gather(*tasks)

    bulunan_sinyal = 0
    for s in results:
        if not s: continue
        
        # --- ANA STRATEJİ: RSI 30 DİPTEN DÖNÜŞ VE MACD POZİTİF ---
        if s['rsi'] > 30 and s['macd'] > s['macd_sig']:
            gonderilen_hisseler[s['kod']] = su_an_ts
            bulunan_sinyal += 1
            
            df_plot = s['df'].tail(50)
            atr = (df_plot['High'] - df_plot['Low']).rolling(14).mean().iloc[-1]
            fiyat = s['fiyat']

            buf = io.BytesIO()
            mpf.plot(df_plot, type='candle', style='charles', savefig=buf)
            buf.seek(0)

            h_temiz = s['kod'].replace(".IS", "").replace("^", "")
            keyboard = [[InlineKeyboardButton("📈 TradingView", url=f"https://tradingview.com:{h_temiz}")]]

            mesaj = (
                f"🚀 **#{s['kod']} - DİPTEN DÖNÜŞ**\n\n"
                f"💰 **Fiyat:** {fiyat:,.2f} TL\n"
                f"📊 **RSI:** {s['rsi']:.1f} 📈\n"
                f"📈 **MACD:** GÜÇLÜ 🟢\n\n"
                f"🎯 **Hedef:** {fiyat + (atr*2.5):,.2f} TL\n"
                f"🛑 **Stop:** {fiyat - (atr*1.5):,.2f} TL"
            )
            
            await context.bot.send_photo(chat_id=MY_CHAT_ID, photo=buf, caption=mesaj, 
                                        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            await asyncio.sleep(0.3) 

    if bulunan_sinyal == 0:
        logging.info("Kriterlere uyan yeni hisse yok.")
