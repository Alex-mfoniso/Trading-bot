import numpy as np

class PerformanceAnalyzer:
    def __init__(self, trades, equity_curve, initial_balance):
        self.trades = trades
        self.equity_curve = equity_curve
        self.initial_balance = initial_balance
        
    def calculate_drawdown(self):
        if not self.equity_curve:
            return 0.0
            
        peak = self.initial_balance
        max_dd = 0.0
        
        for equity in self.equity_curve:
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak
            if dd > max_dd:
                max_dd = dd
                
        return max_dd
        
    def generate_report(self):
        total_trades = len(self.trades)
        if total_trades == 0:
            return {"Total Trades": 0}
            
        wins = [t for t in self.trades if t["profit"] > 0]
        losses = [t for t in self.trades if t["profit"] < 0]
        win_rate = len(wins) / total_trades
        avg_win = np.mean([t["profit"] for t in wins]) if wins else 0
        avg_loss = np.mean([abs(t["profit"]) for t in losses]) if losses else 0
        avg_rr = avg_win / avg_loss if avg_loss != 0 else 0
        
        max_drawdown = self.calculate_drawdown()
        final_balance = self.equity_curve[-1] if self.equity_curve else self.initial_balance
        expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)
        
        return {
            "Total Trades": total_trades,
            "Win Rate (%)": round(win_rate * 100, 2),
            "Average RR": round(avg_rr, 2),
            "Max Drawdown (%)": round(max_drawdown * 100, 2),
            "Final Balance": round(final_balance, 2),
            "Expectancy per trade": round(expectancy, 2)
        }
