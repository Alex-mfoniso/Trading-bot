import time

class StrategyEngine:
    def check_strategy(self, current_slice, num_strategies=5):
        if len(current_slice) < 2:
            return None
            
        current_candle = current_slice.iloc[-1]
        in_session = current_candle.get("is_killzone", True)
        
        if not in_session:
            return None

        adx = current_candle.get("adx", 0)
        
        # Define market regime
        is_trending = adx > 25
        is_ranging = adx < 20
        
        # Order strategies based on current market regime
        if is_trending:
            # Trending: Trend Follow -> Breakout -> Scalper -> MACD -> Vol Anomaly
            strategy_order = [
                (self._strategy_1_ema_trend, 1),
                (self._strategy_2_breakout, 2),
                (self._strategy_6_scalping, 6),
                (self._strategy_4_macd_cross, 4),
                (self._strategy_5_volume_anomaly, 5)
            ]
        elif is_ranging:
            # Ranging: Mean Reversion -> MACD -> Vol Anomaly
            strategy_order = [
                (self._strategy_3_mean_reversion, 3),
                (self._strategy_4_macd_cross, 4),
                (self._strategy_5_volume_anomaly, 5)
            ]
        else:
            # Transitioning/Neutral: MACD -> EMA Trend -> Breakout -> Vol Anomaly
            strategy_order = [
                (self._strategy_4_macd_cross, 4),
                (self._strategy_1_ema_trend, 1),
                (self._strategy_2_breakout, 2),
                (self._strategy_5_volume_anomaly, 5),
                (self._strategy_6_scalping, 6)
            ]

        # Execute selected strategies
        for strat_func, strat_id in strategy_order:
            # Skip if strat_id is beyond requested limit
            if strat_id > num_strategies and strat_id != 6:
                continue
                
            signal = strat_func(current_candle, current_slice)
            if signal:
                signal["strategy_id"] = strat_id
                return signal
                
        return None

    def _strategy_1_ema_trend(self, candle, slice):
        adx = candle.get("adx", 0)
        trend_state = candle.get("trend_state", 0) # 1 = Bullish structure, -1 = Bearish
        
        if adx < 25:
            return None

        trend_up = candle["ema_50"] > candle["ema_200"] and trend_state >= 0
        trend_down = candle["ema_50"] < candle["ema_200"] and trend_state <= 0
        
        if trend_up:
            if candle["low"] <= candle["ema_50"] and candle["close"] > candle["ema_50"]:
                entry = candle["close"]
                sl = candle["low"] - candle["atr_14"] * 2.0
                bp = entry - sl
                tp = entry + bp * 2.0
                return {
                    "type": "long", "entry": entry, "sl": sl, "tp": tp, "strategy_id": 1,
                    "strategy_name": "EMA Trend Pullback",
                    "description": "Follows the long-term trend (EMA 50/200 & Structure) and enters when price dips to the EMA 50 'value area'.",
                    "trigger_details": f"Bullish Trend | EMA 50 Dip | ADX: {adx:.1f} | Structure: {trend_state}",
                    "expectation": "Expect price to find support at the EMA 50 and resume the main uptrend."
                }
                
        elif trend_down:
            if candle["high"] >= candle["ema_50"] and candle["close"] < candle["ema_50"]:
                entry = candle["close"]
                sl = candle["high"] + candle["atr_14"] * 2.0
                bp = sl - entry
                tp = entry - bp * 2.0
                return {
                    "type": "short", "entry": entry, "sl": sl, "tp": tp, "strategy_id": 1,
                    "strategy_name": "EMA Trend Pullback",
                    "description": "Follows the long-term downtrend (EMA 50/200 & Structure) and enters when price rallies to the EMA 50 'value area'.",
                    "trigger_details": f"Bearish Trend | EMA 50 Rally | ADX: {adx:.1f} | Structure: {trend_state}",
                    "expectation": "Expect price to find resistance at the EMA 50 and resume the main downtrend."
                }
        return None

    def _strategy_2_breakout(self, candle, slice):
        adx = candle.get("adx", 0)
        trend_state = candle.get("trend_state", 0)
        
        if adx < 25:
            return None

        prev_candle = slice.iloc[-2]
        vol_check = candle["volume"] > candle["volume_avg"]
        
        if candle["close"] > prev_candle["highest_20"] and trend_state >= 0:
            if vol_check:
                entry = candle["close"]
                sl = candle["low"] - candle["atr_14"] * 2.0
                bp = entry - sl
                tp = entry + bp * 2.0
                return {
                    "type": "long", "entry": entry, "sl": sl, "tp": tp, "strategy_id": 2,
                    "strategy_name": "Volatility Breakout",
                    "description": "Enters when price breaks above a 20-period high with strong volume and trend alignment.",
                    "trigger_details": f"High Breakout | Volume > Avg | ADX: {adx:.1f} | Structure: {trend_state}",
                    "expectation": "Expect a fast, explosive continuation as momentum buyers enter."
                }
            
        elif candle["close"] < prev_candle["lowest_20"] and trend_state <= 0:
            if vol_check:
                entry = candle["close"]
                sl = candle["high"] + candle["atr_14"] * 2.0
                bp = sl - entry
                tp = entry - bp * 2.0
                return {
                    "type": "short", "entry": entry, "sl": sl, "tp": tp, "strategy_id": 2,
                    "strategy_name": "Volatility Breakout",
                    "description": "Enters when price breaks below a 20-period low with strong volume and trend alignment.",
                    "trigger_details": f"Low Breakout | Volume > Avg | ADX: {adx:.1f} | Structure: {trend_state}",
                    "expectation": "Expect a fast drop as support breaks."
                }
        return None

    def _strategy_3_mean_reversion(self, candle, slice):
        adx = candle.get("adx", 50)
        if adx > 20:
            return None
            
        rsi = candle["rsi_14"]
        if rsi < 30:
            if candle["low"] <= candle["bb_lower"] and candle["close"] > candle["bb_lower"]:
                entry = candle["close"]
                sl = candle["low"] - candle["atr_14"] * 2.0
                tp = entry + (entry - sl) * 2.0
                return {
                    "type": "long", "entry": entry, "sl": sl, "tp": tp, "strategy_id": 3,
                    "strategy_name": "Mean Reversion (Range)",
                    "description": "Enters when price is 'overstretched' to the downside (RSI < 30) in a quiet market.",
                    "trigger_details": f"RSI Oversold ({rsi:.1f}) | Lower BB Tag",
                    "expectation": "Expect price to 'snap back' to the balance point."
                }
        elif rsi > 70:
            if candle["high"] >= candle["bb_upper"] and candle["close"] < candle["bb_upper"]:
                entry = candle["close"]
                sl = candle["high"] + candle["atr_14"] * 2.0
                tp = entry - (sl - entry) * 2.0
                return {
                    "type": "short", "entry": entry, "sl": sl, "tp": tp, "strategy_id": 3,
                    "strategy_name": "Mean Reversion (Range)",
                    "description": "Enters when price is 'overstretched' to the upside (RSI > 70) in a quiet market.",
                    "trigger_details": f"RSI Overbought ({rsi:.1f}) | Upper BB Tag",
                    "expectation": "Expect sellers to step in."
                }
        return None

    def _strategy_4_macd_cross(self, candle, slice):
        prev_candle = slice.iloc[-2]
        macd_val = candle["macd_line"]
        sig_val = candle["macd_signal"]
        prev_macd = prev_candle["macd_line"]
        prev_sig = prev_candle["macd_signal"]
        
        if macd_val > sig_val and prev_macd <= prev_sig:
            if macd_val < 0:
                entry = candle["close"]
                sl = candle["low"] - candle["atr_14"] * 2.0
                tp = entry + (entry - sl) * 2
                return {
                    "type": "long", "entry": entry, "sl": sl, "tp": tp, "strategy_id": 4,
                    "strategy_name": "MACD Zero-Line Cross",
                    "description": "Enters when the MACD line crosses above its signal line while below zero.",
                    "trigger_details": "Bullish MACD Cross | Below 0 Line",
                    "expectation": "Expect a slow but steady reversal."
                }
        elif macd_val < sig_val and prev_macd >= prev_sig:
            if macd_val > 0:
                entry = candle["close"]
                sl = candle["high"] + candle["atr_14"] * 2.0
                tp = entry - (sl - entry) * 2
                return {
                    "type": "short", "entry": entry, "sl": sl, "tp": tp, "strategy_id": 4,
                    "strategy_name": "MACD Zero-Line Cross",
                    "description": "Enters when the MACD line crosses below its signal line while above zero.",
                    "trigger_details": "Bearish MACD Cross | Above 0 Line",
                    "expectation": "Expect price to roll over."
                }
        return None

    def _strategy_5_volume_anomaly(self, candle, slice):
        is_anomaly = candle["volume"] > (candle["volume_avg"] * 2.5)
        if is_anomaly:
            body_size = abs(candle["close"] - candle["open"])
            if body_size > (candle["atr_14"] * 0.5):
                entry = candle["close"]
                if candle["close"] > candle["open"]:
                    sl = candle["low"] - candle["atr_14"] * 2.0
                    tp = entry + (entry - sl) * 2.0
                    return {
                        "type": "long", "entry": entry, "sl": sl, "tp": tp, "strategy_id": 5,
                        "strategy_name": "High-Volume Anomaly",
                        "description": "Detects unusual institution-sized volume that pushes price strongly.",
                        "trigger_details": f"Volume Anomaly ({candle['volume']/candle['volume_avg']:.1f}x) | Bullish Body",
                        "expectation": "Expect 'Smart Money' to continue pushing the price."
                    }
                else:
                    sl = candle["high"] + candle["atr_14"] * 2.0
                    tp = entry - (sl - entry) * 2.0
                    return {
                        "type": "short", "entry": entry, "sl": sl, "tp": tp, "strategy_id": 5,
                        "strategy_name": "High-Volume Anomaly",
                        "description": "Detects unusual institution-sized volume that pushes price strongly.",
                        "trigger_details": f"Volume Anomaly ({candle['volume']/candle['volume_avg']:.1f}x) | Bearish Body",
                        "expectation": "Expect heavy selling pressure to persist."
                    }
        return None

    def _strategy_6_scalping(self, candle, slice):
        ema_9 = candle.get("ema_9")
        ema_21 = candle.get("ema_21")
        if ema_9 is None or ema_21 is None:
            return None
        bullish_trend = ema_9 > ema_21
        bearish_trend = ema_9 < ema_21
        
        if bullish_trend:
            if candle["low"] < ema_9 and candle["close"] > ema_9:
                entry = candle["close"]
                sl = candle["low"] - candle["atr_14"] * 2.0
                tp = entry + (entry - sl) * 2.0
                return {
                    "type": "long", "entry": entry, "sl": sl, "tp": tp, "strategy_id": 6,
                    "strategy_name": "HFT Scalper (M1/M5)",
                    "description": "A high-speed chaser that enters on small pullbacks to the fast EMA 9.",
                    "trigger_details": "EMA 9/21 Bullish | Pullback to 9",
                    "expectation": "Expect a quick surge for a small profit."
                }
        elif bearish_trend:
            if candle["high"] > ema_9 and candle["close"] < ema_9:
                entry = candle["close"]
                sl = candle["high"] + candle["atr_14"] * 2.0
                tp = entry - (sl - entry) * 2.0
                return {
                    "type": "short", "entry": entry, "sl": sl, "tp": tp, "strategy_id": 6,
                    "strategy_name": "HFT Scalper (M1/M5)",
                    "description": "A high-speed chaser that enters on small rallies back to the EMA 9.",
                    "trigger_details": "EMA 9/21 Bearish | Pullback to 9",
                    "expectation": "Expect price to drop quickly."
                }
        return None
