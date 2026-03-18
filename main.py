from data_layer import DataLayer
from indicator_engine import IndicatorEngine
from backtest_engine import BacktestEngine
from performance import PerformanceAnalyzer

def main():
    dl = DataLayer()
    df = dl.generate_synthetic_data(5000)
    print("Generated 5000 rows of synthetic OHLCV data.")
    
    df = IndicatorEngine.add_features(df)
    print(f"Added indicators. {len(df)} rows remaining after warmup.")
    
    from structure_engine import StructureEngine
    df = StructureEngine.add_structure(df, left_bars=5, right_bars=5)
    print("Added structure detection.")
    
    from session_engine import SessionEngine
    df = SessionEngine.add_sessions(df)
    print("Added session filters.")
    
    from walk_forward import WalkForwardEngine
    
    try:
        start_balance = float(input("Enter starting balance for backtest: "))
    except ValueError:
        print("Invalid input for balance. Defaulting to 10000.0")
        start_balance = 10000.0
        
    try:
        num_strategies = int(input("How many strategies do you want to run? (2-5): "))
        num_strategies = max(1, min(5, num_strategies)) # bounds check
    except ValueError:
        print("Invalid input for strategies. Defaulting to 3.")
        num_strategies = 3

    wf_engine = WalkForwardEngine(
        df, 
        window_size=1000, 
        step_size=500, 
        initial_balance=start_balance, 
        risk_per_trade=0.01,
        num_strategies=num_strategies
    )
    results, all_trades = wf_engine.run()
    
    # Analyze total performance across all disjoint trades
    analyzer = PerformanceAnalyzer(all_trades, [], start_balance) # Quick global stat without equity reconstruction
    global_report = analyzer.generate_report()
    
    print("\n--- GLOBAL AGGREGATE STATS ---")
    print(f"Total Trades Taken Across Folds: {global_report['Total Trades']}")
    print(f"Global Win Rate (%): {global_report.get('Win Rate (%)', 0)}")
    print(f"Global Expectancy: {global_report.get('Expectancy per trade', 0)}")

if __name__ == "__main__":
    main()
