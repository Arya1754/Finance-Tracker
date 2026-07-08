import argparse
import logging
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests
import yfinance as yf
from flask import Flask, jsonify
from flask_cors import CORS
from sklearn.metrics import mean_absolute_error
from sklearn.ensemble import RandomForestRegressor
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv()

IST = ZoneInfo("Asia/Kolkata")
TICKERS = ["BANDHANBNK.NS", "ADANIPOWER.NS", "WSTCSTPAPR.NS", "ZOTA.NS", "POONAWALLA.NS", "GOLDBEES.NS"]
PHYSICAL_GOLD_PREMIUM = 1.127

logger = logging.getLogger("finance-tracker")
nlp_analyzer = SentimentIntensityAnalyzer()

app = Flask(__name__)
CORS(app)


@dataclass(frozen=True)
class AppConfig:
    telegram_token: str
    telegram_chat_id: str
    debug: bool = False
    port: int = 5000


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def load_config() -> AppConfig:
    telegram_token = os.getenv("TELEGRAM_TOKEN")
    telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not telegram_token or not telegram_chat_id:
        raise RuntimeError("Missing TELEGRAM_TOKEN or TELEGRAM_CHAT_ID environment variables.")

    return AppConfig(
        telegram_token=telegram_token,
        telegram_chat_id=telegram_chat_id,
        debug=os.getenv("FLASK_DEBUG", "0") == "1",
        port=int(os.getenv("PORT", "5000")),
    )


def is_market_window(now: datetime | None = None) -> bool:
    current_time = now or datetime.now(IST)
    if current_time.weekday() >= 5:
        return False

    open_time = current_time.replace(hour=9, minute=30, second=0, microsecond=0)
    close_time = current_time.replace(hour=15, minute=30, second=0, microsecond=0)
    return open_time <= current_time <= close_time


def send_mobile_alert(message: str, config: AppConfig, max_attempts: int = 3) -> bool:
    if not message.strip():
        logger.warning("Skipped Telegram send because the message was empty.")
        return False

    url = f"https://api.telegram.org/bot{config.telegram_token}/sendMessage"
    chunks = [message[i : i + 3500] for i in range(0, len(message), 3500)] or [message]

    for index, chunk in enumerate(chunks, start=1):
        payload = {
            "chat_id": config.telegram_chat_id,
            "text": chunk,
            "parse_mode": "HTML",
        }

        last_error = None
        for attempt in range(1, max_attempts + 1):
            try:
                response = requests.post(url, json=payload, timeout=15)
                if response.ok:
                    logger.info("Sent Telegram chunk %s/%s.", index, len(chunks))
                    last_error = None
                    break

                last_error = f"HTTP {response.status_code}: {response.text}"
                logger.warning("Telegram send failed on attempt %s/%s: %s", attempt, max_attempts, last_error)
            except Exception as exc:  # pragma: no cover - network dependent
                last_error = str(exc)
                logger.warning("Telegram send exception on attempt %s/%s: %s", attempt, max_attempts, exc)

            if attempt < max_attempts:
                time.sleep(2 * attempt)

        if last_error is not None:
            logger.error("Unable to send Telegram chunk %s/%s after retries: %s", index, len(chunks), last_error)
            return False

    return True


def safe_history(ticker: str, period: str = "6mo") -> pd.DataFrame:
    try:
        return yf.Ticker(ticker).history(period=period)
    except Exception as exc:
        logger.exception("Failed to load history for %s: %s", ticker, exc)
        return pd.DataFrame()


def get_news_sentiment_score(ticker: str) -> float:
    try:
        stock = yf.Ticker(ticker)
        news = stock.news or []

        total_score = 0.0
        article_count = 0

        for article in news:
            title = article.get("title", "")
            if not title:
                continue

            total_score += nlp_analyzer.polarity_scores(title)["compound"]
            article_count += 1

        if article_count == 0:
            return 0.0

        return float(total_score / article_count)
    except Exception as exc:
        logger.warning("News sentiment failed for %s: %s", ticker, exc)
        return 0.0


def translate_score_to_label(score: float) -> str:
    if score >= 0.15:
        return "Bullish 📈"
    if score <= -0.15:
        return "Bearish 📉"
    return "Neutral ⚖️"


