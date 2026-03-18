from risk_engine import RiskEngine
from strategy_engine import StrategyEngine

class BacktestEngine:
    def __init__(self, data, initial_balance=10000.0, risk_per_trade=0.01, num_strategies=5, spread=0.20):
        self.data = data
        self.balance = initial_balance
        self.initial_balance = initial_balance
        self.risk_engine = RiskEngine(risk_percent=risk_per_trade)
        self.strategy = StrategyEngine()
        self.num_strategies = num_strategies
        self.spread = spread # Spread in $ (e.g. 0.20 for XAUUSD)
        self.trades = []
        self.equity_curve = []
        
    def run(self):
        # We start looking for signals after 200 candles to give indicators time to settle, 
        # though we already dropped NaN in indicator engine, we can just start at index 1
        for i in range(1, len(self.data) - 1):
            current_slice = self.data.iloc[:i+1]
            
            signal = self.strategy.check_strategy(current_slice, self.num_strategies)
            
            if signal:
                result = self.simulate_trade(i+1, signal)
                if result:
                    self.trades.append(result)
                    self.balance += result["profit"]
            
            self.equity_curve.append(self.balance)
            
        return self.trades, self.equity_curve
        
    def simulate_trade(self, start_index, signal):
        entry = signal["entry"]
        sl = signal["sl"]
        tp = signal["tp"]
        trade_type = signal["type"]
        entry_atr = self.data.iloc[start_index-1].get("atr_14", 0)
        
        # Risk & Size
        risk_amount = self.risk_engine.calculate_risk_amount(self.balance)
        stop_distance = abs(entry - sl)
        if stop_distance == 0:
            return None
            
        position_size = risk_amount / stop_distance
        lots, actual_risk_pct, is_high_risk = self.risk_engine.calculate_lots(self.balance, risk_amount, stop_distance)
        final_risk_amount = (actual_risk_pct / 100) * self.balance
        
        # Spread Cost Adjustment (Upfront)
        # Contract size for XAUUSD is usually 100. Spread 0.20 * 100 * lots = $20 per 1.0 lot.
        spread_cost = self.spread * lots * 100 
        
        # Partial TP Setup (50% at 1:1 Risk/Reward)
        tp_1 = entry + (entry - sl) if trade_type == "long" else entry - (sl - entry)
        partial_hit = False
        partial_profit = 0.0
        
        be_moved = False
        current_sl = sl
        
        # Step forward in time
        for j in range(start_index, len(self.data)):
            candle = self.data.iloc[j]
            high = candle["high"]
            low = candle["low"]
            close = candle["close"]
            atr = candle.get("atr_14", entry_atr)
            
            if trade_type == "long":
                profit_points = close - entry
                
                # 1. Partial TP Check (50% at TP1)
                if not partial_hit and high >= tp_1:
                    partial_profit = (tp_1 - entry) * (position_size * 0.5)
                    partial_hit = True
                    # Move to Break-even automatically on Partial TP
                    current_sl = entry + (atr * 0.1)
                    be_moved = True

                # 2. Break-Even Check (if not already moved by Partial TP)
                if not be_moved and profit_points > (entry_atr * 1.0):
                    current_sl = entry + (atr * 0.1)
                    be_moved = True

                # 3. Trailing Stop
                if profit_points > (entry_atr * 1.5):
                    suggested_sl = close - (atr * 1.5)
                    if suggested_sl > current_sl:
                        current_sl = suggested_sl

                # Check Exits
                if low <= current_sl:
                    # Calculate PnL for remaining 50% (or 100% if no partial hit)
                    remaining_pct = 0.5 if partial_hit else 1.0
                    pnl_remaining = (current_sl - entry) * (position_size * remaining_pct)
                    total_pnl = partial_profit + pnl_remaining - spread_cost
                    return {
                        "type": "long", "lots": lots, "profit": total_pnl, 
                        "status": "partial_hit_then_sl" if partial_hit else "sl",
                        "partial_tp": partial_hit
                    }
                if high >= tp:
                    remaining_pct = 0.5 if partial_hit else 1.0
                    pnl_remaining = (tp - entry) * (position_size * remaining_pct)
                    total_pnl = partial_profit + pnl_remaining - spread_cost
                    return {
                        "type": "long", "lots": lots, "profit": total_pnl, 
                        "status": "tp", "partial_tp": partial_hit
                    }
            
            else: # short
                profit_points = entry - close
                
                # 1. Partial TP
                if not partial_hit and low <= tp_1:
                    partial_profit = (entry - tp_1) * (position_size * 0.5)
                    partial_hit = True
                    current_sl = entry - (atr * 0.1)
                    be_moved = True

                # 2. Break-Even
                if not be_moved and profit_points > (entry_atr * 1.0):
                    current_sl = entry - (atr * 0.1)
                    be_moved = True

                # 3. Trailing Stop
                if profit_points > (entry_atr * 1.5):
                    suggested_sl = close + (atr * 1.5)
                    if suggested_sl < current_sl:
                        current_sl = suggested_sl

                # Check Exits
                if high >= current_sl:
                    remaining_pct = 0.5 if partial_hit else 1.0
                    pnl_remaining = (entry - current_sl) * (position_size * remaining_pct)
                    total_pnl = partial_profit + pnl_remaining - spread_cost
                    return {
                        "type": "short", "lots": lots, "profit": total_pnl, 
                        "status": "partial_hit_then_sl" if partial_hit else "sl",
                        "partial_tp": partial_hit
                    }
                if low <= tp:
                    remaining_pct = 0.5 if partial_hit else 1.0
                    pnl_remaining = (entry - tp) * (position_size * remaining_pct)
                    total_pnl = partial_profit + pnl_remaining - spread_cost
                    return {
                        "type": "short", "lots": lots, "profit": total_pnl, 
                        "status": "tp", "partial_tp": partial_hit
                    }
                    
        return None
