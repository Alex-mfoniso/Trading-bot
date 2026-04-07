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
    
    last = df.iloc[-1]
    print(f"RSI: {last['rsi_14']:.2f}")
    print(f"ADX: {last['adx']:.2f}")
    print(f"Close: {last['close']:.2f} | ATR: {last['atr_14']:.2f} | BB_Lower: {last['bb_lower']:.2f} | BB_Upper: {last['bb_upper']:.2f}")

mt5.shutdown()
