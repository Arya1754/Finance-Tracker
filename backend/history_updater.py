import pandas as pd
import yfinance as yf
import logging
from datetime import datetime, timezone
from backend.config import DATA_DIR

logger = logging.getLogger("prediction")

def update_prediction_history():
    history_path = DATA_DIR / "prediction_history.csv"
    if not history_path.exists():
        return
        
    try:
        df = pd.read_csv(history_path)
        updated = False
        
        for idx, row in df.iterrows():
            if pd.isna(row['Actual Price']) or row['Actual Price'] == "":
                ticker = row['Ticker']
                pred_date = row['Date']
                
                # Fetch recent history to find the actual close for that date
                # We fetch a bit of buffer
                stock = yf.Ticker(ticker)
                hist = stock.history(period="5d")
                
                # Convert index to date strings for comparison
                hist.index = hist.index.strftime('%Y-%m-%d')
                
                if pred_date in hist.index:
                    actual_close = hist.loc[pred_date, 'Close']
                    
                    # We also need previous close to determine direction
                    # We can approximate direction correct by checking if prediction direction matches actual direction
                    # Wait, prediction is done today for tomorrow. So pred_date is tomorrow's date?
                    # Ah, in predictor we logged today's date. The prediction was FOR tomorrow.
                    # Let's assume the prediction made on 'Date' is predicting the close of the next trading day.
                    # We need the close on 'Date' (as baseline) and 'Date + 1 trading day' as actual.
                    
                    # To keep it simple: we predicted a price. We compare predicted price with actual_close of the day the prediction was meant for.
                    # If we made prediction on Date T for T+1, then actual price should be the close of T+1.
                    
                    pred_price = float(row['Predicted Price'])
                    actual = float(actual_close)
                    
                    abs_error = abs(pred_price - actual)
                    
                    # Let's just store the actual price and absolute error
                    df.at[idx, 'Actual Price'] = round(actual, 2)
                    df.at[idx, 'Absolute Error'] = round(abs_error, 2)
                    updated = True
                    
        if updated:
            df.to_csv(history_path, index=False)
            logger.info("Prediction history updated with actuals.")
            
    except Exception as e:
        logger.error(f"Error updating prediction history: {e}")
