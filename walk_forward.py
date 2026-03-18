import pandas as pd
from backtest_engine import BacktestEngine
from performance import PerformanceAnalyzer

class WalkForwardEngine:
    def __init__(self, data, window_size=1000, step_size=500, initial_balance=10000, risk_per_trade=0.01, num_strategies=5):
        self.data = data
        self.window_size = window_size
        self.step_size = step_size
        self.initial_balance = initial_balance  
        self.risk_per_trade = risk_per_trade
        self.num_strategies = num_strategies
        
    def run(self):
        results = []
        all_trades = []
        
        start_idx = 0
        fold = 1
        
        while start_idx + self.window_size <= len(self.data):
            end_idx = start_idx + self.window_size
            
            test_slice = self.data.iloc[start_idx:end_idx].reset_index(drop=True)
            
            print(f"Running Walk-Forward Fold {fold} | Rows {start_idx} to {end_idx}")
            
            # Run simulation on this slice independently
            engine = BacktestEngine(test_slice, initial_balance=self.initial_balance, risk_per_trade=self.risk_per_trade, num_strategies=self.num_strategies)
            trades, equity_curve = engine.run()
            
            # Analyze performance for this isolated fold
            analyzer = PerformanceAnalyzer(trades, equity_curve, self.initial_balance)
            report = analyzer.generate_report()
            report['Fold'] = fold
            
            results.append(report)
            all_trades.extend(trades)
            
            # Step forward
            start_idx += self.step_size
            fold += 1
            
        print("\n=== WALK-FORWARD VALIDATION SUMMARY ===")
        for r in results:
            print(f"Fold {r['Fold']} | Trades: {r['Total Trades']} | Win Rate: {r.get('Win Rate (%)', 0)}% | Max DD: {r.get('Max Drawdown (%)', 0)}% | Expectancy: {r.get('Expectancy per trade', 0)}")
            
        return results, all_trades
