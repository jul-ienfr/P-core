# Polymarket météo — execution queue candidates 2026-04-25

Mode: **paper only**. Probabilité modèle = proxy normal autour du forecast max, pas calibration finale.

| Rank | Marché | Source | Comptes | Forecast | Proba proxy | YES ask | YES avg $50 | Edge ask | Reco |
|---:|---|---|---:|---:|---:|---:|---:|---:|---|
| 1 | Shanghai April 26 YES 24°C `2065035` | OK | 10 | 23.8 | 31.9% | 0.140 | 0.190 | +17.9% | paper_micro_yes_strict_limit |
| 2 | Seoul April 26 YES 23°C `2064873` | OK | 10 | 22.6 | 30.7% | 0.190 | 0.229 | +11.7% | watch_or_paper_yes_if_station_confirms |
| 3 | Tel Aviv April 26 YES 24°C `2064999` | MISSING | 9 | 24.5 | 29.8% | 0.010 | 0.069 | +28.8% | source_missing_do_not_trade |
| 4 | Munich April 26 YES 18°C `2064992` | OK | 11 | 18.3 | 31.4% | 0.320 | 0.320 | -0.6% | avoid_yes_market_price_too_high |
| 5 | Beijing April 26 YES 24°C `2065110` | OK | 8 | 24.4 | 30.7% | 0.200 | 0.229 | +10.7% | watch_or_paper_yes_if_station_confirms |
| 6 | Seoul April 27 YES 16°C `2074309` | OK | 6 | 16.5 | 29.8% | 0.140 | 0.198 | +15.8% | paper_micro_yes_strict_limit |
| 7 | Ankara April 26 YES 20°C `2064959` | OK | 9 | 20.4 | 30.7% | 0.350 | 0.368 | -4.3% | avoid_yes_market_price_too_high |
| 8 | London April 26 YES 18°C `2064826` | OK | 11 | 18.2 | 31.9% | 0.430 | 0.449 | -11.1% | avoid_yes_market_price_too_high |
| 9 | Shanghai April 27 YES 26°C `2074476` | OK | 3 | 25.8 | 31.9% | 0.330 | 0.349 | -1.1% | avoid_yes_market_price_too_high |
| 10 | Moscow April 26 YES 10°C `2065208` | MISSING | 9 | 10.0 | 32.3% | 0.360 | 0.384 | -3.7% | source_missing_do_not_trade |

## Lecture rapide
- **Shanghai April 26 YES 24°C**: ask 0.140, proba proxy 31.9%, edge ask +17.9%, reco `paper_micro_yes_strict_limit`. Source: https://www.wunderground.com/history/daily/cn/shanghai/ZSPD. Book $50 avg: 0.1898.
- **Seoul April 26 YES 23°C**: ask 0.190, proba proxy 30.7%, edge ask +11.7%, reco `watch_or_paper_yes_if_station_confirms`. Source: https://www.wunderground.com/history/daily/kr/incheon/RKSI. Book $50 avg: 0.2288.
- **Tel Aviv April 26 YES 24°C**: ask 0.010, proba proxy 29.8%, edge ask +28.8%, reco `source_missing_do_not_trade`. Source: absente. Book $50 avg: 0.0685.
- **Munich April 26 YES 18°C**: ask 0.320, proba proxy 31.4%, edge ask -0.6%, reco `avoid_yes_market_price_too_high`. Source: https://www.wunderground.com/history/daily/de/munich/EDDM. Book $50 avg: 0.32.
- **Beijing April 26 YES 24°C**: ask 0.200, proba proxy 30.7%, edge ask +10.7%, reco `watch_or_paper_yes_if_station_confirms`. Source: https://www.wunderground.com/history/daily/cn/beijing/ZBAA. Book $50 avg: 0.2293.

## Règle opérateur
- Réel argent: non, tant que la source station n’est pas relue directement.
- Paper: micro YES strict-limit sur Shanghai 24°C prioritaire; éventuellement Beijing/Seoul 27 si la source confirme.
- Éviter les candidats où le $50 avg détruit l’edge, même si top ask semble bon.