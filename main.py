async def sinyal_tara(update: Update = None, context: ContextTypes.DEFAULT_TYPE = None):
    start_time = datetime.now()
    logging.info("🔄 BIST Orta Seviye Tarama BAŞLADI")
    
    if update:
        await update.message.reply_text("🔄 BIST orta seviye tarama yapılıyor...")

    with ThreadPoolExecutor(max_workers=12) as executor:
        loop = asyncio.get_event_loop()
        tasks = [loop.run_in_executor(executor, get_stock_data, kod) for kod in HISSE_LISTESI]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    # Hata kontrolü
    signals = []
    errors = 0
    for r in results:
        if isinstance(r, Exception):
            errors += 1
        elif isinstance(r, dict):
            signals.append(r)

    duration = (datetime.now() - start_time).seconds

    logging.info(f"✅ Tarama tamamlandı | Sinyal: {len(signals)} | Hata: {errors} | Süre: {duration}s")

    if not signals:
        mesaj = f"❌ Bu taramada orta seviyede sinyal bulunamadı.\n({duration} saniye sürdü)"
        if update:
            await update.message.reply_text(mesaj)
        else:
            await context.bot.send_message(chat_id=MY_CHAT_ID, text=mesaj)
        return

    signals.sort(key=lambda x: x.get('volume_ratio', 0), reverse=True)

    mesaj = f"📊 **ORTA SEVİYE TRADE TARAMASI** ({len(signals)} adet) - {datetime.now().strftime('%H:%M')}\n"
    mesaj += f"Süre: {duration} saniye\n\n"

    for s in signals[:12]:   # 10 yerine 12
        mesaj += (
            f"**#{s['kod']}** {s['pattern']}\n"
            f"💰 Fiyat: `{s['fiyat']}`\n"
            f"🎯 Hedef: `{s['hedef']}` (+%{s['kar']})\n"
            f"🛑 Stop: `{s['stop']}`\n"
            f"📊 RSI: `{s['rsi']}` | Vol: `{s['volume_ratio']}`x\n"
            f"────────────────────\n\n"
        )

    # Mesajı hem update varsa hem de otomatik job için gönder
    if update and update.message:
        await update.message.reply_text(mesaj, parse_mode='Markdown')
    else:
        await context.bot.send_message(chat_id=MY_CHAT_ID, text=mesaj, parse_mode='Markdown')
