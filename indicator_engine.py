import pandas as pd
import numpy as np

class IndicatorEngine:
    @staticmethod
    def add_features(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        
        # EMAs
        df["ema_9"] = df["close"].ewm(span=9, adjust=False).mean()
        df["ema_21"] = df["close"].ewm(span=21, adjust=False).mean()
        df["ema_50"] = df["close"].ewm(span=50, adjust=False).mean()
        df["ema_200"] = df["close"].ewm(span=200, adjust=False).mean()
        
        # RSI 14 (Wilder's Smoothing)
        delta = df["close"].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
        rs = avg_gain / avg_loss
        df["rsi_14"] = 100 - (100 / (1 + rs))
        
        # ATR 14 (Wilder's Smoothing)
        high_low = df["high"] - df["low"]
        high_close = np.abs(df["high"] - df["close"].shift())
        low_close = np.abs(df["low"] - df["close"].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        df["atr_14"] = true_range.ewm(alpha=1/14, adjust=False).mean()
        
        # Volume average
        df["volume_avg"] = df["volume"].rolling(20).mean()

        # MACD (12, 26, 9)
        ema_12 = df['close'].ewm(span=12, adjust=False).mean()
        ema_26 = df['close'].ewm(span=26, adjust=False).mean()
        df['macd_line'] = ema_12 - ema_26
        df['macd_signal'] = df['macd_line'].ewm(span=9, adjust=False).mean()

        # Bollinger Bands (20, 2)
        df['bb_mid'] = df['close'].rolling(window=20).mean()
        bb_std = df['close'].rolling(window=20).std()
        df['bb_upper'] = df['bb_mid'] + (bb_std * 2)
        df['bb_lower'] = df['bb_mid'] - (bb_std * 2)
        df['bb_width'] = df['bb_upper'] - df['bb_lower']

        # ADX (Average Directional Index) - 14 period (Wilder's Smoothing)
        plus_dm_raw = df['high'].diff()
        minus_dm_raw = df['low'].diff()
        
        plus_dm = np.where((plus_dm_raw > 0) & (plus_dm_raw > minus_dm_raw), plus_dm_raw, 0)
        minus_dm = np.where((minus_dm_raw > 0) & (minus_dm_raw > plus_dm_raw), minus_dm_raw, 0)
        
        tr = pd.concat([df['high'] - df['low'], 
                        abs(df['high'] - df['close'].shift()), 
                        abs(df['low'] - df['close'].shift())], axis=1).max(axis=1)
        
        tr_smooth = tr.ewm(alpha=1/14, adjust=False).mean()
        
        plus_di = 100 * (pd.Series(plus_dm, index=df.index).ewm(alpha=1/14, adjust=False).mean() / tr_smooth)
        minus_di = 100 * (pd.Series(minus_dm, index=df.index).ewm(alpha=1/14, adjust=False).mean() / tr_smooth)
        
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        df['adx'] = dx.ewm(alpha=1/14, adjust=False).mean()

        # Rolling High/Low (Donchian 20)
        df['highest_20'] = df['high'].rolling(window=20).max()
        df['lowest_20'] = df['low'].rolling(window=20).min()
        
        # Drop initial NaN rows required for warmup
        df.dropna(inplace=True)
        return df.reset_index(drop=True)

