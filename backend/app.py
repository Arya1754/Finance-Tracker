import logging
import yfinance as yf
from flask import Flask, jsonify
from flask_cors import CORS
from backend.config import TICKERS, DATA_DIR
from backend.portfolio import PortfolioManager
from backend.predictor import EnsemblePredictor
from backend.sentiment import get_news_sentiment
from backend.telegram_service import send_telegram_message, format_morning_report, format_volatility_alert
from backend.history_updater import update_prediction_history

app = Flask(__name__)
CORS(app)
logger = logging.getLogger("app")

portfolio_mgr = PortfolioManager(DATA_DIR / "portfolio.json")

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "version": "1.0.0"}), 200

@app.route('/api/portfolio', methods=['GET'])
def get_portfolio():
    try:
        summary = portfolio_mgr.get_summary()
        return jsonify(summary), 200
    except Exception as e:
        logger.error(f"Portfolio error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/run-morning', methods=['POST'])
def run_morning_job():
    logger.info("Starting morning job...")
    try:
        # 1. Update yesterday's predictions with actuals
        update_prediction_history()
        
        # 2. Get Portfolio Summary
        portfolio_summary = portfolio_mgr.get_summary()
        
        # 3. Generate predictions and sentiment
        predictions = {}
        for ticker in TICKERS:
            predictor = EnsemblePredictor(ticker)
            pred_data = predictor.predict_tomorrow()
            
            if not pred_data:
                continue
                
            sentiment_data = get_news_sentiment(ticker)
            pred_data['sentiment'] = sentiment_data
            
            # Optional: We could read the history here to fetch yesterday's prediction error
            predictions[ticker] = pred_data
            
        # 4. Format and Send Telegram Message
        if predictions:
            message = format_morning_report(predictions, portfolio_summary)
            send_telegram_message(message)
            
        return jsonify({"status": "success", "message": "Morning report generated and sent."}), 200
    except Exception as e:
        logger.error(f"Error in morning job: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/run-volatility', methods=['POST'])
def run_volatility_job():
    logger.info("Starting volatility check...")
    try:
        alerts_sent = []
        for ticker in TICKERS:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="2d")
            if len(hist) < 2:
                continue
                
            prev_close = hist["Close"].iloc[-2]
            current_price = hist["Close"].iloc[-1]
            
            change_pct = ((current_price - prev_close) / prev_close) * 100
            
            # 5% threshold
            if abs(change_pct) >= 5.0:
                msg = format_volatility_alert(ticker, current_price, change_pct)
                send_telegram_message(msg)
                alerts_sent.append(ticker)
                
        return jsonify({"status": "success", "alerts_sent": alerts_sent}), 200
    except Exception as e:
        logger.error(f"Error in volatility job: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)