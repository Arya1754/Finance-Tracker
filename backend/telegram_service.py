import requests
import logging
from datetime import datetime, timezone
import pytz
from backend.config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger("telegram")

def send_telegram_message(message: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logger.error("Telegram credentials not configured.")
        return
        
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        logger.info("Telegram message sent successfully.")
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")

def format_morning_report(predictions: dict, portfolio_summary: dict) -> str:
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    date_str = now.strftime('%d %b %Y')
    time_str = now.strftime('%H:%M IST')
    
    msg = f"━━━━━━━━━━━━━━━━━━\n"
    msg += f"<b>Daily Portfolio Update</b>\n"
    msg += f"{date_str}\n"
    msg += f"━━━━━━━━━━━━━━━━━━\n\n"
    
    for ticker, data in predictions.items():
        name = ticker.replace(".NS", "")
        if name == "GOLDBEES":
            name = "Physical Gold 24K (1g)"
            
        msg += f"<b>{name}</b>\n"
        msg += f"Current: ₹{data['current_price']}\n"
        
        # Calculate yesterday change based on current and previous (which we can approximate or pass from portfolio)
        # Using prediction data
        daily_prof = data.get('yesterday_change_price', 0)
        pct = data.get('yesterday_change_pct', 0)
        arrow = "▲" if daily_prof >= 0 else "▼"
        msg += f"Yesterday: {arrow} ₹{abs(daily_prof):.2f} ({abs(pct):.2f}%)\n"
            
        msg += f"Tomorrow: ₹{data['expected_low']} – ₹{data['expected_high']}\n"
        msg += f"Confidence: {data['confidence']}%\n"
        
        # Historical prediction (could be extracted if we passed it, simplifying here to just what is available)
        if data.get('yesterday_prediction_error') is not None:
            err = data['yesterday_prediction_error']
            correct = "Correct" if data.get('yesterday_direction_correct') else "Incorrect"
            msg += f"Yesterday Prediction: {correct}\n"
            msg += f"Error: ₹{err}\n"
            
        msg += f"Sentiment: {data['sentiment']['label']}\n"
        msg += f"━━━━━━━━━━━━━━━━━━\n\n"
        
    msg += f"<b>Portfolio Summary</b>\n"
    if portfolio_summary.get('total_value', 0) > 0:
        msg += f"Total Value: ₹{portfolio_summary['total_value']:,.2f}\n"
        prof = portfolio_summary['today_profit']
        arrow = "🟢 ▲" if prof >= 0 else "🔴 ▼"
        msg += f"Today's P/L: {arrow} ₹{abs(prof):,.2f}\n"
    
    msg += f"Generated: {time_str}\n"
    msg += f"━━━━━━━━━━━━━━━━━━"
    return msg

def format_volatility_alert(ticker: str, current_price: float, change_pct: float) -> str:
    ist = pytz.timezone('Asia/Kolkata')
    time_str = datetime.now(ist).strftime('%H:%M IST')
    
    sign = "+" if change_pct >= 0 else ""
    icon = "🚀" if change_pct >= 0 else "🩸"
    
    msg = f"⚠️ <b>VOLATILITY ALERT</b> {icon}\n"
    msg += f"<b>{ticker.replace('.NS', '')}</b>\n"
    msg += f"Movement: {sign}{change_pct:.2f}%\n"
    msg += f"Current Price: ₹{current_price}\n"
    msg += f"Time: {time_str}"
    return msg
