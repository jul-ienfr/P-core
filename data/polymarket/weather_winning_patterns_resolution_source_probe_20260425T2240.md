# Polymarket météo — probe sources de résolution

- Généré: 2026-04-25T22:38:26Z
- Mode: lecture seule / paper-only

## Sources extraites depuis Gamma
| market | question | source hints | status |
|---|---|---|---|
| 2065210 | Will the highest temperature in Moscow be 12°C on April 26? | for this market will be information from NOAA, specifically the highest reading under the "Temp" column on the specified date once information is finalized for all hours on that date, available here: https://www ; for... | ok |
| 2065032 | Will the highest temperature in Shanghai be 21°C on April 26? | for this market will be information from Wunderground, specifically the highest temperature recorded for all times on this day by the Forecast for the Shanghai Pudong International Airport Station once information is ... | ok |
| 2074474 | Will the highest temperature in Shanghai be 24°C on April 27? | for this market will be information from Wunderground, specifically the highest temperature recorded for all times on this day by the Forecast for the Shanghai Pudong International Airport Station once information is ... | ok |
| 2065108 | Will the highest temperature in Beijing be 22°C on April 26? | for this market will be information from Wunderground, specifically the highest temperature recorded for all times on this day by the Forecast for the Beijing Capital International Airport Station once information is ... | ok |
| 2064990 | Will the highest temperature in Munich be 16°C on April 26? | for this market will be information from Wunderground, specifically the highest temperature recorded for all times on this day by the Forecast for the Munich Airport Station once information is finalized, available he... | ok |

## Conclusion opérateur
- Gamma donne les questions et parfois les règles, mais la source officielle doit être lisible et vérifiée avant tout fill papier.
- Si `source_hints` est vide ou ambigu: ouvrir/extraire les règles complètes du marché avant exécution.
- Ne pas inférer une station depuis la ville seule.