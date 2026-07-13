import argparse
import sys
import logging
from backend.app import app

logger = logging.getLogger("app")

def main():
    parser = argparse.ArgumentParser(description="Run Portfolio Intelligence Jobs")
    parser.add_argument("--job", choices=["morning", "volatility"], required=True, help="Job to run")
    args = parser.parse_args()
    
    # Use Flask test client to hit our own endpoints internally
    with app.test_client() as client:
        if args.job == "morning":
            logger.info("Executing morning job via run_jobs.py")
            response = client.post('/api/run-morning')
            logger.info(f"Morning Job Status: {response.status_code}")
            logger.info(f"Response: {response.get_json()}")
            
        elif args.job == "volatility":
            logger.info("Executing volatility job via run_jobs.py")
            response = client.post('/api/run-volatility')
            logger.info(f"Volatility Job Status: {response.status_code}")
            logger.info(f"Response: {response.get_json()}")

if __name__ == "__main__":
    main()
