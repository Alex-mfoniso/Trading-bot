import unittest
import pandas as pd
import numpy as np
from risk_engine import RiskEngine
from backtest_engine import BacktestEngine
from strategy_engine import StrategyEngine

class TestTradingBot(unittest.TestCase):
    
    def setUp(self):
        # Create a mock RiskEngine
        self.risk = RiskEngine(
            initial_balance=100000, 
            risk_percent=0.01, 
            fixed_risk_usd=500.0,
            daily_loss_limit=2000.0,
            max_overall_loss=5000.0
        )
        
        # Create mock data for BacktestEngine
        dates = pd.date_range(start="2024-01-01", periods=300, freq="h")
        self.mock_data = pd.DataFrame({
            "timestamp": dates,
            "open": np.linspace(2000, 2100, 300),
            "high": np.linspace(2005, 2105, 300),
            "low": np.linspace(1995, 2095, 300),
            "close": np.linspace(2000, 2100, 300),
            "volume": [100] * 300,
            "ema_200": [2005] * 300, # Warmup indicators
            "atr_14": [10] * 300,
            "is_killzone": [True] * 300
        })

    def test_risk_allowed(self):
        # 1. Check Standard Allowed
        allowed, reason = self.risk.is_trading_allowed(100000)
        self.assertTrue(allowed)
        
        # 2. Check Daily Limit Hit
        self.risk.update_daily_pnl(-2500)
        allowed, reason = self.risk.is_trading_allowed(97500)
        self.assertFalse(allowed)
        self.assertIn("DAILY LIMIT", reason)
        
        # 3. Check Overall Drawdown Hit
        self.risk.reset_daily_pnl()
        allowed, reason = self.risk.is_trading_allowed(94000) # Floor is 95000
        self.assertFalse(allowed)
        self.assertIn("MAX DRAWDOWN", reason)

    def test_calculate_lots(self):
        # 1. Normal Trade (Risk $500, SL Distance 10 pts, Contract 100)
        # $500 / (10 * 100) = 0.5 Lots
        lots, risk_pct, skip, reason = self.risk.calculate_lots(100000, 500, 10.0)
        self.assertEqual(lots, 0.5)
        self.assertFalse(skip)
        
        # 2. Extreme Risk (0.01 lot risks $200 but target is $25)
        self.risk.fixed_risk_usd = 25.0
        lots, risk_pct, skip, reason = self.risk.calculate_lots(100000, 25.0, 50.0)
        # 0.01 * 50 * 100 = $50. $50 > $25 * 1.5 ($37.50). 
        # So skip = True.
        self.assertTrue(skip)
        self.assertIn("Risk too high", reason)

    def test_backtest_warmup(self):
        engine = BacktestEngine(self.mock_data.iloc[:50], initial_balance=100000) # Only 50 bars
        trades, equity = engine.run()
        # Should have zero trades because warmup is < 200 bars
        self.assertEqual(len(trades), 0)

    def test_partial_tp_logic(self):
        # Create a tiny 10-bar dataset with a clear winning breakout
        test_data = pd.DataFrame({
            "timestamp": pd.date_range("2024-01-01", periods=10, freq="h"),
            "open": [2000, 2010, 2020, 2030, 2040, 2050, 2060, 2070, 2080, 2090],
            "high": [2005, 2015, 2025, 2035, 2045, 2055, 2065, 2075, 2085, 2095],
            "low":  [1995, 2005, 2015, 2025, 2035, 2045, 2055, 2065, 2075, 2085],
            "close": [2000, 2010, 2020, 2030, 2040, 2050, 2060, 2070, 2080, 2090],
            "ema_200": [1900]*10, "atr_14": [10]*10, "is_killzone": [True]*10
        })
        
        engine = BacktestEngine(test_data, initial_balance=100000)
        # Manually trigger a trade simulation
        signal = {"type": "long", "entry": 2010, "sl": 2000, "tp": 2050}
        result = engine.simulate_trade(2, signal)
        
        # Result should show partial TP hit
        self.assertIsNotNone(result)
        self.assertTrue(result["partial_tp"])
        self.assertTrue(result["profit"] > 0)

if __name__ == "__main__":
    unittest.main()
