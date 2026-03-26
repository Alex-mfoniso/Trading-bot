import time
from datetime import datetime, timezone

class RiskEngine:
    """
    Elite Risk Management Engine designed for Prop Firm (GFT/Topstep) compliance.
    Handles dynamic lot sizing, daily loss limits (UTC reset), and overall drawdown.
    """
    def __init__(self, 
                 risk_percent=0.005, 
                 fixed_risk_usd=25.0, 
                 daily_loss_limit=150.0, 
                 max_overall_loss=500.0, 
                 initial_balance=5000.0, 
                 target_profit=400.0,
                 max_lots_per_trade=5.0):
        
        # Risk Parameters
        self.risk_percent = risk_percent
        self.fixed_risk_usd = fixed_risk_usd
        self.daily_loss_limit = abs(daily_loss_limit)
        self.max_overall_loss = abs(max_overall_loss)
        self.target_profit = abs(target_profit)
        self.initial_balance = initial_balance
        self.max_lots = max_lots_per_trade
        
        # Calculated Floors
        self.overall_loss_floor = initial_balance - self.max_overall_loss
        
        # State Trackers
        self.peak_equity = initial_balance
        self.daily_loss_accumulator = 0.0
        self.last_reset_date = datetime.now(timezone.utc).date()
        
    def _check_daily_reset(self, current_time=None):
        """Resets the daily loss tracker if a new day has started."""
        if current_time:
             if isinstance(current_time, str):
                 current_date = datetime.fromisoformat(current_time.replace('Z', '+00:00')).date()
             elif hasattr(current_time, 'date'):
                 current_date = current_time.date()
             else:
                 current_date = datetime.now(timezone.utc).date()
        else:
            current_date = datetime.now(timezone.utc).date()

        if current_date > self.last_reset_date:
            self.daily_loss_accumulator = 0.0
            self.last_reset_date = current_date
            
    def reset_daily_pnl(self):
        """Force manual reset of daily pnl accumulator."""
        self.daily_loss_accumulator = 0.0

    def calculate_risk_amount(self, account_balance):
        """Returns the conservative risk amount (Min of Fixed $ vs %)."""
        pct_risk = account_balance * self.risk_percent
        return min(self.fixed_risk_usd, pct_risk)

    def is_trading_allowed(self, current_balance, current_time=None):
        """Standard check for prop firm limits. Returns (bool, reason_string)."""
        self._check_daily_reset(current_time)
        
        # 1. Update High-Water Mark
        if current_balance > self.peak_equity:
            self.peak_equity = current_balance
            
        # 2. Check Profit Target (Finish line)
        current_profit = current_balance - self.initial_balance
        if current_profit >= self.target_profit:
            return False, f"TARGET REACHED! Profit ${current_profit:.2f} >= Goal ${self.target_profit:.2f}"
            
        # 3. Check Overall Drawdown
        if current_balance <= self.overall_loss_floor:
            return False, f"MAX DRAWDOWN! Balance ${current_balance:.2f} <= Floor ${self.overall_loss_floor:.2f}"
            
        # 4. Check Daily Loss Limit
        if self.daily_loss_accumulator <= -self.daily_loss_limit:
            return False, f"DAILY LIMIT! Loss ${abs(self.daily_loss_accumulator):.2f} hit limit of ${self.daily_loss_limit:.2f}"
            
        return True, "Allowed"

    def calculate_lots(self, account_balance, risk_amount, stop_distance, contract_size=100, min_lots=0.01):
        """
        Precise lot sizing with multi-level safety filters. 
        Returns (lots, risk_percent, should_skip, reason).
        """
        if stop_distance <= 0:
            return 0.0, 0.0, True, "Invalid Stop (0)"
            
        # Math: Lots = Risk_Amount / (Distance * Contract_Size)
        raw_lots = risk_amount / (stop_distance * contract_size)
        
        # 1. Apply Constraints
        final_lots = max(raw_lots, min_lots)
        final_lots = min(final_lots, self.max_lots)
        final_lots = round(final_lots, 2)
        
        # 2. Re-calculate actual risk for verification
        actual_risk_amount = final_lots * stop_distance * contract_size
        actual_risk_percent = (actual_risk_amount / account_balance) * 100
        
        # 3. Validation Logic
        should_skip = False
        reason = "OK"
        
        # If the minimum possible lot size (0.01) still risks too much (1.5x tolerance), ABORT.
        if actual_risk_amount > (risk_amount * 1.5):
            should_skip = True
            reason = f"Risk too high (${actual_risk_amount:.2f} > limit ${risk_amount:.2f})"
        elif final_lots == self.max_lots:
            reason = "MAX LOTS reached (Safety constraint)"
            
        return final_lots, round(actual_risk_percent, 2), should_skip, reason

    def update_daily_pnl(self, pnl):
        """Updates the daily loss accumulator."""
        self.daily_loss_accumulator += pnl
        self.peak_equity = max(self.peak_equity, self.initial_balance + self.daily_loss_accumulator)
