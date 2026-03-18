import pandas as pd
import numpy as np

class DataLayer:
    def __init__(self, data_path=None):
        self.data_path = data_path

    def load_data(self):
        if self.data_path:
            return pd.read_csv(self.data_path)
        return None
        
    def generate_synthetic_data(self, periods=5000):
        np.random.seed(42)
        dates = pd.date_range(start="2020-01-01", periods=periods, freq="1h")
        
        returns = np.random.normal(0, 0.002, periods)
        close = 2000 * np.exp(np.cumsum(returns))
        
        high = close * (1 + np.abs(np.random.normal(0, 0.001, periods)))
        low = close * (1 - np.abs(np.random.normal(0, 0.001, periods)))
        open_price = pd.Series(close).shift(1).fillna(close[0]).values
        
        high = np.maximum.reduce([high, open_price, close])
        low = np.minimum.reduce([low, open_price, close])
        volume = np.random.randint(100, 1000, periods)
        
        df = pd.DataFrame({
            "timestamp": dates,
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume
        })
        return df
