# Shanghai 2065032 — probe API historique ZSPD

- Généré: 2026-04-25T22:41:19Z
- Mode: lecture seule / paper-only
- Observations historiques trouvées: 13

## Endpoint status
| ok | status | endpoint | error |
|---|---:|---|---|
| True | 200 | https://api.weather.com/v1/location/ZSPD:9:CN/observations/historical.json |  |
| False | None | https://api.weather.com/v1/location/ZSPD/observations/historical.json | HTTPError: HTTP Error 400: Bad Request |
| False | None | https://api.weather.com/v1/location/31.15,121.803/observations/historical.json | HTTPError: HTTP Error 400: Bad Request |
| True | 200 | https://api.weather.com/v3/wx/observations/current |  |

## Max observation
- Max observé API: 55°F ≈ 12.8°C à 1777132800

## Décision
- Si la série historique n’est pas disponible/finale, rester en `SOURCE_CHECK_FIRST_THEN_PAPER_LIMIT`.
- Le signal provisoire NO 21°C reste valide seulement comme proxy.
- Aucun fill papier final tant que la source historique finalisée n’est pas disponible.