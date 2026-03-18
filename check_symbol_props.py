import MetaTrader5 as mt5

def check_symbol(symbol="XAUUSD"):
    if not mt5.initialize():
        print("Initialize failed")
        return

    # Try to find symbol by partial match if not found directly
    res = mt5.symbol_info(symbol)
    if res is None:
        print(f"Symbol '{symbol}' not found directly. Searching...")
        symbols = mt5.symbols_get()
        for s in symbols:
            if "XAU" in s.name or "GOLD" in s.name:
                print(f"Found related symbol: {s.name}")
        mt5.shutdown()
        return

    print(f"--- SYMBOL INFO: {res.name} ---")
    print(f"Digits: {res.digits}")
    print(f"Tick size: {res.trade_tick_size}")
    print(f"Stop level: {res.trade_stops_level}")
    print(f"Filling mode: {res.filling_mode}")
    print(f"Execution mode: {res.trade_exemode}")
    
    # Check if SL/TP are allowed on market orders
    # SYMBOL_TRADE_EXEMODE_MARKET = 2 (Market-execution)
    # Some market execution brokers do NOT allow SL/TP in the initial order
    if res.trade_exemode == mt5.SYMBOL_TRADE_EXECUTION_MARKET:
        print("Execution: MARKET (Likely requires Two-Step for SL/TP)")
    elif res.trade_exemode == mt5.SYMBOL_TRADE_EXECUTION_INSTANT:
        print("Execution: INSTANT")
    else:
        print(f"Execution: {res.trade_exemode}")

    mt5.shutdown()

if __name__ == "__main__":
    check_symbol()
