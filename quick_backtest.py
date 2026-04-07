import MetaTrader5 as mt5
import pandas as pd
import time
from session_engine import SessionEngine
from indicator_engine import IndicatorEngine
from structure_engine import StructureEngine
from backtest_engine import BacktestEngine
from performance import PerformanceAnalyzer

# --- Configuration ---
SYMBOL = "CADCHF"
TIMEFRAME = mt5.TIMEFRAME_H1 # USER is likely running H1
NUM_BARS = 100 # ~4 days of H1 data

def get_historical_data(symbol, timeframe, num_bars):
    if not mt5.initialize():
        print(f"initialize() failed, error code = {mt5.last_error()}")
        return None
    
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

def run_diagnostic():
    print(f"--- DIAGNOSTIC: Checking last {NUM_BARS} M5 bars for {SYMBOL} ---")
    df = get_historical_data(SYMBOL, TIMEFRAME, NUM_BARS)
    
    if df is None or df.empty:
        print("Data fetching failed.")
        mt5.shutdown()
        return

    print("--- Processing Indicators ---")
    df = IndicatorEngine.add_features(df)
    df = StructureEngine.add_structure(df)
    df = SessionEngine.add_sessions(df)
    
    print(f"--- Running Diagnostic Backtest (5 Strategies) ---")
    engine = BacktestEngine(df, initial_balance=5000, risk_per_trade=0.01, num_strategies=5, spread=0.20)
    trades, equity_curve = engine.run()
    
    print("\nDIAGNOSTIC TRADES FOUND (Last 2-3 Days):")
    if not trades:
        print(">>> NO TRADES FOUND in the last 1000 M5 bars. Strategies are currently too restrictive for this market regime.")
    else:
        for t in trades:
            print(f"[{t.get('open_time')}] {t['type'].upper()} | Strategy: {t.get('strategy_name', t['strategy'])} | Result: {t['profit']:.2f}")

    # Check ADX and RSI averages to see market regime
    last_adx = df['adx'].iloc[-1]
    avg_adx = df['adx'].tail(NUM_BARS).mean()
    print(f"\nMarket Context:")
    print(f"Current ADX: {last_adx:.2f}")
    print(f"Average ADX (Last 1000 bars): {avg_adx:.2f} (< 25 = No TrendFollow, < 20 = Range only)")
    
    mt5.shutdown()

if __name__ == "__main__":
    run_diagnostic()
