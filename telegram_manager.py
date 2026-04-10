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
            "*Should I execute this trade?* (Reply 'y' or 'n')"
        )
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
                cmd = update["message"]["text"].strip().lower()
                
                if cmd == "/status":
                    self._handle_status(engine)
                elif cmd == "/closeall":
                    self._handle_close_all(engine)
                elif cmd == "/help":
                    self.send_message("*Commands:*\n/status - Check active trades\n/closeall - Close all trades immediately\n/help - Show this message")

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
        count = engine.close_all_trades(reason="Telegram Remote Close")
        self.send_message(f"✅ Closed {count} trade(s).")
