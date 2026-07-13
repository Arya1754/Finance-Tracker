import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Base paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"
MODELS_DIR = BASE_DIR / "backend" / "models"

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)
MODELS_DIR.mkdir(parents=True, exist_ok=True)

# Tickers to track
TICKERS = [
    "BANDHANBNK.NS",
    "ADANIPOWER.NS",
    "WSTCSTPAPR.NS",
    "POONAWALLA.NS",
    "ZOTA.NS",
    "GOLDBEES.NS"
]

# Telegram config
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Physical Gold Premium to match Mumbai 24K Spot rates over ETF
PHYSICAL_GOLD_PREMIUM = 1.17

# Logging Setup
def setup_logging():
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    formatter = logging.Formatter(log_format)

    # General App Logger
    app_logger = logging.getLogger("app")
    app_logger.setLevel(logging.INFO)
    app_handler = logging.FileHandler(LOGS_DIR / "app.log")
    app_handler.setFormatter(formatter)
    app_logger.addHandler(app_handler)
    if not any(isinstance(h, logging.StreamHandler) for h in app_logger.handlers):
        sh = logging.StreamHandler()
        sh.setFormatter(formatter)
        app_logger.addHandler(sh)

    # Telegram Logger
    telegram_logger = logging.getLogger("telegram")
    telegram_logger.setLevel(logging.INFO)
    telegram_handler = logging.FileHandler(LOGS_DIR / "telegram.log")
    telegram_handler.setFormatter(formatter)
    telegram_logger.addHandler(telegram_handler)
    if not any(isinstance(h, logging.StreamHandler) for h in telegram_logger.handlers):
        sh = logging.StreamHandler()
        sh.setFormatter(formatter)
        telegram_logger.addHandler(sh)

    # Prediction Logger
    prediction_logger = logging.getLogger("prediction")
    prediction_logger.setLevel(logging.INFO)
    prediction_handler = logging.FileHandler(LOGS_DIR / "prediction.log")
    prediction_handler.setFormatter(formatter)
    prediction_logger.addHandler(prediction_handler)
    if not any(isinstance(h, logging.StreamHandler) for h in prediction_logger.handlers):
        sh = logging.StreamHandler()
        sh.setFormatter(formatter)
        prediction_logger.addHandler(sh)

setup_logging()