def build_prediction_frame(history_data: pd.DataFrame) -> pd.DataFrame:
    frame = history_data.copy()

    frame["Close"] = pd.to_numeric(frame["Close"], errors="coerce")
    frame = frame.dropna(subset=["Close"])

    frame["Return_1D"] = frame["Close"].pct_change()
    frame["Return_3D"] = frame["Close"].pct_change(3)
    frame["Return_5D"] = frame["Close"].pct_change(5)
    frame["SMA_5"] = frame["Close"].rolling(window=5).mean()
    frame["SMA_10"] = frame["Close"].rolling(window=10).mean()
    frame["SMA_20"] = frame["Close"].rolling(window=20).mean()
    frame["VOL_5"] = frame["Return_1D"].rolling(window=5).std()
    frame["VOL_10"] = frame["Return_1D"].rolling(window=10).std()
    frame["Close_to_SMA_5"] = frame["Close"] / frame["SMA_5"] - 1.0
    frame["Close_to_SMA_20"] = frame["Close"] / frame["SMA_20"] - 1.0

    if "Volume" in frame.columns:
        volume_series = pd.to_numeric(frame["Volume"], errors="coerce")
        frame["Volume"] = volume_series
        frame["Volume_Change"] = frame["Volume"].pct_change()
        frame["Volume_SMA_5"] = frame["Volume"].rolling(window=5).mean()
        frame["Volume_Ratio"] = frame["Volume"] / frame["Volume_SMA_5"] - 1.0
    else:
        frame["Volume_Change"] = 0.0
        frame["Volume_Ratio"] = 0.0

    if {"High", "Low"}.issubset(frame.columns):
        high_series = pd.to_numeric(frame["High"], errors="coerce")
        low_series = pd.to_numeric(frame["Low"], errors="coerce")
        frame["Intraday_Range"] = (high_series - low_series) / frame["Close"]
    else:
        frame["Intraday_Range"] = 0.0

    # PREDICT RETURNS INSTEAD OF ABSOLUTE PRICE
    frame["Target_Return"] = frame["Close"].pct_change().shift(-1)
    
    # Replace infinities, but DO NOT dropna yet!
    frame = frame.replace([np.inf, -np.inf], np.nan)
    return frame


def predict_tomorrow(history_data: pd.DataFrame, sentiment_score: float = 0.0) -> float | None:
    try:
        if history_data is None or history_data.empty or len(history_data) < 45 or "Close" not in history_data:
            return None

        df = build_prediction_frame(history_data)
        
        feature_cols = [
            "Return_1D", "Return_3D", "Return_5D", 
            "Close_to_SMA_5", "Close_to_SMA_20", 
            "VOL_5", "VOL_10", 
            "Volume_Change", "Volume_Ratio", "Intraday_Range"
        ]

        # Isolate the very last row for TOMORROW'S prediction
        df_features_clean = df.dropna(subset=feature_cols)
        if len(df_features_clean) < 30:
            return None
            
        latest_features = df_features_clean[feature_cols].iloc[-1].values.reshape(1, -1)
        current_close = df_features_clean["Close"].iloc[-1]

        # Prepare Training Data (Drop the last row because its target is NaN)
        train_df = df_features_clean.dropna(subset=["Target_Return"])
        
        x_values = train_df[feature_cols].values
        y_values = train_df["Target_Return"].values

        split_index = max(int(len(train_df) * 0.8), 10)
        train_x, train_y = x_values[:split_index], y_values[:split_index]
        validation_x, validation_y = x_values[split_index:], y_values[split_index:]

        model = RandomForestRegressor(
            n_estimators=100, 
            random_state=42, 
            n_jobs=-1, 
            min_samples_leaf=5, 
            max_depth=5
        )
        model.fit(train_x, train_y)

        if len(validation_x) > 0:
            model_validation_prediction = model.predict(validation_x)
            baseline_validation_prediction = np.zeros_like(validation_y) 
            
            model_mae = mean_absolute_error(validation_y, model_validation_prediction)
            baseline_mae = mean_absolute_error(validation_y, baseline_validation_prediction)

            if model_mae >= baseline_mae * 1.02:
                logger.info("Using naive fallback (0% return) for prediction.")
                return round(float(current_close), 2)

        base_return_prediction = model.predict(latest_features)[0]
        fused_return = base_return_prediction + (sentiment_score * 0.005) 
        predicted_price = current_close * (1.0 + fused_return)

        return round(float(predicted_price), 2)
        
    except Exception as exc:
        logger.exception("Machine learning calculation failed: %s", exc)
        return None


def normalize_prices(ticker: str, current_price: float, yesterday_price: float, predicted_price: float | None) -> tuple[float, float, float | None, str, str]:
    if ticker == "GOLDBEES.NS":
        current_price = (current_price * 100) * PHYSICAL_GOLD_PREMIUM
        yesterday_price = (yesterday_price * 100) * PHYSICAL_GOLD_PREMIUM
        predicted_price = (predicted_price * 100) * PHYSICAL_GOLD_PREMIUM if predicted_price is not None else None
        return current_price, yesterday_price, predicted_price, "GOLD (24K)", "Neutral ⚖️"

    return current_price, yesterday_price, predicted_price, ticker.replace(".NS", ""), ""


