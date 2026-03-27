import pandas as pd
import time
import os
import csv
import MetaTrader5 as mt5
from indicator_engine import IndicatorEngine
from structure_engine import StructureEngine
from session_engine import SessionEngine
from strategy_engine import StrategyEngine
import requests
import json
import threading
from risk_engine import RiskEngine

class LiveDemoEngine:
    def __init__(self, initial_balance=5000, risk_per_trade=0.005, num_strategies=3, use_mt5=False, symbol="XAUUSD"):
        self.strategy_engine = StrategyEngine()
        self.risk_engine = RiskEngine(
            risk_percent=risk_per_trade, 
            fixed_risk_usd=25.0, 
            daily_loss_limit=150.0, # $150 as per Goat Funded Trader rules
            max_overall_loss=500.0, # 10% as per GFT
            initial_balance=initial_balance,
            target_profit=400.0 # 8% Target for Phase 1
        )
        self.balance = initial_balance
        self.active_trade = None
        self.trade_lock = threading.Lock() # Ensure real-time monitor and candle loop don't fight
        self.history = []
        self.num_strategies = num_strategies
        self.use_mt5 = use_mt5
        self.symbol = symbol
        self.google_sheet_url = None # Set this in run_mt5_demo.py
        self.htf_trend = 0 # 1: Bullish, -1: Bearish, 0: Unknown/Neutral
        self.log_file = "trade_history.csv"
        self._initialize_log()
        
        mode = "MT5 REAL-TIME" if use_mt5 else "LOCAL SIMULATION"
        print(f"[{time.strftime('%H:%M:%S')}] LIVE DEMO INITIALIZED | Mode: {mode} | Balance: {self.balance} | Risk: {risk_per_trade*100}%")

    def on_new_candle(self, new_candle_row, history_df):
        """
        Simulates receiving a closed 1H candle from a Websocket or REST API
        """
        # Append new candle to our rolling history
        if not history_df.empty:
            history_df = pd.concat([history_df, pd.DataFrame([new_candle_row])], ignore_index=True)
        else:
            history_df = pd.DataFrame([new_candle_row])
            
        print(f"[{time.strftime('%H:%M:%S')}] Received new candle. Total rolling history: {len(history_df)} bars.")
        
        # 1. RISK CHECK (Prop Firm Rules)
        allowed, reason = self.risk_engine.is_trading_allowed(self.balance)
        if not allowed:
            print(f"[{time.strftime('%H:%M:%S')}] 🛑 [ABORTED] {reason}")
            return history_df
        
        # We need a decent chunk of history to compute 200 EMA and structure comfortably
        if len(history_df) < 250: # Adjusted from 250 to 200 for current_slice, but 250 is safer for full indicators
            return history_df
            
        # For 1H bars, recomputing columns on a rolling 250-bar window takes ms.
        # Ensure we have enough data for indicators and structure
        window = history_df.tail(250).copy() # Use a larger window for indicator calculation
        window = IndicatorEngine.add_features(window)
        window = StructureEngine.add_structure(window, left_bars=5, right_bars=5)
        window = SessionEngine.add_sessions(window)

        current_slice = window.tail(200) # Use a smaller, processed slice for strategy checks
        current_candle = current_slice.iloc[-1]

        # 1.5 MTF TREND CHECK (Fetching H1 trend from MT5 if enabled)
        if self.use_mt5:
            self.htf_trend = self._fetch_htf_trend()
            if self.htf_trend != 0:
                trend_str = "BULLISH 🟢" if self.htf_trend == 1 else "BEARISH 🔴"
                print(f"[{time.strftime('%H:%M:%S')}] HTF TREND (H1): {trend_str}")
        
        # 2. Check for new signals ALWAYS (even if trade is active, for opposite signals)
        signal = self.strategy_engine.check_strategy(current_slice, self.num_strategies, htf_trend=self.htf_trend)
         # 3. If trade is active, manage it
        if self.active_trade:
            self.active_trade["candle_count"] = self.active_trade.get("candle_count", 0) + 1
            
            # CHECK FOR OPPOSITE SIGNAL EXIT (Sensible check)
            if signal:
                is_opposite = (self.active_trade["type"] == "long" and signal["type"] == "short") or \
                               (self.active_trade["type"] == "short" and signal["type"] == "long")
                
                if is_opposite:
                    # PRIORITY LOGIC:
                    # Only flip if it's the SAME strategy OR a higher priority strategy (lower priority number)
                    current_priority = self.active_trade.get("priority", 10)
                    new_priority = signal.get("priority", 10)
                    
                    should_flip = (signal["strategy_id"] == self.active_trade["strategy"]) or (new_priority < current_priority)
                    
                    if should_flip:
                        # Check elapsed time for safety (2-minute rule)
                        elapsed_seconds = time.time() - self.active_trade.get("open_time", 0)
                        if elapsed_seconds > 120:
                            print(f"[{time.strftime('%H:%M:%S')}] OPPOSITE SIGNAL DETECTED ({signal.get('strategy_name')})! Closing current {self.active_trade['type']} to flip.")
                            self._close_active_trade(current_candle, reason="Opposite Signal (High Priority)")
                            # After closing, we can immediately open the new signal
                            self._execute_trade(signal, current_candle)
                            return history_df
                        else:
                            print(f"[{time.strftime('%H:%M:%S')}] Opposite signal ignored (Trade < 2 mins old).")
                    else:
                        print(f"[{time.strftime('%H:%M:%S')}] Opposite signal ignored (Low priority: {signal.get('strategy_name')}).")

            # 3. Check for SL/TP on active trade (Thread-safe)
        with self.trade_lock:
            # Real-time monitoring for SL/TP/Partial TP (Independent of candle close)
            # This is now handled by the background thread, but we check here too for safety
            self.monitor_active_trade()
            return history_df

        # 4. Check for existing trade
        with self.trade_lock:
            if self.active_trade:
                return history_df
                
            # 4. If no trade is active, look for new entry
            if signal:
                # SAME CANDLE FLIP PREVENTION
                if self.history:
                    last_trade = self.history[-1]
                    if last_trade.get("open_candle_time") == current_candle.get("timestamp"):
                        print(f"[{time.strftime('%H:%M:%S')}] Entry skipped: Already traded on this candle.")
                        return history_df
                        
                self._execute_trade(signal, current_candle)
            
        return history_df
        
    def _execute_trade(self, signal, current_candle):
        entry = signal["entry"]
        sl = signal["sl"]
        tp = signal["tp"]
        strategy_id = signal.get("strategy_id", "Unknown")
        
        risk_amount = self.risk_engine.calculate_risk_amount(self.balance)
        stop_distance = abs(entry - sl)
        
        if stop_distance == 0:
            return
            
        # 3. Liquidity Check (Tick Volume should be > 50% of Average)
        vol_avg = current_candle.get("volume_avg", 0)
        curr_vol = current_candle.get("volume", 0)
        if vol_avg > 0 and curr_vol < (vol_avg * 0.5):
             print(f"[{time.strftime('%H:%M:%S')}] 🛑 [ABORTED] Low liquidity! Vol: {curr_vol} < 50% of Avg ({vol_avg:.0f})")
             return
             
        # 4. DYNAMIC RISK SCALING
        adx = current_candle.get("adx", 0)
        risk_multiplier = 1.0 # Standard
        
        if adx > 40:
            risk_multiplier = 1.5 # High Confidence Trend
            print(f"[{time.strftime('%H:%M:%S')}] 🔥 DYNAMIC RISK: High ADX ({adx:.1f}). Increasing risk to 1.5x.")
        elif adx < 25:
            risk_multiplier = 0.5 # Low Confidence / Chop
            print(f"[{time.strftime('%H:%M:%S')}] 💤 DYNAMIC RISK: Low ADX ({adx:.1f}). Reducing risk to 0.5x.")
        
        adjusted_risk_amount = risk_amount * risk_multiplier
        
        # Smarter Lot Calculation
        lots, actual_risk_pct, should_skip, reason = self.risk_engine.calculate_lots(self.balance, adjusted_risk_amount, stop_distance)
        
        if should_skip:
            print(f"[{time.strftime('%H:%M:%S')}] 🛑 [ABORTED] {reason}")
            return
            
        final_risk_amount = (actual_risk_pct / 100) * self.balance
        is_high_risk = actual_risk_pct > 2.0
        
        # Log detailed strategy breakdown
        print("\n" + "="*50)
        print(f"[{time.strftime('%H:%M:%S')}] 🚀 NEW TRADE EXECUTED")
        print(f"Strategy:    {signal.get('strategy_name', 'Unknown')}")
        print(f"Logic:       {signal.get('description', 'No description available')}")
        print(f"Trigger:     {signal.get('trigger_details', 'No details')}")
        print(f"Expectation: {signal.get('expectation', 'No expectation')}")
        print("-"*50)
        print(f"Order:       {signal['type'].upper()} | Lots: {lots:.2f} | @ {entry:.2f}")
        print(f"Stops:       SL: {sl:.2f} | TP: {tp:.2f}")
        print("="*50 + "\n")

        # Execute on MT5 if enabled
        ticket = None
        if self.use_mt5:
            ticket = self._send_mt5_order(signal["type"], lots, sl, tp)
            if not ticket:
                return # Stop if MT5 failed

        # Calculate TP1 (1:1 Risk/Reward)
        tp_1 = entry + (entry - sl) if signal["type"] == "long" else entry - (sl - entry)

        self.active_trade = {
            "type": signal["type"],
            "entry_price": entry,
            "sl": sl,
            "tp": tp,
            "tp_1": tp_1,
            "lots": lots,
            "initial_lots": lots, # Keep the original size for logging
            "strategy": strategy_id,
            "strategy_name": signal.get("strategy_name", "Unknown"),
            "priority": signal.get("priority", 10),
            "mt5_ticket": ticket,
            "entry_atr": current_candle.get("atr_14", 0),
            "candle_count": 0,
            "be_moved": False,
            "partial_tp_hit": False,
            "open_time": time.time(), # For 2-minute safety buffer
            "open_candle_time": current_candle.get("timestamp"),
            "open_time_str": time.strftime('%Y-%m-%d %H:%M:%S')
        }
        
        print(f"[{time.strftime('%H:%M:%S')}] TRADE ACTIVE | SL: {sl:.2f} | TP: {tp:.2f} | Ticket: {ticket}")
        if is_high_risk:
            print(f"[{time.strftime('%H:%M:%S')}] [WARNING] High risk trade detected!")

    def _send_mt5_order(self, order_type, lots, sl, tp):
        """
        Sends a real market order to MetaTrader 5 with proper rounding and safety checks.
        """
        symbol_info = mt5.symbol_info(self.symbol)
        if symbol_info is None:
            print(f"[{time.strftime('%H:%M:%S')}] Symbol {self.symbol} not found!")
            return None
            
        if not symbol_info.visible:
            if not mt5.symbol_select(self.symbol, True):
                print(f"[{time.strftime('%H:%M:%S')}] Symbol {self.symbol} selection failed!")
                return None

        # 1. Detect Filling Mode
        # Some brokers use FOK (1), some use IOC (2), some use RETURN
        # We use explicit bit values because some MT5 Python versions lack the constants
        filling_mode = mt5.ORDER_FILLING_IOC
        if symbol_info.filling_mode & 1: # SYMBOL_FILLING_FOK
            filling_mode = mt5.ORDER_FILLING_FOK
        elif symbol_info.filling_mode & 2: # SYMBOL_FILLING_IOC
            filling_mode = mt5.ORDER_FILLING_IOC
        else:
            filling_mode = mt5.ORDER_FILLING_RETURN

        # 2. Rounding and Precision
        digits = symbol_info.digits
        tick_size = symbol_info.trade_tick_size
        
        def round_to_tick(val):
            return round(round(val / tick_size) * tick_size, digits)

        mt5_order_type = mt5.ORDER_TYPE_BUY if order_type == "long" else mt5.ORDER_TYPE_SELL
        tick = mt5.symbol_info_tick(self.symbol)
        
        # 2.5 Spread Gate Protection
        spread_points = symbol_info.spread
        max_allowed_spread = 35 # 3.5 pips on Gold is the "efficiency" limit
        if spread_points > max_allowed_spread:
            print(f"[{time.strftime('%H:%M:%S')}] 🛑 [ABORTED] High Spread: {spread_points} > {max_allowed_spread} max! Market too expensive.")
            return None

        price = tick.ask if order_type == "long" else tick.bid
        
        # 3. Check Stop Level (Minimum Distance)
        stop_level = symbol_info.trade_stops_level * symbol_info.point
        vol_step = symbol_info.volume_step
        
        if order_type == "long":
            if sl > price - stop_level:
                sl = price - stop_level - (symbol_info.point * 10) # Force a safe distance
            if tp < price + stop_level:
                tp = price + stop_level + (symbol_info.point * 10)
        else:
            if sl < price + stop_level:
                sl = price + stop_level + (symbol_info.point * 10)
            if tp > price - stop_level:
                tp = price - stop_level - (symbol_info.point * 10)

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.symbol,
            "volume": float(round(round(lots / vol_step) * vol_step, 2)),
            "type": mt5_order_type,
            "price": float(round_to_tick(price)),
            "sl": 0.0, # Market execution requires 0.0 initially
            "tp": 0.0, # Market execution requires 0.0 initially
            "deviation": 20,
            "magic": 123456,
            "comment": "Antigravity Bot",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling_mode,
        }
        
        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            print(f"[{time.strftime('%H:%M:%S')}] MT5 MARKET ORDER FAILED! Error code: {result.retcode} | Comment: {result.comment}")
            return None
        
        ticket = result.order
        print(f"[{time.strftime('%H:%M:%S')}] MT5 POSITION OPENED! Ticket: {ticket}. Adding SL/TP now...")

        # 4. Step 2: Add SL/TP
        # We need to wait a tiny bit or just send the modify request
        modify_request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": self.symbol,
            "position": ticket,
            "sl": float(round_to_tick(sl)),
            "tp": float(round_to_tick(tp))
        }
        
        modify_result = mt5.order_send(modify_request)
        if modify_result.retcode != mt5.TRADE_RETCODE_DONE:
            print(f"[{time.strftime('%H:%M:%S')}] MT5 SL/TP MODIFICATION FAILED! Error code: {modify_result.retcode} | Comment: {modify_result.comment}")
            # We still return the ticket because the position IS open!
        else:
            print(f"[{time.strftime('%H:%M:%S')}] MT5 SL/TP ADDED SUCCESSFULLY to Ticket: {ticket}")

        return ticket

    def monitor_active_trade(self):
        """
        High-frequency monitoring for Partial TP, Trailing Stop, and SL/TP.
        Should be called every few seconds, independent of candle timeframe.
        """
        if not self.use_mt5: return # No ticks in simulation mode
        
        with self.trade_lock:
            t = self.active_trade
            if not t:
                return
    
            # 1. MT5 CHECK (If position closed externally)
            if t.get("mt5_ticket"):
                position = mt5.positions_get(ticket=t["mt5_ticket"])
                if not position:
                    print(f"[{time.strftime('%H:%M:%S')}] MT5 Position {t['mt5_ticket']} closed externally (SL/TP).")
                    self._handle_trade_closure(reason="External Close (MT5)")
                    return
                
                # Fetch latest tick for real-time price
                tick = mt5.symbol_info_tick(self.symbol)
                if not tick: return
                
                # SPREAD PROTECTION:
                # Long TPs hit on BID. Short TPs hit on ASK.
                current_price = tick.bid if t["type"] == "long" else tick.ask
                high_price = tick.bid # For Long targets
                low_price = tick.ask # For Short targets
            else:
                return

        # 2. SAFETY BUFFER (2-Minute Rule)
        elapsed_seconds = time.time() - t["open_time"]
        if elapsed_seconds < 120:
             return

        atr = t.get("entry_atr", 0)

        # 3. PARTIAL TAKE-PROFIT & BREAK-EVEN & TRAILING STOP LOGIC
        if t["type"] == "long":
            profit_points = current_price - t["entry_price"]
            
            # Partial TP: Close 50% at 1:1 R:R
            if not t.get("partial_tp_hit", False) and high_price >= t["tp_1"]:
                print(f"[{time.strftime('%H:%M:%S')}] 🎯 [REAL-TIME] PARTIAL TP HIT (Long)! Price: {current_price:.2f} >= TP1: {t['tp_1']:.2f}")
                self._partial_close_trade(0.5, reason="Partial TP")
                t["partial_tp_hit"] = True
                
                # Move to Break-Even immediately
                if not t.get("be_moved", False):
                    new_sl = t["entry_price"] + (atr * 0.1)
                    self._modify_trade_sl(new_sl)
                    t["be_moved"] = True
                    t["sl"] = new_sl

            # Break-Even: Move to entry if price > 1 ATR from entry (if not already moved)
            if not t.get("be_moved", False) and profit_points > (atr * 1.0):
                print(f"[{time.strftime('%H:%M:%S')}] [REAL-TIME] MOVE TO BREAK-EVEN! Profit > 1 ATR.")
                new_sl = t["entry_price"] + (atr * 0.1)
                self._modify_trade_sl(new_sl)
                t["be_moved"] = True
                t["sl"] = new_sl

            # Trailing Stop: Move SL if price > 1.5 ATR from entry
            if profit_points > (atr * 1.5):
                suggested_sl = current_price - (atr * 1.5)
                if suggested_sl > t["sl"]:
                    print(f"[{time.strftime('%H:%M:%S')}] [REAL-TIME] TRAILING SL! New Long SL: {suggested_sl:.2f}")
                    self._modify_trade_sl(suggested_sl)
                    t["sl"] = suggested_sl

        elif t["type"] == "short":
            profit_points = t["entry_price"] - current_price
            
            # Partial TP
            if not t.get("partial_tp_hit", False) and low_price <= t["tp_1"]:
                print(f"[{time.strftime('%H:%M:%S')}] 🎯 [REAL-TIME] PARTIAL TP HIT (Short)! Price: {current_price:.2f} <= TP1: {t['tp_1']:.2f}")
                self._partial_close_trade(0.5, reason="Partial TP")
                t["partial_tp_hit"] = True
                
                if not t.get("be_moved", False):
                    new_sl = t["entry_price"] - (atr * 0.1)
                    self._modify_trade_sl(new_sl)
                    t["be_moved"] = True
                    t["sl"] = new_sl

            # Break-Even
            if not t.get("be_moved", False) and profit_points > (atr * 1.0):
                print(f"[{time.strftime('%H:%M:%S')}] [REAL-TIME] MOVE TO BREAK-EVEN! Profit > 1 ATR.")
                new_sl = t["entry_price"] - (atr * 0.1)
                self._modify_trade_sl(new_sl)
                t["be_moved"] = True
                t["sl"] = new_sl

            # Trailing Stop
            if profit_points > (atr * 1.5):
                suggested_sl = current_price + (atr * 1.5)
                if suggested_sl < t["sl"]:
                    print(f"[{time.strftime('%H:%M:%S')}] [REAL-TIME] TRAILING SL! New Short SL: {suggested_sl:.2f}")
                    self._modify_trade_sl(suggested_sl)
                    t["sl"] = suggested_sl

    def _partial_close_trade(self, close_percent, reason=""):
        t = self.active_trade
        if not t: return

        close_lots = t["lots"] * close_percent
        # Ensure minimum lot size (0.01)
        close_lots = max(0.01, round(close_lots, 2))
        
        if self.use_mt5 and t.get("mt5_ticket"):
            # Close Partial on MT5
            ticket = t["mt5_ticket"]
            pos = mt5.positions_get(ticket=ticket)
            if pos:
                p = pos[0]
                type_dict = {mt5.ORDER_TYPE_BUY: mt5.ORDER_TYPE_SELL, mt5.ORDER_TYPE_SELL: mt5.ORDER_TYPE_BUY}
                request = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": self.symbol,
                    "volume": float(close_lots),
                    "type": type_dict[p.type],
                    "position": ticket,
                    "price": mt5.symbol_info_tick(self.symbol).bid if p.type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(self.symbol).ask,
                    "deviation": 20,
                    "magic": 123456,
                    "comment": f"Partial: {reason}",
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": mt5.ORDER_FILLING_IOC,
                }
                res = mt5.order_send(request)
                if res.retcode == mt5.TRADE_RETCODE_DONE:
                    print(f"[{time.strftime('%H:%M:%S')}] MT5 Partial Close ({close_lots} lots) SUCCESS.")
                    # Update local state
                    t["lots"] -= close_lots
                else:
                    print(f"[{time.strftime('%H:%M:%S')}] MT5 Partial Close FAILED! Code: {res.retcode}")
        else:
            # Simulation: Just add the pnl of the closed portion to balance
            if t["type"] == "long":
                pnl = (t["tp_1"] - t["entry_price"]) * close_lots * 100
            else:
                pnl = (t["entry_price"] - t["tp_1"]) * close_lots * 100
            
            self.balance += pnl
            t["lots"] -= close_lots
            print(f"[{time.strftime('%H:%M:%S')}] Simulation Partial Close: ${pnl:.2f} added. Remaining lots: {t['lots']:.2f}")

    def _modify_trade_sl(self, new_sl):
        if not self.use_mt5 or not self.active_trade.get("mt5_ticket"):
            return
            
        # Round new_sl properly
        symbol_info = mt5.symbol_info(self.symbol)
        if not symbol_info: return
        tick_size = symbol_info.trade_tick_size
        digits = symbol_info.digits
        rounded_sl = round(round(new_sl / tick_size) * tick_size, digits)

        # 3. Check Stop Level (Minimum Distance) + SAFETY BUFFER
        tick = mt5.symbol_info_tick(self.symbol)
        # We use a 2x Stop Level or 35 Points minimum buffer to avoid 10013
        stop_level_pts = max(symbol_info.trade_stops_level, 35) 
        stop_level = stop_level_pts * symbol_info.point
        
        current_price = tick.bid if self.active_trade["type"] == "long" else tick.ask
        
        if self.active_trade["type"] == "long":
            if rounded_sl > current_price - stop_level:
                # print(f"DEBUG: Skipping SL {rounded_sl}. Too close to {current_price} (Buffer: {stop_level})")
                return 
        else:
            if rounded_sl < current_price + stop_level:
                # print(f"DEBUG: Skipping SL {rounded_sl}. Too close to {current_price} (Buffer: {stop_level})")
                return 

        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": self.symbol,
            "position": self.active_trade["mt5_ticket"],
            "sl": float(rounded_sl),
            "tp": float(self.active_trade["tp"]) # Keep existing TP
        }
        res = mt5.order_send(request)
        if res.retcode != mt5.TRADE_RETCODE_DONE:
            print(f"[{time.strftime('%H:%M:%S')}] FAILED TO MODIFY SL! Code: {res.retcode}")

    def _get_mt5_pnl(self, ticket):
        """Fetches the real dollar profit for a specific position from MT5 history."""
        if not self.use_mt5: return 0.0
        
        # Give MT5 a second to process the final deal
        time.sleep(1)
        
        # Positions in MT5 are tied to a "Position ID", which for a single trade
        # is the ticket of the original opening order.
        deals = mt5.history_deals_get(position=ticket)
        if deals:
            total_profit = sum(d.profit + d.commission + d.swap for d in deals)
            return total_profit
        
        # Fallback: Searching by ticket if Position ID fails
        history_deals = mt5.history_deals_get(ticket=ticket)
        if history_deals:
             return sum(d.profit + d.commission + d.swap for d in history_deals)

        return 0.0

    def _close_active_trade(self, candle, reason=""):
        t = self.active_trade
        if not t: return

        close_price = candle["close"]
        final_pnl = 0.0
        
        if self.use_mt5 and t.get("mt5_ticket"):
            # Close on MT5
            ticket = t["mt5_ticket"]
            pos = mt5.positions_get(ticket=ticket)
            if pos:
                p = pos[0]
                type_dict = {mt5.ORDER_TYPE_BUY: mt5.ORDER_TYPE_SELL, mt5.ORDER_TYPE_SELL: mt5.ORDER_TYPE_BUY}
                request = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": self.symbol,
                    "volume": p.volume,
                    "type": type_dict[p.type],
                    "position": ticket,
                    "price": mt5.symbol_info_tick(self.symbol).bid if p.type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(self.symbol).ask,
                    "deviation": 20,
                    "magic": 123456,
                    "comment": f"Close: {reason}",
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": mt5.ORDER_FILLING_IOC,
                }
                res = mt5.order_send(request)
                if res.retcode == mt5.TRADE_RETCODE_DONE:
                    print(f"[{time.strftime('%H:%M:%S')}] MT5 Trade {ticket} closed via script.")
                else:
                    print(f"[{time.strftime('%H:%M:%S')}] FAILED TO CLOSE MT5 Trade {ticket}! Code: {res.retcode}")

            # Fetch Real PnL
            final_pnl = self._get_mt5_pnl(ticket)
        else:
            # Update Balance (Simulation)
            if t["type"] == "long":
                final_pnl = (close_price - t["entry_price"]) * t["lots"] * 100
            else:
                final_pnl = (t["entry_price"] - close_price) * t["lots"] * 100
        
        # Determine Status
        status = "PROFIT ✅" if final_pnl > 0.01 else "LOSS ❌"
        if abs(final_pnl) <= 0.01: status = "BREAK-EVEN ⚖️"
        elif t.get("be_moved") and final_pnl > -0.01: status = "BREAK-EVEN ⚖️"
        
        # Update Daily Tracker
        self.risk_engine.update_daily_pnl(final_pnl)
        
        # Log Detailed Outcome
        print("\n" + "="*50)
        print(f"🏁 TRADE CLOSED: {t.get('strategy_name', 'Strat ' + str(t.get('strategy', '?')))}")
        print(f"Result:      {status}")
        print(f"Total PnL:   {'+' if final_pnl > 0 else ''}${final_pnl:.2f}")
        print(f"Exit Reason: {reason}")
        print("-"*50)
        
        self.balance += final_pnl
        print(f"New Balance: ${self.balance:.2f} | Today: ${self.risk_engine.daily_loss_accumulator:+.2f}")
        print("="*50 + "\n")

        # Record in history and file
        t["exit_price"] = close_price
        t["pnl"] = final_pnl
        t["exit_reason"] = reason
        t["status"] = status
        self.history.append(t)
        self._log_to_file(t)

        self.active_trade = None

    def _fetch_htf_trend(self):
        """Fetches last 50 H1 bars from MT5 and calculates the trend state."""
        if not self.use_mt5: return 0
        
        # Fetch H1 rates
        rates = mt5.copy_rates_from_pos(self.symbol, mt5.TIMEFRAME_H1, 0, 50)
        if rates is None or len(rates) < 20:
            return 0
            
        df_h1 = pd.DataFrame(rates)
        # We only need a basic trend check for efficiency
        # Using 50-period EMA on H1 as the trend filter
        df_h1['ema_50'] = df_h1['close'].ewm(span=50, adjust=False).mean()
        
        current_close = df_h1['close'].iloc[-1]
        ema_50 = df_h1['ema_50'].iloc[-1]
        
        if current_close > ema_50:
            return 1 # Bullish
        elif current_close < ema_50:
            return -1 # Bearish
        return 0

    def _initialize_log(self):
        """Creates the trade_history.csv file with headers if it doesn't already exist."""
        if not os.path.exists(self.log_file):
            with open(self.log_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "Open_Time", "Ticket", "Strategy", "Type", "Lots", "Entry", "SL", "TP", 
                    "Exit_Time", "Exit_Price", "PnL", "Result", "Exit_Reason"
                ])
                
    def _log_to_file(self, t):
        """Appends a finished trade's record to the CSV file and sends to Google Sheets if configured."""
        try:
            # 1. Local CSV Log
            with open(self.log_file, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    t.get("open_time_str", "N/A"),
                    t.get("mt5_ticket", "SIM"),
                    t.get("strategy_name", "Unknown"),
                    t.get("type", "N/A").upper(),
                    f"{t.get('initial_lots', t.get('lots', 0.0)):.2f}",
                    f"{t.get('entry_price', 0.0):.2f}",
                    f"{t.get('sl', 0.0):.2f}",
                    f"{t.get('tp', 0.0):.2f}",
                    time.strftime('%Y-%m-%d %H:%M:%S'),
                    f"{t.get('exit_price', 0.0):.2f}",
                    f"{t.get('pnl', 0.0):.2f}",
                    t.get("status", "N/A"),
                    t.get("exit_reason", "N/A")
                ])
            
            # 2. Google Sheets Online Log
            if self.google_sheet_url:
                self._log_to_google_sheets(t)
                
        except Exception as e:
            print(f"Error logging to file/cloud: {e}")

    def _log_to_google_sheets(self, t):
        """Sends trade data to a Google Sheets Webhook (Apps Script)."""
        if not self.google_sheet_url: return
        
        data = {
            "Open_Time": t.get("open_time_str", "N/A"),
            "Ticket": str(t.get("mt5_ticket", "SIM")),
            "Strategy": t.get("strategy_name", "Unknown"),
            "Type": t.get("type", "N/A").upper(),
            "Lots": round(t.get("lots", 0.0), 2),
            "Entry": round(t.get("entry_price", 0.0), 2),
            "SL": round(t.get("sl", 0.0), 2),
            "TP": round(t.get("tp", 0.0), 2),
            "Exit_Time": time.strftime('%Y-%m-%d %H:%M:%S'),
            "Exit_Price": round(t.get("exit_price", 0.0), 2),
            "PnL": round(t.get("pnl", 0.0), 2),
            "Result": t.get("status", "N/A"),
            "Exit_Reason": t.get("exit_reason", "N/A")
        }
        
        try:
            # We use a POST request to send the data to the Google Apps Script Web App
            response = requests.post(self.google_sheet_url, json=data, timeout=10)
            if response.status_code == 200:
                print(f"[{time.strftime('%H:%M:%S')}] ☁️ Trade synced to Google Sheets Online.")
            else:
                print(f"[{time.strftime('%H:%M:%S')}] ☁️ Failed to sync to Google Sheets. Code: {response.status_code}")
        except Exception as e:
            print(f"[{time.strftime('%H:%M:%S')}] ☁️ Error syncing to Google Sheets: {e}")

    def _handle_trade_closure(self, reason=""):
        """Special handler for trades closed outside the script (e.g. SL hit on server)"""
        t = self.active_trade
        if not t: return
        
        if self.use_mt5 and t.get("mt5_ticket"):
            final_pnl = self._get_mt5_pnl(t["mt5_ticket"])
            # Determine status
            status = "PROFIT ✅" if final_pnl > 0.01 else "LOSS ❌"
            if abs(final_pnl) <= 0.01: status = "BREAK-EVEN ⚖️"
            t["status"] = status
            t["exit_price"] = 0.0 # Unknown exactly if closed externally without more work
            t["exit_reason"] = reason
            
            self._log_to_file(t)
            
            self.risk_engine.update_daily_pnl(final_pnl)
            self.balance += final_pnl
            print(f"[{time.strftime('%H:%M:%S')}] External Trade Closed. PnL: ${final_pnl:.2f} | Reason: {reason}")
            
        self.active_trade = None
