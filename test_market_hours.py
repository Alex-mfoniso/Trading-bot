import pandas as pd
from session_engine import SessionEngine

def test_market_hours():
    test_cases = [
        ("2024-03-01 10:00:00", True),  # Friday morning - Open
        ("2024-03-01 22:30:00", False), # Friday night - Closed (Weekend)
        ("2024-03-02 12:00:00", False), # Saturday - Closed
        ("2024-03-03 22:30:00", False), # Sunday night early - Closed
        ("2024-03-03 23:30:00", True),  # Sunday night late - Open
        ("2024-03-04 10:00:00", True),  # Monday morning - Open
        ("2024-03-04 22:30:00", False), # Monday night break - Closed
    ]

    print("--- Running Market Hours Tests ---")
    for ts, expected in test_cases:
        is_open, msg = SessionEngine.get_market_status(ts)
        result = "PASS" if is_open == expected else "FAIL"
        print(f"[{result}] {ts} -> {msg} (Expected: {expected})")

if __name__ == "__main__":
    test_market_hours()
