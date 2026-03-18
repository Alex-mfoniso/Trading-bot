import time
import pandas as pd
from data_layer import DataLayer
from live_engine import LiveDemoEngine

def main():
    print("--- STARTING PHASE 5: LIVE DEMO FORWARD TEST ---")
    
    # 1. Ask for configuration
    try:
        num_strategies = int(input("How many strategies do you want to run? (2-5): "))
        num_strategies = max(1, min(5, num_strategies)) # bounds check
    except ValueError:
        print("Invalid input for strategies. Defaulting to 3.")
        num_strategies = 3
        
    timeframe_input = input("Which timeframe? (M1, M5, M15, M30, H1, H4, D1): ").strip().upper()
    if not timeframe_input:
        timeframe_input = "H1"
        print("Defaulting timeframe to H1.")

    print(f"--- Configuration: {num_strategies} Strategies on {timeframe_input} ---")
    
    # 2. We create some initial warmup data representing the "past"
    dl = DataLayer()
    df_all = dl.generate_synthetic_data(1000)
    
    # We will pretend the first 250 bars are our already-downloaded historical history
    history_df = df_all.iloc[:250].copy()
    
    # The remaining bars will be "streamed" in one by one, simulating a live websocket feed
    live_stream = df_all.iloc[250:].copy()
    
    # Initialize the Paper/Demo Execution Engine
    demo = LiveDemoEngine(initial_balance=10000, risk_per_trade=0.01, num_strategies=num_strategies)
    
    # 3. Start the streaming loop
    print("Connecting to simulated Exchange WebSocket...")
    time.sleep(1)
    
    # To keep the terminal output manageable for the demo, we'll fast forward the stream without explicit sleep 
    # but still process it strictly 1 candle at a time out-of-sample.
    
    for i in range(len(live_stream)):
        new_candle = live_stream.iloc[i].to_dict()
        
        # In real life, on_new_candle would be a callback triggered by websockets
        history_df = demo.on_new_candle(new_candle, history_df)
        
        # Stop early just to show a brief snippet of "live" action
        # In reality, this loop runs forever.
        if i > 100: 
            break
            
    print("\n--- DEMO SESSION DISCONNECTED ---")
    print(f"Final Demo Account Balance: ${demo.balance:.2f}")

if __name__ == "__main__":
    main()
