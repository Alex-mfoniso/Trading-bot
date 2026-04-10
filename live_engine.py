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
    def __init__(self, initial_balance=5000, risk_per_trade=0.005, num_strategies=3, use_mt5=False, symbol="XAUUSD", ignore_sessions=False, max_trades=2):
        self.strategy_engine = StrategyEngine()
        self.risk_engine = RiskEngine(
            risk_percent=risk_per_trade, 
            fixed_risk_usd=initial_balance * risk_per_trade, 
            daily_loss_limit=150.0, # $150 as per Goat Funded Trader rules
            max_overall_loss=500.0, # 10% as per GFT
            initial_balance=initial_balance,
            target_profit=400.0 # 8% Target for Phase 1
        )
        self.balance = initial_balance
        self.active_trades = {} # Dictionary of active trades keyed by ticket/ID
        self.trade_lock = threading.RLock()
        self.history = []
        self.num_strategies = num_strategies
        self.use_mt5 = use_mt5
        self.symbol = symbol
        self.ignore_sessions = ignore_sessions
        self.max_trades = max_trades
        self.google_sheet_url = None # Set this in run_mt5_demo.py
        self.htf_trend = 0 # 1: Bullish, -1: Bearish, 0: Unknown/Neutral
        self.log_file = "trade_history.csv"
        self._initialize_log()
        
        mode = "MT5 REAL-TIME" if use_mt5 else "LOCAL SIMULATION"
        print(f"[{time.strftime('%H:%M:%S')}] LIVE DEMO INITIALIZED | Mode: {mode} | Balance: {self.balance} | Risk: {risk_per_trade*100}%")

    def on_new_candle(self, new_candle_row, history_df):
        """
        Ingests a new closed candle and triggers signal checks.
        """
        # Append new candle to our rolling history
        if not history_df.empty:
            # Check if this candle is already the last one to avoid duplicates
            if history_df.iloc[-1]['timestamp'] == new_candle_row['timestamp']:
                return history_df
            history_df = pd.concat([history_df, pd.DataFrame([new_candle_row])], ignore_index=True)
        else:
            history_df = pd.DataFrame([new_candle_row])
            
        print(f"[{time.strftime('%H:%M:%S')}] Received new candle. Total rolling history: {len(history_df)} bars.")
        
        # Trigger signal check and trade management
        signal, candle = self._process_latest_state(history_df)
        return history_df, signal, candle

    def _process_latest_state(self, history_df):
        """
        Core logic to manage active trades and look for new signals.
        Returns (signal, candle) if a new trade is recommended, else (None, None).
        """
        # 1. RISK CHECK (Prop Firm Rules)
        allowed, reason = self.risk_engine.is_trading_allowed(self.balance)
        if not allowed:
            # print(f"[{time.strftime('%H:%M:%S')}] 🛑 [ABORTED] {reason}")
            return
        
        if len(history_df) < 250:
            return
            
        window = history_df.tail(250).copy()
        window = IndicatorEngine.add_features(window)
        window = StructureEngine.add_structure(window, left_bars=5, right_bars=5)
        window = SessionEngine.add_sessions(window)

        current_slice = window.tail(200)
        current_candle = current_slice.iloc[-1]

        # 1.5 MTF TREND CHECK
        if self.use_mt5:
            self.htf_trend = self._fetch_htf_trend()
            if self.htf_trend != 0:
                trend_str = "BULLISH 🟢" if self.htf_trend == 1 else "BEARISH 🔴"
                print(f"[{time.strftime('%H:%M:%S')}] HTF TREND (H1): {trend_str}")
        
        # 2. Check for new signals
        signal = self.strategy_engine.check_strategy(current_slice, self.num_strategies, htf_trend=self.htf_trend, ignore_sessions=self.ignore_sessions)
        
        # 3. Handle active trade management
        with self.trade_lock:
            # Create a copy of keys to avoid modification during iteration issues
            tickets = list(self.active_trades.keys())
            for t_id in tickets:
                if t_id in self.active_trades:
                    self.monitor_active_trade(self.active_trades[t_id], current_price_sim=current_candle['close'])

        # 4. Look for new entry
        if len(self.active_trades) >= self.max_trades:
            # print(f"[{time.strftime('%H:%M:%S')}] Max trades ({self.max_trades}) reached. Skipping signal search.")
            return None, None

        if signal:
            # SAME CANDLE FLIP PREVENTION (Per Strategy)
            if self.history:
                last_trade = self.history[-1]
            # SAME STRATEGY PREVENTION
            with self.trade_lock:
                already_running = any(t.get("strategy") == signal["strategy_id"] for t in self.active_trades.values())
                if already_running:
                    # print(f"DEBUG: Already in {signal['strategy_id']}. Skipping duplicate.")
                    return None, None
            
            return signal, current_candle
            
        return None, None

    def heartbeat(self, history_df):
        """
        Call this frequently to ensure the bot isn't 'idle'.
        If no trade is active, it re-checks signals from the last known state.
        """
        signal, candle = self._process_latest_state(history_df)
        return history_df, signal, candle
        
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
        
        # Calculate TP1 (1:1 Risk/Reward)
        tp_1 = entry + (entry - sl) if signal["type"] == "long" else entry - (sl - entry)

        new_trade = {
            "type": signal["type"],
            "entry_price": entry,
            "sl": sl,
            "tp": tp,
            "tp_1": tp_1,
            "lots": lots,
            "initial_lots": lots,
            "accumulated_pnl": 0.0,
            "strategy": strategy_id,
            "strategy_name": signal.get("strategy_name", "Unknown"),
            "priority": signal.get("priority", 10),
            "entry_atr": current_candle.get("atr_14", 0),
            "candle_count": 0,
            "be_moved": False,
            "partial_tp_hit": False,
            "open_time": time.time(), # For 2-minute safety buffer
            "open_candle_time": current_candle.get("timestamp"),
            "open_time_str": time.strftime('%Y-%m-%d %H:%M:%S')
        }

        if self.use_mt5:
            ticket = self._send_mt5_order(signal["type"], lots, sl, tp)
            if not ticket:
                return # Stop if MT5 failed
            # Register as active trade
            new_trade["mt5_ticket"] = ticket
            with self.trade_lock:
                self.active_trades[ticket] = new_trade
            
            print(f"[{time.strftime('%H:%M:%S')}] TRADE ACTIVE | SL: {new_trade['sl']} | TP: {new_trade['tp']} | Ticket: {ticket}")
        else:
            # Simulation Mode
            # Generate a unique ID for simulation
            sim_id = f"SIM_{int(time.time())}_{signal['strategy_id']}"
            new_trade["sim_id"] = sim_id
            with self.trade_lock:
                self.active_trades[sim_id] = new_trade
            print(f"[{time.strftime('%H:%M:%S')}] Simulation Trade Opened: {sim_id}")

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

    def monitor_active_trade(self, t, current_price_sim=None):
        """
        High-frequency monitoring for Partial TP, Trailing Stop, and SL/TP.
        Should be called every few seconds, independent of candle timeframe.
        'current_price_sim' is used in simulation mode to check stops on candle close.
        """
        if not self.use_mt5 and current_price_sim is None: return 
        
        with self.trade_lock:
            if not t:
                return
            
            # Diagnostic: Print status every 30 iterations (approx 30s) to avoid spam
            t["monitor_count"] = t.get("monitor_count", 0) + 1
            is_diag_tick = (t["monitor_count"] % 30 == 0)
    
            # 1. MT5 CHECK (If position closed externally)
            if self.use_mt5 and t.get("mt5_ticket"):
                position = mt5.positions_get(ticket=t["mt5_ticket"])
                if not position:
                    print(f"[{time.strftime('%H:%M:%S')}] MT5 Position {t['mt5_ticket']} closed externally (SL/TP).")
                    self._handle_trade_closure(t, reason="External Close (MT5)")
                    return
                
                # Fetch latest tick for real-time price
                tick = mt5.symbol_info_tick(self.symbol)
                if not tick: return
                
                # SPREAD PROTECTION:
                # Long TPs hit on BID. Short TPs hit on ASK.
                current_price = tick.bid if t["type"] == "long" else tick.ask
                high_price = tick.bid # For Long targets
                low_price = tick.ask # For Short targets
            elif not self.use_mt5 and current_price_sim is not None:
                # SIMULATION MODE
                current_price = current_price_sim
                high_price = current_price # Simplification: use close price
                low_price = current_price 
            else:
                return

            if is_diag_tick:
               profit_pts = (current_price - t['entry_price']) if t['type'] == 'long' else (t['entry_price'] - current_price)
               print(f"[{time.strftime('%H:%M:%S')}] Monitoring Ticket {t.get('mt5_ticket', 'SIM')}: Profit {profit_pts:.2f} | BE: {t.get('be_moved')} | Part: {t.get('partial_tp_hit')}")

        # 1.5 SIMULATION SL/TP CHECK
        if not self.use_mt5:
            is_long = t["type"] == "long"
            hit_sl = (is_long and low_price <= t["sl"]) or (not is_long and high_price >= t["sl"])
            hit_tp = (is_long and high_price >= t["tp"]) or (not is_long and low_price <= t["tp"])
            
            if hit_sl:
                print(f"[{time.strftime('%H:%M:%S')}] 🛑 [SIM] STOP LOSS HIT! Price: {current_price:.2f} | SL: {t['sl']:.2f}")
                self._close_active_trade(t, {"close": t["sl"]}, reason="Stop Loss (Sim)")
                return
            if hit_tp:
                print(f"[{time.strftime('%H:%M:%S')}] 🎯 [SIM] TAKE PROFIT HIT! Price: {current_price:.2f} | TP: {t['tp']:.2f}")
                self._close_active_trade(t, {"close": t["tp"]}, reason="Take Profit (Sim)")
                return

        # 2. SAFETY BUFFER (2-Minute Rule)
        # Skip buffer for simulation if it's based on candle close
        if self.use_mt5:
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
                self._partial_close_trade(t, 0.5, reason="Partial TP")
                t["partial_tp_hit"] = True
                
                # Move to Break-Even immediately
                if not t.get("be_moved", False):
                    new_sl = t["entry_price"] + (atr * 0.1)
                    self._modify_trade_sl(t, new_sl)
                    t["be_moved"] = True
                    t["sl"] = new_sl

            # Break-Even: Move to entry if price > 1 ATR from entry (if not already moved)
            if not t.get("be_moved", False) and profit_points > (atr * 1.0):
                print(f"[{time.strftime('%H:%M:%S')}] [REAL-TIME] MOVE TO BREAK-EVEN! Profit > 1 ATR.")
                new_sl = t["entry_price"] + (atr * 0.1)
                self._modify_trade_sl(t, new_sl)
                t["be_moved"] = True
                t["sl"] = new_sl

            # Trailing Stop: Move SL if price > 1.5 ATR from entry
            if profit_points > (atr * 1.5):
                suggested_sl = current_price - (atr * 1.5)
                if suggested_sl > t["sl"]:
                    print(f"[{time.strftime('%H:%M:%S')}] [REAL-TIME] TRAILING SL! New Long SL: {suggested_sl:.2f}")
                    self._modify_trade_sl(t, suggested_sl)
                    t["sl"] = suggested_sl

        elif t["type"] == "short":
            profit_points = t["entry_price"] - current_price
            
            # Partial TP
            if not t.get("partial_tp_hit", False) and low_price <= t["tp_1"]:
                print(f"[{time.strftime('%H:%M:%S')}] 🎯 [REAL-TIME] PARTIAL TP HIT (Short)! Price: {current_price:.2f} <= TP1: {t['tp_1']:.2f}")
                self._partial_close_trade(t, 0.5, reason="Partial TP")
                t["partial_tp_hit"] = True
                
                if not t.get("be_moved", False):
                    new_sl = t["entry_price"] - (atr * 0.1)
                    self._modify_trade_sl(t, new_sl)
                    t["be_moved"] = True
                    t["sl"] = new_sl

            # Break-Even
            if not t.get("be_moved", False) and profit_points > (atr * 1.0):
                print(f"[{time.strftime('%H:%M:%S')}] [REAL-TIME] MOVE TO BREAK-EVEN! Profit > 1 ATR.")
                new_sl = t["entry_price"] - (atr * 0.1)
                self._modify_trade_sl(t, new_sl)
                t["be_moved"] = True
                t["sl"] = new_sl

            # Trailing Stop
            if profit_points > (atr * 1.5):
                suggested_sl = current_price + (atr * 1.5)
                if suggested_sl < t["sl"]:
                    print(f"[{time.strftime('%H:%M:%S')}] [REAL-TIME] TRAILING SL! New Short SL: {suggested_sl:.2f}")
                    self._modify_trade_sl(t, suggested_sl)
                    t["sl"] = suggested_sl

    def _partial_close_trade(self, t, close_percent, reason=""):
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
            # Simulation: Just add the pnl of the closed portion to accumulated_pnl
            if t["type"] == "long":
                pnl = (t["tp_1"] - t["entry_price"]) * close_lots * 100
            else:
                pnl = (t["entry_price"] - t["tp_1"]) * close_lots * 100
            
            t["accumulated_pnl"] = t.get("accumulated_pnl", 0.0) + pnl
            t["lots"] -= close_lots
            print(f"[{time.strftime('%H:%M:%S')}] [SIM] Partial Close SUCCESS. PnL: ${pnl:.2f}")
            print(f"[{time.strftime('%H:%M:%S')}] Simulation Partial Close: ${pnl:.2f} added. Remaining lots: {t['lots']:.2f}")

    def _modify_trade_sl(self, t, new_sl):
        if not self.use_mt5 or not t.get("mt5_ticket"):
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
        
        current_price = tick.bid if t["type"] == "long" else tick.ask
        
        if t["type"] == "long":
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
            "position": t["mt5_ticket"],
            "sl": float(rounded_sl),
            "tp": float(t["tp"]) # Keep existing TP
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

    def _close_active_trade(self, t, candle, reason=""):
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
            
            # Add previously taken partial profits
            final_pnl += t.get("accumulated_pnl", 0.0)
        
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
        
        # Remove from active trades
        t_id = t.get("mt5_ticket") or t.get("sim_id")
        with self.trade_lock:
            if t_id in self.active_trades:
                del self.active_trades[t_id]

        # Record in history and file
        t["exit_price"] = close_price
        t["pnl"] = final_pnl
        t["exit_reason"] = reason
        t["status"] = status
        self.history.append(t)
        self._log_to_file(t)

    def close_all_trades(self, reason="Manual Bulk Close"):
        """Immediately closes all active positions."""
        with self.trade_lock:
            trades = list(self.active_trades.values())
        
        if not trades:
            return 0
            
        count = 0
        current_tick = mt5.symbol_info_tick(self.symbol) if self.use_mt5 else None
        candle = {"close": current_tick.bid if current_tick and self.use_mt5 else 0}
        
        for t in trades:
            self._close_active_trade(t, candle, reason=reason)
            count += 1
        return count

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

    def _handle_trade_closure(self, t, reason=""):
        """Special handler for trades closed outside the script (e.g. SL hit on server)"""
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
            
        t_id = t.get("mt5_ticket") or t.get("sim_id")
        with self.trade_lock:
            if t_id in self.active_trades:
                del self.active_trades[t_id]

    def recover_active_trade(self, history_df):
        """
        Attempts to find and resume tracking of an existing open position on MT5.
        """
        if not self.use_mt5:
            return

        from datetime import datetime
        print(f"[{time.strftime('%H:%M:%S')}] Checking for existing open positions to recover...")
        
        positions = mt5.positions_get(symbol=self.symbol)
        if positions is None or len(positions) == 0:
            print(f"[{time.strftime('%H:%M:%S')}] No active positions found for {self.symbol}.")
            return

        # Estimate ATR once for all recovered trades
        current_atr = 0
        if len(history_df) >= 200:
            try:
                window = history_df.tail(250).copy()
                window = IndicatorEngine.add_features(window)
                if not window.empty:
                    current_atr = window.iloc[-1].get("atr_14", 0)
            except Exception as e:
                print(f"[{time.strftime('%H:%M:%S')}] Note: Could not calculate dynamic recovery ATR ({e}). Using 0.")

        for target_pos in positions:
            # Reconstruct state
            entry = target_pos.price_open
            sl = target_pos.sl
            tp = target_pos.tp
            trade_type = "long" if target_pos.type == mt5.POSITION_TYPE_BUY else "short"
            
            # Calculate TP1 (1:1 Risk/Reward) if possible
            tp_1 = entry + (entry - sl) if trade_type == "long" else entry - (sl - entry)
            if sl == 0: tp_1 = entry # Safety

            recovered_trade = {
                "type": trade_type,
                "entry_price": entry,
                "sl": sl,
                "tp": tp,
                "tp_1": tp_1,
                "lots": target_pos.volume,
                "initial_lots": target_pos.volume,
                "accumulated_pnl": 0.0,
                "strategy": "Recovered",
                "strategy_name": "Recovered Trade",
                "priority": 10,
                "mt5_ticket": target_pos.ticket,
                "entry_atr": current_atr,
                "candle_count": 0,
                "be_moved": False,
                "partial_tp_hit": False,
                "open_time": target_pos.time, 
                "open_candle_time": None, # Unknown
                "open_time_str": datetime.fromtimestamp(target_pos.time).strftime('%Y-%m-%d %H:%M:%S')
            }
            
            with self.trade_lock:
                self.active_trades[target_pos.ticket] = recovered_trade
            
            print(f"[{time.strftime('%H:%M:%S')}] 🔄 RECOVERED ACTIVE TRADE | Ticket: {target_pos.ticket} | {trade_type.upper()} | Entry: {entry} | SL: {sl}")
