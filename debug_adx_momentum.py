import MetaTrader5 as mt5
import pandas as pd
from indicator_engine import IndicatorEngine

if not mt5.initialize():
    exit()

symbol = "XAUUSD"
timeframe = mt5.TIMEFRAME_M5

rates = mt5.copy_rates_from_pos(symbol, timeframe, 1, 100)
if rates is not None:
    df = pd.DataFrame(rates)
    df['timestamp'] = pd.to_datetime(df['time'], unit='s')
    df.rename(columns={'tick_volume': 'volume'}, inplace=True)
    df = IndicatorEngine.add_features(df)
    
    last_10 = df.tail(10)
    print("--- ADX MOMENTUM (Last 10 Candles) ---")
    for i, row in last_10.iterrows():
        print(f"Time: {row['timestamp']} | ADX: {row['adx']:.2f}")

mt5.shutdown()
