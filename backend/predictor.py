import pandas as pd
import numpy as np
import yfinance as yf
import joblib
import logging
import csv
from datetime import datetime, timezone
from pathlib import Path
from sklearn.ensemble import RandomForestRegressor, ExtraTreesRegressor, GradientBoostingRegressor
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import mean_absolute_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from backend.indicators import add_technical_indicators
from backend.config import MODELS_DIR, DATA_DIR, PHYSICAL_GOLD_PREMIUM

logger = logging.getLogger("prediction")

class EnsemblePredictor:
    def __init__(self, ticker: str):
        self.ticker = ticker
        self.model_path = MODELS_DIR / f"{ticker}_model.pkl"
        self.history_path = DATA_DIR / "prediction_history.csv"
        self.features = [
            'EMA_20', 'EMA_50', 'SMA_20', 'SMA_50', 'RSI', 'MACD', 'MACD_Signal', 
            'MACD_Histogram', 'ATR', 'Bollinger_Mid', 'Bollinger_Upper', 'Bollinger_Lower', 
            'OBV', 'Rolling_Volatility', 'Volume_Ratio', 'Dist_EMA_20', 'Dist_EMA_50', 
            'Dist_Bollinger_Mid'
        ]
        
    def needs_retraining(self, df: pd.DataFrame) -> bool:
        if not self.model_path.exists():
            return True
            
        try:
            metadata = joblib.load(self.model_path).get("metadata", {})
            last_train_date = metadata.get("last_train_date")
            last_train_samples = metadata.get("n_samples", 0)
            
            if not last_train_date:
                return True
                
            days_since_train = (datetime.now(timezone.utc).date() - last_train_date).days
            if days_since_train >= 7:
                return True
                
            new_samples = len(df) - last_train_samples
            if new_samples >= 10:
                return True
                
            return False
        except Exception as e:
            logger.error(f"Error checking retrain status for {self.ticker}: {e}")
            return True

    def _prepare_data(self) -> pd.DataFrame:
        df = yf.Ticker(self.ticker).history(period="2y")
        if df.empty or len(df) < 60:
            return pd.DataFrame()
            
        if self.ticker == "GOLDBEES.NS":
            df[['Open', 'High', 'Low', 'Close']] = df[['Open', 'High', 'Low', 'Close']] * (100 * PHYSICAL_GOLD_PREMIUM)
            
        df = add_technical_indicators(df)
        
        # Target is next day's return
        df['Target_Return'] = df['Close'].pct_change().shift(-1)
        
        # Drop rows with NaN due to indicators or shift
        df = df.dropna()
        return df

    def train(self, df: pd.DataFrame) -> dict:
        logger.info(f"Training models for {self.ticker}")
        
        X = df[self.features]
        y = df['Target_Return']
        
        # TimeSeriesSplit
        tscv = TimeSeriesSplit(n_splits=5)
        
        rf = RandomForestRegressor(n_estimators=100, random_state=42)
        et = ExtraTreesRegressor(n_estimators=100, random_state=42)
        gb = GradientBoostingRegressor(n_estimators=100, random_state=42)
        
        models = {'rf': rf, 'et': et, 'gb': gb}
        validation_maes = {'rf': [], 'et': [], 'gb': []}
        
        for train_index, test_index in tscv.split(X):
            X_train, X_test = X.iloc[train_index], X.iloc[test_index]
            y_train, y_test = y.iloc[train_index], y.iloc[test_index]
            
            scaler = StandardScaler()
            X_train_scaled = scaler.fit_transform(X_train)
            X_test_scaled = scaler.transform(X_test)
            
            for name, model in models.items():
                model.fit(X_train_scaled, y_train)
                preds = model.predict(X_test_scaled)
                validation_maes[name].append(mean_absolute_error(y_test, preds))

        # Train final models on all data
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        
        for model in models.values():
            model.fit(X_scaled, y)
            
        avg_mae = np.mean([np.mean(validation_maes[m]) for m in models])
        
        model_data = {
            "scaler": scaler,
            "models": models,
            "metadata": {
                "last_train_date": datetime.now(timezone.utc).date(),
                "n_samples": len(df),
                "avg_mae": avg_mae
            }
        }
        joblib.dump(model_data, self.model_path)
        return model_data

    def predict_tomorrow(self) -> dict:
        df = self._prepare_data()
        if df.empty:
            return {}
            
        if self.needs_retraining(df):
            model_data = self.train(df)
        else:
            model_data = joblib.load(self.model_path)
            
        scaler = model_data["scaler"]
        models = model_data["models"]
        avg_mae = model_data["metadata"]["avg_mae"]
        
        # Get latest data point (today's close)
        latest = df.iloc[-1]
        X_latest = pd.DataFrame([latest[self.features]])
        X_scaled = scaler.transform(X_latest)
        
        # Ensemble predictions (Returns)
        preds = [model.predict(X_scaled)[0] for model in models.values()]
        mean_return = np.mean(preds)
        std_return = np.std(preds)  # Agreement among models
        
        current_price = latest['Close']
        
        # Calculate yesterday changes
        prev_close = df.iloc[-2]['Close'] if len(df) > 1 else current_price
        yesterday_change_price = current_price - prev_close
        yesterday_change_pct = (yesterday_change_price / prev_close) * 100 if prev_close != 0 else 0
        
        predicted_price = current_price * (1 + mean_return)
        
        # Expected bounds using ATR
        atr = latest['ATR']
        expected_low = predicted_price - atr
        expected_high = predicted_price + atr
        
        # Confidence Score Calculation (50 to 95)
        # Factors: model agreement (std_return), recent volatility, historical MAE
        recent_vol = latest['Rolling_Volatility']
        
        # Base confidence 75
        confidence = 75.0
        
        # Penalty for high disagreement
        if std_return > 0.02:
            confidence -= 10
        elif std_return < 0.005:
            confidence += 10
            
        # Penalty for high volatility
        if recent_vol > 0.03:
            confidence -= 10
        elif recent_vol < 0.01:
            confidence += 5
            
        # Penalty for high MAE
        if avg_mae > 0.02:
            confidence -= 10
        elif avg_mae < 0.01:
            confidence += 5
            
        confidence = max(50, min(95, confidence))
        
        prediction_result = {
            "current_price": round(current_price, 2),
            "yesterday_change_price": round(yesterday_change_price, 2),
            "yesterday_change_pct": round(yesterday_change_pct, 2),
            "predicted_return": round(mean_return, 4),
            "predicted_price": round(predicted_price, 2),
            "expected_low": round(expected_low, 2),
            "expected_high": round(expected_high, 2),
            "confidence": round(confidence, 1),
            "atr": round(atr, 2)
        }
        
        self._log_prediction(prediction_result)
        return prediction_result
        
    def _log_prediction(self, res: dict):
        # Columns: Date,Ticker,Predicted Price,Actual Price,Absolute Error,Direction Correct,Confidence,Model Version
        today = datetime.now(timezone.utc).date().isoformat()
        row = [
            today,
            self.ticker,
            res["predicted_price"],
            "", # Actual Price updated next day
            "", # Absolute Error updated next day
            "", # Direction Correct updated next day
            res["confidence"],
            "v1.0 Ensemble"
        ]
        
        file_exists = self.history_path.exists()
        
        with open(self.history_path, 'a', newline='') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["Date","Ticker","Predicted Price","Actual Price","Absolute Error","Direction Correct","Confidence","Model Version"])
            writer.writerow(row)