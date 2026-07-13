import yfinance as yf
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from datetime import datetime, timezone
import logging

logger = logging.getLogger("app")
analyzer = SentimentIntensityAnalyzer()

def get_news_sentiment(ticker: str) -> dict:
    """
    Fetches news for a ticker and calculates a weighted sentiment score.
    Weights: Today 50%, Yesterday 30%, Older 20%. Ignore > 3 days old.
    """
    try:
        stock = yf.Ticker(ticker)
        news = stock.news
        if not news:
            return {"label": "Neutral", "score": 0.0}

        today = datetime.now(timezone.utc).date()
        
        weighted_score = 0.0
        total_weight = 0.0

        for article in news:
            title = article.get("title", "")
            if not title:
                continue
            
            # yfinance news timestamp is usually in seconds
            pub_time = article.get("providerPublishTime")
            if not pub_time:
                continue
                
            article_date = datetime.fromtimestamp(pub_time, tz=timezone.utc).date()
            days_old = (today - article_date).days
            
            if days_old > 3:
                continue
                
            sentiment = analyzer.polarity_scores(title)
            compound = sentiment["compound"]
            
            if days_old == 0:
                weight = 0.50
            elif days_old == 1:
                weight = 0.30
            else:
                weight = 0.20
                
            weighted_score += (compound * weight)
            total_weight += weight

        if total_weight == 0:
            return {"label": "Neutral", "score": 0.0}

        final_score = weighted_score / total_weight
        
        if final_score >= 0.05:
            label = "Bullish"
        elif final_score <= -0.05:
            label = "Bearish"
        else:
            label = "Neutral"
            
        return {"label": label, "score": round(final_score, 4)}

    except Exception as e:
        logger.error(f"Error fetching sentiment for {ticker}: {e}")
        return {"label": "Neutral", "score": 0.0}
