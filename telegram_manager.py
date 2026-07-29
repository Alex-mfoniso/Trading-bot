import requests
import time
import threading

class TelegramManager:
    def __init__(self, token, chat_id):
        self.token = token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self.last_update_id = 0
        
    def send_message(self, text):
        """Sends a plain text message to the user."""
        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }
        try:
            requests.post(url, json=payload, timeout=5)
        except Exception as e:
            print(f"Telegram Error: {e}")

    def send_signal_alert(self, signal, candle):
        """Sends a high-visibility signal alert with strategy details."""
        msg = (
            "🔔 *NEW SIGNAL DETECTED*\n\n"
            f"📈 *Strategy:* {signal.get('strategy_name', 'Unknown')}\n"
            f"🧭 *Type:* {signal['type'].upper()}\n"
            f"💵 *Entry:* {signal['entry']}\n"
            f"🛑 *SL:* {signal['sl']}\n"
            f"🎯 *TP:* {signal['tp']}\n\n"
            f"📊 *Lots:* {signal.get('calculated_lots', 0.0)} ({signal.get('actual_risk_pct', 0.0)}% Risk)\n"
            f"📉 *HTF Trend:* {signal.get('htf_trend', 'Unknown')}\n"
        )
        warnings = signal.get("warnings", [])
        if warnings:
            msg += "\n⚠️ *WARNINGS:*\n"
            for w in warnings:
                msg += f"- {w}\n"
            msg += "\n*EXECUTE THIS TRADE ANYWAY?* (Reply 'y' or 'n')"
        else:
            msg += "\n*Should I execute this trade?* (Reply 'y' or 'n')"
            
        self.send_message(msg)

    def get_updates(self):
        """Polls Telegram for new messages."""
        url = f"{self.base_url}/getUpdates"
        params = {"offset": self.last_update_id + 1, "timeout": 1}
        try:
            resp = requests.get(url, params=params, timeout=5).json()
            if resp.get("ok"):
                return resp.get("result", [])
        except Exception as e:
            print(f"Telegram Poll Error: {e}")
        return []

    def poll_for_response(self, timeout=60):
        """
        Waits for a 'y' or 'n' response from the user for a trade approval.
        Returns 'y' or 'n' or 'timeout'.
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            updates = self.get_updates()
            for update in updates:
                self.last_update_id = update["update_id"]
                if "message" in update and "text" in update["message"]:
                    text = update["message"]["text"].strip().lower()
                    if text in ['y', 'yes']:
                        return 'y'
                    if text in ['n', 'no']:
                        return 'n'
            time.sleep(1)
        return 'timeout'

    def process_commands(self, engine):
        """
        Checks for systemic commands like /status or /closeall.
        This should be called regularly (e.g. from the heartbeat).
        """
        updates = self.get_updates()
        for update in updates:
            self.last_update_id = update["update_id"]
            if "message" in update and "text" in update["message"]:
                text = update["message"]["text"].strip().lower()
                
                # Check for y/n response for pending decisions
                if text in ['y', 'yes', 'n', 'no']:
                    self._handle_modification_approval(engine, text)
                    continue

                if text == "/status":
                    self._handle_status(engine)
                elif text.startswith("/be"):
                    self._handle_be(engine, text)
                elif text.startswith("/partial"):
                    self._handle_partial(engine, text)
                elif text.startswith("/close"):
                    # Distinguish between /closeall and /close <ticket>
                    if text == "/closeall":
                        self._handle_close_all(engine)
                    else:
                        self._handle_manual_close(engine, text)
                elif text == "/help":
                    self.send_message(
                        "*Advanced Commands:*\n"
                        "/status - Check active trades\n"
                        "/be <ticket> - Move trade to Break-Even\n"
                        "/partial <ticket> <%> - Take partial (e.g. /partial 123 50)\n"
                        "/close <ticket> - Close specific trade\n"
                        "/closeall - Close all trades immediately\n"
                        "/help - Show this message"
                    )

    def _handle_status(self, engine):
        if not engine.active_trades:
            self.send_message("💤 *No active trades.* Searching for signals...")
            return
            
        status_msg = "🕯 *Active Trades Status:*\n\n"
        for t in engine.active_trades.values():
            status_msg += (
                f"ID: `{t.get('mt5_ticket', 'SIM')}`\n"
                f"Type: {t['type'].upper()} | Strategy: {t.get('strategy_name')}\n"
                f"BE: {t.get('be_moved')} | Partial: {t.get('partial_tp_hit')}\n"
                f"SL: {t['sl']} | TP: {t['tp']}\n"
                "------------------\n"
            )
        self.send_message(status_msg)

    def _handle_close_all(self, engine):
        self.send_message("⚠️ *Closing ALL active trades immediately...*")
        count = engine.close_all_trades(reason="Telegram Remote Close All")
        self.send_message(f"✅ Closed {count} trade(s).")

    def _handle_be(self, engine, cmd_text):
        parts = cmd_text.split()
        if len(parts) < 2:
            self.send_message("❌ Usage: `/be <ticket>`")
            return
        
        ticket = parts[1]
        with engine.trade_lock:
            # Check if ticket is in engine.active_trades (it could be string or int)
            t = engine.active_trades.get(ticket) or engine.active_trades.get(int(ticket) if ticket.isdigit() else None)
            
            if not t:
                self.send_message(f"❌ Trade `{ticket}` not found.")
                return
            
            # Use atr for the buffer as engine._modify_trade_sl expects
            atr = t.get("entry_atr", 0)
            if t["type"] == "long":
                new_sl = t["entry_price"] + (atr * 0.1)
            else:
                new_sl = t["entry_price"] - (atr * 0.1)
            
            engine._modify_trade_sl(t, new_sl)
            t["be_moved"] = True
            t["sl"] = new_sl
            self.send_message(f"⚖️ *Break-Even* request sent for Trade `{ticket}`.")

    def _handle_partial(self, engine, cmd_text):
        parts = cmd_text.split()
        if len(parts) < 3:
            self.send_message("❌ Usage: `/partial <ticket> <percent_to_close>`")
            return
            
        ticket = parts[1]
        try:
            percent = float(parts[2]) / 100.0
        except ValueError:
            self.send_message("❌ Invalid percentage.")
            return

        with engine.trade_lock:
            t = engine.active_trades.get(ticket) or engine.active_trades.get(int(ticket) if ticket.isdigit() else None)
            if not t:
                self.send_message(f"❌ Trade `{ticket}` not found.")
                return
            
            engine._partial_close_trade(t, percent, reason="Telegram Manual Partial")
            self.send_message(f"🎯 *Partial Close* ({int(percent*100)}%) requested for Trade `{ticket}`.")

    def _handle_manual_close(self, engine, cmd_text):
        parts = cmd_text.split()
        if len(parts) < 2:
            self.send_message("❌ Usage: `/close <ticket>`")
            return
            
        ticket = parts[1]
        with engine.trade_lock:
            t = engine.active_trades.get(ticket) or engine.active_trades.get(int(ticket) if ticket.isdigit() else None)
            if not t:
                self.send_message(f"❌ Trade `{ticket}` not found.")
                return
            
            # Construct a dummy candle for closure
            # In real execution, _close_active_trade will fetch latest tick if use_mt5 is True
            dummy_candle = {"close": 0} 
            engine._close_active_trade(t, dummy_candle, reason="Telegram Manual Close")
            self.send_message(f"🛑 *Close* request sent for Trade `{ticket}`.")

    def _handle_modification_approval(self, engine, text):
        """Processes a 'y' or 'n' response for the most recent pending modification."""
        approved = text in ['y', 'yes']
        
        with engine.trade_lock:
            if not engine.pending_modifications:
                # self.send_message("❓ *No pending decisions to approve.*")
                return

            # Find the most recent pending modification
            sorted_pending = sorted(
                engine.pending_modifications.items(), 
                key=lambda x: x[1]['request_time'], 
                reverse=True
            )
            
            key, details = sorted_pending[0] # Take the latest one
            ticket = details["ticket"]
            decision_type = details["type"]
            
            # Update the trade's approval state
            t = engine.active_trades.get(ticket) or engine.active_trades.get(int(ticket) if str(ticket).isdigit() else None)
            if t:
                if "approvals" not in t:
                    t["approvals"] = {}
                t["approvals"][decision_type] = approved
                
                status_str = "✅ *Approved*" if approved else "❌ *Rejected*"
                self.send_message(f"{status_str} request for *{decision_type}* on Ticket `{ticket}`.")
                
                # Internal cleanup happens in engine.monitor_active_trade() on next tick
            else:
                self.send_message(f"❌ Trade `{ticket}` for pending decision no longer active.")
                if key in engine.pending_modifications:
                    del engine.pending_modifications[key]
