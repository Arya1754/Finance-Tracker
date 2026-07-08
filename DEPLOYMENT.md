# Deployment

This project is best deployed as a scheduled Telegram alert pipeline, not as a public frontend app.

## What it does
- Sends a daily market-open briefing at 9:30 AM India time on weekdays.
- Checks for large daily moves during market hours and sends Telegram alerts when a move crosses the 5% threshold.
- Keeps your Telegram credentials out of the repository.

## Local setup
1. Create a `.env` file at the project root.
2. Copy the values from `.env.example` and replace the placeholders.
3. Run one of these commands:
   - `python app.py --job morning`
   - `python app.py --job volatility`
   - `python app.py --job serve` for the optional Flask health/API server.

## Free deployment
Use GitHub Actions so the pipeline runs without an always-on server.

1. Push the repository to GitHub.
2. In the GitHub repo settings, add these secrets:
   - `TELEGRAM_TOKEN`
   - `TELEGRAM_CHAT_ID`
3. Leave the workflow file at `.github/workflows/telegram-alerts.yml` enabled.
4. The workflow will run automatically:
   - `0 4 * * 1-5` for the 9:30 AM IST briefing.
   - `0 5-10 * * 1-5` for the market-hours volatility scans.

## Notes
- GitHub Actions is free for public repositories and usually generous for small private projects.
- If you want a web endpoint later, run `python app.py --job serve` on a host that supports long-running processes.
- The alert pipeline is already designed to keep going if one ticker fails; it logs the failure and continues with the rest.