def build_asset_snapshot(ticker: str) -> dict:
    try:
        hist = safe_history(ticker, "6mo")
        if hist.empty or len(hist) < 2:
            return {
                "status": "error",
                "ticker": ticker,
                "display_name": ticker.replace(".NS", ""),
                "message": "No historical data",
            }

        current_price = float(hist["Close"].iloc[-1])
        yesterday_price = float(hist["Close"].iloc[-2])
        if not np.isfinite(current_price) or not np.isfinite(yesterday_price):
            raise ValueError("Invalid price data received")

        sentiment_val = 0.0 if ticker == "GOLDBEES.NS" else get_news_sentiment_score(ticker)
        sentiment_label = translate_score_to_label(sentiment_val)
        predicted_price = predict_tomorrow(hist, sentiment_score=sentiment_val)

        current_price, yesterday_price, predicted_price, display_name, gold_sentiment_override = normalize_prices(
            ticker,
            current_price,
            yesterday_price,
            predicted_price,
        )

        if gold_sentiment_override:
            sentiment_label = gold_sentiment_override

        actual_diff = current_price - yesterday_price
        actual_pct_change = (actual_diff / yesterday_price) * 100 if yesterday_price else 0.0

        if predicted_price is not None and current_price:
            predicted_pct_change = ((predicted_price - current_price) / current_price) * 100
            prediction_text = f"₹{predicted_price:,.2f} ({'🚀' if predicted_pct_change >= 0 else '📉'} {predicted_pct_change:+.2f}%)"
        else:
            prediction_text = "Calculations Unavailable ⚠️"

        return {
            "status": "success",
            "ticker": ticker,
            "display_name": display_name,
            "price": round(current_price, 2),
            "yesterday_price": round(yesterday_price, 2),
            "actual_diff": round(actual_diff, 2),
            "actual_pct_change": round(actual_pct_change, 2),
            "prediction": round(predicted_price, 2) if predicted_price is not None else None,
            "prediction_text": prediction_text,
            "sentiment_label": sentiment_label,
            "asset_type": "commodity" if ticker == "GOLDBEES.NS" else "equity",
        }
    except Exception as exc:
        logger.exception("Snapshot failed for %s: %s", ticker, exc)
        return {
            "status": "error",
            "ticker": ticker,
            "display_name": ticker.replace(".NS", ""),
            "message": str(exc),
        }


def build_daily_report() -> tuple[str, int, int]:
    lines = ["🌅 <b>Good Morning! Here is your Daily Portfolio Briefing:</b>", ""]
    success_count = 0
    failure_count = 0

    for ticker in TICKERS:
        snapshot = build_asset_snapshot(ticker)
        if snapshot["status"] != "success":
            failure_count += 1
            lines.append(f"⚠️ <b>{escape(snapshot['display_name'])}</b>")
            lines.append(f"Status: {escape(snapshot['message'])}")
            lines.append("------------------------")
            continue

        success_count += 1
        actual_emoji = "🟢" if snapshot["actual_pct_change"] >= 0 else "🔴"
        lines.append(f"🏦 <b>{escape(snapshot['display_name'])}</b>")
        lines.append(f"Current Price : ₹{snapshot['price']:,.2f}")
        lines.append(
            f"Yesterday Price Difference : {snapshot['actual_diff']:+.2f} ({actual_emoji} {snapshot['actual_pct_change']:+.2f}%)"
        )
        lines.append(f"AI Predicts   : {snapshot['prediction_text']}")
        lines.append(f"Market News   : {escape(snapshot['sentiment_label'])}")
        lines.append("------------------------")

    lines.append("")
    lines.append(f"Generated at {datetime.now(IST):%Y-%m-%d %H:%M %Z}")
    return "\n".join(lines), success_count, failure_count


