import csv
import requests
import json
import time

# --- CONFIGURATION ---
# Replace with your Google Apps Script URL from run_mt5_demo.py
GOOGLE_SHEET_URL = "https://script.google.com/macros/s/AKfycbxvq6KZHwPozEWr2OHtFj1-W0cLtME3g_KiCyA6u05Ya0KQK56wqrmj_oxR-SsnL-Odug/exec"
CSV_FILE = "trade_history.csv"

def sync_logs():
    print(f"[{time.strftime('%H:%M:%S')}] STARTING LOG SYNC TO GOOGLE SHEETS...")
    
    try:
        with open(CSV_FILE, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            count = 0
            for row in reader:
                # Map CSV headers to the JSON format expected by the Google Apps Script
                # (CSV headers: Open_Time, Ticket, Strategy, Type, Lots, Entry, SL, TP, Exit_Time, Exit_Price, PnL, Result, Exit_Reason)
                
                # Use a standard browser User-Agent to avoid being blocked header
                headers = {"User-Agent": "Mozilla/5.0"}
                
                try:
                    # Send row to Google Sheets
                    response = requests.post(GOOGLE_SHEET_URL, json=row, headers=headers, timeout=10)
                    if response.status_code == 200:
                        count += 1
                        # We wait a tiny bit to avoid hitting rate limits if there are many rows
                        time.sleep(0.5)
                    else:
                        print(f"Failed to sync row. Status: {response.status_code}")
                except Exception as e:
                    print(f"Error syncing row: {e}")
                    
            print(f"\n[{time.strftime('%H:%M:%S')}] SYNC COMPLETE! {count} trades uploaded to your Online Sheet.")
            
    except FileNotFoundError:
        print(f"Error: {CSV_FILE} not found. No local logs to sync.")
    except Exception as e:
        print(f"Error reading CSV: {e}")

if __name__ == "__main__":
    sync_logs()
