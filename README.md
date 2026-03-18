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

## 📦 Navigation & Setup

### 1. Requirements
*   **Python 3.10+**
*   **MetaTrader 5 Terminal** (running on Windows)
*   Required libs: `pandas`, `numpy`, `MetaTrader5`

### 2. Configure Your Settings
Update the constants in `main.py` or `run_backtest.py`:
- `SYMBOL = "XAUUSD"`
- `RISK_PER_TRADE = 0.01` (1%)
- `SPREAD = 0.20` (Adjust based on your broker's gold spread)

### 3. Running a Backtest
```powershell
python run_backtest.py
```
This will prompt you for:
- Number of bars to test
- Timeframe (M5, M15, H1, etc.)
- Number of strategies to evaluate (1-5)
- Spread adjustment for simulation accuracy

### 4. Running Live/Demo
```powershell
python run_mt5_demo.py
```
*Make sure MT5 allows "Algo Trading" in the terminal settings!*

---

## 🛡 Risk Disclaimer
*Trading Gold (XAUUSD) carries significant risk due to its high volatility. This bot is intended for educational and research purposes. Always test on a Demo account before using real capital.*

---

## 📝 License
MIT License - Created for XAUUSD professional traders.
