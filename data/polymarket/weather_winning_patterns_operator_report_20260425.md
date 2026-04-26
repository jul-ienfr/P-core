# Polymarket météo — patterns gagnants

## Synthèse
- Comptes météo positifs: 10,050
- Weather-heavy/mixed: 85
- Top80 analysés: 80

## Règles opérateur
- **R1 surface complète** — Group all markets by city/date/unit before scoring isolated bins.
- **R2 side par source** — Choose YES/NO from the official settlement source, not from trader consensus alone.
- **R3 incohérences voisines** — Prioritize thresholds/bins whose prices contradict neighboring bins or the implied temperature distribution.
- **R4 consensus = carte** — Use profitable-account activity to select surfaces to inspect; require source and book validation before paper/live.
- **R5 strict limit** — Enter only at strict limit when spread/slippage keep positive net edge.
- **R6 caps portefeuille** — Prefer many tiny independent edges over one large conviction; cap by city/date/surface.
- **R7 proxy séparé** — Treat forecast proxies as filters only; official source pending means watch/paper-only at most.

## Surfaces consensus prioritaires
| surface | side | comptes | signaux | statut |
|---|---:|---:|---:|---|
| Moscow April 26 12°C | NO | 9 | 32 | source_proxy_aligned_needs_official_check |
| Shanghai April 26 21°C | NO | 10 | 30 | source_proxy_aligned_needs_official_check |
| Beijing April 26 22°C | NO | 8 | 23 | source_proxy_aligned_needs_official_check |
| Seoul April 26 17°C | NO | 10 | 28 | source_proxy_aligned_needs_official_check |
| Munich April 26 16°C | NO | 11 | 38 | source_proxy_aligned_needs_official_check |
| Shanghai April 27 24°C | NO | 3 | 29 | source_proxy_aligned_needs_official_check |
| Seoul April 27 15°C | NO | 6 | 23 | source_proxy_aligned_needs_official_check |
| London April 26 20°C | NO | 11 | 27 | source_proxy_aligned_needs_official_check |
| Munich April 27 18°C | NO | 5 | 34 | source_proxy_aligned_needs_official_check |
| Ankara April 26 18°C | NO | 9 | 32 | source_proxy_aligned_needs_official_check |
| Tel Aviv April 26 22°C | NO | 9 | 24 | source_proxy_aligned_needs_official_check |
| Denver April 26 64°F | NO | 6 | 20 | source_proxy_aligned_needs_official_check |

## Candidats orderbook
| surface | label | side | ask | source | tradability |
|---|---:|---:|---:|---|---|
| Moscow April 26 | 12°C | NO | 0.987 | proxy_aligned | ok |
| Shanghai April 26 | 21°C | NO | 0.954 | proxy_aligned | ok |
| Beijing April 26 | 22°C | NO | 0.995 | proxy_aligned | extreme_or_missing |
| Munich April 26 | 16°C | NO | 0.991 | proxy_aligned | ok |
| Shanghai April 27 | 24°C | NO | 0.965 | proxy_aligned | ok |
| Seoul April 27 | 15°C | NO | 0.978 | proxy_aligned | ok |
| London April 26 | 20°C | NO | 0.975 | proxy_aligned | ok |
| Munich April 27 | 18°C | NO | 0.93 | proxy_aligned | ok |
| Seoul April 26 | 17°C | NO | 0.992 | proxy_aligned | ok |
| Ankara April 26 | 18°C | NO | 0.978 | proxy_aligned | ok |
| Tel Aviv April 26 | 22°C | NO | 0.993 | proxy_aligned | ok |
| Denver April 26 | 64°F | NO | 0.955 | proxy_aligned | ok |

## Brief
Météo patterns gagnants: 85 comptes weather-heavy/mixed sur 10050 positifs. Pattern dominant: surface ville/date complète + source officielle + strict-limit. Top surface: Moscow April 26 NO 12°C.