def build_volatility_report() -> tuple[str | None, int]:
    if not is_market_window():
        logger.info("Skipping volatility scan outside the Indian market window.")
        return None, 0

    alert_lines = ["🚨 <b>Volatility Watch</b> 🚨", ""]
    alert_count = 0

    for ticker in TICKERS:
        try:
            hist = safe_history(ticker, "2d")
            if len(hist) < 2:
                logger.warning("Skipping %s because only %s rows were returned.", ticker, len(hist))
                continue

            current_price = float(hist["Close"].iloc[-1])
            yesterday_price = float(hist["Close"].iloc[-2])
            if not np.isfinite(current_price) or not np.isfinite(yesterday_price):
                continue

            if ticker == "GOLDBEES.NS":
                current_price = (current_price * 100) * PHYSICAL_GOLD_PREMIUM
                yesterday_price = (yesterday_price * 100) * PHYSICAL_GOLD_PREMIUM

            pct_change = ((current_price - yesterday_price) / yesterday_price) * 100 if yesterday_price else 0.0
            if abs(pct_change) < 5.0:
                continue

            direction = "🚀 SURGING" if pct_change > 0 else "🩸 CRASHING"
            display_name = "GOLD (24K)" if ticker == "GOLDBEES.NS" else ticker.replace(".NS", "")

            alert_lines.append(f"<b>{escape(display_name)}</b> is {direction}")
            alert_lines.append(f"Current Price: ₹{current_price:,.2f}")
            alert_lines.append(f"Movement: {pct_change:+.2f}%")
            alert_lines.append("")
            alert_count += 1
        except Exception as exc:
            logger.exception("Error checking volatility for %s: %s", ticker, exc)

    if alert_count == 0:
        return None, 0

    alert_lines.append(f"Checked at {datetime.now(IST):%Y-%m-%d %H:%M %Z}")
    return "\n".join(alert_lines), alert_count


def run_morning_briefing(config: AppConfig) -> int:
    message, success_count, failure_count = build_daily_report()
    summary = f"\n\nSummary: {success_count} succeeded, {failure_count} failed."
    sent = send_mobile_alert(message + summary, config)

    if sent:
        logger.info("Morning briefing delivered successfully.")
        return 0

    fallback = "🚨 <b>Daily briefing generation finished, but Telegram delivery failed.</b>"
    send_mobile_alert(fallback, config)
    return 1


def run_volatility_scan(config: AppConfig) -> int:
    message, alert_count = build_volatility_report()
    if not message:
        logger.info("No volatility alerts were generated.")
        return 0

    if send_mobile_alert(message, config):
        logger.info("Volatility alerts delivered successfully for %s asset(s).", alert_count)
        return 0

    logger.error("Volatility alert delivery failed.")
    return 1


def build_portfolio_payload() -> dict:
    portfolio_data = {}

    for ticker in TICKERS:
        snapshot = build_asset_snapshot(ticker)
        key = snapshot["display_name"]

        if snapshot["status"] == "success":
            portfolio_data[key] = {
                "price": snapshot["price"],
                "prediction": snapshot["prediction"],
                "status": "success",
                "type": snapshot["asset_type"],
            }
        else:
            portfolio_data[key] = {
                "price": None,
                "prediction": None,
                "status": "error",
                "message": snapshot["message"],
            }

    return portfolio_data


@app.route("/health", methods=["GET"])
def health() -> tuple[dict, int]:
    return jsonify({"status": "ok", "market_window": is_market_window(), "timestamp": datetime.now(IST).isoformat()}), 200


@app.route("/api/portfolio", methods=["GET"])
def get_portfolio():
    return jsonify(build_portfolio_payload())


@app.route("/api/run-morning", methods=["POST", "GET"])
def api_run_morning():
    try:
        config = load_config()
        exit_code = run_morning_briefing(config)
        return jsonify({"status": "ok" if exit_code == 0 else "failed", "exit_code": exit_code})
    except Exception as exc:
        logger.exception("Morning trigger failed: %s", exc)
        return jsonify({"status": "error", "message": str(exc)}), 500


@app.route("/api/run-volatility", methods=["POST", "GET"])
def api_run_volatility():
    try:
        config = load_config()
        exit_code = run_volatility_scan(config)
        return jsonify({"status": "ok" if exit_code == 0 else "failed", "exit_code": exit_code})
    except Exception as exc:
        logger.exception("Volatility trigger failed: %s", exc)
        return jsonify({"status": "error", "message": str(exc)}), 500


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Finance Tracker alert pipeline")
    parser.add_argument(
        "--job",
        choices=["morning", "volatility", "all", "serve"],
        default="serve",
        help="What to run: a single alert job, both jobs, or the optional Flask server.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    args = parse_args(argv)

    if args.job == "serve":
        config = load_config()
        app.run(debug=config.debug, host="0.0.0.0", port=config.port)
        return 0

    config = load_config()
    if args.job == "morning":
        return run_morning_briefing(config)
    if args.job == "volatility":
        return run_volatility_scan(config)

    morning_status = run_morning_briefing(config)
    volatility_status = run_volatility_scan(config)
    return 0 if morning_status == 0 and volatility_status == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())