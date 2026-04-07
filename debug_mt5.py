import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime

def check_mt5():
    if not mt5.initialize():
        print("Initialize failed")
        return

    symbol = "XAUUSD"
    timeframe = mt5.TIMEFRAME_H1
    
    # Check account info
    account_info = mt5.account_info()
    if account_info:
        print(f"Account: {account_info.login}")
        print(f"Equity: {account_info.equity}")
        print(f"Server: {account_info.server}")
    else:
        print("Failed to get account info")

    # Get last 5 closed candles (excluding current one)
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 1, 5)
    if rates is None:
        print("Failed to get rates")
        mt5.shutdown()
        return

    df = pd.DataFrame(rates)
    df['timestamp'] = pd.to_datetime(df['time'], unit='s')
    print("\nLast 5 H1 candles:")
    print(df[['timestamp', 'close', 'tick_volume']])

    # Check terminal time
    terminal_time = mt5.terminal_info()
    if terminal_time:
        print(f"\nTerminal time: {datetime.fromtimestamp(mt5.symbol_info_tick(symbol).time)}")
    
    # Check for active positions
    positions = mt5.positions_get(symbol=symbol)
    if positions:
        print(f"\nActive positions: {len(positions)}")
        for p in positions:
            print(f"  - Ticket: {p.ticket}, Type: {p.type}, Profit: {p.profit}")
    else:
        print("\nNo active positions")

    mt5.shutdown()

if __name__ == "__main__":
    check_mt5()
