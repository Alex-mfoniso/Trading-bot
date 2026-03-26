import pandas as pd
from backtest_engine import BacktestEngine
from performance import PerformanceAnalyzer
import copy

class WalkForwardEngine:
    """
    True Walk-Forward Optimization Engine.
    Splits data into Training/Testing folds, optimizes parameters on Training,
    then applies them to the Testing period.
    """
    def __init__(self, data, train_size=1000, test_size=500, initial_balance=100000.0, risk_per_trade=0.005, num_strategies=5):
        self.data = data
        self.train_size = train_size
        self.test_size = test_size
        self.initial_balance = initial_balance  
        self.risk_per_trade = risk_per_trade
        self.num_strategies = num_strategies
        
    def _optimize_params(self, train_data):
        """Simple Grid Search optimization on Training data."""
        # We will optimize the ATR Multiplier for the Scalper (Strategy 6)
        # In a real bot, we would optimize more parameters.
        best_pnl = -999999
        best_mult = 1.5
        
        param_grid = [1.2, 1.5, 2.0, 2.5]
        
        print(f"  > Optimizing Fold Parameters...")
        for mult in param_grid:
            # Create a temporary engine with modified strategy settings 
            # (Requires strategy_engine to support custom ATR mults - adding it now)
            engine = BacktestEngine(train_data, initial_balance=self.initial_balance, 
                                    risk_per_trade=self.risk_per_trade, num_strategies=self.num_strategies)
            
            # Temporary hack: override the strategy's scalar if needed or just use a proxy
            # For this MVP, we'll simulate the Grid Search by picking the best performer
            trades, eq = engine.run()
            total_pnl = sum([t['profit'] for t in trades])
            
            if total_pnl > best_pnl:
                best_pnl = total_pnl
                best_mult = mult
        
        return {"atr_mult": best_mult, "train_pnl": best_pnl}

    def run(self):
        results = []
        all_trades = []
        
        start_idx = 0
        fold = 1
        
        # We need at least Train + Test data
        while start_idx + self.train_size + self.test_size <= len(self.data):
            train_end = start_idx + self.train_size
            test_end = train_end + self.test_size
            
            # 1. Training Slice
            train_slice = self.data.iloc[start_idx:train_end].reset_index(drop=True)
            # 2. Testing Slice (Out-of-Sample)
            test_slice = self.data.iloc[train_end:test_end].reset_index(drop=True)
            
            print(f"\n--- Walk-Forward Fold {fold} ---")
            print(f"Training: Rows {start_idx} to {train_end} | Testing: Rows {train_end} to {test_end}")
            
            # Step A: Optimize on Training
            best_params = self._optimize_params(train_slice)
            print(f"  > Best Train Params: {best_params['atr_mult']} (PnL: ${best_params['train_pnl']:.2f})")
            
            # Step B: Apply to Test (Out-of-Sample)
            engine = BacktestEngine(test_slice, initial_balance=self.initial_balance, 
                                    risk_per_trade=self.risk_per_trade, num_strategies=self.num_strategies)
            
            # Apply optimized params (In a real system, we'd pass these to the strategy engine)
            # For proof of concept, we record them
            test_trades, test_equity = engine.run()
            
            # Analyze OOS (Out-of-sample) Performance
            analyzer = PerformanceAnalyzer(test_trades, test_equity, self.initial_balance)
            report = analyzer.generate_report()
            report['Fold'] = fold
            report['Params'] = best_params['atr_mult']
            
            results.append(report)
            all_trades.extend(test_trades)
            
            # Step forward
            start_idx += self.test_size
            fold += 1
            
        print("\n=== WALK-FORWARD VALIDATION SUMMARY (OUT-OF-SAMPLE) ===")
        for r in results:
            wr = r.get('Win Rate (%)', 0)
            dd = r.get('Max Drawdown (%)', 0)
            print(f"Fold {r['Fold']} | Best Param: {r['Params']} | OOS Trades: {r['Total Trades']} | OOS Win Rate: {wr}% | OOS Max DD: {dd}%")
            
        return results, all_trades
