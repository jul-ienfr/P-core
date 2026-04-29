# Historical account profiles

The account-learning pipeline is backfill-first and read-only. It consumes public Polymarket weather account trades that already exist locally, normalizes them into `account_trades`, and builds `shadow_profiles` JSON/Markdown artifacts for sizing, timing, city, market type, abstention, and price-bucket priors.

Commands:

```bash
python -m weather_pm.cli account-trades-backfill --input-json data/polymarket/account-analysis/weather_top10_profitable_account_patterns_20260427T093936Z.json
python -m weather_pm.cli account-trades-import --input-json data/polymarket/account-analysis/weather_top10_profitable_account_patterns_20260427T093936Z.json --output-json data/polymarket/account-learning/account_trades.json
python -m weather_pm.cli shadow-profiles-report --trades-json data/polymarket/account-learning/account_trades.json --output-json data/polymarket/account-learning/shadow_profiles.json --output-md data/polymarket/account-learning/shadow_profiles.md
python -m weather_pm.cli shadow-profiles-deep-dive --profiles-json data/polymarket/account-learning/shadow_profiles.json --wallet 0x... --output-md data/polymarket/account-learning/profile_0x....md
```

Safety constraints:

- No wallet integration.
- No signatures.
- No real `place_order` or `cancel_order` path.
- Artifacts are account-learning priors only; they do not authorize copy-trading.
