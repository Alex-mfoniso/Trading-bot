import time
import MetaTrader5 as mt5
import threading
import pandas as pd
from live_engine import LiveDemoEngine
from session_engine import SessionEngine

# --- Configuration ---
SYMBOL = "XAUUSD"
TIMEFRAME = mt5.TIMEFRAME_H1
RISK_PERCENT = 0.01

# --- PUBLIC REPORTING ---
# Paste your Google Apps Script Web App URL here to enable online Excel logs
GOOGLE_SHEET_URL = "https://script.google.com/macros/s/AKfycbxvq6KZHwPozEWr2OHtFj1-W0cLtME3g_KiCyA6u05Ya0KQK56wqrmj_oxR-SsnL-Odug/exec" 

def get_historical_data(symbol, timeframe, num_bars):
    """
    Fetches the last N closed bars from MT5 and formats them into our standard DataFrame.
    Returns None if fetching fails.
    """
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 1, num_bars)
    if rates is None:
        print(f"Failed to copy rates from MT5! Error code: {mt5.last_error()}")
        return None
        
    df = pd.DataFrame(rates)
    df['timestamp'] = pd.to_datetime(df['time'], unit='s')
    df.rename(columns={'tick_volume': 'volume'}, inplace=True)
    df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
    
    return df
    
def get_current_candle(symbol, timeframe):
    """
    Gets the most recently closed candle (index 1).
    Index 0 is the currently forming (open) candle.
    """
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 1, 1)
    if rates is None:
        return None
        
    df = pd.DataFrame(rates)
    df['timestamp'] = pd.to_datetime(df['time'], unit='s')
    df.rename(columns={'tick_volume': 'volume'}, inplace=True)
    return df.iloc[0].to_dict()

def setup_mt5():
    # Initialize without explicit credentials - uses the active MT5 session
    if not mt5.initialize():
        print(f"initialize() failed, error code = {mt5.last_error()}")
        return False
        
    # Check if symbol is available in the MarketWatch
    if not mt5.symbol_select(SYMBOL, True):
        print(f"Failed to select symbol {SYMBOL}")
        mt5.shutdown()
        return False
        
    return True

def background_monitor(engine):
    """
    Background thread that monitors active trades every 1 second.
    Completely independent of the main candle loop.
    """
    print(f"[{time.strftime('%H:%M:%S')}] 🚀 High-Frequency Management Thread Started.")
    while True:
        try:
            engine.monitor_active_trade()
            time.sleep(1) # React in less than 1 second
        except Exception as e:
            # We don't want the monitor thread to ever crash the whole bot
            time.sleep(5)

def main():
    print("--- STARTING Phase 5: METATRADER 5 DEMO INTEGRATION ---")
    
    # Ask for configuration
    try:
        num_strategies = int(input("How many strategies do you want to run? (2-5): "))
        num_strategies = max(1, min(5, num_strategies)) # bounds check
    except ValueError:
        print("Invalid input for strategies. Defaulting to 3.")
        num_strategies = 3
        
    timeframe_input = input("Which timeframe? (M1, M5, M15, M30, H1, H4, D1) [Default: H1]: ").strip().upper()
    
    # Map input timeframe to MT5 constant
    tf_map = {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30,
        "H1": mt5.TIMEFRAME_H1,
        "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1
    }
    
    TIMEFRAME = tf_map.get(timeframe_input, mt5.TIMEFRAME_H1)
    tf_display = timeframe_input if timeframe_input in tf_map else "H1"
    
    print(f"\n--- Configuration: {num_strategies} Strategies on {tf_display} ---")

    if not setup_mt5():
        return
        
    account_info = mt5.account_info()
    if account_info is None:
        print("Failed to get MT5 account info.")
        mt5.shutdown()
        return
        
    balance = account_info.balance
    print(f"Connected to MT5. Current Account Balance: ${balance:.2f} | Account: {account_info.login} | Server: {account_info.server}")

    # Ask for Execution Mode
    exec_mode = input("\nEnable REAL MT5 Execution? (y/n) [Default: n]: ").strip().lower()
    enable_execution = exec_mode == 'y'

    auto_repeat_input = input("Enable Auto-Repeat (automatically wait for next candle)? (y/n) [Default: y]: ").strip().lower()
    auto_repeat = auto_repeat_input != 'n'

    # 1. Fetch initial warmup history (e.g., 500 bars)
    print("Fetching historical data for Engine warmup...")
    history_df = get_historical_data(SYMBOL, TIMEFRAME, 500)
    
    if history_df is None or history_df.empty:
        mt5.shutdown()
        return

    # 2. Start-up Configuration
    demo = LiveDemoEngine(
        initial_balance=balance, 
        risk_per_trade=RISK_PERCENT, 
        num_strategies=num_strategies,
        use_mt5=enable_execution,
        symbol=SYMBOL
    )
    
    # 2.5 Optional Online Reporting
    if GOOGLE_SHEET_URL:
        demo.google_sheet_url = GOOGLE_SHEET_URL
        print(f"[{time.strftime('%H:%M:%S')}] ☁️ Cloud Reporting Enabled: {GOOGLE_SHEET_URL}")
    else:
        print(f"[{time.strftime('%H:%M:%S')}] 📄 Local Logging Only (Google Sheet URL not set).")

    
    # Track the last known candle timestamp so we only process new candles once
    last_processed_time = history_df.iloc[-1]['timestamp']
    
    print(f"Waiting for new {SYMBOL} {tf_display} candles from MT5...")
    
    # --- START HIGH-FREQUENCY MONITOR THREAD ---
    monitor_thread = threading.Thread(target=background_monitor, args=(demo,), daemon=True)
    monitor_thread.start()
    
    # 3. Check initial market status
    is_open, status_msg = SessionEngine.get_market_status()
    print(f"\n[{time.strftime('%H:%M:%S')}] INITIAL STATUS: {status_msg}")
    last_market_status = is_open

    try:
        while True:
            # Check for market status changes
            current_open, current_msg = SessionEngine.get_market_status()
            if current_open != last_market_status:
                print(f"\n[{time.strftime('%H:%M:%S')}] MARKET STATUS ALERT: {current_msg}")
                last_market_status = current_open

            # Poll MT5 for new closed candles
            time.sleep(10)
            
            latest_candle = get_current_candle(SYMBOL, TIMEFRAME)
            if latest_candle is None:
                continue
                
            latest_time = latest_candle['timestamp']
            
            # If the timestamp of the last *closed* candle is newer than our recorded one
            if latest_time > last_processed_time:
                print(f"\n[{time.strftime('%H:%M:%S')}] New {tf_display} closed candle detected at {latest_time}!")
                last_processed_time = latest_time
                
                # Check for trade
                old_balance = demo.balance
                history_df = demo.on_new_candle(latest_candle, history_df)
                
                # If no trade was taken (and no trade is active)
                if not demo.active_trade and not auto_repeat:
                    choice = input("\nNo trade found. Repeat and wait for next candle? (y/n) or type 'auto' to enable auto-mode: ").strip().lower()
                    if choice == 'n':
                        print("Stopping MT5 Demo Engine.")
                        break
                    elif choice == 'auto':
                        auto_repeat = True
                        print("Auto-Repeat enabled. Waiting for next candle...")
                    else:
                        print("Waiting for next candle...")
                
    except KeyboardInterrupt:
        print("\nStopping MT5 Demo Engine.")
        
    finally:
        mt5.shutdown()
        
if __name__ == "__main__":
    main()
