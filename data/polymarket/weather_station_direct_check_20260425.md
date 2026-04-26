# Weather station direct check + crude surface execution — 2026-04-25

Paper-only. Forecast extracted from Wunderground embedded app-root-state for Polymarket settlement station. Probabilities = crude normal proxy; strict-limit only; no real orders.

## Station checks
- Shanghai April 26 — station ZSPD — embedded_wunderground_forecast_ok — forecast_max=22.22°C — consensus=22C, 21C, 23C, 24C, 26C
- Tokyo April 26 — station RJTT — embedded_wunderground_forecast_ok — forecast_max=20.0°C — consensus=20C, 19C, 21C, 18C, 22C
- London April 26 — station EGLC — embedded_wunderground_forecast_ok — forecast_max=18.89°C — consensus=18C, 17C, 19C, 20C, 16C
- Munich April 26 — station EDDM — embedded_wunderground_forecast_ok — forecast_max=19.44°C — consensus=19C, 17C, 20C, 18C, 15C
- Seoul April 26 — station RKSI — embedded_wunderground_forecast_ok — forecast_max=17.22°C — consensus=20C or higher, 19C, 18C, 17C, 16C
- Singapore April 26 — station WSSS — embedded_wunderground_forecast_ok — forecast_max=31.67°C — consensus=31C, 32C, 34C, 33C, 30C
- Wellington April 26 — station NZWN — embedded_wunderground_forecast_ok — forecast_max=17.22°C — consensus=17C, 18C, 16C, 15C, 20C
- Taipei April 26 — station RCSS — embedded_wunderground_forecast_ok — forecast_max=27.78°C — consensus=29C, 27C, 28C, 30C, 31C

