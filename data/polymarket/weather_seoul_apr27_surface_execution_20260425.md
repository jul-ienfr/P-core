# Seoul Apr 27 surface execution check

Station: RKSI — Incheon Intl Airport — forecast max 16.0°C — Mostly cloudy. Highs 15 to 17C and lows 9 to 11C.

| Rank | Market | Kind | Model prob | YES ask | $5 avg | $20 avg | Edge ask | Reco |
|---:|---|---|---:|---:|---:|---:|---:|---|
| 1 | `2074308` Will the highest temperature in Seoul be 15°C on April 27? | exact | 23.3% | 0.029 | 0.0298 | 0.0438 | +20.4% | paper_micro_strict_limit |
| 2 | `2074309` Will the highest temperature in Seoul be 16°C on April 27? | exact | 32.3% | 0.14 | 0.14 | 0.1794 | +18.3% | watch |
| 3 | `2074307` Will the highest temperature in Seoul be 14°C on April 27? | exact | 8.7% | 0.016 | 0.0191 | 0.0306 | +7.1% | watch |
| 4 | `2074310` Will the highest temperature in Seoul be 17°C on April 27? | exact | 23.3% | 0.2 | 0.2 | 0.2163 | +3.3% | watch |
| 5 | `2074306` Will the highest temperature in Seoul be 13°C or below on April 27? | threshold_low | 1.9% | 0.012 | 0.0209 | 0.0371 | +0.7% | avoid |
| 6 | `2074314` Will the highest temperature in Seoul be 21°C on April 27? | exact | 0.0% | 0.04 | 0.0426 | 0.0505 | -4.0% | avoid |
| 7 | `2074315` Will the highest temperature in Seoul be 22°C on April 27? | exact | 0.0% | 0.045 | 0.0461 | 0.0645 | -4.5% | avoid |
| 8 | `2074311` Will the highest temperature in Seoul be 18°C on April 27? | exact | 8.7% | 0.24 | 0.24 | 0.24 | -15.3% | avoid |
| 9 | `2074313` Will the highest temperature in Seoul be 20°C on April 27? | exact | 0.2% | 0.16 | 0.16 | 0.1751 | -15.8% | avoid |
| 10 | `2074312` Will the highest temperature in Seoul be 19°C on April 27? | exact | 1.7% | 0.2 | 0.2189 | 0.2452 | -18.3% | avoid |

## Paper suggestion
YES `2074308` limit <= **0.05**, size **$5 paper**, no market-buy.