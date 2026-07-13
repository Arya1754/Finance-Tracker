import pandas as pd
import numpy as np

def add_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds technical indicators to the DataFrame.
    Expected columns: Open, High, Low, Close, Volume
    """
    df = df.copy()
    
    # EMAs and SMAs
    df['EMA_20'] = df['Close'].ewm(span=20, adjust=False).mean()
    df['EMA_50'] = df['Close'].ewm(span=50, adjust=False).mean()
    df['SMA_20'] = df['Close'].rolling(window=20).mean()
    df['SMA_50'] = df['Close'].rolling(window=50).mean()

    # RSI (14 period)
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # MACD
    ema_12 = df['Close'].ewm(span=12, adjust=False).mean()
    ema_26 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = ema_12 - ema_26
    df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['MACD_Histogram'] = df['MACD'] - df['MACD_Signal']

    # ATR (14 period)
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df['ATR'] = true_range.rolling(window=14).mean()

    # Bollinger Bands (20 period, 2 std dev)
    df['Bollinger_Mid'] = df['Close'].rolling(window=20).mean()
    std_dev = df['Close'].rolling(window=20).std()
    df['Bollinger_Upper'] = df['Bollinger_Mid'] + (std_dev * 2)
    df['Bollinger_Lower'] = df['Bollinger_Mid'] - (std_dev * 2)

    # OBV (On-Balance Volume)
    obv = (np.sign(df['Close'].diff()) * df['Volume']).fillna(0).cumsum()
    df['OBV'] = obv

    # Rolling Volatility (20 period of daily returns)
    df['Daily_Return'] = df['Close'].pct_change()
    df['Rolling_Volatility'] = df['Daily_Return'].rolling(window=20).std()

    # Volume Ratio (Volume / 20 period SMA of Volume)
    df['Volume_SMA_20'] = df['Volume'].rolling(window=20).mean()
    df['Volume_Ratio'] = df['Volume'] / df['Volume_SMA_20']

    # Distances
    df['Dist_EMA_20'] = (df['Close'] - df['EMA_20']) / df['EMA_20']
    df['Dist_EMA_50'] = (df['Close'] - df['EMA_50']) / df['EMA_50']
    df['Dist_Bollinger_Mid'] = (df['Close'] - df['Bollinger_Mid']) / df['Bollinger_Mid']

    # Expected Range (Output requirement)
    df['Expected_High'] = df['Close'] + df['ATR']
    df['Expected_Low'] = df['Close'] - df['ATR']

    return df