## Top paper-only candidates by crude edge
| reco | city/date | station max | bin | side | p_yes | YES ask | NO ask | edge | accounts |
|---|---|---:|---|---|---:|---:|---:|---:|---:|
| paper_micro_no_strict_limit | Seoul April 26 | 17.22 | 20C or higher | NO | 0.052 | 0.75 | 0.27 | 0.678 | 17 |
| paper_micro_yes_strict_limit | Seoul April 26 | 17.22 | 17C | YES | 0.276 | 0.007 | 0.995 | 0.269 | 17 |
| paper_micro_no_strict_limit | London April 26 | 18.89 | 18C | NO | 0.230 | 0.5 | 0.53 | 0.240 | 20 |
| paper_micro_no_strict_limit | Singapore April 26 | 31.67 | 33C | NO | 0.181 | 0.43 | 0.62 | 0.199 | 17 |
| paper_micro_yes_strict_limit | Munich April 26 | 19.44 | 21C or higher | YES | 0.225 | 0.029 | 0.984 | 0.196 | 20 |
| paper_micro_yes_strict_limit | Seoul April 26 | 17.22 | 16C | YES | 0.194 | 0.002 | 0.999 | 0.192 | 17 |
| paper_micro_yes_strict_limit | Seoul April 26 | 17.22 | 18C | YES | 0.240 | 0.06 | 0.944 | 0.180 | 17 |
| paper_micro_yes_strict_limit | London April 26 | 18.89 | 20C | YES | 0.206 | 0.04 | 0.964 | 0.167 | 20 |
| paper_micro_no_strict_limit | Wellington April 26 | 17.22 | 17C | NO | 0.276 | 0.47 | 0.56 | 0.164 | 17 |
| paper_micro_no_strict_limit | Tokyo April 26 | 20.0 | 20C | NO | 0.279 | 0.48 | 0.56 | 0.161 | 21 |
| paper_micro_no_strict_limit | Munich April 26 | 19.44 | 18C | NO | 0.168 | 0.38 | 0.68 | 0.152 | 20 |
| paper_micro_yes_strict_limit | Singapore April 26 | 31.67 | 31C | YES | 0.250 | 0.1 | 0.92 | 0.150 | 17 |
| paper_micro_yes_strict_limit | Munich April 26 | 19.44 | 20C | YES | 0.258 | 0.115 | 0.919 | 0.143 | 20 |
| paper_micro_no_strict_limit | Shanghai April 26 | 22.22 | 23C | NO | 0.240 | 0.38 | 0.63 | 0.130 | 20 |
| paper_micro_yes_strict_limit | Singapore April 26 | 31.67 | 30C | YES | 0.141 | 0.013 | 0.988 | 0.128 | 17 |
| paper_micro_yes_strict_limit | Shanghai April 26 | 22.22 | 21C | YES | 0.194 | 0.066 | 0.935 | 0.128 | 20 |
| paper_micro_no_strict_limit | Taipei April 26 | 27.78 | 29C | NO | 0.194 | 0.33 | 0.68 | 0.126 | 16 |
| watch_or_paper_no_if_station_confirms | Munich April 26 | 19.44 | 19C | NO | 0.266 | 0.42 | 0.63 | 0.104 | 20 |
| watch_or_paper_yes_if_station_confirms | Tokyo April 26 | 20.0 | 18C | YES | 0.105 | 0.023 | 0.985 | 0.082 | 21 |
| watch_or_paper_yes_if_station_confirms | Taipei April 26 | 27.78 | 26C | YES | 0.129 | 0.05 | 0.951 | 0.079 | 16 |
| watch_or_paper_no_if_station_confirms | Taipei April 26 | 27.78 | 28C | NO | 0.276 | 0.36 | 0.65 | 0.074 | 16 |
| watch_or_paper_no_if_station_confirms | Singapore April 26 | 31.67 | 32C | NO | 0.272 | 0.37 | 0.66 | 0.068 | 17 |
| watch_or_paper_no_if_station_confirms | Singapore April 26 | 31.67 | 34C | NO | 0.074 | 0.17 | 0.86 | 0.066 | 17 |
| watch_or_paper_yes_if_station_confirms | Shanghai April 26 | 22.22 | 20C | YES | 0.084 | 0.019 | 0.991 | 0.065 | 20 |
| watch_or_paper_no_if_station_confirms | Shanghai April 26 | 22.22 | 22C | NO | 0.276 | 0.35 | 0.66 | 0.064 | 20 |
| watch_or_paper_yes_if_station_confirms | Tokyo April 26 | 20.0 | 22C | YES | 0.105 | 0.045 | 0.964 | 0.060 | 21 |
| watch_or_paper_no_if_station_confirms | Wellington April 26 | 17.22 | 16C | NO | 0.194 | 0.33 | 0.75 | 0.056 | 17 |
| watch_or_paper_yes_if_station_confirms | Wellington April 26 | 17.22 | 15C | YES | 0.084 | 0.03 | 0.977 | 0.054 | 17 |
| watch_or_paper_yes_if_station_confirms | Taipei April 26 | 27.78 | 27C | YES | 0.240 | 0.19 | 0.82 | 0.051 | 16 |
| avoid_or_watch | Wellington April 26 | 17.22 | 20C | YES | 0.042 | 0.006 | 0.998 | 0.036 | 17 |
| avoid_or_watch | London April 26 | 18.89 | 19C | NO | 0.278 | 0.32 | 0.69 | 0.032 | 20 |
| avoid_or_watch | Seoul April 26 | 17.22 | 19C | NO | 0.129 | 0.2 | 0.84 | 0.031 | 17 |
| avoid_or_watch | Munich April 26 | 19.44 | 17C | YES | 0.065 | 0.04 | 0.969 | 0.025 | 20 |
| avoid_or_watch | Seoul April 26 | 17.22 | 14C | YES | 0.022 | 0.001 | - | 0.021 | 17 |
| avoid_or_watch | Taipei April 26 | 27.78 | 31C | NO | 0.022 | 0.049 | 0.96 | 0.018 | 16 |