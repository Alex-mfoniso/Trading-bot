import pandas as pd

class SessionEngine:
    @staticmethod
    def get_market_status(current_time=None) -> tuple[bool, str]:
        """
        Determines if the XAUUSD market is currently open based on standard UTC hours:
        Open: Sunday 23:00 UTC to Friday 22:00 UTC.
        Daily break: 22:00 - 23:00 UTC.
        """
        if current_time is None:
            current_time = pd.Timestamp.now(tz='UTC')
        else:
            current_time = pd.to_datetime(current_time)
            if current_time.tzinfo is None:
                current_time = current_time.tz_localize('UTC')

        day = current_time.weekday()  # Monday is 0, Sunday is 6
        hour = current_time.hour
        
        # Weekend: Closed from Friday 22:00 to Sunday 23:00 UTC
        if day == 4 and hour >= 22:  # Friday late
            return False, "Market CLOSED (Weekend)"
        if day == 5:  # Saturday
            return False, "Market CLOSED (Weekend)"
        if day == 6 and hour < 23:  # Sunday early
            return False, "Market CLOSED (Weekend)"
            
        # Daily break: 22:00 - 23:00 UTC
        if hour == 22:
            return False, "Market CLOSED (Daily Break)"
            
        return True, "Market OPEN"

    @staticmethod
    def add_sessions(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        
        # Assumes timestamp column exists and is already in UTC 
        df['datetime'] = pd.to_datetime(df['timestamp'])
        hours = df['datetime'].dt.hour
        
        # Standard Forex Sessions (UTC)
        # London Session: 08:00 - 16:00 UTC
        # New York Session: 13:00 - 21:00 UTC
        
        df['is_london'] = (hours >= 8) & (hours < 16)
        df['is_ny'] = (hours >= 13) & (hours < 21)
        
        # High volume/volatility overlap
        df['is_overlap'] = df['is_london'] & df['is_ny']
        
        # We will define our "killzone" as any time during the London or NY session
        df['is_killzone'] = df['is_london'] | df['is_ny']
        
        df.drop(columns=['datetime'], inplace=True, errors='ignore')
        
        return df
