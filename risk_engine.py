class RiskEngine:
    def __init__(self, risk_percent=0.005, fixed_risk_usd=25.0, daily_loss_limit=200.0, max_overall_loss=500.0, initial_balance=5000.0, target_profit=400.0):
        self.risk_percent = risk_percent
        self.fixed_risk_usd = fixed_risk_usd
        self.daily_loss_limit = daily_loss_limit # 4% as per GFT
        self.max_overall_loss = max_overall_loss # 10%
        self.target_profit = target_profit # 8% for Phase 1 ($400)
        self.initial_limit_balance = initial_balance - max_overall_loss # 4500.0
        self.initial_balance = initial_balance
        
        # Trackers
        self.daily_loss_accumulator = 0.0
        
    def calculate_risk_amount(self, account_balance):
        return min(self.fixed_risk_usd, account_balance * self.risk_percent)

    def is_trading_allowed(self, current_balance):
        # 0. Check Profit Target
        current_profit = current_balance - self.initial_balance
        if current_profit >= self.target_profit:
            print(f"🎉 [TARGET REACHED] Profit ${current_profit:.2f} >= Target ${self.target_profit:.2f}. GOAL ACHIEVED!")
            return False
            
        # 1. Check Max Overall Loss
        if current_balance <= self.initial_limit_balance:
            print(f"🛑 [MAX LOSS] Balance ${current_balance:.2f} <= Limit ${self.initial_limit_balance:.2f}. Trading STOPPED.")
            return False
            
        # 2. Check Daily Loss Limit
        if self.daily_loss_accumulator <= -self.daily_loss_limit:
            print(f"🛑 [DAILY LIMIT] Lost ${abs(self.daily_loss_accumulator):.2f} today. Daily limit reached.")
            return False
            
        return True

    def update_daily_pnl(self, pnl):
        self.daily_loss_accumulator += pnl
        
    def reset_daily_pnl(self):
        self.daily_loss_accumulator = 0.0

    def calculate_lots(self, account_balance, risk_amount, stop_distance, contract_size=100, min_lots=0.01):
        if stop_distance == 0:
            return 0, 0, False
            
        raw_lots = risk_amount / (stop_distance * contract_size)
        
        # Determine lot size with min constraint
        final_lots = max(raw_lots, min_lots)
        final_lots = round(final_lots, 2)
        
        # Calculate ACTUAL risk this lot size represents
        actual_risk_amount = final_lots * stop_distance * contract_size
        actual_risk_percent = (actual_risk_amount / account_balance) * 100
        
        # Decide if it's "safe" (Prop firm rule: usually < 1-2% per trade)
        is_high_risk = actual_risk_percent > 2.0
        
        return final_lots, round(actual_risk_percent, 2), is_high_risk
