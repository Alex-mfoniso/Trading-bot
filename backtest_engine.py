import pandas as pd
from risk_engine import RiskEngine
from strategy_engine import StrategyEngine

class BacktestEngine:
    """
    Advanced Backtesting Engine with slippage, commission, and prop-firm risk gating.
    Now supports the Elite RiskEngine API.
    """
    def __init__(self, data, 
                 initial_balance=5000.0, 
                 risk_per_trade=0.005, 
                 num_strategies=5, 
                 spread=0.20,
                 commission_per_lot=7.0,
                 slippage_per_lot=2.0,
                 fixed_risk_usd=25.0,
                 daily_loss_limit=150.0,
                 max_overall_loss=500.0,
                 target_profit=400.0,
                 max_lots_per_trade=5.0):
        
        self.data = data
        self.balance = initial_balance
        self.initial_balance = initial_balance
        self.risk_engine = RiskEngine(
            risk_percent=risk_per_trade,
            fixed_risk_usd=fixed_risk_usd,
            daily_loss_limit=daily_loss_limit,
            max_overall_loss=max_overall_loss,
            initial_balance=initial_balance,
            target_profit=target_profit,
            max_lots_per_trade=max_lots_per_trade
        )
        self.strategy = StrategyEngine()
        self.num_strategies = num_strategies
        self.spread = spread
        self.commission_per_lot = commission_per_lot
        self.slippage_per_lot = slippage_per_lot
        self.trades = []
        self.equity_curve = []
        self.cooldown_until = 0 # Index until which we skip trades
        
    def run(self):
        """Main backtest loop."""
        for i in range(1, len(self.data) - 1):
            current_row = self.data.iloc[i]
            
            # 1. Warmup Guard & Indicator Integrity
            if i < 200: # Ensure at least 200 bars for EMA 200 and other indicators
                self.equity_curve.append(self.balance)
                continue
                
            # Check for NaNs in critical columns at current index
            if pd.isna(current_row.get("ema_200")) or pd.isna(current_row.get("atr_14")):
                self.equity_curve.append(self.balance)
                continue

            # 2. Risk Gate Check
            allowed, reason = self.risk_engine.is_trading_allowed(self.balance, current_row["timestamp"])
            if not allowed:
                self.equity_curve.append(self.balance)
                continue
                
            # 3. Cooldown Check (One-at-a-time + 5 bar buffer)
            if i < self.cooldown_until:
                self.equity_curve.append(self.balance)
                continue

            # 4. Strategy Check
            current_slice = self.data.iloc[:i+1]
            signal = self.strategy.check_strategy(current_slice, self.num_strategies)
            
            if signal:
                # 5. Simulate Trade
                result = self.simulate_trade(i+1, signal)
                if result:
                    self.trades.append(result)
                    self.balance += result["profit"]
                    self.risk_engine.update_daily_pnl(result["profit"])
                    # Set cooldown (skip next 5 bars after trade closes)
                    self.cooldown_until = result["exit_index"] + 5
            
            self.equity_curve.append(self.balance)
            
        return self.trades, self.equity_curve
        
    def simulate_trade(self, start_index, signal):
        """Simulates price action, stops, and management logic for a single trade."""
        entry = signal["entry"]
        sl = signal["sl"]
        tp = signal["tp"]
        trade_type = signal["type"]
        entry_row = self.data.iloc[start_index-1]
        entry_atr = entry_row.get("atr_14", 0)
        
        # Risk & Size
        risk_amount = self.risk_engine.calculate_risk_amount(self.balance)
        stop_distance = abs(entry - sl)
        if stop_distance == 0:
            return None
            
        # Call the new Elite RiskEngine calculate_lots
        lots, actual_risk_pct, should_skip, reason = self.risk_engine.calculate_lots(self.balance, risk_amount, stop_distance)
        
        if should_skip:
            return None
            
        # Position size in absolute units (e.g. 0.01 lot = 1.0 unit for XAUUSD math)
        position_size = lots * 100 
        
        # 0.1 Commission & Slippage model
        commission = self.commission_per_lot * lots
        slippage = self.slippage_per_lot * lots # Friction penalty
        spread_cost = self.spread * position_size 
        total_entry_friction = commission + slippage + spread_cost
        
        # Partial TP Setup (50% at 1:1 Risk/Reward)
        tp_1 = entry + (entry - sl) if trade_type == "long" else entry - (sl - entry)
        partial_hit = False
        partial_profit = 0.0
        
        be_moved = False
        current_sl = sl
        
        # Step forward in time until closure
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
                    # Move to Break-even (with minor buffer)
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
                    remaining_pct = 0.5 if partial_hit else 1.0
                    pnl_remaining = (current_sl - entry) * (position_size * remaining_pct)
                    total_pnl = partial_profit + pnl_remaining - total_entry_friction
                    return {
                        "type": "long", "lots": lots, "profit": total_pnl, 
                        "status": "partial_hit_then_sl" if partial_hit else "sl",
                        "partial_tp": partial_hit, "exit_index": j
                    }
                if high >= tp:
                    remaining_pct = 0.5 if partial_hit else 1.0
                    pnl_remaining = (tp - entry) * (position_size * remaining_pct)
                    total_pnl = partial_profit + pnl_remaining - total_entry_friction
                    return {
                        "type": "long", "lots": lots, "profit": total_pnl, 
                        "status": "tp", "partial_tp": partial_hit, "exit_index": j
                    }
            
            else: # short
                profit_points = entry - close
                
                # 1. Partial TP Check
                if not partial_hit and low <= tp_1:
                    partial_profit = (entry - tp_1) * (position_size * 0.5)
                    partial_hit = True
                    current_sl = entry - (atr * 0.1)
                    be_moved = True

                # 2. Break-Even Check
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
                    total_pnl = partial_profit + pnl_remaining - total_entry_friction
                    return {
                        "type": "short", "lots": lots, "profit": total_pnl, 
                        "status": "partial_hit_then_sl" if partial_hit else "sl",
                        "partial_tp": partial_hit, "exit_index": j
                    }
                if low <= tp:
                    remaining_pct = 0.5 if partial_hit else 1.0
                    pnl_remaining = (entry - tp) * (position_size * remaining_pct)
                    total_pnl = partial_profit + pnl_remaining - total_entry_friction
                    return {
                        "type": "short", "lots": lots, "profit": total_pnl, 
                        "status": "tp", "partial_tp": partial_hit, "exit_index": j
                    }
                    
        return {
            "type": trade_type, "lots": lots, "profit": (close - entry) * position_size - total_entry_friction,
            "status": "end_of_data", "partial_tp": partial_hit, "exit_index": len(self.data)-1
        }
