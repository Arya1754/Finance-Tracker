import json
import logging
import yfinance as yf
from pathlib import Path

logger = logging.getLogger("app")

class PortfolioManager:
    def __init__(self, portfolio_path: Path):
        self.portfolio_path = portfolio_path
        self.portfolio = self.load_portfolio()

    def load_portfolio(self) -> dict:
        try:
            if self.portfolio_path.exists():
                with open(self.portfolio_path, 'r') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logger.error(f"Error loading portfolio: {e}")
            return {}

    def get_summary(self) -> dict:
        summary = {
            "total_value": 0.0,
            "today_profit": 0.0,
            "largest_gainer": {"ticker": None, "pct": -float('inf')},
            "largest_loser": {"ticker": None, "pct": float('inf')},
            "holdings": {}
        }
        
        for ticker, data in self.portfolio.items():
            shares = data.get("shares", 0)
            if shares == 0:
                continue

            try:
                stock = yf.Ticker(ticker)
                history = stock.history(period="2d")
                if len(history) < 2:
                    continue
                
                prev_close = history["Close"].iloc[-2]
                current_price = history["Close"].iloc[-1]
                
                value = shares * current_price
                daily_profit = shares * (current_price - prev_close)
                pct_change = ((current_price - prev_close) / prev_close) * 100
                
                summary["total_value"] += value
                summary["today_profit"] += daily_profit
                
                summary["holdings"][ticker] = {
                    "shares": shares,
                    "value": value,
                    "current_price": current_price,
                    "prev_close": prev_close,
                    "daily_profit": daily_profit,
                    "pct_change": pct_change
                }
                
                if pct_change > summary["largest_gainer"]["pct"]:
                    summary["largest_gainer"] = {"ticker": ticker, "pct": pct_change}
                
                if pct_change < summary["largest_loser"]["pct"]:
                    summary["largest_loser"] = {"ticker": ticker, "pct": pct_change}

            except Exception as e:
                logger.error(f"Error calculating stats for {ticker}: {e}")

        # Handle case where all were 0
        if summary["largest_gainer"]["ticker"] is None:
            summary["largest_gainer"] = None
        if summary["largest_loser"]["ticker"] is None:
            summary["largest_loser"] = None
            
        return summary
