# 🏅 XAUUSD Advanced Backtester & Trading Bot

An institutional-grade algorithmic trading system for **Gold (XAUUSD)**, built with MetaTrader 5 (MT5) integration, multiple strategy layers, and advanced risk management (Partial TP & Trailing Stops).

---

## 🚀 Key Features

*   **MT5 Live/Demo Integration**: Real-time signal execution and position management on MetaTrader 5.
*   **6 Institutional Strategies**: Covering Trend-Following, Mean-Reversion, Breakouts, and HFT Scalping.
*   **Market Regime Detection**: Automatically toggles between Trending and Ranging strategies based on ADX volatility.
*   **Structure Engine (BOS)**: Identifies "Break of Structure" and trend alignment for higher-probability entries.
*   **Advanced Trade Management**: 
    *   **Partial Take-Profit (PTP)**: Closes 50% of the position at 1:1 Risk/Reward.
    *   **Automatic Break-Even**: Move SL to entry as soon as TP1 is hit.
    *   **Trailing Stop**: Move SL dynamically (1.5x ATR) to lock in profits during long runners.
*   **Realistic Backtesting**: Built-in **Spread Simulation** support to account for real broker costs.

---

## 🔗 MetaTrader 5 Connection & Setup

Follow these steps to connect the bot to your MT5 terminal:

### 1. Terminal Configuration
1.  Open your **MetaTrader 5** terminal.
2.  Go to **Tools > Options** (or press `Ctrl+O`).
3.  In the **Expert Advisors** tab:
    *   ✅ Check **"Allow Algo Trading"**.
    *   ✅ Check **"Allow DLL imports"**.
4.  Ensure you are logged into your **Demo or Live account**.
5.  In the **Market Watch**, ensure `XAUUSD` (or your broker's symbol for Gold, e.g., `GOLD`) is visible.

### 2. Python Environment
Ensure you have the MT5 Python library installed:
```bash
pip install MetaTrader5 pandas numpy
```

---

## 🛠 Project Structure

- `main.py`: Main entry point for the application.
- `strategy_engine.py`: Core trading logic (6 specialized strategies).
- `indicator_engine.py`: Vectorized technical indicators (Pandas-based).
- `structure_engine.py`: Market structure and trend-state identification (BOS).
- `backtest_engine.py`: Historical simulation with spread & partial TP.
- `live_engine.py`: Real-time trade management and MT5 bridge.
- `risk_engine.py`: Lot sizing, risk-percent calculation, and safety checks.
- `session_engine.py`: New York & London Killzones and market hour tracking.

---

## 📊 Strategies Included

1.  **EMA Trend Pullback**: Follows long-term trend confirms (50/200 EMA) and enters on value-area retracements.
2.  **Volatility Breakout**: Enters on explosive moves exceeding 20-period highs/lows with high volume.
3.  **Mean Reversion (Range)**: Targets overstretched RSI levels (>70 or <30) during quiet (low ADX) sessions.
4.  **MACD Zero-Line Cross**: High-probability momentum reversal strategy.
5.  **High-Volume Anomaly**: Detects "Smart Money" institutional volume spikes that lead to sustained moves.
6.  **HFT Scalper (M1/M5)**: Ultra-fast trend chaser using EMA 9/21 crossovers and pullbacks.

---

## 📦 How to Use the Bot

### 1. Configure Your Settings
Update the constants in `main.py` or `run_backtest.py`:
- `SYMBOL = "XAUUSD"` (Check if your broker uses `GOLD` instead).
- `RISK_PER_TRADE = 0.01` (Default is 1%).
- `SPREAD = 0.20` (Adjust based on your broker's specific gold spread).

### 2. Running a Backtest
Validate your strategy on historical bars:
```powershell
python run_backtest.py
```
This will prompt you for:
- **Bars to test**: e.g., 5000 for a long history.
- **Timeframe**: M5, M15, H1, etc.
- **Strategies**: 1 to 5 depending on your focus.
- **Spread**: Realistic dollar cost per trade.

### 3. Running Live/Demo Execution
Connect the bot to your MT5 terminal for real-time trading:
```powershell
python run_mt5_demo.py
```
The bot will:
1.  Initialize connection to your running MT5 terminal.
2.  Wait for new candles on the `XAUUSD` chart.
3.  Execute trades based on the selected strategies.
4.  Manage **Partial Take-Profits**, **Break-Even moves**, and **Trailing Stops** automatically.

---

## 🛡 Risk Disclaimer
*Trading Gold (XAUUSD) carries significant risk due to its high volatility. This bot is intended for educational and research purposes. Always test on a Demo account before using real capital.*

---

## 📝 License
MIT License - Created for XAUUSD professional traders.
