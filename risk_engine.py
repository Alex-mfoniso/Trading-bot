class RiskEngine:
    def __init__(self, risk_percent=0.01):
        self.risk_percent = risk_percent
        
    def calculate_risk_amount(self, account_balance):
        return account_balance * self.risk_percent
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
        
        # Decide if it's "safe" (e.g. within 3x target risk or below 5% absolute)
        is_high_risk = actual_risk_percent > max(5.0, self.risk_percent * 3 * 100)
        
        return final_lots, round(actual_risk_percent, 2), is_high_risk
