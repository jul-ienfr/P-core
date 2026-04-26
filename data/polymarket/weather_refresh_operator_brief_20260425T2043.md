# Weather operator refresh brief — 2026-04-25 20:43 CEST

## Verdict
- Reco globale: `paper_micro_only`
- Confiance: `profitable_weather_signal_with_execution_caution`
- Raison: unique_profitable_weather_accounts_match_live_markets_but_extreme_price_blocks_normal_sizing
- Règle sécurité: paper-only; pas de sizing normal tant que `extreme_price`, quote manquante, ou daily officiel pending.

## Synthèse live
- Marchés matchés: 8 — 2065018, 2065028, 2074350, 2074460, 2064908, 2074470, 2074360, 2064918
- Comptes uniques météo rentables: 10 (10 weather-heavy)
- Row-level matches: 40
- Villes: Hong Kong, Dallas

## Actions immédiates
- `poll_direct_resolution_source`
- `paper_micro_order_with_strict_limit_and_fill_tracking`
- `do_not_use_normal_size_until_extreme_price_clears`

## Cartes marchés live
| market | ville/date | blocker | verdict | matches | top comptes | direct source | next |
|---|---|---|---|---:|---|---|---|
| 2065018 | Hong Kong April 26 | `extreme_price` | `paper_micro` | 5 | Poligarch $50,120 / Maskache2 $49,973 / HenryTheAtmoPhD $45,563 | https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=rhrread&lang=en | poll_direct_resolution_source, paper_micro_order_with_strict_limit_and_fill_tracking |
| 2065028 | Hong Kong April 26 | `none` | `watch_or_paper` | 5 | Poligarch $50,120 / Maskache2 $49,973 / HenryTheAtmoPhD $45,563 | https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=rhrread&lang=en | poll_direct_resolution_source, paper_order_with_limit_and_fill_tracking |
| 2074350 | Dallas April 27 | `missing_tradeable_quote` | `watch_or_paper` | 5 | Handsanitizer23 $71,174 / Shoemaker34 $33,960 / khalidakup $29,586 | https://www.wunderground.com/history/daily/us/tx/dallas/KDAL | poll_direct_resolution_source, wait_for_executable_depth |
| 2074460 | Hong Kong April 27 | `missing_tradeable_quote` | `watch_or_paper` | 5 | Poligarch $50,120 / Maskache2 $49,973 / HenryTheAtmoPhD $45,563 | https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=rhrread&lang=en | poll_direct_resolution_source, wait_for_executable_depth |
| 2064908 | Dallas April 26 | `missing_tradeable_quote` | `watch_or_paper` | 5 | Handsanitizer23 $71,174 / Shoemaker34 $33,960 / khalidakup $29,586 | https://www.wunderground.com/history/daily/us/tx/dallas/KDAL | poll_direct_resolution_source, wait_for_executable_depth |
| 2074470 | Hong Kong April 27 | `missing_tradeable_quote` | `watch_or_paper` | 5 | Poligarch $50,120 / Maskache2 $49,973 / HenryTheAtmoPhD $45,563 | https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=rhrread&lang=en | poll_direct_resolution_source, wait_for_executable_depth |
| 2074360 | Dallas April 27 | `missing_tradeable_quote` | `watch_or_paper` | 5 | Handsanitizer23 $71,174 / Shoemaker34 $33,960 / khalidakup $29,586 | https://www.wunderground.com/history/daily/us/tx/dallas/KDAL | poll_direct_resolution_source, wait_for_executable_depth |
| 2064918 | Dallas April 26 | `high_slippage_risk` | `watch_or_paper` | 5 | Handsanitizer23 $71,174 / Shoemaker34 $33,960 / khalidakup $29,586 | https://www.wunderground.com/history/daily/us/tx/dallas/KDAL | poll_direct_resolution_source, wait_for_tighter_spread |

## Artefacts
- Refresh wrapper: `data/polymarket/weather_operator_refresh_20260425T2043.json`
- Operator refreshed: `data/polymarket/weather_strategy_operator_report_refreshed_20260425T2043.json`
- Account summary: `data/polymarket/weather_profitable_accounts_operator_summary_20260425T2043.json`
- Brief: `data/polymarket/weather_refresh_operator_brief_20260425T2043.md`
