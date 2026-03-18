import pandas as pd
import numpy as np

class StructureEngine:
    @staticmethod
    def add_structure(df: pd.DataFrame, left_bars=5, right_bars=5) -> pd.DataFrame:
        df = df.copy()
        
        highs = df['high'].values
        lows = df['low'].values
        closes = df['close'].values
        
        swing_highs = np.full(len(df), np.nan)
        swing_lows = np.full(len(df), np.nan)
        
        for i in range(left_bars + right_bars, len(df)):
            window_highs = highs[i - (left_bars + right_bars) : i + 1]
            window_lows = lows[i - (left_bars + right_bars) : i + 1]
            
            center_high = highs[i - right_bars]
            center_low = lows[i - right_bars]
            
            # Use max/min to find if center is the strict extreme
            if center_high == np.max(window_highs):
                swing_highs[i] = center_high
                
            if center_low == np.min(window_lows):
                swing_lows[i] = center_low
                
        df['last_swing_high'] = pd.Series(swing_highs).ffill()
        df['last_swing_low'] = pd.Series(swing_lows).ffill()
        
        bos_bullish = np.zeros(len(df), dtype=bool)
        bos_bearish = np.zeros(len(df), dtype=bool)
        trend = np.zeros(len(df), dtype=int)
        
        current_trend = 0
        
        for i in range(1, len(df)):
            close_price = closes[i]
            lsh = df['last_swing_high'].iloc[i]
            lsl = df['last_swing_low'].iloc[i]
            
            prev_close = closes[i-1]
            
            bos_bull = False
            bos_bear = False
            
            # Break of structure checking
            if not np.isnan(lsh) and close_price > lsh and prev_close <= lsh:
                bos_bull = True
                bos_bullish[i] = True
                
            if not np.isnan(lsl) and close_price < lsl and prev_close >= lsl:
                bos_bear = True
                bos_bearish[i] = True
                
            if bos_bull:
                current_trend = 1
            elif bos_bear:
                current_trend = -1
                
            trend[i] = current_trend
            
        df['bos_bullish'] = bos_bullish
        df['bos_bearish'] = bos_bearish
        df['trend_state'] = trend
        
        return df
