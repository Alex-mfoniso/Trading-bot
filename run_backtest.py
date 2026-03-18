import MetaTrader5 as mt5
import pandas as pd
import time
from session_engine import SessionEngine
from indicator_engine import IndicatorEngine
from structure_engine import StructureEngine
from backtest_engine import BacktestEngine
from performance import PerformanceAnalyzer

# --- Configuration ---
SYMBOL = "XAUUSD"

def get_historical_data(symbol, timeframe, num_bars):
    """
    Fetches historical bars from MT5 and formats them into our standard DataFrame.
    """
    if not mt5.initialize():
        print(f"initialize() failed, error code = {mt5.last_error()}")
        return None
    
    # We fetch num_bars + 250 for indicator warmup
    total_bars = num_bars + 250
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, total_bars)
    
    if rates is None:
        print(f"Failed to copy rates from MT5! Error code: {mt5.last_error()}")
        return None
        
    df = pd.DataFrame(rates)
    df['timestamp'] = pd.to_datetime(df['time'], unit='s')
    df.rename(columns={'tick_volume': 'volume'}, inplace=True)
    df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
    
    return df

def run_full_backtest():
    print("--- STARTING Phase 6: HISTORICAL BACKTEST ---")
    
    # User Inputs
    try:
        num_bars = int(input("How many bars to backtest? (e.g. 1000, 5000): "))
    except ValueError:
        num_bars = 1000
    
    timeframe_input = input("Which timeframe? (M1, M5, M15, M30, H1, H4, D1) [Default: H1]: ").strip().upper()
    
    tf_map = {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30,
        "H1": mt5.TIMEFRAME_H1,
        "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1
    }
    
    timeframe = tf_map.get(timeframe_input, mt5.TIMEFRAME_H1)
    tf_display = timeframe_input if timeframe_input in tf_map else "H1"
    
    try:
        num_strategies = int(input("How many strategies? (1-5): "))
        num_strategies = max(1, min(5, num_strategies))
    except ValueError:
        num_strategies = 3
        
    try:
        start_balance = float(input("Starting balance? (e.g. 10000.0): "))
    except ValueError:
        start_balance = 10000.0
        
    try:
        spread = float(input("Spread in $? (e.g. 0.20 for XAUUSD) [Default 0.20]: "))
    except ValueError:
        spread = 0.20

    print(f"\n--- Fetching Data for {SYMBOL} {tf_display} ---")
    df = get_historical_data(SYMBOL, timeframe, num_bars)
    
    if df is None or df.empty:
        print("Data fetching failed. Exiting.")
        mt5.shutdown()
        return

    print("--- Processing Indicators and Structure ---")
    df = IndicatorEngine.add_features(df)
    df = StructureEngine.add_structure(df)
    df = SessionEngine.add_sessions(df)
    
    # Market status check (optional for backtest, but good for context)
    is_open, status_msg = SessionEngine.get_market_status()
    print(f"Current Market Status: {status_msg}")
    
    print(f"--- Running Backtest on {len(df)} bars (after warmup) ---")
    engine = BacktestEngine(df, initial_balance=start_balance, risk_per_trade=0.01, num_strategies=num_strategies, spread=spread)
    trades, equity_curve = engine.run()
    
    print("--- Generating Performance Report ---")
    analyzer = PerformanceAnalyzer(trades, equity_curve, start_balance)
    report = analyzer.generate_report()
    
    print("\n" + "="*40)
    print(f" BACKTEST REPORT: {SYMBOL} {tf_display}")
    print("="*40)
    for key, value in report.items():
        print(f"{key:25}: {value}")
    print("="*40)
    
    mt5.shutdown()

if __name__ == "__main__":
    run_full_backtest()
